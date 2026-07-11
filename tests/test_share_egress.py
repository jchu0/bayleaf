"""De-identified share/report egress (ADR-0018 D3).

Pins the three things that make a share honest and auditable:
1. It is **approver-gated** (a viewer/reviewer is refused) — data does not leave on a low
   privilege.
2. It applies the **conservative Safe-Harbor-style scrub** (`api.safe_harbor.redact_record`):
   direct identifiers (`submitted_by`, `subject_id`) are gone from every emitted row, and the
   manifest labels the scrub as a version, not a compliance attestation.
3. It records a **DATA_EXPORTED provenance event** that surfaces in the run's trail, pinned to
   the exact bytes emitted by a content hash — so every data-out is auditable next to the
   decisions (ADR-0002), and `_evaluate`'s deterministic cache is never mutated to get it there.

Offline: a TestClient drives the app in-process, the share ledger is redirected to a tmp file.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.main import app
from pipeguard.provenance import EventType

# A committed run that carries intake identity (sample_metadata.csv → subject_id/submitted_by),
# so the scrub is demonstrably removing something rather than passing an already-clean row.
_RUN = "RUN-2026-07-11-CLINVAR-RTH"
_APPROVER = {"X-PipeGuard-Role": "approver", "X-PipeGuard-Actor": "b.chen"}


@pytest.fixture
def client(tmp_path: Any, monkeypatch: Any) -> TestClient:
    # Isolate the append-only share store to a tmp JSONL so tests never touch the repo default.
    monkeypatch.delenv("PIPEGUARD_SHARE_STORE", raising=False)  # default (jsonl), whatever the env
    monkeypatch.setenv("PIPEGUARD_SHARE_PATH", str(tmp_path / "share.events.jsonl"))
    return TestClient(app)


def test_share_requires_approver(client: TestClient) -> None:
    # A viewer and a reviewer are both refused — a share is an approver action.
    for role in ("viewer", "reviewer"):
        denied = client.post(
            f"/api/runs/{_RUN}/share",
            headers={"X-PipeGuard-Role": role, "X-PipeGuard-Actor": "a.rivera"},
        )
        assert denied.status_code == 403, role


def test_share_unknown_run_is_404(client: TestClient) -> None:
    assert client.post("/api/runs/NOPE/share", headers=_APPROVER).status_code == 404


def test_share_scrubs_direct_identifiers_and_labels_the_scrub(client: TestClient) -> None:
    resp = client.post(f"/api/runs/{_RUN}/share", headers=_APPROVER)
    assert resp.status_code == 200
    body = resp.json()
    manifest, rows = body["manifest"], body["rows"]

    # The scrub version is labelled — never a compliance claim.
    assert manifest["policy_id"] == "safe-harbor-style-v1"
    assert "NOT" in manifest["disclaimer"] and "compliance" in manifest["disclaimer"].lower()
    assert len(manifest["safe_harbor_classes"]) == 18  # the §164.514(b)(2) identifier classes

    # Every emitted row has DROPPED the direct identifiers, and kept the decision columns.
    assert rows, "the run has at least one decision card to share"
    assert manifest["n_rows"] == len(rows)
    for row in rows:
        assert "submitted_by" not in row  # operator PII — dropped
        assert "subject_id" not in row  # unique subject key — dropped
        assert {"run_id", "sample_id", "verdict"} <= set(row)  # decision columns survive


def test_share_records_a_data_exported_event_in_the_trail(client: TestClient) -> None:
    share = client.post(f"/api/runs/{_RUN}/share", headers=_APPROVER).json()
    manifest = share["manifest"]

    # The run's provenance trail now carries the DATA_EXPORTED event, pinned to the same bytes.
    detail = client.get(f"/api/runs/{_RUN}").json()
    exported = [e for e in detail["events"] if e["event_type"] == EventType.DATA_EXPORTED.value]
    assert len(exported) >= 1
    event = next(e for e in exported if e["id"] == manifest["event_id"])
    assert event["payload"]["content_hash"] == manifest["content_hash"]  # trail can't drift
    assert event["actor"] == "human:b.chen"  # who exported is recorded
    assert event["run_id"] == _RUN
    # The egress is an output edge in the lineage, tied to the same content hash.
    assert event["outputs"][0]["content_hash"] == manifest["content_hash"]


def test_share_does_not_perturb_the_gate_decision(client: TestClient) -> None:
    # A share is an egress transform, never a gate input (ADR-0001): the cards are byte-identical
    # before and after a share is recorded.
    before = client.get(f"/api/runs/{_RUN}").json()["cards"]
    client.post(f"/api/runs/{_RUN}/share", headers=_APPROVER)
    after = client.get(f"/api/runs/{_RUN}").json()["cards"]
    assert before == after
