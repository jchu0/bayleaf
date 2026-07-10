"""Scale drivers over the failure-mode generator: one large run and many runs.

Why a separate module (not more constants in :mod:`~pipeguard.synthetic.generator`):
the generator owns the *failure mode -> verdict* contract and the two committed demo
stories; this module owns the orthogonal concern of **volume** — building N-sample
runs and batches of runs so the frontend's scale affordances (pagination, filtering,
big verdict mixes) have real data to exercise. It composes the generator's public
API and adds **no** rule logic and **no** new failure modes.

Two knobs the driver adds on top of the generator:

1. **Zero-padded, uniform-width sample IDs** (``S01``..``S30``). The log rule matches
   on ``sid in line``, so a naive ``S1`` would substring-match a line about ``S10``.
   Equal-length distinct IDs can't be substrings of one another, which is the whole
   guarantee — see :func:`sample_ids`.
2. **A deterministic, CLEAN-dominant spread of failure modes** so a scaled run reads
   like a real plate (mostly PROCEED, a realistic minority across the other three
   verdicts) rather than all-PROCEED — see :func:`planted_modes`.

Everything here is seeded and reproducible: the same ``(n, seed)`` yields the same
run byte-for-byte, so the one committed scale run (:data:`SCALE_RUN`) can be
regenerated and diffed, and bulk volume is regenerable on demand into a git-ignored
directory rather than committed.
"""

from __future__ import annotations

import random
import string
from datetime import date, datetime, timedelta
from pathlib import Path

from .generator import (
    DEMO_RUNS,
    FailureMode,
    RunSpec,
    SampleSpec,
    generate_run,
)

__all__ = [
    "BULK_DIR_NAME",
    "COMMITTED_RUNS",
    "COMMITTED_SCALE_RUN_ID",
    "COMMITTED_SCALE_SEED",
    "SCALE_RUN",
    "build_bulk_specs",
    "build_scale_spec",
    "generate_bulk",
    "generate_committed",
    "planted_modes",
    "sample_ids",
]

# --------------------------------------------------------------------------- #
# Failure-mode spread (deterministic, CLEAN-dominant)
# --------------------------------------------------------------------------- #

# Weighting over failure modes for the weighted "fill" draws. CLEAN dominates so a run
# reads like a real plate (most samples pass); the remainder spreads the three
# non-PROCEED verdicts. These weights are illustrative demo-shaping, NOT derived from
# real run statistics — the guardrail that confidence/thresholds are heuristics, not
# calibrated rates, applies here too. Weights sum to 1.0 for readability (``choices``
# normalizes regardless).
_MODE_WEIGHTS: list[tuple[FailureMode, float]] = [
    (FailureMode.CLEAN, 0.64),
    (FailureMode.LOW_Q30, 0.06),
    (FailureMode.LOW_COVERAGE, 0.06),
    (FailureMode.HIGH_DUP, 0.05),
    (FailureMode.MISSING_METADATA, 0.05),
    (FailureMode.BARCODE_SWAP, 0.05),
    (FailureMode.ABSENT_FROM_SHEET, 0.04),
    (FailureMode.PIPELINE_FAILURE, 0.05),
]


def planted_modes(n: int, *, seed: int) -> list[FailureMode]:
    """Return the ``n`` per-sample failure modes for a scaled run, deterministically.

    The spread is engineered to be *non-degenerate*: when the run is larger than the
    number of failure modes, one of every non-CLEAN mode is planted first, so the
    verdict mix is guaranteed to span HOLD/ESCALATE/RERUN (and every finding type
    shows up for the frontend) regardless of the random draw. The remaining slots are
    filled from the CLEAN-dominant :data:`_MODE_WEIGHTS`, then the whole list is
    shuffled so the guaranteed failures aren't clustered at the front of the plate.

    Seeded via :class:`random.Random` (Mersenne Twister is stable across CPython
    versions), so ``planted_modes(n, seed=s)`` is byte-reproducible — the property the
    committed run and its round-trip test both rely on. Tiny runs (``n`` <= number of
    modes) skip the guarantee and draw purely from the weights.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    rng = random.Random(seed)
    # PROCESS_FAILURE is excluded from the auto-spread: it needs the extra `trace.txt`
    # artifact (an opt-in execution-trace input), so it isn't part of the standard
    # five-artifact QC/gate failure spread. Excluding it also keeps the committed scale
    # run byte-identical as new modes are added to the enum.
    non_clean = [
        m for m in FailureMode if m not in (FailureMode.CLEAN, FailureMode.PROCESS_FAILURE)
    ]
    modes: list[FailureMode] = []
    # Guarantee variety on runs with room to spare: one of every non-CLEAN mode up
    # front means all four operator verdicts always appear, never an all-PROCEED plate.
    if n > len(non_clean):
        modes.extend(non_clean)
    population = [m for m, _ in _MODE_WEIGHTS]
    weights = [w for _, w in _MODE_WEIGHTS]
    while len(modes) < n:
        modes.append(rng.choices(population, weights=weights)[0])
    del modes[n:]  # defensive: never exceed n (only reachable for very small n)
    rng.shuffle(modes)  # de-cluster the guaranteed block across the plate
    return modes


# --------------------------------------------------------------------------- #
# Zero-padded sample IDs (the anti-substring guarantee)
# --------------------------------------------------------------------------- #


def _pad_width(n: int) -> int:
    """Digits to render sample numbers 1..n at a uniform width (at least two).

    Uniform width is the anti-substring guarantee: two equal-length *distinct* strings
    can never be substrings of one another, so the log rule's ``sid in line`` match
    cannot cross-fire (``S1`` matching a line about ``S10``). Two-digit minimum keeps
    small runs looking like plates (``S01`` not ``S1``) and matches the demo runs.
    """
    return max(2, len(str(n)))


def sample_ids(n: int) -> list[str]:
    """Return ``["S01", "S02", ...]`` — ``n`` zero-padded, uniform-width sample IDs."""
    width = _pad_width(n)
    return [f"S{k:0{width}d}" for k in range(1, n + 1)]


# --------------------------------------------------------------------------- #
# Spec builders
# --------------------------------------------------------------------------- #


def build_scale_spec(
    n_samples: int,
    *,
    run_id: str,
    run_name: str,
    date: str,
    subject_base: int = 3000,
    seed: int = 0,
) -> RunSpec:
    """Build a single ``n_samples``-sample run with padded IDs and a mixed spread.

    Composes :func:`sample_ids` and :func:`planted_modes` into a :class:`RunSpec` the
    existing :func:`~pipeguard.synthetic.generator.generate_run` can render unchanged.
    Deterministic in ``(n_samples, seed)``. The metadata for each sample is left blank
    so the generator auto-fills it from its fixed vocabularies.
    """
    ids = sample_ids(n_samples)
    modes = planted_modes(n_samples, seed=seed)
    samples = [SampleSpec(sample_id=sid, mode=mode) for sid, mode in zip(ids, modes, strict=True)]
    return RunSpec(
        run_id=run_id,
        run_name=run_name,
        date=date,
        subject_base=subject_base,
        samples=samples,
    )


# Bulk runs are spread across days with a few runs per day, mirroring how a lab files
# several flowcells against one date (RUN-...-A, -B, ...). Purely cosmetic — nothing
# gates on the date or letter — but it keeps the generated run list realistic.
_RUNS_PER_DAY = 4


def build_bulk_specs(
    count: int,
    *,
    samples_per_run: int = 12,
    start_date: str = "2026-07-09",
    run_id_prefix: str = "bulk_run",
    seed: int = 0,
) -> list[RunSpec]:
    """Build ``count`` distinct runs for bulk volume, each with its own spread.

    Each run gets a distinct ``run_id`` (``bulk_run_000``..), a distinct ``run_name``
    (date + A/B/C/D letter), a distinct ``date`` (a few runs per day), a distinct
    ``subject_base`` (so subject IDs never collide across runs), and a distinct per-run
    ``seed`` (``seed + i``) so every plate has its own failure spread. The whole batch
    is reproducible from ``(count, samples_per_run, start_date, seed)``.
    """
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")
    base: date = datetime.fromisoformat(start_date).date()
    specs: list[RunSpec] = []
    for i in range(count):
        day = base + timedelta(days=i // _RUNS_PER_DAY)
        letter = string.ascii_uppercase[i % _RUNS_PER_DAY]
        specs.append(
            build_scale_spec(
                samples_per_run,
                run_id=f"{run_id_prefix}_{i:03d}",
                run_name=f"RUN-{day.isoformat()}-{letter}",
                date=day.isoformat(),
                # Space subject bases far enough apart that runs never share a SUBJ-*.
                subject_base=4000 + i * 1000,
                seed=seed + i,
            )
        )
    return specs


# --------------------------------------------------------------------------- #
# The one committed scale run (regenerable + round-tripped, like the demo runs)
# --------------------------------------------------------------------------- #

# A single ~30-sample run is committed so the demo shows scale out of the box; bulk
# volume (dozens of runs) is regenerated on demand into a git-ignored directory
# (BULK_DIR_NAME), never committed — the repo stays small (data guardrail).
COMMITTED_SCALE_RUN_ID = "mock_run_scale_30"
COMMITTED_SCALE_SEED = 20260709

SCALE_RUN: RunSpec = build_scale_spec(
    30,
    run_id=COMMITTED_SCALE_RUN_ID,
    run_name="RUN-2026-07-09-SCALE",
    date="2026-07-09",
    subject_base=3000,
    seed=COMMITTED_SCALE_SEED,
)

# Every committed generated run — the two demo stories plus the scale run — so a
# single command (``python -m pipeguard.synthetic``) regenerates all of them and the
# round-trip test can pin every one.
COMMITTED_RUNS: list[RunSpec] = [*DEMO_RUNS, SCALE_RUN]

# Directory (under data/) for on-demand bulk volume. Git-ignored — regenerable from
# the CLI, so its bytes never enter the repo.
BULK_DIR_NAME = "synthetic_bulk"


# --------------------------------------------------------------------------- #
# Drivers
# --------------------------------------------------------------------------- #


def generate_committed(out_dir: str | Path) -> list[Path]:
    """Write every committed run (:data:`COMMITTED_RUNS`) under ``out_dir``.

    This is what the bare ``python -m pipeguard.synthetic`` invocation runs: it
    regenerates the two demo stories *and* the scale run into ``data/``, so the whole
    committed set stays byte-reproducible from one command.
    """
    return [generate_run(spec, out_dir) for spec in COMMITTED_RUNS]


def generate_bulk(
    out_dir: str | Path,
    count: int,
    *,
    samples_per_run: int = 12,
    start_date: str = "2026-07-09",
    seed: int = 0,
) -> list[Path]:
    """Write ``count`` bulk runs under ``out_dir`` and return their directories.

    Intended for the git-ignored :data:`BULK_DIR_NAME` sink — this is the volume the
    frontend's scale affordances test against, regenerated on demand rather than
    committed.
    """
    specs = build_bulk_specs(
        count, samples_per_run=samples_per_run, start_date=start_date, seed=seed
    )
    return [generate_run(spec, out_dir) for spec in specs]
