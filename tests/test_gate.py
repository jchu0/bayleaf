"""Tests for the deterministic gate: parsing, rules, aggregation, and the stub.

These run fully offline (no API). They pin the demo scenario so a regression in
the rule engine is caught before it reaches the dashboard.
"""

from pathlib import Path

import pytest

from pipeguard import DEFAULT_RUNBOOK, Verdict, evaluate_run, load_run, run_gate
from pipeguard.models import QCMetrics
from pipeguard.rules import _evaluate_metric
from pipeguard.synthesis import StubSynthesizer, aggregate_verdict

DATA = Path(__file__).resolve().parent.parent / "data" / "mock_run_01"


@pytest.fixture(scope="module")
def artifacts():
    return load_run(DATA)


@pytest.fixture(scope="module")
def findings(artifacts):
    return evaluate_run(artifacts, DEFAULT_RUNBOOK)


def test_all_samples_parsed(artifacts):
    assert set(artifacts.sample_ids()) == {"S1", "S2", "S3", "S4", "S5"}
    assert len(artifacts.qc) == 5
    assert len(artifacts.sample_sheet) == 5
    assert artifacts.log_lines  # log parsed


def test_clean_samples_have_no_findings(findings):
    for sid in ("S1", "S2", "S3"):
        assert findings[sid] == [], f"{sid} should be clean"


def test_s4_barcode_mismatch_is_critical_provenance(findings):
    prov = [f for f in findings["S4"] if f.rule_id == "PROV-001"]
    assert len(prov) == 1
    f = prov[0]
    assert f.severity.value == "critical"
    assert f.suggested_verdict is Verdict.ESCALATE
    # Evidence must cite both the declared and observed barcodes.
    sources = {e.source for e in f.evidence}
    assert {"SampleSheet.csv", "demux_stats.csv"} <= sources


def test_s4_missing_subject_id_flagged(findings):
    meta = [f for f in findings["S4"] if f.rule_id == "META-001"]
    assert len(meta) == 1
    assert "subject_id" in meta[0].detail


def test_s5_borderline_qc_only_warnings(findings):
    s5 = findings["S5"]
    assert s5, "S5 should have findings"
    assert all(f.severity.value == "warn" for f in s5)
    metrics_flagged = {f.rule_id for f in s5}
    assert "QC-Q30" in metrics_flagged
    assert "QC-MEAN_COVERAGE" in metrics_flagged


def test_verdict_aggregation_precedence(findings):
    assert aggregate_verdict(findings["S1"]) is Verdict.PROCEED
    assert aggregate_verdict(findings["S4"]) is Verdict.ESCALATE  # critical prov wins
    assert aggregate_verdict(findings["S5"]) is Verdict.HOLD


def test_metric_hard_fail_is_rerun():
    threshold = DEFAULT_RUNBOOK.threshold_for("q30")
    finding = _evaluate_metric("SX", threshold, 60.0)  # below hard_fail 75
    assert finding is not None
    assert finding.severity.value == "critical"
    assert finding.suggested_verdict is Verdict.RERUN


def test_metric_pass_returns_none():
    threshold = DEFAULT_RUNBOOK.threshold_for("q30")
    assert _evaluate_metric("SX", threshold, 95.0) is None


def test_missing_metric_flagged():
    threshold = DEFAULT_RUNBOOK.threshold_for("mean_coverage")
    finding = _evaluate_metric("SX", threshold, None)
    assert finding is not None and finding.severity.value == "warn"


def test_run_gate_orders_urgent_first():
    cards = run_gate(load_run(DATA), synthesizer=StubSynthesizer())
    verdicts = [c.verdict for c in cards]
    # ESCALATE (S4) must come before HOLD (S5), which comes before PROCEED.
    assert verdicts[0] is Verdict.ESCALATE
    assert verdicts[1] is Verdict.HOLD
    assert all(v is Verdict.PROCEED for v in verdicts[2:])


def test_stub_card_is_grounded():
    cards = run_gate(load_run(DATA), synthesizer=StubSynthesizer())
    by_id = {c.sample_id: c for c in cards}
    s4 = by_id["S4"]
    assert s4.generated_by == "stub"
    assert 0.0 <= s4.confidence <= 1.0
    assert s4.findings  # findings carried onto the card
    assert s4.next_steps


def test_hard_fail_sample_reruns():
    """A synthetic hard QC failure should aggregate to RERUN."""
    art = load_run(DATA)
    # Corrupt S2's Q30 below the hard-fail floor.
    art.qc = [q if q.sample_id != "S2" else QCMetrics(sample_id="S2", q30=60.0) for q in art.qc]
    cards = {c.sample_id: c for c in run_gate(art, synthesizer=StubSynthesizer())}
    assert cards["S2"].verdict is Verdict.RERUN
