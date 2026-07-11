"""Tests for the review-queue / ticket domain (``api/routers/review_queue.py``) — off the gate.

Fully in-isolation per the build contract: every test drives a throwaway
``FastAPI(); app.include_router(review_queue.router)`` with a ``TestClient`` and a tmp JSONL
store — nothing imports ``api/main.py``, so a failure points at the review-queue seam, not at
unrelated wiring. The auth dev-default (no headers → ``approver``) is exercised alongside
explicit viewer/reviewer/approver headers to pin the RBAC.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.review_store import get_review_store
from api.routers import review_queue

# Explicit principals via the dev-shim auth headers (api/auth.py). No headers == approver.
VIEWER = {"X-PipeGuard-Role": "viewer"}
REVIEWER = {"X-PipeGuard-Actor": "a.rivera", "X-PipeGuard-Role": "reviewer"}
APPROVER = {"X-PipeGuard-Actor": "b.chen", "X-PipeGuard-Role": "approver"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient over a local app mounting ONLY the review router, backed by a tmp JSONL store.

    The store path + choice are set per test so tickets never leak between tests or into the repo.
    """
    monkeypatch.setenv("PIPEGUARD_REVIEW_PATH", str(tmp_path / "tickets.jsonl"))
    monkeypatch.delenv("PIPEGUARD_REVIEW_STORE", raising=False)  # default: offline JSONL
    app = FastAPI()
    app.include_router(review_queue.router)
    return TestClient(app)


def _ticket(**over):
    body = {
        "run_id": "mock_run_01",
        "sample_id": "S4",
        "gate": "preflight",
        "verdict": "escalate",
        "rule_id": "PROV-001",
        "title": "SampleSheet/demux barcode mismatch",
        "priority": "high",
    }
    body.update(over)
    return body


def _create(client, headers=REVIEWER, **over):
    resp = client.post("/api/review/tickets", json=_ticket(**over), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _act(client, tid, action, headers=None):
    """POST a lifecycle action, defaulting to the permissive dev principal (approver)."""
    return client.post(
        f"/api/review/tickets/{tid}/action", json={"action": action}, headers=headers or {}
    )


def _assign(client, tid, assignee, headers=None):
    """POST an assignment (assignee=None unassigns), defaulting to the dev principal (approver)."""
    return client.post(
        f"/api/review/tickets/{tid}/assign", json={"assignee": assignee}, headers=headers or {}
    )


def _seed(created_at, *, status="open", **over):
    """Write a ticket straight to the store with a controlled ``created_at``/``status``.

    The ``created_at`` is server-authored at open-time, so it can't be set through the API — the
    ``since`` window + total-header tests seed the store directly (the fixture's monkeypatched
    ``PIPEGUARD_REVIEW_PATH`` is already active because the test requests the ``client`` fixture).
    """
    record = {
        **_ticket(**over),
        "id": uuid.uuid4().hex,
        "schema_version": review_queue.REVIEW_SCHEMA_VERSION,
        "created_at": created_at,
        "status": status,
        "opened_by": "seed",
        "assignee": None,
        "actions": [],
    }
    get_review_store().create(record)
    return record


# --- create / read ---------------------------------------------------------------------------


def test_create_ticket_authors_server_fields_and_snapshots_context(client):
    t = _create(client, headers=REVIEWER)
    # Server-authored fields: id/created_at minted, status opens, opener == principal, empty trail.
    assert t["id"] and t["created_at"]
    assert t["status"] == "open"
    assert t["opened_by"] == "a.rivera"  # captured from the authenticated actor, not the body
    assert t["actions"] == []
    assert t["schema_version"] == review_queue.REVIEW_SCHEMA_VERSION
    # The decided-sample context is stored verbatim (a snapshot), never recomputed.
    assert (t["gate"], t["verdict"], t["rule_id"], t["priority"]) == (
        "preflight",
        "escalate",
        "PROV-001",
        "high",
    )


def test_create_rejects_smuggled_server_fields_and_bad_input(client):
    # extra="forbid": a client can't set the server-authored fields.
    assert client.post("/api/review/tickets", json=_ticket(status="resolved")).status_code == 422
    assert client.post("/api/review/tickets", json=_ticket(opened_by="root")).status_code == 422
    assert client.post("/api/review/tickets", json=_ticket(actions=[])).status_code == 422
    # Closed enums + charset locks.
    assert client.post("/api/review/tickets", json=_ticket(gate="bogus")).status_code == 422
    assert client.post("/api/review/tickets", json=_ticket(priority="urgent")).status_code == 422
    assert client.post("/api/review/tickets", json=_ticket(rule_id="bad id")).status_code == 422
    assert client.post("/api/review/tickets", json=_ticket(title="   ")).status_code == 422


def test_list_and_filter(client):
    a = _create(client, run_id="mock_run_01", rule_id="PROV-001")
    b = _create(client, run_id="mock_run_02", rule_id="QC-Q30")
    _create(client, run_id="mock_run_01", rule_id="QC-Q30")

    assert len(client.get("/api/review/tickets").json()) == 3  # all, any role (viewer reads too)
    assert len(client.get("/api/review/tickets", headers=VIEWER).json()) == 3

    by_run = client.get("/api/review/tickets", params={"run_id": "mock_run_01"}).json()
    assert all(t["run_id"] == "mock_run_01" for t in by_run) and len(by_run) == 2
    assert a["id"] in {t["id"] for t in by_run}

    by_rule = client.get("/api/review/tickets", params={"rule_id": "QC-Q30"}).json()
    assert all(t["rule_id"] == "QC-Q30" for t in by_rule) and len(by_rule) == 2

    # Acknowledge one so a status filter has something to select.
    _act(client, b["id"], "acknowledge")
    in_review = client.get("/api/review/tickets", params={"status": "in_review"}).json()
    assert [t["id"] for t in in_review] == [b["id"]]
    assert len(client.get("/api/review/tickets", params={"status": "open"}).json()) == 2

    # Unknown status -> 400 (closed vocabulary), never a silent empty result.
    assert client.get("/api/review/tickets", params={"status": "nope"}).status_code == 400


# --- action lifecycle + status transitions ---------------------------------------------------


def test_action_lifecycle_records_trail_and_transitions_status(client):
    t = _create(client)
    tid = t["id"]

    # open -> in_review (acknowledge, reviewer allowed).
    ack = _act(client, tid, "acknowledge", headers=REVIEWER)
    assert ack.status_code == 200
    body = ack.json()
    assert body["status"] == "in_review"
    assert body["actions"][-1]["action"] == "acknowledge"
    assert body["actions"][-1]["actor"] == "a.rivera"  # server-captured actor
    assert body["actions"][-1]["at"]  # timestamp anchor for the median-review-time KPI

    # in_review -> resolved (resolve, approver).
    res = _act(client, tid, "resolve", headers=APPROVER)
    assert res.json()["status"] == "resolved"
    assert [a["action"] for a in res.json()["actions"]] == ["acknowledge", "resolve"]

    # resolved -> open (reopen).
    reo = _act(client, tid, "reopen", headers=REVIEWER)
    assert reo.json()["status"] == "open"
    assert len(reo.json()["actions"]) == 3


def test_illegal_transitions_are_409(client):
    tid = _create(client)["id"]
    # reopen from open is illegal (409, not 404/403).
    assert _act(client, tid, "reopen").status_code == 409
    # Resolve it, then a second resolve is illegal from 'resolved'.
    assert _act(client, tid, "resolve").status_code == 200
    assert _act(client, tid, "resolve").status_code == 409
    # Acknowledge from 'resolved' is also illegal.
    assert _act(client, tid, "acknowledge").status_code == 409


def test_suppress_resolves_and_is_keyed_by_rule_id(client):
    tid = _create(client, rule_id="PROV-001")["id"]
    res = _act(client, tid, "suppress", headers=APPROVER)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "resolved"
    assert body["actions"][-1]["action"] == "suppress"
    # 'suppress' acts on the ticket's issue-class: its rule_id is unchanged and carries the key.
    assert body["rule_id"] == "PROV-001"


def test_unknown_ticket_action_is_404(client):
    assert _act(client, "deadbeef", "acknowledge").status_code == 404


def test_action_body_rejects_unknown_action_and_smuggled_fields(client):
    tid = _create(client)["id"]
    assert _act(client, tid, "delete").status_code == 422
    # extra="forbid": a caller can't inject the server-authored actor/at.
    assert (
        client.post(
            f"/api/review/tickets/{tid}/action", json={"action": "acknowledge", "actor": "root"}
        ).status_code
        == 422
    )


# --- RBAC ------------------------------------------------------------------------------------


def test_viewer_cannot_create(client):
    # A viewer is 403ed by require_role at the write boundary (but may still read the queue).
    assert client.post("/api/review/tickets", json=_ticket(), headers=VIEWER).status_code == 403


def test_reviewer_can_resolve_and_suppress(client):
    # Design (README §5.5): a reviewer resolves/suppresses hold/rerun tickets. The
    # escalation→approver nuance is enforced in the UI (a reviewer never sees Resolve on an
    # escalate ticket), not at this API level; a viewer still cannot act (see below).
    tid = _create(client, headers=REVIEWER)["id"]
    assert _act(client, tid, "acknowledge", headers=REVIEWER).status_code == 200
    assert _act(client, tid, "resolve", headers=REVIEWER).status_code == 200
    # A reviewer can also suppress a fresh ticket, and an approver can resolve too.
    tid2 = _create(client, headers=REVIEWER)["id"]
    assert _act(client, tid2, "suppress", headers=REVIEWER).status_code == 200
    tid3 = _create(client, headers=REVIEWER)["id"]
    assert _act(client, tid3, "resolve", headers=APPROVER).status_code == 200


def test_viewer_cannot_act(client):
    tid = _create(client)["id"]
    assert _act(client, tid, "acknowledge", headers=VIEWER).status_code == 403


# --- assign (the review↔kanban owner link) ---------------------------------------------------


def test_create_ticket_is_unassigned_by_default(client):
    # A freshly opened ticket has no owner until it is assigned.
    assert _create(client, headers=REVIEWER)["assignee"] is None


def test_assign_sets_assignee_records_audit_and_unassigns(client):
    t = _create(client, headers=REVIEWER)
    tid = t["id"]

    # Reviewer assigns to a user id.
    res = _assign(client, tid, "m.chen", headers=REVIEWER)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["assignee"] == "m.chen"
    assert body["status"] == "open"  # assigning is NOT a status transition
    assert body["actions"][-1]["action"] == "assign"
    assert body["actions"][-1]["actor"] == "a.rivera"  # server-captured actor, not the body
    assert body["actions"][-1]["at"]

    # Reassigning appends another audit entry and overwrites the owner.
    res = _assign(client, tid, "b.chen", headers=APPROVER)
    assert res.json()["assignee"] == "b.chen"

    # Unassign via null.
    res = _assign(client, tid, None, headers=REVIEWER)
    assert res.json()["assignee"] is None
    assert [a["action"] for a in res.json()["actions"]] == ["assign", "assign", "assign"]


def test_assign_rbac_validation_and_unknown_ticket(client):
    tid = _create(client, headers=REVIEWER)["id"]
    # A viewer cannot assign (write boundary), though it may still read the queue.
    assert _assign(client, tid, "m.chen", headers=VIEWER).status_code == 403
    # A charset-violating assignee is a 422 (can't forge a JSONL line / carry a control char).
    assert _assign(client, tid, "bad id", headers=REVIEWER).status_code == 422
    # extra="forbid": a caller can't smuggle the server-authored audit actor.
    assert (
        client.post(
            f"/api/review/tickets/{tid}/assign",
            json={"assignee": "m.chen", "actor": "root"},
            headers=REVIEWER,
        ).status_code
        == 422
    )
    # Unknown ticket -> 404.
    assert _assign(client, "deadbeef", "m.chen", headers=REVIEWER).status_code == 404


def test_assign_is_not_a_transition_action(client):
    # 'assign' is an audit event, not a status transition: it is absent from _ACTION_RULES and the
    # /action endpoint rejects it (422), so act_on_ticket never indexes the table with it.
    assert "assign" not in review_queue._ACTION_RULES
    tid = _create(client, headers=REVIEWER)["id"]
    assert _act(client, tid, "assign").status_code == 422


# --- recency window (`since`) + total-count header -------------------------------------------


def test_since_window_and_total_header(client):
    # Two tickets on a known timeline (seeded straight to the store to control created_at).
    _seed("2026-01-01T00:00:00+00:00", rule_id="OLD-1")
    _seed("2026-07-01T00:00:00+00:00", rule_id="NEW-1")

    # No `since`: both returned (created_at-ascending), header total == full count.
    r = client.get("/api/review/tickets")
    assert r.status_code == 200
    assert [t["rule_id"] for t in r.json()] == ["OLD-1", "NEW-1"]
    assert r.headers["X-PipeGuard-Ticket-Total"] == "2"

    # `since` mid-window: only the newer ticket, but the header still reports the FULL total.
    r = client.get("/api/review/tickets", params={"since": "2026-06-01"})
    assert [t["rule_id"] for t in r.json()] == ["NEW-1"]
    assert r.headers["X-PipeGuard-Ticket-Total"] == "2"

    # `since` boundary is inclusive (created_at on the since date passes).
    assert len(client.get("/api/review/tickets", params={"since": "2026-07-01"}).json()) == 1

    # `since` after everything: empty body, header total unchanged.
    r = client.get("/api/review/tickets", params={"since": "2027-01-01"})
    assert r.json() == []
    assert r.headers["X-PipeGuard-Ticket-Total"] == "2"

    # Garbage `since` -> 400 (closed contract), never a silent empty result.
    assert client.get("/api/review/tickets", params={"since": "not-a-date"}).status_code == 400


def test_total_header_scopes_to_status_and_ignores_since(client):
    _seed("2026-01-01T00:00:00+00:00", status="resolved", rule_id="R-OLD")
    _seed("2026-07-01T00:00:00+00:00", status="resolved", rule_id="R-NEW")
    _seed("2026-07-01T00:00:00+00:00", status="open", rule_id="O-NEW")

    r = client.get("/api/review/tickets", params={"status": "resolved", "since": "2026-06-01"})
    # Only the recent resolved ticket is returned...
    assert [t["rule_id"] for t in r.json()] == ["R-NEW"]
    # ...but the header counts ALL resolved (ignores `since`), not open, not the recent slice.
    assert r.headers["X-PipeGuard-Ticket-Total"] == "2"


# --- resilience + off-gate -------------------------------------------------------------------


def test_store_failure_returns_503_without_leak(client, monkeypatch):
    class _Boom:
        def create(self, _record):
            raise OSError("disk full at /secret/path")

    monkeypatch.setattr("api.routers.review_queue.get_review_store", _Boom)
    resp = client.post("/api/review/tickets", json=_ticket(), headers=REVIEWER)
    assert resp.status_code == 503 and "unavailable" in resp.json()["detail"]
    assert "disk full" not in resp.text and "/secret/path" not in resp.text  # no path/DSN leak


def test_router_never_touches_the_decision_domain(client):
    # Structural: no decision-core symbol is imported into the review-queue module, so it cannot
    # call the gate, read the ledger, or recompute a verdict (ADR-0001).
    for name in ("run_gate", "EventLedger", "load_run", "triage_card", "DEFAULT_RUNBOOK"):
        assert name not in vars(review_queue)
    # Behavioral: the ticket stores whatever gate/verdict the client passed, verbatim — proving
    # the endpoint never consulted the deterministic gate to derive them.
    t = _create(client, gate="qc", verdict="proceed")
    assert (t["gate"], t["verdict"]) == ("qc", "proceed")
