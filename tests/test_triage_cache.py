"""Cache-through for triage notes (api/triage_cache over api/agent_output_cache) — offline.

Pins the guarantee: a triage note is generated once and served from the backend cache on repeat
requests (navigating away and back doesn't regenerate), it's saved/logged, the key is stable across
restarts (finding signatures), and a transient live→stub degrade is NOT cached under the live key.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.triage_cache as tc
from api.agent_output_cache import agent_cache_key, get_agent_output_cache
from api.main import app
from api.triage_cache import get_or_create_triage
from bayleaf import run_gate_from_dir

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.delenv("BAYLEAF_AGENT_CACHE_STORE", raising=False)
    monkeypatch.setenv("BAYLEAF_AGENT_CACHE_PATH", str(tmp_path / "agent_cache.jsonl"))
    monkeypatch.delenv("BAYLEAF_TRIAGE_AGENT", raising=False)  # offline stub


def _flagged_card() -> Any:
    _, cards = run_gate_from_dir("data/mock_run_01")
    return next(c for c in cards if c.sample_id == "S4")  # escalate — has findings


def _triage_key(card: Any, corpus_version: str) -> str:
    return agent_cache_key(
        "triage",
        {
            "run_id": "mock_run_01",
            "sample_id": "S4",
            "signatures": [f.signature for f in card.findings],
            "agent": "stub",
            "model": None,
            "corpus_version": corpus_version,
        },
    )


def test_key_is_stable_and_sensitive() -> None:
    base: dict[str, Any] = {"signatures": ["a", "b"], "agent": "stub", "corpus_version": "1.0.0"}
    assert agent_cache_key("triage", base) == agent_cache_key(
        "triage", {**base, "signatures": ["b", "a"]}
    )  # order-independent (lists sorted)
    assert agent_cache_key("triage", base) != agent_cache_key("triage", {**base, "agent": "claude"})
    assert agent_cache_key("triage", base) != agent_cache_key("repair", base)  # namespace matters


def test_generates_once_then_serves_from_cache() -> None:
    card = _flagged_card()
    calls = {"n": 0}
    real = tc.triage_card

    def counting(c: Any, agent: Any = None) -> Any:
        calls["n"] += 1
        return real(c, agent=agent)

    mp = pytest.MonkeyPatch()
    mp.setattr(tc, "triage_card", counting)
    try:
        first = get_or_create_triage("mock_run_01", card)
        second = get_or_create_triage("mock_run_01", card)
    finally:
        mp.undo()

    assert first is not None and second is not None
    assert calls["n"] == 1  # generated once; the second call is served from the cache
    assert second.id == first.id  # the SAME persisted note, not a regenerated one
    assert get_agent_output_cache().get(_triage_key(card, first.corpus_version)) is not None


def test_endpoint_serves_the_same_note_twice() -> None:
    a = client.get("/api/runs/mock_run_01/cards/S4/triage")
    b = client.get("/api/runs/mock_run_01/cards/S4/triage")
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["id"] == b.json()["id"]  # cached — a regenerated note would have a new id


def test_degraded_note_is_not_cached() -> None:
    """A live agent that degraded to the stub (generated_by != selected agent) must NOT be cached
    under the live key — so it retries next time instead of pinning a transient fallback."""
    card = _flagged_card()

    class _FakeClaudeSelected:
        name = "claude"
        model = "claude-sonnet-5"

    mp = pytest.MonkeyPatch()
    mp.setattr(tc, "get_triage_agent", lambda: _FakeClaudeSelected())
    stub_note = tc.triage_card(card)  # a real STUB note (generated_by='stub')
    mp.setattr(tc, "triage_card", lambda c, agent=None: stub_note)
    try:
        note = get_or_create_triage("mock_run_01", card)
        assert note is not None and note.generated_by == "stub"
        key = agent_cache_key(
            "triage",
            {
                "run_id": "mock_run_01",
                "sample_id": "S4",
                "signatures": [f.signature for f in card.findings],
                "agent": "claude",
                "model": "claude-sonnet-5",
                "corpus_version": note.corpus_version,
            },
        )
        assert get_agent_output_cache().get(key) is None  # degrade not pinned under the live key
    finally:
        mp.undo()
