"""The runbook: operator-configurable thresholds and gate policy.

In a real deployment this would be a versioned YAML the lab owns. Keeping it as
a typed object here makes the rule engine's decisions fully traceable ("held
because Q30 84.1 < gate 85.0") and lets the UI show *which rule* fired.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .metrics.mapping import producible_metric_keys


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
            # STRUCTURAL, EXPECTED HOLD (audit P3-1): cluster_pf is a RUN-LEVEL SAV/InterOp metric
            # (Illumina %PF clusters). A reads-only fastq→BAM path (the live GIAB driver,
            # scripts/run_giab_pipeline.py) structurally CANNOT produce it, so it arrives absent and
            # this required=True threshold NA-flags → every reads-based run HOLDs. That HOLD is the
            # honest "cluster_pf-missing" signal the pinned demo relies on (HG002 → HOLD), NOT a QC
            # failure. Keeping required=True is a deliberate honesty choice: reaching PROCEED on the
            # live path means SOURCING cluster_pf from a real SAV/InterOp feed (a deferred policy
            # decision), never flipping this flag. Do NOT change `required` (ADR-0001/G1).
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
            # VARIANT-GATE SCOPE (audit P3-10): the variant gate is DP-ONLY — `variant.dp` is the
            # only variant-tier THRESHOLD here. GQ (`variant.gq`) and Ts/Tv (`variant.titv`) are
            # registered + wired but UNGATED observations (a phred / target-band metric the
            # one-sided gate can't score); allele-balance (`variant.allele_balance`) and gnomAD AF
            # are NOT computed (no parser). This is a genotype-DEPTH gate, not a full
            # variant-quality gate; label it as such wherever it surfaces (fuller variant QC later).
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
    # WS-01: the named pipeline profile this runbook scores (default = the lean base profile). Used
    # only for honest narration today; WS-05's `RunbookSet` will key profiles by this.
    pipeline_profile: str = "default"
    # WS-01 (fail-closed): registry `our_key`s a profile EXPECTS to have examined. Any expected key
    # with no observed value → a `QC-EXPECTED-<key>` HOLD (rules._check_expected_metrics), so a
    # profile-bound safety metric can no longer skip silently when a pipeline simply omits it. EMPTY
    # by default → DEFAULT_RUNBOOK is byte-for-byte unchanged (a genuinely lean run is never
    # penalised). MECHANISM ONLY in WS-01·PR1: no deployed code sets this yet (`_active_runbook`
    # never populates it), so QC-EXPECTED fires only for a runbook that explicitly opts in — the
    # production consumer (a per-profile expected set) is WS-05's `RunbookSet`, which lifts this
    # SAME field onto the per-(assay, sample_type, platform) profile (a move, not a rename).
    expected_metrics: tuple[str, ...] = ()

    @field_validator("expected_metrics")
    @classmethod
    def _expected_metrics_are_producible(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        """Fail LOUD at config-load if a profile expects a metric the parse layer cannot produce.

        Without this, a typo'd or registered-but-unwired key (7 of 20 registered keys have no
        parser) is *never* in `by_key`, so it would HOLD every sample of every run forever, with a
        finding that misdirects the operator toward the pipeline instead of the profile config. A
        profile may only expect a metric the system can actually examine. Also de-dupes (order
        kept), so a duplicated key can't emit two identical findings.
        """
        producible = producible_metric_keys()
        seen: dict[str, None] = {}
        for key in v:
            if key not in producible:
                raise ValueError(
                    f"expected_metrics key {key!r} is not producible by the current parse layer; "
                    f"a profile may only expect a metric the system can examine. Producible keys: "
                    f"{sorted(producible)}"
                )
            seen.setdefault(key, None)  # de-dupe, preserving first-seen order
        return tuple(seen)

    def threshold_for(self, metric: str) -> QCThreshold | None:
        return next((t for t in self.qc_thresholds if t.metric == metric), None)


DEFAULT_RUNBOOK = Runbook()
