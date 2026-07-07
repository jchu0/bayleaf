"""The deterministic rule engine.

This is the trust anchor of the whole system. It never guesses: it computes hard,
cited `Finding`s from the artifacts and the runbook. The synthesis layer (stub or
Claude) may *narrate* these findings but must not invent numbers or verdicts the
rules didn't produce.

Rule families:
    provenance  - barcode/index mismatch, sample present in some artifacts but not others
    metadata    - required intake fields missing
    qc          - metric vs. runbook gate (borderline WARN vs. hard-fail CRITICAL)
    pipeline    - failure markers in the run log referencing the sample
"""

from __future__ import annotations

from .models import (
    Category,
    Evidence,
    Finding,
    QCMetrics,
    RunArtifacts,
    Sample,
    SampleSheetEntry,
    Severity,
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
        category=Category.METADATA,
        severity=Severity.WARN,
        title="Required intake metadata is missing",
        detail=(
            f"Sample {sid} is missing required field(s): {', '.join(missing)}. "
            f"Incomplete provenance metadata blocks downstream traceability."
        ),
        evidence=[
            Evidence(source="sample_metadata.csv", locator=f"sample_id={sid}", value=f, expected="present")
            for f in missing
        ],
        suggested_verdict=Verdict.HOLD,
    )


def _evaluate_metric(sid: str, threshold: QCThreshold, value: float | None) -> Finding | None:
    if value is None:
        return Finding(
            rule_id=f"QC-{threshold.metric.upper()}-NA",
            category=Category.QC,
            severity=Severity.WARN,
            title=f"{threshold.label} is missing",
            detail=f"No {threshold.label} value was reported for {sid}.",
            evidence=[Evidence(source="qc_metrics.csv", locator=f"{sid}.{threshold.metric}", value="missing")],
            suggested_verdict=Verdict.HOLD,
        )

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
        # Distinguish a true borderline (just past the gate) from a clear miss.
        if threshold.higher_is_better:
            borderline_edge = threshold.gate * (1 - threshold.borderline_band)
            borderline = value >= borderline_edge
        else:
            borderline_edge = threshold.gate * (1 + threshold.borderline_band)
            borderline = value <= borderline_edge
        severity = Severity.WARN
        verdict = Verdict.HOLD
        qualifier = "is borderline against" if borderline else "misses"

    direction = "≥" if threshold.higher_is_better else "≤"
    return Finding(
        rule_id=f"QC-{threshold.metric.upper()}",
        category=Category.QC,
        severity=severity,
        title=f"{threshold.label} {qualifier} the QC gate",
        detail=(
            f"{threshold.label} for {sid} is {value:g}{threshold.unit}; runbook gate is "
            f"{direction} {threshold.gate:g}{threshold.unit} "
            f"(hard-fail {threshold.hard_fail:g}{threshold.unit})."
        ),
        evidence=[
            Evidence(
                source="qc_metrics.csv",
                locator=f"{sid}.{threshold.metric}",
                value=f"{value:g}{threshold.unit}",
                expected=f"{direction} {threshold.gate:g}{threshold.unit}",
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
        category=Category.PIPELINE,
        severity=Severity.CRITICAL,
        title="Pipeline logged a failure for this sample",
        detail=f"The run log contains {len(hits)} failure marker(s) referencing {sid}.",
        evidence=[Evidence(source="pipeline.log", locator="matched line", value=line.strip()) for line in hits[:5]],
        suggested_verdict=Verdict.RERUN,
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
        for threshold in runbook.qc_thresholds:
            metric_finding = _evaluate_metric(sid, threshold, getattr(qc, threshold.metric, None))
            if metric_finding:
                findings.append(metric_finding)

    log_finding = _check_log(sid, artifacts.log_lines, runbook)
    if log_finding:
        findings.append(log_finding)

    return findings


def evaluate_run(
    artifacts: RunArtifacts, runbook: Runbook | None = None
) -> dict[str, list[Finding]]:
    """Run every rule against every sample. Returns findings keyed by sample_id."""
    runbook = runbook or DEFAULT_RUNBOOK
    return {sid: evaluate_sample(sid, artifacts, runbook) for sid in artifacts.sample_ids()}
