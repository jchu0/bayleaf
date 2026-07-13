// Cross-sample contamination — verifybamid2 (FREEMIX). OPTIONAL add-on: NOT in the germline base
// profile. It lives in `pipelines/optional_modules/` (NOT `pipelines/germline/`) on purpose: the
// germline reference dir is a byte-for-byte mirror of the card-graph compiler's output (drift-tested),
// and the compiler has no concept of an input-gated conditional module — so an optional tool cannot
// be a committed germline file without either being always-on or breaking the drift lock. The
// maintainer's LIVE pass wires this into an extended workflow (downstream of markdup) guarded on an
// operator-supplied ancestry SVD/UD resource panel (`--SVDPrefix`), a LABELLED pipeline input never
// fabricated here (ADR-0004). The publish dir (`*.selfSM`) is what `ingest.nfcore` already parses.
process VERIFYBAMID2 {
    tag "${meta.id}"
    conda 'bioconda::verifybamid2=2.0.1'
    container 'quay.io/biocontainers/verifybamid2:2.0.1--h9ee0642_2'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    tuple val(meta), path(dedup)
    tuple path(reference), path(reference_idx)
    val svd_prefix

    output:
    tuple val(meta), path("*.selfSM"), emit: selfsm
    tuple val(meta), path("*.Ancestry"), emit: ancestry, optional: true

    script:
    // The standard verifyBamID2 invocation: estimate contamination for one BAM against the SVD/UD
    // ancestry panel. `--SVDPrefix` points at the operator-supplied resource; `--Reference` the same
    // FASTA the alignment used. Emits `${meta.id}.verifybamid2.selfSM` (FREEMIX in the 7th column).
    """
    verifyBamID2 \
      --SVDPrefix ${svd_prefix} \
      --Reference ${reference} \
      --BamFile ${dedup} \
      --NumThread ${task.cpus} \
      --Output ${meta.id}.verifybamid2
    """

    stub:
    // OFFLINE stub — emits a realistic `.selfSM` (real header + one FREEMIX row) WITHOUT running the
    // tool (compose ≠ execute, ADR-0001/0003), so the ingest adapter can be exercised on fixture
    // data. `\\t`/`\\n` reach bash printf literally (Groovy un-escapes one backslash) → real TSV.
    """
    printf '#SEQ_ID\\tRG\\tCHIP_ID\\t#SNPS\\t#READS\\tAVG_DP\\tFREEMIX\\tFREELK1\\tFREELK0\\tFREE_RH\\tFREE_RA\\tCHIPMIX\\tCHIPLK1\\tCHIPLK0\\tCHIP_RH\\tCHIP_RA\\tDPREF\\tRDPHET\\tRDPALT\\n' > ${meta.id}.verifybamid2.selfSM
    printf '${meta.id}\\tALL\\tNA\\t1000000\\t50000000\\t35.2\\t0.0042\\t1234.5\\t1250.0\\tNA\\tNA\\tNA\\tNA\\tNA\\tNA\\tNA\\t35.0\\t1.0\\t0.5\\n' >> ${meta.id}.verifybamid2.selfSM
    """
}
