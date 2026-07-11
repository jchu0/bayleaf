// Coverage — mosdepth
process MOSDEPTH {
    tag "${params.sample}"
    conda 'bioconda::mosdepth=0.3.8'
    container 'quay.io/biocontainers/mosdepth:0.3.8--hd299d5a_0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    path dedup
    path panel

    output:
    path("*.mosdepth.summary.txt"), emit: mosdepth_summary
    path("*.thresholds.bed.gz"), emit: mosdepth_thresholds

    script:
    """
    samtools index ${dedup}
    mosdepth --by ${panel} --no-per-base --thresholds 1,10,20,30 -t ${task.cpus} \
      ${params.sample}.panel ${dedup}
    """

    stub:
    """
    touch ${params.sample}.panel.mosdepth.summary.txt ${params.sample}.panel.thresholds.bed.gz
    """
}
