"""Per-run UPSTREAM waiver — the declared-absent metric class (FASTQ-start runs).

The maintainer's insight: a HOLD on a missing run-level Illumina/SAV metric (cluster PF) is the gate
WORKING — it refuses to proceed past QC it never examined. But an analysis that legitimately starts
from FASTQ has no upstream sequencer feed, so that absence is EXPECTED, not a gap. The runbook
comment on cluster_pf already named the only honest way past it: "reaching PROCEED means … DECLARING
a runbook exemption (a policy decision), never flipping this flag."

This pins that exemption end to end:
  1. ``Runbook.waive_source_classes`` marks ONLY the declared source class waived (cluster_pf, via
     the registry ``source.module``) — never a hand-picked metric, never a sibling class.
  2. A waived + absent metric emits a VISIBLE INFO "declared absent" note (NOT the NA HOLD, NOT a
     silent drop) and does NOT gate — so verdict flips HOLD → PROCEED while the card stays honest.
  3. ``load_run`` reads the run dir's ``run_policy.json`` into ``waived_metric_sources`` tolerantly
     (a garbled/absent file waives nothing — a policy file can never silently WIDEN a gate).
  4. The driver records the declaration into ``run_policy.json`` for every run (auditable).

Guardrail (ADR-0001): the waiver maps a declared POLICY input onto the runbook; the SAME
deterministic rules still decide. It is not an operator override of a verdict.
"""

from __future__ import annotations

import json
from pathlib import Path

from bayleaf import run_gate
from bayleaf.models import (
    QCMetrics,
    RunArtifacts,
    Sample,
    SampleSheetEntry,
    Severity,
    Verdict,
)
from bayleaf.parsers import _parse_waived_sources
from bayleaf.runbook import DEFAULT_RUNBOOK
from bayleaf.synthesis import StubSynthesizer

_SAV = frozenset({"sav_interop"})


def _reads_only_run(*, waived: frozenset[str], mean_coverage: float = 54.2) -> RunArtifacts:
    """A reads-derived run (real HG002 metric scales) with cluster_pf ABSENT — the structural HOLD a
    FASTQ→BAM path always produces. ``waived`` is the run's declared-absent source-class policy;
    ``mean_coverage`` is a construction-time knob so a caller can build a genuinely-failing run
    without mutating the returned model (each call yields a fresh, independent RunArtifacts)."""
    return RunArtifacts(
        run_id="R",
        sample_sheet=[SampleSheetEntry(sample_id="S1")],
        samples=[
            Sample(
                sample_id="S1",
                subject_id="S1",
                tissue="blood",
                library_prep="wgs",
                submitted_by="t",
            )
        ],
        qc=[
            QCMetrics(
                sample_id="S1",
                q30=88.22,
                reads_passing_filter=99.31,
                mean_coverage=mean_coverage,
                dup_rate=0.0057,
                cluster_pf=None,  # absent — the SAV/InterOp metric a reads-only path can't produce
            )
        ],
        waived_metric_sources=waived,
    )


def _card(art: RunArtifacts):  # type: ignore[no-untyped-def]
    return {c.sample_id: c for c in run_gate(art, synthesizer=StubSynthesizer())}["S1"]


# ── 1. the transform targets ONLY the declared class ─────────────────────────────────────────


def test_waive_source_classes_marks_only_the_sav_class() -> None:
    wb = DEFAULT_RUNBOOK.waive_source_classes(_SAV)
    waived = {t.metric for t in wb.qc_thresholds if t.waived}
    assert waived == {"cluster_pf"}  # the sole SAV/InterOp-sourced threshold, nothing else
    # every other required threshold is untouched (still gates a lean run)
    assert all(not t.waived for t in wb.qc_thresholds if t.metric != "cluster_pf")


def test_waive_source_classes_empty_is_identity() -> None:
    assert DEFAULT_RUNBOOK.waive_source_classes(frozenset()) is DEFAULT_RUNBOOK


def test_waive_unknown_class_waives_nothing() -> None:
    # A policy naming a class no threshold belongs to can never silently drop a real gate.
    wb = DEFAULT_RUNBOOK.waive_source_classes(frozenset({"not_a_real_module"}))
    assert not any(t.waived for t in wb.qc_thresholds)


# ── 2. the gate: HOLD → PROCEED with a VISIBLE note, nothing silently dropped ─────────────────


def test_sequencer_default_still_holds_on_missing_cluster_pf() -> None:
    card = _card(_reads_only_run(waived=frozenset()))
    assert card.verdict is Verdict.HOLD  # unchanged behavior — the honest structural HOLD
    assert any(f.rule_id == "QC-CLUSTER_PF-NA" for f in card.findings)


def test_fastq_only_waiver_proceeds_with_a_visible_declared_absent_note() -> None:
    card = _card(_reads_only_run(waived=_SAV))
    assert card.verdict is Verdict.PROCEED  # the waiver lifts the SAV HOLD
    waived_notes = [f for f in card.findings if f.rule_id == "QC-CLUSTER_PF-WAIVED"]
    assert len(waived_notes) == 1
    note = waived_notes[0]
    assert note.severity is Severity.INFO  # visible, but INFO
    assert note.suggested_verdict is Verdict.PROCEED  # never gates
    assert "declared absent" in note.title.lower()
    # the NA HOLD is REPLACED by the note, not merely suppressed — never a silent drop
    assert not any(f.rule_id == "QC-CLUSTER_PF-NA" for f in card.findings)


def test_waiver_does_not_touch_a_real_failing_metric() -> None:
    # A run that ALSO fails a non-SAV gate still HOLDs/RERUNs — the waiver only excuses the declared
    # class, never a genuine QC failure (the whole point of keeping gates). Built failing at
    # construction (mean_coverage far below the 15x hard-fail), never by mutating a returned model.
    card = _card(_reads_only_run(waived=_SAV, mean_coverage=5.0))
    assert card.verdict is not Verdict.PROCEED
    assert any("COVERAGE" in f.rule_id for f in card.findings)


# ── 3. load_run reads the policy marker tolerantly ────────────────────────────────────────────


def test_load_run_parses_policy_marker(tmp_path: Path) -> None:
    p = tmp_path / "run_policy.json"
    p.write_text(json.dumps({"upstream": "fastq_only", "waived_metric_sources": ["sav_interop"]}))
    assert _parse_waived_sources(p) == _SAV


def test_load_run_policy_is_tolerant(tmp_path: Path) -> None:
    assert _parse_waived_sources(tmp_path / "absent.json") == frozenset()  # absent → nothing waived
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    assert _parse_waived_sources(bad) == frozenset()  # garbled → nothing waived (safe default)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"waived_metric_sources": "sav_interop"}))  # str, not list
    assert _parse_waived_sources(wrong) == frozenset()
