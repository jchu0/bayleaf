# Data Strategy

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-07 (MST) |
| **Audience** | all (contributors and Claude Code) |
| **Related** | [ADR-0004](../adr/ADR-0004-vcf-first-giab-substrate.md), [ADR-0007](../adr/ADR-0007-ml-ready-structured-outputs.md), [tasks T-013](../planning/tasks.md) |

## Overview

How PipeGuard sources, labels, and stores its data. The through-line: **every
artifact is labeled by origin**, so real reference data, programmatically
perturbed data, and hand-authored demo data are never confused — a hard
requirement for a provenance tool.

## Principles

1. **VCF-first.** Develop against per-sample bundles of VCF + QC outputs
   (fastp / FastQC / MultiQC) + sample sheet/manifest. The upstream genomics
   pipeline is input generation and is deferred (ADR-0004).
2. **Dual track.** Real GIAB truth data for correctness and faithfulness;
   synthetic perturbations for labeled failure modes (triage, retries, verdicts).
3. **Label every artifact by origin** (see table below). The label is carried in
   the provenance ledger and, later, in the record schemas (ADR-0007).
4. **Don't commit large or raw data.** Commit accessions + a fetch script; raw
   reads and large artifacts stay out of git (see `.gitignore`).
5. **ML-ready outputs.** Structured, schema-versioned, and labeled, so the ledgers
   double as an ML corpus (ADR-0007).

## Origin labels

| Label | Meaning |
|---|---|
| `real-giab` | Real GIAB HG002 data (NIST) plus its gold-standard truth VCF / high-confidence BED |
| `synthetic` | Programmatically perturbed from real data to create labeled failure modes |
| `contrived` | Hand-authored demo data — realistic formats, invented values (no real provenance) |

## Sources

1. **GIAB HG002** (NIST) — real short-read Illumina data + truth VCF + high-confidence BED. Open license.
2. **gnomAD** — population allele frequencies. **ClinVar** — clinical significance (public domain). Used for annotation, not gating claims.
3. **Synthetic generator** — perturbs GIAB-derived bundles into labeled failure modes (sample swap, duplicate/missing barcodes, low reads-PF, low Q30, coverage dropout, low-support variant, contamination, step failure).

## Layout

1. `data/<run>/` — a run bundle: VCF + QC outputs + sample sheet/manifest.
2. Large raw inputs are fetched by script (accessions recorded), never committed.
3. `data/README.md` records the origin label of each dataset in the repo.

## Current state

**Fact:** `data/mock_run_01/` is **`contrived`** — hand-authored in session 1 with
realistic Illumina formats but invented values (barcodes, QC numbers, and the two
planted issues: S4 barcode swap, S5 borderline QC). It is **not** GIAB data. It is
labeled in [`data/README.md`](../../data/README.md) and will be superseded or
augmented by `real-giab` + `synthetic` bundles ([tasks T-013](../planning/tasks.md)).
