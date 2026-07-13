"""The seeded germline chain as an :class:`NfGraph` — the reference the Builder's default template
compiles to.

This mirrors the Pipeline-Builder's seeded germline template (the same tools, versions, and typed
wiring the frontend `BuilderShared` ships), expressed as compiler input. Compiling it yields the
committed reference pipeline under ``pipelines/germline/`` — so the "what the Builder emits" and the
"canonical pipeline in the repo" are the SAME artifact by construction, and a drift test pins it.

Node output/input kinds are listed in the catalog's port order (see ``catalog.py``); edges index
into those orders. Chain: fastp → bwa-mem2 → samtools markdup → {mosdepth, bcftools call → norm,
verifybamid2}; fastp/markdup/mosdepth QC feed MultiQC. References (reference_fasta, panel_bed) are
unwired inputs, so they compile to ``params.reference`` / ``params.panel_bed`` source channels.

verifybamid2 (contamination / FREEMIX, T-071a) consumes the dedup BAM + the shared reference and an
OPTIONAL ``svd_panel`` external input (``OPTIONAL_INPUT_PARAMS`` → ``params.verifybamid_svd``): when
that param is UNSET — the offline/default demo — the process receives an empty channel and runs ZERO
tasks, so it is DORMANT and the pinned demo scenario is unchanged. It only computes contamination
when an operator arms the ancestry panel (a labelled input, ADR-0004; not committed here).

NOTE (frontend parity): this graph historically mirrored the Builder's seeded template one-to-one.
Adding a dormant verifybamid2 node here (the compiler's canonical reference) slightly outpaces the
frontend ``BuilderShared`` template, which does not yet ship a verifybamid2 card — a labelled seam
for the maintainer, not a wiring gap (nothing cross-checks the two by construction).
"""

from __future__ import annotations

from .compiler import NfEdge, NfGraph, NfNode


def germline_graph() -> NfGraph:
    """The germline-panel card graph (matches the Builder's seeded template). Node out/in kinds are
    in catalog port order — MultiQC now ingests every QC stream (fastp_json + markdup_metrics +
    samtools_stats + mosdepth_summary + mosdepth_thresholds); fastp_html publishes (unwired)."""
    nodes = [
        NfNode("n_fastp", "fastp", ins=["fastq"], outs=["fastq", "fastp_json", "fastp_html"]),
        NfNode("n_bwa", "bwa-mem2", ins=["fastq", "reference_fasta"], outs=["bam"]),
        NfNode(
            "n_markdup",
            "samtools markdup",
            ins=["bam"],
            outs=["bam", "bai", "markdup_metrics", "samtools_stats"],
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
            ins=[
                "fastp_json",
                "markdup_metrics",
                "samtools_stats",
                "mosdepth_summary",
                "mosdepth_thresholds",
            ],
            outs=["multiqc_json"],
        ),
        # Contamination (FREEMIX), DORMANT by default (T-071a). Input order matches the catalog's
        # verifybamid2 ports: bam (from markdup), reference_fasta (shared, unwired), svd_panel (the
        # OPTIONAL external input, unwired → params.verifybamid_svd → empty unless armed).
        NfNode(
            "n_verifybamid",
            "verifybamid2",
            ins=["bam", "reference_fasta", "svd_panel"],
            outs=["selfsm"],
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
        NfEdge("n_markdup", 3, "n_multiqc", 2),  # samtools stats → MultiQC
        NfEdge("n_mosdepth", 0, "n_multiqc", 3),  # mosdepth summary → MultiQC
        NfEdge("n_mosdepth", 1, "n_multiqc", 4),  # mosdepth thresholds → MultiQC
        NfEdge("n_markdup", 0, "n_verifybamid", 0),  # dedup bam → contamination (reference + svd
        # unwired: reference is the shared value channel, svd_panel is the OPTIONAL dormant input)
    ]
    return NfGraph(name="germline-panel", nodes=nodes, edges=edges)
