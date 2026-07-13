"""Server-side agent-binding store + pure resolver (ADR-0024, scope-by-wiring) — offline.

Pins the enforcement primitives: `normalize_bindings` is tolerant of arbitrary client JSON,
`granted_grants` distinguishes NOT-bound (None → deny) from bound-with-no-grants ([]), the store
round-trips per run, a re-record wins, and SQLite matches JSONL byte-for-byte.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api.agent_binding_store import (
    JsonlAgentBindingStore,
    SqliteAgentBindingStore,
    get_agent_binding_store,
    granted_grants,
    normalize_bindings,
)


def test_normalize_is_tolerant() -> None:
    raw = [
        {"agent": "qc_triage", "node": "n_fastp", "grants": ["outputs", "logs", "logs"]},
        {"agent": "qc_triage", "node": "n_mosdepth"},  # no grants → defaults to ['outputs']
        {"agent": "", "node": "n_x"},  # dropped: no agent
        {"node": "n_y"},  # dropped: no agent
        "garbage",  # dropped: not a dict
        {"agent": "a", "node": "n", "grants": ["outputs", "bogus"]},  # bogus grant dropped
    ]
    out = normalize_bindings(raw)
    assert out == [
        {"agent": "qc_triage", "node": "n_fastp", "grants": ["outputs", "logs"]},
        {"agent": "qc_triage", "node": "n_mosdepth", "grants": ["outputs"]},
        {"agent": "a", "node": "n", "grants": ["outputs"]},
    ]
    assert normalize_bindings(None) == [] and normalize_bindings("x") == []


def test_granted_grants_bound_vs_not_bound() -> None:
    bindings = [
        {"agent": "qc_triage", "node": "n_fastp", "grants": ["outputs", "logs"]},
        {"agent": "qc_triage", "node": "n_mosdepth", "grants": []},
    ]
    assert granted_grants(bindings, "qc_triage", "n_fastp") == ["outputs", "logs"]
    assert granted_grants(bindings, "qc_triage", "n_mosdepth") == []  # bound, no grants
    assert granted_grants(bindings, "qc_triage", "n_bwa") is None  # NOT wired → deny signal
    assert granted_grants(bindings, "archivist", "n_fastp") is None  # wrong agent → deny


def _use_jsonl(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.delenv("BAYLEAF_AGENT_BINDING_STORE", raising=False)
    monkeypatch.setenv("BAYLEAF_AGENT_BINDING_PATH", str(tmp_path / "b.jsonl"))


def test_store_records_and_gets_per_run(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_agent_binding_store()
    assert isinstance(store, JsonlAgentBindingStore)
    assert store.get("RUN-X") is None

    b = [{"agent": "qc_triage", "node": "n_fastp", "grants": ["outputs"]}]
    store.record("RUN-X", b, captured_at="2026-07-13T00:00:00+00:00")
    got = store.get("RUN-X")
    assert got is not None and got["bindings"] == b


def test_rerecord_wins(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_agent_binding_store()
    store.record("RUN-X", [{"agent": "a", "node": "n1", "grants": ["outputs"]}], captured_at="t1")
    store.record("RUN-X", [{"agent": "a", "node": "n2", "grants": ["logs"]}], captured_at="t2")
    got = store.get("RUN-X")
    assert got is not None and got["bindings"][0]["node"] == "n2"  # last write wins


def test_sqlite_matches_jsonl(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("BAYLEAF_AGENT_BINDING_STORE", "sqlite")
    monkeypatch.setenv("BAYLEAF_AGENT_BINDING_DB", str(tmp_path / "b.sqlite"))
    store = get_agent_binding_store()
    assert isinstance(store, SqliteAgentBindingStore)
    b = [{"agent": "qc_triage", "node": "n_fastp", "grants": ["outputs", "logs"]}]
    store.record("RUN-X", b, captured_at="t")
    store.record("RUN-X", b, captured_at="t2")  # upsert on the PK, not a duplicate
    got = store.get("RUN-X")
    assert got is not None and got["captured_at"] == "t2" and got["bindings"] == b
