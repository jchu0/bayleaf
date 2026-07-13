"""Records for the advisory QC-triage agent (schemas.md #13/#15, ADR-0009).

Two record shapes live here:

  * :class:`KnowledgeEntry` — one curated knowledge-corpus record (a
    `failure_signature`) mapping a QC/provenance failure to a conservative likely
    cause + suggested action, each with a source citation. Retrieval-only; it never
    encodes a verdict.
  * :class:`TriageNote` — the agent's **advisory** output for one flagged decision
    card. `advisory` is pinned ``True`` and there is deliberately no verdict or
    confidence field: the agent narrates and advises, the rules decide (ADR-0001).

Both reuse the shared identity/hash/time helpers so they acquire type-prefixed ids,
content hashes, and UTC timestamps the same way every other record does.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from ..identifiers import SCHEMA_VERSION, new_id, utc_now
from ..identifiers import content_hash as _content_hash

# Version of the curated knowledge corpus + note templating; bump when either the
# corpus schema or the stub's phrasing changes so cached/persisted notes stay traceable.
TRIAGE_CORPUS_VERSION = "1.0.0"


class KnowledgeEntry(BaseModel):
    """One curated knowledge-corpus record (schemas.md KnowledgeRecord #15, ADR-0009).

    A `failure_signature`-kind record: it maps a QC/provenance failure to a
    conservative *likely cause* and *suggested action*, with a `source` citation so
    the advice stays traceable. `keywords` are the signature tokens the keyword
    retriever matches against; an embedding backend would index the same text later.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Stable curated id, e.g. 'know_barcode_index_mismatch'")
    kind: str = Field("failure_signature", description="KnowledgeRecord kind (schemas.md #15)")
    category: str | None = Field(
        None, description="Finding category this addresses (provenance|qc|coverage|…)"
    )
    title: str
    keywords: list[str] = Field(
        default_factory=list, description="Signature tokens used for keyword retrieval"
    )
    likely_cause: str = Field(..., description="Conservative, hedged candidate cause")
    suggested_action: str = Field(..., description="Advisory next step; never a verdict")
    source: str = Field(..., description="Provenance/citation for the advice")
    tags: list[str] = Field(default_factory=list)
    version: str = TRIAGE_CORPUS_VERSION


class TriageCitation(BaseModel):
    """One traceable reference behind a triage note — a corpus entry or a finding.

    Keeping evidence and generated advice separable (CLAUDE.md life-science guardrail)
    lets a reader trace every suggestion back to a curated knowledge id or the rule
    finding it addresses. `score` is a **heuristic** keyword-overlap value in [0, 1]
    for knowledge hits — not a calibrated probability — and is ``None`` for findings.
    """

    model_config = ConfigDict(frozen=True)

    source_kind: Literal["knowledge", "finding"]
    ref: str = Field(..., description="Knowledge corpus id (know_…) or the finding's rule_id")
    title: str | None = None
    score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Heuristic keyword-overlap score for knowledge hits (NOT a probability)",
    )


class TriageNote(BaseModel):
    """An ADVISORY triage note for one flagged decision card (schemas.md #13).

    The QC-triage agent reads the deterministic rule findings, retrieves matching
    knowledge, and suggests a likely cause + next action. It **never** sets or
    overrides a verdict (ADR-0001): `advisory` is pinned ``True`` and this record has
    no verdict or confidence field at all. Uncertainty is carried in conservative
    phrasing and in the per-citation heuristic score.
    """

    id: str = Field(default_factory=lambda: new_id("note"))
    advisory: Literal[True] = True
    agent: str = Field(..., description="Advisory agent name, e.g. 'qc_triage'")
    sample_id: str | None = None
    addresses_rule_ids: list[str] = Field(
        default_factory=list, description="rule_ids of the findings this note addresses"
    )
    addresses_signatures: list[str] = Field(
        default_factory=list, description="Semantic finding signatures this note addresses"
    )
    likely_cause: str
    suggested_action: str
    citations: list[TriageCitation] = Field(
        default_factory=list, description="Corpus ids + finding refs backing this note"
    )
    generated_by: str = Field("stub", description="'stub' or 'claude' — provenance of the advice")
    model: str | None = Field(
        None, description="LLM id when generated_by='claude'; None for the deterministic stub"
    )
    corpus_version: str = TRIAGE_CORPUS_VERSION
    schema_version: int = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=utc_now)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        """Stable identity over the advisory payload (excludes id/created_at)."""
        return _content_hash(
            {
                "advisory": self.advisory,
                "agent": self.agent,
                "sample_id": self.sample_id,
                "addresses_rule_ids": self.addresses_rule_ids,
                "addresses_signatures": self.addresses_signatures,
                "likely_cause": self.likely_cause,
                "suggested_action": self.suggested_action,
                "citations": [c.model_dump(mode="json") for c in self.citations],
                "generated_by": self.generated_by,
                "model": self.model,
                "corpus_version": self.corpus_version,
            }
        )


class AgentReply(BaseModel):
    """An ADVISORY answer to a user's free-text QUESTION about a decision card (ADR-0001).

    The interactive sibling of :class:`TriageNote`: instead of auto-triaging a flagged card, the
    agent answers a question the operator asked about it. ``advisory`` is pinned ``True`` and there
    is deliberately no verdict/confidence field — the agent answers, the rules decide. Citations
    stay deterministic (retriever + the card's findings), so provenance survives even on the live
    path; the model only writes the ``answer`` prose. With AI OFF, the stub NEVER fabricates an
    answer — it returns a grounded, retrieval-based response explicitly framed as retrieved
    knowledge, not generated text (ADR-0006 deterministic fallback).
    """

    id: str = Field(default_factory=lambda: new_id("ask"))
    advisory: Literal[True] = True
    agent: str = Field(..., description="Advisory agent name, e.g. 'qc_triage'")
    sample_id: str | None = None
    question: str = Field(..., description="The operator's verbatim question")
    answer: str = Field(..., description="Advisory answer (stub: retrieval; claude: prose)")
    citations: list[TriageCitation] = Field(
        default_factory=list, description="Corpus ids + finding refs grounding the answer"
    )
    generated_by: str = Field("stub", description="'stub' or 'claude' — provenance of the answer")
    model: str | None = Field(
        None, description="LLM id when generated_by='claude'; None for the deterministic stub"
    )
    corpus_version: str = TRIAGE_CORPUS_VERSION
    schema_version: int = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=utc_now)
