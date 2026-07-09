"""Tests for the decision-card QC readout projection (api/card_readout.py).

This is a PURE projection over an already-decided card (ADR-0001): it re-presents metrics the
deterministic gate already emitted and must never contradict them. The tests drive it against a
real card from `data/mock_run_01` (loaded via `run_gate_from_dir`) plus the default runbook, and
exercise the optional HTTP side-channel IN ISOLATION — a local FastAPI app with only this router
mounted, so nothing here depends on api/main.py.
"""

from __future__ import annotations

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
from pipeguard.models import CanonicalUnit, Gate, MetricValue, Verdict

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
