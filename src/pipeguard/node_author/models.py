"""Records for the advisory node-authoring agent (T-046; ADR-0009 / ADR-0003).

Four record shapes live here, mirroring the pipeline-repair agent's model layer:

  * :data:`ARTIFACT_KINDS` — the closed, real port-kind vocabulary a proposed node may speak.
    It is a hand-mirrored copy of the frontend builder's ``ARTIFACT_KINDS`` (the union of every
    ``BTOOLSPEC`` in/out kind and every emitted ``GIAB_LOC`` locator kind, see
    ``frontend/src/components/BuilderShared.tsx``). Kept in the framework-agnostic core as a
    literal set — never imported from the frontend — so the core stays deployment-agnostic
    (CLAUDE.md architecture guardrail 1). A port whose kind is NOT in this set is **reserved**:
    an inert, labelled slot the wiring never connects (never a fabricated live edge).
  * :class:`PortSpec` — one typed input/output port. Its :attr:`known` flag is COMPUTED from
    :data:`ARTIFACT_KINDS`, so the "never invent a port kind" guardrail is structural: a port is
    reserved iff its kind is unknown to the real vocabulary.
  * :class:`LocatorSuggestion` — a SUGGESTED ``run_layout.yaml`` locator for an output port
    (mirrors the frontend ``GiabLoc`` shape). Advisory: it proposes where an artifact would land,
    it never emits a real locator or runs anything.
  * :class:`ToolCardEntry` — one curated tool-card record in the knowledge corpus (ADR-0009).
    Retrieval-only; it encodes NO verdict and NO threshold value.
  * :class:`NodeProposal` — the agent's ADVISORY output for one request. ``advisory`` is pinned
    ``True`` and there is deliberately no verdict or confidence field: the agent PROPOSES a node
    for human review; it never edits a pipeline, runs a tool, or sets a verdict (ADR-0001/0003).

All reuse the shared identity/hash/time helpers so they acquire type-prefixed ids, content
hashes, and UTC timestamps the same way every other record does.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from ..identifiers import SCHEMA_VERSION, new_id, utc_now
from ..identifiers import content_hash as _content_hash

# Version of the curated tool-card corpus + proposal templating; bump when either the corpus
# schema or the stub's phrasing changes so cached/persisted proposals stay traceable (mirrors
# PIPELINE_REPAIR_CORPUS_VERSION).
NODE_AUTHOR_CORPUS_VERSION = "1.0.0"

# The closed, REAL port-kind vocabulary a proposed node may wire (the union of every BTOOLSPEC
# in/out kind and every emitted GIAB_LOC locator kind in the frontend builder). Mirrored here as
# a literal so the framework-agnostic core never imports the frontend; a periodic sweep keeps the
# two in sync (see the module docstring). Any kind outside this set is proposed as a RESERVED port.
ARTIFACT_KINDS: frozenset[str] = frozenset(
    {
        "bai",
        "bam",
        "fastp_json",
        "fastq",
        "filtered_vcf",
        "markdup_metrics",
        "mosdepth_summary",
        "mosdepth_thresholds",
        "multiqc_json",
        "ngscheckmate",
        "panel_bed",
        "reference_fasta",
        "truth_vcf",
        "vcf",
    }
)

# The builder's pipeline-stage vocabulary (frontend node `stage`), mirrored as a literal set so a
# proposed node's stage stays in the controlled set. Same closed-vocabulary discipline as
# pipeline_repair.PipelineStage; kept as strings here to keep the two sibling agents independent.
PIPELINE_STAGES: frozenset[str] = frozenset(
    {
        "intake",
        "demux",
        "read_qc",
        "align",
        "markdup",
        "coverage",
        "variant_call",
        "filter",
        "qc_aggregate",
    }
)

# Where a port sits on the Databricks-style card (frontend port-placement convention): the primary
# sample-data lane (left->right), a reference/panel input (top), or a QC/metrics exit (bottom).
PortRole = Literal["data", "reference", "qc"]


class PortSpec(BaseModel):
    """One typed input or output port on a proposed node.

    :attr:`kind` is the port's artifact kind; :attr:`known` is COMPUTED from
    :data:`ARTIFACT_KINDS`, so a port is a live typed slot iff its kind is in the real builder
    vocabulary. A port with an unknown kind is **reserved** — an honest, labelled slot the wiring
    never connects — so the agent can surface a real-but-unregistered tool I/O (e.g. ``fastp_html``)
    without ever inventing a live wire (CLAUDE.md guardrail 4; builder-cards README §1).
    """

    model_config = ConfigDict(frozen=True)

    kind: str = Field(..., description="Artifact kind; must be in ARTIFACT_KINDS to be a live port")
    required: bool = Field(True, description="Required vs optional/user-defined port")
    role: PortRole = Field("data", description="Card edge: data (L->R) | reference | qc")
    note: str | None = Field(None, description="What this port maps to (a real flag/glob/output)")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def known(self) -> bool:
        """True iff :attr:`kind` is a real vocabulary kind; a False port is RESERVED (unwired)."""
        return self.kind in ARTIFACT_KINDS


class LocatorSuggestion(BaseModel):
    """A SUGGESTED ``run_layout.yaml`` locator for one output port (mirrors the ``GiabLoc`` shape).

    Advisory only: it proposes where an artifact would be found (a path or glob) and how it would be
    parsed, so a human can wire the real locator. It never emits a locator or runs the tool
    (compose ≠ execute, ADR-0003). ``origin`` is deliberately absent — it is locked ``unknown`` at
    emit and stamped only at ingest, never proposed here.
    """

    model_config = ConfigDict(frozen=True)

    kind: str = Field(..., description="Artifact kind this locator resolves")
    field: Literal["path", "glob"] = Field("path", description="Resolve by exact path or by glob")
    loc: str = Field(..., description="The suggested path/glob under the run directory")
    parser: str = Field("null", description="Parser key (e.g. 'fastp_json'); 'null' if unparsed")
    required: bool = Field(True, description="Whether ingest should require this artifact")
    role: Literal["output", "reference"] = Field("output", description="Pipeline output vs ref")
    on_multiple: Literal["first", "all", "error"] = Field(
        "error", description="Policy when the glob matches multiple files"
    )


class NodeCitation(BaseModel):
    """One traceable reference behind a proposal — the corpus entry, a card doc, or the tool.

    Keeps evidence and generated advice separable (CLAUDE.md life-science guardrail 4): every
    proposal traces to a curated tool-card id, the design/card doc it grounds in, and the tool it
    proposes. :attr:`score` is a **heuristic** keyword-overlap value in [0, 1] for knowledge hits —
    not a calibrated probability — and is ``None`` for the card_doc/tool references.
    """

    model_config = ConfigDict(frozen=True)

    source_kind: Literal["knowledge", "card_doc", "tool"]
    ref: str = Field(..., description="Corpus id (tool_…/source_…), a doc/card path, or tool name")
    title: str | None = None
    score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Heuristic keyword-overlap score for knowledge hits (NOT a probability)",
    )


class ToolCardEntry(BaseModel):
    """One curated tool-card record (ADR-0009 knowledge corpus) the node-author retrieves over.

    Maps a tool (by ``tool`` name / ``keywords``) to its real, typed builder node: a pinned
    :attr:`version`, its :attr:`inputs` / :attr:`outputs` ports (each a :class:`PortSpec`, real
    kinds live and unregistered kinds reserved), and its suggested :attr:`locators` — grounded in
    the per-tool cards under ``docs/design/builder-cards/`` and the frontend ``BTOOLSPEC``.
    Retrieval-only: it encodes NO verdict and NO threshold value.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Stable curated id, e.g. 'tool_fastp'")
    kind: str = Field("tool_card", description="KnowledgeRecord kind (schemas.md)")
    tool: str = Field(..., description="Canonical tool/source name (matches the builder palette)")
    version: str = Field(..., description="Pinned tool version, e.g. '0.23.4'")
    stage: str | None = Field(None, description="Pipeline stage role (PIPELINE_STAGES vocabulary)")
    category: str | None = Field(None, description="Finding category this tool relates to")
    title: str
    keywords: list[str] = Field(
        default_factory=list, description="Tokens (tool name + synonyms) used for keyword retrieval"
    )
    inputs: list[PortSpec] = Field(default_factory=list)
    outputs: list[PortSpec] = Field(default_factory=list)
    locators: list[LocatorSuggestion] = Field(default_factory=list)
    summary: str = Field(..., description="Proposed human-reviewed node (advisory; not auto-added)")
    rationale: str = Field(..., description="Why these ports/version; conservative + hedged")
    source: str = Field(..., description="Provenance/citation for the card (doc + BTOOLSPEC ref)")
    tags: list[str] = Field(default_factory=list)


class NodeProposal(BaseModel):
    """An ADVISORY builder-node proposal for one request (mirrors the frontend ``AgentProposal``).

    ``advisory`` is pinned ``True`` and this record has no verdict or confidence field at all: the
    agent PROPOSES a node for **human review**, it never edits a pipeline, runs a tool, or
    sets/overrides a verdict (ADR-0001/0003). The tool, version, ports, and locators are
    DETERMINISTIC — they come from the curated corpus, never the LLM; only :attr:`summary` /
    :attr:`rationale` prose may be refined by the live agent. :attr:`reserved_kinds` lists every
    port kind outside :data:`ARTIFACT_KINDS` (surfaced, never wired). :attr:`matched` is False for a
    conservative "no tool-card matched — defer to a human" proposal that fabricates no ports.
    """

    id: str = Field(default_factory=lambda: new_id("node"))
    advisory: Literal[True] = True
    agent: str = Field(..., description="Advisory agent name, e.g. 'node_author'")
    request: str = Field(..., description="The natural-language request this responds to (echoed)")
    matched: bool = Field(
        False, description="Whether a curated tool-card matched (else a defer-to-human proposal)"
    )
    tool: str | None = Field(None, description="Proposed tool/source name; None when unmatched")
    version: str | None = Field(None, description="Pinned tool version; None when unmatched")
    stage: str | None = Field(None, description="Pipeline stage role (PIPELINE_STAGES vocabulary)")
    inputs: list[PortSpec] = Field(default_factory=list, description="Proposed typed input ports")
    outputs: list[PortSpec] = Field(default_factory=list, description="Proposed typed output ports")
    locators: list[LocatorSuggestion] = Field(
        default_factory=list, description="Suggested run_layout locators for the output ports"
    )
    reserved_kinds: list[str] = Field(
        default_factory=list,
        description="Port kinds outside ARTIFACT_KINDS — surfaced as reserved, never wired",
    )
    summary: str = Field(..., description="The proposed, human-reviewed node (prose)")
    rationale: str = Field(..., description="Why this node/ports; conservative + hedged (prose)")
    citations: list[NodeCitation] = Field(
        default_factory=list, description="Corpus id + card-doc + tool refs backing this proposal"
    )
    generated_by: str = Field(
        "stub", description="'stub' or 'claude' — provenance of the prose (frontend `mode`)"
    )
    model: str | None = Field(
        None, description="LLM id when generated_by='claude'; None for the deterministic stub"
    )
    disclaimer: str = (
        "Advisory node proposal for human review — not a QC verdict, not calibrated, not clinical. "
        "It composes a node; it never runs a tool, edits a pipeline, or re-decides a run."
    )
    corpus_version: str = NODE_AUTHOR_CORPUS_VERSION
    schema_version: int = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=utc_now)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mode(self) -> str:
        """Frontend ``AgentProposal.mode`` — an alias for :attr:`generated_by` ('stub'|'claude').

        Surfaced so the React ``AgentProposal`` shape maps 1:1 without a rename at the seam; it is
        derived, so it is excluded from :attr:`content_hash` (``generated_by`` is already hashed).
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
                "request": self.request,
                "matched": self.matched,
                "tool": self.tool,
                "version": self.version,
                "stage": self.stage,
                "inputs": [p.model_dump(mode="json") for p in self.inputs],
                "outputs": [p.model_dump(mode="json") for p in self.outputs],
                "locators": [loc.model_dump(mode="json") for loc in self.locators],
                "reserved_kinds": self.reserved_kinds,
                "summary": self.summary,
                "rationale": self.rationale,
                "citations": [c.model_dump(mode="json") for c in self.citations],
                "generated_by": self.generated_by,
                "model": self.model,
                "corpus_version": self.corpus_version,
            }
        )
