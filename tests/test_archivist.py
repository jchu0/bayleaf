"""Tests for the advisory Archivist agent #3 (offline, stub-first).

These run fully offline (no API). They pin the guardrails that make the librarian safe: the
digest is ADVISORY, carries NO verdict/confidence field, organizes only runs/artifacts that
exist, preserves origin, and NEVER touches a decision (ADR-0001 / design §5.2). The Claude
path is exercised with a fake client to prove it degrades to the stub and never authors the
deterministic index.
"""

from pathlib import Path

import pytest

from api.archivist import (
    ArchiveDigest,
    ClaudeArchivist,
    RunArchiveInput,
    StubArchivist,
    archive_digest,
    build_run_input_from_dir,
    get_archivist_agent,
    main,
)

DATA = Path(__file__).resolve().parent.parent / "data"
RUN_1 = DATA / "mock_run_01"
RUN_2 = DATA / "mock_run_02"
RUN_3 = DATA / "mock_run_03"


@pytest.fixture(scope="module")
def run1() -> RunArchiveInput:
    return build_run_input_from_dir(RUN_1)


@pytest.fixture(scope="module")
def all_runs() -> list[RunArchiveInput]:
    return [build_run_input_from_dir(d) for d in (RUN_1, RUN_2, RUN_3)]


# --- the deterministic stub digest ------------------------------------------


def test_stub_digest_over_one_run_is_advisory(run1: RunArchiveInput):
    digest = archive_digest([run1])
    assert isinstance(digest, ArchiveDigest)
    assert digest.advisory is True
    assert digest.agent == "archivist"
    assert digest.generated_by == "stub"
    assert digest.model is None  # the stub uses no model
    assert digest.scope == "run"
    assert digest.run_ids == [run1.run_id]
    assert digest.n_runs == 1
    assert digest.summary and digest.proposed_action  # human-readable digest + proposal


def test_digest_carries_no_verdict_or_confidence_field(run1: RunArchiveInput):
    """The digest is structurally unable to state a decision (ADR-0001 / §5.2.1)."""
    dumped = archive_digest([run1]).model_dump()
    assert "verdict" not in dumped  # only the roll-up `verdict_counts`, never a decision
    assert "confidence" not in dumped
    assert "decision" not in dumped
    # It also cannot mutate the source cards' verdicts (it never touches them).
    assert all(c.verdict is not None for c in run1.cards)


def test_least_privilege_input_has_no_intake_identity():
    """The librarian's input carries NO subject/operator PII, so none can be indexed or egressed
    (design §5.2.7 least-privilege)."""
    fields = set(RunArchiveInput.model_fields)
    assert not fields & {"subject_id", "tissue", "submitted_by"}


def test_digest_counts_match_the_cards(run1: RunArchiveInput):
    digest = archive_digest([run1])
    assert digest.n_samples == len(run1.cards)
    assert digest.n_attention == sum(1 for c in run1.cards if c.is_actionable)
    assert sum(digest.verdict_counts.values()) == len(run1.cards)
    # verdict_counts is grounded per-card — never fabricated.
    for card in run1.cards:
        assert digest.verdict_counts[card.verdict.value] >= 1


def test_index_scope_for_multiple_runs(all_runs: list[RunArchiveInput]):
    digest = archive_digest(all_runs)
    assert digest.scope == "index"
    assert digest.n_runs == len(all_runs)
    assert set(digest.run_ids) == {r.run_id for r in all_runs}
    # A cross-run index is a bounded rollup: no per-artifact manifest.
    assert digest.manifest == []
    assert sum(digest.by_status.values()) == len(all_runs)
    assert sum(digest.by_origin.values()) == len(all_runs)


def test_manifest_lists_only_real_artifacts(run1: RunArchiveInput):
    digest = archive_digest([run1])
    assert digest.manifest, "a single-run digest prepares an export manifest"
    on_disk = {p.name for p in RUN_1.iterdir() if p.is_file()}
    for ref in digest.manifest:
        assert ref.name in on_disk  # never invents an artifact
        assert ref.origin == run1.origin  # origin preserved verbatim
        assert ref.kind  # librarian classification present
    assert digest.n_artifacts == len(digest.manifest)


def test_archive_ready_reflects_lifecycle_only(run1: RunArchiveInput):
    """`archive_ready` restates the already-decided lifecycle state, never derives a new one."""
    digest = archive_digest([run1])
    assert digest.archive_ready == (run1.status == "released")
    # A run still pending review is never proposed archive-ready.
    if run1.status == "needs_review":
        assert digest.archive_ready is False
        assert digest.n_archive_ready == 0
        assert "hold" in digest.proposed_action.lower()


def test_citations_reference_every_covered_run(all_runs: list[RunArchiveInput]):
    digest = archive_digest(all_runs)
    run_cites = {c.ref for c in digest.citations if c.source_kind == "run"}
    assert run_cites == {r.run_id for r in all_runs}
    # Every signature citation is a real finding signature on the covered cards.
    real_signatures = {f.signature for r in all_runs for c in r.cards for f in c.findings}
    sig_cites = {c.ref for c in digest.citations if c.source_kind == "signature"}
    assert sig_cites <= real_signatures


def test_recurring_signatures_are_grounded(run1: RunArchiveInput):
    digest = archive_digest([run1])
    real = {f.signature for c in run1.cards for f in c.findings}
    for sig in digest.recurring_signatures:
        assert sig.signature in real  # never fabricated
        assert sig.count >= 1


def test_content_hash_is_stable(run1: RunArchiveInput):
    a = archive_digest([run1])
    b = archive_digest([run1])
    assert len(a.content_hash) == 64
    assert a.content_hash == b.content_hash  # deterministic across runs


def test_empty_input_yields_an_empty_digest():
    digest = archive_digest([])
    assert digest.advisory is True
    assert digest.n_runs == 0
    assert digest.manifest == []
    assert "no runs" in digest.summary.lower()


def test_digest_over_a_clean_run_with_no_recurring_signatures():
    """Regression: a released, all-PROCEED run has runs present but NO recurring signatures.
    The run-scope summary must guard `signatures[0]` (it was evaluated eagerly and 500'd the
    /archive-digest endpoint for any clean run). Uses a real all-clean GIAB run dir."""
    clean = build_run_input_from_dir(DATA / "RUN-2026-06-05-GIAB-A")
    assert sum(len(c.findings) for c in clean.cards) == 0  # precondition: nothing recurring
    digest = archive_digest([clean])  # must not raise
    assert digest.recurring_signatures == []
    assert digest.summary and digest.proposed_action  # built, not crashed
    assert "Top recurring signature" not in digest.summary


def test_default_agent_is_the_stub(monkeypatch):
    monkeypatch.delenv("BAYLEAF_ARCHIVIST_AGENT", raising=False)
    assert isinstance(get_archivist_agent(), StubArchivist)


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


def _claude_agent(monkeypatch, client) -> ClaudeArchivist:
    agent = ClaudeArchivist()
    monkeypatch.setattr(agent, "_get_client", lambda: client)
    return agent


def test_claude_path_prose_is_llm_but_index_stays_deterministic(run1, monkeypatch):
    """On the live path the model writes ONLY the summary; the index/manifest stay deterministic."""
    client = _FakeClient(_FakeResponse('{"summary": "MODEL summary of the archive."}'))
    digest = _claude_agent(monkeypatch, client).digest([run1])
    assert digest.generated_by == "claude"
    assert digest.model  # the model id is recorded
    assert digest.summary == "MODEL summary of the archive."  # prose from the model
    # ...but every organizational field matches the deterministic stub exactly.
    stub = StubArchivist().digest([run1])
    assert digest.verdict_counts == stub.verdict_counts
    assert digest.manifest == stub.manifest
    assert digest.proposed_action == stub.proposed_action
    assert [c.ref for c in digest.citations] == [c.ref for c in stub.citations]
    assert digest.advisory is True and "verdict" not in digest.model_dump()


def test_claude_path_falls_back_to_stub_on_refusal(run1, monkeypatch):
    client = _FakeClient(_FakeResponse(None, stop_reason="refusal"))
    digest = _claude_agent(monkeypatch, client).digest([run1])
    assert digest.generated_by == "stub"  # degraded, not crashed
    assert digest.summary == StubArchivist().digest([run1]).summary


def test_claude_path_falls_back_to_stub_on_error(run1, monkeypatch):
    digest = _claude_agent(monkeypatch, _FakeClient(raises=True)).digest([run1])
    assert digest.generated_by == "stub"  # error degrades to stub


def test_claude_path_empty_input_never_calls_the_api(monkeypatch):
    # A raising client proves the empty-set guard returns before any API call.
    digest = _claude_agent(monkeypatch, _FakeClient(raises=True)).digest([])
    assert digest.generated_by == "stub" and digest.n_runs == 0


# --- CLI smoke --------------------------------------------------------------


def test_cli_main_runs_offline(capsys):
    assert main([str(RUN_1)]) == 0
    out = capsys.readouterr().out
    assert "Archive digest (stub)" in out
    assert "proposal" in out
