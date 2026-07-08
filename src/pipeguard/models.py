"""Core data models for the provenance + QC decision gate.

These types are the contract between every layer of the system:

    parsers  ->  RunArtifacts
    rules    ->  Finding[]
    synthesis -> DecisionCard

They are deliberately framework-agnostic (no Streamlit / FastAPI imports) so the
same package backs the Streamlit MVP today and a FastAPI service later.

The decision records carry the `schemas.md` trust layer: every `Finding` derives
the **gate** it belongs to, a rule-version-independent **signature**, and a
**content_hash**; every `DecisionCard` derives a per-gate breakdown and its own
content hash. Verdict aggregation still lives in `synthesis.base` — never here.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field

from .identifiers import SCHEMA_VERSION, utc_now
from .identifiers import content_hash as _content_hash


class Verdict(str, Enum):
    """The four operator-facing outcomes of the decision gate."""

    PROCEED = "proceed"
    HOLD = "hold"
    RERUN = "rerun"
    ESCALATE = "escalate"


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


class Gate(str, Enum):
    """The three checkpoints a finding/verdict can belong to (ADR-0013)."""

    PREFLIGHT = "preflight"
    QC = "qc"
    VARIANT = "variant"


class Category(str, Enum):
    PROVENANCE = "provenance"
    QC = "qc"
    COVERAGE = "coverage"
    CONTAMINATION = "contamination"
    IDENTITY = "identity"
    VARIANT = "variant"
    PIPELINE = "pipeline"
    METADATA = "metadata"


class SourceKind(str, Enum):
    """Provenance class of a piece of evidence (schemas.md Evidence.source_kind)."""

    ARTIFACT = "artifact"
    METRIC = "metric"
    MULTIQC_SOURCE = "multiqc_source"
    EXECUTION_TRACE = "execution_trace"
    PARAMS = "params"
    HUMAN_NOTE = "human_note"


# Which gate owns each category (ADR-0013 three-gate model). Identity/provenance
# checks ride the QC gate; intake metadata and pipeline/operational failures are
# preflight; variant-level is the variant gate.
_CATEGORY_GATE: dict[Category, Gate] = {
    Category.PROVENANCE: Gate.QC,
    Category.QC: Gate.QC,
    Category.COVERAGE: Gate.QC,
    Category.CONTAMINATION: Gate.QC,
    Category.IDENTITY: Gate.QC,
    Category.METADATA: Gate.PREFLIGHT,
    Category.PIPELINE: Gate.PREFLIGHT,
    Category.VARIANT: Gate.VARIANT,
}

_VERDICT_RANK: dict[Verdict, int] = {
    Verdict.PROCEED: 0,
    Verdict.HOLD: 1,
    Verdict.RERUN: 2,
    Verdict.ESCALATE: 3,
}
_SEVERITY_RANK: dict[Severity, int] = {Severity.INFO: 0, Severity.WARN: 1, Severity.CRITICAL: 2}

# Version of the rule pack that emits findings; bumped when rule logic changes.
# Kept out of the issue signature so a signature stays stable across rule versions.
RULE_PACK_VERSION = "1.0.0"


class Evidence(BaseModel):
    """A single, traceable piece of supporting evidence for a finding.

    Every finding must cite where it came from so an operator can verify the
    recommendation without reconstructing context from scattered files. Field
    names map to `schemas.md`: `source` = source_file, `value` = observed_value,
    `expected` = expected_value.
    """

    source: str = Field(..., description="Artifact/file the evidence came from (source_file)")
    locator: str | None = Field(None, description="Row/field/line pointer within the source")
    value: str | None = Field(None, description="Observed value or excerpt (observed_value)")
    expected: str | None = Field(None, description="Expected value or threshold (expected_value)")
    source_kind: SourceKind = Field(
        SourceKind.ARTIFACT, description="Provenance class of this evidence"
    )
    source_field: str | None = Field(None, description="Specific field/column within the source")
    threshold: str | None = Field(None, description="Gate threshold, when distinct from `expected`")


class Finding(BaseModel):
    """A single deterministic observation produced by the rule engine.

    Findings are *facts* (with citations). They carry a suggested verdict, but the
    final verdict on the card is decided by aggregating all findings. They are
    treated as immutable: `content_hash` is their identity, and `signature` is a
    semantic, rule-version-independent key for recurrence tracking.
    """

    rule_id: str
    category: Category
    severity: Severity
    title: str
    detail: str
    evidence: list[Evidence] = Field(default_factory=list)
    suggested_verdict: Verdict
    rule_version: str = RULE_PACK_VERSION
    schema_version: int = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=utc_now)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gate(self) -> Gate:
        """Which of the three gates owns this finding (derived from category)."""
        return _CATEGORY_GATE.get(self.category, Gate.QC)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def signature(self) -> str:
        """Semantic, rule-version-independent recurrence key (schemas.md redline 5)."""
        loci = sorted(f"{e.source}:{e.locator}" for e in self.evidence)
        payload = {"category": self.category.value, "rule_id": self.rule_id, "loci": loci}
        return _content_hash(payload)[:16]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        """Stable identity of this immutable finding (excludes created_at)."""
        return _content_hash(
            {
                "rule_id": self.rule_id,
                "category": self.category.value,
                "severity": self.severity.value,
                "title": self.title,
                "detail": self.detail,
                "evidence": [e.model_dump(mode="json") for e in self.evidence],
                "suggested_verdict": self.suggested_verdict.value,
                "rule_version": self.rule_version,
            }
        )


class GateResult(BaseModel):
    """Per-gate rollup shown on a card: which gate, its verdict, and why."""

    gate: Gate
    verdict: Verdict
    severity: Severity
    rationale: str
    finding_rule_ids: list[str] = Field(default_factory=list)


class DecisionCard(BaseModel):
    """The synthesized, operator-facing output for one sample.

    `verdict`, `findings`, and `gate_results` are grounded in the deterministic
    rule engine. `rationale`/`next_steps` are narration (stub today, Claude when
    enabled). `confidence` is intentionally omitted until it is grounded (T-019)
    — a meaningless heuristic bar would misrepresent certainty.
    """

    sample_id: str
    verdict: Verdict
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Heuristic; omitted until grounded (T-019)"
    )
    headline: str
    rationale: str
    next_steps: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    generated_by: str = Field(
        "stub", description="'stub' or 'claude' — provenance of the narration"
    )
    analysis_run_id: str | None = Field(
        None, description="Anchors the card to the gate execution that produced it"
    )
    schema_version: int = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def is_actionable(self) -> bool:
        """True when the card needs a human touch (anything but a clean pass)."""
        return self.verdict is not Verdict.PROCEED

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gate_results(self) -> list[GateResult]:
        """Per-gate breakdown derived from the findings on this card."""
        buckets: dict[Gate, list[Finding]] = defaultdict(list)
        for f in self.findings:
            buckets[f.gate].append(f)
        results: list[GateResult] = []
        for gate in (Gate.PREFLIGHT, Gate.QC, Gate.VARIANT):
            fs = buckets.get(gate)
            if not fs:
                continue
            verdict = max((f.suggested_verdict for f in fs), key=lambda v: _VERDICT_RANK[v])
            worst = max(fs, key=lambda f: _SEVERITY_RANK[f.severity])
            results.append(
                GateResult(
                    gate=gate,
                    verdict=verdict,
                    severity=worst.severity,
                    rationale=f"{len(fs)} {gate.value} finding(s); most severe: {worst.title}",
                    finding_rule_ids=[f.rule_id for f in fs],
                )
            )
        return results

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        """Stable identity of the card (over its narration + finding hashes)."""
        return _content_hash(
            {
                "sample_id": self.sample_id,
                "verdict": self.verdict.value,
                "headline": self.headline,
                "rationale": self.rationale,
                "next_steps": self.next_steps,
                "finding_hashes": [f.content_hash for f in self.findings],
                "generated_by": self.generated_by,
            }
        )


class Sample(BaseModel):
    """Sample-level metadata joined from the intake sheet."""

    sample_id: str
    subject_id: str | None = None
    tissue: str | None = None
    library_prep: str | None = None
    submitted_by: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class QCMetrics(BaseModel):
    """Per-sample QC metrics pulled from the QC report."""

    sample_id: str
    q30: float | None = None
    pct_reads_identified: float | None = None
    mean_coverage: float | None = None
    dup_rate: float | None = None
    cluster_pf: float | None = None


class SampleSheetEntry(BaseModel):
    """One row of the demux sample sheet (the declared truth for barcodes)."""

    sample_id: str
    index: str | None = None
    index2: str | None = None


class DemuxRecord(BaseModel):
    """One row of demultiplexing stats (what the sequencer actually observed)."""

    sample_id: str
    index: str | None = None
    reads: int | None = None
    pct_reads: float | None = None


class RunArtifacts(BaseModel):
    """Everything the gate ingests for a single run, keyed by sample_id where possible."""

    run_id: str
    samples: list[Sample] = Field(default_factory=list)
    sample_sheet: list[SampleSheetEntry] = Field(default_factory=list)
    demux: list[DemuxRecord] = Field(default_factory=list)
    qc: list[QCMetrics] = Field(default_factory=list)
    log_lines: list[str] = Field(default_factory=list)

    def sample_ids(self) -> list[str]:
        """Union of sample IDs seen across all artifacts, order-stable."""
        seen: dict[str, None] = {}
        for s in self.samples:
            seen.setdefault(s.sample_id, None)
        for e in self.sample_sheet:
            seen.setdefault(e.sample_id, None)
        for q in self.qc:
            seen.setdefault(q.sample_id, None)
        for d in self.demux:
            seen.setdefault(d.sample_id, None)
        return list(seen)
