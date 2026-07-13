// Contamination (FREEMIX) — verifybamid2
process VERIFYBAMID2 {
    tag "${meta.id}"
    conda 'bioconda::verifybamid2=2.0.1'
    container 'quay.io/biocontainers/verifybamid2:2.0.1--h9ee0642_2'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    tuple val(meta), path(dedup)
    tuple path(reference), path(reference_idx)
    path svd_prefix

    output:
    tuple val(meta), path("*.selfSM"), emit: selfsm

    script:
    """
    verifyBamID2 \
      --SVDPrefix ${svd_prefix} \
      --Reference ${reference} \
      --BamFile ${dedup} \
      --NumThread ${task.cpus} \
      --Output ${meta.id}.verifybamid2
    """

    stub:
    """
    printf '#SEQ_ID\\tRG\\tCHIP_ID\\t#SNPS\\t#READS\\tAVG_DP\\tFREEMIX\\tFREELK1\\tFREELK0\\tFREE_RH\\tFREE_RA\\tCHIPMIX\\tCHIPLK1\\tCHIPLK0\\tCHIP_RH\\tCHIP_RA\\tDPREF\\tRDPHET\\tRDPALT\\n' > ${meta.id}.verifybamid2.selfSM
    printf '${meta.id}\\tALL\\tNA\\t1000000\\t50000000\\t35.2\\t0.0042\\t1234.5\\t1250.0\\tNA\\tNA\\tNA\\tNA\\tNA\\tNA\\tNA\\t35.0\\t1.0\\t0.5\\n' >> ${meta.id}.verifybamid2.selfSM
    """
}
