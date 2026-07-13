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

from bayleaf import Verdict, run_gate_from_dir
from bayleaf.synthetic import (
    COMMITTED_RUNS,
    DEMO_RUNS,
    INTENDED_VERDICT,
    ORIGIN_LABEL,
    SCALE_RUN,
    FailureMode,
    RunSpec,
    SampleSpec,
    build_bulk_specs,
    build_scale_spec,
    generate_bulk,
    generate_run,
    planted_modes,
    sample_ids,
)
from bayleaf.synthetic.__main__ import main as cli_main
from bayleaf.synthetic.generator import main

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
    FailureMode.PROCESS_FAILURE: {"EXEC-001"},
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
    """Every run self-declares as contrived synthetic data (never real GIAB), both
    in-band (pipeline.log tag) and out-of-band (origin marker file), and the two agree.

    ``contrived`` (not ``synthetic``) is the data-strategy label for machine-generated,
    invented-value runs; the reconciled marker + tag both derive from ORIGIN_LABEL so
    they can't drift (the bug: a hand-added 'synthetic' marker beside a 'contrived' tag).
    """
    run_dir = generate_run(_ALL_MODES_SPEC, tmp_path)
    log = (run_dir / "pipeline.log").read_text()
    assert "bayleaf-synthetic" in log
    assert f"origin={ORIGIN_LABEL}" in log
    assert ORIGIN_LABEL == "contrived"
    assert (run_dir / "origin").read_text() == f"{ORIGIN_LABEL}\n"


@pytest.mark.parametrize("spec", COMMITTED_RUNS, ids=lambda s: s.run_id)
def test_committed_demo_run_verdicts(spec: RunSpec) -> None:
    """Every committed bundle (mock_run_0{2,3} + the 30-sample scale run) matches its
    generator labels — the scale run proves zero-padded IDs round-trip at volume."""
    run_dir = DATA / spec.run_id
    assert run_dir.is_dir(), f"missing committed run {run_dir}; run `make` regen?"
    assert _verdicts(run_dir) == spec.expected_verdicts()


@pytest.mark.parametrize("spec", COMMITTED_RUNS, ids=lambda s: s.run_id)
def test_committed_demo_run_is_reproducible(spec: RunSpec, tmp_path: Path) -> None:
    """Regenerating a committed run yields byte-identical files to what's committed —
    so the committed data (incl. the origin marker) can never silently drift."""
    fresh = generate_run(spec, tmp_path)
    committed = DATA / spec.run_id
    for name in (
        "SampleSheet.csv",
        "sample_metadata.csv",
        "demux_stats.csv",
        "qc_metrics.csv",
        "pipeline.log",
        "origin",
    ):
        assert (fresh / name).read_bytes() == (committed / name).read_bytes(), name


def test_main_regenerates_into_target_dir(tmp_path: Path) -> None:
    """The module CLI writes every demo run under the given output directory."""
    main([str(tmp_path)])
    for spec in DEMO_RUNS:
        assert (tmp_path / spec.run_id / "SampleSheet.csv").exists()


# --------------------------------------------------------------------------- #
# Scale tooling (T-013 scale half): large runs, bulk runs, and the CLI over them
# --------------------------------------------------------------------------- #

# A large run distinct from the committed one (different id/seed) so the round-trip is
# exercised on freshly generated bytes, not only the committed fixture.
_FRESH_SCALE_SPEC = build_scale_spec(
    32,
    run_id="mock_run_scale_test",
    run_name="RUN-TEST-SCALE",
    date="2026-07-09",
    seed=7,
)


def test_scale_run_round_trips_every_planted_verdict(tmp_path: Path) -> None:
    """A freshly generated large run round-trips: every zero-padded sample lands on its
    planted verdict. This is the core scale contract — the substring-safe IDs are what
    let 30+ samples share a log without the log rule cross-firing."""
    run_dir = generate_run(_FRESH_SCALE_SPEC, tmp_path)
    assert _verdicts(run_dir) == _FRESH_SCALE_SPEC.expected_verdicts()


def test_committed_scale_run_spans_all_verdicts() -> None:
    """The committed scale run is a realistic mix, not an all-PROCEED plate — so the
    frontend's scale affordances have every verdict to filter/sort at volume."""
    assert set(SCALE_RUN.expected_verdicts().values()) == set(Verdict)
    assert len(SCALE_RUN.samples) == 30


def test_zero_padded_ids_prevent_log_substring_crossfire(tmp_path: Path) -> None:
    """S01 (clean) must not inherit a PIPE-001 failure from S10/S11/S12's log lines —
    the exact bug naive S1..S30 IDs hit via the log rule's ``sid in line`` match. This
    is the regression guard for the zero-padding fix."""
    spec = RunSpec(
        run_id="mock_run_substring",
        run_name="RUN-TEST-SUBSTRING",
        date="2026-07-09",
        samples=[
            *[SampleSpec(sample_id=f"S{n:02d}", mode=FailureMode.CLEAN) for n in range(1, 10)],
            SampleSpec(sample_id="S10", mode=FailureMode.PIPELINE_FAILURE),
            SampleSpec(sample_id="S11", mode=FailureMode.PIPELINE_FAILURE),
            SampleSpec(sample_id="S12", mode=FailureMode.PIPELINE_FAILURE),
        ],
    )
    run_dir = generate_run(spec, tmp_path)
    _, cards = run_gate_from_dir(run_dir)
    by_id = {c.sample_id: c for c in cards}
    # The clean sample whose *unpadded* id ("S1") is a substring of S10/S11/S12 stays PROCEED.
    assert by_id["S01"].verdict is Verdict.PROCEED
    assert by_id["S01"].findings == []
    for fid in ("S10", "S11", "S12"):
        assert by_id[fid].verdict is Verdict.RERUN


def test_planted_modes_is_deterministic() -> None:
    """Same (n, seed) -> identical modes; the reproducibility the committed run rests on."""
    assert planted_modes(30, seed=1) == planted_modes(30, seed=1)


def test_planted_modes_guarantees_every_mode_on_large_runs() -> None:
    """A run larger than the mode set plants one of every failure mode, so a scaled
    run's verdict mix is guaranteed non-degenerate regardless of the random draw.

    PROCESS_FAILURE is deliberately excluded from the auto-spread (it needs the extra
    `trace.txt` artifact — an opt-in execution-trace input), so the guarantee covers every
    mode over the standard five artifacts, not the trace-failure mode."""
    expected = {m for m in FailureMode if m is not FailureMode.PROCESS_FAILURE}
    assert set(planted_modes(30, seed=99)) == expected


def test_sample_ids_uniform_width_no_substrings() -> None:
    """IDs are zero-padded to a uniform width so none is a substring of another."""
    ids = sample_ids(30)
    assert ids[0] == "S01" and ids[-1] == "S30"
    assert len({len(i) for i in ids}) == 1  # uniform width
    assert not any(a != b and a in b for a in ids for b in ids)  # no id substrings another
    assert sample_ids(150)[0] == "S001"  # widens past 99


def test_build_bulk_specs_are_distinct_and_reproducible() -> None:
    """Bulk runs get distinct dirs/names and are reproducible from their args."""
    specs = build_bulk_specs(24, seed=3)
    assert len(specs) == 24
    assert len({s.run_id for s in specs}) == 24  # distinct directory names
    assert len({s.run_name for s in specs}) == 24  # distinct RunNames
    assert build_bulk_specs(24, seed=3) == specs  # same args -> identical specs


def test_bulk_runs_round_trip(tmp_path: Path) -> None:
    """A small bulk batch generates and every run round-trips to its planted verdicts,
    each tagged with the origin marker."""
    for spec in build_bulk_specs(3, samples_per_run=10, seed=5):
        run_dir = generate_run(spec, tmp_path)
        assert _verdicts(run_dir) == spec.expected_verdicts()
        assert (run_dir / "origin").read_text() == f"{ORIGIN_LABEL}\n"


def test_generate_bulk_writes_all_runs(tmp_path: Path) -> None:
    """The bulk driver writes every requested run with its artifacts + origin marker."""
    run_dirs = generate_bulk(tmp_path, 4, samples_per_run=8, seed=0)
    assert len(run_dirs) == 4
    for run_dir in run_dirs:
        assert (run_dir / "SampleSheet.csv").exists()
        assert (run_dir / "origin").read_text() == f"{ORIGIN_LABEL}\n"


def test_cli_demo_regenerates_all_committed_runs(tmp_path: Path) -> None:
    """`python -m bayleaf.synthetic demo` writes every committed run (incl. scale)."""
    cli_main(["demo", "--out", str(tmp_path)])
    for spec in COMMITTED_RUNS:
        assert (tmp_path / spec.run_id / "origin").read_text() == f"{ORIGIN_LABEL}\n"


def test_cli_bulk_writes_into_target_dir(tmp_path: Path) -> None:
    """`python -m bayleaf.synthetic bulk` writes N runs into the target directory."""
    cli_main(["bulk", "--count", "3", "--samples", "6", "--out", str(tmp_path)])
    assert sum(1 for p in tmp_path.iterdir() if p.is_dir()) == 3
