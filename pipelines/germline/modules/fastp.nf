// Read QC + trim — fastp
process FASTP {
    tag "${meta.id}"
    conda 'bioconda::fastp=0.23.4'
    container 'quay.io/biocontainers/fastp:0.23.4--h5f740d0_0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    tuple val(meta), path(read1), path(read2)

    output:
    tuple val(meta), path("*.trim.R1.fastq.gz"), path("*.trim.R2.fastq.gz"), emit: fastq
    tuple val(meta), path("*.fastp.json"), emit: fastp_json
    tuple val(meta), path("*.fastp.html"), emit: fastp_html
    tuple val(meta), path("*.unpaired.fastq.gz"), emit: unpaired_fastq
    tuple val(meta), path("*.failed.fastq.gz"), emit: failed_fastq

    script:
    """
    fastp -i ${read1} -I ${read2} \
      -o ${meta.id}.trim.R1.fastq.gz -O ${meta.id}.trim.R2.fastq.gz \
      --unpaired1 ${meta.id}.unpaired.fastq.gz --unpaired2 ${meta.id}.unpaired.fastq.gz \
      --failed_out ${meta.id}.failed.fastq.gz \
      -j ${meta.id}.fastp.json -h ${meta.id}.fastp.html -w ${task.cpus}
    """

    stub:
    """
    touch ${meta.id}.trim.R1.fastq.gz ${meta.id}.trim.R2.fastq.gz ${meta.id}.unpaired.fastq.gz ${meta.id}.failed.fastq.gz ${meta.id}.fastp.json ${meta.id}.fastp.html
    """
}
