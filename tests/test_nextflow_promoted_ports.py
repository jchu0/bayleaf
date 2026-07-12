"""Reserved-port promotion (maintainer note 6): every SHOWN Builder port must map to a REAL
connectable Nextflow channel — or be removed. These tests pin the four reserved output ports that
were PROMOTED to real emit channels (their tool's current command genuinely produces the file):

  - fastp     ``unpaired_fastq`` / ``failed_fastq``  (``--unpaired1/2`` / ``--failed_out`` flags)
  - bcftools norm ``vcf_index``                    (the ``.csi`` its ``bcftools index -f`` writes)
  - MultiQC   ``multiqc_html``                     (``multiqc .`` always writes the HTML report)

Each promoted port must (a) appear as a real ``emit:`` on its module, (b) be produced by the real
command (script) AND the stub, and (c) be wireable — a graph connecting the promoted port to a
downstream sink compiles and threads the right ``.out.<kind>`` channel. The germline byte-for-byte
drift guard (``test_nextflow_compile.py``) proves the seeded chain still compiles with the new spec
outputs. Removed reserved ports (bwa read_group, mosdepth per_base, norm panel_bed, the four MultiQC
no-producer inputs) live only in the frontend catalog and are covered by the frontend build.

WS-10 addendum (2026-07-12): the compile/stub tests above cannot prove a promoted MANDATORY output
is actually produced at RUNTIME — the stub ``touch``es it, so ``-stub-run`` and the drift guard pass
regardless. Two guards close that gap: an offline check that every catalogued output is created
by its own stub (so ``-stub-run`` genuinely materialises the whole DAG), and a REAL-PATH acceptance
test that runs the fastp spec's actual command on real HG002 reads and asserts every declared output
appears. The latter empirically settled the review's "fastp unpaired/failed may be absent → pipeline
dies at step 1" worry: fastp opens the ``--unpaired1/2`` / ``--failed_out`` writers eagerly, so the
files are ALWAYS created (even an empty 828-byte gzip at zero failures) — the outputs are genuinely
mandatory, not optional.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeguard.nextflow import NfEdge, NfGraph, NfNode, compile_graph, germline_graph
from pipeguard.nextflow.catalog import PROCESS_CATALOG, catalog_entry

_REPO = Path(__file__).resolve().parents[1]
_GIAB_FASTQ = _REPO / "data" / "real-giab" / "fastq"


def _output_globs(decl: str) -> list[str]:
    """The output-file glob(s) a Port declaration publishes, e.g. ``path("*.fastp.json")`` →
    ``['*.fastp.json']``. A port may declare more than one (fastp's paired trimmed fastq)."""
    return re.findall(r"""path\(\s*["']([^"']+)["']\s*\)""", decl)


def _resolve_fastp() -> str | None:
    """fastp from the bioconda bin (``PIPEGUARD_BIOCONDA_BIN``, the documented genomics-toolchain
    override) or the PATH; ``None`` if neither has it — then the real-path test skips, like the
    live-Nextflow ones."""
    bioconda = os.environ.get("PIPEGUARD_BIOCONDA_BIN")
    if bioconda:
        cand = Path(bioconda) / "fastp"
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return shutil.which("fastp")


# ── fastp: unpaired_fastq + failed_fastq ──────────────────────────────────────────
def test_fastp_promoted_outputs_are_real_emit_channels() -> None:
    """A fastp node declaring its full output set emits unpaired_fastq + failed_fastq, and the real
    command carries the flags that actually produce those files (never a fabricated slot)."""
    g = NfGraph(
        name="fastp-full",
        nodes=[
            NfNode(
                "fp",
                "fastp",
                ins=["fastq"],
                outs=["fastp_json", "fastq", "fastp_html", "unpaired_fastq", "failed_fastq"],
            )
        ],
    )
    fastp = compile_graph(g).files["modules/fastp.nf"]
    assert 'path("*.unpaired.fastq.gz"), emit: unpaired_fastq' in fastp
    assert 'path("*.failed.fastq.gz"), emit: failed_fastq' in fastp
    # The real command produces them — the flags are present, not just the emit decl.
    assert (
        "--unpaired1 ${meta.id}.unpaired.fastq.gz --unpaired2 ${meta.id}.unpaired.fastq.gz" in fastp
    )
    assert "--failed_out ${meta.id}.failed.fastq.gz" in fastp
    # The stub touches them so -stub-run validates the wiring.
    assert "${meta.id}.unpaired.fastq.gz" in fastp and "${meta.id}.failed.fastq.gz" in fastp


# ── bcftools norm: vcf_index ──────────────────────────────────────────────────────
def test_bcftools_norm_vcf_index_is_a_real_emit_channel() -> None:
    """norm emits vcf_index — the `.csi` its `bcftools index -f` already writes (a genuine byproduct
    of the unchanged command, not a new flag)."""
    g = NfGraph(
        name="norm-index",
        nodes=[
            NfNode(
                "n",
                "bcftools norm",
                ins=["vcf", "reference_fasta"],
                outs=["filtered_vcf", "vcf_index"],
            )
        ],
    )
    norm = compile_graph(g).files["modules/bcftools_norm.nf"]
    assert 'path("*.norm.vcf.gz.csi"), emit: vcf_index' in norm
    assert "bcftools index -f ${meta.id}.norm.vcf.gz" in norm  # the command that produces the .csi
    assert "${meta.id}.norm.vcf.gz.csi" in norm  # stub touches it too


# ── MultiQC: multiqc_html ─────────────────────────────────────────────────────────
def test_multiqc_html_is_a_real_emit_channel() -> None:
    """MultiQC emits multiqc_html — `multiqc .` always writes the report (no --no-report passed)."""
    g = NfGraph(
        name="mqc-html",
        nodes=[
            NfNode("fp", "fastp", ins=["fastq"], outs=["fastp_json"]),
            NfNode(
                "m",
                "MultiQC",
                ins=[
                    "fastp_json",
                    "markdup_metrics",
                    "samtools_stats",
                    "mosdepth_summary",
                    "mosdepth_thresholds",
                ],
                outs=["multiqc_json", "multiqc_html"],
            ),
        ],
        edges=[NfEdge("fp", 0, "m", 0)],
    )
    multiqc = compile_graph(g).files["modules/multiqc.nf"]
    assert 'path("multiqc_report.html"), emit: multiqc_html' in multiqc
    assert "multiqc_report.html" in multiqc  # stub touches it


# ── a promoted port wires to a downstream sink ────────────────────────────────────
def test_promoted_port_wires_to_a_custom_sink() -> None:
    """A graph connecting a PROMOTED output (fastp unpaired_fastq) to a downstream (custom) card
    compiles and threads the right `FASTP.out.unpaired_fastq` channel — proving the port is a real,
    connectable channel end-to-end, not a decorative slot."""
    g = NfGraph(
        name="promoted-wire",
        nodes=[
            NfNode(
                "fp",
                "fastp",
                ins=["fastq"],
                outs=["fastp_json", "fastq", "fastp_html", "unpaired_fastq", "failed_fastq"],
            ),
            # An operator-authored sink consuming the promoted unpaired-reads channel.
            NfNode(
                "sink",
                "count-unpaired",
                ins=["unpaired_fastq"],
                outs=["report"],
                script="zcat ${unpaired_fastq} | wc -l > ${meta.id}.count.txt",
            ),
        ],
        edges=[NfEdge("fp", 3, "sink", 0)],  # from_idx 3 = unpaired_fastq
    )
    main = compile_graph(g).main_nf
    assert "COUNT_UNPAIRED(FASTP.out.unpaired_fastq)" in main


def test_germline_still_compiles_with_the_promoted_spec_outputs() -> None:
    """The seeded germline chain still compiles (its nodes declare a SUBSET of the now-larger spec
    outputs) — a second guard alongside the byte-for-byte drift test."""
    bundle = compile_graph(germline_graph())
    # The reference modules carry the promoted emits after regeneration.
    assert "emit: unpaired_fastq" in bundle.files["modules/fastp.nf"]
    assert "emit: vcf_index" in bundle.files["modules/bcftools_norm.nf"]
    assert "emit: multiqc_html" in bundle.files["modules/multiqc.nf"]


# ── WS-10 guard 1 (offline): every declared output is created by its own stub ──────
def test_every_catalogued_output_is_created_by_its_stub() -> None:
    """For EVERY catalogued tool, each declared OUTPUT glob has a matching file in that tool's
    ``stub:`` block — so ``nextflow run -stub-run`` genuinely materialises every output the compiler
    wires as mandatory. A declared-but-unproduced output (the failure class WS-10 probed: a real
    ``path("…")`` glob with nothing to match) fails here, offline, for all tools at once — freezing
    the promotion's core invariant (a shown port maps to a REAL, produced channel) against drift."""
    for tool, spec in PROCESS_CATALOG.items():
        stub_tokens = spec.stub.replace("\n", " ").split()
        for port in spec.outputs:
            for glob in _output_globs(port.decl):
                assert any(fnmatch.fnmatchcase(tok, glob) for tok in stub_tokens), (
                    f"{tool}: declared output {glob!r} (emit {port.channel}) is not created by the "
                    f"stub — `-stub-run` would fail the mandatory-output glob. Stub: {spec.stub!r}"
                )


# ── WS-10 guard 2 (REAL-PATH acceptance, env-gated): the real command emits it all ─
@pytest.mark.skipif(
    _resolve_fastp() is None or not (_GIAB_FASTQ / "HG002.R1.fastq.gz").exists(),
    reason="real-path: needs fastp (PIPEGUARD_BIOCONDA_BIN or PATH) + data/real-giab/fastq/ reads",
)
def test_fastp_catalog_command_produces_every_declared_output(tmp_path: Path) -> None:
    """REAL-PATH acceptance (env-gated, skip-safe like live-Nextflow tests): run the fastp spec's
    ACTUAL ``script`` on real HG002 reads and assert EVERY declared output is produced on disk. This
    is the guard the compile/stub tests structurally cannot give — it un-stubs the boundary and, for
    the promoted ``unpaired_fastq``/``failed_fastq`` ports, settles the review's "may be absent →
    pipeline dies at step 1" worry on real data. It drives the assertions off the catalog spec
    itself (command + declared globs), so it can never drift from what ships."""
    fastp = _resolve_fastp()
    assert fastp is not None  # guarded by skipif
    spec = catalog_entry("fastp")
    assert spec is not None
    r1, r2 = _GIAB_FASTQ / "HG002.R1.fastq.gz", _GIAB_FASTQ / "HG002.R2.fastq.gz"
    # Fill the Nextflow interpolations the driver supplies; resolve `fastp` to the env binary.
    cmd = (
        spec.script.replace("${read1}", str(r1))
        .replace("${read2}", str(r2))
        .replace("${meta.id}", "HG002")
        .replace("${task.cpus}", "2")
        .replace("fastp ", f"{fastp} ", 1)  # first token only; ".fastp.json" is untouched
    )
    subprocess.run(cmd, shell=True, cwd=tmp_path, check=True, capture_output=True)
    produced = sorted(p.name for p in tmp_path.iterdir())
    for port in spec.outputs:
        for glob in _output_globs(port.decl):
            assert any(fnmatch.fnmatchcase(name, glob) for name in produced), (
                f"fastp output {glob!r} (emit {port.channel}) NOT produced by the real command — "
                f"Nextflow's mandatory glob path({glob!r}) would fail. Produced: {produced}"
            )
