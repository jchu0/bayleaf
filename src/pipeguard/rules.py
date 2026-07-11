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

from .metrics import default_registry, metric_values_for
from .models import (
    Category,
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

    # DISPLAY in the operator-facing raw unit (option 2 / schemas.md units contract): the
    # observed value as the tool reported it, and the canonical thresholds rendered back
    # into that same unit so the message reads naturally (e.g. "84.1%; gate >= 85%").
    reg = default_registry()
    disp_gate = reg.denormalize(threshold.our_key, threshold.gate, mv.raw_unit)
    disp_hard = reg.denormalize(threshold.our_key, threshold.hard_fail, mv.raw_unit)
    direction = "≥" if threshold.higher_is_better else "≤"
    return Finding(
        rule_id=f"QC-{threshold.metric.upper()}",
        sample_id=sid,
        category=Category.QC,
        severity=severity,
        title=f"{threshold.label} {qualifier} the QC gate",
        detail=(
            f"{threshold.label} for {sid} is {mv.raw_value:g}{threshold.unit}; runbook gate is "
            f"{direction} {disp_gate:g}{threshold.unit} "
            f"(hard-fail {disp_hard:g}{threshold.unit})."
        ),
        evidence=[
            Evidence(
                source="qc_metrics.csv",
                locator=f"{sid}.{threshold.metric}",
                value=f"{mv.raw_value:g}{threshold.unit}",
                expected=f"{direction} {disp_gate:g}{threshold.unit}",
                source_kind=SourceKind.METRIC,
                source_field=threshold.metric,
                threshold=f"hard-fail {direction} {disp_hard:g}{threshold.unit}",
            )
        ],
        suggested_verdict=verdict,
    )


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
