"""The runbook: operator-configurable thresholds and gate policy.

In a real deployment this would be a versioned YAML the lab owns. Keeping it as
a typed object here makes the rule engine's decisions fully traceable ("held
because Q30 84.1 < gate 85.0") and lets the UI show *which rule* fired.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QCThreshold(BaseModel):
    """A one-sided QC gate with a borderline band.

    A value past `hard_fail` is a CRITICAL finding; a value within
    `borderline_band` (relative) of the gate is a WARN (borderline) finding.
    `higher_is_better` flips the comparison direction for metrics like
    duplication rate where lower is better.
    """

    metric: str
    # Registry `our_key` (controlled vocabulary) this threshold gates on — the stable link
    # from the runbook to the metric registry (metric_registry.md rule 4). A test asserts
    # every our_key is registered.
    our_key: str
    label: str
    # `gate`/`hard_fail` are in the metric's registry CANONICAL unit (decimals — a fraction
    # for rates like Q30 0.85, `x` for coverage). The rules compare
    # `MetricValue.normalized_value` (also canonical) against them, so a threshold and the
    # value it gates are always on the same scale (schemas.md units contract). `unit` is the
    # DISPLAY symbol (%/x) the finding renders the canonical value back into for operators.
    gate: float
    hard_fail: float
    higher_is_better: bool = True
    borderline_band: float = 0.03  # within 3% (relative) of the gate -> borderline
    unit: str = ""


class Runbook(BaseModel):
    run_id_field: str = "run_id"
    require_metadata_fields: list[str] = Field(
        default_factory=lambda: ["subject_id", "tissue", "library_prep", "submitted_by"]
    )
    qc_thresholds: list[QCThreshold] = Field(
        default_factory=lambda: [
            # gate/hard_fail in CANONICAL units (fractions for rates, x for coverage) — the
            # same scale as MetricValue.normalized_value the rules compare them against.
            QCThreshold(
                metric="q30", our_key="qc.q30", label="Q30", gate=0.85, hard_fail=0.75, unit="%"
            ),
            QCThreshold(
                metric="pct_reads_identified",
                our_key="qc.reads_passing_filter",
                label="% reads identified",
                gate=0.70,
                hard_fail=0.50,
                unit="%",
            ),
            QCThreshold(
                metric="mean_coverage",
                our_key="qc.mean_target_coverage",
                label="Mean coverage",
                gate=30.0,
                hard_fail=15.0,
                unit="x",
            ),
            QCThreshold(
                metric="cluster_pf",
                our_key="qc.cluster_pf",
                label="Cluster PF",
                gate=0.80,
                hard_fail=0.60,
                unit="%",
            ),
            QCThreshold(
                metric="dup_rate",
                our_key="qc.duplication",
                label="Duplication rate",
                gate=0.30,
                hard_fail=0.50,
                higher_is_better=False,
                unit="%",
            ),
        ]
    )
    # Log substrings that indicate a failed pipeline step for a given sample.
    log_failure_markers: list[str] = Field(
        default_factory=lambda: ["ERROR", "FAILED", "exit code 1", "segmentation fault"]
    )

    def threshold_for(self, metric: str) -> QCThreshold | None:
        return next((t for t in self.qc_thresholds if t.metric == metric), None)


DEFAULT_RUNBOOK = Runbook()
