// Filter / normalize — bcftools norm
process BCFTOOLS_NORM {
    tag "${meta.id}"
    conda 'bioconda::bcftools=1.20'
    container 'quay.io/biocontainers/bcftools:1.20--h8b25389_0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    tuple val(meta), path(calls)
    tuple path(reference), path(reference_idx)

    output:
    tuple val(meta), path("*.norm.vcf.gz"), emit: filtered_vcf

    script:
    """
    bcftools norm -f ${reference} -Oz -o ${meta.id}.norm.vcf.gz ${calls}
    bcftools index -f ${meta.id}.norm.vcf.gz
    """

    stub:
    """
    touch ${meta.id}.norm.vcf.gz
    """
}
