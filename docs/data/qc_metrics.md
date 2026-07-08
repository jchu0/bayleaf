# QC Metrics — Runbook

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-07 (MST) |
| **Audience** | bioinformatics / software |
| **Related** | [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [qc_metrics-sources.md](qc_metrics-sources.md) (field names), [qc_metrics-rare-disease.md](qc_metrics-rare-disease.md) (cited thresholds) |

## Overview

The decided QC runbook. Operator-owned and **config-driven — no hardcoded universal
thresholds** (guidelines defer to per-assay validation). Field names are verified in
`qc_metrics-sources.md`; the defaults here are **cited guideline examples**, all
adjustable per assay. Scoped to **Illumina** (MiSeq, NextSeq, NovaSeq, NovaSeq X).
Three checkpoints per ADR-0013.

## Principles

1. **No hardcoded universal thresholds.** Each assay has a validated, stated config;
   the gate checks the run against *that*. Guideline examples are the shipped defaults.
   Operators adjust thresholds; **user-defined custom metrics are a future goal**.
2. **Gate on breadth/callability, not just mean depth.** `% target ≥ 20×` (panel/WES)
   or `% genome ≥ 15×` (WGS) + a per-base callable floor; gaps in reportable regions
   → HOLD + orthogonal/Sanger fill, never silent fail.
3. **Depth is per-modality; Q30 is per platform × read-length** (matrix below).
4. **Surface and decide** (ADR-0013): most breaches → HOLD or ESCALATE; RERUN only
   for operational / file-system failures.
5. **Normalize units** — fastp fields are fractions (0–1); MultiQC are percentages.

## Gate 1 — Preflight / intake (before the queue)

Run-level Illumina QC + FASTQ sanity, with a **manual override** for genuinely-sparse
edge cases.

| Metric | Field / source | Default (cited, configurable) | On breach |
|---|---|---|---|
| % PhiX aligned | SAV / InterOp | > 90% → clustering failure ("didn't sequence it") | reject / ESCALATE (override-able) |
| % ≥ Q30 (platform-aware) | run QC | platform matrix below | HOLD |
| Yield (reads / Gb) | run QC / fastp | ≥ per-assay need | HOLD |
| Per-sample FASTQ sanity | file | read count > 0, plausible size | ESCALATE (empty) / HOLD |
| Barcode / index integrity | sample sheet vs demux | exact match, unique, no collision | ESCALATE |

## Gate 2 — QC gate (processing quality; breadth-first)

| Metric | Field (sources doc) | Default (cited, configurable) | On breach |
|---|---|---|---|
| Q30 | fastp `q30_rate` (fraction) | platform matrix | HOLD |
| Duplication | Picard `PERCENT_DUPLICATION` | assay-tuned (WES < 20%; amplicon high by design) | HOLD |
| % mapped | flagstat | ≥ 95% (ROT) | HOLD |
| On-target rate | Picard `PCT_SELECTED_BASES` | assay-tuned (hyb ~80%, amplicon ~90%) | HOLD |
| **Breadth: % target ≥ 20×** | mosdepth / Picard `PCT_TARGET_BASES_20X` | **≥ 99% (ACGS example)** | HOLD |
| Mean/median coverage (per-modality) | mosdepth / Picard | panel 100–500×, WES ~100×, WGS ~30× | HOLD |
| Callable floor / gaps in reportable regions | mosdepth per-base | 0 gaps; else describe + fill | HOLD (+ Sanger) |
| Uniformity (fold-80) | Picard `FOLD_80_BASE_PENALTY` | < 2 (ROT) | HOLD |
| Sample identity / swap | **NGSCheckMate** (sarek germline: `ngscheckmate_matched.txt`) + sex-vs-coverage | concordant; no swap | ESCALATE |
| Contamination (optional) | VerifyBamID2 `FREEMIX` — **extra step, not sarek-default** | > 3% fail (GE); band 1.5–3% | ESCALATE |

## Gate 3 — Variant gate (output; caller-aware)

| Metric | Field | Default (cited) | On breach |
|---|---|---|---|
| Depth (DP) | VCF `FORMAT/DP` | ≥ 10–20× (ACMG / Pedersen) | HOLD |
| Genotype quality (GQ) | VCF `GQ` | ≥ 20 (Pedersen 2021) | HOLD |
| Allele balance (het) | VCF `AD` → AB | 0.2–0.8, ≈0.5 (Pedersen) | HOLD |
| Caller-appropriate filters | GATK `QD<2.0`… / DeepVariant / FreeBayes | **caller-specific** (QUAL is not portable) | HOLD |
| Ti/Tv (callset sanity) | Picard / bcftools | ~3.0 WES, ~2.0 WGS — trend, not per-variant gate | HOLD (advisory) |
| Het/Hom SNV ratio | bcftools | < 3 (GE) | HOLD |
| Flagged variant: gnomAD AF + ClinVar | `INFO/AF`, `CLNSIG` | rare-disease AF cutoffs; ClinVar 5-tier | ESCALATE / HOLD |

## Verdict policy (ADR-0013)

1. Borderline (near the configured default) → **HOLD**.
2. Provenance / identity (barcode, contamination, sex, swap) → **ESCALATE**.
3. Operational / file-system failures (network, missing files, distributed-FS race
   conditions, step crash) → **RERUN**.
4. Clean → **PROCEED**. Worst verdict wins.
5. Depth vs breadth are surfaced as distinct signals. Every decision + resolution is
   recorded to the experience corpora (ADR-0009).

## CNV & mosaicism

Out of gate scope (no dedicated caller — wishlist). But the coverage-uniformity and
allele-balance signals above let the QC-triage agent make **advisory** CNV/dropout or
mosaic-suggestive observations (agent depth) — without asserting a call.

## Sample type

Thresholds are also **sample-type-aware** (scope: **whole blood**, **saliva**).
Saliva carries oral-microbiome DNA, so vs. blood it typically shows **lower
human-mapped %, lower on-target rate, and lower/variable human yield** — loosen the
mapping / on-target / yield gates for saliva. This is **microbial** content, *not*
cross-sample human contamination: VerifyBamID2 `FREEMIX` (SNP-based, human–human) is
largely unaffected, so the contamination gate is unchanged. `sample_type` is a
first-class metadata field (feeds the record schema); a runbook profile keys on
**assay × sample type**.

## Platform matrix — Illumina % ≥ Q30 (vendor RUO spec, not a clinical gate)

| Platform | Read length → expected % ≥ Q30 |
|---|---|
| NovaSeq 6000 v1.5 | 2×50 ≥ 90% · 2×150 ≥ 85% · 2×250 ≥ 75% |
| NovaSeq X | 2×150 ≥ 85% · 2×300 ≥ 75% |
| MiSeq | v2 2×150 > 80% · v3 2×75 > 85% |
| NextSeq | verify per kit — **TODO: add from spec sheet** |

The Q30 gate = the platform × read-length expected value, operator-adjustable.

## Config model & test-data validation

Thresholds live in an operator-owned runbook **profile** keyed on **assay × sample
type** (whole blood / saliva). We ship two:
1. A **guideline-default profile** — the cited defaults above.
2. A concrete **test-data profile** tuned to our GIAB HG002 panel-subset — **pending
   [T-017](../planning/tasks.md)** (fetch a small real FASTQ→BAM). This gives the gate
   real numbers to validate against, with **no hardcoded universals**: the test-data
   profile is configured to what that dataset actually achieves.
