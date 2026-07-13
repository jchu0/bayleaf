"""Tests for the deterministic gate: parsing, rules, aggregation, and the stub.

These run fully offline (no API). They pin the demo scenario so a regression in
the rule engine is caught before it reaches the dashboard.
"""

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeguard import DEFAULT_RUNBOOK, Verdict, evaluate_run, load_run, run_gate
from pipeguard.metrics import default_registry, metric_values_for
from pipeguard.models import (
    Category,
    CheckCoverage,
    Evidence,
    Finding,
    Gate,
    QCMetrics,
    RunArtifacts,
    Sample,
    Severity,
    SourceKind,
)
from pipeguard.parsers import parse_sample_sheet, parse_sample_sheet_header
from pipeguard.provenance import EventLedger, EventType
from pipeguard.rules import _evaluate_metric, compute_check_coverage, evaluate_sample
from pipeguard.runbook import Runbook
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


def test_fraction_metric_display_is_not_100x_too_small():
    """SCI-01 regression. A fraction-raw metric (raw_unit 'fraction', display '%') must render in
    percent, not 100x too small. A failing breadth_20x=0.85 reads '85%' with gate '≥ 90%', never
    '0.85%' / '≥ 0.9%'. Display-only: the verdict still gates on the canonical value (0.85 misses
    the 0.90 gate but clears the 0.80 hard-fail, so it is a WARN — unchanged by the display fix).
    These strings flow into Finding.content_hash/signature, so this pins them."""
    threshold = DEFAULT_RUNBOOK.threshold_for("breadth_20x")
    mv = default_registry().observe(
        metric_key="qc.breadth_20x", raw_value=0.85, raw_unit="fraction", sample_id="SX"
    )
    finding = _evaluate_metric("SX", threshold, mv)
    assert finding is not None
    assert finding.severity is Severity.WARN
    assert finding.detail == "Breadth ≥20x for SX is 85%; runbook gate is ≥ 90% (hard-fail 80%)."
    ev = finding.evidence[0]
    assert ev.value == "85%"
    assert ev.expected == "≥ 90%"
    assert ev.threshold == "hard-fail ≥ 80%"


# ── WS-01 · PR1: fail-closed on missing / expected-but-absent QC ──────────────────


def test_sheet_without_qc_holds():
    """Gap A: a sheet-declared sample with NO QC row emits QC-MISSING and fails closed — absence of
    QC is unverified data, never clean data, so a safety gate cannot PROCEED on it. Exercises the
    real evaluate_sample → _check_presence → aggregate_verdict path."""
    art = load_run(DATA)
    # S1 is on the sheet AND has intake metadata; drop only its QC row → declared-but-not-examined
    # (metadata present so META-002 can't fire — the HOLD is attributable purely to missing QC).
    assert any(e.sample_id == "S1" for e in art.sample_sheet)
    assert any(s.sample_id == "S1" for s in art.samples)
    art.qc = [q for q in art.qc if q.sample_id != "S1"]
    findings = evaluate_sample("S1", art, DEFAULT_RUNBOOK)
    missing = [f for f in findings if f.rule_id == "QC-MISSING"]
    assert len(missing) == 1
    f = missing[0]
    assert f.category is Category.QC and f.severity is Severity.WARN
    assert f.suggested_verdict is Verdict.HOLD
    ev = f.evidence[0]  # self-authored, cites the real source
    assert ev.source == "qc_metrics.csv" and ev.value == "missing" and ev.expected == "present"
    assert ev.source_kind is SourceKind.METRIC
    # I1 + I2: the verdict is exactly aggregate_verdict(findings) and fails closed (not PROCEED).
    assert aggregate_verdict(findings) is Verdict.HOLD
    assert aggregate_verdict(findings) is not Verdict.PROCEED


def test_declared_sample_never_proceeds_without_examined_qc():
    """Gap A guard (freezes the finding): no sheet-declared, QC-less sample maps to PROCEED — and
    and the boundary holds: an intake-only sample (no sheet, no QC) is NOT false-HOLDed."""
    art = load_run(DATA)
    art.qc = []  # strip ALL QC → every sheet-declared sample is now declared-but-unexamined
    for sid in art.sample_ids():
        findings = evaluate_sample(sid, art, DEFAULT_RUNBOOK)
        assert any(f.rule_id == "QC-MISSING" for f in findings), sid
        assert aggregate_verdict(findings) is not Verdict.PROCEED, sid
    # Boundary: a sample ONLY in intake metadata (sheet None, qc None) → no false QC-MISSING.
    intake_only = RunArtifacts(run_id="r", samples=[Sample(sample_id="INTAKE_ONLY")])
    findings = evaluate_sample("INTAKE_ONLY", intake_only, DEFAULT_RUNBOOK)
    assert not any(f.rule_id == "QC-MISSING" for f in findings)


def test_expected_metric_absent_holds():
    """Gap C: a profile that EXPECTS a metric the sample didn't produce emits QC-EXPECTED-* → HOLD,
    restoring the signal a `required=False` threshold would silently drop."""
    art = load_run(DATA)
    book = DEFAULT_RUNBOOK.model_copy(
        update={"expected_metrics": ("qc.breadth_20x",), "pipeline_profile": "germline-panel"}
    )
    # Premise: S1's QC omits breadth_20x (a richer-report metric mock_run_01 doesn't carry).
    s1_qc = next(q for q in art.qc if q.sample_id == "S1")
    assert "qc.breadth_20x" not in {mv.metric_key for mv in metric_values_for(s1_qc)}
    findings = evaluate_sample("S1", art, book)
    exp = [f for f in findings if f.rule_id == "QC-EXPECTED-QC.BREADTH_20X"]
    assert len(exp) == 1
    f = exp[0]
    assert f.severity is Severity.WARN and f.suggested_verdict is Verdict.HOLD
    ev = f.evidence[0]
    assert ev.value == "not examined" and ev.expected == "present"
    assert ev.source_kind is SourceKind.METRIC
    assert aggregate_verdict(findings) is Verdict.HOLD  # I1 + I2


def test_expected_metric_default_runbook_no_finding():
    """Gap C negative (the lean-run guarantee): the SAME clean sample under DEFAULT_RUNBOOK
    (expected_metrics == ()) emits no QC-EXPECTED-* and stays byte-for-byte clean."""
    findings = evaluate_sample("S1", load_run(DATA), DEFAULT_RUNBOOK)
    assert not any(f.rule_id.startswith("QC-EXPECTED") for f in findings)
    assert findings == []  # S1 was clean before this change; still clean


def test_expected_metric_set_leaves_no_silent_skip():
    """Gap C guard: every expected-but-absent key produces exactly one QC-EXPECTED finding (none
    silently vanishes), and DEFAULT_RUNBOOK.expected_metrics is provably empty (default = no-op)."""
    art = load_run(DATA)
    expected = ("qc.breadth_20x", "qc.pct_mapped", "qc.on_target")
    book = DEFAULT_RUNBOOK.model_copy(update={"expected_metrics": expected})
    s1_qc = next(q for q in art.qc if q.sample_id == "S1")
    present = {mv.metric_key for mv in metric_values_for(s1_qc)}
    absent_expected = {k for k in expected if k not in present}
    findings = evaluate_sample("S1", art, book)
    flagged = {
        f.rule_id.removeprefix("QC-EXPECTED-").lower()
        for f in findings
        if f.rule_id.startswith("QC-EXPECTED")
    }
    assert flagged == absent_expected  # no expected-absent key skipped, none invented
    assert DEFAULT_RUNBOOK.expected_metrics == ()  # the default path is provably a no-op


def test_qc_missing_holds_through_the_decision_card():
    """Gap A end-to-end (I1 through the card the product actually serves, not just the reducer
    helper): dropping S1's QC row makes run_gate's DecisionCard for S1 a HOLD, and the card's
    verdict equals aggregate_verdict over the card's own findings — never synthesizer-authored."""
    art = load_run(DATA)
    art.qc = [q for q in art.qc if q.sample_id != "S1"]
    cards = {c.sample_id: c for c in run_gate(art, synthesizer=StubSynthesizer())}
    s1 = cards["S1"]
    assert any(f.rule_id == "QC-MISSING" for f in s1.findings)
    assert s1.verdict is Verdict.HOLD
    assert s1.verdict is aggregate_verdict(s1.findings)  # verdict == reducer over card findings


def test_expected_metrics_rejects_unproducible_key():
    """WS-01 hardening (from adversarial review): a profile that expects a metric the parse layer
    cannot produce fails LOUD at Runbook construction — never a per-sample, unclearable
    HOLD. Producible keys are accepted and de-duped. (pydantic validates on construction; note
    `model_copy(update=)` deliberately skips validation, so profile builders must construct.)"""
    with pytest.raises(ValidationError):
        Runbook(expected_metrics=("contamination.freemix",))  # registered but no wired parser
    with pytest.raises(ValidationError):
        Runbook(expected_metrics=("qc.brdth_20x",))  # a typo can't become a run-wide HOLD
    book = Runbook(expected_metrics=("qc.breadth_20x", "qc.breadth_20x", "qc.pct_mapped"))
    assert book.expected_metrics == ("qc.breadth_20x", "qc.pct_mapped")  # producible + de-duped


def test_hg002_committed_run_has_no_spurious_qc_missing():
    """WS-01 Gap A real-data leg (offline against the committed HG002 fixture): HG002 carries a real
    QC row, so QC-MISSING must NOT fire — the new rule neither masks nor duplicates HG002's existing
    honest cluster_pf HOLD (a reads-only path can't produce the run-level %PF metric)."""
    run_dir = DATA.parent / "RUN-2026-07-08-GIAB-HG002"
    findings = evaluate_run(load_run(run_dir), DEFAULT_RUNBOOK)["HG002"]
    assert not any(f.rule_id == "QC-MISSING" for f in findings)  # QC present → no missing-QC HOLD
    # …the existing structural cluster_pf NA-HOLD is retained, unchanged by WS-01.
    assert any(f.rule_id == "QC-CLUSTER_PF-NA" for f in findings)
    assert aggregate_verdict(findings) is Verdict.HOLD


# ── WS-01 · PR2: CheckCoverage + honest "N ran / M not examined" prose ─────────────


def test_compute_check_coverage_marks_uncovered_categories():
    """WS-01 Gap D: contamination + identity have no parser → always reported NOT examined (never
    silently omitted); a clean sample's ran-count is < expected; the labels name them. A clean QC
    gate that ran finding-less STILL counts as ran (the gateRan fix — ran != produced a finding)."""
    art = load_run(DATA)
    findings = evaluate_sample("S1", art, DEFAULT_RUNBOOK)  # S1 is clean (no findings)
    assert findings == []
    cov = compute_check_coverage("S1", art, DEFAULT_RUNBOOK, findings)
    assert {Category.CONTAMINATION, Category.IDENTITY} <= set(cov.categories_not_run)
    assert cov.checks_ran < cov.checks_expected
    assert "contamination" in cov.not_examined and "identity" in cov.not_examined
    assert Category.QC in cov.categories_ran  # a clean gate RAN even with no QC finding
    assert cov.checks_ran == len(cov.categories_ran)
    assert cov.checks_expected == len(cov.categories_ran) + len(cov.categories_not_run)


def test_empty_findings_prose_states_coverage_not_all_passed():
    """WS-01 Gap B: a clean card's prose states coverage ('N/M categories ran; … not examined'),
    NEVER 'all checks passed', and carries the real CheckCoverage. The verdict stays PROCEED — a
    narration change only (I1)."""
    s1 = {c.sample_id: c for c in run_gate(load_run(DATA), synthesizer=StubSynthesizer())}["S1"]
    assert s1.verdict is Verdict.PROCEED
    blob = (s1.headline + " " + s1.rationale).lower()
    for banned in ("all checks passed", "cleared every", "no inconsistencies were found"):
        assert banned not in blob
    assert s1.check_coverage is not None
    assert f"{s1.check_coverage.checks_ran}/{s1.check_coverage.checks_expected}" in s1.headline
    assert "not examined" in s1.rationale.lower() and s1.check_coverage.not_examined


def test_no_card_claims_all_checks_passed_when_a_category_not_run():
    """WS-01 Gap B guard: over the whole demo run, no card's prose asserts blanket clearance while a
    category was NOT examined, and the denominator is honest (expected == ran + not_run, and
    contamination/identity are not-run on every card today)."""
    for c in run_gate(load_run(DATA), synthesizer=StubSynthesizer()):
        cov = c.check_coverage
        assert cov is not None
        assert cov.checks_expected == len(cov.categories_ran) + len(cov.categories_not_run)
        assert {Category.CONTAMINATION, Category.IDENTITY} <= set(cov.categories_not_run)
        blob = (c.headline + " " + c.rationale).lower()
        if cov.not_examined:
            for banned in ("all checks passed", "cleared every", "no inconsistencies were found"):
                assert banned not in blob, c.sample_id


def test_check_coverage_excluded_from_content_hash():
    """WS-01 cross-gap invariant (I3): CheckCoverage is contextual metadata (like metric_values) —
    NOT in content_hash and never changes the verdict. Attaching/detaching leaves the hash
    byte-identical, and it round-trips through model_dump(mode='json')."""
    s1 = {c.sample_id: c for c in run_gate(load_run(DATA), synthesizer=StubSynthesizer())}["S1"]
    assert isinstance(s1.check_coverage, CheckCoverage)
    detached = s1.model_copy(update={"check_coverage": None})
    assert s1.content_hash == detached.content_hash  # un-hashed
    assert s1.verdict is detached.verdict  # verdict-neutral
    dumped = s1.model_dump(mode="json")  # survives JSON serialization (API/ML, ADR-0007)
    assert dumped["check_coverage"]["checks_expected"] == s1.check_coverage.checks_expected


# ── WS-06 metric correctness (source/label honesty; Gaps 4 & 5) ────────────────────


def test_mean_coverage_source_is_honest():
    """WS-06 §9b: the mean-coverage metric names the tool the committed germline pipeline actually
    runs (mosdepth's published summary) — never Picard CollectHsMetrics, which the pipeline never
    invokes. Borrowing a tool's metric name it doesn't produce is dishonest provenance."""
    src = default_registry().entry("qc.mean_target_coverage").source
    assert src.module == "mosdepth" and "picard" not in src.module.lower()
    assert src.source_file == "mosdepth.summary.txt"


def test_driver_computed_metrics_name_their_real_tool():
    """Guard (WS-06 §9b): every metric the committed germline driver actually WRITES (fastp read QC
    + mosdepth coverage/breadth) names the tool that computes it, never Picard CollectHsMetrics (the
    reads-only pipeline never runs Picard). Freezes 'borrowed a metric name from a tool we don't
    run'. (on_target / fold_* stay Picard-sourced — Picard IS their tool; we just don't run it.)"""
    reg = default_registry()
    driver_computed = {
        "qc.q30": "fastp",
        "qc.reads_passing_filter": "fastp",
        "qc.duplication": "fastp",
        "qc.mean_target_coverage": "mosdepth",
        "qc.breadth_20x": "mosdepth",
        "qc.breadth_30x": "mosdepth",
    }
    for our_key, tool in driver_computed.items():
        module = reg.entry(our_key).source.module
        assert module == tool, f"{our_key} claims {module!r}, driver computes it with {tool}"
        assert "picard" not in module.lower()


def test_reads_passing_filter_label_is_not_a_demux_concept():
    """WS-06 §9c: the qc.reads_passing_filter threshold renders 'Reads passing filter' (fastp's
    survival metric, matching the registry display_name), never '% reads identified' (a demux
    concept it is not). The label flows into finding title/detail/content_hash, so this pins it."""
    threshold = DEFAULT_RUNBOOK.threshold_for("pct_reads_identified")
    assert threshold is not None and threshold.label == "Reads passing filter"
    mv = default_registry().observe(
        metric_key="qc.reads_passing_filter", raw_value=60.0, raw_unit="percent", sample_id="SX"
    )
    finding = _evaluate_metric("SX", threshold, mv)  # 60% < gate 70% -> a WARN finding
    assert finding is not None and "Reads passing filter" in finding.title
    blob = (finding.title + finding.detail + " ".join(e.value for e in finding.evidence)).lower()
    assert "reads identified" not in blob


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
    # The stub fabricates NO next_steps (WS-07 Q1): the honest AI-off fallback points the operator
    # at the real QC artifacts (reports + metric readout, surfaced by api/card_readout.py), never
    # boilerplate advice. Real next_steps only exist on the live Claude path. See
    # tests/test_stub_next_steps.py for the full anti-boilerplate guard.
    assert s4.next_steps == []


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


def test_sample_sheet_header_parses_platform_date_and_run_name():
    """The [Header] block yields the run's platform / raw ISO date / run name, and
    the parsed values are threaded onto RunArtifacts by load_run."""
    header = parse_sample_sheet_header(DATA / "SampleSheet.csv")
    assert header.platform == "NovaSeq"
    assert header.run_date == "2026-07-07"  # kept as the raw string, not a datetime
    assert header.run_name == "RUN-2026-07-07-A"
    # load_run threads the same values onto the model the API/frontend consume.
    art = load_run(DATA)
    assert art.platform == "NovaSeq"
    assert art.run_date == "2026-07-07"
    assert art.run_name == "RUN-2026-07-07-A"


def test_sample_sheet_header_missing_keys_are_none_not_a_crash(tmp_path: Path) -> None:
    """Missing [Header] rows -> None (a missing field is a signal), and a sheet with no
    [Header] section at all still parses without raising."""
    partial = tmp_path / "SampleSheet.csv"
    partial.write_text(
        "[Header]\n"
        "FileFormatVersion,2\n"
        "InstrumentPlatform,MiSeq\n"  # only the platform is present
        "\n"
        "[BCLConvert_Data]\n"
        "Sample_ID,index\n"
        "S1,ACGTACGT\n"
    )
    header = parse_sample_sheet_header(partial)
    assert header.platform == "MiSeq"
    assert header.run_date is None and header.run_name is None

    headerless = tmp_path / "NoHeader.csv"
    headerless.write_text("[BCLConvert_Data]\nSample_ID,index\nS1,ACGTACGT\n")
    assert parse_sample_sheet_header(headerless) == (None, None, None)


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


def test_card_carries_registry_normalized_metric_values():
    """The gate surfaces the registry-normalized QC metrics on the card (T-025 step 4).

    S5's raw QC row (q30=84.1%, mean_coverage=29.2x, ...) is normalized through the
    registry — percent rates become fractions; coverage stays x — and attached, each
    anchored to the same AnalysisRun as the card.
    """
    cards = {c.sample_id: c for c in run_gate(load_run(DATA), synthesizer=StubSynthesizer())}
    s5 = cards["S5"]
    by_key = {mv.metric_key: mv for mv in s5.metric_values}
    assert math.isclose(by_key["qc.q30"].normalized_value, 0.841)  # 84.1% -> fraction
    assert math.isclose(by_key["qc.mean_target_coverage"].normalized_value, 29.2)  # x stays x
    assert by_key["qc.duplication"].raw_value == 22.6  # raw kept alongside for audit
    assert all(mv.analysis_run_id == s5.analysis_run_id for mv in s5.metric_values)


def test_metric_values_are_not_in_content_hash():
    """metric_values is contextual metadata (like run_id) — NOT part of card identity.

    Proves the demo stays byte-identical: attaching or clearing metric_values must not
    move the content_hash the pinned tests (16 events / verdicts / hashes) depend on.
    """
    s5 = {c.sample_id: c for c in run_gate(load_run(DATA), synthesizer=StubSynthesizer())}["S5"]
    assert s5.metric_values  # populated on this run
    assert s5.content_hash == s5.model_copy(update={"metric_values": []}).content_hash


def test_card_metric_values_round_trip_json():
    """metric_values survives model_dump(mode='json') — API/ML serialization (ADR-0007)."""
    s5 = {c.sample_id: c for c in run_gate(load_run(DATA), synthesizer=StubSynthesizer())}["S5"]
    dumped = s5.model_dump(mode="json")
    by_key = {mv["metric_key"]: mv for mv in dumped["metric_values"]}
    assert by_key["qc.q30"]["normalized_value"] == 0.841
    assert by_key["qc.q30"]["canonical_unit"] == "fraction"
