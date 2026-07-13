"""Tests for the decision-card QC readout projection (api/card_readout.py).

This is a PURE projection over an already-decided card (ADR-0001): it re-presents metrics the
deterministic gate already emitted and must never contradict them. The tests drive it against a
real card from `data/mock_run_01` (loaded via `run_gate_from_dir`) plus the default runbook, and
exercise the optional HTTP side-channel IN ISOLATION — a local FastAPI app with only this router
mounted, so nothing here depends on api/main.py.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.card_readout import (
    CardHeader,
    Direction,
    QcReadout,
    ReadoutStatus,
    build_card_header,
    build_qc_readout,
    router,
)
from pipeguard import DEFAULT_RUNBOOK, DecisionCard, run_gate_from_dir
from pipeguard.models import CanonicalUnit, Gate, MetricValue, Severity, Verdict
from pipeguard.rules import _evaluate_metric

_RUN_DIR = "data/mock_run_01"


def _card(sample_id: str) -> DecisionCard:
    """The real decision card for a sample in the pinned demo run."""
    _, cards = run_gate_from_dir(_RUN_DIR)
    card = next((c for c in cards if c.sample_id == sample_id), None)
    assert card is not None, f"sample {sample_id} not in {_RUN_DIR}"
    return card


# --- The projection against a real card -----------------------------------------------------


def test_readout_covers_every_metric_exactly_once() -> None:
    """No metric value is dropped or duplicated by the join; all land in the QC gate group."""
    card = _card("S5")
    readout = build_qc_readout(card, DEFAULT_RUNBOOK)

    assert isinstance(readout, QcReadout)
    assert readout.sample_id == "S5"
    rows = [row for gate in readout.gates for row in gate.rows]
    assert len(rows) == len(card.metric_values)
    assert {r.metric for r in rows} == {mv.metric_key for mv in card.metric_values}
    # Every mock QC metric belongs to the QC gate, so there is exactly one gate group.
    assert [g.gate for g in readout.gates] == [Gate.QC]


def test_borderline_and_pass_statuses_mirror_the_gate() -> None:
    """S5 is a HOLD: Q30 and coverage miss the gate (borderline), the rest pass. Status, display,
    direction, and the borderline-band flag must all reflect the runbook exactly."""
    card = _card("S5")
    readout = build_qc_readout(card, DEFAULT_RUNBOOK)
    by_metric = {row.metric: row for gate in readout.gates for row in gate.rows}

    q30 = by_metric["qc.q30"]
    assert q30.status is ReadoutStatus.BORDERLINE
    assert q30.direction is Direction.AT_LEAST
    assert q30.observed_display == "84.1%"
    assert q30.threshold_display == ">= 85%"
    assert q30.hard_fail_display == "< 75%"
    assert q30.within_borderline_band is True
    assert q30.flagged is True
    # The canonical value is preserved losslessly alongside the rendered display.
    assert q30.observed_value == 0.841
    assert q30.canonical_unit is CanonicalUnit.FRACTION

    cov = by_metric["qc.mean_target_coverage"]
    assert cov.status is ReadoutStatus.BORDERLINE
    assert cov.observed_display == "29.2x"
    assert cov.threshold_display == ">= 30x"

    reads = by_metric["qc.reads_passing_filter"]
    assert reads.status is ReadoutStatus.PASS
    assert reads.flagged is False

    # A lower-is-better metric flips the direction and the hard-fail side.
    dup = by_metric["qc.duplication"]
    assert dup.status is ReadoutStatus.PASS
    assert dup.direction is Direction.AT_MOST
    assert dup.threshold_display == "<= 30%"
    assert dup.hard_fail_display == "> 50%"


def test_flagged_first_ordering_and_counts() -> None:
    """Within a gate, fail/borderline rows sort ahead of passes; counts add up."""
    card = _card("S5")
    readout = build_qc_readout(card, DEFAULT_RUNBOOK)
    qc_gate = readout.gates[0]

    ranks = [0 if r.flagged else 1 for r in qc_gate.rows]
    assert ranks == sorted(ranks), "flagged rows must come first"
    assert qc_gate.flagged_count == 2  # Q30 + coverage
    assert readout.flagged_count == sum(g.flagged_count for g in readout.gates) == 2


def test_clean_pass_run_has_no_flags() -> None:
    """A PROCEED card projects to all-pass, zero flags — the readout never invents attention."""
    card = _card("S1")
    assert card.verdict is Verdict.PROCEED
    readout = build_qc_readout(card, DEFAULT_RUNBOOK)
    assert readout.flagged_count == 0
    assert all(r.status is ReadoutStatus.PASS for g in readout.gates for r in g.rows)


def test_readout_default_runbook_when_omitted() -> None:
    """Omitting the runbook falls back to DEFAULT_RUNBOOK (same result)."""
    card = _card("S5")
    default = build_qc_readout(card).model_dump()
    explicit = build_qc_readout(card, DEFAULT_RUNBOOK).model_dump()
    assert default == explicit


# --- Synthetic cards for the hard-fail and ungated branches ---------------------------------


def _metric(key: str, value: float, unit: CanonicalUnit) -> MetricValue:
    """A minimal MetricValue for exercising the projection's join branches."""
    return MetricValue(
        sample_id="SYN",
        metric_key=key,
        gate=Gate.QC,
        raw_value=value,
        raw_unit="fraction",
        normalized_value=value,
        canonical_unit=unit,
        metric_registry_version=1,
    )


def _synthetic_card(*metrics: MetricValue) -> DecisionCard:
    return DecisionCard(
        sample_id="SYN",
        verdict=Verdict.HOLD,
        headline="synthetic",
        rationale="synthetic",
        metric_values=list(metrics),
    )


def test_hard_fail_status() -> None:
    """A value past hard_fail (Q30 0.60 < 0.75) is FAIL, not borderline."""
    card = _synthetic_card(_metric("qc.q30", 0.60, CanonicalUnit.FRACTION))
    row = build_qc_readout(card, DEFAULT_RUNBOOK).gates[0].rows[0]
    assert row.status is ReadoutStatus.FAIL
    assert row.flagged is True
    assert row.within_borderline_band is False
    assert row.observed_display == "60%"


# --- target_band (BOTH-TAILS) thresholds — WS-06 Gap 2 API wiring ---------------------------
#
# The default runbook's `variant.titv` threshold is a `target_band` gate: PASS inside
# [target_low, target_high] = [2.0, 2.1], WARN/HOLD inside the hard band [1.8, 2.8] but outside
# the target (either tail), CRITICAL/RERUN outside the hard band (either tail). The readout must
# PROJECT that both-tails decision — a one-sided `value >= gate` formatter silently reads every
# high-tail value as PASS and renders the Threshold column as a single `>=` comparator.


def _titv_metric(value: float) -> MetricValue:
    """A Ts/Tv ratio MetricValue (canonical `ratio`) for exercising the target_band branch.

    normalized_value is set directly (no registry round-trip), so raw_unit is cosmetic; the
    readout renders from normalized_value + canonical_unit, matching a real observed Ts/Tv."""
    return MetricValue(
        sample_id="SYN",
        metric_key="variant.titv",
        gate=Gate.VARIANT,
        raw_value=value,
        raw_unit="ratio",
        normalized_value=value,
        canonical_unit=CanonicalUnit.RATIO,
        metric_registry_version=1,
    )


def test_target_band_in_band_value_passes_and_shows_the_band() -> None:
    """An in-band Ts/Tv (2.05 ∈ [2.0, 2.1]) is PASS, and the Threshold column shows the BAND
    [2, 2.1] / hard band [1.8, 2.8] — never a single one-sided `>= 2` comparator."""
    row = build_qc_readout(_synthetic_card(_titv_metric(2.05)), DEFAULT_RUNBOOK).gates[0].rows[0]
    assert row.metric == "variant.titv"
    assert row.status is ReadoutStatus.PASS
    assert row.flagged is False
    assert row.observed_display == "2.05"
    assert row.threshold_display == "[2, 2.1]"
    assert row.hard_fail_display == "[1.8, 2.8]"
    assert ">=" not in (row.threshold_display or "") and "<=" not in (row.threshold_display or "")
    # A both-tails gate is neither at-least nor at-most — the direction says WITHIN, not a lie.
    assert row.direction.value == "within"


def test_target_band_out_of_target_high_tail_is_flagged_not_pass() -> None:
    """The bug: a Ts/Tv above the target band (2.5, outside [2.0, 2.1] but inside the hard band)
    is a HOLD in the core, so the readout MUST flag it BORDERLINE. A one-sided formatter reads
    2.5 >= gate 2.0 as PASS — the high tail slips through as 'all clear'."""
    row = build_qc_readout(_synthetic_card(_titv_metric(2.5)), DEFAULT_RUNBOOK).gates[0].rows[0]
    assert row.status is ReadoutStatus.BORDERLINE
    assert row.flagged is True
    assert row.threshold_display == "[2, 2.1]"


def test_target_band_outside_hard_high_tail_is_fail() -> None:
    """A Ts/Tv outside the hard band (3.0 > hard_high 2.8) is CRITICAL/RERUN in the core → the
    readout must be FAIL. The one-sided formatter reads 3.0 >= 2.0 as PASS."""
    row = build_qc_readout(_synthetic_card(_titv_metric(3.0)), DEFAULT_RUNBOOK).gates[0].rows[0]
    assert row.status is ReadoutStatus.FAIL
    assert row.flagged is True


def test_target_band_status_projects_the_core_rule_never_re_decides() -> None:
    """Anti-drift guard: for a target_band threshold the readout status is a pure PROJECTION of the
    core rule (`rules._evaluate_metric`), never re-decided in the API (ADR-0001). Sweep the in-band
    value, both out-of-target tails, and both out-of-hard tails; the readout status must equal the
    finding severity mapped None→PASS / WARN→BORDERLINE / CRITICAL→FAIL for every point."""
    threshold = DEFAULT_RUNBOOK.threshold_for("variant_titv")
    assert threshold is not None and threshold.kind == "target_band"
    expected = {
        2.05: ReadoutStatus.PASS,  # inside the target band
        1.85: ReadoutStatus.BORDERLINE,  # out of target, in hard band (low tail)
        2.5: ReadoutStatus.BORDERLINE,  # out of target, in hard band (high tail)
        1.5: ReadoutStatus.FAIL,  # outside the hard band (low tail)
        3.0: ReadoutStatus.FAIL,  # outside the hard band (high tail)
    }
    for value, want in expected.items():
        mv = _titv_metric(value)
        row = build_qc_readout(_synthetic_card(mv), DEFAULT_RUNBOOK).gates[0].rows[0]
        assert row.status is want, f"titv={value}: readout {row.status}, want {want}"
        finding = _evaluate_metric("SYN", threshold, mv)
        core_status = (
            ReadoutStatus.PASS
            if finding is None
            else ReadoutStatus.FAIL
            if finding.severity is Severity.CRITICAL
            else ReadoutStatus.BORDERLINE
        )
        assert row.status is core_status, f"titv={value}: readout must mirror the core rule"


def test_fraction_metric_agrees_with_rules_finding_display() -> None:
    """SCI-01 regression: the QC-readout side-channel and the rules.py finding text must render a
    fraction-raw metric (breadth_20x, raw_unit 'fraction', display '%') the SAME way — as percent,
    not 100x too small. Both surfaces convert normalized_value → the display unit, so a failing
    breadth_20x=0.85 reads '85%' with gate '90%' on both, never '0.85%' / '0.9%'."""
    mv = _metric("qc.breadth_20x", 0.85, CanonicalUnit.FRACTION)  # 0.85 < gate 0.90, > hard 0.80
    row = build_qc_readout(_synthetic_card(mv), DEFAULT_RUNBOOK).gates[0].rows[0]
    assert row.status is ReadoutStatus.BORDERLINE
    assert row.observed_display == "85%"
    assert row.threshold_display == ">= 90%"
    assert row.hard_fail_display == "< 80%"

    # The deterministic rule's finding text must agree with the readout, digit for digit.
    finding = _evaluate_metric("SYN", DEFAULT_RUNBOOK.threshold_for("breadth_20x"), mv)
    assert finding is not None
    assert finding.evidence[0].value == row.observed_display  # both "85%"
    assert "≥ 90%" in finding.detail and "hard-fail 80%" in finding.detail


def test_ungated_metric_is_marked_not_gated_never_guessed() -> None:
    """A metric with no runbook threshold is surfaced (not dropped) as not_gated / UNKNOWN."""
    card = _synthetic_card(_metric("qc.made_up_metric", 0.5, CanonicalUnit.FRACTION))
    row = build_qc_readout(card, DEFAULT_RUNBOOK).gates[0].rows[0]
    assert row.status is ReadoutStatus.NOT_GATED
    assert row.direction is Direction.UNKNOWN
    assert row.threshold_display is None
    assert row.hard_fail_display is None
    assert row.flagged is False
    # The observed value is still shown honestly, in its canonical form.
    assert row.observed_value == 0.5


def test_empty_metrics_yields_empty_readout() -> None:
    """A card with no metric values projects to an empty (but valid) readout — no crash."""
    readout = build_qc_readout(_synthetic_card(), DEFAULT_RUNBOOK)
    assert readout.gates == []
    assert readout.flagged_count == 0


# --- The header helper ----------------------------------------------------------------------


def test_header_surfaces_injected_context() -> None:
    """Given server-resolved origin + sample, the header carries sample-type/origin, nothing
    marked not-captured."""
    _, cards = run_gate_from_dir(_RUN_DIR)
    arts, _ = run_gate_from_dir(_RUN_DIR)
    card = next(c for c in cards if c.sample_id == "S5")
    sample = next(s for s in arts.samples if s.sample_id == "S5")

    header = build_card_header(card, origin="contrived", sample=sample)
    assert isinstance(header, CardHeader)
    assert header.sample_id == "S5"
    assert header.run_id == "mock_run_01"
    assert header.origin == "contrived"
    assert header.sample_type == sample.tissue
    assert header.not_captured == []


def test_header_marks_missing_context_never_fabricates() -> None:
    """Absent origin + sample, those fields are None and named in not_captured — not invented."""
    card = _card("S5")
    header = build_card_header(card)  # no origin, no sample
    assert header.origin is None
    assert header.sample_type is None
    assert header.library_prep is None
    assert set(header.not_captured) == {"origin", "sample_type", "library_prep"}
    # What IS on the card is still surfaced honestly.
    assert header.verdict is card.verdict
    assert header.generated_by == card.generated_by


# --- The HTTP side-channel, mounted in ISOLATION (no api/main.py) ---------------------------


def _client() -> TestClient:
    """A FastAPI app carrying ONLY this router — proves the router is self-contained."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_router_returns_header_and_readout() -> None:
    client = _client()
    resp = client.get("/api/runs/mock_run_01/cards/S5/qc-readout")
    assert resp.status_code == 200
    body = resp.json()
    assert body["header"]["sample_id"] == "S5"
    # Origin is resolvable server-side from the run's marker file.
    assert body["header"]["origin"] == "contrived"
    assert body["readout"]["sample_id"] == "S5"
    assert body["readout"]["flagged_count"] == 2


def test_router_404s_on_unknown_run_and_sample() -> None:
    client = _client()
    assert client.get("/api/runs/no_such_run/cards/S5/qc-readout").status_code == 404
    assert client.get("/api/runs/mock_run_01/cards/NOPE/qc-readout").status_code == 404


# --- Gate dependency: an unclear upstream gate blocks its downstream ones --------------------
def test_qc_hold_blocks_the_downstream_variant_gate() -> None:
    """Maintainer's two-tier gate model: sample-tier QC gates downstream analysis. A sample whose
    QC gate isn't clear reads its Variant gate as blocked-by-qc (not 'all clear'); a fully clear
    sample blocks nothing. Pure re-presentation — the verdict already reflects the QC finding."""
    _, cards = run_gate_from_dir("data/mock_run_02")
    qc_unclear = next(
        c
        for c in cards
        if any(gr.gate is Gate.QC and gr.verdict is not Verdict.PROCEED for gr in c.gate_results)
    )
    readout = build_qc_readout(qc_unclear)
    variant = next(g for g in readout.gates if g.gate is Gate.VARIANT)
    assert variant.blocked_by is Gate.QC
    # The blocking gate itself, and anything upstream of it, is not blocked.
    for g in readout.gates:
        if g.gate in (Gate.PREFLIGHT, Gate.QC):
            assert g.blocked_by is None

    clear = next(c for c in cards if not c.gate_results)  # no findings ⇒ every gate clear
    assert all(g.blocked_by is None for g in build_qc_readout(clear).gates)


# --- QC-report artifact surfacing (WS-07 Q1) ------------------------------------------------
#
# The AI-off default (the stub) fabricates no next_steps; instead the readout points the operator
# at the REAL QC artifacts — the run's fastp.html / multiqc_report.html reports if present on disk,
# always alongside the metric readout. A run with no HTML report (mock_run_01, CSVs only) reports
# that absence honestly (empty ``qc_reports``) — never boilerplate advice.


def _run_dir_with_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Copy the pinned mock_run_01 into a tmp data root and drop the named HTML reports beside its
    CSVs, then repoint ``PIPEGUARD_DATA_ROOT`` at it. The endpoint re-derives the card from this
    copy and scans it for QC reports — nothing runs Nextflow."""
    dst = tmp_path / "mock_run_01"
    shutil.copytree(_RUN_DIR, dst)
    for name in names:
        (dst / name).write_text("<html>fake QC report</html>", encoding="utf-8")
    monkeypatch.setenv("PIPEGUARD_DATA_ROOT", str(tmp_path))


def test_qc_reports_surfaced_when_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When the run dir carries QC HTML reports, the readout links each one to the read-only
    artifact-serve endpoint — the sample-scoped fastp report AND the run-level MultiQC report,
    while the metric readout is still fully populated (the fallback is reports + readout)."""
    _run_dir_with_reports(tmp_path, monkeypatch, "S5.fastp.html", "multiqc_report.html")
    body = _client().get("/api/runs/mock_run_01/cards/S5/qc-readout").json()

    reports = body["qc_reports"]
    by_name = {r["name"]: r for r in reports}
    assert set(by_name) == {"S5.fastp.html", "multiqc_report.html"}
    # Links resolve to the existing inline artifact-serve endpoint (real, followable).
    assert by_name["S5.fastp.html"]["url"] == "/api/runs/mock_run_01/artifacts/S5.fastp.html"
    assert by_name["S5.fastp.html"]["scope"] == "sample"
    assert by_name["multiqc_report.html"]["scope"] == "run"
    # The metric readout is still there — reports AUGMENT it, never replace it.
    assert body["readout"]["flagged_count"] == 2


def test_qc_reports_exclude_a_different_samples_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A per-sample report belonging to ANOTHER sample must not leak onto this card; the run-level
    report still surfaces."""
    _run_dir_with_reports(tmp_path, monkeypatch, "S4.fastp.html", "multiqc_report.html")
    body = _client().get("/api/runs/mock_run_01/cards/S5/qc-readout").json()
    names = {r["name"] for r in body["qc_reports"]}
    assert names == {"multiqc_report.html"}  # S4's fastp report is excluded from S5's card


def test_qc_reports_absent_is_honest_for_mock_run_01() -> None:
    """The pinned mock_run_01 has only CSVs — no HTML report. The endpoint reports that absence
    honestly (empty ``qc_reports``) and the metric readout still stands (never boilerplate)."""
    body = _client().get("/api/runs/mock_run_01/cards/S5/qc-readout").json()
    assert body["qc_reports"] == []
    assert body["readout"]["flagged_count"] == 2  # the real fallback: the metric readout
