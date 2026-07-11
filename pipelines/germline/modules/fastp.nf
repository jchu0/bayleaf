// Read QC + trim — fastp
process FASTP {
    tag "${params.sample}"
    conda 'bioconda::fastp=0.23.4'
    container 'quay.io/biocontainers/fastp:0.23.4--h5f740d0_0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    tuple path(read1), path(read2)

    output:
    tuple path("*.trim.R1.fastq.gz"), path("*.trim.R2.fastq.gz"), emit: fastq
    path("*.fastp.json"), emit: fastp_json

    script:
    """
    fastp -i ${read1} -I ${read2} \
      -o ${params.sample}.trim.R1.fastq.gz -O ${params.sample}.trim.R2.fastq.gz \
      -j ${params.sample}.fastp.json -h ${params.sample}.fastp.html -w ${task.cpus}
    """

    stub:
    """
    touch ${params.sample}.trim.R1.fastq.gz ${params.sample}.trim.R2.fastq.gz ${params.sample}.fastp.json
    """
}
