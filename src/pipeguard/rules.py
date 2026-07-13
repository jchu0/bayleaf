"""The deterministic rule engine.

This is the trust anchor of the whole system. It never guesses: it computes hard,
cited `Finding`s from the artifacts and the runbook. The synthesis layer (stub or
Claude) may *narrate* these findings but must not invent numbers or verdicts the
rules didn't produce.

Rule families:
    provenance  - barcode/index mismatch, sample present in some artifacts but not others
    metadata    - required intake fields missing
    qc          - metric vs. runbook gate (borderline WARN vs. hard-fail CRITICAL)
    pipeline    - a run-log failure marker (PIPE-001) or a failed execution-trace task (EXEC-001)
"""

from __future__ import annotations

from .metrics import MetricRegistry, default_registry, metric_values_for
from .models import (
    Category,
    CheckCoverage,
    Evidence,
    Finding,
    MetricValue,
    QCMetrics,
    RunArtifacts,
    Sample,
    SampleSheetEntry,
    Severity,
    SourceKind,
    TraceRecord,
    VariantCall,
    Verdict,
)
from .runbook import DEFAULT_RUNBOOK, QCThreshold, Runbook


def _combine_index(entry: SampleSheetEntry) -> str | None:
    """Render a sample sheet's declared barcode the way demux reports it: 'i7-i5'."""
    if entry.index and entry.index2:
        return f"{entry.index}-{entry.index2}"
    return entry.index or entry.index2


def _check_barcode(
    sid: str,
    sheet: SampleSheetEntry | None,
    demux_index: str | None,
    demux_source: str,
) -> Finding | None:
    if sheet is None or not demux_index:
        return None
    expected = _combine_index(sheet)
    if expected is None:
        return None
    if expected.upper() == demux_index.strip().upper():
        return None
    return Finding(
        rule_id="PROV-001",
        sample_id=sid,
        category=Category.PROVENANCE,
        severity=Severity.CRITICAL,
        title="Barcode does not match the declared sample sheet",
        detail=(
            f"Sample {sid} was demultiplexed on index {demux_index}, but the sample "
            f"sheet declares {expected}. A barcode/sample-ID mismatch means reads may "
            f"be attributed to the wrong sample — chain of custody is not intact."
        ),
        evidence=[
            Evidence(
                source="SampleSheet.csv",
                locator=f"Sample_ID={sid}",
                value=expected,
                expected="matches demultiplexed index",
            ),
            Evidence(
                source=demux_source,
                locator=f"SampleID={sid}",
                value=demux_index,
                expected=expected,
            ),
        ],
        suggested_verdict=Verdict.ESCALATE,
    )


def _check_presence(
    sid: str,
    meta: Sample | None,
    sheet: SampleSheetEntry | None,
    qc: QCMetrics | None,
) -> list[Finding]:
    findings: list[Finding] = []
    # Sequenced/QC'd but never declared on the sample sheet -> provenance gap.
    if sheet is None and qc is not None:
        findings.append(
            Finding(
                rule_id="PROV-002",
                sample_id=sid,
                category=Category.PROVENANCE,
                severity=Severity.CRITICAL,
                title="Sample has QC results but is absent from the sample sheet",
                detail=(
                    f"{sid} appears in QC output but not in the sample sheet, so its "
                    f"provenance cannot be established."
                ),
                evidence=[
                    Evidence(source="qc_metrics.csv", locator=f"sample_id={sid}", value="present"),
                    Evidence(source="SampleSheet.csv", locator=f"Sample_ID={sid}", value="missing"),
                ],
                suggested_verdict=Verdict.ESCALATE,
            )
        )
    # Declared on the sample sheet (submitted for sequencing) but NO QC artifact — the symmetric
    # partner of PROV-002. Missing QC is unverified DATA, not clean data: without a rule here the
    # sample emits zero findings and `aggregate_verdict([])` PROCEEDs — the exact case a safety gate
    # must fail CLOSED on. Guarded on `sheet is not None` so a not-yet-sequenced, intake-only sample
    # (no sheet, no QC) is never false-HOLDed (WS-01 Gap A).
    if sheet is not None and qc is None:
        findings.append(
            Finding(
                rule_id="QC-MISSING",
                sample_id=sid,
                category=Category.QC,
                severity=Severity.WARN,
                title="Declared for sequencing but no QC results",
                detail=(
                    f"{sid} is declared on the sample sheet but has no QC row, so it was never "
                    f"examined. Missing QC is treated as unverified (HOLD), never as passing."
                ),
                evidence=[
                    Evidence(
                        source="qc_metrics.csv",
                        locator=f"sample_id={sid}",
                        value="missing",
                        expected="present",
                        source_kind=SourceKind.METRIC,
                    )
                ],
                suggested_verdict=Verdict.HOLD,
            )
        )
    # Declared and sequenced but no intake metadata -> can't confirm what it is.
    if meta is None and (sheet is not None or qc is not None):
        findings.append(
            Finding(
                rule_id="META-002",
                sample_id=sid,
                category=Category.METADATA,
                severity=Severity.WARN,
                title="No intake metadata for a sequenced sample",
                detail=f"{sid} was processed but has no row in the intake sheet.",
                evidence=[
                    Evidence(
                        source="sample_metadata.csv", locator=f"sample_id={sid}", value="missing"
                    )
                ],
                suggested_verdict=Verdict.HOLD,
            )
        )
    return findings


def _check_metadata(sid: str, meta: Sample | None, runbook: Runbook) -> Finding | None:
    if meta is None:
        return None
    missing = []
    for field in runbook.require_metadata_fields:
        value = getattr(meta, field, None)
        if value is None:
            value = meta.extra.get(field)
        if value in (None, ""):
            missing.append(field)
    if not missing:
        return None
    return Finding(
        rule_id="META-001",
        sample_id=sid,
        category=Category.METADATA,
        severity=Severity.WARN,
        title="Required intake metadata is missing",
        detail=(
            f"Sample {sid} is missing required field(s): {', '.join(missing)}. "
            f"Incomplete provenance metadata blocks downstream traceability."
        ),
        evidence=[
            Evidence(
                source="sample_metadata.csv",
                locator=f"sample_id={sid}",
                value=f,
                expected="present",
            )
            for f in missing
        ],
        suggested_verdict=Verdict.HOLD,
    )


# The runbook `unit` is a display SYMBOL, but the metric registry's conversion table is keyed on
# unit NAMES. Only "%" needs translating (→ "percent"); "x"/"ratio"/"" already match a registry
# unit name or have no conversion (a passthrough). See `_to_display_unit`.
_DISPLAY_UNIT_NAME: dict[str, str] = {"%": "percent"}


def _to_display_unit(
    reg: MetricRegistry, our_key: str, canonical_value: float, symbol: str
) -> float:
    """Render a CANONICAL (normalized) value into the number shown beside the runbook `symbol`.

    Mirrors `api/card_readout._to_display` (normalized_value → threshold.unit) so the finding text
    and the QC-readout side-channel can never disagree by a factor of 100 for a fraction-raw metric
    (breadth/pct_mapped/on_target), whose raw_unit ("fraction") differs from its display symbol
    ("%"). Bridges the display symbol to the registry unit NAME, then denormalizes over the
    registry's OWN closed conversion table (never a hardcoded 100x). A symbol the registry has no
    distinct unit for (e.g. "x", "") leaves the canonical value unchanged — the same conservative
    passthrough card_readout uses rather than guessing a conversion.
    """
    to_unit = _DISPLAY_UNIT_NAME.get(symbol.strip(), symbol.strip())
    try:
        return reg.denormalize(our_key, canonical_value, to_unit)
    except ValueError:
        return canonical_value


def _evaluate_metric(sid: str, threshold: QCThreshold, mv: MetricValue | None) -> Finding | None:
    if mv is None:
        # Optional threshold + no observation → nothing to say (only a present-but-failing value
        # gates an optional metric). Keeps a lean run from being NA-flagged on richer checks.
        if not threshold.required:
            return None
        return Finding(
            rule_id=f"QC-{threshold.metric.upper()}-NA",
            sample_id=sid,
            category=Category.QC,
            severity=Severity.WARN,
            title=f"{threshold.label} is missing",
            detail=f"No {threshold.label} value was reported for {sid}.",
            evidence=[
                Evidence(
                    source="qc_metrics.csv",
                    locator=f"{sid}.{threshold.metric}",
                    value="missing",
                    source_kind=SourceKind.METRIC,
                    source_field=threshold.metric,
                )
            ],
            suggested_verdict=Verdict.HOLD,
        )

    # WS-06 Gap 2: a target_band metric (Ts/Tv, fold-enrichment) is out of spec on EITHER tail, so
    # it is scored by the band branch, not the one-sided gate below (which can only catch one side).
    if threshold.kind == "target_band":
        return _evaluate_target_band(sid, threshold, mv)

    # DECISION on the CANONICAL (normalized) value vs the canonical threshold — both on the
    # registry's scale, so a change in the source's raw unit can't silently move the gate.
    value = mv.normalized_value
    passes = value >= threshold.gate if threshold.higher_is_better else value <= threshold.gate
    if passes:
        return None

    hard_fail = (
        value < threshold.hard_fail if threshold.higher_is_better else value > threshold.hard_fail
    )
    if hard_fail:
        severity = Severity.CRITICAL
        verdict = Verdict.RERUN
        qualifier = "hard-fails"
    else:
        # Distinguish a true borderline (just past the gate) from a clear miss. The band is
        # relative (gate * (1 ± band)), so the classification is scale-invariant.
        if threshold.higher_is_better:
            borderline_edge = threshold.gate * (1 - threshold.borderline_band)
            borderline = value >= borderline_edge
        else:
            borderline_edge = threshold.gate * (1 + threshold.borderline_band)
            borderline = value <= borderline_edge
        severity = Severity.WARN
        verdict = Verdict.HOLD
        qualifier = "is borderline against" if borderline else "misses"

    # DISPLAY in the operator-facing unit (schemas.md units contract): the observed value and the
    # canonical thresholds rendered into the runbook DISPLAY unit (`threshold.unit`) so the message
    # reads naturally (e.g. "84.1%; gate >= 85%"). Converts from the CANONICAL value — not the raw
    # value — via the same normalized→display path card_readout uses, so a fraction-raw metric
    # (raw_unit "fraction", display "%") no longer renders 100x too small (0.85% -> 85%).
    reg = default_registry()
    disp_value = _to_display_unit(reg, threshold.our_key, mv.normalized_value, threshold.unit)
    disp_gate = _to_display_unit(reg, threshold.our_key, threshold.gate, threshold.unit)
    disp_hard = _to_display_unit(reg, threshold.our_key, threshold.hard_fail, threshold.unit)
    direction = "≥" if threshold.higher_is_better else "≤"
    return Finding(
        rule_id=f"QC-{threshold.metric.upper()}",
        sample_id=sid,
        category=Category.QC,
        severity=severity,
        title=f"{threshold.label} {qualifier} the QC gate",
        detail=(
            f"{threshold.label} for {sid} is {disp_value:g}{threshold.unit}; runbook gate is "
            f"{direction} {disp_gate:g}{threshold.unit} "
            f"(hard-fail {disp_hard:g}{threshold.unit})."
        ),
        evidence=[
            Evidence(
                source="qc_metrics.csv",
                locator=f"{sid}.{threshold.metric}",
                value=f"{disp_value:g}{threshold.unit}",
                expected=f"{direction} {disp_gate:g}{threshold.unit}",
                source_kind=SourceKind.METRIC,
                source_field=threshold.metric,
                threshold=f"hard-fail {direction} {disp_hard:g}{threshold.unit}",
            )
        ],
        suggested_verdict=verdict,
    )


def _evaluate_target_band(sid: str, threshold: QCThreshold, mv: MetricValue) -> Finding | None:
    """Score a BOTH-TAILS (target_band) metric against its canonical band (WS-06 Gap 2).

    PASS (None) inside ``[target_low, target_high]``; a WARN → HOLD ``Finding`` inside
    ``[hard_low, hard_high]`` but outside the target band (either tail); a CRITICAL → RERUN
    ``Finding`` outside the hard band (either tail). Decides on the CANONICAL (normalized) value vs
    canonical band edges — same scale, so the source's raw unit can't silently move the gate — then
    renders value + both bands into the operator DISPLAY unit via the same ``_to_display_unit`` path
    the one-sided branch uses. The rule only AUTHORS the finding; ``aggregate_verdict`` maps it to a
    verdict (ADR-0001)."""
    value = mv.normalized_value
    # The QCThreshold validator guarantees all four edges are present for kind=="target_band"; the
    # asserts narrow float | None -> float for mypy and document that invariant.
    assert (
        threshold.target_low is not None
        and threshold.target_high is not None
        and threshold.hard_low is not None
        and threshold.hard_high is not None
    )
    if threshold.target_low <= value <= threshold.target_high:
        return None  # in the target band — passes

    within_hard = threshold.hard_low <= value <= threshold.hard_high
    if within_hard:
        severity = Severity.WARN
        verdict = Verdict.HOLD
        qualifier = "is outside the target band"
    else:
        severity = Severity.CRITICAL
        verdict = Verdict.RERUN
        qualifier = "is outside the acceptable band"

    reg = default_registry()
    u = threshold.unit
    disp_value = _to_display_unit(reg, threshold.our_key, value, u)
    disp_tlo = _to_display_unit(reg, threshold.our_key, threshold.target_low, u)
    disp_thi = _to_display_unit(reg, threshold.our_key, threshold.target_high, u)
    disp_hlo = _to_display_unit(reg, threshold.our_key, threshold.hard_low, u)
    disp_hhi = _to_display_unit(reg, threshold.our_key, threshold.hard_high, u)
    return Finding(
        rule_id=f"QC-{threshold.metric.upper()}",
        sample_id=sid,
        category=Category.QC,
        severity=severity,
        title=f"{threshold.label} {qualifier}",
        detail=(
            f"{threshold.label} for {sid} is {disp_value:g}{u}; runbook target band is "
            f"[{disp_tlo:g}, {disp_thi:g}]{u} (hard band [{disp_hlo:g}, {disp_hhi:g}]{u})."
        ),
        evidence=[
            Evidence(
                source="qc_metrics.csv",
                locator=f"{sid}.{threshold.metric}",
                value=f"{disp_value:g}{u}",
                expected=f"within [{disp_tlo:g}, {disp_thi:g}]{u}",
                source_kind=SourceKind.METRIC,
                source_field=threshold.metric,
                threshold=f"hard band [{disp_hlo:g}, {disp_hhi:g}]{u}",
            )
        ],
        suggested_verdict=verdict,
    )


def _check_expected_metrics(
    sid: str, by_key: dict[str, MetricValue], runbook: Runbook
) -> list[Finding]:
    """Turn a profile's EXPECTED-but-absent metric into a HOLD (WS-01, fail-closed).

    For each registry ``our_key`` the runbook's ``expected_metrics`` names but the sample produced
    no ``MetricValue`` for, emit ``QC-EXPECTED-<key>`` (WARN → HOLD). This restores signal for a
    ``required=False`` safety metric *bound to a named profile* — a pipeline that simply omits it
    can no longer read "all clear" — WITHOUT NA-flagging a genuinely lean run: an empty
    ``expected_metrics`` (the DEFAULT) makes this a no-op. The verdict still comes only from
    ``aggregate_verdict`` over these self-authored findings (ADR-0001); this rule decides that
    absence is *unverified*, never that the metric failed. An unregistered key is never in
    ``by_key``, so it surfaces as a HOLD too — a misconfigured profile fails loud, not silent.
    """
    findings: list[Finding] = []
    for our_key in runbook.expected_metrics:
        if our_key in by_key:
            continue
        findings.append(
            Finding(
                rule_id=f"QC-EXPECTED-{our_key.upper()}",
                sample_id=sid,
                category=Category.QC,
                severity=Severity.WARN,
                title=f"Expected metric not examined: {our_key}",
                detail=(
                    f"The '{runbook.pipeline_profile}' profile expects {our_key} to be examined, "
                    f"but no value was reported for {sid}. An expected-but-absent metric is "
                    f"treated as unverified (HOLD), not as passing."
                ),
                evidence=[
                    Evidence(
                        source="qc_metrics.csv",
                        locator=f"{sid}.{our_key}",
                        value="not examined",
                        expected="present",
                        source_kind=SourceKind.METRIC,
                        source_field=our_key,
                    )
                ],
                suggested_verdict=Verdict.HOLD,
            )
        )
    return findings


def _check_log(sid: str, log_lines: list[str], runbook: Runbook) -> Finding | None:
    hits = [
        line
        for line in log_lines
        if sid in line and any(marker in line for marker in runbook.log_failure_markers)
    ]
    if not hits:
        return None
    return Finding(
        rule_id="PIPE-001",
        sample_id=sid,
        category=Category.PIPELINE,
        severity=Severity.CRITICAL,
        title="Pipeline logged a failure for this sample",
        detail=f"The run log contains {len(hits)} failure marker(s) referencing {sid}.",
        evidence=[
            Evidence(
                source="pipeline.log",
                locator="matched line",
                value=line.strip(),
                source_kind=SourceKind.EXECUTION_TRACE,
            )
            for line in hits[:5]
        ],
        suggested_verdict=Verdict.RERUN,
    )


def _check_execution_trace(sid: str, trace: list[TraceRecord], runbook: Runbook) -> Finding | None:
    """EXEC-001: a failed pipeline PROCESS (from the structured Nextflow trace) → RERUN.

    The structured sibling of PIPE-001: instead of grepping a free-text log it reads the task
    table (`trace.txt`). A task belongs to this sample by its nf-core `tag` (EXACT match, so a
    zero-padded id can't cross-fire the way a substring would); a task is a failure when its
    status is in the runbook's failure set OR its exit code is nonzero. Operational failures
    map to RERUN (qc_metrics.md verdict policy 3). Composes ≠ executes: this READS a trace the
    run produced, it never runs a process.
    """
    fails = [
        t
        for t in trace
        if t.tag == sid
        and (
            (t.status is not None and t.status in runbook.trace_failure_statuses)
            or (t.exit is not None and t.exit != 0)
        )
    ]
    if not fails:
        return None
    return Finding(
        rule_id="EXEC-001",
        sample_id=sid,
        category=Category.PIPELINE,
        severity=Severity.CRITICAL,
        title="A pipeline process failed for this sample",
        detail=f"The execution trace reports {len(fails)} failed task(s) for {sid}.",
        evidence=[
            Evidence(
                source="trace.txt",
                locator=t.process or t.task_id or "task",
                value=f"status={t.status or '?'} exit={t.exit if t.exit is not None else '?'}",
                source_kind=SourceKind.EXECUTION_TRACE,
            )
            for t in fails[:5]
        ],
        suggested_verdict=Verdict.RERUN,
    )


def _norm_sig(value: str) -> str:
    """Fold a ClinVar significance / review-status string for robust matching.

    ClinVar writes "Likely_pathogenic", a config may say "likely pathogenic" — comparing on
    alphanumerics only makes the match separator-/case-insensitive WITHOUT ever altering the
    stored/quoted string (the finding always cites the value verbatim; this is match-only).
    """
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _check_route_to_human(
    sid: str, variant_calls: list[VariantCall], runbook: Runbook
) -> Finding | None:
    """VAR-RTH-001 — route a sample to MANDATORY human review when an annotated candidate carries
    an armed ClinVar significance (ADR-0018 D2).

    OFF BY DEFAULT: `runbook.route_to_human` is disarmed unless an operator configures
    significances, so a stock run never fires this and the deterministic QC gate is unchanged.
    When armed, this is a review-ROUTING rule, NOT a clinical-significance verdict: it quotes
    ClinVar VERBATIM as cited evidence and suggests ESCALATE (route to a human) — it authors no
    pathogenicity of its own (ADR-0004). A qualified human adjudicates via the RBAC-gated review
    queue (ADR-0017). The action space is only {route-to-human}; there is no Pathogenic/Benign
    determination and no probability.
    """
    policy = runbook.route_to_human
    if not policy.armed:
        return None
    armed = {_norm_sig(s) for s in policy.significances}
    allowed_rev = {_norm_sig(s) for s in policy.review_statuses}
    hit = next(
        (
            v
            for v in variant_calls
            if v.sample_id == sid
            and v.clinvar_significance
            and _norm_sig(v.clinvar_significance) in armed
            and (
                not allowed_rev
                or (v.clinvar_review_status and _norm_sig(v.clinvar_review_status) in allowed_rev)
            )
        ),
        None,
    )
    if hit is None:
        return None
    gene_bit = f" in {hit.gene}" if hit.gene else ""
    hgvs_bit = f" ({hit.hgvs})" if hit.hgvs else ""
    citation = hit.clinvar_accession or "ClinVar"
    return Finding(
        rule_id="VAR-RTH-001",
        sample_id=sid,
        category=Category.VARIANT,
        severity=Severity.CRITICAL,
        title="Clinically significant variant — mandatory human review",
        detail=(
            f"An annotated candidate for {sid}{gene_bit}{hgvs_bit} is classified "
            f'"{hit.clinvar_significance}" in ClinVar ({citation}). Per the runbook route-to-human '
            f"policy this sample is ESCALATED to a qualified reviewer before release. PipeGuard "
            f"makes no pathogenicity determination of its own — the classification is quoted "
            f"verbatim from ClinVar and a human adjudicates."
        ),
        evidence=[
            Evidence(
                source=(f"ClinVar {hit.clinvar_version}" if hit.clinvar_version else "ClinVar"),
                locator=hit.clinvar_accession or hit.hgvs or f"sample_id={sid}",
                value=hit.clinvar_significance,  # VERBATIM CLNSIG — never PipeGuard's determination
                expected="reviewed by a qualified human before release",
                source_field="CLNSIG",
                threshold=(
                    f"review status: {hit.clinvar_review_status}"
                    if hit.clinvar_review_status
                    else None
                ),
            ),
            Evidence(
                source="variants.csv",
                locator=f"sample_id={sid}",
                value=f"{hit.gene or '?'} {hit.hgvs or ''}".strip(),
                expected="route-to-human policy armed",
            ),
        ],
        suggested_verdict=Verdict.ESCALATE,
    )


def evaluate_sample(sid: str, artifacts: RunArtifacts, runbook: Runbook) -> list[Finding]:
    meta = next((s for s in artifacts.samples if s.sample_id == sid), None)
    sheet = next((e for e in artifacts.sample_sheet if e.sample_id == sid), None)
    demux = next((d for d in artifacts.demux if d.sample_id == sid), None)
    qc = next((q for q in artifacts.qc if q.sample_id == sid), None)

    findings: list[Finding] = []
    findings.extend(_check_presence(sid, meta, sheet, qc))

    barcode = _check_barcode(sid, sheet, demux.index if demux else None, "demux_stats.csv")
    if barcode:
        findings.append(barcode)

    meta_finding = _check_metadata(sid, meta, runbook)
    if meta_finding:
        findings.append(meta_finding)

    if qc is not None:
        # Normalize once via the registry, then gate each threshold on its our_key's value.
        # A None QCMetrics field yields no MetricValue -> the threshold sees `None` (missing).
        by_key = {mv.metric_key: mv for mv in metric_values_for(qc)}
        for threshold in runbook.qc_thresholds:
            metric_finding = _evaluate_metric(sid, threshold, by_key.get(threshold.our_key))
            if metric_finding:
                findings.append(metric_finding)
        # Expected-metric set (WS-01): a profile-bound metric that was NOT examined → HOLD. The
        # `qc is None` is already covered by QC-MISSING above, so this only runs with QC present.
        findings.extend(_check_expected_metrics(sid, by_key, runbook))

    log_finding = _check_log(sid, artifacts.log_lines, runbook)
    if log_finding:
        findings.append(log_finding)

    trace_finding = _check_execution_trace(sid, artifacts.execution_trace, runbook)
    if trace_finding:
        findings.append(trace_finding)

    # Route-to-human (VAR-RTH-001) — OFF by default; fires only when the runbook arms it AND an
    # annotated candidate carries a matching ClinVar significance. Rules decide to route; a human
    # adjudicates (ADR-0018 D2). A stock run has an empty variant_calls list and a disarmed policy,
    # so this is a no-op and the existing demo scenario is byte-for-byte unchanged.
    rth_finding = _check_route_to_human(sid, artifacts.variant_calls, runbook)
    if rth_finding:
        findings.append(rth_finding)

    return findings


def evaluate_run(
    artifacts: RunArtifacts, runbook: Runbook | None = None
) -> dict[str, list[Finding]]:
    """Run every rule against every sample. Returns findings keyed by sample_id."""
    runbook = runbook or DEFAULT_RUNBOOK
    return {sid: evaluate_sample(sid, artifacts, runbook) for sid in artifacts.sample_ids()}


# The FIXED catalog of check CATEGORIES a QC decision claims to cover — the denominator for
# CheckCoverage (WS-01 Gap D). contamination + identity have NO parser today, so they are ALWAYS
# reported not-examined (honest absence, never silently omitted). The rest run when the artifact
# they read is present. A FIXED product claim, not runbook-derived — so an unexamined category can't
# vanish just because the runbook has no threshold for it. WS-02 flips contamination/identity to
# "ran" automatically (their first emitted finding does it — see below).
_EXPECTED_CATEGORIES: tuple[Category, ...] = (
    Category.PROVENANCE,
    Category.METADATA,
    Category.QC,
    Category.CONTAMINATION,
    Category.IDENTITY,
    Category.PIPELINE,
)


def compute_check_coverage(
    sid: str, artifacts: RunArtifacts, runbook: Runbook, findings: list[Finding]
) -> CheckCoverage:
    """Deterministic coverage telemetry: which of the fixed expected check categories ran for this
    sample vs. were NOT examined. A pure function of ``(artifacts, findings)`` computed in the trust
    anchor; it NARRATES coverage and never sets a verdict (ADR-0001).

    A category **ran** when its rule/parser EXECUTED — proxied by "the artifact it reads is present
    OR it emitted a finding for this sample" — NOT by "produced a finding". So a clean QC gate
    (finding-less) counts as ran (never confused with a gate that never ran — the review's
    ``gateRan`` fix), and a qc-only sample's provenance check (which emits PROV-002 on the missing
    sheet) counts too. contamination/identity have no parser today → not-examined until WS-02 wires
    FREEMIX / NGSCheckMate, at which point their first finding auto-flips them to ran. ``runbook``
    is taken for signature stability so a future ``RunbookSet`` profile can widen the catalog
    without a signature change.
    """
    meta = next((s for s in artifacts.samples if s.sample_id == sid), None)
    sheet = next((e for e in artifacts.sample_sheet if e.sample_id == sid), None)
    demux = next((d for d in artifacts.demux if d.sample_id == sid), None)
    qc = next((q for q in artifacts.qc if q.sample_id == sid), None)
    found_categories = {f.category for f in findings}
    artifact_present: dict[Category, bool] = {
        Category.PROVENANCE: sheet is not None or demux is not None,
        Category.METADATA: meta is not None,
        Category.QC: qc is not None,
        Category.CONTAMINATION: False,  # no parser today — WS-02 wires FREEMIX
        Category.IDENTITY: False,  # no parser today — WS-02 wires NGSCheckMate / sex-concordance
        Category.PIPELINE: bool(artifacts.log_lines) or bool(artifacts.execution_trace),
    }
    ran = {c: artifact_present[c] or c in found_categories for c in _EXPECTED_CATEGORIES}
    categories_ran = [c for c in _EXPECTED_CATEGORIES if ran[c]]
    categories_not_run = [c for c in _EXPECTED_CATEGORIES if not ran[c]]
    return CheckCoverage(
        checks_expected=len(_EXPECTED_CATEGORIES),
        checks_ran=len(categories_ran),
        not_examined=[c.value for c in categories_not_run],
        categories_ran=categories_ran,
        categories_not_run=categories_not_run,
    )
