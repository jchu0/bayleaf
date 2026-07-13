// GIAB truth concordance — hap.py (SNP/INDEL Recall/Precision/F1). OPTIONAL benchmarking add-on:
// NOT in the germline base profile. Like verifybamid2 it lives in `pipelines/optional_modules/`
// (NOT `pipelines/germline/`) because the germline dir is a byte-for-byte mirror of the card-graph
// compiler output (drift-tested) and the compiler has no input-gated-conditional concept.
//
// A LIVE run needs a GIAB TRUTH VCF + a high-confidence BED — LABELLED pipeline inputs the operator
// supplies for the benchmarked sample (e.g. GIAB HG002 v4.2.1); they are NEVER invented or hardcoded
// here (ADR-0004: never fabricate truth). The publish dir (`*.summary.csv`) is what `ingest.nfcore`
// already parses (the SNP + PASS row's METRIC.F1_Score). Compose != execute — emitted, never run.
process HAPPY {
    tag "${meta.id}"
    conda 'bioconda::hap.py=0.3.15'
    container 'quay.io/biocontainers/hap.py:0.3.15--py27h5c5a3ab_0'
    publishDir "${params.outdir}/results", mode: 'copy'

    input:
    tuple val(meta), path(query_vcf)
    tuple path(reference), path(reference_idx)
    path truth_vcf
    path confident_bed

    output:
    tuple val(meta), path("*.summary.csv"), emit: happy_summary
    tuple val(meta), path("*.extended.csv"), emit: happy_extended, optional: true

    script:
    // Standard hap.py invocation: benchmark the query VCF against the GIAB truth VCF, restricted to
    // the high-confidence BED, on the same reference FASTA. Emits `${meta.id}.happy.summary.csv`.
    """
    hap.py \
      ${truth_vcf} \
      ${query_vcf} \
      -o ${meta.id}.happy \
      -r ${reference} \
      -f ${confident_bed} \
      --threads ${task.cpus}
    """

    stub:
    // OFFLINE stub — emits a realistic `summary.csv` (real header + the four Type/Filter rows) WITHOUT
    // running the tool (compose != execute, ADR-0001/0003), so the ingest adapter can be exercised on
    // fixture data. `\\n` reaches bash printf literally (Groovy un-escapes one backslash) → real CSV.
    """
    printf 'Type,Filter,TRUTH.TOTAL,TRUTH.TP,TRUTH.FN,QUERY.TOTAL,QUERY.FP,QUERY.UNK,FP.gt,FP.al,METRIC.Recall,METRIC.Precision,METRIC.Frac_NA,METRIC.F1_Score,TRUTH.TOTAL.TiTv_ratio,QUERY.TOTAL.TiTv_ratio,TRUTH.TOTAL.het_hom_ratio,QUERY.TOTAL.het_hom_ratio\\n' > ${meta.id}.happy.summary.csv
    printf 'INDEL,ALL,500000,490000,10000,510000,5000,8000,300,200,0.9800,0.9900,0.0157,0.9850,,,1.4,1.42\\n' >> ${meta.id}.happy.summary.csv
    printf 'INDEL,PASS,500000,485000,15000,495000,3000,7000,200,150,0.9700,0.9940,0.0141,0.9818,,,1.4,1.41\\n' >> ${meta.id}.happy.summary.csv
    printf 'SNP,ALL,3000000,2960000,40000,3020000,9000,22000,600,400,0.9867,0.9970,0.0073,0.9918,2.05,2.06,1.5,1.52\\n' >> ${meta.id}.happy.summary.csv
    printf 'SNP,PASS,3000000,2985000,15000,3005000,2000,20000,200,100,0.9950,0.9993,0.0066,0.9971,2.05,2.06,1.5,1.52\\n' >> ${meta.id}.happy.summary.csv
    """
}
