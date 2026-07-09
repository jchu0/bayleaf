"""Tests for the Pipeline Builder authoring lifecycle (ADR-0014) — PRODUCT state, off the gate.

Isolation per the build contract: each test builds its OWN tiny FastAPI app mounting ONLY the
lifecycle router (never ``api.main``), and drives it with a TestClient, so a failure points at
this seam, not unrelated wiring. Drafts are seeded straight into the append-only store (standing
in for ``POST /api/pipelines``) so the test depends on nothing outside the router + store. The
store is a per-test tmp JSONL file; the dry-run resolves against the committed real run dir
``data/mock_run_01`` (flat files: SampleSheet.csv, qc_metrics.csv, demux_stats.csv, …).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.pipeline_store import get_pipeline_store
from api.routers.pipelines_lifecycle import _DATA_ROOT, router


@pytest.fixture
def client(tmp_path: Any, monkeypatch: Any) -> TestClient:
    # Route every store read/write into a per-test tmp JSONL file; force the JSONL adapter so the
    # test never touches a real DB. get_pipeline_store() re-reads the env per call, so seeding and
    # the endpoints share the same file.
    monkeypatch.setenv("PIPEGUARD_PIPELINE_PATH", str(tmp_path / "pipelines.jsonl"))
    monkeypatch.delenv("PIPEGUARD_PIPELINE_STORE", raising=False)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _seed_draft(name: str, graph: dict[str, Any]) -> dict[str, Any]:
    """Append a fresh draft version straight to the store (stands in for the save endpoint)."""
    return get_pipeline_store().append(
        {
            "id": uuid.uuid4().hex,
            "name": name,
            "schema_version": "builder/0.1",
            "created_at": "2026-07-09T00:00:00+00:00",
            "graph": graph,
            "profile": None,
            "status": "draft",
            "submitted_by": None,
            "reviewed_by": None,
            "approved_by": None,
        }
    )


def _node_graph(*locators: dict[str, Any]) -> dict[str, Any]:
    """A minimal builder graph carrying the given locators on a single node (the frontend shape)."""
    return {"nodes": [{"id": "n1", "locators": list(locators)}]}


def _loc(kind: str, pg: str, loc: str, **over: Any) -> dict[str, Any]:
    base = {"kind": kind, "pg": pg, "loc": loc, "required": True, "role": "output", "on": "error"}
    base.update(over)
    return base


# --- submit + approve happy path -------------------------------------------------------------


def test_submit_then_approve_happy_path(client: TestClient) -> None:
    _seed_draft("wgs", _node_graph())  # a draft with no locators is fine for the transition path

    sub = client.post("/api/pipelines/wgs/submit")  # dev default actor = approver (⊇ reviewer)
    assert sub.status_code == 200
    body = sub.json()
    assert body["status"] == "pending_review"
    assert body["submitted_by"] == "dev"  # actor.id captured into the audit field
    assert body["version"] == 2  # append-only: the transition is a new revision, not a mutation

    app = client.post("/api/pipelines/wgs/approve")
    assert app.status_code == 200
    ap = app.json()
    assert ap["status"] == "approved"
    assert ap["approved_by"] == "dev"
    assert ap["submitted_by"] == "dev"  # the earlier audit field carries forward
    assert ap["emitted_at"]  # approval blesses AND records the emitted baseline
    assert ap["version"] == 3


def test_submit_unknown_pipeline_is_404(client: TestClient) -> None:
    assert client.post("/api/pipelines/nope/submit").status_code == 404


def test_approve_requires_pending_review_state(client: TestClient) -> None:
    # A draft that was never submitted cannot be approved (guarded state machine) -> 409.
    _seed_draft("wgs", _node_graph())
    resp = client.post("/api/pipelines/wgs/approve")
    assert resp.status_code == 409
    assert "expected 'pending_review'" in resp.json()["detail"]


# --- approve requires the approver role (403 for a reviewer) ---------------------------------


def test_approve_requires_approver_role(client: TestClient) -> None:
    _seed_draft("wgs", _node_graph())
    # A reviewer may submit …
    reviewer = {"X-PipeGuard-Role": "reviewer", "X-PipeGuard-Actor": "a.rivera"}
    assert client.post("/api/pipelines/wgs/submit", headers=reviewer).status_code == 200
    # … but may NOT approve (approver-only) -> 403, and the error must not leak the caller id.
    denied = client.post("/api/pipelines/wgs/approve", headers=reviewer)
    assert denied.status_code == 403
    assert "a.rivera" not in denied.text
    # An approver clears the gate.
    ok = client.post(
        "/api/pipelines/wgs/approve",
        headers={"X-PipeGuard-Role": "approver", "X-PipeGuard-Actor": "b.chen"},
    )
    assert ok.status_code == 200
    assert ok.json()["approved_by"] == "b.chen"


def test_submit_requires_reviewer_or_approver(client: TestClient) -> None:
    _seed_draft("wgs", _node_graph())
    denied = client.post("/api/pipelines/wgs/submit", headers={"X-PipeGuard-Role": "viewer"})
    assert denied.status_code == 403


# --- dry-run: matched / missing / ambiguous / invalid against a real run dir ------------------


def test_dry_run_reports_matched_missing_and_refuses_traversal(client: TestClient) -> None:
    graph = _node_graph(
        _loc("qc", "path", "qc_metrics.csv"),  # a real flat file in mock_run_01 -> matched
        _loc("bam", "glob", "align/*.md.bam"),  # no align/ subdir in mock_run_01 -> missing
        _loc("evil", "path", "../../../etc/passwd"),  # escapes the run dir -> invalid, no leak
    )
    _seed_draft("wgs", graph)

    resp = client.post("/api/pipelines/wgs/dry-run")  # default run_id = mock_run_01
    assert resp.status_code == 200
    body = resp.json()
    assert body["executed"] is False  # a dry-run NEVER executes (compose != execute)
    by_kind = {loc["kind"]: loc for loc in body["locators"]}

    assert by_kind["qc"]["status"] == "matched"
    assert by_kind["qc"]["paths"] == ["qc_metrics.csv"]  # relative-to-run-dir, never absolute
    assert by_kind["bam"]["status"] == "missing"
    assert by_kind["bam"]["paths"] == []
    assert by_kind["evil"]["status"] == "invalid"  # traversal refused before touching the fs
    assert by_kind["evil"]["paths"] == []  # nothing resolved for an escaping locator
    # No resolved path is host-absolute, and the deployment's absolute data root never leaks —
    # the only place the traversal string appears is the client's own echoed `pattern` input.
    for loc in body["locators"]:
        assert all(not p.startswith("/") for p in loc["paths"])
    assert str(_DATA_ROOT.resolve()) not in resp.text

    assert body["summary"]["matched"] == 1
    assert body["summary"]["missing"] == 1
    assert body["summary"]["invalid"] == 1


def test_dry_run_glob_multiplicity_is_ambiguous_unless_on_all(client: TestClient) -> None:
    # mock_run_01 has several *.csv files. on='error' -> ambiguous; on='all' -> matched (a set).
    _seed_draft(
        "amb",
        _node_graph(
            _loc("csv_err", "glob", "*.csv", on="error"),
            _loc("csv_all", "glob", "*.csv", on="all"),
        ),
    )
    body = client.post("/api/pipelines/amb/dry-run").json()
    by_kind = {loc["kind"]: loc for loc in body["locators"]}
    assert by_kind["csv_err"]["status"] == "ambiguous"
    assert len(by_kind["csv_err"]["paths"]) > 1
    assert by_kind["csv_all"]["status"] == "matched"


def test_dry_run_unknown_run_is_404(client: TestClient) -> None:
    _seed_draft("wgs", _node_graph(_loc("qc", "path", "qc_metrics.csv")))
    assert client.post("/api/pipelines/wgs/dry-run?run_id=no_such_run").status_code == 404


# --- diff: working graph vs last emitted (approved) snapshot ---------------------------------


def test_diff_reports_added_before_baseline_then_drift_after_emit(client: TestClient) -> None:
    g1 = _node_graph(
        _loc("bam", "glob", "align/*.bam"),
        _loc("qc", "path", "qc_metrics.csv", required=False),
    )
    _seed_draft("wgs", g1)

    # No emitted baseline yet -> every working locator is "added" relative to nothing.
    pre = client.get("/api/pipelines/wgs/diff").json()
    assert pre["has_baseline"] is False
    assert {a["kind"] for a in pre["added"]} == {"bam", "qc"}

    # Submit + approve -> the approved version (graph == g1) becomes the emitted baseline.
    client.post("/api/pipelines/wgs/submit")
    client.post("/api/pipelines/wgs/approve")

    # Edit + save a new draft: bam's pattern changes, qc is dropped, vcf is added.
    g2 = _node_graph(
        _loc("bam", "glob", "align/*.cram"),  # changed pattern
        _loc("vcf", "glob", "variants/*.vcf.gz", required=False),  # added
    )  # qc removed
    _seed_draft("wgs", g2)

    diff = client.get("/api/pipelines/wgs/diff").json()
    assert diff["has_baseline"] is True
    assert diff["emitted_version"] is not None
    assert diff["working_version"] > diff["emitted_version"]  # working is newer than the baseline
    assert {c["kind"] for c in diff["changed"]} == {"bam"}
    assert {a["kind"] for a in diff["added"]} == {"vcf"}
    assert {r["kind"] for r in diff["removed"]} == {"qc"}
    # The changed row carries both before/after specs so the UI can render the drift.
    bam = next(c for c in diff["changed"] if c["kind"] == "bam")
    assert bam["before"]["pattern"] == "align/*.bam"
    assert bam["after"]["pattern"] == "align/*.cram"


def test_diff_unchanged_right_after_emit(client: TestClient) -> None:
    # Immediately after approval, working == emitted, so nothing has drifted.
    _seed_draft("wgs", _node_graph(_loc("qc", "path", "qc_metrics.csv")))
    client.post("/api/pipelines/wgs/submit")
    client.post("/api/pipelines/wgs/approve")
    diff = client.get("/api/pipelines/wgs/diff").json()
    assert diff["has_baseline"] is True
    assert diff["added"] == [] and diff["removed"] == [] and diff["changed"] == []
    assert diff["unchanged_count"] == 1


def test_diff_unknown_pipeline_is_404(client: TestClient) -> None:
    assert client.get("/api/pipelines/nope/diff").status_code == 404
