// Duplicate marking — samtools markdup
process SAMTOOLS_MARKDUP {
    tag "${params.sample}"
    conda 'bioconda::samtools=1.20'
    container 'quay.io/biocontainers/samtools:1.20--h50ea8bc_0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    path aligned

    output:
    path("*.dedup.bam"), emit: bam
    path("*.dedup.bam.bai"), emit: bai
    path("*.markdup.txt"), emit: markdup_metrics

    script:
    """
    samtools markdup -f ${params.sample}.markdup.txt ${aligned} ${params.sample}.dedup.bam
    samtools index ${params.sample}.dedup.bam
    """

    stub:
    """
    touch ${params.sample}.dedup.bam ${params.sample}.dedup.bam.bai ${params.sample}.markdup.txt
    """
}
