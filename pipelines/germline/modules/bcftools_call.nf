// Variant calling — bcftools call
process BCFTOOLS_CALL {
    tag "${params.sample}"
    conda 'bioconda::bcftools=1.20'
    container 'quay.io/biocontainers/bcftools:1.20--h8b25389_0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    path dedup
    tuple path(reference), path(reference_idx)
    path panel

    output:
    path("*.calls.vcf.gz"), emit: vcf

    script:
    """
    samtools index ${dedup}
    bcftools mpileup -f ${reference} -R ${panel} -Ou ${dedup} \
      | bcftools call -mv -Oz -o ${params.sample}.calls.vcf.gz
    """

    stub:
    """
    touch ${params.sample}.calls.vcf.gz
    """
}
