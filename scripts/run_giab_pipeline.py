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

Compose ≠ execute stays intact at the CORE: ``src/bayleaf/`` never runs a tool; this standalone
driver (in ``scripts/``, outside the core) shells out to Nextflow, which orchestrates the toolchain.

Prereqs: ``nextflow`` + a JRE and the bioconda tools (``fastp``, ``bwa-mem2``, ``samtools``,
``mosdepth``, ``bcftools``, ``multiqc``) on PATH — e.g. the ``hackathon`` conda env; the chr20
reference indexed under ``data/real-giab/ref/chr20.fa``; the raw panel fastqs under
``data/real-giab/fastq/``. Nothing raw is committed — reference + intermediates are git-ignored.

    PATH=/path/to/hackathon/bin:$PATH uv run python scripts/run_giab_pipeline.py
"""

from __future__ import annotations

import argparse
import glob
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

from bayleaf import run_gate_from_dir

_REPO = Path(__file__).resolve().parent.parent
_GIAB = _REPO / "data" / "real-giab"
_REF = _GIAB / "ref" / "chr20.fa"
_RAW_R1 = _GIAB / "fastq" / "HG002.R1.fastq.gz"
_RAW_R2 = _GIAB / "fastq" / "HG002.R2.fastq.gz"
_PANEL_BED = _REPO / "scripts" / "panel_regions.example.bed"

# The GIAB samples with panel-scale reads on disk (data/real-giab/fastq/, git-ignored). The live
# driver can run ANY subset as a real multi-sample flowcell — each row aligns against the shared
# chr20 reference + panel BED. HG002 is the Ashkenazim son; HG003/HG004 are the father/mother (same
# panel slice, fetched by scripts/fetch_panel_fastq.sh — reads never committed). This is the single
# source of truth for which samples the API may process (api/routers/intake.py imports the ids).
_GIAB_SAMPLE_READS: dict[str, tuple[Path, Path]] = {
    "HG002": (_GIAB / "fastq" / "HG002.R1.fastq.gz", _GIAB / "fastq" / "HG002.R2.fastq.gz"),
    "HG003": (_GIAB / "fastq" / "HG003.R1.fastq.gz", _GIAB / "fastq" / "HG003.R2.fastq.gz"),
    "HG004": (_GIAB / "fastq" / "HG004.R1.fastq.gz", _GIAB / "fastq" / "HG004.R2.fastq.gz"),
}
GIAB_SAMPLE_IDS: frozenset[str] = frozenset(_GIAB_SAMPLE_READS)

# Per-run UPSTREAM declaration → the metric-registry source classes it declares ABSENT. A
# ``fastq_only`` run (analysis starts from FASTQ, no Illumina/SAV instrument feed) declares the
# ``sav_interop`` class absent, so the gate NOTES the missing cluster-PF instead of HOLDing on it
# (bayleaf.runbook.Runbook.waive_source_classes). ``sequencer`` (default) waives nothing — every
# metric expected, a missing required one HOLDs. Written into the run dir as run_policy.json.
_UPSTREAM_WAIVERS: dict[str, list[str]] = {"sequencer": [], "fastq_only": ["sav_interop"]}
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
    # Per-run upstream declaration (``sequencer`` | ``fastq_only``). Recorded into the run dir as
    # run_policy.json so the gate can waive the declared-absent metric class (_UPSTREAM_WAIVERS).
    upstream: str = "sequencer"
    # Optional multi-sample set: (sample_id, r1, r2) rows. Empty → the single (sample, read1, read2)
    # above (the Builder-run + single-sample path, byte-identical). When set, the driver writes an
    # N-row Nextflow samplesheet and fans out per sample (parse/write/gate is already N-way).
    samples: tuple[tuple[str, Path, Path], ...] = ()

    def sample_rows(self) -> list[tuple[str, Path, Path]]:
        """The (sample, r1, r2) rows: the multi-sample set if set, else the single default."""
        if self.samples:
            return list(self.samples)
        return [(self.sample, self.read1, self.read2)]


@dataclass(frozen=True)
class SampleMetrics:
    """One sample's parsed QC — the unit of the W4 multi-sample fan-out. The published pipeline
    names every per-sample output ``${meta.id}.*`` (nf-core ``[meta, files]``), so an N-sample run
    yields N of these, one per discovered sample. A fan-out of 1 (the live HG002 driver) yields
    exactly one, which the run-dir writer emits BYTE-IDENTICALLY to the pre-fan-out driver.
    ``n_variants`` is carried for the run log only — it is not a frozen-five column."""

    sample: str
    q30: float
    reads_pf: float
    coverage: float
    dup: float
    total_reads: int
    b20: float
    b30: float
    n_variants: int = 0


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
    a JRE + the bioconda tools must be on PATH (the intake endpoint injects BAYLEAF_BIOCONDA_BIN).
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
    # --read1/--read2. This live driver still writes a SINGLE-row sheet (only HG002 has panel reads
    # on disk), so the actual Nextflow run is a fan-out of 1 — the emitted outputs are named
    # ${meta.id}.* = HG002.*. The POST-run parse (parse_publish_dir) is now genuinely N-sample
    # capable: it discovers every ${id}.fastp.json in the publish dir and writes one run-dir row per
    # sample, so the moment a multi-sample sheet (multiple read pairs on disk) is handed in, an
    # N-sample run yields N gated cards. That multi-read-pair live input is the env-gated piece.
    samplesheet = scratch / "samplesheet.csv"
    rows = cfg.sample_rows()
    samplesheet.write_text(
        "sample,fastq_1,fastq_2\n" + "".join(f"{s},{r1},{r2}\n" for s, r1, r2 in rows),
        encoding="utf-8",
        newline="\n",
    )
    # Executor auto-detected at the run boundary; no cluster here → the local-serial fallback.
    profile = _detect_profile()
    ids = [s for s, _r1, _r2 in rows]
    _log(
        "nextflow",
        f"nextflow run {cfg.pipeline.name} — {len(rows)} sample(s) {ids} · -profile {profile}",
    )
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


def _one_for(results: Path, sample: str, pattern: str) -> Path:
    """The single published output for ``sample`` matching ``{sample}.{pattern}``.

    The sample-id **dot prefix** anchors the match so a shared-prefix pair like ``S1``/``S10`` never
    cross-captures (``S1.*`` cannot match ``S10.…`` — the char after ``S1`` is ``0``, not ``.``);
    ``glob.escape`` neutralizes any metachar in a sample id. An ABSENT output is a hard error: a
    partial publish dir (a sample missing one of its per-sample files) FAILS LOUD here rather than
    silently dropping the sample or fabricating a metric.
    """
    hits = sorted(results.glob(f"{glob.escape(sample)}.{pattern}"))
    if not hits:
        sys.exit(
            f"expected a published output for sample {sample!r} matching "
            f"'{sample}.{pattern}' under {results} — the publish dir is partial for this sample"
        )
    return hits[0]


def discover_samples(results: Path) -> list[str]:
    """Every sample id published under ``results``, discovered from the per-sample
    ``${id}.fastp.json`` (the fan-out's canonical first-stage per-sample artifact). Sorted so the
    run-dir row order is stable. An EMPTY publish dir (no fastp output at all) fails loud."""
    ids = sorted(p.name[: -len(".fastp.json")] for p in results.glob("*.fastp.json"))
    if not ids:
        sys.exit(
            f"no per-sample outputs found under {results} (expected at least one *.fastp.json)"
        )
    return ids


# The post-run parse contract, as ONE constant both the parser and the execution routers share so
# they can never drift. Each entry maps a Builder output-artifact KIND → the published-file GLOB
# ``parse_sample`` reads for it (relative to a sample's ``<sample>.`` prefix, via ``_one_for``).
# This is the frozen-five gate contract: a run dir needs all four to yield a gate-able card (fastp →
# Q30/reads-PF/dup/total-reads, mosdepth_summary → mean coverage, mosdepth_thresholds → 20x/30x
# breadth, filtered_vcf → variant count). The API rejects (422) at SUBMIT any authored pipeline that
# does not PRODUCE all these kinds — so a non-germline-shaped graph fails fast up front instead of
# running to completion in Nextflow then dying HERE at parse with no card (WS-09). The globs are
# unchanged from the pre-WS-09 literals, so the germline reference parse is byte-identical.
_FROZEN_FIVE_OUTPUTS: dict[str, str] = {
    "fastp_json": "fastp.json",
    "mosdepth_summary": "*mosdepth.summary.txt",
    "mosdepth_thresholds": "*thresholds.bed.gz",
    "filtered_vcf": "norm.vcf.gz",
}
# The artifact-kinds an authored graph must PRODUCE to be gate-able (the keys of the map above).
REQUIRED_OUTPUT_KINDS: frozenset[str] = frozenset(_FROZEN_FIVE_OUTPUTS)


def parse_sample(results: Path, sample: str) -> SampleMetrics:
    """Parse ONE sample's published frozen-five inputs into a :class:`SampleMetrics`. Reuses the
    per-file parsers over the shared ``_FROZEN_FIVE_OUTPUTS`` globs (the same constant the submit
    gate validates against, so the two can't drift); every per-sample output is required
    (``_one_for`` fails loud on a missing one), so a partial publish dir never yields a fabricated
    or half-populated sample."""
    q30, reads_pf, dup, total_reads = parse_fastp(
        _one_for(results, sample, _FROZEN_FIVE_OUTPUTS["fastp_json"])
    )
    coverage, b20, b30 = parse_mosdepth(
        _one_for(results, sample, _FROZEN_FIVE_OUTPUTS["mosdepth_summary"]),
        _one_for(results, sample, _FROZEN_FIVE_OUTPUTS["mosdepth_thresholds"]),
    )
    n_variants = count_variants(_one_for(results, sample, _FROZEN_FIVE_OUTPUTS["filtered_vcf"]))
    return SampleMetrics(sample, q30, reads_pf, coverage, dup, total_reads, b20, b30, n_variants)


def parse_publish_dir(results: Path) -> list[SampleMetrics]:
    """Discover ALL samples in the published output and parse each into a :class:`SampleMetrics`.

    An N-sample fan-out yields N records (→ N gated cards from one run dir); a fan-out of 1 yields
    exactly one, so the HG002 path is unchanged. Loud on an empty publish dir (``discover_samples``)
    or a sample with a missing per-sample output (``_one_for``) — the honest failure the guardrail
    requires, never a silent drop.
    """
    return [parse_sample(results, s) for s in discover_samples(results)]


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


def write_run_dir_multi(cfg: RunConfig, samples: list[SampleMetrics]) -> None:
    """Write the ONE run dir the read-API discovers + gates (data/<run_id>/), holding one row per
    sample across every frozen-five file.

    This is the flowcell model: one sequencing run → one run dir → N samples (exactly what a demux
    produces, and what ``data/mock_run_01`` already is — S1..S5 in one dir). The gate reads
    ``qc_metrics.csv`` row-by-row and emits one card per sample, so an N-sample run yields N gated
    results without any read-API or gate change. A **fan-out of 1** emits BYTE-IDENTICAL output to
    the pre-fan-out single-sample driver (the ``write_run_dir`` wrapper below preserves that path).

    Beyond the frozen five, ``qc_metrics.csv`` also carries the REAL breadth-of-coverage metrics
    mosdepth computed per sample (breadth_20x/30x) — honest extra QC from each sample's own data
    (not contrived). ``cluster_pf`` stays blank (a run-level SAV metric not derivable from reads).
    ``demux_stats.csv``'s ``% Reads`` is each sample's share of the run's total reads (100% for a
    lone sample); ``sample_metadata.csv`` stays fixture-authored per the honesty note below.
    """
    if not samples:  # a defensive guard — parse_publish_dir already fails loud on an empty dir
        sys.exit("write_run_dir_multi: no samples to write (empty publish dir)")
    cfg.run_dir.mkdir(parents=True, exist_ok=True)

    def w(name: str, text: str) -> None:
        (cfg.run_dir / name).write_text(text, encoding="utf-8", newline="\n")

    w(
        "SampleSheet.csv",
        f"[Header]\nFileFormatVersion,2\nRunName,{cfg.run_id}\n"
        f"InstrumentPlatform,{cfg.platform}\nDate,{cfg.run_date}\n\n"
        "[Reads]\nRead1Cycles,250\nRead2Cycles,250\n\n"
        "[BCLConvert_Data]\nSample_ID,index,index2\n"
        + "".join(f"{s.sample},NA,NA\n" for s in samples),
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
        + "".join(
            f"{s.sample},{s.sample},blood,PCR-free,{cfg.submitted_by},"
            "fixture-authored-placeholder\n"
            for s in samples
        ),
    )
    # Real read counts from fastp; % Reads is each sample's share of the run total (100% for one).
    total_all = sum(s.total_reads for s in samples)

    def pct(reads: int) -> float:
        return (reads / total_all * 100.0) if total_all else 100.0

    w(
        "demux_stats.csv",
        "SampleID,Index,# Reads,% Reads\n"
        + "".join(f"{s.sample},NA,{s.total_reads},{pct(s.total_reads):.1f}\n" for s in samples),
    )
    # cluster_pf is a run-level SAV/InterOp metric not derivable from reads → left blank (honest).
    w(
        "qc_metrics.csv",
        "sample_id,q30,pct_reads_identified,mean_coverage,dup_rate,cluster_pf,"
        "breadth_20x,breadth_30x\n"
        + "".join(
            f"{s.sample},{s.q30:.2f},{s.reads_pf:.2f},{s.coverage:.1f},{s.dup:.4f},,"
            f"{s.b20:.4f},{s.b30:.4f}\n"
            for s in samples
        ),
    )
    w("pipeline.log", "\n".join(_LOG) + "\n")
    w("origin", f"{cfg.origin}\n")
    # Record the run's UPSTREAM policy so the gate (bayleaf.parsers.load_run) can waive the
    # declared-absent metric class. Written for EVERY run (an auditable declaration): ``sequencer``
    # records an empty waiver (no behavior change); ``fastq_only`` records the SAV class.
    w(
        "run_policy.json",
        json.dumps(
            {
                "upstream": cfg.upstream,
                "waived_metric_sources": _UPSTREAM_WAIVERS.get(cfg.upstream, []),
            },
            indent=2,
        )
        + "\n",
    )


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
    """Single-sample convenience wrapper over :func:`write_run_dir_multi`, kept as the stable
    scalar entrypoint (the offline preflight test calls it positionally). Packs the scalars into a
    one-sample list; for a fan-out of 1 the run dir is BYTE-IDENTICAL to the pre-fan-out driver."""
    write_run_dir_multi(
        cfg,
        [SampleMetrics(cfg.sample, q30, reads_pf, coverage, dup, total_reads, b20, b30)],
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a Nextflow pipeline into data/<run_id>/.")
    ap.add_argument("--run-id", default=_RUN_ID, help="run id / data dir name (slug)")
    ap.add_argument("--run-date", default=_RUN_DATE, help="ISO date for the [Header]")
    ap.add_argument("--platform", default=_PLATFORM, help="Illumina InstrumentPlatform")
    ap.add_argument("--submitted-by", default="giab", help="operator id for sample_metadata")
    ap.add_argument("--sample", default=_SAMPLE, help="sample id")
    ap.add_argument(
        "--samples", default="",
        help="comma-separated GIAB sample ids to run as ONE multi-sample flowcell (resolved to "
        "reads via the on-disk registry); overrides --sample/--read1/--read2 when set",
    )  # fmt: skip
    ap.add_argument("--pipeline", type=Path, default=_PIPELINE, help="Nextflow main.nf to run")
    ap.add_argument("--read1", type=Path, default=_RAW_R1, help="R1 fastq(.gz)")
    ap.add_argument("--read2", type=Path, default=_RAW_R2, help="R2 fastq(.gz)")
    ap.add_argument("--reference", type=Path, default=_REF, help="indexed reference FASTA")
    ap.add_argument("--panel-bed", type=Path, default=_PANEL_BED, help="panel BED")
    ap.add_argument("--origin", default="real-giab", help="provenance origin tag for the run dir")
    ap.add_argument(
        "--upstream", default="sequencer", choices=sorted(_UPSTREAM_WAIVERS),
        help="upstream declaration: 'sequencer' (default; all metrics expected) or 'fastq_only' "
        "(no Illumina/SAV feed → the SAV metric class is declared absent; gate notes, not holds)",
    )  # fmt: skip
    args = ap.parse_args()

    # --samples resolves a comma-separated id list to (id, r1, r2) rows via the on-disk registry, so
    # the API can run a real multi-sample flowcell (HG002+HG003+HG004). Absent → the single-sample
    # (sample/read1/read2) default, byte-identical to the pre-multi driver (the Builder-run path).
    multi: tuple[tuple[str, Path, Path], ...] = ()
    if args.samples.strip():
        rows: list[tuple[str, Path, Path]] = []
        for sid in (x.strip() for x in args.samples.split(",") if x.strip()):
            if sid not in _GIAB_SAMPLE_READS:
                sys.exit(
                    f"unknown sample {sid!r} — not in the on-disk GIAB registry "
                    f"{sorted(_GIAB_SAMPLE_READS)}. Fetch its panel reads first "
                    "(scripts/fetch_panel_fastq.sh)."
                )
            r1, r2 = _GIAB_SAMPLE_READS[sid]
            rows.append((sid, r1, r2))
        multi = tuple(rows)

    cfg = RunConfig(
        run_id=args.run_id,
        run_dir=_REPO / "data" / args.run_id,
        platform=args.platform,
        run_date=args.run_date,
        submitted_by=args.submitted_by,
        sample=multi[0][0] if multi else args.sample,
        pipeline=args.pipeline,
        read1=multi[0][1] if multi else args.read1,
        read2=multi[0][2] if multi else args.read2,
        reference=args.reference,
        panel_bed=args.panel_bed,
        origin=args.origin,
        upstream=args.upstream,
        samples=multi,
    )

    # Reference + panel are shared across samples (checked once); each sample's reads are checked in
    # the per-sample loop below so a missing fastq names the sample it belongs to.
    for path, hint in (
        (cfg.reference, "indexed reference FASTA missing"),
        (cfg.panel_bed, "panel BED missing"),
    ):
        if not path.exists():
            sys.exit(f"required input missing: {path} — {hint}")
    for sid, r1, r2 in cfg.sample_rows():
        for path, hint in ((r1, f"{sid} R1 fastq missing"), (r2, f"{sid} R2 fastq missing")):
            if not path.exists():
                sys.exit(f"required input missing: {path} — {hint}")

    ids = [s for s, _r1, _r2 in cfg.sample_rows()]
    _log("intake", f"registering run {cfg.run_id} — {len(ids)} sample(s) {ids}")
    # Pre-flight guards (P3-3/4/5) — fail LOUDLY before the Nextflow launch, never silently proceed.
    # Reference index + contig naming are shared (checked once); FASTQ pairing is per sample.
    _preflight_reference_index(cfg.reference)
    _preflight_contigs(cfg.reference, cfg.panel_bed)
    for _sid, r1, r2 in cfg.sample_rows():
        _preflight_fastqs(r1, r2)
    results = run_nextflow(cfg)
    # W4: discover + parse EVERY sample the pipeline published (one ${id}.fastp.json per sample).
    # A fan-out of 1 (this live HG002 driver) parses one; a multi-sample sheet would parse N. A
    # partial publish dir fails loud inside parse_publish_dir — never a fabricated metric.
    samples = parse_publish_dir(results)
    for s in samples:
        _log(
            "gate",
            f"handing {s.sample} to run_gate (Q30 {s.q30:.1f}%, reads-PF {s.reads_pf:.1f}%, "
            f"cov {s.coverage:.1f}x, dup {s.dup:.3f}%, {s.n_variants} variants)",
        )
    write_run_dir_multi(cfg, samples)  # ONE run dir, one row per sample (byte-identical for N=1)
    capture_versions(cfg)  # P3-6: snapshot the resolved tool/Nextflow versions that ran this run

    _, cards = run_gate_from_dir(cfg.run_dir)  # default runbook — the read-API's recompute

    n = len(samples)
    label = "HG002 panel fastqs" if n == 1 else f"{n} samples"
    print(f"\n=== REAL GIAB {label} → Nextflow germline pipeline → gate ===")
    for s in samples:
        print(f"\n  sample {s.sample}:")
        print(f"    reads (fastp in)    : {s.total_reads:,}")
        print(f"    Q30                 : {s.q30:.1f}%   (fastp)")
        print(f"    reads passing filter: {s.reads_pf:.1f}%   (fastp)")
        print(f"    mean coverage       : {s.coverage:.1f}x   (mosdepth --by panel, dedup BAM)")
        print(f"    duplication         : {s.dup:.3f}%  (fastp)")
        print(f"    breadth             : {s.b20 * 100:.1f}% >=20x, {s.b30 * 100:.1f}% >=30x")
        print(f"    variants (norm)     : {s.n_variants}   (bcftools call | norm)")
    print(f"\n  run dir: {cfg.run_dir.relative_to(_REPO)}  (discoverable by the read-API)")
    for card in cards:
        print(f"  sample {card.sample_id}: {card.verdict.value.upper()} — {card.headline}")
        for f in card.findings:
            print(f"    - [{f.severity.value}] {f.rule_id}: {f.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
