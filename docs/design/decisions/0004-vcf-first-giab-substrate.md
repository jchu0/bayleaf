# ADR 0004 — VCF-first inputs on a GIAB substrate

- **Status:** accepted
- **Date:** 2026-07-07 (MST)
- **Related:** 0001, data/schemas.md, quality/evaluation.md

## Context
The product is the AI/provenance/decision layer, not the upstream genomics
pipeline. Building a real fastp → aligner → variant-calling pipeline first would
consume the build budget and block everything downstream. We also need real,
grounded data with known truth to evaluate rigorously, plus controlled failure
modes to exercise triage and retries.

## Decision
Develop **VCF-first**: the input contract is a per-sample bundle of VCF + QC
outputs (fastp / FastQC / MultiQC) + sample sheet/manifest. Use **GIAB HG002**
(NIST reference sample, open license, gold-standard truth VCF + high-confidence
BED) as the real substrate, framed as a rare-disease **germline DNA panel**
(short-read Illumina). Run a two-track dataset: real GIAB truth data for
correctness, and **synthetic perturbations** for labeled failure modes (sample
swap, duplicate/missing barcodes, low reads-PF, low Q30, coverage dropout,
low-support variant, contamination, step failure). Every artifact is tagged in
the provenance ledger as `real-giab` or `synthetic`. Generating pipeline outputs
end-to-end (nf-core/sarek) is a later stretch, not a blocker.

## Alternatives considered
- Build the upstream pipeline first — rejected: scope trap; blocks the product.
- Purely synthetic data — rejected: no ground truth for correctness/faithfulness.
- Purely real data — rejected: can't stage the failure modes the triage flow needs.

## Consequences
The product is unblocked from day one. GIAB truth doubles as evaluation ground
truth; synthetic data drives the four verdicts, retry logic, and seeds the agent
experience ledger. Clinical claims stay grounded in ClinVar/GIAB truth; planted
issues live in the operational layer (IDs, QC metrics, depth), never invented
pathogenicity. RNA-seq (STAR/salmon) is out of scope for the core.
