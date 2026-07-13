"""WS-05 — multi-dimensional ``RunbookSet`` + per-sample profile resolution.

Test-first (RED before impl). These freeze the four contracts the workstream owes:

1. ``RunbookSet.resolve`` selects the ``germline-panel`` profile for a panel sample and the
   ``default`` profile for every other sample (pure function of sample metadata + the set).
2. **The WS-01 loop closes.** ``Runbook.expected_metrics`` was shipped as a *mechanism* with no
   deployed consumer (nothing set it). The ``germline-panel`` profile is that consumer: a panel
   sample whose QC omits ``qc.breadth_20x``/``qc.breadth_30x`` now HOLDs on ``QC-EXPECTED`` —
   proof the mechanism has a real production wiring.
3. **Byte-identical demo.** The pinned ``data/mock_run_01`` scenario yields the SAME verdicts on
   the plain-``Runbook`` path AND with ``DEFAULT_RUNBOOK_SET`` resolving every mock sample to the
   default profile (S1-S3 proceed, S4 escalate, S5 hold).
4. A ``RunbookSet`` built with a bogus/unproducible ``expected_metrics`` key still fails loud (the
   WS-01 producible-key validator).

Invariant (ADR-0001): the verdict stays a pure function of findings via ``aggregate_verdict`` — the
set only SELECTS a threshold/expected profile per sample, it never authors a verdict.
"""

from __future__ import annotations

import pytest

from bayleaf import Verdict, evaluate_run, load_run, run_gate
from bayleaf.models import QCMetrics, RunArtifacts, Sample, SampleSheetEntry
from bayleaf.runbook import (
    DEFAULT_RUNBOOK,
    DEFAULT_RUNBOOK_SET,
    GERMLINE_PANEL_RUNBOOK,
    Runbook,
    RunbookKey,
    RunbookProfile,
    RunbookSet,
)
from bayleaf.synthesis import aggregate_verdict

DATA = "data/mock_run_01"


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────
def _panel_sample(sid: str = "P1", tissue: str = "blood") -> Sample:
    """A germline-panel sample: assay declared via `extra['assay']` (the explicit opt-in seam)."""
    return Sample(
        sample_id=sid,
        subject_id=f"SUBJ-{sid}",
        tissue=tissue,
        library_prep="germline-panel",
        submitted_by="op",
        extra={"assay": "germline-panel"},
    )


def _plain_sample(sid: str = "B1", tissue: str = "blood") -> Sample:
    """A non-panel sample — no germline-panel assay, so it resolves to the default profile."""
    return Sample(
        sample_id=sid,
        subject_id=f"SUBJ-{sid}",
        tissue=tissue,
        library_prep="TruSeq DNA PCR-Free",
        submitted_by="op",
    )


def _panel_run(sid: str = "P1") -> RunArtifacts:
    """A one-sample panel run: complete metadata + passing frozen-five QC, breadth OMITTED.

    With the germline-panel profile the ONLY findings are the two ``QC-EXPECTED`` HOLDs, so the
    verdict flip is unambiguously attributable to ``expected_metrics`` (not a failing gate).
    """
    return RunArtifacts(
        run_id="RUN-PANEL",
        platform="NovaSeq",
        samples=[_panel_sample(sid)],
        sample_sheet=[SampleSheetEntry(sample_id=sid)],  # no index → barcode check is a no-op
        qc=[
            QCMetrics(
                sample_id=sid,
                q30=90.0,  # 0.90 ≥ gate 0.85
                pct_reads_identified=90.0,  # 0.90 ≥ gate 0.70
                mean_coverage=40.0,  # 40 ≥ gate 30
                cluster_pf=90.0,  # 0.90 ≥ gate 0.80
                dup_rate=10.0,  # 0.10 ≤ gate 0.30
                # breadth_20x / breadth_30x deliberately omitted (None)
            )
        ],
    )


# ── Gap A: RunbookSet.resolve selects the right profile ──────────────────────────────────────
def test_resolve_selects_germline_panel_for_panel_sample() -> None:
    rs = DEFAULT_RUNBOOK_SET
    resolved = rs.resolve(_panel_sample(), platform="NovaSeq")
    assert resolved.pipeline_profile == "germline-panel"
    assert resolved.expected_metrics == ("qc.breadth_20x", "qc.breadth_30x")
    # a non-panel sample falls back to the stock default profile
    plain = rs.resolve(_plain_sample(), platform="NovaSeq")
    assert plain.pipeline_profile == "default"
    assert plain.expected_metrics == ()


def test_resolve_matches_assay_from_library_prep_fallback() -> None:
    """assay is read from `extra['assay']` first, then `library_prep` — so a run that carries the
    kit only in `library_prep` still routes to the panel profile."""
    s = Sample(sample_id="LP1", tissue="blood", library_prep="germline-panel", submitted_by="op")
    assert DEFAULT_RUNBOOK_SET.resolve(s).pipeline_profile == "germline-panel"


def test_resolution_precedence_assay_beats_sample_type_beats_platform() -> None:
    """Binary-weight precedence: assay (4) > sample_type (2) > platform (1), a total order."""
    rs = RunbookSet(
        default=DEFAULT_RUNBOOK,
        profiles=[
            RunbookProfile(
                key=RunbookKey(platform="novaseq"), runbook=Runbook(pipeline_profile="by-platform")
            ),
            RunbookProfile(
                key=RunbookKey(sample_type="blood"), runbook=Runbook(pipeline_profile="by-type")
            ),
            RunbookProfile(
                key=RunbookKey(assay="wgs"), runbook=Runbook(pipeline_profile="by-assay")
            ),
        ],
    )
    # all three single-axis profiles match → assay wins
    s = Sample(sample_id="X", tissue="blood", extra={"assay": "wgs"})
    assert rs.resolve(s, platform="NovaSeq").pipeline_profile == "by-assay"
    # drop assay → sample_type beats platform
    s2 = Sample(sample_id="Y", tissue="blood")
    assert rs.resolve(s2, platform="NovaSeq").pipeline_profile == "by-type"
    # drop assay + sample_type → platform is the only match
    s3 = Sample(sample_id="Z", tissue="lung")
    assert rs.resolve(s3, platform="NovaSeq").pipeline_profile == "by-platform"
    # nothing matches → default
    s4 = Sample(sample_id="W", tissue="lung")
    assert rs.resolve(s4, platform="HiSeq").pipeline_profile == "default"


def test_exact_match_wins_over_single_axis() -> None:
    rs = RunbookSet(
        default=DEFAULT_RUNBOOK,
        profiles=[
            RunbookProfile(key=RunbookKey(assay="wgs"), runbook=Runbook(pipeline_profile="broad")),
            RunbookProfile(
                key=RunbookKey(assay="wgs", sample_type="blood", platform="novaseq"),
                runbook=Runbook(pipeline_profile="exact"),
            ),
        ],
    )
    s = Sample(sample_id="X", tissue="blood", extra={"assay": "wgs"})
    assert rs.resolve(s, platform="NovaSeq").pipeline_profile == "exact"


def test_empty_set_and_unknown_axes_fall_back_to_default() -> None:
    empty = RunbookSet(default=DEFAULT_RUNBOOK, profiles=[])
    assert empty.resolve(_panel_sample(), platform="NovaSeq") is empty.default
    # non-empty set, but no axis matches → default profile
    unknown = DEFAULT_RUNBOOK_SET.resolve(
        Sample(sample_id="Y", tissue="pancreas", extra={"assay": "exome"}), platform="HiSeq"
    )
    assert unknown.pipeline_profile == "default"


def test_normalization_is_case_and_whitespace_insensitive() -> None:
    """A key stored lower-case still matches a mixed-case / padded sample value."""
    s = Sample(sample_id="X", tissue="  Blood ", extra={"assay": "  Germline-Panel  "})
    assert DEFAULT_RUNBOOK_SET.resolve(s).pipeline_profile == "germline-panel"


# ── Gap A guard: coercion no-op + never-ungates ──────────────────────────────────────────────
def test_of_coercion_is_a_noop_passthrough() -> None:
    rb = Runbook(pipeline_profile="custom")
    rs = RunbookSet.of(rb)
    # no profiles → every sample (and a None sample) resolves to the bare runbook, unchanged
    assert rs.resolve(_panel_sample(), platform="NovaSeq") == rb
    assert rs.resolve(None) == rb
    assert rs.default is rb  # coercion never clones the runbook


def test_resolution_is_per_sample_and_never_ungates() -> None:
    rs = DEFAULT_RUNBOOK_SET
    # (a) resolve never returns None and never returns an empty-threshold runbook (fail-closed):
    for sample in (_plain_sample(), _panel_sample(), None):
        rb = rs.resolve(sample, platform="NovaSeq")
        assert rb is not None
        assert rb.qc_thresholds, "a resolved runbook must keep its gating thresholds"
    # (b) two distinct samples with distinct matching entries never collapse to the same runbook:
    two = RunbookSet(
        default=DEFAULT_RUNBOOK,
        profiles=[
            RunbookProfile(key=RunbookKey(assay="wgs"), runbook=Runbook(pipeline_profile="wgs")),
            RunbookProfile(
                key=RunbookKey(assay="panel"), runbook=Runbook(pipeline_profile="panel")
            ),
        ],
    )
    a = two.resolve(Sample(sample_id="A", extra={"assay": "wgs"}))
    b = two.resolve(Sample(sample_id="B", extra={"assay": "panel"}))
    assert a.pipeline_profile == "wgs"
    assert b.pipeline_profile == "panel"
    assert a is not b


# ── Gap A: WS-01 expected_metrics loop now has a real consumer ────────────────────────────────
def test_ws01_expected_metrics_loop_closes_end_to_end() -> None:
    art = _panel_run()
    # DORMANT baseline: the stock DEFAULT_RUNBOOK sets no expected_metrics, so the same panel
    # sample PROCEEDs — proving the profile (not the sample) is what arms the HOLD.
    base = evaluate_run(art, DEFAULT_RUNBOOK)["P1"]
    assert aggregate_verdict(base) is Verdict.PROCEED
    assert not any(f.rule_id.startswith("QC-EXPECTED") for f in base)

    # With the RunbookSet, the germline-panel profile resolves and expected_metrics fires.
    findings = evaluate_run(art, DEFAULT_RUNBOOK_SET)["P1"]
    assert any(f.rule_id == "QC-EXPECTED-QC.BREADTH_20X" for f in findings)
    assert any(f.rule_id == "QC-EXPECTED-QC.BREADTH_30X" for f in findings)
    # verdict is a pure function of the self-authored findings (ADR-0001)
    assert aggregate_verdict(findings) is Verdict.HOLD


def test_loop_closes_through_run_gate_cards() -> None:
    """End-to-end through the engine: a card carries the HOLD the profile's expected set drives."""
    cards = run_gate(_panel_run(), runbook=DEFAULT_RUNBOOK_SET)
    card = next(c for c in cards if c.sample_id == "P1")
    assert card.verdict is Verdict.HOLD


def test_germline_panel_runbook_shares_default_thresholds() -> None:
    """The panel profile differs from default ONLY by expected_metrics + pipeline_profile — the
    threshold list (what actually gates) is unchanged, so it never silently re-gates a metric."""
    assert GERMLINE_PANEL_RUNBOOK.qc_thresholds == DEFAULT_RUNBOOK.qc_thresholds
    assert GERMLINE_PANEL_RUNBOOK.expected_metrics == ("qc.breadth_20x", "qc.breadth_30x")


# ── Gap A: byte-identical pinned demo (back-compat coercion) ──────────────────────────────────
def test_default_runbook_set_demo_byte_identical() -> None:
    plain = {c.sample_id: c.verdict for c in run_gate(load_run(DATA), runbook=DEFAULT_RUNBOOK)}
    via_set = {
        c.sample_id: c.verdict for c in run_gate(load_run(DATA), runbook=DEFAULT_RUNBOOK_SET)
    }
    assert plain == via_set
    # pinned verdict invariants (mirror test_gate::test_verdict_aggregation_precedence)
    assert via_set["S1"] is Verdict.PROCEED
    assert via_set["S2"] is Verdict.PROCEED
    assert via_set["S3"] is Verdict.PROCEED
    assert via_set["S4"] is Verdict.ESCALATE
    assert via_set["S5"] is Verdict.HOLD


def test_plain_runbook_path_unchanged() -> None:
    """A bare Runbook passed to evaluate_run/run_gate is used AS-IS for every sample (no coercion,
    no per-sample resolution) — the deepest signature widen is a no-op on the existing path."""
    art = load_run(DATA)
    plain_findings = evaluate_run(art, DEFAULT_RUNBOOK)
    default_findings = evaluate_run(art, None)  # None → DEFAULT_RUNBOOK
    assert {sid: [f.signature for f in fs] for sid, fs in plain_findings.items()} == {
        sid: [f.signature for f in fs] for sid, fs in default_findings.items()
    }


# ── Gap B (validator still fires through the set): bogus expected key fails loud ──────────────
def test_bogus_expected_metrics_key_fails_loud() -> None:
    """A profile in a RunbookSet cannot expect a metric the parse layer can't produce — the WS-01
    producible-key validator fires at Runbook construction, so a typo can't silently HOLD."""
    with pytest.raises(ValueError):
        Runbook(pipeline_profile="typo", expected_metrics=("qc.definitely_not_real",))
    # and the same guard holds when that runbook is a set profile
    with pytest.raises(ValueError):
        RunbookSet(
            default=DEFAULT_RUNBOOK,
            profiles=[
                RunbookProfile(
                    key=RunbookKey(assay="typo"),
                    runbook=Runbook(expected_metrics=("qc.bogus_key",)),
                )
            ],
        )
