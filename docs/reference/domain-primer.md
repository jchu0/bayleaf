# Domain Primer — Rare-Disease Germline Sequencing

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | software / all (non-genomics readers) |
| **Related** | [glossary.md](glossary.md), [data/strategy.md](../data/strategy.md), [data/qc_metrics-rare-disease.md](../data/qc_metrics-rare-disease.md), [data/qc_metrics-sources.md](../data/qc_metrics-sources.md), [design/architecture.md](../design/architecture.md) |

## Overview

Orientation for a reader without a genomics background: what PipeGuard's domain is,
enough vocabulary to read the rest of the docs, and why a per-sample QC + provenance
gate is worth building. This primer explains the *domain*; the *system* is in
[architecture.md](../design/architecture.md), and precise terms are in the
[glossary](glossary.md). Numbers here are cited guideline **examples**, not clinical
thresholds — the runbook treats them as configurable defaults ([qc_metrics.md](../data/qc_metrics.md)).

## 1. The problem space: rare-disease germline panels

1. **Germline** means the inherited (constitutional) genome the patient was born
   with — the same in every cell — as opposed to *somatic* mutations that a tumor
   acquires. **Fact:** constitutional variants are heterozygous at roughly 50%
   variant-allele fraction (one of two gene copies), which shapes the whole QC
   picture (source: [qc_metrics-rare-disease.md](../data/qc_metrics-rare-disease.md) §Headline).
2. **Rare disease** here means looking for the one (or few) causal variant(s)
   behind an individual patient's condition, often across a family (a proband plus
   parents — a **trio**). Because the answer can hinge on a single position, being
   *sure you can see every reportable position* matters more than raw read count.
3. **Panel** means sequencing only a curated set of disease-relevant genes (a
   targeted assay), rather than the whole exome (**WES**) or whole genome (**WGS**).
   PipeGuard's stated domain is a **rare-disease germline DNA panel, Illumina
   short-read** ([architecture.md](../design/architecture.md)).

## 2. Depth, breadth, and why "deep like cancer" is misleading

A recurring confusion, resolved in the literature review
([qc_metrics-rare-disease.md](../data/qc_metrics-rare-disease.md) §Headline). Two
distinct axes:

1. **Depth** — how many reads cover a given base (e.g. "30×").
2. **Breadth / callability** — what *fraction* of the reportable region is covered
   deeply enough to call confidently.

Key points, all cited as guideline **examples** (not universal gates):

1. **Fact (magnitude):** typical mean depths are WGS ~30×, WES ~100×, panel
   ~100–500×. A panel's number *looks* cancer-like.
2. **Fact (rationale):** the reason differs. Cancer/ctDNA goes deep to detect
   *low-fraction* somatic variants (depth ∝ 1/VAF). A germline panel goes deep for
   **breadth and uniformity** — insurance that every reportable base clears the
   het-calling floor — because a ~50%-fraction heterozygote is already easy to see
   at ~15–20× local depth (>99% het sensitivity).
3. **Consequence:** for rare disease the distinguishing QC question is *breadth /
   callability of the reportable regions* plus genotype confidence and
   family/identity checks — not low-fraction sensitivity. Gaps in reportable
   regions are described and filled orthogonally (e.g. Sanger), not silently failed.

> **No universal depth number.** Major guidelines (ACMG, ACGS, EuroGentest,
> CAP/AMP) deliberately set *no* single hard depth threshold and defer the minimum
> to per-assay validation ([qc_metrics-rare-disease.md](../data/qc_metrics-rare-disease.md)
> §1). PipeGuard follows this: thresholds are per-assay config, not hardcoded facts.

## 3. From instrument to variants: the short-read pipeline

The upstream genomics pipeline is *input generation* and is out of PipeGuard's scope
(ADR-0004); PipeGuard reads its outputs. Reference stages
([qc_metrics-sources.md](../data/qc_metrics-sources.md)):

1. **Sequencing (Illumina short-read).** The instrument (e.g. NovaSeq, MiSeq)
   produces short reads and per-run quality signals — cluster pass-filter, error
   rate, and **%≥Q30** (the fraction of base calls with a Phred quality ≥30,
   i.e. ≤1-in-1000 estimated error). Q30 expectations are **platform × read-length**
   specific vendor specs, not clinical gates ([qc_metrics.md](../data/qc_metrics.md)
   platform matrix).
2. **Demultiplexing (demux) / barcoding.** A run pools many samples; each library
   carries **index barcodes** (an i7 and often an i5 sequence). Demux software reads
   the indexes and sorts reads back to the right sample using a **sample sheet**
   that declares which barcode belongs to which sample. **Why it matters here:** a
   duplicated, missing, or swapped barcode is a *chain-of-custody* failure — the
   right data attributed to the wrong patient — so PipeGuard treats barcode/index
   integrity as a hard provenance check at the preflight gate
   ([qc_metrics-sources.md](../data/qc_metrics-sources.md) §B).
3. **Alignment + QC.** Reads are trimmed (fastp), mapped to the reference genome,
   deduplicated, and summarized (mosdepth for coverage, Picard/samtools for
   alignment stats, MultiQC to aggregate). Contamination and sample-swap checks
   (VerifyBamID2, NGSCheckMate) confirm the data is one clean individual.
4. **Variant calling + annotation.** A caller (e.g. GATK, DeepVariant, FreeBayes)
   produces a **VCF** listing where the sample differs from the reference, with
   per-genotype depth (DP), genotype quality (GQ), and allele balance. Variants are
   then annotated with population frequency and clinical databases (below).

## 4. The reference and annotation data

1. **GIAB HG002 (the truth set).** Genome in a Bottle (a NIST-led consortium)
   provides real Illumina data for well-characterized reference samples plus a
   **gold-standard "truth" VCF and a high-confidence BED** marking regions where the
   truth is trustworthy. **Why it matters:** it is real data with a *known right
   answer*, so it can serve as ground truth to check that a tool's calls (and, for
   PipeGuard, its verdicts) are correct — an eventual Phase-2 evaluation substrate
   ([strategy.md](../data/strategy.md), [quality/evaluation.md](../quality/evaluation.md)).
   Open license.
2. **gnomAD (population frequency).** Aggregated allele frequencies across large
   populations. A variant common in gnomAD is unlikely to cause a rare disease; a
   very rare one is more plausibly relevant. Used as an *annotation* to help
   prioritize, not as a gating claim.
3. **ClinVar (clinical significance).** A public archive of reported variant
   interpretations (pathogenic / likely-pathogenic / uncertain / likely-benign /
   benign, with a review-confidence "star" level). Public domain; used for
   annotation only.

> **Guardrail.** gnomAD/ClinVar are used to *annotate and surface*, never to assert
> pathogenicity. PipeGuard makes **no diagnostic, therapeutic, or pathogenicity
> claims** (CLAUDE.md life-science guardrails); clinical variant statements stay
> grounded in ClinVar/GIAB truth and are never invented.

## 5. Why a per-sample QC + provenance gate matters

After a run finishes, an operator must decide, **per sample**, whether to proceed,
hold, rerun, or escalate — today by hand-combing logs and QC reports. In a
rare-disease context two failure modes are especially costly:

1. **A mis-attributed sample** (barcode swap, contamination, sample-swap) — the
   right analysis on the wrong patient's data. This is a provenance problem, which
   is why identity/barcode issues **escalate**.
2. **A silently under-covered reportable region** — a real variant that was never
   callable because breadth fell short in that gene. This is why the gate surfaces
   *breadth* distinctly from *depth*.

A per-sample gate that (a) makes the call from **cited, rule-derived evidence**, (b)
separates depth from breadth, and (c) records every input and decision in an
**append-only provenance ledger** turns a manual, siloed judgment into a traceable,
auditable one. How PipeGuard implements this — the three-gate model, the
rules-decide/AI-advises invariant, and the event ledger — is in
[architecture.md](../design/architecture.md); this primer only motivates *why*.

---

*Marker legend:* **Fact** (cited to a grounded source) · **Assumption** ·
**Decision** · **TODO**. Numbers in this primer are guideline examples, treated by
the runbook as configurable defaults — **not** calibrated clinical thresholds.
