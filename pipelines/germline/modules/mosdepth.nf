// Coverage — mosdepth
process MOSDEPTH {
    tag "${meta.id}"
    conda 'bioconda::mosdepth=0.3.8'
    container 'quay.io/biocontainers/mosdepth:0.3.8--hd299d5a_0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    tuple val(meta), path(dedup)
    path panel

    output:
    tuple val(meta), path("*.mosdepth.summary.txt"), emit: mosdepth_summary
    tuple val(meta), path("*.thresholds.bed.gz"), emit: mosdepth_thresholds
    tuple val(meta), path("*.regions.bed.gz"), emit: mosdepth_regions
    tuple val(meta), path("*.mosdepth.global.dist.txt"), emit: mosdepth_global_dist
    tuple val(meta), path("*.mosdepth.region.dist.txt"), emit: mosdepth_region_dist

    script:
    """
    samtools index ${dedup}
    mosdepth --by ${panel} --no-per-base --thresholds 1,10,20,30 -t ${task.cpus} \
      ${meta.id}.panel ${dedup}
    """

    stub:
    """
    touch ${meta.id}.panel.mosdepth.summary.txt ${meta.id}.panel.thresholds.bed.gz ${meta.id}.panel.regions.bed.gz ${meta.id}.panel.mosdepth.global.dist.txt ${meta.id}.panel.mosdepth.region.dist.txt
    """
}
