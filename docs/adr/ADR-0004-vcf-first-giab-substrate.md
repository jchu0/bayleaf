# ADR-0004 — VCF-first inputs on a GIAB substrate

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-07 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | ADR-0001, ADR-0007 |

## Context

The product is the AI/provenance/decision layer, not the upstream genomics
pipeline. Building a real fastp → aligner → variant-calling pipeline first would
consume the build budget and block everything downstream. We also need real,
grounded data with known truth to evaluate rigorously, plus controlled failure
modes to exercise triage and retries.

## Decision

Develop **VCF-first**: the input contract is a per-sample bundle of VCF + QC
outputs (fastp / FastQC / MultiQC) + sample sheet/manifest. Use **GIAB HG002**
(NIST reference sample; open license; gold-standard truth VCF + high-confidence
BED) as the real substrate, framed as a rare-disease **germline DNA panel**
(short-read Illumina). Run a two-track dataset: real GIAB truth data for
correctness, and **synthetic perturbations** for labeled failure modes (sample
swap, duplicate/missing barcodes, low reads-PF, low Q30, coverage dropout,
low-support variant, contamination, step failure). Every artifact is tagged in
the provenance ledger as `real-giab` or `synthetic`. End-to-end generation
(nf-core/sarek) is a later stretch, not a blocker.

## Assumptions

- GIAB HG002 is representative enough for the gate's logic.
- Synthetic perturbations can stand in for the operational failure modes we need.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Build the upstream pipeline first | Scope trap; blocks the product |
| Purely synthetic data | No ground truth for correctness/faithfulness |
| Purely real data | Can't stage the failure modes the triage flow needs |

## Consequences

| | |
|---|---|
| **Gains** | Product unblocked from day one; GIAB truth doubles as evaluation ground truth; synthetic data drives all four verdicts, retries, and seeds the experience ledger |
| **Costs** | A synthetic-data generator to build and keep labeled |
| **Follow-ups** | Clinical claims stay grounded in ClinVar/GIAB truth; planted issues live only in the operational layer. RNA-seq (STAR/salmon) is out of core scope |

## Revisit when

- We need end-to-end pipeline outputs, a different reference sample, or a real
  clinical panel definition.
