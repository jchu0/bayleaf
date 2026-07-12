"""Run the REAL GIAB HG002 panel fastqs through the germline pipeline **via Nextflow**, end to end.

This is the app's execution driver (``POST /api/runs`` triggers it). It is **Nextflow-first**: it
does NOT call fastp/bwa-mem2/samtools/… itself — it hands the whole chain to Nextflow by running the
generated pipeline at ``pipelines/germline/main.nf`` (the SAME artifact the Pipeline Builder emits
from its cards, ADR-0003), then parses the pipeline's published QC outputs into the frozen-five CSV
contract:

    nextflow run pipelines/germline/main.nf -profile <standard|slurm> --input samplesheet.csv …
      → per-sample fan-out (one chain per samplesheet row) via the auto-detected executor:
        `sbatch` on PATH → SLURM (a job per sample), else local single-thread-serial (W4)
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
from typing import IO

from pipeguard import run_gate_from_dir

_REPO = Path(__file__).resolve().parent.parent
_GIAB = _REPO / "data" / "real-giab"
_REF = _GIAB / "ref" / "chr20.fa"
_RAW_R1 = _GIAB / "fastq" / "HG002.R1.fastq.gz"
_RAW_R2 = _GIAB / "fastq" / "HG002.R2.fastq.gz"
_PANEL_BED = _REPO / "scripts" / "panel_regions.example.bed"
_WORK = _GIAB / "pipeline"  # intermediates + the nextflow work/ dir (git-ignored)
_NF_RUNS = _REPO / ".nf-runs"  # per-run Nextflow scratch (work/ + nf-out/), git-ignored
_PIPELINE = _REPO / "pipelines" / "germline" / "main.nf"  # the Builder-generated pipeline, ADR-0003

_SAMPLE = "HG002"
_RUN_ID = "RUN-2026-07-08-GIAB-HG002"
_RUN_DIR = _REPO / "data" / _RUN_ID
_PLATFORM = "HiSeq 2500"  # the NIST 2x250bps instrument these reads come from
_RUN_DATE = "2026-07-08"


@dataclass(frozen=True)
class RunConfig:
    """Per-run identity + the pipeline and inputs to run — all overridable via CLI so the API can
    drive a fresh run (the intake endpoint keeps the HG002 defaults; the Builder-run endpoint passes
    a compiled pipeline + operator-chosen inputs). Only the identity/pipeline/inputs vary."""

    run_id: str
    run_dir: Path
    platform: str
    run_date: str
    submitted_by: str
    sample: str = _SAMPLE
    pipeline: Path = _PIPELINE
    read1: Path = _RAW_R1
    read2: Path = _RAW_R2
    reference: Path = _REF
    panel_bed: Path = _PANEL_BED
    origin: str = "real-giab"  # provenance tag for the run dir; operator inputs may set another


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


def _detect_profile() -> str:
    """Pick the Nextflow executor profile for THIS host (W4, ADR-0003 — same graph, executor by
    profile). ``sbatch`` on PATH → ``slurm`` (one job per sample; per-sample parallel on an HPC
    submit node); otherwise ``standard`` — the local single-thread-serial fallback (one sample at a
    time). Mirrors the ``shutil.which("nextflow")`` probe; the compiled bundle is unchanged, only
    the executor is chosen here (compose ≠ execute). CONFIG-VERIFIED, not cluster-verified — this
    env has no ``sbatch``, so the demo always takes the local-serial branch."""
    return "slurm" if shutil.which("sbatch") else "standard"


# --------------------------------------------------------------------------------------------------
# Pre-flight guards (P3-3/P3-4/P3-5) — cheap, LOUD, and run BEFORE the Nextflow launch so a bad
# input fails in milliseconds with a clear message instead of burning a full launch that dies deep
# inside bwa-mem2 (or, worse, yields a silently-wrong result). Each raises SystemExit (via sys.exit,
# the driver's existing failure idiom) with an actionable message; none EVER silently proceeds. They
# are pure functions of their path args so they can be unit-tested without Nextflow on PATH.
# --------------------------------------------------------------------------------------------------

_GZIP_MAGIC = b"\x1f\x8b"

# The index sidecars the germline pipeline's reference channel needs on disk — `.fai` (samtools
# faidx, used by mosdepth/bcftools) plus the bwa-mem2 index set. main.nf globs `${reference}.*`, so
# a missing member would only surface as a bwa-mem2 crash mid-run; we assert them up front instead.
_REQUIRED_INDEX_SUFFIXES: tuple[str, ...] = (
    ".fai", ".0123", ".amb", ".ann", ".bwt.2bit.64", ".pac",
)  # fmt: skip

# Resolved-version probes (P3-6). Provenance capture only — these RECORD what is on PATH, they do
# NOT pin or change anything. bwa-mem2 uses the bare `version` subcommand; the rest take --version.
_VERSION_PROBES: tuple[tuple[str, list[str]], ...] = (
    ("nextflow", ["nextflow", "-version"]),
    ("fastp", ["fastp", "--version"]),
    ("bwa-mem2", ["bwa-mem2", "version"]),
    ("samtools", ["samtools", "--version"]),
    ("mosdepth", ["mosdepth", "--version"]),
    ("bcftools", ["bcftools", "--version"]),
    ("multiqc", ["multiqc", "--version"]),
)


def _open_maybe_gzip(path: Path) -> IO[str]:
    """Open a FASTQ/FASTA as text, detecting gzip by MAGIC BYTE (not extension) so a mislabelled
    file is handled honestly rather than mis-parsed."""
    with path.open("rb") as raw:
        is_gz = raw.read(2) == _GZIP_MAGIC
    if is_gz:
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def _read_id_core(header: str) -> str:
    """Normalize a FASTQ header to a MATE-INDEPENDENT read id for pairing comparison: drop the
    leading '@', any whitespace-delimited comment (Casava 1.8 '1:N:0:…'), and a trailing '/1'|'/2'
    mate suffix — so proper mates compare equal but two unrelated files do not."""
    core = header[1:] if header.startswith("@") else header
    parts = core.split()
    core = parts[0] if parts else core
    if core.endswith(("/1", "/2")):
        core = core[:-2]
    return core


def _next_record(fh: IO[str]) -> tuple[str, str, str, str] | None:
    """Read the next 4-line FASTQ record (header, seq, plus, qual); None at clean EOF."""
    header = fh.readline()
    if header == "":
        return None
    seq, plus, qual = fh.readline(), fh.readline(), fh.readline()
    return header.rstrip("\n"), seq.rstrip("\n"), plus.rstrip("\n"), qual.rstrip("\n")


def _validate_record(rec: tuple[str, str, str, str], label: str, path: Path, idx: int) -> None:
    """Structural FASTQ sanity for one record — catches non-FASTQ / truncated / corrupt input."""
    header, seq, plus, qual = rec
    if not header.startswith("@"):
        sys.exit(
            f"preflight: {label} ({path.name}) record {idx} is not FASTQ — header {header[:24]!r} "
            "does not start with '@'. Input is not FASTQ (or is corrupt); failing before launch."
        )
    if not plus.startswith("+"):
        sys.exit(
            f"preflight: {label} ({path.name}) record {idx} is malformed — 3rd line {plus[:24]!r} "
            "does not start with '+'. Truncated or non-FASTQ; failing before launch."
        )
    if len(seq) != len(qual):
        sys.exit(
            f"preflight: {label} ({path.name}) record {idx} seq/qual length mismatch "
            f"({len(seq)} vs {len(qual)}). Corrupt FASTQ; failing before launch."
        )


def _preflight_fastqs(read1: Path, read2: Path) -> None:
    """P3-3: R1/R2 exist + readable, look like FASTQ, and pass a pairing sanity check.

    A swapped/mismatched pair, a non-FASTQ input, or unequal mate counts must fail HERE with a clear
    message — not silently yield a wrong result downstream. Streams both files in lockstep,
    validating each record and comparing mate-independent read ids; equal read counts are the
    classic pairing gate. This is an O(reads) pass, acceptable at panel scale (and far cheaper than
    a Nextflow launch) — the driver is HG002-panel-scoped; a huge-WGS sampled-window variant is a
    later refinement.
    """
    for label, p in (("R1", read1), ("R2", read2)):
        if not p.is_file():
            sys.exit(f"preflight: {label} fastq is not a readable file: {p}")
        if p.stat().st_size == 0:
            sys.exit(f"preflight: {label} fastq is empty: {p}")
    if read1.resolve() == read2.resolve():
        sys.exit(f"preflight: R1 and R2 are the SAME file ({read1}) — that is not a read pair")

    n = 0
    with _open_maybe_gzip(read1) as fh1, _open_maybe_gzip(read2) as fh2:
        while True:
            rec1, rec2 = _next_record(fh1), _next_record(fh2)
            if rec1 is None and rec2 is None:
                break
            if rec1 is None or rec2 is None:
                longer = "R2" if rec1 is None else "R1"
                sys.exit(
                    f"preflight: FASTQ pair length mismatch — {longer} has more reads "
                    f"(R1={read1.name}, R2={read2.name}). Mates must have equal read counts; "
                    "the pair looks truncated or mismatched. Failing before launch."
                )
            _validate_record(rec1, "R1", read1, n)
            _validate_record(rec2, "R2", read2, n)
            id1, id2 = _read_id_core(rec1[0]), _read_id_core(rec2[0])
            if id1 != id2:
                sys.exit(
                    f"preflight: FASTQ read {n} does not pair — R1 id {id1!r} != R2 id {id2!r} "
                    f"(R1={read1.name}, R2={read2.name}). R1/R2 look swapped or from different "
                    "samples. Failing before launch."
                )
            n += 1
    if n == 0:
        sys.exit(f"preflight: no FASTQ records found in {read1.name} / {read2.name}")
    _log("preflight", f"FASTQ pair OK — {n} paired reads, ids matched ({read1.name}/{read2.name})")


def _reference_contigs(reference: Path) -> set[str]:
    """Contig names of the reference — from the `.fai` if present (cheap), else FASTA headers."""
    fai = Path(f"{reference}.fai")
    if fai.is_file():
        return {ln.split("\t")[0] for ln in fai.read_text().splitlines() if ln.strip()}
    contigs: set[str] = set()
    with _open_maybe_gzip(reference) as fh:
        for line in fh:
            if line.startswith(">"):
                contigs.add(line[1:].split()[0])
    return contigs


def _bed_contigs(panel_bed: Path) -> set[str]:
    """Contig names (col 1) of a BED, skipping comment / track / browser lines."""
    contigs: set[str] = set()
    for line in panel_bed.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "track", "browser")):
            continue
        contigs.add(s.split()[0])
    return contigs


def _preflight_contigs(reference: Path, panel_bed: Path) -> None:
    """P3-4: assert every panel-BED contig exists in the reference (e.g. '20' vs 'chr20').

    A reference/BED naming mismatch does not crash — it silently yields ~0% panel breadth (mosdepth
    finds no overlap), which is far worse than a loud failure. Fail here instead.
    """
    ref = _reference_contigs(reference)
    if not ref:
        sys.exit(
            f"preflight: could not read any contigs from reference {reference} "
            "(no .fai and no FASTA '>' headers). Cannot verify contig naming."
        )
    bed = _bed_contigs(panel_bed)
    if not bed:
        _log("preflight", f"panel BED {panel_bed.name} has no rows — skipping contig check", "WARN")
        return
    missing = sorted(bed - ref)
    if missing:
        sys.exit(
            f"preflight: panel BED contig(s) {missing} are absent from reference {reference.name} "
            f"(reference has {sorted(ref)[:8]}). Likely a build/naming mismatch (e.g. '20' vs "
            "'chr20') — this would yield a silent ~0% panel breadth. Fix the BED or the reference."
        )
    _log("preflight", f"contig naming OK — panel BED {sorted(bed)} is a subset of the reference")


def _preflight_reference_index(reference: Path) -> None:
    """P3-5: verify the reference index sidecars exist BEFORE the launch.

    Without these, the run would launch, run fastp, and only then die inside bwa-mem2 — burning the
    whole launch. Checking on disk first turns that into an instant, actionable failure.
    """
    missing = [sfx for sfx in _REQUIRED_INDEX_SUFFIXES if not Path(f"{reference}{sfx}").is_file()]
    if missing:
        sys.exit(
            f"preflight: reference index sidecar(s) missing for {reference.name}: {missing}. "
            f"Build them before launching: `samtools faidx {reference.name}` (.fai) and "
            f"`bwa-mem2 index {reference.name}` (.0123/.amb/.ann/.bwt.2bit.64/.pac). Failing now "
            "avoids a full Nextflow launch that would die in bwa-mem2."
        )
    _log("preflight", f"reference index OK — all sidecars present for {reference.name}")


def _probe_version(label: str, argv: list[str]) -> str:
    """Best-effort single version line for one tool. Tolerant by design: a missing or failing tool
    is RECORDED, never fatal — capturing provenance must not break a run."""
    exe = shutil.which(argv[0])
    if exe is None:
        return f"{label}: not found on PATH"
    try:
        out = subprocess.run(
            [exe, *argv[1:]], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - defensive
        return f"{label}: unavailable ({type(exc).__name__})"
    lines = [ln.strip() for ln in (out.stdout + out.stderr).splitlines() if ln.strip()]
    if not lines:
        return f"{label}: (no version output)"
    # Prefer a line mentioning "version" (nextflow/multiqc), else the first line (samtools/etc).
    chosen = next((ln for ln in lines if "version" in ln.lower()), lines[0])
    return f"{label}: {chosen}"


def capture_versions(cfg: RunConfig) -> None:
    """P3-6: record the RESOLVED tool/Nextflow versions that ran this run into `versions.txt`.

    Provenance capture ONLY — this RECORDS what was on PATH; it does NOT pin or change any container
    or conda tag (that is deliberately out of scope, Medium risk). "Deterministic reruns" for this
    project mean wiring + gate re-derivation, not bitwise-identical outputs — the module pins are
    floating tags + a version floor, so a per-run snapshot of what actually resolved is the honest
    reproducibility artifact. Every probe is best-effort (see `_probe_version`).
    """
    cfg.run_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# Resolved tool versions captured at run time (provenance, NOT a re-pin) {stamp}",
        f"# run_id: {cfg.run_id}",
        f"# pipeline: {cfg.pipeline}",
        f"python: {sys.version.split()[0]}",
    ]
    lines.extend(_probe_version(label, argv) for label, argv in _VERSION_PROBES)
    out = cfg.run_dir / "versions.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    _log("provenance", f"captured resolved tool versions -> {cfg.run_dir.name}/versions.txt")


def run_nextflow(cfg: RunConfig) -> Path:
    """Hand the whole chain to Nextflow; return the published-results dir.

    Nextflow-first: the driver runs ``nextflow run <cfg.pipeline>`` (the germline reference by
    default, or a Builder-compiled pipeline) against ``cfg``'s inputs — it does NOT invoke
    fastp/bwa-mem2/samtools/… itself. Each process publishes to ``<outdir>/results``. ``nextflow`` +
    a JRE + the bioconda tools must be on PATH (the intake endpoint injects PIPEGUARD_BIOCONDA_BIN).
    Work + outputs land in a per-run gitignored scratch dir so concurrent runs never collide.
    """
    nextflow = shutil.which("nextflow")
    if nextflow is None:
        sys.exit(
            "nextflow not found on PATH. Put an env with nextflow + a JRE + the bioconda tools on\n"
            f"  PATH, e.g. PATH=/path/to/envs/hackathon/bin:$PATH uv run python {__file__}"
        )
    if not cfg.pipeline.exists():
        sys.exit(f"pipeline missing: {cfg.pipeline} — compile a graph or generate the reference")
    scratch = _NF_RUNS / cfg.run_id
    scratch.mkdir(parents=True, exist_ok=True)
    outdir = scratch / "nf-out"
    env = os.environ.copy()
    java_home = _java_home(Path(nextflow))
    if java_home:
        env.setdefault("JAVA_HOME", java_home)  # the launcher needs a JVM the env may not export
    # Per-sample fan-out (W4): hand the pipeline a samplesheet (sample,fastq_1,fastq_2), not
    # --read1/--read2. This single-sample run is a degenerate fan-out of 1 — the emitted outputs
    # are named ${meta.id}.* = HG002.*, byte-identical to the pre-fan-out driver, so the frozen-five
    # parse below is unchanged (a multi-sample sheet + N-run-dir parse is the deferred slice).
    samplesheet = scratch / "samplesheet.csv"
    samplesheet.write_text(
        f"sample,fastq_1,fastq_2\n{cfg.sample},{cfg.read1},{cfg.read2}\n",
        encoding="utf-8",
        newline="\n",
    )
    # Executor auto-detected at the run boundary; no cluster here → the local-serial fallback.
    profile = _detect_profile()
    _log("nextflow", f"nextflow run {cfg.pipeline.name} — sample {cfg.sample} · -profile {profile}")
    cmd = [
        nextflow, "run", str(cfg.pipeline), "-ansi-log", "false", "-profile", profile,
        "-work-dir", str(scratch / "work"),
        "--input", str(samplesheet),
        "--reference", str(cfg.reference), "--panel_bed", str(cfg.panel_bed),
        "--outdir", str(outdir),
    ]  # fmt: skip
    subprocess.run(
        cmd,
        check=True, cwd=scratch, env=env,
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
        f"{cfg.sample},NA,NA\n",
    )
    # P3-9 HONESTY NOTE: this sample_metadata.csv is FIXTURE-AUTHORED, not real subject metadata.
    # The live driver has no LIMS/subject feed, so subject_id and tissue are PLACEHOLDERS: subj_id
    # is set to the sample_id and tissue is hardcoded 'blood' (true for HG002, but NOT sourced from
    # any subject record). The trailing `metadata_origin` column marks this IN THE FILE so a
    # downstream reader can never mistake it for accessioned subject data. We use an extra COLUMN
    # (parse-safe — it lands in Sample.extra) rather than a leading '#' comment line because the
    # core parser (parse_sample_metadata -> pd.read_csv, no comment= set) would read a '#' line as
    # the header row and drop every sample. Rewiring the driver to a real subject feed is a deferred
    # data-platform seam; the audit (P3-9) prefers this note over that rewire.
    w(
        "sample_metadata.csv",
        "sample_id,subject_id,tissue,library_prep,submitted_by,metadata_origin\n"
        f"{cfg.sample},{cfg.sample},blood,PCR-free,{cfg.submitted_by},"
        "fixture-authored-placeholder\n",
    )
    # Real read count from fastp; single sample so 100% of reads are this sample.
    w("demux_stats.csv", f"SampleID,Index,# Reads,% Reads\n{cfg.sample},NA,{total_reads},100.0\n")
    # cluster_pf is a run-level SAV/InterOp metric not derivable from reads → left blank (honest).
    w(
        "qc_metrics.csv",
        "sample_id,q30,pct_reads_identified,mean_coverage,dup_rate,cluster_pf,"
        "breadth_20x,breadth_30x\n"
        f"{cfg.sample},{q30:.2f},{reads_pf:.2f},{coverage:.1f},{dup:.4f},,{b20:.4f},{b30:.4f}\n",
    )
    w("pipeline.log", "\n".join(_LOG) + "\n")
    w("origin", f"{cfg.origin}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a Nextflow pipeline into data/<run_id>/.")
    ap.add_argument("--run-id", default=_RUN_ID, help="run id / data dir name (slug)")
    ap.add_argument("--run-date", default=_RUN_DATE, help="ISO date for the [Header]")
    ap.add_argument("--platform", default=_PLATFORM, help="Illumina InstrumentPlatform")
    ap.add_argument("--submitted-by", default="giab", help="operator id for sample_metadata")
    ap.add_argument("--sample", default=_SAMPLE, help="sample id")
    ap.add_argument("--pipeline", type=Path, default=_PIPELINE, help="Nextflow main.nf to run")
    ap.add_argument("--read1", type=Path, default=_RAW_R1, help="R1 fastq(.gz)")
    ap.add_argument("--read2", type=Path, default=_RAW_R2, help="R2 fastq(.gz)")
    ap.add_argument("--reference", type=Path, default=_REF, help="indexed reference FASTA")
    ap.add_argument("--panel-bed", type=Path, default=_PANEL_BED, help="panel BED")
    ap.add_argument("--origin", default="real-giab", help="provenance origin tag for the run dir")
    args = ap.parse_args()
    cfg = RunConfig(
        run_id=args.run_id,
        run_dir=_REPO / "data" / args.run_id,
        platform=args.platform,
        run_date=args.run_date,
        submitted_by=args.submitted_by,
        sample=args.sample,
        pipeline=args.pipeline,
        read1=args.read1,
        read2=args.read2,
        reference=args.reference,
        panel_bed=args.panel_bed,
        origin=args.origin,
    )

    for path, hint in (
        (cfg.reference, "indexed reference FASTA missing"),
        (cfg.read1, "R1 fastq missing"),
        (cfg.read2, "R2 fastq missing"),
        (cfg.panel_bed, "panel BED missing"),
    ):
        if not path.exists():
            sys.exit(f"required input missing: {path} — {hint}")

    _log("intake", f"registering run {cfg.run_id} — sample {cfg.sample}")
    # Pre-flight guards (P3-3/4/5) — fail LOUDLY before the Nextflow launch, never silently proceed.
    _preflight_reference_index(cfg.reference)
    _preflight_contigs(cfg.reference, cfg.panel_bed)
    _preflight_fastqs(cfg.read1, cfg.read2)
    results = run_nextflow(cfg)
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
    capture_versions(cfg)  # P3-6: snapshot the resolved tool/Nextflow versions that ran this run

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
