// Variant calling — bcftools call
process BCFTOOLS_CALL {
    tag "${meta.id}"
    conda 'bioconda::bcftools=1.20'
    container 'quay.io/biocontainers/bcftools:1.20--h8b25389_0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    tuple val(meta), path(dedup)
    tuple path(reference), path(reference_idx)
    path panel

    output:
    tuple val(meta), path("*.calls.vcf.gz"), emit: vcf

    script:
    """
    samtools index ${dedup}
    bcftools mpileup -f ${reference} -R ${panel} -Ou ${dedup} \
      | bcftools call -mv -Oz -o ${meta.id}.calls.vcf.gz
    """

    stub:
    """
    touch ${meta.id}.calls.vcf.gz
    """
}
