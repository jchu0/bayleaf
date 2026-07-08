"""Failure-mode-driven generator for contrived NovaSeq run directories.

The generator is the inverse of the rule engine: instead of reading artifacts and
emitting findings, it takes a per-sample *failure mode* and writes artifacts whose
values are engineered so the **existing** parsers + rules land that sample on a known
verdict. Keeping the two in lock-step is what makes the demo data trustworthy — the
accompanying test round-trips every generated run back through ``run_gate`` and
asserts the verdicts match the labels here.

Why a generator (not more hand-authored files): one honest source of truth for the
mapping ``failure mode -> verdict``, reproducible byte-for-byte, so ``data/`` can grow
diverse runs without hand-tuning numbers against the runbook every time.

Design choices that keep the modes deterministic and non-overlapping:

1. **One rule per mode.** Every non-clean sample is written so exactly one rule fires
   (e.g. a ``low_q30`` sample keeps passing coverage/dup/metadata/barcode), so the
   aggregated verdict is unambiguous and the label is provable.
2. **Sample IDs stay ``S1``..``S9``** so no ID is a substring of another — the log
   rules match on ``sid in line``, and ``S1`` must not match a line about ``S10``.
3. **Origin is always ``contrived``** and tagged in-band (a ``pipeguard-synthetic``
   note in ``pipeline.log``); values are invented, never real GIAB data.

The framework-agnostic core (no UI deps) writes plain CSV/text so the output matches
``data/mock_run_01/`` byte-shape: LF line endings, trailing newline, no quoting.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..models import Verdict

# --------------------------------------------------------------------------- #
# Failure modes and their intended verdicts
# --------------------------------------------------------------------------- #


class FailureMode(str, Enum):
    """A per-sample defect the generator plants, each tied to a single rule.

    The value is the wire label used in specs and the accompanying test. See
    :data:`INTENDED_VERDICT` for the verdict each mode is engineered to produce.
    """

    CLEAN = "clean"  # nothing planted -> PROCEED
    BARCODE_SWAP = "barcode_swap"  # demux index != sample sheet (PROV-001) -> ESCALATE
    MISSING_METADATA = "missing_metadata"  # blank required intake field (META-001) -> HOLD
    ABSENT_FROM_SHEET = "absent_from_sheet"  # QC row, no sheet row (PROV-002) -> ESCALATE
    LOW_Q30 = "low_q30"  # Q30 below gate, above hard-fail (QC-Q30) -> HOLD
    LOW_COVERAGE = "low_coverage"  # coverage below gate (QC-MEAN_COVERAGE) -> HOLD
    HIGH_DUP = "high_dup"  # duplication above gate (QC-DUP_RATE) -> HOLD
    PIPELINE_FAILURE = "pipeline_failure"  # failure marker in log (PIPE-001) -> RERUN


# The single source of truth for the mode -> verdict contract the test enforces.
INTENDED_VERDICT: dict[FailureMode, Verdict] = {
    FailureMode.CLEAN: Verdict.PROCEED,
    FailureMode.BARCODE_SWAP: Verdict.ESCALATE,
    FailureMode.MISSING_METADATA: Verdict.HOLD,
    FailureMode.ABSENT_FROM_SHEET: Verdict.ESCALATE,
    FailureMode.LOW_Q30: Verdict.HOLD,
    FailureMode.LOW_COVERAGE: Verdict.HOLD,
    FailureMode.HIGH_DUP: Verdict.HOLD,
    FailureMode.PIPELINE_FAILURE: Verdict.RERUN,
}


def intended_verdict(mode: FailureMode) -> Verdict:
    """Return the verdict the current rules produce for a sample with ``mode``."""
    return INTENDED_VERDICT[mode]


# --------------------------------------------------------------------------- #
# Fixed synthetic vocabularies (contrived — realistic shapes, invented values)
# --------------------------------------------------------------------------- #

# Distinct 8-mer (i7, i5) pairs. Clean samples' demux index equals their declared
# pair; a barcode_swap borrows a *different* i5 so the observed combo mismatches.
_INDEX_POOL: list[tuple[str, str]] = [
    ("ATTACTCG", "TATAGCCT"),
    ("TCCGGAGA", "ATAGAGGC"),
    ("CGCTCATT", "CCTATCCT"),
    ("GAGATTCC", "GGCTCTGA"),
    ("ATTCAGAA", "AGGCGAAG"),
    ("GAATTCGT", "TAATCTTA"),
    ("CTGAAGCT", "CAGGACGT"),
    ("TAATGCGC", "GTACTGAC"),
    ("CGGCTATG", "GCCTCTAT"),
]

_TISSUES: list[str] = ["blood", "saliva"]
_PREPS: list[str] = ["TruSeq DNA PCR-Free", "Nextera DNA Flex"]
_SUBMITTERS: list[str] = ["a.rivera", "k.osei", "m.chen"]

# The intake field blanked by MISSING_METADATA (mirrors mock_run_01's S4). It is a
# required field in the default runbook, so blanking it trips META-001 (HOLD).
_MISSING_FIELD = "subject_id"

# QC values that clear every default runbook gate with comfortable margin. A single
# metric is overridden per failure mode; the rest stay here so only one rule fires.
_PASS_Q30_BASE = 90.0
_PASS_PCT_ID_BASE = 84.0
_PASS_COVERAGE_BASE = 34.0
_PASS_DUP_BASE = 11.0
_PASS_CLUSTER_PF_BASE = 86.0

# Overridden metric values: below the gate but above the hard-fail floor, so each is
# a borderline WARN (-> HOLD), not a CRITICAL hard-fail (-> RERUN). Runbook gates:
# Q30 >= 85 (hard 75), coverage >= 30 (hard 15), dup <= 30 (hard 50).
_LOW_Q30_VALUE = 80.0
_LOW_COVERAGE_VALUE = 22.0
_HIGH_DUP_VALUE = 40.0


# --------------------------------------------------------------------------- #
# Spec models
# --------------------------------------------------------------------------- #


class SampleSpec(BaseModel):
    """One sample in a run: its ID, planted failure mode, and optional metadata.

    Metadata fields left ``None`` are auto-filled from the fixed vocabularies so a
    spec can be as terse as ``SampleSpec(sample_id="S1", mode=FailureMode.CLEAN)``.
    """

    model_config = ConfigDict(frozen=True)

    sample_id: str
    mode: FailureMode = FailureMode.CLEAN
    subject_id: str | None = None
    tissue: str | None = None
    library_prep: str | None = None
    submitted_by: str | None = None

    @property
    def intended_verdict(self) -> Verdict:
        """The verdict the gate should return for this sample."""
        return INTENDED_VERDICT[self.mode]


class RunSpec(BaseModel):
    """A whole run: its identifiers plus the ordered samples to synthesize."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(..., description="Directory name, e.g. 'mock_run_02'")
    run_name: str = Field(..., description="Illumina RunName, e.g. 'RUN-2026-07-08-A'")
    date: str = Field(..., description="ISO date 'YYYY-MM-DD' for the sample sheet + log")
    samples: list[SampleSpec]
    subject_base: int = Field(1000, description="Offset for auto-derived SUBJ-* IDs")

    def expected_verdicts(self) -> dict[str, Verdict]:
        """Map each sample_id to the verdict the gate should produce for it."""
        return {s.sample_id: s.intended_verdict for s in self.samples}


# --------------------------------------------------------------------------- #
# Per-sample value derivation
# --------------------------------------------------------------------------- #


def _declared_index(i: int) -> tuple[str, str]:
    """The (i7, i5) pair declared for sample position ``i`` in the sample sheet."""
    return _INDEX_POOL[i % len(_INDEX_POOL)]


def _observed_index(i: int, mode: FailureMode) -> str:
    """The 'i7-i5' combo demux observed. Swapped i5 for a barcode_swap sample."""
    i7, i5 = _declared_index(i)
    if mode is FailureMode.BARCODE_SWAP:
        # Borrow a neighbour's i5 (guaranteed distinct — pool i5s are unique) so the
        # observed combo no longer matches the declared one.
        _, other_i5 = _INDEX_POOL[(i + 1) % len(_INDEX_POOL)]
        return f"{i7}-{other_i5}"
    return f"{i7}-{i5}"


def _qc_values(i: int, mode: FailureMode) -> dict[str, float]:
    """Per-sample QC metrics: passing by default, one metric perturbed by ``mode``.

    Passing values carry a small, deterministic per-sample wobble (keyed on ``i``) so
    a run does not read as robotic, while staying well inside every gate.
    """
    values = {
        "q30": _PASS_Q30_BASE + (i % 5) * 0.6,
        "pct_reads_identified": _PASS_PCT_ID_BASE + (i % 4) * 1.5,
        "mean_coverage": _PASS_COVERAGE_BASE + (i % 6) * 1.4,
        "dup_rate": _PASS_DUP_BASE + (i % 5) * 1.2,
        "cluster_pf": _PASS_CLUSTER_PF_BASE + (i % 4) * 1.0,
    }
    if mode is FailureMode.LOW_Q30:
        values["q30"] = _LOW_Q30_VALUE
    elif mode is FailureMode.LOW_COVERAGE:
        values["mean_coverage"] = _LOW_COVERAGE_VALUE
    elif mode is FailureMode.HIGH_DUP:
        values["dup_rate"] = _HIGH_DUP_VALUE
    return values


def _effective_metadata(spec: SampleSpec, i: int, subject_base: int) -> dict[str, str]:
    """Resolve a sample's intake row, auto-filling gaps and blanking for the mode.

    A ``missing_metadata`` sample gets an empty ``subject_id`` cell (a present row
    with a blank required field) so META-001 fires — as opposed to no row at all,
    which would instead be caught by META-002.
    """
    row = {
        "sample_id": spec.sample_id,
        "subject_id": spec.subject_id or f"SUBJ-{subject_base + i + 1}",
        "tissue": spec.tissue or _TISSUES[i % len(_TISSUES)],
        "library_prep": spec.library_prep or _PREPS[i % len(_PREPS)],
        "submitted_by": spec.submitted_by or _SUBMITTERS[i % len(_SUBMITTERS)],
    }
    if spec.mode is FailureMode.MISSING_METADATA:
        row[_MISSING_FIELD] = ""  # blank the required intake field -> META-001 (HOLD)
    return row


def _reads(i: int) -> int:
    """Deterministic, plausible per-sample read count for demux stats."""
    return 9_600_000 + (i % 6) * 700_000


# --------------------------------------------------------------------------- #
# Artifact renderers (each returns the exact file text, LF + trailing newline)
# --------------------------------------------------------------------------- #


def _join(lines: list[str]) -> str:
    """Match mock_run_01 byte-shape: LF-joined lines with a single trailing LF."""
    return "\n".join(lines) + "\n"


def _render_sample_sheet(spec: RunSpec) -> str:
    """Illumina v2 sectioned sheet. absent_from_sheet samples are omitted here."""
    lines = [
        "[Header]",
        "FileFormatVersion,2",
        f"RunName,{spec.run_name}",
        "InstrumentPlatform,NovaSeq",
        f"Date,{spec.date}",
        "",
        "[Reads]",
        "Read1Cycles,151",
        "Read2Cycles,151",
        "Index1Cycles,8",
        "Index2Cycles,8",
        "",
        "[BCLConvert_Settings]",
        "SoftwareVersion,4.1.7",
        "AdapterRead1,CTGTCTCTTATACACATCT",
        "",
        "[BCLConvert_Data]",
        "Sample_ID,index,index2",
    ]
    for i, s in enumerate(spec.samples):
        if s.mode is FailureMode.ABSENT_FROM_SHEET:
            continue  # the whole point: sequenced/QC'd but never declared here
        i7, i5 = _declared_index(i)
        lines.append(f"{s.sample_id},{i7},{i5}")
    return _join(lines)


def _render_metadata(spec: RunSpec) -> str:
    """Intake sheet. Every sample gets a row (so META-002 never fires by accident)."""
    lines = ["sample_id,subject_id,tissue,library_prep,submitted_by"]
    for i, s in enumerate(spec.samples):
        m = _effective_metadata(s, i, spec.subject_base)
        lines.append(
            f"{m['sample_id']},{m['subject_id']},{m['tissue']},"
            f"{m['library_prep']},{m['submitted_by']}"
        )
    return _join(lines)


def _demux_rows(spec: RunSpec) -> list[tuple[str, str, int]]:
    """(sample_id, observed_index, reads) for every demultiplexed sample."""
    rows: list[tuple[str, str, int]] = []
    for i, s in enumerate(spec.samples):
        if s.mode is FailureMode.ABSENT_FROM_SHEET:
            continue  # not in the sheet -> no demux bin of its own
        rows.append((s.sample_id, _observed_index(i, s.mode), _reads(i)))
    return rows


# Fraction of a real run's reads that land in "Undetermined" (unassignable to any
# barcode). Baking it in keeps per-sample % Reads summing to ~92% like a real
# Demultiplex_Stats.csv, rather than a tautological 100%.
_UNDETERMINED_FRACTION = 0.08


def _demux_with_pct(spec: RunSpec) -> list[tuple[str, str, int, float]]:
    """Demux rows plus each sample's % share of the run's *total* reads.

    The denominator includes an ``_UNDETERMINED_FRACTION`` of unassigned reads, so
    the assigned shares sum to ~92% (as in mock_run_01), not 100%.
    """
    rows = _demux_rows(spec)
    assigned = sum(r[2] for r in rows) or 1
    total = assigned / (1 - _UNDETERMINED_FRACTION)
    return [(sid, index, reads, round(reads / total * 100, 1)) for sid, index, reads in rows]


def _render_demux(spec: RunSpec) -> str:
    """BCL Convert Demultiplex_Stats.csv style. % Reads is share of assigned reads."""
    lines = ["SampleID,Index,# Reads,% Reads"]
    for sample_id, index, reads, pct in _demux_with_pct(spec):
        lines.append(f"{sample_id},{index},{reads},{pct:.1f}")
    return _join(lines)


def _render_qc(spec: RunSpec) -> str:
    """Flattened MultiQC-style per-sample metrics. Every sample gets a row."""
    lines = ["sample_id,q30,pct_reads_identified,mean_coverage,dup_rate,cluster_pf"]
    for i, s in enumerate(spec.samples):
        v = _qc_values(i, s.mode)
        lines.append(
            f"{s.sample_id},{v['q30']:.1f},{v['pct_reads_identified']:.1f},"
            f"{v['mean_coverage']:.1f},{v['dup_rate']:.1f},{v['cluster_pf']:.1f}"
        )
    return _join(lines)


def _render_log(spec: RunSpec) -> str:
    """Free-text pipeline log.

    Only ``pipeline_failure`` samples get a line carrying a runbook failure marker
    (``exit code 1`` / ``FAILED``) so PIPE-001 fires for them and nobody else. The
    barcode-swap WARN and QC WARN lines are narrative colour — they contain no marker
    and never trip a rule. The ``pipeguard-synthetic`` line is the in-band origin tag.
    """
    base = datetime.fromisoformat(f"{spec.date}T02:14:03+00:00")

    def ts(offset_min: int) -> str:
        return (base + timedelta(minutes=offset_min)).strftime("%Y-%m-%dT%H:%M:%SZ")

    n = len(spec.samples)
    assigned = round(sum(pct for *_, pct in _demux_with_pct(spec)), 1)

    lines = [
        f"{ts(0)} [INFO] bclconvert: run {spec.run_name} demultiplexing started ({n} samples)",
        f"{ts(1)} [INFO] pipeguard-synthetic: CONTRIVED demo run generated by "
        f"pipeguard.synthetic.generator (origin=contrived); invented values, not real GIAB data",
        f"{ts(27)} [INFO] bclconvert: demultiplexing complete; "
        f"{assigned:.1f}% of reads assigned to a sample",
    ]

    offset = 28
    for i, s in enumerate(spec.samples):
        if s.mode is FailureMode.BARCODE_SWAP:
            _, declared_i5 = _declared_index(i)
            observed_i5 = _observed_index(i, s.mode).split("-")[1]
            lines.append(
                f"{ts(offset)} [WARN] bclconvert: sample {s.sample_id} observed index2 "
                f"{observed_i5} does not match declared index2 {declared_i5}; "
                f"possible index misassignment"
            )
            offset += 1

    clean = [s.sample_id for s in spec.samples if s.mode is FailureMode.CLEAN]
    if clean:
        lines.append(f"{ts(offset)} [INFO] fastqc: {' '.join(clean)} passed all modules")
        offset += 1

    _qc_flag_label = {
        FailureMode.LOW_Q30: "borderline Q30 below the configured gate",
        FailureMode.LOW_COVERAGE: "low mean coverage below the configured gate",
        FailureMode.HIGH_DUP: "elevated duplication above the configured gate",
    }
    for s in spec.samples:
        label = _qc_flag_label.get(s.mode)
        if label is not None:
            lines.append(f"{ts(offset)} [WARN] fastqc: {s.sample_id} flagged {label}")
            offset += 1

    for s in spec.samples:
        if s.mode is FailureMode.PIPELINE_FAILURE:
            lines.append(
                f"{ts(offset)} [ERROR] align: BWA-MEM step for sample {s.sample_id} "
                f"exited with exit code 1; alignment FAILED"
            )
            offset += 1

    lines.append(
        f"{ts(offset + 2)} [INFO] pipeline: run {spec.run_name} reached decision gate; "
        f"{n} samples awaiting operator review"
    )
    return _join(lines)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


def generate_run(spec: RunSpec, out_dir: str | Path) -> Path:
    """Write a complete run directory for ``spec`` under ``out_dir``.

    Creates ``out_dir/<run_id>/`` with the five artifacts the parsers read. The
    output is deterministic (same spec -> byte-identical files), so committed demo
    runs can be regenerated and diffed. Returns the created run directory.
    """
    run_dir = Path(out_dir) / spec.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # Pin encoding + LF explicitly so the byte-identical guarantee (and the
    # reproducibility test) hold on Windows too, where text-mode write would
    # otherwise translate "\n" -> "\r\n" and diverge from the committed POSIX bytes.
    for name, render in (
        ("SampleSheet.csv", _render_sample_sheet),
        ("sample_metadata.csv", _render_metadata),
        ("demux_stats.csv", _render_demux),
        ("qc_metrics.csv", _render_qc),
        ("pipeline.log", _render_log),
    ):
        (run_dir / name).write_text(render(spec), encoding="utf-8", newline="\n")
    return run_dir


# --------------------------------------------------------------------------- #
# Committed demo runs
# --------------------------------------------------------------------------- #

# Two runs telling different stories; together they exercise all four verdicts and
# all eight failure modes. Kept here (not in the test) so `python -m
# pipeguard.synthetic.generator` reproduces exactly what's committed under data/.
DEMO_RUNS: list[RunSpec] = [
    # QC-heavy run: mostly-clean plate with two QC misses, one crashed step, one swap.
    RunSpec(
        run_id="mock_run_02",
        run_name="RUN-2026-07-08-A",
        date="2026-07-08",
        subject_base=2200,
        samples=[
            SampleSpec(sample_id="S1", mode=FailureMode.CLEAN),
            SampleSpec(sample_id="S2", mode=FailureMode.CLEAN),
            SampleSpec(sample_id="S3", mode=FailureMode.LOW_Q30),
            SampleSpec(sample_id="S4", mode=FailureMode.HIGH_DUP),
            SampleSpec(sample_id="S5", mode=FailureMode.PIPELINE_FAILURE),
            SampleSpec(sample_id="S6", mode=FailureMode.BARCODE_SWAP),
        ],
    ),
    # Provenance-heavy run: intake gaps, a coverage miss, an unsheeted sample, a
    # crashed step. Exercises PROCEED / HOLD / RERUN / ESCALATE from a different angle.
    RunSpec(
        run_id="mock_run_03",
        run_name="RUN-2026-07-08-B",
        date="2026-07-08",
        subject_base=2300,
        samples=[
            SampleSpec(sample_id="S1", mode=FailureMode.CLEAN),
            SampleSpec(sample_id="S2", mode=FailureMode.MISSING_METADATA),
            SampleSpec(sample_id="S3", mode=FailureMode.LOW_COVERAGE),
            SampleSpec(sample_id="S4", mode=FailureMode.ABSENT_FROM_SHEET),
            SampleSpec(sample_id="S5", mode=FailureMode.PIPELINE_FAILURE),
            SampleSpec(sample_id="S6", mode=FailureMode.CLEAN),
        ],
    ),
]


def _default_data_dir() -> Path:
    """Repo ``data/`` dir, relative to this file (dev-tool convenience)."""
    return Path(__file__).resolve().parents[3] / "data"


def main(argv: list[str] | None = None) -> None:
    """Regenerate the committed demo runs (``mock_run_02``, ``mock_run_03``).

    Usage: ``python -m pipeguard.synthetic.generator [OUT_DIR]`` (defaults to the
    repo's ``data/``). ``mock_run_01`` is hand-authored and never touched.
    """
    args = sys.argv[1:] if argv is None else argv
    out_dir = Path(args[0]) if args else _default_data_dir()
    for spec in DEMO_RUNS:
        run_dir = generate_run(spec, out_dir)
        print(f"wrote {run_dir} ({len(spec.samples)} samples)")


if __name__ == "__main__":
    main()
