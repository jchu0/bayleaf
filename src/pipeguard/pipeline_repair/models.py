"""Records for the advisory pipeline-repair agent (agent #2, ADR-0012 / ADR-0008).

Four record shapes live here:

  * :class:`PipelineStage` — the closed set of pipeline stages a proposed remediation can
    attach to. Grounded in the Pipeline Builder's node ``stage`` vocabulary (there is no
    ``StageKind`` type in code yet — the builder ships in the React/HTML prototype — so this
    is the "small literal set" the handoff calls for).
  * :class:`RecurringSignature` — the agent's INPUT: one recurring issue signature rolled up
    from the monitoring view, the same shape the monitoring endpoint computes
    (``api.main.MonitoringSignature``). Assembled by :func:`assemble_recurring_signatures`.
  * :class:`RemediationEntry` — one curated remediation-template record in the knowledge
    corpus (ADR-0009). Retrieval-only; it encodes NO verdict and NO threshold value.
  * :class:`RepairProposal` — the agent's ADVISORY output for one recurring signature,
    mirroring the frontend's ``AgentProposal`` shape. ``advisory`` is pinned ``True`` and
    there is deliberately no verdict or confidence field: the agent proposes a
    human-reviewed fix, it never edits a pipeline or sets a verdict (ADR-0001).

All reuse the shared identity/hash/time helpers so they acquire type-prefixed ids, content
hashes, and UTC timestamps the same way every other record does.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from ..identifiers import SCHEMA_VERSION, new_id, utc_now
from ..identifiers import content_hash as _content_hash
from ..models import DecisionCard, Gate

# Version of the curated remediation corpus + proposal templating; bump when either the
# corpus schema or the stub's phrasing changes so cached/persisted proposals stay traceable.
PIPELINE_REPAIR_CORPUS_VERSION = "1.0.0"


class PipelineStage(str, Enum):
    """Where a proposed remediation attaches in the pipeline graph (frontend ``attachTo``).

    Grounded in the Pipeline Builder's node ``stage`` vocabulary from the Phase-2 prototype
    (``demux → read_qc → align → markdup → coverage → variant_call → filter → qc_aggregate``,
    see ``source/PipeGuard.dc.html``), plus ``intake`` for the accessioning / metadata step
    that precedes the compute graph. No ``StageKind`` type exists in code yet, so this is the
    small, closed literal set the handoff (``handoffs/03-builder-phase2-README.md`` §6) calls
    for. It is a *location*, never a decision — attaching a fix here changes nothing on the
    gate until a human approves and the builder emits a new ``run_layout.yaml``.
    """

    INTAKE = "intake"  # accessioning / LIMS handoff — where provenance + metadata originate
    DEMUX = "demux"
    READ_QC = "read_qc"
    ALIGN = "align"
    MARKDUP = "markdup"
    COVERAGE = "coverage"
    VARIANT_CALL = "variant_call"
    FILTER = "filter"
    QC_AGGREGATE = "qc_aggregate"


class RecurringSignature(BaseModel):
    """A recurring issue signature rolled up from the monitoring view (the agent's INPUT).

    The same shape the monitoring endpoint already computes
    (``api.main.MonitoringSignature`` — a distinct :attr:`~pipeguard.models.Finding.signature`
    with its display metadata and its tally). :attr:`count` / :attr:`run_ids` are lifetime
    tallies over the served runs, **not** calibrated rates (CLAUDE.md life-science guardrail
    2). Frozen because it is an assembled fact the agent consumes and never mutates.
    """

    model_config = ConfigDict(frozen=True)

    signature: str = Field(..., description="Stable, rule-version-independent finding signature")
    rule_id: str = Field(..., description="rule_id of the finding this signature came from")
    title: str = Field(..., description="Human-readable finding title (first-sighting metadata)")
    gate: Gate = Field(..., description="Gate the addressed finding belongs to")
    count: int = Field(
        ..., ge=1, description="Occurrences across the served runs (a tally, not a rate)"
    )
    run_ids: list[str] = Field(default_factory=list, description="Runs the signature recurred in")


class RemediationEntry(BaseModel):
    """One curated remediation-template record (ADR-0009 knowledge corpus; ADR-0008 taxonomy).

    Maps an issue class (by ``rule_ids`` / ``keywords``) to a conservative, human-reviewed
    remediation: a :attr:`summary` (the proposed fix), the :attr:`attach_to` stage and
    :attr:`scope` gate it applies at, and a short :attr:`rationale` — each with a
    :attr:`source` citation so the proposal stays traceable. Retrieval-only: it encodes NO
    verdict and NO threshold *value* (the runbook owns thresholds — the template defers to
    "the runbook's configured gate/band" rather than inventing a number).
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Stable curated id, e.g. 'repair_barcode_index_swap'")
    kind: str = Field("remediation_template", description="KnowledgeRecord kind (schemas.md #15)")
    category: str | None = Field(
        None, description="Finding category this addresses (provenance|qc|coverage|…)"
    )
    rule_ids: list[str] = Field(
        default_factory=list, description="rule_ids this remediation addresses (e.g. PROV-001)"
    )
    title: str
    keywords: list[str] = Field(
        default_factory=list, description="Signature tokens used for keyword retrieval"
    )
    summary: str = Field(
        ..., description="Proposed, human-reviewed remediation (advisory; never auto-applied)"
    )
    attach_to: PipelineStage | None = Field(
        None, description="Stage the fix attaches to; None when the fix is workflow-wide"
    )
    scope: Gate | None = Field(None, description="Gate phase the fix guards")
    rationale: str = Field(..., description="Why this remediation; conservative + hedged")
    source: str = Field(..., description="Provenance/citation for the remediation")
    tags: list[str] = Field(default_factory=list)
    version: str = PIPELINE_REPAIR_CORPUS_VERSION


class RepairCitation(BaseModel):
    """One traceable reference behind a proposal — a corpus entry, the rule, or the signature.

    Keeping evidence and generated advice separable (CLAUDE.md life-science guardrail 4) lets
    a reader trace every proposal back to a curated remediation id, the ``rule_id`` it
    addresses, and the recurring ``signature`` it responds to. :attr:`score` is a **heuristic**
    keyword-overlap value in [0, 1] for knowledge hits — not a calibrated probability — and is
    ``None`` for the rule/signature references.
    """

    model_config = ConfigDict(frozen=True)

    source_kind: Literal["knowledge", "rule", "signature"]
    ref: str = Field(
        ..., description="Corpus id (repair_…), the finding's rule_id, or the signature"
    )
    title: str | None = None
    score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Heuristic keyword-overlap score for knowledge hits (NOT a probability)",
    )


class RepairProposal(BaseModel):
    """An ADVISORY remediation proposal for one recurring signature (frontend ``AgentProposal``).

    Mirrors the frontend ``AgentProposal`` (``agent`` / ``advisoryOnly`` / ``summary`` /
    ``attachTo`` / ``scope`` / ``mode``). ``advisory`` is pinned ``True`` and this record has
    no verdict or confidence field at all: the agent proposes a **human-reviewed** fix, it
    never edits a pipeline or sets/overrides a verdict (ADR-0001). ``attach_to`` / ``scope``
    and every citation are DETERMINISTIC — they come from the curated corpus and the addressed
    rule/signature, never from the LLM; only :attr:`summary` / :attr:`rationale` prose may be
    refined by the live agent. Uncertainty is carried in conservative phrasing and in the
    per-citation heuristic score.
    """

    id: str = Field(default_factory=lambda: new_id("repair"))
    advisory: Literal[True] = True
    agent: str = Field(..., description="Advisory agent name, e.g. 'pipeline_repair'")
    addresses_rule_id: str = Field(..., description="rule_id of the signature this addresses")
    addresses_signature: str = Field(
        ..., description="The recurring finding signature this proposal responds to"
    )
    signature_count: int = Field(
        ..., ge=1, description="Occurrences of the signature (a tally, not a rate)"
    )
    run_ids: list[str] = Field(default_factory=list, description="Runs the signature recurred in")
    summary: str = Field(..., description="The proposed, human-reviewed remediation (prose)")
    rationale: str = Field(..., description="Why this remediation; conservative + hedged (prose)")
    # attachTo / scope: DETERMINISTIC from the corpus, not the LLM. attach_to is None for a
    # workflow-wide fix (e.g. an operational retry guard that pins to no single stage).
    attach_to: PipelineStage | None = Field(
        None,
        description="Pipeline stage the fix attaches to (frontend attachTo); None = workflow-wide",
    )
    scope: Gate | None = Field(None, description="Gate phase the fix guards (frontend scope)")
    citations: list[RepairCitation] = Field(
        default_factory=list,
        description="Corpus ids + the rule/signature refs backing this proposal",
    )
    generated_by: str = Field(
        "stub", description="'stub' or 'claude' — provenance of the prose (frontend `mode`)"
    )
    model: str | None = Field(
        None, description="LLM id when generated_by='claude'; None for the deterministic stub"
    )
    corpus_version: str = PIPELINE_REPAIR_CORPUS_VERSION
    schema_version: int = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=utc_now)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mode(self) -> str:
        """Frontend ``AgentProposal.mode`` — an alias for :attr:`generated_by` ('stub'|'claude').

        Surfaced so the React ``AgentProposal`` shape maps 1:1 without a rename at the seam;
        it is derived, so it is excluded from :attr:`content_hash` (``generated_by`` is already
        hashed).
        """
        return self.generated_by

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        """Stable identity over the advisory payload (excludes id/created_at/derived mode)."""
        return _content_hash(
            {
                "advisory": self.advisory,
                "agent": self.agent,
                "addresses_rule_id": self.addresses_rule_id,
                "addresses_signature": self.addresses_signature,
                "signature_count": self.signature_count,
                "run_ids": self.run_ids,
                "summary": self.summary,
                "rationale": self.rationale,
                "attach_to": self.attach_to.value if self.attach_to else None,
                "scope": self.scope.value if self.scope else None,
                "citations": [c.model_dump(mode="json") for c in self.citations],
                "generated_by": self.generated_by,
                "model": self.model,
                "corpus_version": self.corpus_version,
            }
        )


def assemble_recurring_signatures(
    runs: Mapping[str, Sequence[DecisionCard]],
) -> list[RecurringSignature]:
    """Roll recurring finding signatures up from a set of runs' decision cards.

    Mirrors the monitoring endpoint's counter (``api.main.get_monitoring``): count
    :attr:`~pipeguard.models.Finding.signature` across every served run's cards, fix the
    display metadata on first sighting (the signature key is stable across rule versions, so
    any occurrence carries the same ``rule_id`` / ``title`` / ``gate``), and collect the runs
    each recurred in. Ranked by descending count, ties broken on ``signature`` for
    deterministic ordering. This is the shared assembler the on-demand endpoint and the
    offline tests both use, so the agent's input matches exactly what the dashboard shows.
    """
    counts: dict[str, int] = {}
    meta: dict[str, tuple[str, str, Gate]] = {}
    # dict-as-ordered-set: preserves first-seen run order and de-dupes a signature that
    # recurs twice within the same run (still one run in `run_ids`, but count reflects both).
    run_set: dict[str, dict[str, None]] = {}
    for run_id, cards in runs.items():
        for card in cards:
            for f in card.findings:
                counts[f.signature] = counts.get(f.signature, 0) + 1
                meta.setdefault(f.signature, (f.rule_id, f.title, f.gate))
                run_set.setdefault(f.signature, {}).setdefault(run_id, None)
    sigs = [
        RecurringSignature(
            signature=sig,
            rule_id=meta[sig][0],
            title=meta[sig][1],
            gate=meta[sig][2],
            count=n,
            run_ids=list(run_set[sig]),
        )
        for sig, n in counts.items()
    ]
    sigs.sort(key=lambda s: (-s.count, s.signature))
    return sigs


def recurring_signature(
    runs: Mapping[str, Sequence[DecisionCard]], signature: str
) -> RecurringSignature | None:
    """The one :class:`RecurringSignature` matching ``signature`` (``None`` if absent).

    The on-demand endpoint path: assemble the rollup over the served runs, then pick the row
    the operator drilled into. Kept next to the assembler so both stay grounded in the same
    counting logic.
    """
    return next((s for s in assemble_recurring_signatures(runs) if s.signature == signature), None)
