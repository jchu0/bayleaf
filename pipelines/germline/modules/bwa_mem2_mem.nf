// Alignment — bwa-mem2
process BWA_MEM2_MEM {
    tag "${meta.id}"
    conda 'bioconda::bwa-mem2=2.2.1 bioconda::samtools=1.20'
    container 'quay.io/biocontainers/mulled-v2-e5d375990341c5aef3c9aff74f96f66f65375ef6:beb9b76a4c73c05e0b4b4f3fda67c9e1e5b6dc4f-0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    tuple val(meta), path(read1), path(read2)
    tuple path(reference), path(reference_idx)

    output:
    tuple val(meta), path("*.aligned.bam"), emit: bam

    script:
    """
    bwa-mem2 mem -t ${task.cpus} \
      -R "@RG\tID:${meta.id}\tSM:${meta.id}\tPL:ILLUMINA\tLB:${meta.id}-panel" \
      ${reference} ${read1} ${read2} \
      | samtools sort -n -@ ${task.cpus} -O bam - \
      | samtools fixmate -m - - \
      | samtools sort -@ ${task.cpus} -O bam -o ${meta.id}.aligned.bam -
    """

    stub:
    """
    touch ${meta.id}.aligned.bam
    """
}
