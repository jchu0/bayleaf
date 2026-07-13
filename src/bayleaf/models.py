"""Core data models for the provenance + QC decision gate.

These types are the contract between every layer of the system:

    parsers  ->  RunArtifacts
    rules    ->  Finding[]
    synthesis -> DecisionCard

They are deliberately framework-agnostic (no web-framework imports) so the same
package backs the FastAPI service and any other delivery layer.

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
    `MetricValue` contract. The metric registry (`bayleaf.metrics`) is the authority
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


class CheckCoverage(BaseModel):
    """Deterministic 'N ran / M not examined' coverage telemetry for one sample (WS-01).

    Computed in the trust anchor (``rules.compute_check_coverage``) as a pure function of
    ``(artifacts, runbook, findings)``. It exists to make PROCEED honest: a clean card must say
    "the checks that ran found nothing", NOT "all checks passed" — because contamination/identity
    have no parser today and are therefore NOT examined. Carried on the card as un-hashed contextual
    metadata (like ``metric_values``); it NARRATES coverage and never sets or influences the verdict
    (ADR-0001). ``ran`` means a category's rule/parser executed given the artifacts present — NOT
    that it produced a finding — so a clean gate that ran is never confused with one that never ran.
    """

    checks_expected: int = Field(..., description="Size of the fixed expected-category catalog")
    checks_ran: int = Field(..., description="How many expected categories actually ran")
    not_examined: list[str] = Field(
        default_factory=list, description="Labels of the categories that were NOT examined"
    )
    categories_ran: list[Category] = Field(default_factory=list)
    categories_not_run: list[Category] = Field(default_factory=list)


class DecisionCard(BaseModel):
    """The synthesized, operator-facing output for one sample.

    `verdict`, `findings`, and `gate_results` are grounded in the deterministic
    rule engine. `rationale`/`next_steps` are narration (stub today, Claude when
    enabled). `confidence` is intentionally omitted until it is grounded (T-019)
    — a meaningless heuristic bar would misrepresent certainty.

    `metric_values` surfaces the registry-normalized QC numbers the gate already
    computed (T-025) so they are API/frontend-visible and ML-ready (ADR-0007). Like
    `run_id`, they are contextual metadata: excluded from `content_hash` so the card's
    identity stays tied to the decision, not the evidence carried alongside it.
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
    metric_values: list[MetricValue] = Field(
        default_factory=list,
        description="Registry-normalized QC metrics for this sample (T-025); contextual "
        "ML/audit metadata (ADR-0007) — like run_id, NOT part of content_hash",
    )
    check_coverage: CheckCoverage | None = Field(
        None,
        description="Deterministic 'N ran / M not examined' coverage telemetry (WS-01); contextual "
        "metadata like metric_values — NOT hashed, and never sets a verdict (ADR-0001)",
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
        """Stable identity of the card (over its narration + finding hashes).

        Deliberately over an explicit key set: `run_id` and `metric_values` are
        contextual metadata (not the decision) and are omitted so the identity stays
        byte-identical whether or not they are attached.
        """
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
    """Per-sample QC metrics pulled from the QC report.

    The first five are the frozen-CSV contract every run carries. The rest are additional
    registered metrics a richer QC report may also emit (preflight / extra QC / variant tier) —
    each is ``None`` when absent (a missing metric is a signal, not a default), so a lean real run
    and a fuller contrived run both parse. When present they populate the decision card's preflight
    & variant gate groups; the metric registry already knows every one.
    """

    sample_id: str
    q30: float | None = None
    reads_passing_filter: float | None = None
    mean_coverage: float | None = None
    dup_rate: float | None = None
    cluster_pf: float | None = None
    # preflight tier
    phix_aligned: float | None = None
    # extra QC tier
    breadth_20x: float | None = None
    breadth_30x: float | None = None
    pct_mapped: float | None = None
    on_target: float | None = None
    # variant tier
    variant_dp: float | None = None
    variant_gq: float | None = None
    variant_titv: float | None = None


class RawObservation(BaseModel):
    """One raw metric observation as INGESTED, before registry normalization — the atom of the
    registry-keyed ingestion contract (WS-06). ``raw_value`` is on ``raw_unit`` (the scale it was
    emitted in — DECLARED, never guessed; the pct_* trap the registry defends). ``source_field`` /
    ``source_locator`` keep provenance to the artifact column it came from.
    ``metrics.metric_values_for`` normalizes a map of these into canonical ``MetricValue``s.
    """

    model_config = ConfigDict(frozen=True)

    raw_value: float
    raw_unit: str
    source_field: str | None = None
    source_locator: str | None = None


class SampleMetrics(BaseModel):
    """One sample's ingested metrics as a REGISTRY-KEYED map (WS-06 ingestion contract) — the
    inversion of the flat, field-enumerated ``QCMetrics``. ``raw`` maps a registry ``our_key`` to
    its ``RawObservation``, so an nf-core/MultiQC adapter (WS-03) can emit metrics WITHOUT a new
    named model field per metric. ``QCMetrics`` lowers into this via
    ``metrics.sample_metrics_from_qcmetrics`` during the transition (it stays the frozen-CSV parse
    output for one release; the ``RunArtifacts.qc`` type flip + registry-driven parser are PR2).
    """

    sample_id: str
    raw: dict[str, RawObservation] = Field(default_factory=dict)


class MetricValue(BaseModel):
    """One observed metric, normalized against the metric registry (schemas.md #6).

    A `MetricValue` is a *fact*: the raw number a tool emitted (`raw_value` in
    `raw_unit`) plus its value in the registry's `canonical_unit` (`normalized_value`).
    It is treated as immutable — hence `frozen` and a `content_hash` identity.

    Self-containment (ADR-0007): `canonical_unit` and `metric_registry_version` are
    *snapshotted onto the record*, not dereferenced from the registry at read time, so
    a ledger row is standalone-interpretable for ML/audit without loading the registry
    that produced it. The registry (`bayleaf.metrics`) is what *computes*
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


class TraceRecord(BaseModel):
    """One task row from a Nextflow/nf-core execution trace (`trace.txt`).

    A STRUCTURED pipeline-execution signal the gate READS — it never runs a process
    (composes ≠ executes, ADR-0001/0003). `tag` is the nf-core sample tag; `status` is the
    task disposition (COMPLETED / FAILED / CACHED / ABORTED); `exit` is the process exit code
    (0 = success). A failed task is the structured sibling of PIPE-001's free-text log marker
    — the EXEC-001 rule maps it to RERUN. Every field is optional so a partial/garbled trace
    is a signal, not a crash (CLAUDE.md data-handling 2).
    """

    task_id: str | None = None
    process: str | None = None
    tag: str | None = None
    status: str | None = None
    exit: int | None = None


class VariantCall(BaseModel):
    """One annotated candidate variant bayleaf READS from an externally-produced annotated
    VCF/table (ADR-0018) — a driver ran the annotator (VEP/bcftools); bayleaf never does
    (composes ≠ executes, ADR-0001/0003). Clinical significance is a VERBATIM quotation of
    ClinVar, never bayleaf's own determination (ADR-0004 — never invent pathogenicity):
    `clinvar_significance` is the raw CLNSIG string, `clinvar_review_status` the review status
    (star rating), `clinvar_accession` + `clinvar_version` the citation. Every field is optional
    so a partial/garbled annotation is a signal, not a crash (CLAUDE.md data-handling 2). This
    record feeds only the OFF-BY-DEFAULT flag-for-review rule (VAR-FFR-001); it sets no verdict.
    """

    sample_id: str
    gene: str | None = None
    hgvs: str | None = None  # e.g. NM_000059.4:c.68_69del
    clinvar_significance: str | None = None  # CLNSIG, verbatim (e.g. "Pathogenic")
    clinvar_review_status: str | None = None  # CLNREVSTAT, verbatim
    clinvar_accession: str | None = None  # e.g. VCV000009999
    clinvar_version: str | None = None  # ClinVar release for the citation


class RunArtifacts(BaseModel):
    """Everything the gate ingests for a single run, keyed by sample_id where possible."""

    run_id: str
    samples: list[Sample] = Field(default_factory=list)
    sample_sheet: list[SampleSheetEntry] = Field(default_factory=list)
    demux: list[DemuxRecord] = Field(default_factory=list)
    # WS-06 transition: holds the frozen-CSV `QCMetrics` (the current parser output) OR the
    # registry-keyed `SampleMetrics` a real-run adapter emits (WS-03). Both normalize through
    # `metrics.metric_values_for`, and every reader of `.qc` uses only `.sample_id` + that loop, so
    # the gate is agnostic to which shape a run carries — an ingested `results/` dir gates exactly
    # like the frozen CSV. The hard flip to SampleMetrics-only (dropping QCMetrics + the frozen-CSV
    # parser rewrite) is a later cleanup, once nothing constructs QCMetrics.
    qc: list[QCMetrics | SampleMetrics] = Field(default_factory=list)
    log_lines: list[str] = Field(default_factory=list)
    # Structured Nextflow/nf-core execution trace (`trace.txt`) — READ, never run (EXEC-001).
    execution_trace: list[TraceRecord] = Field(default_factory=list)
    # Annotated candidate variants READ from an externally-produced annotated VCF/table
    # (ADR-0018). Empty for every run today; feeds only the off-by-default flag-for-review rule.
    variant_calls: list[VariantCall] = Field(default_factory=list)
    # Run-level context parsed from the sample sheet's [Header] block (Illumina v2).
    # All optional: a sheet may omit any of them, and `run_date` stays the raw ISO
    # string — we never fabricate a datetime when the field is absent.
    platform: str | None = None
    run_date: str | None = None
    run_name: str | None = None
    # Per-run POLICY: metric-registry source modules the operator DECLARED ABSENT for this run (e.g.
    # ``{"sav_interop"}`` for a FASTQ-start run with no upstream Illumina/SAV data). The gate WAIVES
    # those thresholds — an absent value emits an INFO "not examined — declared absent" note instead
    # of the NA HOLD (runbook.Runbook.waive_source_classes → rules._evaluate_metric). Empty = the
    # default (every metric expected; a missing required one HOLDs). A declared policy INPUT, not an
    # operator override of a verdict — rules still decide (ADR-0001). Un-hashed context.
    waived_metric_sources: frozenset[str] = Field(default_factory=frozenset)

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
        for v in self.variant_calls:
            seen.setdefault(v.sample_id, None)
        return list(seen)


# `DecisionCard.metric_values` forward-references `MetricValue`, which is defined *below*
# `DecisionCard`. With `from __future__ import annotations` the annotation is a string, so
# pydantic cannot resolve it at class-definition time; rebuild once here — now that
# `MetricValue` is in the module namespace — to finalize the schema explicitly rather than
# relying on lazy auto-rebuild.
DecisionCard.model_rebuild()
