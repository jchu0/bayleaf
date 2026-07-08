"""Tests for the advisory QC-triage agent (offline, stub only).

These run fully offline (no API). They pin the guardrails that make the agent safe:
the note is advisory, cites the knowledge corpus, addresses the flagged findings, and
NEVER touches the verdict. The API endpoint is exercised in-process via TestClient.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from pipeguard import Verdict, load_run, run_gate, triage_card
from pipeguard.synthesis import StubSynthesizer
from pipeguard.triage import (
    KeywordRetriever,
    StubTriageAgent,
    TriageNote,
    load_knowledge_corpus,
)

DATA = Path(__file__).resolve().parent.parent / "data" / "mock_run_01"


@pytest.fixture(scope="module")
def cards():
    return {c.sample_id: c for c in run_gate(load_run(DATA), synthesizer=StubSynthesizer())}


# --- corpus + retrieval -----------------------------------------------------


def test_corpus_loads_and_is_well_formed():
    corpus = load_knowledge_corpus()
    assert len(corpus) >= 8  # curated ~8-12 entries
    ids = [e.id for e in corpus]
    assert len(set(ids)) == len(ids)  # unique ids
    for e in corpus:
        assert e.id.startswith("know_")
        assert e.keywords and e.likely_cause and e.suggested_action and e.source
        # No verdict leaks into the corpus — advice must not pre-decide the gate.
        assert not hasattr(e, "verdict")


def test_retriever_ranks_barcode_entry_for_barcode_query():
    retriever = KeywordRetriever.from_default_corpus()
    hits = retriever.retrieve("barcode index mismatch sample sheet demultiplexed", top_k=3)
    assert hits, "expected at least one hit"
    assert hits[0].entry.id == "know_barcode_index_mismatch"
    assert 0.0 < hits[0].score <= 1.0  # heuristic overlap, normalized
    # Ordering is by descending score.
    assert all(hits[i].score >= hits[i + 1].score for i in range(len(hits) - 1))


def test_retriever_returns_nothing_for_empty_query():
    assert KeywordRetriever.from_default_corpus().retrieve("", top_k=3) == []


# --- the agent / triage_card ------------------------------------------------


def test_clean_proceed_card_yields_no_note(cards):
    note = triage_card(cards["S1"])  # S1 is a clean PROCEED
    assert note is None


def test_flagged_card_yields_advisory_note(cards):
    note = triage_card(cards["S4"])  # ESCALATE: barcode + missing subject_id
    assert isinstance(note, TriageNote)
    assert note.advisory is True
    assert note.agent == "qc_triage"
    assert note.generated_by == "stub"
    assert note.model is None  # stub uses no model
    assert note.likely_cause and note.suggested_action


def test_note_addresses_the_flagged_findings(cards):
    s4 = cards["S4"]
    note = triage_card(s4)
    assert note is not None
    flagged_rule_ids = {f.rule_id for f in s4.findings}
    assert set(note.addresses_rule_ids) == flagged_rule_ids
    assert set(note.addresses_signatures) == {f.signature for f in s4.findings}


def test_note_cites_corpus_and_findings(cards):
    note = triage_card(cards["S4"])
    assert note is not None
    kinds = {c.source_kind for c in note.citations}
    assert kinds == {"knowledge", "finding"}
    # At least one knowledge citation, carrying a corpus id + heuristic score.
    know = [c for c in note.citations if c.source_kind == "knowledge"]
    assert know and all(c.ref.startswith("know_") for c in know)
    assert all(c.score is not None and 0.0 <= c.score <= 1.0 for c in know)
    # The barcode escalation should surface the barcode knowledge entry.
    assert any(c.ref == "know_barcode_index_mismatch" for c in know)
    # Finding citations reference the rule_ids by id (no score).
    finding_refs = {c.ref for c in note.citations if c.source_kind == "finding"}
    assert finding_refs == {f.rule_id for f in cards["S4"].findings}


def test_note_never_touches_the_verdict(cards):
    """The advisory note carries no verdict/confidence field (ADR-0001 invariant)."""
    s4 = cards["S4"]
    note = triage_card(s4)
    assert note is not None
    dumped = note.model_dump()
    assert "verdict" not in dumped
    assert "confidence" not in dumped
    # Triaging does not mutate the card's verdict.
    assert s4.verdict is Verdict.ESCALATE


def test_hold_card_also_gets_a_note(cards):
    note = triage_card(cards["S5"])  # HOLD: borderline Q30 + coverage
    assert note is not None
    assert note.sample_id == "S5"
    know = [c.ref for c in note.citations if c.source_kind == "knowledge"]
    # A QC/coverage entry should be retrieved for the borderline metrics.
    assert any(ref in {"know_low_q30", "know_low_coverage_depth"} for ref in know)


def test_note_content_hash_is_stable_and_deterministic(cards):
    a = triage_card(cards["S4"])
    b = triage_card(cards["S4"])
    assert a is not None and b is not None
    assert len(a.content_hash) == 64
    assert a.content_hash == b.content_hash  # deterministic across runs


def test_agent_falls_back_to_conservative_note_when_corpus_empty(cards):
    """With no corpus match, the stub defers to a human rather than inventing a cause."""
    agent = StubTriageAgent(retriever=KeywordRetriever(()))  # empty corpus
    note = agent.triage_card(cards["S4"])
    assert note is not None
    assert not [c for c in note.citations if c.source_kind == "knowledge"]
    assert "human reviewer" in note.suggested_action.lower()
    # Findings are still addressed even when no knowledge matched.
    assert set(note.addresses_rule_ids) == {f.rule_id for f in cards["S4"].findings}


# --- API endpoint -----------------------------------------------------------

client = TestClient(app)


def test_triage_endpoint_returns_advisory_note_for_flagged_sample():
    resp = client.get("/api/runs/mock_run_01/cards/S4/triage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["advisory"] is True
    assert body["agent"] == "qc_triage"
    assert "verdict" not in body  # never decides
    assert any(c["source_kind"] == "knowledge" for c in body["citations"])
    assert body["content_hash"]  # computed field serializes


def test_triage_endpoint_404s_for_clean_and_unknown_samples():
    assert client.get("/api/runs/mock_run_01/cards/S1/triage").status_code == 404  # clean
    assert client.get("/api/runs/mock_run_01/cards/NOPE/triage").status_code == 404  # unknown
    assert client.get("/api/runs/NOPE/cards/S4/triage").status_code == 404  # unknown run
