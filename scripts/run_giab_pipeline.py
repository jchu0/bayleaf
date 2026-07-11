"""Run the REAL GIAB HG002 panel fastqs through the germline pipeline **via Nextflow**, end to end.

This is the app's execution driver (``POST /api/runs`` triggers it). It is **Nextflow-first**: it
does NOT call fastp/bwa-mem2/samtools/… itself — it hands the whole chain to Nextflow by running the
generated pipeline at ``pipelines/germline/main.nf`` (the SAME artifact the Pipeline Builder emits
from its cards, ADR-0003), then parses the pipeline's published QC outputs into the frozen-five CSV
contract:

    nextflow run pipelines/germline/main.nf --read1 … --read2 … --reference … --panel_bed …
      → fastp → bwa-mem2 → samtools markdup → {mosdepth, bcftools call → norm} + MultiQC
      → parse fastp.json + mosdepth summary/thresholds → data/<run_id>/ (dashboard-discoverable)

then runs the run dir through the *unchanged* ``run_gate`` with the default runbook — the same
recompute the read-API serves. The run shows up in the operator UI like any other, but every number
is derived from real reads that flowed through a real Nextflow execution.

Compose ≠ execute stays intact at the CORE: ``src/pipeguard/`` never runs a tool; this standalone
driver (in ``scripts/``, outside the core) shells out to Nextflow, which orchestrates the toolchain.

Prereqs: ``nextflow`` + a JRE and the bioconda tools (``fastp``, ``bwa-mem2``, ``samtools``,
``mosdepth``, ``bcftools``, ``multiqc``) on PATH — e.g. the ``hackathon`` conda env; the chr20
reference indexed under ``data/real-giab/ref/chr20.fa``; the raw panel fastqs under
``data/real-giab/fastq/``. Nothing raw is committed — reference + intermediates are git-ignored.

    PATH=/path/to/hackathon/bin:$PATH uv run python scripts/run_giab_pipeline.py
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pipeguard import run_gate_from_dir

_REPO = Path(__file__).resolve().parent.parent
_GIAB = _REPO / "data" / "real-giab"
_REF = _GIAB / "ref" / "chr20.fa"
_RAW_R1 = _GIAB / "fastq" / "HG002.R1.fastq.gz"
_RAW_R2 = _GIAB / "fastq" / "HG002.R2.fastq.gz"
_PANEL_BED = _REPO / "scripts" / "panel_regions.example.bed"
_WORK = _GIAB / "pipeline"  # intermediates + the nextflow work/ dir (git-ignored)
_PIPELINE = _REPO / "pipelines" / "germline" / "main.nf"  # the Builder-generated pipeline, ADR-0003

_SAMPLE = "HG002"
_RUN_ID = "RUN-2026-07-08-GIAB-HG002"
_RUN_DIR = _REPO / "data" / _RUN_ID
_PLATFORM = "HiSeq 2500"  # the NIST 2x250bps instrument these reads come from
_RUN_DATE = "2026-07-08"


@dataclass(frozen=True)
class RunConfig:
    """Per-run identifiers — overridable via CLI so the API intake endpoint can drive a fresh run.
    The processed reads stay the HG002 panel fixtures; only the run's identity varies."""

    run_id: str
    run_dir: Path
    platform: str
    run_date: str
    submitted_by: str


_LOG: list[str] = []


def _log(stage: str, msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} [{level}] {stage}: {msg}"
    _LOG.append(line)
    print(line)


def _java_home(nextflow: Path) -> str | None:
    """The conda env's JAVA_HOME for the Nextflow launcher (``<env>/lib/jvm``, sibling of bin)."""
    candidate = nextflow.resolve().parent.parent / "lib" / "jvm"
    return str(candidate) if candidate.exists() else None


def run_nextflow() -> Path:
    """Hand the whole germline chain to Nextflow; return the published-results dir.

    Nextflow-first: the driver runs ``nextflow run pipelines/germline/main.nf`` — it does NOT invoke
    fastp/bwa-mem2/samtools/… itself. Each process publishes to ``<outdir>/results``. ``nextflow`` +
    a JRE + the bioconda tools must be on PATH (the intake endpoint injects PIPEGUARD_BIOCONDA_BIN).
    """
    nextflow = shutil.which("nextflow")
    if nextflow is None:
        sys.exit(
            "nextflow not found on PATH. Put an env with nextflow + a JRE + the bioconda tools on\n"
            f"  PATH, e.g. PATH=/path/to/envs/hackathon/bin:$PATH uv run python {__file__}"
        )
    if not _PIPELINE.exists():
        sys.exit(f"generated pipeline missing: {_PIPELINE} — run generate_reference_pipeline.py")
    _WORK.mkdir(parents=True, exist_ok=True)
    outdir = _WORK / "nf-out"
    env = os.environ.copy()
    java_home = _java_home(Path(nextflow))
    if java_home:
        env.setdefault("JAVA_HOME", java_home)  # the launcher needs a JVM the env may not export
    _log("nextflow", f"nextflow run {_PIPELINE.relative_to(_REPO)} — real HG002 panel reads")
    subprocess.run(
        [nextflow, "run", str(_PIPELINE), "-ansi-log", "false", "-work-dir", str(_WORK / "work"),
         "--sample", _SAMPLE, "--read1", str(_RAW_R1), "--read2", str(_RAW_R2),
         "--reference", str(_REF), "--panel_bed", str(_PANEL_BED), "--outdir", str(outdir)],
        check=True, cwd=_WORK, env=env,
    )  # fmt: skip
    results = outdir / "results"
    if not results.is_dir():
        sys.exit(f"nextflow run produced no results dir at {results}")
    _log("nextflow", "pipeline completed — parsing published QC outputs")
    return results


def _one(results: Path, pattern: str) -> Path:
    """The single published output matching ``pattern`` (an absent output is a hard error)."""
    hits = sorted(results.glob(pattern))
    if not hits:
        sys.exit(f"expected a pipeline output matching {pattern} under {results}")
    return hits[0]


def parse_mosdepth(summary: Path, thresholds: Path) -> tuple[float, float, float]:
    """Mean panel coverage + 20x/30x breadth from mosdepth's published summary + thresholds."""
    mean = 0.0
    for line in summary.read_text().splitlines():
        if line.startswith("total_region\t"):
            mean = float(line.split("\t")[3])
    total = ge20 = ge30 = 0
    with gzip.open(thresholds, "rt") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            total += int(c[2]) - int(c[1])
            ge20 += int(c[6])
            ge30 += int(c[7])
    b20 = ge20 / total if total else 0.0
    b30 = ge30 / total if total else 0.0
    return mean, b20, b30


def count_variants(norm_vcf: Path) -> int:
    """Normalized panel-variant count from the published norm VCF (bgzip is gzip-readable)."""
    n = 0
    with gzip.open(norm_vcf, "rt") as fh:
        for line in fh:
            if not line.startswith("#"):
                n += 1
    return n


def parse_fastp(fastp_json: Path) -> tuple[float, float, float, int]:
    d = json.loads(fastp_json.read_text())
    q30 = d["summary"]["after_filtering"]["q30_rate"] * 100.0
    before = d["summary"]["before_filtering"]["total_reads"]
    passed = d["filtering_result"]["passed_filter_reads"]
    reads_pf = (passed / before * 100.0) if before else 0.0
    dup = d["duplication"]["rate"] * 100.0
    return q30, reads_pf, dup, before


def write_run_dir(
    cfg: RunConfig,
    q30: float,
    reads_pf: float,
    coverage: float,
    dup: float,
    total_reads: int,
    b20: float,
    b30: float,
) -> None:
    """Write the run dir the read-API discovers + gates (data/<run_id>/).

    Beyond the frozen five, the QC report also carries the REAL breadth-of-coverage metrics mosdepth
    computed (breadth_20x/30x) — honest extra QC from this run's own data (not contrived), so the
    real card's QC group is richer than five rows. cluster_pf stays blank (a run-level SAV metric
    not derivable from reads).
    """
    cfg.run_dir.mkdir(parents=True, exist_ok=True)

    def w(name: str, text: str) -> None:
        (cfg.run_dir / name).write_text(text, encoding="utf-8", newline="\n")

    w(
        "SampleSheet.csv",
        f"[Header]\nFileFormatVersion,2\nRunName,{cfg.run_id}\n"
        f"InstrumentPlatform,{cfg.platform}\nDate,{cfg.run_date}\n\n"
        "[Reads]\nRead1Cycles,250\nRead2Cycles,250\n\n"
        "[BCLConvert_Data]\nSample_ID,index,index2\n"
        f"{_SAMPLE},NA,NA\n",
    )
    w(
        "sample_metadata.csv",
        "sample_id,subject_id,tissue,library_prep,submitted_by\n"
        f"{_SAMPLE},{_SAMPLE},blood,PCR-free,{cfg.submitted_by}\n",
    )
    # Real read count from fastp; single sample so 100% of reads are this sample.
    w("demux_stats.csv", f"SampleID,Index,# Reads,% Reads\n{_SAMPLE},NA,{total_reads},100.0\n")
    # cluster_pf is a run-level SAV/InterOp metric not derivable from reads → left blank (honest).
    w(
        "qc_metrics.csv",
        "sample_id,q30,pct_reads_identified,mean_coverage,dup_rate,cluster_pf,"
        "breadth_20x,breadth_30x\n"
        f"{_SAMPLE},{q30:.2f},{reads_pf:.2f},{coverage:.1f},{dup:.4f},,{b20:.4f},{b30:.4f}\n",
    )
    w("pipeline.log", "\n".join(_LOG) + "\n")
    w("origin", "real-giab\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the GIAB panel pipeline into data/<run_id>/.")
    ap.add_argument("--run-id", default=_RUN_ID, help="run id / data dir name (slug)")
    ap.add_argument("--run-date", default=_RUN_DATE, help="ISO date for the [Header]")
    ap.add_argument("--platform", default=_PLATFORM, help="Illumina InstrumentPlatform")
    ap.add_argument("--submitted-by", default="giab", help="operator id for sample_metadata")
    args = ap.parse_args()
    cfg = RunConfig(
        run_id=args.run_id,
        run_dir=_REPO / "data" / args.run_id,
        platform=args.platform,
        run_date=args.run_date,
        submitted_by=args.submitted_by,
    )

    for path, hint in (
        (_REF, "build the chr20 reference index first"),
        (_RAW_R1, "fetch the panel fastqs"),
        (_PANEL_BED, "missing panel BED"),
    ):
        if not path.exists():
            sys.exit(f"required input missing: {path} — {hint}")

    _log("intake", f"registering run {cfg.run_id} — sample {_SAMPLE} (real GIAB HG002 panel reads)")
    results = run_nextflow()
    q30, reads_pf, dup, total_reads = parse_fastp(_one(results, "*.fastp.json"))
    coverage, b20, b30 = parse_mosdepth(
        _one(results, "*.mosdepth.summary.txt"), _one(results, "*.thresholds.bed.gz")
    )
    n_variants = count_variants(_one(results, "*.norm.vcf.gz"))
    _log(
        "gate",
        f"handing the run/ outputs to run_gate (Q30 {q30:.1f}%, reads-PF {reads_pf:.1f}%, "
        f"cov {coverage:.1f}x, dup {dup:.3f}%, {n_variants} variants)",
    )
    write_run_dir(cfg, q30, reads_pf, coverage, dup, total_reads, b20, b30)

    _, cards = run_gate_from_dir(cfg.run_dir)  # default runbook — the read-API's recompute
    card = cards[0]

    print("\n=== REAL GIAB HG002 panel fastqs → Nextflow germline pipeline → gate ===")
    print(f"  reads (fastp in)    : {total_reads:,}")
    print(f"  Q30                 : {q30:.1f}%   (fastp)")
    print(f"  reads passing filter: {reads_pf:.1f}%   (fastp)")
    print(f"  mean coverage       : {coverage:.1f}x   (mosdepth --by panel, bwa-mem2 dedup BAM)")
    print(f"  duplication         : {dup:.3f}%  (fastp)")
    print(f"  breadth             : {b20 * 100:.1f}% >=20x, {b30 * 100:.1f}% >=30x")
    print(f"  variants (norm)     : {n_variants}   (bcftools call | norm)")
    print(f"\n  run dir: {cfg.run_dir.relative_to(_REPO)}  (discoverable by the read-API)")
    print(f"  sample {card.sample_id}: {card.verdict.value.upper()} — {card.headline}")
    for f in card.findings:
        print(f"    - [{f.severity.value}] {f.rule_id}: {f.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
