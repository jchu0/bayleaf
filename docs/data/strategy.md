# Data Strategy

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | all (contributors and Claude Code) |
| **Related** | [ADR-0004](../adr/ADR-0004-vcf-first-giab-substrate.md), [ADR-0007](../adr/ADR-0007-ml-ready-structured-outputs.md), [licensing.md](licensing.md), [schemas.md](schemas.md), [tasks T-013](../planning/tasks.md) |

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
6. **Real BAM-level building data.** To build and validate the coverage and
   contamination gates, use small **real test data** (a panel-region subset of GIAB HG002)
   rather than WGS. The fetch script
   ([`scripts/fetch_giab_hg002.py`](../../scripts/fetch_giab_hg002.py)) is **implemented and
   validated end-to-end** on a bioconda env — it pulls the real HG002 GRCh38 v4.2.1 truth VCF
   (+ tabix index) with the stdlib and, opt-in, slices a panel-region BAM via `samtools`. This
   yields real coverage/identity metrics for the coverage gate (ADR-0013); raw artifacts stay
   git-ignored (`data/real-giab/`), re-fetchable on demand.

## Origin labels

| Label | Meaning |
|---|---|
| `real-giab` | Real GIAB HG002 data (NIST) plus its gold-standard truth VCF / high-confidence BED |
| `synthetic` | Programmatically perturbed **from real data** to create labeled failure modes |
| `contrived` | Invented values, no real provenance — hand-authored *or* machine-generated (realistic formats, **not** derived from real data). The distinguishing axis from `synthetic` is real-data derivation, not authoring method: the [`pipeguard.synthetic`](../../src/pipeguard/synthetic/) generator emits `contrived` runs because its values are invented, not perturbed from a real sample. |

## Sources

1. **GIAB HG002** (NIST) — real short-read Illumina data + truth VCF + high-confidence BED. Open license.
2. **gnomAD** — population allele frequencies. **ClinVar** — clinical significance (public domain). Used for annotation, not gating claims.
3. **Failure-mode generator** ([`pipeguard.synthetic`](../../src/pipeguard/synthetic/)) —
   emits labeled failure-mode run directories (sample swap, duplicate/missing barcodes, low
   reads-PF, low Q30, coverage dropout, low-support variant, contamination, step failure). It
   is **`contrived`, not `synthetic`**: values are invented (realistic Illumina shapes), *not*
   perturbed from a real sample, so every run carries an in-band `pipeguard-synthetic`
   origin tag and is reproducible under `data/`. Perturbing real GIAB bundles into `synthetic`
   failure modes remains the aspirational upgrade (see origin labels below).

## Layout

1. `data/<run>/` — a run bundle: VCF + QC outputs + sample sheet/manifest.
2. Large raw inputs are fetched by script (accessions recorded), never committed.
3. `data/README.md` records the origin label of each dataset in the repo.

## Current state

Per-track status (each artifact labeled by origin):

1. **`contrived` — done.** `data/mock_run_01/` is hand-authored (realistic Illumina formats,
   invented values, two planted issues: S4 barcode swap, S5 borderline QC), labeled in
   [`data/README.md`](../../data/README.md). The [`pipeguard.synthetic`](../../src/pipeguard/synthetic/)
   generator now also emits `contrived` failure-mode runs programmatically (Sources 3).
2. **`real-giab` — fetch validated end-to-end.** The GIAB HG002 fetch script
   ([`scripts/fetch_giab_hg002.py`](../../scripts/fetch_giab_hg002.py)) runs end-to-end on a
   bioconda env (real truth VCF + panel-region reads slice); data stays git-ignored
   (`data/real-giab/`), never committed, re-fetchable ([tasks T-013](../planning/tasks.md)).
3. **`synthetic` (perturbed-from-real) — aspirational.** Deriving labeled failure modes by
   perturbing real GIAB bundles is the remaining upgrade over the `contrived` generator.
