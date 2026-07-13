"""Tests for the Settings/config AUTHORING seam (T-051) — override store, OFF the decision gate.

Driven fully IN ISOLATION per the build contract: each test builds its OWN tiny FastAPI app that
mounts ONLY ``api/routers/settings.py`` and drives it with a TestClient. Nothing here imports
``api/main.py`` — a failure points at the settings seam, not at unrelated wiring. Offline: the
JSONL store is a tmp file (``BAYLEAF_SETTINGS_PATH``) and the SQLite store a tmp DB, so no test
touches the repo or the network.

Auth is the dev-shim (``api/auth.py``): with NO headers the actor is ``dev``/``approver`` (clears
every gate), and the ``X-Bayleaf-Role`` header lets a test act as a lower role to prove the
403 gates.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.settings import router
from api.settings_store import (
    JsonlSettingsStore,
    SqliteSettingsStore,
    get_settings_store,
)


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """A throwaway app mounting ONLY the settings router, backed by a tmp JSONL store."""
    monkeypatch.setenv("BAYLEAF_SETTINGS_PATH", str(tmp_path / "settings.jsonl"))
    monkeypatch.delenv("BAYLEAF_SETTINGS_STORE", raising=False)
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)


def _body(**over):
    body = {
        "name": "wgs_germline",
        # An arbitrary override payload — stored as-is, only lenient-sanity-checked (not schema'd).
        "payload": {
            "qc.q30": {"gate": 0.90, "hard_fail": 0.80, "borderline_band": 0.03},
            "qc.mean_target_coverage": {"gate": 40.0, "hard_fail": 20.0},
        },
    }
    body.update(over)
    return body


# --- save a draft: server-authored fields + audit capture ------------------------------------


def test_save_draft_captures_submitter_and_authors_fields(client):
    # No auth headers -> the permissive dev actor (approver) clears the reviewer/approver gate.
    resp = client.post("/api/settings/thresholds", json=_body(name="alpha"))
    assert resp.status_code == 201
    ack = resp.json()
    assert ack["version"] == 1 and ack["status"] == "draft"
    assert ack["id"] and ack["created_at"] and ack["name"] == "alpha"
    assert ack["submitted_by"] == "dev"  # captured from the authed actor, not the body
    assert "payload" not in ack  # the ack never echoes the payload back (no reflection surface)

    # The stored revision reserves the full lifecycle with the *_by fields server-authored.
    stored = client.get("/api/settings/thresholds/alpha").json()[0]
    assert stored["status"] == "draft"
    assert stored["submitted_by"] == "dev"
    assert stored["reviewed_by"] is None and stored["approved_by"] is None
    assert stored["payload"]["qc.q30"]["gate"] == 0.90  # arbitrary payload round-trips exactly


def test_submitted_by_reflects_the_header_actor(client):
    # The dev-shim reads X-Bayleaf-Actor / X-Bayleaf-Role; a reviewer may save a draft and the
    # captured submitter is the header identity, not a hardcoded/client-supplied value.
    resp = client.post(
        "/api/settings/thresholds",
        json=_body(name="beta"),
        headers={"X-Bayleaf-Actor": "a.rivera", "X-Bayleaf-Role": "reviewer"},
    )
    assert resp.status_code == 201
    assert resp.json()["submitted_by"] == "a.rivera"


# --- versioning: monotonic per name, latest-per-name catalog, history -------------------------


def test_versioning_and_catalog_and_history(client):
    assert client.post("/api/settings/thresholds", json=_body(name="alpha")).json()["version"] == 1
    v2 = client.post(
        "/api/settings/thresholds", json=_body(name="alpha", payload={"gate": 0.5})
    ).json()
    assert v2["version"] == 2  # monotonic PER name
    client.post("/api/settings/thresholds", json=_body(name="beta"))

    # Catalog = the LATEST revision of each distinct name, sorted by name.
    catalog = client.get("/api/settings/thresholds").json()
    assert [(o["name"], o["version"]) for o in catalog] == [("alpha", 2), ("beta", 1)]
    assert next(o for o in catalog if o["name"] == "alpha")["payload"] == {"gate": 0.5}

    # Full history for one name, ascending by version.
    hist = client.get("/api/settings/thresholds/alpha").json()
    assert [o["version"] for o in hist] == [1, 2]
    assert client.get("/api/settings/thresholds/nope").status_code == 404  # unknown name


# --- approve: requires approver (403 for reviewer), audits approved_by ------------------------


def test_approve_requires_approver_and_audits_approver(client):
    client.post("/api/settings/thresholds", json=_body(name="wgs"))

    # A reviewer may SAVE but not APPROVE -> 403, and nothing is appended.
    forbidden = client.post(
        "/api/settings/thresholds/wgs/approve", headers={"X-Bayleaf-Role": "reviewer"}
    )
    assert forbidden.status_code == 403
    assert [o["version"] for o in client.get("/api/settings/thresholds/wgs").json()] == [1]

    # A viewer is likewise blocked from approving.
    assert (
        client.post(
            "/api/settings/thresholds/wgs/approve", headers={"X-Bayleaf-Role": "viewer"}
        ).status_code
        == 403
    )

    # An approver (dev default) approves -> a NEW immutable revision, status=approved + approved_by.
    approved = client.post(
        "/api/settings/thresholds/wgs/approve",
        headers={"X-Bayleaf-Actor": "boss", "X-Bayleaf-Role": "approver"},
    )
    assert approved.status_code == 201
    rec = approved.json()
    assert rec["status"] == "approved" and rec["approved_by"] == "boss" and rec["version"] == 2
    assert rec["payload"]["qc.q30"]["gate"] == 0.90  # payload carried forward from the draft

    # Append-only: the draft revision is preserved, and the latest-per-name is now approved.
    hist = client.get("/api/settings/thresholds/wgs").json()
    assert [(o["version"], o["status"]) for o in hist] == [(1, "draft"), (2, "approved")]
    latest = next(o for o in client.get("/api/settings/thresholds").json() if o["name"] == "wgs")
    assert latest["status"] == "approved"


def test_approve_unknown_name_is_404(client):
    assert client.post("/api/settings/thresholds/ghost/approve").status_code == 404


# --- structural PII / smuggled-field guard (extra="forbid") ----------------------------------


def test_extra_forbid_blocks_smuggled_server_and_identity_fields(client):
    # The client cannot set server-authored fields (id/version/created_at/status) ...
    assert client.post("/api/settings/thresholds", json=_body(id="deadbeef")).status_code == 422
    assert client.post("/api/settings/thresholds", json=_body(version=99)).status_code == 422
    assert client.post("/api/settings/thresholds", json=_body(status="approved")).status_code == 422
    # ... nor any identity/audit (PII) field — no operator name/email enters through the body.
    assert client.post("/api/settings/thresholds", json=_body(submitted_by="me")).status_code == 422
    assert client.post("/api/settings/thresholds", json=_body(approved_by="me")).status_code == 422
    assert client.post("/api/settings/thresholds", json=_body(reviewed_by="me")).status_code == 422


def test_malformed_actor_header_is_400_before_any_write(client):
    # A newline in the actor id could forge a log/JSONL line -> rejected at the auth boundary (400),
    # and nothing is persisted (the store is never reached).
    resp = client.post(
        "/api/settings/thresholds", json=_body(name="x"), headers={"X-Bayleaf-Actor": "e\nvil"}
    )
    assert resp.status_code == 400
    assert client.get("/api/settings/thresholds").json() == []


# --- sanity guardrails on the payload --------------------------------------------------------


def test_payload_must_be_a_nonempty_json_object(client):
    # Not an object -> 422 (pydantic type guard); empty object -> 422 (nothing to override).
    assert client.post("/api/settings/thresholds", json=_body(payload=[1, 2])).status_code == 422
    assert client.post("/api/settings/thresholds", json=_body(payload="nope")).status_code == 422
    assert client.post("/api/settings/thresholds", json=_body(payload={})).status_code == 422
    # A required field missing entirely -> 422.
    body = _body()
    del body["payload"]
    assert client.post("/api/settings/thresholds", json=body).status_code == 422


def test_payload_rejects_obviously_out_of_range_thresholds(client):
    # A negative gate, an absurd magnitude, and an out-of-[0,1] relative band are clear errors.
    assert (
        client.post(
            "/api/settings/thresholds", json=_body(payload={"qc.q30": {"gate": -0.5}})
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/settings/thresholds", json=_body(payload={"qc.q30": {"hard_fail": 1e12}})
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/settings/thresholds", json=_body(payload={"qc.q30": {"borderline_band": 5}})
        ).status_code
        == 422
    )


def test_payload_is_tolerant_of_unknown_shape(client):
    # A missing/odd field is a SIGNAL, not a crash: an unknown key with a normal value saves fine
    # (the store is tolerant of shape, strict only on clearly-broken threshold numbers).
    resp = client.post(
        "/api/settings/thresholds",
        json=_body(name="odd", payload={"note": "raise coverage", "future_knob": {"gate": 45.0}}),
    )
    assert resp.status_code == 201
    stored = client.get("/api/settings/thresholds/odd").json()[0]
    assert stored["payload"]["note"] == "raise coverage"  # unknown fields kept as-is


# --- the store degrades on a write failure without leaking the path/DSN ----------------------


def test_write_failure_returns_503_without_leak(tmp_path, monkeypatch):
    class _Boom:
        def append(self, _record):
            raise OSError("disk full at /secret/path")

    monkeypatch.setattr("api.routers.settings.get_settings_store", _Boom)
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app).post("/api/settings/thresholds", json=_body())
    assert resp.status_code == 503 and "unavailable" in resp.json()["detail"]
    assert "disk full" not in resp.text and "/secret/path" not in resp.text  # no path/DSN leak


# --- the SQLite adapter end-to-end + the factory selection/degradation ------------------------


def test_sqlite_store_roundtrips_through_the_endpoint(tmp_path, monkeypatch):
    # Route the endpoint's saves into a real (offline, zero-dep) SQLite DB, then read them back
    # through the store — proving "threshold overrides in a database" end to end.
    db = tmp_path / "settings_overrides.sqlite"
    monkeypatch.setenv("BAYLEAF_SETTINGS_STORE", "sqlite")
    monkeypatch.setenv("BAYLEAF_SETTINGS_DB", str(db))
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    assert c.post("/api/settings/thresholds", json=_body(name="wgs")).json()["version"] == 1
    assert c.post("/api/settings/thresholds", json=_body(name="wgs")).json()["version"] == 2
    rows = SqliteSettingsStore(str(db)).get_versions("wgs")
    assert [r["version"] for r in rows] == [1, 2]
    assert rows[0]["payload"]["qc.q30"]["gate"] == 0.90  # full payload round-trips


def test_store_factory_selects_and_degrades(tmp_path, monkeypatch):
    monkeypatch.setenv("BAYLEAF_SETTINGS_DB", str(tmp_path / "s.sqlite"))
    monkeypatch.delenv("BAYLEAF_SETTINGS_STORE", raising=False)
    assert isinstance(get_settings_store(), JsonlSettingsStore)  # default
    monkeypatch.setenv("BAYLEAF_SETTINGS_STORE", "sqlite")
    assert isinstance(get_settings_store(), SqliteSettingsStore)
    # postgres selected but no DATABASE_URL here -> degrade to JSONL, never raise.
    monkeypatch.setenv("BAYLEAF_SETTINGS_STORE", "postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert isinstance(get_settings_store(), JsonlSettingsStore)
