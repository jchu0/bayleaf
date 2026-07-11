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
    # When False, a MISSING metric for this threshold is NOT a finding (the metric is optional —
    # only a present-but-failing value gates). This lets the runbook carry richer, non-blocking
    # checks (extra-QC / variant tier) that score a run which emits them, without NA-flagging a lean
    # run that omits them. The five frozen-CSV metrics stay required=True (unchanged behavior).
    required: bool = True


class RouteToHumanPolicy(BaseModel):
    """OFF-BY-DEFAULT rule that routes a sample to mandatory human review when an annotated
    variant carries a clinically-significant ClinVar classification (ADR-0018 decision D2).

    This is a review-ROUTING rule, NOT a clinical-significance gate. It authors no pathogenicity:
    it reads a variant's *already-present, verbatim* ClinVar significance as EVIDENCE and escalates
    to human judgment — the most conservative action (never auto-proceed, never auto-classify). A
    deterministic rule decides to ROUTE; a qualified human adjudicates the clinical meaning (rules
    decide / humans adjudicate, ADR-0001). Empty ``significances`` = DISARMED (the default), so a
    stock runbook never routes and the deterministic QC gate is byte-for-byte unchanged. Thresholds
    here are illustrative/operator-configurable, NOT clinical thresholds (CLAUDE.md guardrail 3).
    """

    # ClinVar CLNSIG values (matched case-/separator-insensitively) that route a sample to human
    # review. EMPTY by default → the rule is OFF. e.g. ("Pathogenic", "Likely_pathogenic").
    significances: tuple[str, ...] = ()
    # Optional review-status allow-list (star rating floor). Empty → any review status qualifies
    # (still requires an armed significance match). e.g. ("criteria_provided,_multiple_submitters").
    review_statuses: tuple[str, ...] = ()

    @property
    def armed(self) -> bool:
        """True only when at least one significance is configured (else the rule never fires)."""
        return bool(self.significances)


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
            # ── Optional, non-blocking checks (required=False) ──────────────────────────────────
            # They gate a value that IS present but never NA-flag a run that omits them, so a richer
            # (contrived) run is scored on these while a lean (real) run is not. gate/hard_fail are
            # canonical (fractions for the % ones, x for depth); phix / GQ / Ts-Tv stay ungated
            # observations (a control / a target-band metric the one-sided gate can't score).
            QCThreshold(
                metric="breadth_20x",
                our_key="qc.breadth_20x",
                label="Breadth ≥20x",
                gate=0.90,
                hard_fail=0.80,
                required=False,
                unit="%",
            ),
            QCThreshold(
                metric="breadth_30x",
                our_key="qc.breadth_30x",
                label="Breadth ≥30x",
                gate=0.80,
                hard_fail=0.65,
                required=False,
                unit="%",
            ),
            QCThreshold(
                metric="pct_mapped",
                our_key="qc.pct_mapped",
                label="Mapped reads",
                gate=0.95,
                hard_fail=0.90,
                required=False,
                unit="%",
            ),
            QCThreshold(
                metric="on_target",
                our_key="qc.on_target",
                label="On-target rate",
                gate=0.60,
                hard_fail=0.40,
                required=False,
                unit="%",
            ),
            QCThreshold(
                metric="variant_dp",
                our_key="variant.dp",
                label="Variant depth (DP)",
                gate=20.0,
                hard_fail=10.0,
                required=False,
                unit="x",
            ),
        ]
    )
    # Log substrings that indicate a failed pipeline step for a given sample.
    log_failure_markers: list[str] = Field(
        default_factory=lambda: ["ERROR", "FAILED", "exit code 1", "segmentation fault"]
    )
    # Execution-trace task statuses that count as an operational failure (EXEC-001). A task is
    # also a failure on a nonzero exit code, whatever its status. Illustrative/configurable.
    trace_failure_statuses: list[str] = Field(default_factory=lambda: ["FAILED", "ABORTED"])
    # OFF-BY-DEFAULT route-to-human policy (ADR-0018 D2). Disarmed by default (no significances),
    # so the stock runbook never routes and the deterministic QC gate is unchanged. An operator
    # arms it to escalate ClinVar-significant candidates to mandatory human review (RBAC-gated).
    route_to_human: RouteToHumanPolicy = Field(default_factory=RouteToHumanPolicy)

    def threshold_for(self, metric: str) -> QCThreshold | None:
        return next((t for t in self.qc_thresholds if t.metric == metric), None)


DEFAULT_RUNBOOK = Runbook()
