"""The Pipeline-Builder-card → Nextflow (DSL2) compiler (ADR-0003, made executable).

Pins the properties that make the codegen trustworthy: the germline template compiles to the
committed reference pipeline byte-for-byte (drift guard), typed-port edges become the right
channels, a cycle / bad edge is rejected, an uncatalogued tool degrades to a labelled placeholder
(never a fabricated command), and — machine-gated — the generated pipeline actually validates under
`nextflow run -stub-run`. Compose ≠ execute: the compiler emits TEXT, it never runs a tool.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeguard.nextflow import (
    CompileError,
    NfEdge,
    NfGraph,
    NfNode,
    compile_graph,
    germline_graph,
)

_REPO = Path(__file__).resolve().parent.parent
_REFERENCE = _REPO / "pipelines" / "germline"


# ── shape + wiring ───────────────────────────────────────────────────────────────
def test_germline_bundle_has_the_expected_files() -> None:
    files = compile_graph(germline_graph()).files
    assert "main.nf" in files and "nextflow.config" in files and "README.md" in files
    # one module per distinct tool (7 in the germline chain)
    modules = [k for k in files if k.startswith("modules/")]
    assert len(modules) == 7


def test_germline_channel_wiring_matches_the_typed_ports() -> None:
    main = compile_graph(germline_graph()).main_nf
    # Each edge in the graph must appear as an UPSTREAM.out.<kind> argument. Per-sample meta rides
    # INSIDE the tuple, so the spine's channel expressions are unchanged by the fan-out (W4).
    assert "BWA_MEM2_MEM(FASTP.out.fastq, ch_reference)" in main
    assert "SAMTOOLS_MARKDUP(BWA_MEM2_MEM.out.bam)" in main
    assert "MOSDEPTH(SAMTOOLS_MARKDUP.out.bam, ch_panel_bed)" in main
    assert "BCFTOOLS_CALL(SAMTOOLS_MARKDUP.out.bam, ch_reference, ch_panel_bed)" in main
    assert "BCFTOOLS_NORM(BCFTOOLS_CALL.out.vcf, ch_reference)" in main
    # MultiQC is the cross-sample AGGREGATOR: every QC stream is meta-stripped + pooled (W3/W4),
    # including the newly-wired samtools_stats + mosdepth_thresholds.
    assert (
        "MULTIQC(FASTP.out.fastp_json.map { it[1] }.collect(), "
        "SAMTOOLS_MARKDUP.out.markdup_metrics.map { it[1] }.collect(), "
        "SAMTOOLS_MARKDUP.out.samtools_stats.map { it[1] }.collect(), "
        "MOSDEPTH.out.mosdepth_summary.map { it[1] }.collect(), "
        "MOSDEPTH.out.mosdepth_thresholds.map { it[1] }.collect())" in main
    )
    # Reads are a per-sample QUEUE channel from a samplesheet; the FASTA stages its index sidecars.
    assert "ch_reads = Channel.fromPath(params.input)" in main
    assert ".splitCsv(header: true)" in main
    assert ".map { row -> tuple([id: row.sample], file(row.fastq_1), file(row.fastq_2)) }" in main
    ref_ch = 'ch_reference = Channel.value([file(params.reference), file("${params.reference}.*")])'
    assert ref_ch in main


def test_a_process_carries_a_real_command_and_a_stub() -> None:
    files = compile_graph(germline_graph()).files
    fastp = files["modules/fastp.nf"]
    assert "process FASTP" in fastp
    assert "fastp -i ${read1} -I ${read2}" in fastp  # the real command
    assert "conda 'bioconda::fastp=0.23.4'" in fastp
    assert "stub:" in fastp and "touch" in fastp  # -stub-run has something to run


# ── W4: per-sample fan-out + executor profiles ───────────────────────────────────
def test_reads_are_a_per_sample_queue_channel_from_a_samplesheet() -> None:
    """Fan-out (W4): reads become a samplesheet-driven QUEUE channel of `[meta, r1, r2]` per row,
    not a single-sample value channel — so each sample's chain runs independently."""
    main = compile_graph(germline_graph()).main_nf
    assert "ch_reads = Channel.fromPath(params.input)" in main
    assert "tuple([id: row.sample], file(row.fastq_1), file(row.fastq_2))" in main
    assert "Channel.value([file(params.read1)" not in main  # the old single-sample shape is gone


def test_per_sample_process_threads_the_meta_map() -> None:
    """A per-sample process carries `[meta, files]` on its non-reference ports + tags by sample;
    reference inputs stay meta-free shared value channels."""
    files = compile_graph(germline_graph()).files
    bwa = files["modules/bwa_mem2_mem.nf"]
    assert 'tag "${meta.id}"' in bwa
    assert "tuple val(meta), path(read1), path(read2)" in bwa  # per-sample reads, meta-threaded
    assert "tuple path(reference), path(reference_idx)" in bwa  # reference: value channel, no meta
    assert 'tuple val(meta), path("*.aligned.bam"), emit: bam' in bwa


def test_multiqc_is_a_cross_sample_aggregator() -> None:
    """MultiQC (per_sample=False) drops the meta and pools every sample's QC into one report; its
    module carries no `val(meta)` and no per-sample tag."""
    files = compile_graph(germline_graph())
    multiqc = files.files["modules/multiqc.nf"]
    assert "val(meta)" not in multiqc
    assert 'tag "${meta.id}"' not in multiqc
    assert 'path("multiqc_data/multiqc_data.json"), emit: multiqc_json' in multiqc


def test_config_emits_standard_and_slurm_executor_profiles() -> None:
    """W4: the emitted config carries a local single-thread-serial `standard` profile AND an
    env-driven `slurm` profile. Config-verified, not cluster-verified."""
    cfg = compile_graph(germline_graph()).files["nextflow.config"]
    # local-serial fallback
    assert "standard {" in cfg
    assert "executor.queueSize = 1" in cfg
    assert "process.maxForks   = 1" in cfg
    assert "process.cpus       = 1" in cfg
    # slurm — env-driven knobs, never hardcoded guesses
    assert "slurm {" in cfg
    assert "process.executor       = 'slurm'" in cfg
    assert "System.getenv('PIPEGUARD_SLURM_QUEUE')" in cfg
    # the reads param is now the samplesheet `input`, not read1/read2
    assert "input      = null" in cfg
    assert "read1" not in cfg and "read2" not in cfg


def test_full_port_graph_wires_the_new_qc_streams() -> None:
    """W3: samtools_stats + fastp_html are produced (were dangling reserved ports); samtools_stats
    + mosdepth_thresholds are ingested by MultiQC (were unconsumed)."""
    files = compile_graph(germline_graph()).files
    markdup = files["modules/samtools_markdup.nf"]
    assert "samtools stats ${meta.id}.dedup.bam > ${meta.id}.samtools_stats.txt" in markdup
    assert "emit: samtools_stats" in markdup
    assert "emit: fastp_html" in files["modules/fastp.nf"]
    assert 'path("*.fastp.html")' in files["modules/fastp.nf"]
    main = files["main.nf"]
    assert "SAMTOOLS_MARKDUP.out.samtools_stats.map { it[1] }.collect()" in main
    assert "MOSDEPTH.out.mosdepth_thresholds.map { it[1] }.collect()" in main


# ── drift guard: the committed reference IS the compiler output ──────────────────
def test_committed_reference_pipeline_matches_the_compiler() -> None:
    """`pipelines/germline/` must be exactly what the compiler emits for the seeded graph — so the
    'what the Builder produces' and the 'canonical repo pipeline' can never silently diverge."""
    assert _REFERENCE.is_dir(), "run scripts/generate_reference_pipeline.py to (re)generate it"
    bundle = compile_graph(germline_graph())
    for rel, content in bundle.files.items():
        committed = _REFERENCE / rel
        assert committed.is_file(), f"missing committed file {rel}"
        assert committed.read_text(encoding="utf-8") == content, f"drift in {rel} — regenerate"
    # No extra committed files beyond what the compiler emits (a stale module would be drift too).
    on_disk = {str(p.relative_to(_REFERENCE)) for p in _REFERENCE.rglob("*") if p.is_file()}
    assert on_disk == set(bundle.files)


# ── validation / degradation ─────────────────────────────────────────────────────
def test_cycle_is_rejected() -> None:
    g = NfGraph(
        name="loop",
        nodes=[
            NfNode("a", "fastp", ins=["vcf"], outs=["vcf"]),
            NfNode("b", "bcftools norm", ins=["vcf"], outs=["vcf"]),
        ],
        edges=[NfEdge("a", 0, "b", 0), NfEdge("b", 0, "a", 0)],
    )
    with pytest.raises(CompileError, match="cycle"):
        compile_graph(g)


def test_edge_to_unknown_node_is_rejected() -> None:
    g = NfGraph(
        name="bad",
        nodes=[NfNode("a", "fastp", ins=["fastq"], outs=["fastq"])],
        edges=[NfEdge("a", 0, "ghost", 0)],
    )
    with pytest.raises(CompileError, match="unknown node"):
        compile_graph(g)


def test_uncatalogued_tool_becomes_a_labelled_placeholder() -> None:
    # A real tool card with no catalogued command: the wiring is generated, the command is not
    # fabricated — the placeholder fails loudly on a real run but -stub-run still validates.
    g = NfGraph(
        name="unknown-tool",
        nodes=[
            NfNode("a", "fastp", ins=["fastq"], outs=["fastq", "fastp_json"]),
            NfNode("b", "deepvariant", ins=["fastq"], outs=["vcf"]),
        ],
        edges=[NfEdge("a", 0, "b", 0)],
    )
    files = compile_graph(g).files
    placeholder = files["modules/deepvariant.nf"]
    assert "PLACEHOLDER" in placeholder and "exit 1" in placeholder
    assert "stub:" in placeholder  # still stub-runnable
    assert "DEEPVARIANT(FASTP.out.fastq)" in files["main.nf"]  # wired regardless


def test_reference_source_node_maps_to_a_params_channel() -> None:
    # A reference drawn as an explicit source card (no inputs, emits reference_fasta) compiles to
    # params.reference — same as an unwired reference input.
    g = NfGraph(
        name="ref-source",
        nodes=[
            NfNode("ref", "Reference FASTA", ins=[], outs=["reference_fasta"]),
            NfNode("a", "bwa-mem2", ins=["fastq", "reference_fasta"], outs=["bam"]),
        ],
        edges=[NfEdge("ref", 0, "a", 1)],
    )
    main = compile_graph(g).main_nf
    assert "BWA_MEM2_MEM(ch_reads, ch_reference)" in main
    assert "modules/reference_fasta" not in " ".join(compile_graph(g).files)  # source ≠ a process


def test_repeated_tool_is_aliased() -> None:
    g = NfGraph(
        name="twice",
        nodes=[
            NfNode("a", "fastp", ins=["fastq"], outs=["fastq", "fastp_json"]),
            NfNode("b", "fastp", ins=["fastq"], outs=["fastq", "fastp_json"]),
        ],
        edges=[NfEdge("a", 0, "b", 0)],
    )
    main = compile_graph(g).main_nf
    assert "include { FASTP as FASTP_1, FASTP as FASTP_2 }" in main
    assert "FASTP_1(ch_reads)" in main and "FASTP_2(FASTP_1.out.fastq)" in main


# ── machine-gated: the generated pipeline actually runs under Nextflow ────────────
def test_generated_germline_stub_runs(tmp_path: Path) -> None:
    """Skip-safe live check (mirrors the Postgres live test): if `nextflow` is on PATH, the
    generated pipeline must validate end-to-end via `-stub-run` (every process' stub touches its
    outputs, so the whole DAG executes with no tools/data). Absent Nextflow → skip, never fail."""
    nextflow = os.environ.get("PIPEGUARD_NEXTFLOW_BIN") or shutil.which("nextflow")
    if not nextflow:
        pytest.skip("no `nextflow` on PATH — skipping the live stub-run check")

    bundle = compile_graph(germline_graph())
    for rel, content in bundle.files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    # A reference + a sidecar index file, so the FASTA index bundle (file("ref.fa.*")) is non-empty.
    inputs = ["r1.fastq.gz", "r2.fastq.gz", "panel.bed", "ref.fa"]
    inputs += ["ref.fa.fai", "ref.fa.bwt.2bit.64"]  # bwa-mem2 + samtools sidecars
    for name in inputs:
        (tmp_path / name).write_text("", encoding="utf-8")
    # A one-row samplesheet drives the per-sample queue channel (fan-out of 1 exercises the DAG).
    (tmp_path / "samplesheet.csv").write_text(
        "sample,fastq_1,fastq_2\nHG002,r1.fastq.gz,r2.fastq.gz\n", encoding="utf-8"
    )

    proc = subprocess.run(
        [nextflow, "run", str(tmp_path / "main.nf"), "-stub-run",
         "--input", str(tmp_path / "samplesheet.csv"),
         "--reference", str(tmp_path / "ref.fa"), "--panel_bed", str(tmp_path / "panel.bed")],
        cwd=tmp_path, capture_output=True, text=True, timeout=300, env=os.environ,
    )  # fmt: skip
    assert proc.returncode == 0, f"nextflow -stub-run failed:\n{proc.stdout}\n{proc.stderr}"
