"""Tests for the advisory node-authoring agent (offline, stub only; T-046).

These run fully offline (no API). They pin the guardrails that make agent #6 safe: given a
natural-language request for a bioinformatics tool, the proposal is advisory, cites the tool-card
corpus + the tool it proposes, carries typed ports drawn ONLY from the real artifact-kind
vocabulary (unknown kinds flagged reserved, never wired), suggests locators, and NEVER touches a
verdict or runs a tool (compose != execute). The live Claude path is exercised with a fake client
to prove it degrades safely and that the model only phrases the prose.
"""

from bayleaf.node_author import (
    ARTIFACT_KINDS,
    NODE_AUTHOR_CORPUS_VERSION,
    NodeProposal,
    PortSpec,
    StubNodeAuthor,
    ToolCardEntry,
    ToolCardRetriever,
    load_tool_card_corpus,
    propose_node,
)

# --- corpus + retrieval -----------------------------------------------------


def test_corpus_loads_and_is_well_formed():
    corpus = load_tool_card_corpus()
    assert len(corpus) >= 8  # curated ~8-12 entries
    ids = [e.id for e in corpus]
    assert len(set(ids)) == len(ids)  # unique ids
    for e in corpus:
        assert isinstance(e, ToolCardEntry)
        assert e.id.startswith(("tool_", "source_"))
        assert e.tool and e.version and e.title and e.keywords and e.summary and e.rationale
        assert e.source
        # No verdict/confidence leaks into the corpus — a tool-card must not pre-decide the gate.
        assert not hasattr(e, "verdict")
        assert not hasattr(e, "confidence")
        assert e.stage is None or isinstance(e.stage, str)


def test_corpus_ports_are_typed_and_reserved_flag_matches_vocabulary():
    """Every corpus port's `known` flag is exactly `kind in ARTIFACT_KINDS` (the reserved guard)."""
    for e in load_tool_card_corpus():
        for p in (*e.inputs, *e.outputs):
            assert isinstance(p, PortSpec)
            assert p.known == (p.kind in ARTIFACT_KINDS)
        # Each suggested locator resolves a REAL kind (a locator is a run-layout output/reference).
        for loc in e.locators:
            assert loc.kind in ARTIFACT_KINDS


def test_retriever_ranks_fastp_by_name():
    """A direct tool-name hit retrieves the matching card (tool name is full-weight)."""
    hits = ToolCardRetriever.from_default_corpus().retrieve("fastp", top_k=3)
    assert hits and hits[0].entry.id == "tool_fastp"
    assert 0.0 < hits[0].score <= 1.0  # heuristic overlap, normalized
    assert all(hits[i].score >= hits[i + 1].score for i in range(len(hits) - 1))


def test_retriever_ranks_by_function_description():
    """A functional description (no tool name) still routes to the right card."""
    r = ToolCardRetriever.from_default_corpus()
    assert r.retrieve("a tool that calls variants from a BAM", top_k=3)[0].entry.id == (
        "tool_bcftools_call"
    )
    assert r.retrieve("aggregate all the QC reports into one summary", top_k=3)[0].entry.id == (
        "tool_multiqc"
    )
    assert r.retrieve("compute coverage depth over a panel", top_k=3)[0].entry.id == "tool_mosdepth"


def test_retriever_returns_nothing_for_empty_query():
    assert ToolCardRetriever.from_default_corpus().retrieve("", top_k=3) == []


# --- the agent / propose_node -----------------------------------------------


def test_request_yields_advisory_matched_proposal():
    proposal = propose_node("add a tool that trims adapters and does read QC")
    assert isinstance(proposal, NodeProposal)
    assert proposal.advisory is True
    assert proposal.agent == "node_author"
    assert proposal.generated_by == "stub"
    assert proposal.mode == "stub"  # frontend AgentProposal.mode alias
    assert proposal.model is None  # stub uses no model
    assert proposal.matched is True
    assert proposal.tool == "fastp"
    assert proposal.version == "0.23.4"
    assert proposal.stage == "read_qc"
    assert proposal.summary and proposal.rationale
    assert proposal.corpus_version == NODE_AUTHOR_CORPUS_VERSION


def test_proposal_ports_use_only_real_kinds_and_flag_unknowns_reserved():
    """The proposed fastp node's live ports are real kinds; unknowns are reserved, not wired."""
    proposal = propose_node("fastp")
    live = [p for p in (*proposal.inputs, *proposal.outputs) if p.known]
    reserved_ports = [p for p in (*proposal.inputs, *proposal.outputs) if not p.known]
    assert live, "expected at least one live typed port"
    assert all(p.kind in ARTIFACT_KINDS for p in live)
    # fastp documents real-but-unregistered I/O (adapter_fasta in) as reserved. fastp_html was
    # promoted into the real vocabulary (W4 full-port wiring), so it is now a live typed port —
    # NOT reserved — proving the backend mirror tracks the frontend's ARTIFACT_KINDS.
    assert reserved_ports and all(p.kind not in ARTIFACT_KINDS for p in reserved_ports)
    assert proposal.reserved_kinds == sorted({p.kind for p in reserved_ports})
    assert "adapter_fasta" in proposal.reserved_kinds
    assert "fastp_html" in ARTIFACT_KINDS and "fastp_html" not in proposal.reserved_kinds


def test_no_proposal_ever_invents_a_port_kind_across_the_corpus():
    """For every retrievable tool, a live (known) port only ever carries a vocabulary kind."""
    for entry in load_tool_card_corpus():
        proposal = propose_node(entry.tool)
        for p in (*proposal.inputs, *proposal.outputs):
            # A port is either a real vocabulary kind (live) or explicitly reserved, never invented.
            assert p.known == (p.kind in ARTIFACT_KINDS)
            if not p.known:
                assert p.kind in proposal.reserved_kinds


def test_matched_proposal_suggests_locators_for_real_kinds():
    proposal = propose_node("samtools markdup")
    assert proposal.tool == "samtools markdup"
    assert proposal.locators, "expected suggested run-layout locators"
    for loc in proposal.locators:
        assert loc.kind in ARTIFACT_KINDS


def test_proposal_cites_corpus_card_doc_and_tool():
    proposal = propose_node("call variants")
    kinds = {c.source_kind for c in proposal.citations}
    assert kinds == {"knowledge", "card_doc", "tool"}
    know = [c for c in proposal.citations if c.source_kind == "knowledge"]
    assert know and all(c.ref.startswith(("tool_", "source_")) for c in know)
    assert all(c.score is not None and 0.0 <= c.score <= 1.0 for c in know)
    assert any(c.ref == "tool_bcftools_call" for c in know)
    # The tool + card-doc refs anchor the proposal to exactly what it proposes.
    tool = [c for c in proposal.citations if c.source_kind == "tool"]
    doc = [c for c in proposal.citations if c.source_kind == "card_doc"]
    assert tool and tool[0].ref == "bcftools call"
    assert doc and doc[0].ref  # a non-empty provenance string


def test_empty_and_malformed_request_degrade_gracefully():
    """A blank/whitespace or unmatched request defers to a human and fabricates no node."""
    for bad in ("", "   ", "\n\t", "qwerty zxcvb nonsense request"):
        proposal = propose_node(bad)
        assert isinstance(proposal, NodeProposal)
        assert proposal.advisory is True
        assert proposal.matched is False
        assert proposal.tool is None and proposal.version is None
        assert proposal.inputs == [] and proposal.outputs == []
        assert proposal.reserved_kinds == []
        assert not [c for c in proposal.citations if c.source_kind == "knowledge"]
        assert "human reviewer" in proposal.rationale.lower()


def test_proposal_never_touches_the_verdict():
    """The advisory proposal carries no verdict/confidence field (ADR-0001 invariant)."""
    dumped = propose_node("fastp").model_dump()
    assert "verdict" not in dumped
    assert "confidence" not in dumped
    # It is structurally advisory: the pinned flag can never be False.
    assert dumped["advisory"] is True


def test_advisory_flag_is_fixed_true():
    """`advisory` is a Literal[True] — attempting to unset it is a validation error."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        NodeProposal(agent="node_author", request="x", summary="s", rationale="r", advisory=False)  # type: ignore[arg-type]


def test_proposal_content_hash_is_stable_and_deterministic():
    a = propose_node("mosdepth coverage")
    b = propose_node("mosdepth coverage")
    assert len(a.content_hash) == 64
    assert a.content_hash == b.content_hash  # deterministic across runs


def test_agent_defers_to_human_when_corpus_empty():
    """With an empty corpus every request defers to a human — no tool/ports fabricated."""
    agent = StubNodeAuthor(retriever=ToolCardRetriever(()))  # empty corpus
    proposal = agent.propose("fastp")
    assert proposal.matched is False
    assert proposal.tool is None
    assert not proposal.citations
    assert "human reviewer" in proposal.rationale.lower()


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
    from bayleaf.node_author.agent import ClaudeNodeAuthor

    agent = ClaudeNodeAuthor()
    monkeypatch.setattr(agent, "_get_client", lambda: client)
    return agent


def test_claude_path_prose_is_llm_but_shape_and_citations_stay_deterministic(monkeypatch):
    """On the live path the model writes ONLY the prose; ports + provenance stay deterministic."""
    client = _FakeClient(
        _FakeResponse('{"summary": "MODEL summary", "rationale": "MODEL rationale"}')
    )
    proposal = _claude_agent(monkeypatch, client).propose("fastp")
    assert proposal.generated_by == "claude"
    assert proposal.model  # carries the model id
    assert proposal.summary == "MODEL summary"  # prose comes from the model
    assert proposal.rationale == "MODEL rationale"
    # ...but tool/version/ports/reserved + the citations match the deterministic stub exactly.
    stub = StubNodeAuthor().propose("fastp")
    assert proposal.tool == stub.tool
    assert proposal.version == stub.version
    assert [p.kind for p in proposal.inputs] == [p.kind for p in stub.inputs]
    assert [p.kind for p in proposal.outputs] == [p.kind for p in stub.outputs]
    assert proposal.reserved_kinds == stub.reserved_kinds
    assert [c.ref for c in proposal.citations] == [c.ref for c in stub.citations]
    assert proposal.advisory is True and "verdict" not in proposal.model_dump()


def test_claude_path_falls_back_to_stub_on_refusal(monkeypatch):
    client = _FakeClient(_FakeResponse(None, stop_reason="refusal"))
    proposal = _claude_agent(monkeypatch, client).propose("fastp")
    assert proposal.generated_by == "stub"  # degraded, not crashed


def test_claude_path_falls_back_to_stub_on_error(monkeypatch):
    proposal = _claude_agent(monkeypatch, _FakeClient(raises=True)).propose("fastp")
    assert proposal.generated_by == "stub"  # error degrades to stub


def test_claude_path_no_match_returns_stub_defer_without_calling_model(monkeypatch):
    """An unmatched request never reaches the model — it returns the conservative stub proposal."""
    # A client that would raise if called proves the model is never invoked when there is no hit.
    proposal = _claude_agent(monkeypatch, _FakeClient(raises=True)).propose("qwerty nonsense")
    assert proposal.generated_by == "stub"
    assert proposal.matched is False
