"""Tests for the Phase-2 persistence layer (offline).

Pin the ADR-0002 payoff: run the gate with a file-backed ledger, rebuild the
SQLite projection from that authoritative log, and assert the projected rows
match the demo scenario. Also cover the live repo wiring, round-trip stability,
and rebuild idempotency — the DB is a *disposable projection of the ledger*, so
its content must be a pure function of the events.
"""

from pathlib import Path

import pytest

from pipeguard import (
    EventLedger,
    SqliteRepository,
    Verdict,
    load_run,
    rebuild_db,
    run_gate,
)
from pipeguard.persistence import project_events
from pipeguard.synthesis import StubSynthesizer

DATA = Path(__file__).resolve().parent.parent / "data" / "mock_run_01"

# The pinned demo scenario (mirrors test_gate.py): 5 samples; S4 escalate, S5
# hold, S1-S3 proceed; 4 findings; 16 events.
_EXPECTED_VERDICTS = {
    "S1": Verdict.PROCEED,
    "S2": Verdict.PROCEED,
    "S3": Verdict.PROCEED,
    "S4": Verdict.ESCALATE,
    "S5": Verdict.HOLD,
}


@pytest.fixture
def ledger_and_cards(tmp_path: Path):
    """Run the gate once into a file-backed ledger; return (path, cards)."""
    path = tmp_path / "run.events.jsonl"
    ledger = EventLedger(path=path)
    cards = run_gate(load_run(DATA), synthesizer=StubSynthesizer(), ledger=ledger)
    return path, cards


def _rebuilt(path: Path) -> SqliteRepository:
    repo = SqliteRepository(":memory:")
    rebuild_db(path, repo)
    return repo


def test_rebuild_projects_demo_scenario(ledger_and_cards):
    """Replaying the ledger yields the expected run/samples/findings/cards/events."""
    path, _ = ledger_and_cards
    repo = _rebuilt(path)

    runs = repo.list_runs()
    assert len(runs) == 1
    run = runs[0]
    assert run.run_id == "mock_run_01"
    assert run.status == "completed"
    assert run.n_samples == 5
    assert run.started_at is not None and run.completed_at is not None
    # gate_provenance carried through as JSON.
    assert run.gate_provenance["rule_pack_version"]

    assert len(repo.list_samples()) == 5
    assert {s.sample_id for s in repo.list_samples()} == set(_EXPECTED_VERDICTS)
    assert len(repo.list_findings()) == 4  # S4: barcode + missing subject; S5: Q30 + coverage
    assert len(repo.list_events()) == 16  # 1 + 5 + 4 + 5 + 1

    verdicts = {c.sample_id: Verdict(c.verdict) for c in repo.list_decision_cards()}
    assert verdicts == _EXPECTED_VERDICTS
    repo.close()


def test_content_hashes_preserved(ledger_and_cards):
    """Finding and card content_hashes survive the projection verbatim."""
    path, cards = ledger_and_cards
    repo = _rebuilt(path)

    # Card hashes match the in-memory cards keyed by sample.
    card_hashes = {c.sample_id: c.content_hash for c in cards}
    for row in repo.list_decision_cards():
        assert row.content_hash == card_hashes[row.sample_id]
        assert row.content_hash and len(row.content_hash) == 64

    # Every finding hash from the run is present in the projection.
    original_hashes = {f.content_hash for c in cards for f in c.findings}
    projected_hashes = {f.content_hash for f in repo.list_findings()}
    assert projected_hashes == original_hashes
    assert all(h for h in projected_hashes)  # no null hashes
    repo.close()


def test_finding_rows_carry_ledger_payload(ledger_and_cards):
    """Projected findings keep the event payload (rule_id/gate/severity/signature)."""
    path, _ = ledger_and_cards
    repo = _rebuilt(path)
    by_rule = {f.rule_id: f for f in repo.list_findings()}
    assert "PROV-001" in by_rule  # S4 barcode mismatch
    prov = by_rule["PROV-001"]
    assert prov.sample_id == "S4"
    assert prov.gate == "preflight"
    assert prov.severity == "critical"
    assert prov.signature  # semantic recurrence key preserved
    assert prov.id.startswith("find_")
    repo.close()


def test_events_round_trip_faithfully(ledger_and_cards):
    """Projected events reconstruct to the same ledger events, in order."""
    from pipeguard.persistence import read_ledger

    path, _ = ledger_and_cards
    original = list(read_ledger(path))
    repo = _rebuilt(path)
    projected = repo.list_events()

    assert [e.event_type for e in projected] == [e.event_type for e in original]
    assert [e.id for e in projected] == [e.id for e in original]  # ledger (rowid) order
    # Full-fidelity round-trip on a representative event.
    first_original = original[0]
    first_projected = projected[0]
    assert first_projected.model_dump(mode="json") == first_original.model_dump(mode="json")
    repo.close()


def test_run_bundle_scopes_to_one_run(ledger_and_cards):
    """get_run_bundle returns the run's cards + full trail together."""
    path, _ = ledger_and_cards
    repo = _rebuilt(path)
    bundle = repo.get_run_bundle("mock_run_01")
    assert bundle.run is not None and bundle.run.run_id == "mock_run_01"
    assert len(bundle.samples) == 5
    assert len(bundle.cards) == 5
    assert len(bundle.findings) == 4
    assert len(bundle.events) == 16
    repo.close()


def test_rebuild_is_idempotent(ledger_and_cards):
    """Rebuilding twice from the same ledger yields an identical projection."""
    path, _ = ledger_and_cards
    repo = SqliteRepository(":memory:")

    rebuild_db(path, repo)
    snapshot = _dump(repo)

    rebuild_db(path, repo)  # replay again into the same DB
    assert _dump(repo) == snapshot
    repo.close()


def test_live_repo_wiring_matches_rebuild(tmp_path: Path):
    """run_gate(repo=...) writes the same projection a ledger rebuild would."""
    path = tmp_path / "run.events.jsonl"
    ledger = EventLedger(path=path)
    live_repo = SqliteRepository(":memory:")
    run_gate(load_run(DATA), synthesizer=StubSynthesizer(), ledger=ledger, repo=live_repo)

    rebuilt_repo = _rebuilt(path)

    # Same verdicts and same content hashes via both paths (DB = f(ledger)).
    assert {c.sample_id: c.verdict for c in live_repo.list_decision_cards()} == {
        c.sample_id: c.verdict for c in rebuilt_repo.list_decision_cards()
    }
    assert {f.content_hash for f in live_repo.list_findings()} == {
        f.content_hash for f in rebuilt_repo.list_findings()
    }
    assert len(live_repo.list_events()) == len(rebuilt_repo.list_events()) == 16
    live_repo.close()
    rebuilt_repo.close()


def test_default_flow_persists_nothing(tmp_path: Path):
    """No repo passed -> run_gate does not touch a DB (behavior unchanged)."""
    # A fresh DB left untouched by a repo-less run must stay empty.
    repo = SqliteRepository(tmp_path / "unused.sqlite")
    run_gate(load_run(DATA), synthesizer=StubSynthesizer())  # no repo=
    assert repo.list_runs() == []
    assert repo.list_events() == []
    repo.close()


def test_reset_clears_projection(ledger_and_cards):
    """reset() empties every table so the store can be rebuilt from scratch."""
    path, _ = ledger_and_cards
    repo = _rebuilt(path)
    assert repo.list_events()  # populated
    repo.reset()
    assert repo.list_runs() == []
    assert repo.list_samples() == []
    assert repo.list_findings() == []
    assert repo.list_decision_cards() == []
    assert repo.list_events() == []
    repo.close()


def test_project_events_from_in_memory_ledger():
    """project_events works straight off an in-memory ledger (no file needed)."""
    ledger = EventLedger()
    run_gate(load_run(DATA), synthesizer=StubSynthesizer(), ledger=ledger)
    repo = SqliteRepository(":memory:")
    n = project_events(ledger.events, repo)
    assert n == 16
    assert len(repo.list_decision_cards()) == 5
    repo.close()


def _dump(repo: SqliteRepository) -> dict[str, list[dict]]:
    """Order-stable JSON snapshot of every projection table for equality checks."""
    return {
        "runs": [r.model_dump(mode="json") for r in repo.list_runs()],
        "samples": [s.model_dump(mode="json") for s in repo.list_samples()],
        "findings": [f.model_dump(mode="json") for f in repo.list_findings()],
        "cards": [c.model_dump(mode="json") for c in repo.list_decision_cards()],
        "events": [e.model_dump(mode="json") for e in repo.list_events()],
    }
