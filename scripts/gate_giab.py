"""Gate REAL GIAB HG002 panel data through the deterministic QC gate (T-017 / T-002b).

The "it works on real data, not just contrived runs" step. Given the panel-region reads
slice fetched by `fetch_giab_hg002.py --with-reads`, this derives REAL QC metrics from real
GIAB reads and runs them through the *existing* gate:

  1. `mosdepth --by <panel.bed>` → real in-panel **mean coverage + breadth**,
  2. `samtools fastq` (BAM → reads) + `fastp` → real **Q30 / duplication / reads-passing**,
  3. writes a small `real-giab` run directory (git-ignored) with those real numbers in the
     on-disk shape the parsers already read, and
  4. runs it through the gate with a runbook of the four metrics a fastq+BAM actually yields
     (cluster-PF is a run-level SAV metric, not derivable here), printing the decision.

Nothing here touches the core: it reuses `run_gate` and the registry-backed rules unchanged;
the registry normalizes each real value from its declared unit exactly as for a mock run.

Prereqs: `mosdepth` / `samtools` / `fastp` on PATH (bioconda) and the panel BAM already
fetched. NO data is committed — everything lands in the git-ignored `data/real-giab/`.

    python scripts/gate_giab.py
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import sys
from pathlib import Path

from bayleaf import Runbook, run_gate_from_dir
from bayleaf.runbook import QCThreshold

_REPO = Path(__file__).resolve().parent.parent
_GIAB = _REPO / "data" / "real-giab"
_BAM = _GIAB / "HG002.GRCh38.panel.bam"
_PANEL_BED = _REPO / "scripts" / "panel_regions.example.bed"
_MOSDEPTH_DIR = _GIAB / "mosdepth"
_PREFIX = _MOSDEPTH_DIR / "HG002.panel"
_FASTQ_DIR = _GIAB / "fastq"
_FASTP_JSON = _FASTQ_DIR / "HG002.fastp.json"
_RUN_DIR = _GIAB / "run"
_SAMPLE = "HG002"

# The four metrics a fastq + BAM actually yields, each keyed on its registry `our_key` and
# gated in the canonical unit (decimals for rates, x for coverage) exactly like the default
# runbook. `cluster_pf` is a run-level SAV/InterOp metric and is intentionally NOT gated here —
# it isn't derivable from reads alone, so gating it would be a spurious "missing".
_REAL_RUNBOOK = Runbook(
    require_metadata_fields=["subject_id"],
    qc_thresholds=[
        QCThreshold(
            metric="q30", our_key="qc.q30", label="Q30", gate=0.85, hard_fail=0.75, unit="%"
        ),
        QCThreshold(
            metric="pct_reads_identified",
            our_key="qc.reads_passing_filter",
            label="Reads passing filter",
            gate=0.70,
            hard_fail=0.50,
            unit="%",
        ),
        QCThreshold(
            metric="mean_coverage",
            our_key="qc.mean_target_coverage",
            label="Mean coverage",
            gate=30.0,
            hard_fail=15.0,
            unit="x",
        ),
        QCThreshold(
            metric="dup_rate",
            our_key="qc.duplication",
            label="Duplication rate",
            gate=0.30,
            hard_fail=0.50,
            higher_is_better=False,
            unit="%",
        ),
    ],
)


def _require_tool(name: str) -> str:
    tool = shutil.which(name)
    if tool is None:
        sys.exit(
            f"{name} not found on PATH. Install the genomics toolchain, e.g.\n"
            f"  conda install -n hackathon -c conda-forge -c bioconda mosdepth samtools fastp\n"
            f"  PATH=/path/to/env/bin:$PATH python scripts/gate_giab.py"
        )
    return tool


def _require_bam() -> None:
    if not _BAM.exists():
        sys.exit(
            f"panel BAM not found: {_BAM}\n"
            "Fetch it first:  python scripts/fetch_giab_hg002.py --with-reads "
            "--panel-bed scripts/panel_regions.example.bed"
        )


def run_mosdepth() -> None:
    """Run `mosdepth --by <panel.bed>` for per-region coverage + breadth thresholds."""
    _require_bam()
    _MOSDEPTH_DIR.mkdir(parents=True, exist_ok=True)
    if Path(f"{_PREFIX}.mosdepth.summary.txt").exists():
        print(f"mosdepth output exists, reusing {_PREFIX}.*")
        return
    mosdepth = _require_tool("mosdepth")
    cmd = [
        mosdepth, "--by", str(_PANEL_BED), "--no-per-base",
        "--thresholds", "1,10,20,30", "-t", "2", str(_PREFIX), str(_BAM),
    ]  # fmt: skip
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def parse_coverage() -> tuple[float, float, float]:
    """Return (mean_coverage, breadth_20x, breadth_30x) from the mosdepth output.

    Mean is the panel-region mean (`total_region` in the summary); breadth is the fraction of
    panel bases at >= N x, summed across the panel windows from the thresholds file.
    """
    mean = 0.0
    for line in Path(f"{_PREFIX}.mosdepth.summary.txt").read_text().splitlines():
        if line.startswith("total_region\t"):
            mean = float(line.split("\t")[3])
    total_bp = ge20 = ge30 = 0
    with gzip.open(f"{_PREFIX}.thresholds.bed.gz", "rt") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            start, end = int(c[1]), int(c[2])
            total_bp += end - start
            ge20 += int(c[6])  # 20X column
            ge30 += int(c[7])  # 30X column
    return mean, (ge20 / total_bp if total_bp else 0.0), (ge30 / total_bp if total_bp else 0.0)


def run_fastp() -> None:
    """BAM -> paired fastq (`samtools collate | fastq`) -> `fastp` for read-level QC."""
    _require_bam()
    if _FASTP_JSON.exists():
        print(f"fastp output exists, reusing {_FASTP_JSON}")
        return
    samtools = _require_tool("samtools")
    fastp = _require_tool("fastp")
    _FASTQ_DIR.mkdir(parents=True, exist_ok=True)
    r1, r2 = _FASTQ_DIR / "HG002.R1.fastq.gz", _FASTQ_DIR / "HG002.R2.fastq.gz"
    print("extracting fastq from the panel BAM (samtools collate | fastq)...")
    # Collate so mates are adjacent, then split to R1/R2 (drop singletons/secondaries).
    collate = [samtools, "collate", "-@", "2", "-O", str(_BAM)]
    to_fastq = [samtools, "fastq", "-1", str(r1), "-2", str(r2),
                "-0", "/dev/null", "-s", "/dev/null", "-n"]  # fmt: skip
    with subprocess.Popen(collate, stdout=subprocess.PIPE) as coll:
        subprocess.run(to_fastq, stdin=coll.stdout, check=True)
    print("running fastp...")
    fastp_cmd = [
        fastp, "-i", str(r1), "-I", str(r2),
        "-o", str(_FASTQ_DIR / "HG002.R1.trim.fastq.gz"),
        "-O", str(_FASTQ_DIR / "HG002.R2.trim.fastq.gz"),
        "-j", str(_FASTP_JSON), "-h", str(_FASTQ_DIR / "HG002.fastp.html"),
    ]  # fmt: skip
    subprocess.run(fastp_cmd, check=True)


def parse_fastp() -> tuple[float, float, float]:
    """Return (q30_pct, reads_passing_pct, duplication_pct) from fastp.json.

    fastp reports these as fractions; the run's qc_metrics.csv (like the mock runs) is in the
    percent convention the registry mapping declares for these keys, so scale to percent here.
    """
    d = json.loads(_FASTP_JSON.read_text())
    q30 = d["summary"]["after_filtering"]["q30_rate"] * 100.0
    before = d["summary"]["before_filtering"]["total_reads"]
    passed = d["filtering_result"]["passed_filter_reads"]
    reads_pf = (passed / before * 100.0) if before else 0.0
    dup = d["duplication"]["rate"] * 100.0
    return q30, reads_pf, dup


def write_run_dir(q30: float, reads_pf: float, dup: float, coverage: float) -> Path:
    """Write a real-giab run dir (git-ignored) carrying the real metrics the gate reads."""
    _RUN_DIR.mkdir(parents=True, exist_ok=True)
    (_RUN_DIR / "SampleSheet.csv").write_text(
        f"[BCLConvert_Data]\nsample_id,index\n{_SAMPLE},NA\n", encoding="utf-8", newline="\n"
    )
    (_RUN_DIR / "sample_metadata.csv").write_text(
        f"sample_id,subject_id,tissue,library_prep,submitted_by\n"
        f"{_SAMPLE},{_SAMPLE},blood,PCR-free,giab\n",
        encoding="utf-8",
        newline="\n",
    )
    # Real values in the qc_metrics.csv percent/x convention; cluster_pf blank (not measured).
    (_RUN_DIR / "qc_metrics.csv").write_text(
        f"sample_id,q30,pct_reads_identified,mean_coverage,dup_rate,cluster_pf\n"
        f"{_SAMPLE},{q30:.2f},{reads_pf:.2f},{coverage:.1f},{dup:.4f},\n",
        encoding="utf-8",
        newline="\n",
    )
    return _RUN_DIR


def main() -> int:
    run_mosdepth()
    run_fastp()
    coverage, breadth20, breadth30 = parse_coverage()
    q30, reads_pf, dup = parse_fastp()
    write_run_dir(q30, reads_pf, dup, coverage)
    _, cards = run_gate_from_dir(_RUN_DIR, runbook=_REAL_RUNBOOK)
    card = cards[0]

    print("\n=== REAL GIAB HG002 panel data through the QC gate (origin=real-giab) ===")
    print(f"  Q30                 : {q30:.1f}%    (fastp; gate >= 85%)")
    print(f"  reads passing filter: {reads_pf:.1f}%    (fastp; gate >= 70%)")
    print(f"  mean coverage       : {coverage:.1f}x    (mosdepth --by panel; gate >= 30x)")
    print(f"  duplication         : {dup:.3f}%   (fastp; gate <= 30%)")
    print(f"  breadth             : {breadth20 * 100:.1f}% >= 20x,  {breadth30 * 100:.1f}% >= 30x")
    print(f"\n  sample {card.sample_id}: {card.verdict.value.upper()} — {card.headline}")
    for f in card.findings:
        print(f"    - [{f.severity.value}] {f.rule_id}: {f.title}")
    if card.metric_values:
        print("  registry-normalized metrics on the card:")
        for m in card.metric_values:
            raw = f"{m.raw_value:g} {m.raw_unit}"
            print(f"    - {m.metric_key}: {m.normalized_value:g} (raw {raw})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
