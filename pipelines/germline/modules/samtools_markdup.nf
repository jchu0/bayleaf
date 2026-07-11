// Duplicate marking — samtools markdup
process SAMTOOLS_MARKDUP {
    tag "${meta.id}"
    conda 'bioconda::samtools=1.20'
    container 'quay.io/biocontainers/samtools:1.20--h50ea8bc_0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    tuple val(meta), path(aligned)

    output:
    tuple val(meta), path("*.dedup.bam"), emit: bam
    tuple val(meta), path("*.dedup.bam.bai"), emit: bai
    tuple val(meta), path("*.markdup.txt"), emit: markdup_metrics
    tuple val(meta), path("*.samtools_stats.txt"), emit: samtools_stats

    script:
    """
    samtools markdup -f ${meta.id}.markdup.txt ${aligned} ${meta.id}.dedup.bam
    samtools index ${meta.id}.dedup.bam
    samtools stats ${meta.id}.dedup.bam > ${meta.id}.samtools_stats.txt
    """

    stub:
    """
    touch ${meta.id}.dedup.bam ${meta.id}.dedup.bam.bai ${meta.id}.markdup.txt ${meta.id}.samtools_stats.txt
    """
}
