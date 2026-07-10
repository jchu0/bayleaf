"""Run the REAL GIAB HG002 panel fastqs through the *outlined* germline pipeline, end to end.

Unlike ``gate_giab.py`` (which reads the pre-aligned NIST panel BAM), this actually executes the
Pipeline-Builder chain from raw reads on real GIAB HG002 panel fastqs:

    fastp  →  bwa-mem2 mem  →  samtools fixmate/markdup  →  {mosdepth, bcftools call → norm}

then writes a **dashboard-discoverable** run directory (``data/<run_id>/`` with the frozen-five
CSV contract + a narrated ``pipeline.log`` + an ``origin`` tag) and runs it through the *unchanged*
``run_gate`` with the default runbook — the same recompute the read-API serves. So the run shows
up in the operator UI exactly like a mock run, but every number is derived from real reads.

Compose ≠ execute stays intact: this is a standalone driver of the external toolchain (bioconda),
not the app running a tool. The app only ingests the ``run/`` outputs it produces.

Prereqs (bioconda, e.g. the ``hackathon`` conda env on PATH): ``fastp``, ``bwa-mem2``,
``samtools``, ``mosdepth``, ``bcftools``; the chr20 reference indexed under
``data/real-giab/ref/chr20.fa`` (see the module for how it was built); the raw panel fastqs under
``data/real-giab/fastq/``. Nothing raw is committed — reference + intermediates are git-ignored.

    PATH=/path/to/hackathon/bin:$PATH uv run python scripts/run_giab_pipeline.py
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
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
_WORK = _GIAB / "pipeline"  # intermediates (git-ignored)

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


def _tool(name: str) -> str:
    p = shutil.which(name)
    if p is None:
        sys.exit(
            f"{name} not found on PATH. Put the bioconda env on PATH, e.g.\n"
            f"  PATH=/path/to/miniconda3/envs/hackathon/bin:$PATH uv run python {__file__}"
        )
    return p


def _log(stage: str, msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} [{level}] {stage}: {msg}"
    _LOG.append(line)
    print(line)


def _tool_version(tool: str, name: str) -> str:
    """Best-effort version string for the pipeline.log provenance."""
    # Pull the first version-looking token (e.g. 1.3.6 / 2.2.1) from either --version or the
    # `version` subcommand, whichever the tool supports — robust across fastp/bwa-mem2/samtools/
    # mosdepth/bcftools without per-tool special-casing.
    del name  # unused; kept for call-site readability
    for args in ([tool, "--version"], [tool, "version"]):
        try:
            out = subprocess.run(args, capture_output=True, text=True, timeout=20)
            m = re.search(r"\b\d+\.\d+(?:\.\d+)?\b", f"{out.stdout}\n{out.stderr}")
            if m:
                return m.group(0)
        except Exception:
            continue
    return "unknown"


def step_fastp() -> Path:
    """fastp: adapter/quality trim + read-level QC (Q30, dup, reads-passing-filter)."""
    _WORK.mkdir(parents=True, exist_ok=True)
    fastp = _tool("fastp")
    tr1, tr2 = _WORK / "HG002.trim.R1.fastq.gz", _WORK / "HG002.trim.R2.fastq.gz"
    fastp_json = _WORK / "HG002.fastp.json"
    _log("fastp", f"trimming raw reads (v{_tool_version(fastp, 'fastp')})")
    subprocess.run(
        [fastp, "-i", str(_RAW_R1), "-I", str(_RAW_R2), "-o", str(tr1), "-O", str(tr2),
         "-j", str(fastp_json), "-h", str(_WORK / "HG002.fastp.html"), "-w", "3"],
        check=True, capture_output=True,
    )  # fmt: skip
    return fastp_json


def step_align_markdup() -> Path:
    """bwa-mem2 mem → coordinate sort → fixmate → markdup → indexed dedup BAM."""
    bwa, samtools = _tool("bwa-mem2"), _tool("samtools")
    tr1, tr2 = _WORK / "HG002.trim.R1.fastq.gz", _WORK / "HG002.trim.R2.fastq.gz"
    dedup = _WORK / "HG002.dedup.bam"
    rg = f"@RG\\tID:{_SAMPLE}\\tSM:{_SAMPLE}\\tPL:ILLUMINA\\tLB:{_SAMPLE}-panel"
    _log("bwa-mem2", f"aligning to chr20 (v{_tool_version(bwa, 'bwa-mem2')})")
    # bwa-mem2 mem | name-sort → fixmate (-m adds mate score/coord) → coord-sort → markdup.
    aln = subprocess.Popen(
        [bwa, "mem", "-t", "4", "-R", rg, str(_REF), str(tr1), str(tr2)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    nsort = subprocess.Popen(
        [samtools, "sort", "-n", "-@", "2", "-O", "bam", "-"],
        stdin=aln.stdout,
        stdout=subprocess.PIPE,
    )
    fix = subprocess.Popen(
        [samtools, "fixmate", "-m", "-", "-"],
        stdin=nsort.stdout,
        stdout=subprocess.PIPE,
    )
    csort = subprocess.Popen(
        [samtools, "sort", "-@", "2", "-O", "bam", "-"],
        stdin=fix.stdout,
        stdout=subprocess.PIPE,
    )
    markdup_stats = _WORK / "HG002.markdup.txt"
    _log("samtools markdup", "flagging optical/PCR duplicates")
    subprocess.run(
        [samtools, "markdup", "-f", str(markdup_stats), "-", str(dedup)],
        stdin=csort.stdout,
        check=True,
    )
    for p in (aln, nsort, fix, csort):
        p.stdout and p.stdout.close()
        p.wait()
    subprocess.run([samtools, "index", str(dedup)], check=True)
    # Read count actually placed on chr20 (a real "reads through the aligner" number for the log).
    mapped = subprocess.run(
        [samtools, "view", "-c", "-F", "0x904", str(dedup)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _log("samtools markdup", f"{mapped} primary mapped reads in the dedup BAM")
    return dedup


def step_mosdepth(dedup: Path) -> tuple[float, float, float]:
    """mosdepth --by <panel>: mean panel coverage + 20x/30x breadth."""
    mosdepth = _tool("mosdepth")
    prefix = _WORK / "HG002.panel"
    _log("mosdepth", f"panel coverage (v{_tool_version(mosdepth, 'mosdepth')})")
    subprocess.run(
        [mosdepth, "--by", str(_PANEL_BED), "--no-per-base", "--thresholds", "1,10,20,30",
         "-t", "2", str(prefix), str(dedup)],
        check=True, capture_output=True,
    )  # fmt: skip
    mean = 0.0
    for line in Path(f"{prefix}.mosdepth.summary.txt").read_text().splitlines():
        if line.startswith("total_region\t"):
            mean = float(line.split("\t")[3])
    total = ge20 = ge30 = 0
    with gzip.open(f"{prefix}.thresholds.bed.gz", "rt") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            total += int(c[2]) - int(c[1])
            ge20 += int(c[6])
            ge30 += int(c[7])
    b20 = ge20 / total if total else 0.0
    b30 = ge30 / total if total else 0.0
    _log("mosdepth", f"mean {mean:.1f}x, breadth {b20 * 100:.1f}% >=20x / {b30 * 100:.1f}% >=30x")
    return mean, b20, b30


def step_variants(dedup: Path) -> int:
    """bcftools mpileup | call -mv → norm: normalized panel variants (count for the log)."""
    bcftools = _tool("bcftools")
    calls = _WORK / "HG002.calls.vcf.gz"
    norm = _WORK / "HG002.norm.vcf.gz"
    _log("bcftools call", f"variant calling on panel (v{_tool_version(bcftools, 'bcftools')})")
    mpileup = subprocess.Popen(
        [bcftools, "mpileup", "-f", str(_REF), "-R", str(_PANEL_BED), "-Ou", str(dedup)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [bcftools, "call", "-mv", "-Oz", "-o", str(calls)],
        stdin=mpileup.stdout,
        check=True,
        stderr=subprocess.DEVNULL,
    )
    mpileup.stdout and mpileup.stdout.close()
    mpileup.wait()
    _log("bcftools norm", "left-aligning + normalizing variants")
    subprocess.run(
        [bcftools, "norm", "-f", str(_REF), "-Oz", "-o", str(norm), str(calls)],
        check=True,
        capture_output=True,
    )
    subprocess.run([bcftools, "index", "-f", str(norm)], check=True, capture_output=True)
    n = subprocess.run(
        [bcftools, "view", "-H", str(norm)], capture_output=True, text=True, check=True
    ).stdout.count("\n")
    _log("bcftools norm", f"{n} normalized variants in the panel")
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
    fastp_json = step_fastp()
    dedup = step_align_markdup()
    coverage, b20, b30 = step_mosdepth(dedup)
    n_variants = step_variants(dedup)
    q30, reads_pf, dup, total_reads = parse_fastp(fastp_json)
    _log(
        "gate",
        f"handing the run/ outputs to run_gate (Q30 {q30:.1f}%, reads-PF {reads_pf:.1f}%, "
        f"cov {coverage:.1f}x, dup {dup:.3f}%, {n_variants} variants)",
    )
    write_run_dir(cfg, q30, reads_pf, coverage, dup, total_reads, b20, b30)

    _, cards = run_gate_from_dir(cfg.run_dir)  # default runbook — the read-API's recompute
    card = cards[0]

    print("\n=== REAL GIAB HG002 panel fastqs → outlined pipeline → gate ===")
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
