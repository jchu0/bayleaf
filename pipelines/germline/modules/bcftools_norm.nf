// Filter / normalize — bcftools norm
process BCFTOOLS_NORM {
    tag "${params.sample}"
    conda 'bioconda::bcftools=1.20'
    container 'quay.io/biocontainers/bcftools:1.20--h8b25389_0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    path calls
    tuple path(reference), path(reference_idx)

    output:
    path("*.norm.vcf.gz"), emit: filtered_vcf

    script:
    """
    bcftools norm -f ${reference} -Oz -o ${params.sample}.norm.vcf.gz ${calls}
    bcftools index -f ${params.sample}.norm.vcf.gz
    """

    stub:
    """
    touch ${params.sample}.norm.vcf.gz
    """
}
