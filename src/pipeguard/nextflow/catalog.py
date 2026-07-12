"""The tool → Nextflow-DSL2-process catalog — the single source of truth for how a Builder card
becomes a runnable `process`.

Each :class:`ProcessSpec` says, for one tool card: its process name, the bioconda package +
biocontainer image (nf-core convention: a `conda` directive AND a `container` directive so either
profile runs), the typed input/output PORTS (keyed by the same artifact-kind vocabulary the Builder
uses, so the compiler can wire channels straight from the graph edges), a faithful `script:` block
(lifted from `scripts/run_giab_pipeline.py`, the working bioconda driver), and a `stub:` block that
just `touch`es the declared outputs so `nextflow run -stub-run` validates the whole DAG wiring with
no tools or data present.

The catalog is deliberately small and curated (this pipeline's real germline chain). It is NOT a
claim that any card is runnable — only the tools here have a real command; an unknown tool compiles
to a clearly-labelled placeholder process (see the compiler), never a fabricated command.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Port:
    """One typed input/output port of a process, keyed by the Builder's artifact-kind vocabulary.

    ``decl`` is the Nextflow declaration line (e.g. ``path reference`` / ``tuple path(r1),
    path(r2)``). For an output it is paired with ``emit`` (the channel name downstream nodes wire
    to) — the compiler makes ``UPSTREAM.out.<emit>`` the channel for any edge leaving this port.
    """

    kind: str
    decl: str
    emit: str | None = None  # outputs only: the `emit:` channel name (defaults to `kind`)

    @property
    def channel(self) -> str:
        return self.emit or self.kind


@dataclass(frozen=True)
class ProcessSpec:
    """A single tool card's Nextflow process: identity, packaging, ports, and command bodies."""

    tool: str  # the Builder card name (BTOOLSPEC key), e.g. "bcftools call"
    process: str  # the Nextflow process name (UPPER_SNAKE), e.g. BCFTOOLS_CALL
    conda: str  # bioconda spec, e.g. "bioconda::fastp=0.23.4"
    container: str  # a biocontainer image (nf-core convention)
    inputs: tuple[Port, ...]
    outputs: tuple[Port, ...]
    script: str  # the real command (staged-file idiom); tools resolved on PATH by the profile
    stub: str  # `touch` the outputs so -stub-run validates wiring with no tools/data
    publish: str = "results"  # publishDir subdir
    label: str = ""  # a stage label for the process comment
    # Per-sample by default: the process carries the nf-core `[meta, files]` map, runs once per
    # samplesheet row, and names its outputs `${meta.id}.*` — so a multi-sample samplesheet fans
    # out (each sample's chain runs independently) and a single sample is a fan-out of 1 (W4). Set
    # False for a cross-sample AGGREGATOR (e.g. MultiQC): it drops the meta, `.collect()`s every
    # sample's QC streams, and emits ONE report — the compiler wires it accordingly.
    per_sample: bool = True

    def input_kinds(self) -> tuple[str, ...]:
        return tuple(p.kind for p in self.inputs)

    def output_kinds(self) -> tuple[str, ...]:
        return tuple(p.kind for p in self.outputs)


# ── the curated germline-chain catalog ────────────────────────────────────────────────────────
# Commands are faithful to scripts/run_giab_pipeline.py (the working bioconda driver). Per-sample
# processes carry the nf-core `[meta, files]` map and name outputs `${meta.id}.*`; references
# (reference_fasta / panel_bed) arrive as shared value channels WITHOUT meta (broadcast to every
# sample). Each process declares a `stub:` so `nextflow run -stub-run` exercises the DAG with no
# data. MultiQC is the one AGGREGATOR (per_sample=False): it collects every sample's QC into one
# report. The compiler adds the `tuple val(meta), …` wrapper + `tag "${meta.id}"` per this flag.
_SPECS: tuple[ProcessSpec, ...] = (
    ProcessSpec(
        tool="fastp",
        process="FASTP",
        conda="bioconda::fastp=0.23.4",
        container="quay.io/biocontainers/fastp:0.23.4--h5f740d0_0",
        label="Read QC + trim",
        inputs=(Port("fastq", "path(read1), path(read2)"),),
        outputs=(
            Port(
                "fastq",
                'path("*.trim.R1.fastq.gz"), path("*.trim.R2.fastq.gz")',
                emit="fastq",
            ),
            Port("fastp_json", 'path("*.fastp.json")', emit="fastp_json"),
            # fastp already writes the HTML report (`-h …fastp.html` below) — capture it as a real
            # published output rather than a dangling reserved port (W3 full-port-wiring).
            Port("fastp_html", 'path("*.fastp.html")', emit="fastp_html"),
        ),
        script=(
            "fastp -i ${read1} -I ${read2} \\\n"
            "  -o ${meta.id}.trim.R1.fastq.gz -O ${meta.id}.trim.R2.fastq.gz \\\n"
            "  -j ${meta.id}.fastp.json -h ${meta.id}.fastp.html -w ${task.cpus}"
        ),
        stub=(
            "touch ${meta.id}.trim.R1.fastq.gz ${meta.id}.trim.R2.fastq.gz "
            "${meta.id}.fastp.json ${meta.id}.fastp.html"
        ),
    ),
    ProcessSpec(
        tool="bwa-mem2",
        process="BWA_MEM2_MEM",
        conda="bioconda::bwa-mem2=2.2.1 bioconda::samtools=1.20",
        container="quay.io/biocontainers/mulled-v2-e5d375990341c5aef3c9aff74f96f66f65375ef6:"
        "beb9b76a4c73c05e0b4b4f3fda67c9e1e5b6dc4f-0",
        label="Alignment",
        inputs=(
            Port("fastq", "path(read1), path(read2)"),
            Port("reference_fasta", "tuple path(reference), path(reference_idx)"),
        ),
        outputs=(Port("bam", 'path("*.aligned.bam")', emit="bam"),),
        # bwa-mem2 mem | name-sort → fixmate (-m) → coord-sort (faithful to the driver's align step,
        # minus markdup which is its own card downstream). ${reference} must be a pre-indexed fasta.
        script=(
            "bwa-mem2 mem -t ${task.cpus} \\\n"
            '  -R "@RG\\tID:${meta.id}\\tSM:${meta.id}'
            '\\tPL:ILLUMINA\\tLB:${meta.id}-panel" \\\n'
            "  ${reference} ${read1} ${read2} \\\n"
            "  | samtools sort -n -@ ${task.cpus} -O bam - \\\n"
            "  | samtools fixmate -m - - \\\n"
            "  | samtools sort -@ ${task.cpus} -O bam -o ${meta.id}.aligned.bam -"
        ),
        stub="touch ${meta.id}.aligned.bam",
    ),
    ProcessSpec(
        tool="samtools markdup",
        process="SAMTOOLS_MARKDUP",
        conda="bioconda::samtools=1.20",
        container="quay.io/biocontainers/samtools:1.20--h50ea8bc_0",
        label="Duplicate marking",
        inputs=(Port("bam", "path(aligned)"),),
        outputs=(
            Port("bam", 'path("*.dedup.bam")', emit="bam"),
            Port("bai", 'path("*.dedup.bam.bai")', emit="bai"),
            Port("markdup_metrics", 'path("*.markdup.txt")', emit="markdup_metrics"),
            # `samtools stats` on the dedup BAM — a real, MultiQC-parseable alignment-stats stream
            # (was a dangling reserved port; now produced + wired to MultiQC, W3).
            Port("samtools_stats", 'path("*.samtools_stats.txt")', emit="samtools_stats"),
        ),
        script=(
            "samtools markdup -f ${meta.id}.markdup.txt "
            "${aligned} ${meta.id}.dedup.bam\n"
            "samtools index ${meta.id}.dedup.bam\n"
            "samtools stats ${meta.id}.dedup.bam > ${meta.id}.samtools_stats.txt"
        ),
        stub=(
            "touch ${meta.id}.dedup.bam ${meta.id}.dedup.bam.bai "
            "${meta.id}.markdup.txt ${meta.id}.samtools_stats.txt"
        ),
    ),
    ProcessSpec(
        tool="mosdepth",
        process="MOSDEPTH",
        conda="bioconda::mosdepth=0.3.8",
        container="quay.io/biocontainers/mosdepth:0.3.8--hd299d5a_0",
        label="Coverage",
        inputs=(
            Port("bam", "path(dedup)"),
            Port("panel_bed", "path panel"),
        ),
        outputs=(
            Port("mosdepth_summary", 'path("*.mosdepth.summary.txt")', emit="mosdepth_summary"),
            Port("mosdepth_thresholds", 'path("*.thresholds.bed.gz")', emit="mosdepth_thresholds"),
            # The remaining three are REAL byproducts of the SAME `mosdepth --by … --thresholds`
            # command (no extra flag needed): `--by` writes the per-region depth BED and the
            # region distribution, and the global distribution is always emitted (`--no-per-base`
            # suppresses only the per-base track). They were dangling reserved ports on the Builder
            # card (frontend advertises all 5) while the catalog declared only 2 — that arity gap
            # tripped the compiler's output-drift guard and 422'd Export-to-Nextflow on the default
            # view. Declared + published here so a full-5-output node compiles; the seeded
            # germline_graph() still trims to summary+thresholds and stays a valid subset.
            Port("mosdepth_regions", 'path("*.regions.bed.gz")', emit="mosdepth_regions"),
            Port(
                "mosdepth_global_dist",
                'path("*.mosdepth.global.dist.txt")',
                emit="mosdepth_global_dist",
            ),
            Port(
                "mosdepth_region_dist",
                'path("*.mosdepth.region.dist.txt")',
                emit="mosdepth_region_dist",
            ),
        ),
        script=(
            "samtools index ${dedup}\n"
            "mosdepth --by ${panel} --no-per-base --thresholds 1,10,20,30 -t ${task.cpus} \\\n"
            "  ${meta.id}.panel ${dedup}"
        ),
        stub=(
            "touch ${meta.id}.panel.mosdepth.summary.txt ${meta.id}.panel.thresholds.bed.gz "
            "${meta.id}.panel.regions.bed.gz ${meta.id}.panel.mosdepth.global.dist.txt "
            "${meta.id}.panel.mosdepth.region.dist.txt"
        ),
    ),
    ProcessSpec(
        tool="bcftools call",
        process="BCFTOOLS_CALL",
        conda="bioconda::bcftools=1.20",
        container="quay.io/biocontainers/bcftools:1.20--h8b25389_0",
        label="Variant calling",
        inputs=(
            Port("bam", "path(dedup)"),
            Port("reference_fasta", "tuple path(reference), path(reference_idx)"),
            Port("panel_bed", "path panel"),
        ),
        outputs=(Port("vcf", 'path("*.calls.vcf.gz")', emit="vcf"),),
        script=(
            "samtools index ${dedup}\n"
            "bcftools mpileup -f ${reference} -R ${panel} -Ou ${dedup} \\\n"
            "  | bcftools call -mv -Oz -o ${meta.id}.calls.vcf.gz"
        ),
        stub="touch ${meta.id}.calls.vcf.gz",
    ),
    ProcessSpec(
        tool="bcftools norm",
        process="BCFTOOLS_NORM",
        conda="bioconda::bcftools=1.20",
        container="quay.io/biocontainers/bcftools:1.20--h8b25389_0",
        label="Filter / normalize",
        inputs=(
            Port("vcf", "path(calls)"),
            Port("reference_fasta", "tuple path(reference), path(reference_idx)"),
        ),
        outputs=(Port("filtered_vcf", 'path("*.norm.vcf.gz")', emit="filtered_vcf"),),
        script=(
            "bcftools norm -f ${reference} -Oz -o ${meta.id}.norm.vcf.gz ${calls}\n"
            "bcftools index -f ${meta.id}.norm.vcf.gz"
        ),
        stub="touch ${meta.id}.norm.vcf.gz",
    ),
    ProcessSpec(
        tool="MultiQC",
        process="MULTIQC",
        conda="bioconda::multiqc=1.21",
        container="quay.io/biocontainers/multiqc:1.21--pyhdfd78af_0",
        label="QC aggregation",
        # AGGREGATOR: MultiQC scans a directory of QC files pooled ACROSS all samples, so it drops
        # the per-sample meta and the compiler feeds each input `.map { it[1] }.collect()`. Every
        # available metric stream is ingested (was only 3): fastp_json + samtools markdup metrics +
        # samtools stats + mosdepth summary + mosdepth thresholds (W3 full-port-wiring).
        per_sample=False,
        inputs=(
            Port("fastp_json", "path('*')"),
            Port("markdup_metrics", "path('*')"),
            Port("samtools_stats", "path('*')"),
            Port("mosdepth_summary", "path('*')"),
            Port("mosdepth_thresholds", "path('*')"),
        ),
        outputs=(
            Port("multiqc_json", 'path("multiqc_data/multiqc_data.json")', emit="multiqc_json"),
        ),
        script="multiqc . --data-format json",
        stub="mkdir -p multiqc_data && touch multiqc_data/multiqc_data.json",
    ),
)

PROCESS_CATALOG: dict[str, ProcessSpec] = {spec.tool: spec for spec in _SPECS}

# No-input SOURCE cards (the Builder's References section): each emits a reference artifact from a
# `params.<x>` file path rather than from an upstream process. Mapped kind → params key so the
# compiler can build a value channel for it. Not full processes — they have no command. Only the two
# references the germline chain actually consumes are mapped; the retired Truth VCF node's benchmark
# reference is intentionally omitted — the `truth_vcf` KIND stays in the wider vocabulary (a generic
# File-input source can still emit it), but nothing in the catalogued chain consumes it as a ref.
REFERENCE_PARAM: dict[str, str] = {
    "reference_fasta": "reference",
    "panel_bed": "panel_bed",
}

# Reference params whose file carries a SIDECAR INDEX that must be staged alongside it (a FASTA
# needs its bwa-mem2 `.0123/.bwt.2bit.64/…` + samtools `.fai`). For these the compiler stages the
# file + every `<file>.*` sibling as a tuple, so bwa-mem2/bcftools find the index next to the FASTA
# (Nextflow otherwise stages only the single declared file). A BED/VCF needs no sidecar.
INDEXED_REFERENCE_PARAMS: frozenset[str] = frozenset({"reference"})


def catalog_entry(tool: str) -> ProcessSpec | None:
    """The :class:`ProcessSpec` for a Builder card name, or ``None`` if the tool isn't catalogued
    (the compiler emits a labelled placeholder process for it, never a fabricated command)."""
    return PROCESS_CATALOG.get(tool)


# Re-export so ``field`` isn't flagged unused if a future spec needs a default-factory tuple.
_ = field
