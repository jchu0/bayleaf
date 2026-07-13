"""Tests for the advisory QC-triage agent (offline, stub only).

These run fully offline (no API). They pin the guardrails that make the agent safe:
the note is advisory, cites the knowledge corpus, addresses the flagged findings, and
NEVER touches the verdict. The API endpoint is exercised in-process via TestClient.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from bayleaf import Verdict, load_run, run_gate, triage_card
from bayleaf.synthesis import StubSynthesizer
from bayleaf.triage import (
    AgentReply,
    KeywordRetriever,
    StubTriageAgent,
    TriageNote,
    ask_agent,
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


# --- the Claude path (mocked): the flip must degrade safely, never 500 -------


class _FakeBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text, stop_reason="end_turn"):
        self.stop_reason = stop_reason
        self.content = [_FakeBlock(text)] if text is not None else []


class _FakeClient:
    """Stands in for anthropic.Anthropic — .messages.create returns/raises on cue."""

    def __init__(self, response=None, raises=False):
        self._response = response
        self._raises = raises

    @property
    def messages(self):
        return self

    def create(self, **_kwargs):
        if self._raises:
            raise RuntimeError("simulated API failure")
        return self._response


def _claude_agent(monkeypatch, client):
    from bayleaf.triage.agent import ClaudeTriageAgent

    agent = ClaudeTriageAgent()
    monkeypatch.setattr(agent, "_get_client", lambda: client)
    return agent


def test_claude_path_prose_is_llm_but_citations_stay_deterministic(cards, monkeypatch):
    """On the live path the model writes ONLY the prose; provenance stays deterministic.

    This also guards the serialization path: findings carry a datetime, so if the
    prompt payload were built with python-mode model_dump() it would raise before the
    API call and never reach the client — this test would then see a stub note, not
    'claude'.
    """
    client = _FakeClient(
        _FakeResponse('{"likely_cause": "MODEL cause", "suggested_action": "MODEL action"}')
    )
    note = _claude_agent(monkeypatch, client).triage_card(cards["S4"])
    assert note is not None
    assert note.generated_by == "claude"
    assert note.likely_cause == "MODEL cause"  # prose comes from the model
    assert note.suggested_action == "MODEL action"
    # ...but the addressed findings + citations match the deterministic stub exactly.
    stub = StubTriageAgent().triage_card(cards["S4"])
    assert stub is not None
    assert note.addresses_rule_ids == stub.addresses_rule_ids
    assert [c.ref for c in note.citations] == [c.ref for c in stub.citations]
    assert note.advisory is True and "verdict" not in note.model_dump()


def test_claude_path_falls_back_to_stub_on_refusal(cards, monkeypatch):
    client = _FakeClient(_FakeResponse(None, stop_reason="refusal"))
    note = _claude_agent(monkeypatch, client).triage_card(cards["S4"])
    assert note is not None and note.generated_by == "stub"  # degraded, not crashed


def test_claude_path_falls_back_to_stub_on_error(cards, monkeypatch):
    note = _claude_agent(monkeypatch, _FakeClient(raises=True)).triage_card(cards["S4"])
    assert note is not None and note.generated_by == "stub"  # error degrades to stub


# --- interactive ask (Q2): user asks the agent a free-text question -----------


def test_stub_ask_is_grounded_not_fabricated(cards):
    """AI off: ask returns a grounded, retrieval-based answer EXPLICITLY framed as not generated,
    with deterministic citations — never fabricated prose, never a verdict (ADR-0001/0006)."""
    reply = StubTriageAgent().ask(cards["S4"], "why was this escalated?")
    assert isinstance(reply, AgentReply)
    assert reply.advisory is True and reply.agent == "qc_triage"
    assert reply.generated_by == "stub" and reply.model is None
    assert reply.question == "why was this escalated?"
    assert "AI assistance is off" in reply.answer  # honest: retrieval, not a generated answer
    assert reply.citations  # grounded in corpus/findings
    assert "verdict" not in reply.model_dump()  # advisory only


def test_ask_answers_even_a_clean_card(cards):
    """Unlike triage_card (None on a clean card), ask answers ANY card — the operator may ask about
    a PROCEED — and the stub stays honest (grounded retrieval, no fabrication)."""
    assert triage_card(cards["S1"]) is None  # clean → no auto-triage note
    reply = ask_agent(cards["S1"], "is the coverage adequate?", agent=StubTriageAgent())
    assert reply.answer and reply.generated_by == "stub" and reply.advisory is True


def test_claude_ask_answer_is_llm_but_citations_stay_deterministic(cards, monkeypatch):
    """On the live path the model writes ONLY the answer prose; provenance (citations) stays
    deterministic — identical to the stub's for the same card + question."""
    client = _FakeClient(_FakeResponse('{"answer": "MODEL answer"}'))
    reply = _claude_agent(monkeypatch, client).ask(cards["S4"], "cause?")
    assert reply.generated_by == "claude" and reply.answer == "MODEL answer"
    stub = StubTriageAgent().ask(cards["S4"], "cause?")
    assert [c.ref for c in reply.citations] == [c.ref for c in stub.citations]
    assert reply.advisory is True and "verdict" not in reply.model_dump()


def test_claude_ask_falls_back_to_stub_on_error(cards, monkeypatch):
    reply = _claude_agent(monkeypatch, _FakeClient(raises=True)).ask(cards["S4"], "cause?")
    assert reply.generated_by == "stub"  # error degrades to the grounded stub, not a crash


class _RecordingClient(_FakeClient):
    """Records the kwargs create() was called with, so a test can assert the token budget."""

    def __init__(self, response=None):
        super().__init__(response=response)
        self.create_kwargs: dict = {}

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return self._response


def test_claude_ask_requests_a_larger_budget_than_the_two_field_triage_note(cards, monkeypatch):
    """Regression (root cause): the free-text `ask` answer must request a bigger token budget
    than `triage_card`'s two short fields. At the old shared 1024 a grounded answer to a
    flagged-card question truncated mid-string, yielding invalid JSON that silently degraded
    to the stub on exactly the cards where a written answer matters most."""
    from bayleaf.triage.agent import _ASK_MAX_TOKENS

    client = _RecordingClient(_FakeResponse('{"answer": "MODEL answer"}'))
    agent = _claude_agent(monkeypatch, client)
    agent.ask(cards["S4"], "cause?")
    assert client.create_kwargs["max_tokens"] == _ASK_MAX_TOKENS
    assert agent.max_tokens < _ASK_MAX_TOKENS  # bigger than the two-field triage_card budget


def test_claude_ask_falls_back_to_stub_on_truncation(cards, monkeypatch):
    """A max_tokens-truncated response leaves unterminated JSON; degrade to the grounded stub
    cleanly (via the explicit stop_reason guard) rather than reading as an opaque parse error."""
    truncated = _FakeResponse('{"answer": "half-written ans', stop_reason="max_tokens")
    reply = _claude_agent(monkeypatch, _RecordingClient(truncated)).ask(cards["S4"], "cause?")
    assert reply.generated_by == "stub" and reply.answer  # degraded, not crashed


def test_claude_triage_falls_back_to_stub_on_truncation(cards, monkeypatch):
    """Same truncation guard on the auto-triage note path."""
    truncated = _FakeResponse('{"likely_cause": "half', stop_reason="max_tokens")
    note = _claude_agent(monkeypatch, _RecordingClient(truncated)).triage_card(cards["S4"])
    assert note is not None and note.generated_by == "stub"


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


def test_ask_endpoint_returns_advisory_reply():
    resp = client.post("/api/runs/mock_run_01/cards/S4/ask", json={"question": "why escalated?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["advisory"] is True and body["agent"] == "qc_triage"
    assert body["generated_by"] == "stub"  # AI off by default
    assert "verdict" not in body  # never decides
    assert body["question"] == "why escalated?" and body["answer"]


def test_ask_endpoint_answers_a_clean_card_and_404s_for_unknown():
    # a clean card has no triage note but CAN be asked about (200, not 404)
    ok = client.post("/api/runs/mock_run_01/cards/S1/ask", json={"question": "ok?"})
    assert ok.status_code == 200
    bad_sample = client.post("/api/runs/mock_run_01/cards/NOPE/ask", json={"question": "x"})
    assert bad_sample.status_code == 404
    bad_run = client.post("/api/runs/NOPE/cards/S4/ask", json={"question": "x"})
    assert bad_run.status_code == 404


def test_ask_endpoint_rejects_empty_or_extra_fields():
    empty = client.post("/api/runs/mock_run_01/cards/S4/ask", json={"question": ""})
    assert empty.status_code == 422  # min_length=1
    bad = client.post("/api/runs/mock_run_01/cards/S4/ask", json={"question": "x", "role": "admin"})
    assert bad.status_code == 422  # extra="forbid"
