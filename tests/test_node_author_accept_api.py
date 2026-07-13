"""POST /api/builder/node-proposal/accept + GET /api/builder/library (node-author W2).

Drives the accept→library flow with a TestClient. The accept endpoint is the backend the future
Builder "Accept to library" button calls: it re-derives a proposal from the request, RBAC-gates the
write, stamps ``submitted_by``, and stores a versioned **draft** entry. These tests pin the W2
guardrails at the wire: only a reviewer/approver may accept, only a matched proposal can be
accepted, the stored entry is METADATA (no ``script:``/``stub:`` body, no verdict/confidence), and
the library lists back what was accepted. The library sink is redirected to a tmp file so the suite
never touches the repo-root default.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _use_tmp_library(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.delenv("BAYLEAF_LIBRARY_STORE", raising=False)
    monkeypatch.setenv("BAYLEAF_LIBRARY_PATH", str(tmp_path / "library_entries.jsonl"))


def test_accept_stores_a_draft_entry_and_it_lists_back(monkeypatch: Any, tmp_path: Path) -> None:
    _use_tmp_library(monkeypatch, tmp_path)
    resp = client.post("/api/builder/node-proposal/accept", json={"request": "trim adapters QC"})
    assert resp.status_code == 201
    entry = resp.json()
    assert entry["status"] == "draft"
    assert entry["tool"] == "fastp"
    assert entry["version"]  # the pinned tool version
    assert entry["id"].startswith("libentry_")
    assert entry["submitted_by"] == "dev"  # permissive dev-default actor (approver)
    assert entry["created_at"] and entry["updated_at"]
    # The full accepted proposal rides along, losslessly.
    assert entry["proposal"]["advisory"] is True
    assert entry["proposal"]["tool"] == "fastp"

    listed = client.get("/api/builder/library").json()
    assert [e["id"] for e in listed] == [entry["id"]]
    assert listed[0]["tool"] == "fastp"


def test_accept_captures_submitted_by_from_the_authenticated_actor(
    monkeypatch: Any, tmp_path: Path
) -> None:
    _use_tmp_library(monkeypatch, tmp_path)
    resp = client.post(
        "/api/builder/node-proposal/accept",
        json={"request": "mosdepth coverage"},
        headers={"X-Bayleaf-Actor": "a.rivera", "X-Bayleaf-Role": "reviewer"},
    )
    assert resp.status_code == 201
    assert resp.json()["submitted_by"] == "a.rivera"  # stamped from the actor, not the client body


def test_accept_requires_reviewer_or_approver(monkeypatch: Any, tmp_path: Path) -> None:
    _use_tmp_library(monkeypatch, tmp_path)
    resp = client.post(
        "/api/builder/node-proposal/accept",
        json={"request": "fastp"},
        headers={"X-Bayleaf-Role": "viewer"},
    )
    assert resp.status_code == 403  # a viewer may not author a library entry
    # ...and nothing was written.
    assert client.get("/api/builder/library").json() == []


def test_accept_unmatched_request_is_422_and_stores_nothing(
    monkeypatch: Any, tmp_path: Path
) -> None:
    _use_tmp_library(monkeypatch, tmp_path)
    resp = client.post(
        "/api/builder/node-proposal/accept", json={"request": "qwerty zxcvb nonsense request"}
    )
    assert resp.status_code == 422  # a defer-to-human proposal has no node to accept
    assert client.get("/api/builder/library").json() == []


def test_accept_rejects_a_smuggled_extra_field(monkeypatch: Any, tmp_path: Path) -> None:
    _use_tmp_library(monkeypatch, tmp_path)
    # extra="forbid": a client cannot inject server-authored fields (status/submitted_by/proposal).
    resp = client.post(
        "/api/builder/node-proposal/accept",
        json={"request": "fastp", "submitted_by": "attacker", "status": "approved"},
    )
    assert resp.status_code == 422


def test_stored_entry_is_metadata_only_never_a_command_or_a_verdict(
    monkeypatch: Any, tmp_path: Path
) -> None:
    _use_tmp_library(monkeypatch, tmp_path)
    entry = client.post("/api/builder/node-proposal/accept", json={"request": "fastp"}).json()
    proposal = entry["proposal"]
    # G1: no gate value anywhere on the accepted metadata.
    assert "verdict" not in proposal and "confidence" not in proposal
    # compose != execute: no runnable command body is ever stored.
    assert "script" not in proposal and "stub" not in proposal
    for port in (*proposal["inputs"], *proposal["outputs"]):
        assert port["known"] == (port["kind"] not in proposal["reserved_kinds"])


def test_library_list_filters_by_tool_and_status(monkeypatch: Any, tmp_path: Path) -> None:
    _use_tmp_library(monkeypatch, tmp_path)
    client.post("/api/builder/node-proposal/accept", json={"request": "fastp"})
    client.post("/api/builder/node-proposal/accept", json={"request": "mosdepth coverage"})
    assert len(client.get("/api/builder/library").json()) == 2
    only_fastp = client.get("/api/builder/library", params={"tool": "fastp"}).json()
    assert [e["tool"] for e in only_fastp] == ["fastp"]
    # Everything accepted is a draft; nothing is approved yet (approve is the deferred slice).
    assert client.get("/api/builder/library", params={"status": "approved"}).json() == []
    assert len(client.get("/api/builder/library", params={"status": "draft"}).json()) == 2
