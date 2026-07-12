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
"""

from __future__ import annotations

from pipeguard.nextflow import NfEdge, NfGraph, NfNode, compile_graph, germline_graph


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
