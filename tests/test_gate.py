"""Tests for the deterministic gate: parsing, rules, aggregation, and the stub.

These run fully offline (no API). They pin the demo scenario so a regression in
the rule engine is caught before it reaches the dashboard.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeguard import DEFAULT_RUNBOOK, Verdict, evaluate_run, load_run, run_gate
from pipeguard.metrics import default_registry
from pipeguard.models import (
    Category,
    Evidence,
    Finding,
    Gate,
    QCMetrics,
    Severity,
    SourceKind,
)
from pipeguard.parsers import parse_sample_sheet
from pipeguard.provenance import EventLedger, EventType
from pipeguard.rules import _evaluate_metric
from pipeguard.synthesis import StubSynthesizer, aggregate_verdict

DATA = Path(__file__).resolve().parent.parent / "data" / "mock_run_01"


def _q30_mv(raw_percent: float):
    """A qc.q30 MetricValue at a raw percent value (normalized to a fraction by the registry)."""
    return default_registry().observe(
        metric_key="qc.q30", raw_value=raw_percent, raw_unit="percent", sample_id="SX"
    )


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
    finding = _evaluate_metric("SX", threshold, _q30_mv(60.0))  # 60% -> 0.60 < hard_fail 0.75
    assert finding is not None
    assert finding.severity.value == "critical"
    assert finding.suggested_verdict is Verdict.RERUN


def test_metric_pass_returns_none():
    threshold = DEFAULT_RUNBOOK.threshold_for("q30")
    assert _evaluate_metric("SX", threshold, _q30_mv(95.0)) is None  # 95% -> 0.95 >= gate 0.85


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
    assert s4.confidence is None  # confidence omitted until grounded (T-019)
    assert s4.findings  # findings carried onto the card
    assert s4.next_steps


def test_hard_fail_sample_reruns():
    """A synthetic hard QC failure should aggregate to RERUN."""
    art = load_run(DATA)
    # Corrupt S2's Q30 below the hard-fail floor.
    art.qc = [q if q.sample_id != "S2" else QCMetrics(sample_id="S2", q30=60.0) for q in art.qc]
    cards = {c.sample_id: c for c in run_gate(art, synthesizer=StubSynthesizer())}
    assert cards["S2"].verdict is Verdict.RERUN


def test_sample_sheet_tolerates_short_rows(tmp_path: Path) -> None:
    """A row with fewer cells than the header is a data signal (missing fields
    become None), not a zip length crash — guards the tolerant strict=False in
    parse_sample_sheet. A row with a blank sample_id is skipped entirely.
    """
    sheet = tmp_path / "SampleSheet.csv"
    sheet.write_text(
        "[BCLConvert_Data]\n"
        "sample_id,index\n"
        "S1,ACGTACGT\n"
        "S2\n"  # short row: sample_id present, index cell missing
        ",TTTTTTTT\n"  # blank sample_id: dropped
    )
    by_id = {e.sample_id: e for e in parse_sample_sheet(sheet)}
    assert set(by_id) == {"S1", "S2"}  # blank-id row skipped, short row kept
    assert by_id["S2"].index is None  # missing trailing cell -> None, no crash
    assert by_id["S1"].index == "ACGTACGT"


def test_finding_gate_is_derived_from_category(findings):
    """Each finding is labeled with the gate that owns its category (ADR-0013)."""
    s5_qc = [f for f in findings["S5"] if f.category is Category.QC]
    assert s5_qc and all(f.gate is Gate.QC for f in s5_qc)
    # Barcode (provenance) and missing metadata are BOTH caught at preflight, per
    # qc_metrics.md's gate table — before the sample enters the queue.
    s4_prov = [f for f in findings["S4"] if f.category is Category.PROVENANCE]
    assert s4_prov and all(f.gate is Gate.PREFLIGHT for f in s4_prov)
    s4_meta = [f for f in findings["S4"] if f.category is Category.METADATA]
    assert s4_meta and all(f.gate is Gate.PREFLIGHT for f in s4_meta)


def test_card_exposes_per_gate_results():
    """The card derives a per-gate breakdown from its findings."""
    cards = {c.sample_id: c for c in run_gate(load_run(DATA), synthesizer=StubSynthesizer())}
    s4 = cards["S4"]
    gates = {gr.gate for gr in s4.gate_results}
    assert Gate.PREFLIGHT in gates  # S4's barcode + metadata findings ride preflight
    assert all(gr.finding_rule_ids for gr in s4.gate_results)


def test_finding_hash_is_identity_but_signature_ignores_rule_version():
    """content_hash includes rule_version; the semantic signature does not."""
    ev = [Evidence(source="qc_metrics.csv", locator="SX.q30", value="60%")]
    base = {
        "rule_id": "QC-Q30",
        "category": Category.QC,
        "severity": Severity.WARN,
        "title": "t",
        "detail": "d",
        "evidence": ev,
        "suggested_verdict": Verdict.HOLD,
    }
    a = Finding(**base)
    b = Finding(**base, rule_version="9.9.9")
    assert a.content_hash == Finding(**base).content_hash  # deterministic
    assert a.content_hash != b.content_hash  # rule_version is part of identity
    assert a.signature == b.signature  # ...but NOT part of the semantic signature


def test_qc_evidence_tagged_as_metric(findings):
    """QC metric evidence carries the METRIC source_kind for the trust layer."""
    q30 = next(f for f in findings["S5"] if f.rule_id == "QC-Q30")
    assert all(e.source_kind is SourceKind.METRIC for e in q30.evidence)


def test_ledger_captures_gate_event_trail():
    """run_gate emits a bracketed provenance trail into the ledger (ADR-0002)."""
    ledger = EventLedger()
    cards = run_gate(load_run(DATA), synthesizer=StubSynthesizer(), ledger=ledger)
    types = [e.event_type for e in ledger.events]
    assert types[0] is EventType.ANALYSIS_RUN_STARTED
    assert types[-1] is EventType.ANALYSIS_RUN_COMPLETED
    assert len(ledger.by_type(EventType.SAMPLE_REGISTERED)) == 5  # one per sample
    assert len(ledger.by_type(EventType.VERDICT_DECIDED)) == len(cards)
    emitted = ledger.by_type(EventType.FINDING_EMITTED)
    assert len(emitted) == 4  # S4: barcode + missing-subject; S5: Q30 + coverage
    # started(1) + registered(5) + findings(4) + verdicts(5) + completed(1) = 16
    assert len(ledger.events) == 1 + 5 + 4 + 5 + 1
    assert any(e.sample_id == "S4" for e in emitted)
    assert all(e.outputs and e.outputs[0].content_hash for e in emitted)  # hashes
    assert all(e.outputs[0].id.startswith("find_") for e in emitted)  # unique finding ids


def test_cards_anchored_to_one_analysis_run():
    """Every card is anchored to the single AnalysisRun for the execution."""
    ledger = EventLedger()
    cards = run_gate(load_run(DATA), synthesizer=StubSynthesizer(), ledger=ledger)
    started = ledger.by_type(EventType.ANALYSIS_RUN_STARTED)
    assert len(started) == 1
    arun_id = started[0].analysis_run_id
    assert arun_id and all(c.analysis_run_id == arun_id for c in cards)


def test_ledger_persists_jsonl(tmp_path: Path):
    """A file-backed ledger writes one JSON line per event (authoritative record)."""
    import json

    path = tmp_path / "ledger.jsonl"
    ledger = EventLedger(path=path)
    run_gate(load_run(DATA), synthesizer=StubSynthesizer(), ledger=ledger)
    lines = path.read_text().strip().splitlines()
    assert len(lines) == len(ledger.events)
    assert json.loads(lines[0])["event_type"] == "analysis_run.started"


def test_findings_carry_sample_id_and_unique_id(findings):
    """Findings are self-describing: sample_id set + a unique find_ id."""
    s4 = findings["S4"]
    assert all(f.sample_id == "S4" for f in s4)
    ids = [f.id for f in s4]
    assert all(i.startswith("find_") for i in ids)
    assert len(set(ids)) == len(ids)  # unique per finding


def test_signature_discriminates_by_sample():
    """The same rule on different samples yields different signatures (no collision)."""
    ev = [Evidence(source="pipeline.log", locator="matched line", value="ERROR")]
    a = Finding(
        rule_id="PIPE-001",
        sample_id="S2",
        category=Category.PIPELINE,
        severity=Severity.CRITICAL,
        title="t",
        detail="d",
        evidence=ev,
        suggested_verdict=Verdict.RERUN,
    )
    b = a.model_copy(update={"sample_id": "S4"})
    assert a.signature != b.signature  # sample_id is part of the semantic signature


def test_finding_is_immutable():
    """Findings are frozen so content_hash is a pinned identity (schemas.md invariant 1)."""
    f = Finding(
        rule_id="X",
        category=Category.QC,
        severity=Severity.WARN,
        title="t",
        detail="d",
        evidence=[],
        suggested_verdict=Verdict.HOLD,
    )
    with pytest.raises(ValidationError):
        f.title = "changed"


def test_card_content_hash_is_stable_and_distinct():
    """Each card's content_hash is a 64-hex identity that differs by sample."""
    cards = {c.sample_id: c for c in run_gate(load_run(DATA), synthesizer=StubSynthesizer())}
    assert len(cards["S4"].content_hash) == 64
    assert cards["S4"].content_hash != cards["S5"].content_hash
