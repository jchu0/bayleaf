"""Scope-by-wiring enforcement on the node-observations read path (ADR-0024) — offline.

An agent may read a node's observations ONLY if it is WIRED to that node in the run's captured
executed-graph, and only for the grants that binding gives. Back-compat: a run with no captured
bindings, or a request without `agent`, keeps the node-scope + wire-role behavior (additive).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.agent_binding_store import get_agent_binding_store
from api.main import app

client = TestClient(app)
_REVIEWER = {"X-Bayleaf-Actor": "a.rivera", "X-Bayleaf-Role": "reviewer"}
_RUN = "RUN-TEST-BIND"


@pytest.fixture(autouse=True)
def _isolate_binding_store(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.delenv("BAYLEAF_AGENT_BINDING_STORE", raising=False)
    monkeypatch.setenv("BAYLEAF_AGENT_BINDING_PATH", str(tmp_path / "bindings.jsonl"))


def _seed(bindings: list[dict[str, Any]]) -> None:
    get_agent_binding_store().record(_RUN, bindings, captured_at="2026-07-13T00:00:00+00:00")


def _obs(node: str, *, agent: str | None = None, grants: str | None = None) -> Any:
    q = []
    if agent:
        q.append(f"agent={agent}")
    if grants:
        q.append(f"grants={grants}")
    qs = ("?" + "&".join(q)) if q else ""
    return client.get(f"/api/runs/{_RUN}/nodes/{node}/observations{qs}", headers=_REVIEWER)


def test_unbound_agent_is_denied() -> None:
    _seed([{"agent": "qc_triage", "node": "n_fastp", "grants": ["outputs"]}])
    r = _obs("n_mosdepth", agent="qc_triage")  # wired to n_fastp, NOT n_mosdepth
    assert r.status_code == 403
    assert "not wired" in r.json()["detail"]


def test_bound_agent_is_allowed() -> None:
    _seed([{"agent": "qc_triage", "node": "n_fastp", "grants": ["outputs"]}])
    r = _obs("n_fastp", agent="qc_triage")
    assert r.status_code == 200
    assert r.json()["grants"] == ["outputs"]


def test_grants_are_capped_to_the_binding() -> None:
    # Bound with outputs only; a reviewer requests outputs+logs → logs is capped OUT by the binding
    # (the wire-role check passes for reviewer, then enforcement narrows to the granted set).
    _seed([{"agent": "qc_triage", "node": "n_fastp", "grants": ["outputs"]}])
    r = _obs("n_fastp", agent="qc_triage", grants="outputs,logs")
    assert r.status_code == 200
    assert r.json()["grants"] == ["outputs"]  # logs dropped — not in the binding


def test_no_agent_is_backcompat() -> None:
    _seed([{"agent": "qc_triage", "node": "n_fastp", "grants": ["outputs"]}])
    r = _obs("n_mosdepth")  # no agent → not enforced, even though bindings exist
    assert r.status_code == 200


def test_run_without_captured_bindings_is_backcompat() -> None:
    # No _seed(): this run has no captured executed-graph → not enforceable → today's behavior.
    r = _obs("n_fastp", agent="qc_triage")
    assert r.status_code == 200
