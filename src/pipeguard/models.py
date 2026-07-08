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

from pydantic import BaseModel, ConfigDict, Field, computed_field

from .identifiers import SCHEMA_VERSION, new_id, utc_now
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


class CanonicalUnit(str, Enum):
    """The unit a metric is normalized *to* (metric_registry.md `canonical_unit`).

    Defined here, next to the other core-vocabulary enums, because it is part of the
    `MetricValue` contract. The metric registry (`pipeguard.metrics`) is the authority
    on which unit each `our_key` normalizes to; this enum is just the closed set.
    """

    FRACTION = "fraction"  # 0-1
    PERCENT = "percent"  # 0-100
    X = "x"  # fold coverage (e.g. 150x)
    RATIO = "ratio"  # dimensionless ratio (fold-enrichment, Ts/Tv)
    PHRED = "phred"  # phred-scaled quality
    COUNT = "count"  # integer count
    BOOL = "bool"  # 0/1 truth value


# Which gate owns each category (ADR-0013 three-gate model). Provenance (barcode /
# index integrity), intake metadata, and pipeline/operational failures are caught at
# preflight; QC metrics and sample identity/swap (NGSCheckMate) are the QC gate;
# variant-level is the variant gate. Mirrors the qc_metrics.md gate table.
_CATEGORY_GATE: dict[Category, Gate] = {
    Category.PROVENANCE: Gate.PREFLIGHT,
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

    model_config = ConfigDict(frozen=True)

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

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: new_id("find"))
    rule_id: str
    sample_id: str | None = None
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
        payload = {
            "category": self.category.value,
            "rule_id": self.rule_id,
            "sample_id": self.sample_id,
            "loci": loci,
        }
        return _content_hash(payload)[:16]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        """Stable identity of this immutable finding (excludes created_at)."""
        return _content_hash(
            {
                "rule_id": self.rule_id,
                "sample_id": self.sample_id,
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
    run_id: str | None = Field(
        None,
        description="Human run id the card belongs to (e.g. mock_run_01); contextual, "
        "not part of content_hash",
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


class MetricValue(BaseModel):
    """One observed metric, normalized against the metric registry (schemas.md #6).

    A `MetricValue` is a *fact*: the raw number a tool emitted (`raw_value` in
    `raw_unit`) plus its value in the registry's `canonical_unit` (`normalized_value`).
    It is treated as immutable — hence `frozen` and a `content_hash` identity.

    Self-containment (ADR-0007): `canonical_unit` and `metric_registry_version` are
    *snapshotted onto the record*, not dereferenced from the registry at read time, so
    a ledger row is standalone-interpretable for ML/audit without loading the registry
    that produced it. The registry (`pipeguard.metrics`) is what *computes*
    `normalized_value` at observe-time — this model only stores the result, which is why
    it round-trips cleanly through `model_dump(mode="json")` with no registry present.

    On the critical path (T-025): the QC rules build these via `MetricRegistry.observe(...)`
    (which validates `metric_key` against the controlled vocabulary and fills the
    normalized/snapshot fields) and gate on `normalized_value`.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: new_id("metric"))
    sample_id: str
    metric_key: str = Field(..., description="Registry `our_key` (controlled vocabulary)")
    gate: Gate
    raw_value: float = Field(..., description="Value as the tool emitted it, in `raw_unit`")
    raw_unit: str = Field(..., description="Unit of `raw_value` (e.g. percent, fraction, x)")
    normalized_value: float = Field(..., description="`raw_value` converted to `canonical_unit`")
    # Snapshotted from the registry for standalone readability (ADR-0007):
    canonical_unit: CanonicalUnit
    metric_registry_version: int
    analysis_run_id: str | None = None
    source_artifact_id: str | None = Field(None, description="Artifact the value was parsed from")
    source_field: str | None = Field(None, description="Exact field/column within the source")
    source_locator: str | None = Field(None, description="Row/line/path pointer within the source")
    parser_version: str | None = None
    schema_version: int = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=utc_now)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        """Stable identity over the observation (excludes `id`/`created_at`)."""
        return _content_hash(
            {
                "sample_id": self.sample_id,
                "metric_key": self.metric_key,
                "gate": self.gate.value,
                "raw_value": self.raw_value,
                "raw_unit": self.raw_unit,
                "normalized_value": self.normalized_value,
                "canonical_unit": self.canonical_unit.value,
                "metric_registry_version": self.metric_registry_version,
                "analysis_run_id": self.analysis_run_id,
                "source_artifact_id": self.source_artifact_id,
                "source_field": self.source_field,
                "source_locator": self.source_locator,
                "parser_version": self.parser_version,
            }
        )


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
