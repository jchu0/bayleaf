"""Gate REAL GIAB HG002 panel data through the deterministic QC gate (T-017).

The "it works on real data, not just contrived runs" step. Given the panel-region reads
slice fetched by `fetch_giab_hg002.py --with-reads`, this:

  1. runs `mosdepth --by <panel.bed>` to get the REAL in-panel mean coverage + breadth,
  2. writes a small `real-giab` run directory (git-ignored) with that real coverage in the
     same on-disk shape the parsers already read, and
  3. runs it through the *existing* gate (`run_gate_from_dir`) with a coverage-focused
     runbook, printing the decision.

Honest scope: a BAM yields coverage/breadth but not the fastq/run-level metrics (Q30,
duplication, cluster-PF come from upstream fastp/SAV), so this gates the metric the artifact
actually carries — real HG002 panel coverage — and reports breadth alongside. Nothing here
touches the core; it reuses `run_gate` and the registry-backed rules unchanged.

Prereqs: `mosdepth` on PATH (bioconda) and the panel BAM already fetched. NO data is
committed — everything lands in the git-ignored `data/real-giab/`.

    python scripts/gate_giab.py            # gate the fetched slice
"""

from __future__ import annotations

import gzip
import shutil
import subprocess
import sys
from pathlib import Path

from pipeguard import Runbook, run_gate_from_dir
from pipeguard.runbook import QCThreshold

_REPO = Path(__file__).resolve().parent.parent
_GIAB = _REPO / "data" / "real-giab"
_BAM = _GIAB / "HG002.GRCh38.panel.bam"
_PANEL_BED = _REPO / "scripts" / "panel_regions.example.bed"
_MOSDEPTH_DIR = _GIAB / "mosdepth"
_PREFIX = _MOSDEPTH_DIR / "HG002.panel"
_RUN_DIR = _GIAB / "run"
_SAMPLE = "HG002"

# A coverage-focused runbook: a BAM carries coverage, not the fastq/run metrics, so we gate
# the metric the artifact actually has. It still keys on the registry `our_key` (T-025) and
# stores the gate in the canonical unit (x), exactly like the default runbook.
_COVERAGE_RUNBOOK = Runbook(
    require_metadata_fields=["subject_id"],
    qc_thresholds=[
        QCThreshold(
            metric="mean_coverage",
            our_key="qc.mean_target_coverage",
            label="Mean coverage",
            gate=30.0,
            hard_fail=15.0,
            unit="x",
        )
    ],
)


def _require_mosdepth() -> str:
    tool = shutil.which("mosdepth")
    if tool is None:
        sys.exit(
            "mosdepth not found on PATH. Install it in the genomics toolchain, e.g.\n"
            "  conda install -n hackathon -c conda-forge -c bioconda mosdepth\n"
            "  PATH=/path/to/env/bin:$PATH python scripts/gate_giab.py"
        )
    return tool


def run_mosdepth() -> None:
    """Run `mosdepth --by <panel.bed>` for per-region coverage + breadth thresholds."""
    if not _BAM.exists():
        sys.exit(
            f"panel BAM not found: {_BAM}\n"
            "Fetch it first:  python scripts/fetch_giab_hg002.py --with-reads "
            "--panel-bed scripts/panel_regions.example.bed"
        )
    _MOSDEPTH_DIR.mkdir(parents=True, exist_ok=True)
    if Path(f"{_PREFIX}.mosdepth.summary.txt").exists():
        print(f"mosdepth output exists, reusing {_PREFIX}.*")
        return
    mosdepth = _require_mosdepth()
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


def write_run_dir(mean_coverage: float) -> Path:
    """Write a real-giab run dir (git-ignored) carrying the real coverage the gate reads."""
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
    # Only mean_coverage is real (from the BAM); the fastq/run metrics are left blank —
    # the tolerant parser reads a blank cell as None (a signal, not a crash).
    (_RUN_DIR / "qc_metrics.csv").write_text(
        f"sample_id,q30,pct_reads_identified,mean_coverage,dup_rate,cluster_pf\n"
        f"{_SAMPLE},,,{mean_coverage:.1f},,\n",
        encoding="utf-8",
        newline="\n",
    )
    return _RUN_DIR


def main() -> int:
    run_mosdepth()
    mean, breadth20, breadth30 = parse_coverage()
    write_run_dir(mean)
    _, cards = run_gate_from_dir(_RUN_DIR, runbook=_COVERAGE_RUNBOOK)
    card = cards[0]

    print("\n=== REAL GIAB HG002 panel data through the QC gate (origin=real-giab) ===")
    print(f"  mean coverage : {mean:.1f}x   (mosdepth --by panel; gate >= 30x)")
    print(f"  breadth       : {breadth20 * 100:.1f}% >= 20x,  {breadth30 * 100:.1f}% >= 30x")
    print(f"  sample {card.sample_id}: {card.verdict.value.upper()} — {card.headline}")
    for f in card.findings:
        print(f"    - [{f.severity.value}] {f.rule_id}: {f.title}")
    print("\n  (A BAM carries coverage/breadth, not fastq Q30/dup — those come from upstream")
    print("   QC; this gates the real metric the artifact actually holds.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
