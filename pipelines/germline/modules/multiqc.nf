// QC aggregation — MultiQC
process MULTIQC {
    conda 'bioconda::multiqc=1.21'
    container 'quay.io/biocontainers/multiqc:1.21--pyhdfd78af_0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    path('*')
    path('*')
    path('*')
    path('*')
    path('*')

    output:
    path("multiqc_data/multiqc_data.json"), emit: multiqc_json
    path("multiqc_report.html"), emit: multiqc_html

    script:
    """
    multiqc . --data-format json
    """

    stub:
    """
    mkdir -p multiqc_data && touch multiqc_data/multiqc_data.json multiqc_report.html
    """
}
