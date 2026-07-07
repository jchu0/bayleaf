"""Core data models for the provenance + QC decision gate.

These types are the contract between every layer of the system:

    parsers  ->  RunArtifacts
    rules    ->  Finding[]
    synthesis -> DecisionCard

They are deliberately framework-agnostic (no Streamlit / FastAPI imports) so
the same package backs the Streamlit MVP today and a FastAPI service later.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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


class Category(str, Enum):
    PROVENANCE = "provenance"
    QC = "qc"
    PIPELINE = "pipeline"
    METADATA = "metadata"


class Evidence(BaseModel):
    """A single, traceable piece of supporting evidence for a finding.

    Every finding must cite where it came from so an operator can verify the
    recommendation without reconstructing context from scattered files.
    """

    source: str = Field(..., description="Artifact the evidence came from, e.g. 'SampleSheet.csv'")
    locator: str | None = Field(None, description="Row/field/line pointer within the source")
    value: str | None = Field(None, description="The observed value or excerpt")
    expected: str | None = Field(None, description="The expected value or threshold, when applicable")


class Finding(BaseModel):
    """A single deterministic observation produced by the rule engine.

    Findings are *facts* (with citations). They carry a suggested verdict, but
    the final verdict on the card is decided by aggregating all findings.
    """

    rule_id: str
    category: Category
    severity: Severity
    title: str
    detail: str
    evidence: list[Evidence] = Field(default_factory=list)
    suggested_verdict: Verdict


class DecisionCard(BaseModel):
    """The synthesized, operator-facing output for one sample.

    `verdict`, `findings`, and `evidence` are grounded in the deterministic rule
    engine. `rationale` and `next_steps` are the narration layer — produced by
    the StubSynthesizer today and by Claude once live synthesis is enabled.
    """

    sample_id: str
    verdict: Verdict
    confidence: float = Field(..., ge=0.0, le=1.0)
    headline: str
    rationale: str
    next_steps: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    generated_by: str = Field("stub", description="'stub' or 'claude' — provenance of the narration")

    @property
    def is_actionable(self) -> bool:
        """True when the card needs a human touch (anything but a clean pass)."""
        return self.verdict is not Verdict.PROCEED


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
