"""The seeded germline chain as an :class:`NfGraph` — the reference the Builder's default template
compiles to.

This mirrors the Pipeline-Builder's seeded germline template (the same tools, versions, and typed
wiring the frontend `BuilderShared` ships), expressed as compiler input. Compiling it yields the
committed reference pipeline under ``pipelines/germline/`` — so the "what the Builder emits" and the
"canonical pipeline in the repo" are the SAME artifact by construction, and a drift test pins it.

Node output/input kinds are listed in the catalog's port order (see ``catalog.py``); edges index
into those orders. Chain: fastp → bwa-mem2 → samtools markdup → {mosdepth, bcftools call → norm};
fastp/markdup/mosdepth QC feed MultiQC. References (reference_fasta, panel_bed) are unwired inputs,
so they compile to ``params.reference`` / ``params.panel_bed`` source channels.
"""

from __future__ import annotations

from .compiler import NfEdge, NfGraph, NfNode


def germline_graph() -> NfGraph:
    """The germline-panel card graph (matches the Builder's seeded template)."""
    nodes = [
        NfNode("n_fastp", "fastp", ins=["fastq"], outs=["fastq", "fastp_json"]),
        NfNode("n_bwa", "bwa-mem2", ins=["fastq", "reference_fasta"], outs=["bam"]),
        NfNode(
            "n_markdup", "samtools markdup", ins=["bam"], outs=["bam", "bai", "markdup_metrics"]
        ),
        NfNode(
            "n_mosdepth",
            "mosdepth",
            ins=["bam", "panel_bed"],
            outs=["mosdepth_summary", "mosdepth_thresholds"],
        ),
        NfNode(
            "n_call", "bcftools call", ins=["bam", "reference_fasta", "panel_bed"], outs=["vcf"]
        ),
        NfNode("n_norm", "bcftools norm", ins=["vcf", "reference_fasta"], outs=["filtered_vcf"]),
        NfNode(
            "n_multiqc",
            "MultiQC",
            ins=["fastp_json", "markdup_metrics", "mosdepth_summary"],
            outs=["multiqc_json"],
        ),
    ]
    edges = [
        NfEdge("n_fastp", 0, "n_bwa", 0),  # trimmed fastq → aligner
        NfEdge("n_bwa", 0, "n_markdup", 0),  # aligned bam → markdup
        NfEdge("n_markdup", 0, "n_mosdepth", 0),  # dedup bam → coverage
        NfEdge("n_markdup", 0, "n_call", 0),  # dedup bam → variant calling
        NfEdge("n_call", 0, "n_norm", 0),  # raw calls → normalize
        NfEdge("n_fastp", 1, "n_multiqc", 0),  # fastp_json → MultiQC
        NfEdge("n_markdup", 2, "n_multiqc", 1),  # markdup metrics → MultiQC
        NfEdge("n_mosdepth", 0, "n_multiqc", 2),  # mosdepth summary → MultiQC
    ]
    return NfGraph(name="germline-panel", nodes=nodes, edges=edges)
