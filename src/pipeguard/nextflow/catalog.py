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

    def input_kinds(self) -> tuple[str, ...]:
        return tuple(p.kind for p in self.inputs)

    def output_kinds(self) -> tuple[str, ...]:
        return tuple(p.kind for p in self.outputs)


# ── the curated germline-chain catalog ────────────────────────────────────────────────────────
# Commands are faithful to scripts/run_giab_pipeline.py (the working bioconda driver). Reads are a
# read-pair tuple; references (reference_fasta / panel_bed) arrive as their own channels. Each
# process declares a `stub:` so `nextflow run -stub-run` exercises the DAG with no data.
_SPECS: tuple[ProcessSpec, ...] = (
    ProcessSpec(
        tool="fastp",
        process="FASTP",
        conda="bioconda::fastp=0.23.4",
        container="quay.io/biocontainers/fastp:0.23.4--h5f740d0_0",
        label="Read QC + trim",
        inputs=(Port("fastq", "tuple path(read1), path(read2)"),),
        outputs=(
            Port(
                "fastq",
                'tuple path("*.trim.R1.fastq.gz"), path("*.trim.R2.fastq.gz")',
                emit="fastq",
            ),
            Port("fastp_json", 'path("*.fastp.json")', emit="fastp_json"),
        ),
        script=(
            "fastp -i ${read1} -I ${read2} \\\n"
            "  -o ${params.sample}.trim.R1.fastq.gz -O ${params.sample}.trim.R2.fastq.gz \\\n"
            "  -j ${params.sample}.fastp.json -h ${params.sample}.fastp.html -w ${task.cpus}"
        ),
        stub=(
            "touch ${params.sample}.trim.R1.fastq.gz ${params.sample}.trim.R2.fastq.gz "
            "${params.sample}.fastp.json"
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
            Port("fastq", "tuple path(read1), path(read2)"),
            Port("reference_fasta", "tuple path(reference), path(reference_idx)"),
        ),
        outputs=(Port("bam", 'path("*.aligned.bam")', emit="bam"),),
        # bwa-mem2 mem | name-sort → fixmate (-m) → coord-sort (faithful to the driver's align step,
        # minus markdup which is its own card downstream). ${reference} must be a pre-indexed fasta.
        script=(
            "bwa-mem2 mem -t ${task.cpus} \\\n"
            '  -R "@RG\\tID:${params.sample}\\tSM:${params.sample}'
            '\\tPL:ILLUMINA\\tLB:${params.sample}-panel" \\\n'
            "  ${reference} ${read1} ${read2} \\\n"
            "  | samtools sort -n -@ ${task.cpus} -O bam - \\\n"
            "  | samtools fixmate -m - - \\\n"
            "  | samtools sort -@ ${task.cpus} -O bam -o ${params.sample}.aligned.bam -"
        ),
        stub="touch ${params.sample}.aligned.bam",
    ),
    ProcessSpec(
        tool="samtools markdup",
        process="SAMTOOLS_MARKDUP",
        conda="bioconda::samtools=1.20",
        container="quay.io/biocontainers/samtools:1.20--h50ea8bc_0",
        label="Duplicate marking",
        inputs=(Port("bam", "path aligned"),),
        outputs=(
            Port("bam", 'path("*.dedup.bam")', emit="bam"),
            Port("bai", 'path("*.dedup.bam.bai")', emit="bai"),
            Port("markdup_metrics", 'path("*.markdup.txt")', emit="markdup_metrics"),
        ),
        script=(
            "samtools markdup -f ${params.sample}.markdup.txt "
            "${aligned} ${params.sample}.dedup.bam\n"
            "samtools index ${params.sample}.dedup.bam"
        ),
        stub=(
            "touch ${params.sample}.dedup.bam ${params.sample}.dedup.bam.bai "
            "${params.sample}.markdup.txt"
        ),
    ),
    ProcessSpec(
        tool="mosdepth",
        process="MOSDEPTH",
        conda="bioconda::mosdepth=0.3.8",
        container="quay.io/biocontainers/mosdepth:0.3.8--hd299d5a_0",
        label="Coverage",
        inputs=(
            Port("bam", "path dedup"),
            Port("panel_bed", "path panel"),
        ),
        outputs=(
            Port("mosdepth_summary", 'path("*.mosdepth.summary.txt")', emit="mosdepth_summary"),
            Port("mosdepth_thresholds", 'path("*.thresholds.bed.gz")', emit="mosdepth_thresholds"),
        ),
        script=(
            "samtools index ${dedup}\n"
            "mosdepth --by ${panel} --no-per-base --thresholds 1,10,20,30 -t ${task.cpus} \\\n"
            "  ${params.sample}.panel ${dedup}"
        ),
        stub=(
            "touch ${params.sample}.panel.mosdepth.summary.txt "
            "${params.sample}.panel.thresholds.bed.gz"
        ),
    ),
    ProcessSpec(
        tool="bcftools call",
        process="BCFTOOLS_CALL",
        conda="bioconda::bcftools=1.20",
        container="quay.io/biocontainers/bcftools:1.20--h8b25389_0",
        label="Variant calling",
        inputs=(
            Port("bam", "path dedup"),
            Port("reference_fasta", "tuple path(reference), path(reference_idx)"),
            Port("panel_bed", "path panel"),
        ),
        outputs=(Port("vcf", 'path("*.calls.vcf.gz")', emit="vcf"),),
        script=(
            "samtools index ${dedup}\n"
            "bcftools mpileup -f ${reference} -R ${panel} -Ou ${dedup} \\\n"
            "  | bcftools call -mv -Oz -o ${params.sample}.calls.vcf.gz"
        ),
        stub="touch ${params.sample}.calls.vcf.gz",
    ),
    ProcessSpec(
        tool="bcftools norm",
        process="BCFTOOLS_NORM",
        conda="bioconda::bcftools=1.20",
        container="quay.io/biocontainers/bcftools:1.20--h8b25389_0",
        label="Filter / normalize",
        inputs=(
            Port("vcf", "path calls"),
            Port("reference_fasta", "tuple path(reference), path(reference_idx)"),
        ),
        outputs=(Port("filtered_vcf", 'path("*.norm.vcf.gz")', emit="filtered_vcf"),),
        script=(
            "bcftools norm -f ${reference} -Oz -o ${params.sample}.norm.vcf.gz ${calls}\n"
            "bcftools index -f ${params.sample}.norm.vcf.gz"
        ),
        stub="touch ${params.sample}.norm.vcf.gz",
    ),
    ProcessSpec(
        tool="MultiQC",
        process="MULTIQC",
        conda="bioconda::multiqc=1.21",
        container="quay.io/biocontainers/multiqc:1.21--pyhdfd78af_0",
        label="QC aggregation",
        # MultiQC scans a directory of QC outputs; each upstream QC file is staged in flat.
        inputs=(
            Port("fastp_json", "path('*')"),
            Port("markdup_metrics", "path('*')"),
            Port("mosdepth_summary", "path('*')"),
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
# compiler can build a value channel for it. Not full processes — they have no command.
REFERENCE_PARAM: dict[str, str] = {
    "reference_fasta": "reference",
    "panel_bed": "panel_bed",
    "truth_vcf": "truth_vcf",
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
