"""The runbook: operator-configurable thresholds and gate policy.

In a real deployment this would be a versioned YAML the lab owns. Keeping it as
a typed object here makes the rule engine's decisions fully traceable ("held
because Q30 84.1 < gate 85.0") and lets the UI show *which rule* fired.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .metrics.mapping import producible_metric_keys


class QCThreshold(BaseModel):
    """A QC gate. Two shapes, discriminated by `kind`:

    `one_sided` (the DEFAULT, unchanged): a value past `hard_fail` is a CRITICAL finding; a value
    within `borderline_band` (relative) of the gate is a WARN (borderline) finding.
    `higher_is_better` flips the comparison direction for metrics like duplication rate where lower
    is better. `gate`/`hard_fail` decide.

    `target_band` (WS-06 Gap 2): a BOTH-TAILS gate for a metric whose registry ``direction`` is
    ``target_band`` (e.g. Ts/Tv, fold-enrichment) — out of spec on EITHER tail. The four canonical
    band fields decide (``gate``/``hard_fail``/``higher_is_better`` are unused): PASS inside
    ``[target_low, target_high]``; WARN/HOLD inside ``[hard_low, hard_high]`` but outside the target
    band; CRITICAL/RERUN outside the hard band. A one-sided gate can only catch one tail, so a
    target_band metric could never score until this shape existed. Bands are illustrative /
    operator-configurable, NOT clinical (CLAUDE.md life-science guardrail 3).
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
    # WS-06 Gap 2: the gate SHAPE. `one_sided` (default) keeps `gate`/`hard_fail`/`higher_is_better`
    # 100% unchanged — every existing threshold is byte-identical. `target_band` switches to the
    # four canonical band fields below (a both-tails gate); `gate`/`hard_fail` are then unused but
    # stay required for schema stability, so set them to representative in-band edges.
    kind: Literal["one_sided", "target_band"] = "one_sided"
    # Canonical-unit (registry scale, same as `gate`/`hard_fail`) band edges for a `target_band`
    # gate; all four None for a `one_sided` gate (the default). PASS in [target_low, target_high];
    # WARN in [hard_low, hard_high] but outside target; CRITICAL outside [hard_low, hard_high].
    target_low: float | None = None
    target_high: float | None = None
    hard_low: float | None = None
    hard_high: float | None = None

    @model_validator(mode="after")
    def _validate_band(self) -> QCThreshold:
        """A `target_band` gate must carry all four band edges, ordered outer→inner→inner→outer.

        `one_sided` (the default) is untouched — the band fields stay None and this is a no-op — so
        every existing threshold + test is byte-identical. For `target_band`, a missing edge means
        the gate can't score the band it claims to; a mis-ordered band (e.g. target wider than hard)
        is nonsensical. Fail loud at construction rather than silently mis-gating a real run.
        """
        if self.kind != "target_band":
            return self
        edges = {
            "hard_low": self.hard_low,
            "target_low": self.target_low,
            "target_high": self.target_high,
            "hard_high": self.hard_high,
        }
        missing = [name for name, v in edges.items() if v is None]
        if missing:
            raise ValueError(
                f"target_band threshold {self.our_key!r} requires all four band edges; "
                f"missing: {missing}"
            )
        # mypy: the None-check above guarantees these are floats.
        assert (
            self.hard_low is not None
            and self.target_low is not None
            and self.target_high is not None
            and self.hard_high is not None
        )
        if not (self.hard_low <= self.target_low <= self.target_high <= self.hard_high):
            raise ValueError(
                f"target_band threshold {self.our_key!r} band must order "
                f"hard_low <= target_low <= target_high <= hard_high; got "
                f"[{self.hard_low}, {self.target_low}, {self.target_high}, {self.hard_high}]"
            )
        return self


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
                # WS-06 §9c: this our_key is fastp's `pct_surviving` (reads passing filter), NOT a
                # demux "reads identified" share — label it as the registry display_name does. (The
                # `metric`/CSV field name stays for the parser binding; the operator-facing label is
                # what was mislabelled.)
                label="Reads passing filter",
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
            # WS-06 Gap 2: a BOTH-TAILS (target_band) gate for Ts/Tv, the first threshold that can
            # actually score a registry `direction: target_band` metric. Ts/Tv is out of spec on
            # EITHER tail (too low → excess sequencing/false-positive artifact; too high → over-
            # aggressive filtering), which a one-sided gate structurally can't catch. required=False
            # means a run without a `variant_titv` value (the pinned demo + HG002) NA-flags nothing
            # and every existing verdict is byte-identical. The band is an ILLUSTRATIVE whole-genome
            # heuristic (~2.0-2.1 typical, hard 1.8-2.8), NOT a clinical threshold, and is
            # operator-configurable (CLAUDE.md life-science guardrail 3). `gate`/`hard_fail` are
            # unused for a target_band gate but required by the schema — set to the target edges.
            QCThreshold(
                metric="variant_titv",
                our_key="variant.titv",
                label="Ts/Tv ratio",
                gate=2.0,
                hard_fail=1.8,
                kind="target_band",
                target_low=2.0,
                target_high=2.1,
                hard_low=1.8,
                hard_high=2.8,
                required=False,
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
