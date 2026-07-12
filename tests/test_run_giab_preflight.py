"""Pre-flight guards + reproducibility capture for the Nextflow-first GIAB driver (P3-3/4/5/6/9).

These exercise the driver's cheap, LOUD, before-launch validation directly — no Nextflow, no
bioconda tools, no network — so they run in this repo's default offline environment. Each guard must
fail with a clear message (SystemExit, the driver's failure idiom) rather than silently proceed; a
VALID input must pass so the live HG002 run is never broken.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest
from scripts.run_giab_pipeline import (
    _REQUIRED_INDEX_SUFFIXES,
    RunConfig,
    _preflight_contigs,
    _preflight_fastqs,
    _preflight_reference_index,
    _probe_version,
    _read_id_core,
    capture_versions,
    write_run_dir,
)

# A valid Illumina read name shared by both mates (no /1 /2 suffix, like the real GIAB reads).
_HDR = "@D00360:97:H2YVMBCXX:2:1207:16074:43107"

_Rec = tuple[str, str, str]  # (header, seq, qual)


def _write_fastq(path: Path, records: list[_Rec], *, gzipped: bool = True) -> Path:
    """Write a FASTQ (header, seq, qual) list; gzip by default to mirror the real .fastq.gz."""
    text = "".join(f"{h}\n{seq}\n+\n{qual}\n" for h, seq, qual in records)
    if gzipped:
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def _pair(tmp: Path, *, r1: list[_Rec], r2: list[_Rec]) -> tuple[Path, Path]:
    return (
        _write_fastq(tmp / "R1.fastq.gz", r1),
        _write_fastq(tmp / "R2.fastq.gz", r2),
    )


# ------------------------------------------------------------------ P3-3: FASTQ pre-flight


def test_read_id_core_strips_mate_suffix_and_comment() -> None:
    assert _read_id_core("@read1/1") == "read1"
    assert _read_id_core("@read1/2") == "read1"
    assert _read_id_core("@read1 1:N:0:ACGT") == "read1"
    assert _read_id_core(_HDR) == _HDR[1:]  # the real GIAB style: whole name, no suffix


def test_preflight_fastqs_accepts_a_valid_matched_pair(tmp_path: Path) -> None:
    r1, r2 = _pair(
        tmp_path,
        r1=[(f"{_HDR}", "ACGT", "IIII"), ("@r2", "TTTT", "IIII")],
        r2=[(f"{_HDR}", "GGGG", "IIII"), ("@r2", "CCCC", "IIII")],
    )
    _preflight_fastqs(r1, r2)  # must NOT raise


def test_preflight_fastqs_rejects_non_fastq_input(tmp_path: Path) -> None:
    r1 = tmp_path / "R1.fastq.gz"
    with gzip.open(r1, "wt", encoding="utf-8") as fh:
        fh.write("this is not a fastq file at all\n")  # gzip magic OK, content is not FASTQ
    r2 = _write_fastq(tmp_path / "R2.fastq.gz", [(_HDR, "ACGT", "IIII")])
    with pytest.raises(SystemExit, match="not FASTQ"):
        _preflight_fastqs(r1, r2)


def test_preflight_fastqs_rejects_mismatched_read_ids(tmp_path: Path) -> None:
    # Equal length, both valid FASTQ, but the reads do not pair (different samples / swapped).
    r1, r2 = _pair(
        tmp_path,
        r1=[("@sampleA:1", "ACGT", "IIII")],
        r2=[("@sampleB:9", "GGGG", "IIII")],
    )
    with pytest.raises(SystemExit, match="does not pair"):
        _preflight_fastqs(r1, r2)


def test_preflight_fastqs_rejects_unequal_read_counts(tmp_path: Path) -> None:
    r1, r2 = _pair(
        tmp_path,
        r1=[(_HDR, "ACGT", "IIII"), ("@r2", "TTTT", "IIII")],
        r2=[(_HDR, "GGGG", "IIII")],  # R1 has one more read
    )
    with pytest.raises(SystemExit, match="length mismatch"):
        _preflight_fastqs(r1, r2)


def test_preflight_fastqs_rejects_same_file_for_both_mates(tmp_path: Path) -> None:
    r1 = _write_fastq(tmp_path / "R1.fastq.gz", [(_HDR, "ACGT", "IIII")])
    with pytest.raises(SystemExit, match="SAME file"):
        _preflight_fastqs(r1, r1)


def test_preflight_fastqs_rejects_empty_file(tmp_path: Path) -> None:
    r1 = tmp_path / "R1.fastq.gz"
    r1.write_bytes(b"")
    r2 = _write_fastq(tmp_path / "R2.fastq.gz", [(_HDR, "ACGT", "IIII")])
    with pytest.raises(SystemExit, match="empty"):
        _preflight_fastqs(r1, r2)


def test_preflight_fastqs_handles_plain_uncompressed_fastq(tmp_path: Path) -> None:
    # Magic-byte detection (not extension): a plain .fastq must still validate.
    r1 = _write_fastq(tmp_path / "R1.fastq", [(_HDR, "ACGT", "IIII")], gzipped=False)
    r2 = _write_fastq(tmp_path / "R2.fastq", [(_HDR, "GGGG", "IIII")], gzipped=False)
    _preflight_fastqs(r1, r2)  # must NOT raise


# ------------------------------------------------------------------ P3-4: contig pre-flight


def _write_ref_with_fai(tmp: Path, contigs: list[str]) -> Path:
    ref = tmp / "ref.fa"
    ref.write_text("".join(f">{c}\nACGT\n" for c in contigs), encoding="utf-8")
    Path(f"{ref}.fai").write_text("".join(f"{c}\t4\t0\t4\t5\n" for c in contigs), encoding="utf-8")
    return ref


def _write_bed(tmp: Path, contigs: list[str]) -> Path:
    bed = tmp / "panel.bed"
    body = "# a comment header\n" + "".join(f"{c}\t100\t200\twin\n" for c in contigs)
    bed.write_text(body, encoding="utf-8")
    return bed


def test_preflight_contigs_accepts_matching_naming(tmp_path: Path) -> None:
    ref = _write_ref_with_fai(tmp_path, ["chr20"])
    bed = _write_bed(tmp_path, ["chr20"])
    _preflight_contigs(ref, bed)  # must NOT raise


def test_preflight_contigs_rejects_build_naming_mismatch(tmp_path: Path) -> None:
    ref = _write_ref_with_fai(tmp_path, ["chr20"])  # reference has 'chr20'
    bed = _write_bed(tmp_path, ["20"])  # panel BED has '20' — the classic silent ~0% breadth trap
    with pytest.raises(SystemExit, match=r"naming mismatch|absent from reference"):
        _preflight_contigs(ref, bed)


def test_preflight_contigs_falls_back_to_fasta_headers_without_fai(tmp_path: Path) -> None:
    ref = tmp_path / "ref.fa"
    ref.write_text(">chr20 description\nACGT\n", encoding="utf-8")  # no .fai sidecar
    bed = _write_bed(tmp_path, ["chr20"])
    _preflight_contigs(ref, bed)  # must NOT raise (header parse)


# ------------------------------------------------------------ P3-5: reference-index pre-flight


def _write_full_index(tmp: Path) -> Path:
    ref = tmp / "ref.fa"
    ref.write_text(">chr20\nACGT\n", encoding="utf-8")
    for sfx in _REQUIRED_INDEX_SUFFIXES:
        Path(f"{ref}{sfx}").write_text("x", encoding="utf-8")
    return ref


def test_preflight_reference_index_accepts_full_index(tmp_path: Path) -> None:
    _preflight_reference_index(_write_full_index(tmp_path))  # must NOT raise


def test_preflight_reference_index_rejects_missing_sidecar(tmp_path: Path) -> None:
    ref = _write_full_index(tmp_path)
    Path(f"{ref}.bwt.2bit.64").unlink()  # drop the bwa-mem2 index
    with pytest.raises(SystemExit, match=r"index sidecar\(s\) missing"):
        _preflight_reference_index(ref)


# ------------------------------------------------------------ P3-6: reproducibility capture


def test_probe_version_records_a_missing_tool_without_raising() -> None:
    line = _probe_version("definitely-not-a-real-tool", ["definitely-not-a-real-tool", "--version"])
    assert line == "definitely-not-a-real-tool: not found on PATH"


def test_capture_versions_writes_a_run_versions_file(tmp_path: Path) -> None:
    cfg = RunConfig(
        run_id="RUN-TEST",
        run_dir=tmp_path / "run",
        platform="HiSeq 2500",
        run_date="2026-07-11",
        submitted_by="tester",
    )
    capture_versions(cfg)
    text = (cfg.run_dir / "versions.txt").read_text()
    assert "NOT a re-pin" in text  # honest label: capture, not a re-pin
    assert "python:" in text
    assert "nextflow:" in text  # a probe line exists even when nextflow is absent


# ------------------------------------------------------ P3-9: honest fixture-authored note


def test_sample_metadata_is_marked_fixture_authored_and_stays_parseable(tmp_path: Path) -> None:
    from pipeguard.parsers import parse_sample_metadata

    cfg = RunConfig(
        run_id="RUN-TEST",
        run_dir=tmp_path / "run",
        platform="HiSeq 2500",
        run_date="2026-07-11",
        submitted_by="tester",
        sample="HG002",
    )
    write_run_dir(cfg, 90.0, 99.0, 50.0, 1.0, 1000, 0.9, 0.8)
    meta_path = cfg.run_dir / "sample_metadata.csv"
    text = meta_path.read_text()
    # The marker is IN the generated file (header column + placeholder value)...
    assert "metadata_origin" in text
    assert "fixture-authored-placeholder" in text
    # ...and the core parser still reads the sample cleanly (no '#' header-row breakage).
    samples = parse_sample_metadata(meta_path)
    assert len(samples) == 1
    assert samples[0].sample_id == "HG002"
    assert samples[0].tissue == "blood"
    assert samples[0].extra.get("metadata_origin") == "fixture-authored-placeholder"
