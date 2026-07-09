"""Tests for the advisory pipeline-repair agent (offline, stub only).

These run fully offline (no API). They pin the guardrails that make agent #2 safe: given a
recurring issue signature rolled up from the served runs (the same shape the monitoring view
computes), the proposal is advisory, cites the remediation corpus + the addressed
rule/signature, attaches to a concrete stage/gate DETERMINISTICALLY, and NEVER touches the
verdict. The live Claude path is exercised with a fake client to prove it degrades safely.
"""

from pathlib import Path

import pytest

from pipeguard import load_run, run_gate
from pipeguard.models import Gate
from pipeguard.pipeline_repair import (
    PipelineStage,
    RecurringSignature,
    RemediationRetriever,
    RepairProposal,
    StubRepairAgent,
    assemble_recurring_signatures,
    load_remediation_corpus,
    propose_repair,
    recurring_signature,
)
from pipeguard.synthesis import StubSynthesizer

DATA = Path(__file__).resolve().parent.parent / "data"
# PIPE-001 (a logged pipeline failure for S5) recurs across these two runs — a genuine
# cross-run recurring signature, exactly what agent #2 is meant to reason over.
_RECURRENCE_RUNS = ("mock_run_02", "mock_run_03")


def _cards(run_id: str):
    return run_gate(load_run(DATA / run_id), synthesizer=StubSynthesizer())


@pytest.fixture(scope="module")
def runs():
    """A {run_id: cards} rollup over the two runs that share the recurring PIPE-001 signature."""
    return {rid: _cards(rid) for rid in _RECURRENCE_RUNS}


@pytest.fixture(scope="module")
def pipe_signature(runs) -> RecurringSignature:
    """The recurring PIPE-001 signature assembled from the served runs (count == 2)."""
    sigs = [s for s in assemble_recurring_signatures(runs) if s.rule_id == "PIPE-001"]
    assert sigs, "expected a recurring PIPE-001 signature across the mock runs"
    return sigs[0]


# --- corpus + retrieval -----------------------------------------------------


def test_corpus_loads_and_is_well_formed():
    corpus = load_remediation_corpus()
    assert len(corpus) >= 8  # curated ~8-12 entries
    ids = [e.id for e in corpus]
    assert len(set(ids)) == len(ids)  # unique ids
    for e in corpus:
        assert e.id.startswith("repair_")
        assert e.keywords and e.summary and e.rationale and e.source
        # No verdict/confidence leaks into the corpus — a remediation must not pre-decide the gate.
        assert not hasattr(e, "verdict")
        assert not hasattr(e, "confidence")
        # attach_to / scope stay in the controlled vocabulary (or null for a workflow-wide fix).
        assert e.attach_to is None or isinstance(e.attach_to, PipelineStage)
        assert e.scope is None or isinstance(e.scope, Gate)


def test_retriever_ranks_pipeline_entry_for_pipe_signature(pipe_signature):
    retriever = RemediationRetriever.from_default_corpus()
    query = f"{pipe_signature.rule_id} {pipe_signature.title} {pipe_signature.gate.value}"
    hits = retriever.retrieve(query, top_k=3)
    assert hits, "expected at least one hit"
    assert hits[0].entry.id == "repair_pipeline_step_failure"
    assert 0.0 < hits[0].score <= 1.0  # heuristic overlap, normalized
    assert all(hits[i].score >= hits[i + 1].score for i in range(len(hits) - 1))


def test_retriever_ranks_barcode_entry_by_rule_id():
    """A direct rule_id hit retrieves the matching remediation (rule_ids are full-weight)."""
    hits = RemediationRetriever.from_default_corpus().retrieve(
        "PROV-001 barcode does not match the declared sample sheet preflight", top_k=3
    )
    assert hits and hits[0].entry.id == "repair_barcode_index_swap"


def test_retriever_returns_nothing_for_empty_query():
    assert RemediationRetriever.from_default_corpus().retrieve("", top_k=3) == []


# --- assembling the recurring-signature input -------------------------------


def test_assemble_counts_signature_across_runs(runs, pipe_signature):
    """The assembler mirrors the monitoring counter: PIPE-001 recurs across both runs."""
    assert pipe_signature.count == 2
    assert set(pipe_signature.run_ids) == set(_RECURRENCE_RUNS)
    assert pipe_signature.gate is Gate.PREFLIGHT  # PIPE-001 is caught at preflight


def test_recurring_signature_lookup(runs, pipe_signature):
    assert recurring_signature(runs, pipe_signature.signature) == pipe_signature
    assert recurring_signature(runs, "no-such-signature") is None


# --- the agent / propose_repair ---------------------------------------------


def test_recurring_signature_yields_advisory_proposal(pipe_signature):
    proposal = propose_repair(pipe_signature)
    assert isinstance(proposal, RepairProposal)
    assert proposal.advisory is True
    assert proposal.agent == "pipeline_repair"
    assert proposal.generated_by == "stub"
    assert proposal.mode == "stub"  # frontend AgentProposal.mode alias
    assert proposal.model is None  # stub uses no model
    assert proposal.summary and proposal.rationale
    assert proposal.addresses_rule_id == "PIPE-001"
    assert proposal.addresses_signature == pipe_signature.signature
    assert proposal.signature_count == 2


def test_proposal_attaches_to_a_stage_and_gate_deterministically():
    """A barcode signature attaches the guard to demux · preflight (from the corpus, not an LLM)."""
    sig = RecurringSignature(
        signature="deadbeefdeadbeef",
        rule_id="PROV-001",
        title="Barcode does not match the declared sample sheet",
        gate=Gate.PREFLIGHT,
        count=4,
        run_ids=["mock_run_01", "mock_run_02"],
    )
    proposal = propose_repair(sig)
    assert proposal.attach_to is PipelineStage.DEMUX
    assert proposal.scope is Gate.PREFLIGHT


def test_pipe_proposal_scope_is_preflight(pipe_signature):
    proposal = propose_repair(pipe_signature)
    # PIPE-001's remediation is workflow-wide (no single stage) but scoped to the preflight gate.
    assert proposal.attach_to is None
    assert proposal.scope is Gate.PREFLIGHT


def test_proposal_cites_corpus_rule_and_signature(pipe_signature):
    proposal = propose_repair(pipe_signature)
    kinds = {c.source_kind for c in proposal.citations}
    assert kinds == {"knowledge", "rule", "signature"}
    know = [c for c in proposal.citations if c.source_kind == "knowledge"]
    assert know and all(c.ref.startswith("repair_") for c in know)
    assert all(c.score is not None and 0.0 <= c.score <= 1.0 for c in know)
    assert any(c.ref == "repair_pipeline_step_failure" for c in know)
    # The rule + signature refs anchor the proposal to exactly what recurred.
    rule = [c for c in proposal.citations if c.source_kind == "rule"]
    sig = [c for c in proposal.citations if c.source_kind == "signature"]
    assert rule and rule[0].ref == "PIPE-001"
    assert sig and sig[0].ref == pipe_signature.signature


def test_proposal_never_touches_the_verdict(pipe_signature):
    """The advisory proposal carries no verdict/confidence field (ADR-0001 invariant)."""
    dumped = propose_repair(pipe_signature).model_dump()
    assert "verdict" not in dumped
    assert "confidence" not in dumped


def test_proposal_content_hash_is_stable_and_deterministic(pipe_signature):
    a = propose_repair(pipe_signature)
    b = propose_repair(pipe_signature)
    assert len(a.content_hash) == 64
    assert a.content_hash == b.content_hash  # deterministic across runs


def test_agent_defers_to_human_when_corpus_empty(pipe_signature):
    """With no corpus match, the stub proposes nothing concrete and defers to a human."""
    agent = StubRepairAgent(retriever=RemediationRetriever(()))  # empty corpus
    proposal = agent.propose(pipe_signature)
    assert not [c for c in proposal.citations if c.source_kind == "knowledge"]
    assert "human reviewer" in proposal.rationale.lower()
    assert proposal.attach_to is None
    # The addressed rule/signature are still cited even when no remediation matched.
    assert proposal.addresses_rule_id == "PIPE-001"
    assert {c.source_kind for c in proposal.citations} == {"rule", "signature"}
    # scope still anchors to the signature's own gate.
    assert proposal.scope is Gate.PREFLIGHT


# --- the Claude path (mocked): the flip must degrade safely, never crash -----


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
    from pipeguard.pipeline_repair.agent import ClaudeRepairAgent

    agent = ClaudeRepairAgent()
    monkeypatch.setattr(agent, "_get_client", lambda: client)
    return agent


def test_claude_path_prose_is_llm_but_target_and_citations_stay_deterministic(
    pipe_signature, monkeypatch
):
    """On the live path the model writes ONLY the prose; target + provenance stay deterministic."""
    client = _FakeClient(
        _FakeResponse('{"summary": "MODEL summary", "rationale": "MODEL rationale"}')
    )
    proposal = _claude_agent(monkeypatch, client).propose(pipe_signature)
    assert proposal.generated_by == "claude"
    assert proposal.model  # carries the model id
    assert proposal.summary == "MODEL summary"  # prose comes from the model
    assert proposal.rationale == "MODEL rationale"
    # ...but attach_to/scope + the citations match the deterministic stub exactly.
    stub = StubRepairAgent().propose(pipe_signature)
    assert proposal.attach_to == stub.attach_to
    assert proposal.scope == stub.scope
    assert [c.ref for c in proposal.citations] == [c.ref for c in stub.citations]
    assert proposal.advisory is True and "verdict" not in proposal.model_dump()


def test_claude_path_falls_back_to_stub_on_refusal(pipe_signature, monkeypatch):
    client = _FakeClient(_FakeResponse(None, stop_reason="refusal"))
    proposal = _claude_agent(monkeypatch, client).propose(pipe_signature)
    assert proposal.generated_by == "stub"  # degraded, not crashed


def test_claude_path_falls_back_to_stub_on_error(pipe_signature, monkeypatch):
    proposal = _claude_agent(monkeypatch, _FakeClient(raises=True)).propose(pipe_signature)
    assert proposal.generated_by == "stub"  # error degrades to stub
