"""W4 multi-sample driver: the publish-dir → N-run-dir-row parse (offline).

The emitted Nextflow germline pipeline fans out per sample (nf-core ``[meta, files]``), naming every
per-sample output ``${meta.id}.*``. This exercises the DRIVER's post-run parse
(``scripts/run_giab_pipeline.py``) against a FIXTURE publish dir — a directory of per-sample QC
files, no Nextflow, no bioconda tools, no network — so it runs in this repo's default offline
environment. The actual multi-sample Nextflow RUN stays env-gated (no reads on disk here); this pins
the parse/write/gate logic that a real run would drive.

Covered:
  1. an N-sample publish dir → one run dir holding N gated rows (frozen five present per sample);
  2. a fan-out of 1 (HG002) → a run dir BYTE-IDENTICAL to the pre-fan-out single-sample driver;
  3. a partial publish dir (a sample missing one output) → fails LOUD (never a fabricated metric);
  4. an empty publish dir → fails LOUD;
  5. sample-id prefix anchoring (``S1`` never cross-captures ``S10``);
  6. demux ``% Reads`` is each sample's real share of the run total.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from scripts.run_giab_pipeline import (
    RunConfig,
    discover_samples,
    parse_publish_dir,
    parse_sample,
    write_run_dir,
    write_run_dir_multi,
)

from bayleaf import run_gate_from_dir

# ------------------------------------------------------------------ fixture publish-dir builders


def _fastp_json(*, q30_rate: float, total_reads: int, passed: int, dup_rate: float) -> str:
    """A minimal fastp report carrying exactly the fields ``parse_fastp`` reads."""
    return json.dumps(
        {
            "summary": {
                "before_filtering": {"total_reads": total_reads},
                "after_filtering": {"q30_rate": q30_rate},
            },
            "filtering_result": {"passed_filter_reads": passed},
            "duplication": {"rate": dup_rate},
        }
    )


def _mosdepth_summary(mean: float) -> str:
    # cols: chrom length bases mean min max — parse_mosdepth reads split('\t')[3] on total_region.
    return f"chrom\tlength\tbases\tmean\tmin\tmax\ntotal_region\t2000\t100000\t{mean}\t10\t80\n"


def _thresholds_bed(*, span: int, ge20: int, ge30: int) -> str:
    # cols: #chrom start end region 1X 10X 20X 30X — parse uses (end-start), c[6] (20x), c[7] (30x).
    return (
        "#chrom\tstart\tend\tregion\t1X\t10X\t20X\t30X\n"
        f"chr20\t0\t{span}\treg\t{span}\t{span}\t{ge20}\t{ge30}\n"
    )


def _norm_vcf(n_variants: int) -> str:
    lines = ["##fileformat=VCFv4.2", "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"]
    lines += [f"chr20\t{100 + i}\t.\tA\tG\t50\tPASS\t." for i in range(n_variants)]
    return "\n".join(lines) + "\n"


def _write_sample_outputs(
    pub: Path,
    sample: str,
    *,
    mean: float = 50.0,
    total_reads: int = 1_000_000,
    q30_rate: float = 0.90,
    passed: int = 990_000,
    dup_rate: float = 0.05,
    span: int = 2000,
    ge20: int = 1800,
    ge30: int = 1600,
    n_variants: int = 3,
    skip: tuple[str, ...] = (),
) -> None:
    """Write one sample's ``${meta.id}.*`` published outputs into ``pub``.

    ``skip`` names output kinds (``fastp`` / ``mosdepth_summary`` / ``thresholds`` / ``norm``) to
    OMIT, so a caller can build a deliberately partial publish dir for the fail-loud case.
    """
    pub.mkdir(parents=True, exist_ok=True)
    if "fastp" not in skip:
        (pub / f"{sample}.fastp.json").write_text(
            _fastp_json(
                q30_rate=q30_rate, total_reads=total_reads, passed=passed, dup_rate=dup_rate
            )
        )
    if "mosdepth_summary" not in skip:
        (pub / f"{sample}.panel.mosdepth.summary.txt").write_text(_mosdepth_summary(mean))
    if "thresholds" not in skip:
        with gzip.open(pub / f"{sample}.panel.thresholds.bed.gz", "wt", encoding="utf-8") as fh:
            fh.write(_thresholds_bed(span=span, ge20=ge20, ge30=ge30))
    if "norm" not in skip:
        with gzip.open(pub / f"{sample}.norm.vcf.gz", "wt", encoding="utf-8") as fh:
            fh.write(_norm_vcf(n_variants))


def _cfg(run_dir: Path, run_id: str = "RUN-MULTI") -> RunConfig:
    return RunConfig(
        run_id=run_id,
        run_dir=run_dir,
        platform="HiSeq 2500",
        run_date="2026-07-11",
        submitted_by="tester",
    )


def _rows(csv_text: str) -> list[str]:
    """Non-empty lines of a CSV (header + data)."""
    return [ln for ln in csv_text.splitlines() if ln.strip()]


# ------------------------------------------------------------------ 1. N samples → N gated rows


def test_multisample_publish_dir_yields_n_gated_run_dir_rows(tmp_path: Path) -> None:
    pub = tmp_path / "results"
    _write_sample_outputs(pub, "HG002", total_reads=1_000_000, n_variants=3)
    _write_sample_outputs(pub, "HG003", total_reads=800_000, mean=40.0, n_variants=5)
    _write_sample_outputs(pub, "HG004", total_reads=600_000, mean=30.0, n_variants=2)

    samples = parse_publish_dir(pub)
    assert [s.sample for s in samples] == ["HG002", "HG003", "HG004"]  # discovery is sorted

    run_dir = tmp_path / "data" / "RUN-MULTI"
    cfg = _cfg(run_dir)
    write_run_dir_multi(cfg, samples)

    # One run dir, the full frozen five, N rows in each per-sample table.
    for name in ("SampleSheet.csv", "sample_metadata.csv", "demux_stats.csv", "qc_metrics.csv"):
        assert (run_dir / name).exists()
    qc_rows = _rows((run_dir / "qc_metrics.csv").read_text())
    assert len(qc_rows) == 1 + 3  # header + 3 samples
    assert {r.split(",")[0] for r in qc_rows[1:]} == {"HG002", "HG003", "HG004"}

    # The gate turns the ONE run dir into N cards (per-sample verdicts) with no read-API change.
    _artifacts, cards = run_gate_from_dir(run_dir)
    assert {c.sample_id for c in cards} == {"HG002", "HG003", "HG004"}
    assert all(c.verdict is not None for c in cards)


# ------------------------------------------------------------------ 2. fan-out of 1 byte-identical


def test_single_sample_run_dir_is_byte_identical_to_pre_fanout_format(tmp_path: Path) -> None:
    pub = tmp_path / "results"
    _write_sample_outputs(
        pub, "HG002", total_reads=1_000_000, q30_rate=0.90, passed=990_000, dup_rate=0.05
    )
    samples = parse_publish_dir(pub)
    assert len(samples) == 1

    run_dir = tmp_path / "data" / "RUN-1"
    cfg = _cfg(run_dir, run_id="RUN-1")
    write_run_dir_multi(cfg, samples)

    # Exact bytes the pre-fan-out single-sample driver emitted — a hard regression pin.
    assert (run_dir / "SampleSheet.csv").read_text() == (
        "[Header]\nFileFormatVersion,2\nRunName,RUN-1\n"
        "InstrumentPlatform,HiSeq 2500\nDate,2026-07-11\n\n"
        "[Reads]\nRead1Cycles,250\nRead2Cycles,250\n\n"
        "[BCLConvert_Data]\nSample_ID,index,index2\nHG002,NA,NA\n"
    )
    assert (run_dir / "demux_stats.csv").read_text() == (
        "SampleID,Index,# Reads,% Reads\nHG002,NA,1000000,100.0\n"
    )
    assert (run_dir / "qc_metrics.csv").read_text() == (
        "sample_id,q30,pct_reads_identified,mean_coverage,dup_rate,cluster_pf,"
        "breadth_20x,breadth_30x\nHG002,90.00,99.00,50.0,5.0000,,0.9000,0.8000\n"
    )
    assert (run_dir / "sample_metadata.csv").read_text() == (
        "sample_id,subject_id,tissue,library_prep,submitted_by,metadata_origin\n"
        "HG002,HG002,blood,PCR-free,tester,fixture-authored-placeholder\n"
    )


def test_scalar_write_run_dir_wrapper_matches_the_multi_writer(tmp_path: Path) -> None:
    """The kept scalar entrypoint (used by the offline preflight test) delegates to the multi writer
    and must emit the identical single-sample bytes."""
    run_dir = tmp_path / "data" / "RUN-W"
    cfg = _cfg(run_dir, run_id="RUN-W")
    write_run_dir(cfg, 90.0, 99.0, 50.0, 5.0, 1_000_000, 0.9, 0.8)
    assert (run_dir / "demux_stats.csv").read_text() == (
        "SampleID,Index,# Reads,% Reads\nHG002,NA,1000000,100.0\n"
    )
    assert _rows((run_dir / "qc_metrics.csv").read_text())[1] == (
        "HG002,90.00,99.00,50.0,5.0000,,0.9000,0.8000"
    )


# ------------------------------------------------------------------ 3./4. fail loud


def test_partial_publish_dir_fails_loud(tmp_path: Path) -> None:
    """A sample present in the publish dir but MISSING one of its per-sample outputs must fail loud
    (SystemExit) — never silently drop the sample or fabricate a metric."""
    pub = tmp_path / "results"
    _write_sample_outputs(pub, "HG002")
    _write_sample_outputs(pub, "HG003", skip=("thresholds",))  # has fastp, missing thresholds
    with pytest.raises(SystemExit, match=r"HG003.*partial|partial.*HG003"):
        parse_publish_dir(pub)


def test_empty_publish_dir_fails_loud(tmp_path: Path) -> None:
    pub = tmp_path / "results"
    pub.mkdir()
    with pytest.raises(SystemExit, match="no per-sample outputs"):
        parse_publish_dir(pub)


# ------------------------------------------------------------------ 5. prefix anchoring


def test_sample_id_prefix_is_anchored_no_cross_capture(tmp_path: Path) -> None:
    """A shared-prefix pair (``S1`` / ``S10``) must not cross-capture: each sample's parse reads its
    OWN files. Distinct total_reads per sample makes a mixup observable."""
    pub = tmp_path / "results"
    _write_sample_outputs(pub, "S1", total_reads=111_111)
    _write_sample_outputs(pub, "S10", total_reads=222_222)

    assert discover_samples(pub) == ["S1", "S10"]
    m1 = parse_sample(pub, "S1")
    m10 = parse_sample(pub, "S10")
    assert m1.total_reads == 111_111  # S1 did NOT pick up S10's fastp
    assert m10.total_reads == 222_222


# ------------------------------------------------------------------ 6. demux % Reads share


def test_demux_pct_reads_is_per_sample_share(tmp_path: Path) -> None:
    pub = tmp_path / "results"
    _write_sample_outputs(pub, "A", total_reads=750_000)
    _write_sample_outputs(pub, "B", total_reads=250_000)  # total 1_000_000 → 75% / 25%
    run_dir = tmp_path / "data" / "RUN-PCT"
    write_run_dir_multi(_cfg(run_dir, run_id="RUN-PCT"), parse_publish_dir(pub))

    rows = _rows((run_dir / "demux_stats.csv").read_text())[1:]
    pct = {r.split(",")[0]: r.split(",")[3] for r in rows}
    assert pct == {"A": "75.0", "B": "25.0"}
