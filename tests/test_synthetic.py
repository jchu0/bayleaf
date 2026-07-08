"""Tests for the synthetic run generator (T-013, synthetic half).

These are the contract that forces the generator to stay correct: every generated
run is round-tripped back through the real parsers + ``run_gate`` and each sample's
verdict is asserted against the label the generator planted. If a rule or threshold
drifts, or the generator mis-tunes a value, the mismatch surfaces here — offline,
no API. They also pin the committed ``data/mock_run_0{2,3}`` bundles so a hand-edit
that breaks a verdict is caught.
"""

from pathlib import Path

import pytest

from pipeguard import Verdict, run_gate_from_dir
from pipeguard.synthetic import (
    DEMO_RUNS,
    INTENDED_VERDICT,
    FailureMode,
    RunSpec,
    SampleSpec,
    generate_run,
)
from pipeguard.synthetic.generator import main

DATA = Path(__file__).resolve().parent.parent / "data"

# One sample per failure mode, IDs S1..S8 (no ID is a substring of another, which the
# log rule relies on). Mixed into a single run so modes are exercised side by side.
_ALL_MODES_SPEC = RunSpec(
    run_id="mock_run_allmodes",
    run_name="RUN-TEST-ALLMODES",
    date="2026-07-08",
    samples=[SampleSpec(sample_id=f"S{i + 1}", mode=mode) for i, mode in enumerate(FailureMode)],
)


def _verdicts(run_dir: Path) -> dict[str, Verdict]:
    _, cards = run_gate_from_dir(run_dir)
    return {c.sample_id: c.verdict for c in cards}


# The exact rule each mode must trip. Asserting the rule *set* (not just the
# aggregated verdict) enforces the generator's "one rule per mode" design claim: an
# accidental extra finding that doesn't outrank the intended verdict would otherwise
# pass silently. Grounded against the live rules (see docstring above).
_EXPECTED_RULES: dict[FailureMode, set[str]] = {
    FailureMode.CLEAN: set(),
    FailureMode.BARCODE_SWAP: {"PROV-001"},
    FailureMode.MISSING_METADATA: {"META-001"},
    FailureMode.ABSENT_FROM_SHEET: {"PROV-002"},
    FailureMode.LOW_Q30: {"QC-Q30"},
    FailureMode.LOW_COVERAGE: {"QC-MEAN_COVERAGE"},
    FailureMode.HIGH_DUP: {"QC-DUP_RATE"},
    FailureMode.PIPELINE_FAILURE: {"PIPE-001"},
}


@pytest.mark.parametrize("mode", list(FailureMode))
def test_each_failure_mode_hits_intended_verdict(mode: FailureMode, tmp_path: Path) -> None:
    """Each mode aggregates to its intended verdict *and* trips exactly its one rule."""
    spec = RunSpec(
        run_id="mock_run_single",
        run_name="RUN-TEST-SINGLE",
        date="2026-07-08",
        samples=[SampleSpec(sample_id="S1", mode=mode)],
    )
    run_dir = generate_run(spec, tmp_path)
    _, cards = run_gate_from_dir(run_dir)
    (card,) = cards
    assert card.verdict is INTENDED_VERDICT[mode]
    assert {f.rule_id for f in card.findings} == _EXPECTED_RULES[mode]


def test_mixed_run_every_sample_matches_intent(tmp_path: Path) -> None:
    """All eight modes in one run: each sample still lands on its own verdict."""
    run_dir = generate_run(_ALL_MODES_SPEC, tmp_path)
    got = _verdicts(run_dir)
    assert got == _ALL_MODES_SPEC.expected_verdicts()
    # Sanity: the mix actually spans all four operator-facing verdicts.
    assert set(got.values()) == set(Verdict)


def test_generated_run_parses_with_existing_parsers(tmp_path: Path) -> None:
    """The five artifacts load and every declared/QC'd sample is discovered."""
    run_dir = generate_run(_ALL_MODES_SPEC, tmp_path)
    artifacts, _ = run_gate_from_dir(run_dir)
    expected_ids = {s.sample_id for s in _ALL_MODES_SPEC.samples}
    assert set(artifacts.sample_ids()) == expected_ids
    for name in (
        "SampleSheet.csv",
        "sample_metadata.csv",
        "demux_stats.csv",
        "qc_metrics.csv",
        "pipeline.log",
    ):
        assert (run_dir / name).exists()


def test_absent_from_sheet_is_missing_only_from_the_sheet(tmp_path: Path) -> None:
    """absent_from_sheet omits the sample from sheet + demux but keeps QC + intake,
    so PROV-002 (not META-002) is what fires."""
    spec = RunSpec(
        run_id="mock_run_absent",
        run_name="RUN-TEST-ABSENT",
        date="2026-07-08",
        samples=[
            SampleSpec(sample_id="S1", mode=FailureMode.CLEAN),
            SampleSpec(sample_id="S2", mode=FailureMode.ABSENT_FROM_SHEET),
        ],
    )
    run_dir = generate_run(spec, tmp_path)
    artifacts, cards = run_gate_from_dir(run_dir)
    assert "S2" not in {e.sample_id for e in artifacts.sample_sheet}
    assert "S2" in {q.sample_id for q in artifacts.qc}
    assert "S2" in {s.sample_id for s in artifacts.samples}  # intake row present
    s2 = next(c for c in cards if c.sample_id == "S2")
    assert {f.rule_id for f in s2.findings} == {"PROV-002"}


def test_barcode_swap_demux_index_differs_from_sheet(tmp_path: Path) -> None:
    """A swapped sample's declared and observed indexes must actually disagree
    (otherwise PROV-001 could never fire)."""
    spec = RunSpec(
        run_id="mock_run_swap",
        run_name="RUN-TEST-SWAP",
        date="2026-07-08",
        samples=[SampleSpec(sample_id="S1", mode=FailureMode.BARCODE_SWAP)],
    )
    run_dir = generate_run(spec, tmp_path)
    artifacts, _ = run_gate_from_dir(run_dir)
    sheet = next(e for e in artifacts.sample_sheet if e.sample_id == "S1")
    demux = next(d for d in artifacts.demux if d.sample_id == "S1")
    declared = f"{sheet.index}-{sheet.index2}"
    assert demux.index is not None and demux.index != declared


def test_clean_sample_has_no_findings(tmp_path: Path) -> None:
    """A clean sample must trip nothing — the PROCEED baseline the demo rests on."""
    spec = RunSpec(
        run_id="mock_run_clean",
        run_name="RUN-TEST-CLEAN",
        date="2026-07-08",
        samples=[SampleSpec(sample_id="S1", mode=FailureMode.CLEAN)],
    )
    run_dir = generate_run(spec, tmp_path)
    _, cards = run_gate_from_dir(run_dir)
    assert cards[0].findings == []


def test_generated_run_carries_origin_marker(tmp_path: Path) -> None:
    """Every run self-declares as contrived synthetic data (never real GIAB)."""
    run_dir = generate_run(_ALL_MODES_SPEC, tmp_path)
    log = (run_dir / "pipeline.log").read_text()
    assert "pipeguard-synthetic" in log
    assert "origin=contrived" in log


@pytest.mark.parametrize("spec", DEMO_RUNS, ids=lambda s: s.run_id)
def test_committed_demo_run_verdicts(spec: RunSpec) -> None:
    """The committed data/mock_run_0{2,3} bundles match their generator labels."""
    run_dir = DATA / spec.run_id
    assert run_dir.is_dir(), f"missing committed run {run_dir}; run `make` regen?"
    assert _verdicts(run_dir) == spec.expected_verdicts()


@pytest.mark.parametrize("spec", DEMO_RUNS, ids=lambda s: s.run_id)
def test_committed_demo_run_is_reproducible(spec: RunSpec, tmp_path: Path) -> None:
    """Regenerating a demo run yields byte-identical files to what's committed —
    so the committed data can never silently drift from the generator."""
    fresh = generate_run(spec, tmp_path)
    committed = DATA / spec.run_id
    for name in (
        "SampleSheet.csv",
        "sample_metadata.csv",
        "demux_stats.csv",
        "qc_metrics.csv",
        "pipeline.log",
    ):
        assert (fresh / name).read_bytes() == (committed / name).read_bytes(), name


def test_main_regenerates_into_target_dir(tmp_path: Path) -> None:
    """The module CLI writes every demo run under the given output directory."""
    main([str(tmp_path)])
    for spec in DEMO_RUNS:
        assert (tmp_path / spec.run_id / "SampleSheet.csv").exists()
