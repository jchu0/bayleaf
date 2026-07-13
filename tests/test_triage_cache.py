"""Persistent cache-through for rule-derived triage notes (api/triage_cache) — offline.

Pins the guarantee the maintainer asked for: a triage note is generated once and served from the
backend cache on repeat requests (navigating away and back doesn't regenerate), it's saved/logged in
the store, the key is stable across restarts (finding signatures, not the per-run gate id), and a
transient live-API degradation-to-stub is NOT cached under the live key (it retries).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.triage_cache as tc
from api.main import app
from api.triage_cache import get_or_create_triage
from api.triage_cache_store import get_triage_cache_store, triage_cache_key
from bayleaf import run_gate_from_dir

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.delenv("BAYLEAF_TRIAGE_CACHE_STORE", raising=False)
    monkeypatch.setenv("BAYLEAF_TRIAGE_CACHE_PATH", str(tmp_path / "triage_cache.jsonl"))
    monkeypatch.delenv("BAYLEAF_TRIAGE_AGENT", raising=False)  # offline stub


def _flagged_card() -> Any:
    _, cards = run_gate_from_dir("data/mock_run_01")
    return next(c for c in cards if c.sample_id == "S4")  # escalate — has findings


def test_key_is_stable_and_sensitive() -> None:
    base: dict[str, Any] = {
        "run_id": "R",
        "sample_id": "S",
        "signatures": ["a", "b"],
        "agent": "stub",
        "model": None,
        "corpus_version": "1.0.0",
    }
    reordered = triage_cache_key(**{**base, "signatures": ["b", "a"]})
    assert triage_cache_key(**base) == reordered  # order-independent (sorted)
    assert triage_cache_key(**base) != triage_cache_key(**{**base, "agent": "claude"})  # agent
    assert triage_cache_key(**base) != triage_cache_key(**{**base, "signatures": ["a"]})  # findings


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
    assert (
        get_triage_cache_store().get(  # saved in the backend
            triage_cache_key(
                run_id="mock_run_01",
                sample_id="S4",
                signatures=[f.signature for f in card.findings],
                agent="stub",
                model=None,
                corpus_version=first.corpus_version,
            )
        )
        is not None
    )


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
    # triage_card returns a STUB note (generated_by='stub') — simulating a live→stub degrade.
    stub_note = tc.triage_card(card)  # real stub note
    mp.setattr(tc, "triage_card", lambda c, agent=None: stub_note)
    try:
        note = get_or_create_triage("mock_run_01", card)
        assert note is not None and note.generated_by == "stub"
        # Not cached: the store has no entry under the claude key.
        key = triage_cache_key(
            run_id="mock_run_01",
            sample_id="S4",
            signatures=[f.signature for f in card.findings],
            agent="claude",
            model="claude-sonnet-5",
            corpus_version=note.corpus_version,
        )
        assert get_triage_cache_store().get(key) is None
    finally:
        mp.undo()
