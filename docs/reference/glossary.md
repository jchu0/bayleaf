# Glossary

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | all |
| **Related** | [domain-primer.md](domain-primer.md), [data/qc_metrics.md](../data/qc_metrics.md), [data/qc_metrics-sources.md](../data/qc_metrics-sources.md), [data/schemas.md](../data/schemas.md), [design/architecture.md](../design/architecture.md) |

## Overview

One-line definitions across three vocabularies: **bioinformatics/QC**, **software /
architecture**, and **the product**. Definitions match how these terms are used in
this repo; genomics numbers cited elsewhere are guideline examples, not clinical
thresholds. For fuller context see the [domain primer](domain-primer.md).

## Bioinformatics & QC

1. **Allele balance (AB)** — for a heterozygous call, the fraction of reads
   supporting the alternate allele; expected ≈0.5, with a typical band 0.2–0.8
   ([qc_metrics.md](../data/qc_metrics.md)).
2. **Barcode / index (i7, i5)** — short synthetic sequences added per library so
   pooled samples can be sorted back after sequencing; dual-index uses both i7 and
   i5.
3. **BCL Convert / bcl2fastq** — Illumina demultiplexing software that converts raw
   base-call files to per-sample FASTQ using the sample sheet.
4. **bcftools** — toolkit for manipulating and computing stats over VCF/BCF variant
   files.
5. **Breadth (of coverage)** — the fraction of a target region covered at or above a
   depth threshold (e.g. "% of target ≥20×"); the rare-disease-distinguishing QC
   axis, distinct from depth.
6. **Callability** — whether a region has enough reliable coverage to make confident
   genotype calls; gaps in reportable regions are described and orthogonally filled,
   not silently failed.
7. **ClinVar** — public archive of reported clinical significance for variants
   (pathogenic → benign, with review-confidence stars); used for annotation only.
8. **Contamination** — presence of DNA from another individual in a sample;
   quantified for germline by a cross-sample metric (see FREEMIX).
9. **Coverage depth** — the number of reads covering a base (e.g. 30×); typical
   means WGS ~30×, WES ~100×, panel ~100–500× (guideline examples).
10. **Demultiplexing (demux)** — sorting pooled reads back to their source sample by
    reading index barcodes against the sample sheet.
11. **Depth (DP)** — VCF `FORMAT/DP`: read depth supporting a genotype call.
12. **Duplication** — the fraction of reads that are PCR/optical duplicates; assay-
    dependent (high by design for amplicon).
13. **fastp** — read trimming / filtering tool that emits per-sample read-QC JSON
    (Q30, duplication, etc.) as fractions (0–1).
14. **FASTQ** — text format holding sequencing reads and per-base quality scores.
15. **FREEMIX** — VerifyBamID2's cross-sample contamination estimate (fraction);
    illustrative default flags >3% ([qc_metrics.md](../data/qc_metrics.md)).
16. **Germline** — the inherited (constitutional) genome, identical across cells;
    contrasted with somatic (tumor-acquired) variants.
17. **GIAB (Genome in a Bottle)** — NIST-led consortium providing well-characterized
    reference samples (e.g. **HG002**) with a gold-standard truth VCF and
    high-confidence BED; open license.
18. **gnomAD** — aggregated population allele frequencies; used to prioritize (rare =
    more plausibly relevant), not to gate.
19. **GQ (genotype quality)** — Phred-scaled confidence in a genotype call;
    illustrative floor GQ ≥ 20 (Pedersen 2021).
20. **MultiQC** — aggregator that collects many tools' QC outputs into one report;
    its `pct_*` fields are percentages (×100), a normalization trap vs fastp
    fractions.
21. **mosdepth** — fast per-base / per-region coverage tool; source for depth and
    breadth (`% target ≥ N×`).
22. **NGSCheckMate** — sample-identity / swap detector comparing genotype
    fingerprints across a run; the QC-gate identity check.
23. **nf-core/sarek** — the nf-core germline/somatic variant-calling Nextflow
    pipeline whose output conventions PipeGuard's schema mirrors
    ([nf-core-conventions.md](../data/nf-core-conventions.md)).
24. **Panel (targeted assay)** — sequencing only a curated set of disease-relevant
    genes, versus whole exome (WES) or whole genome (WGS).
25. **peddy** — pedigree/sex/relatedness QC tool (MIT license).
26. **Picard** — Broad Institute toolkit for alignment/coverage metrics (e.g.
    `PCT_TARGET_BASES_20X`, `FOLD_80_BASE_PENALTY`); MIT license.
27. **Preflight / QC / variant** — the three gates (see product section).
28. **Q30 (% ≥ Q30)** — fraction of base calls with Phred quality ≥30 (≤1-in-1000
    estimated error); expectations are platform × read-length vendor specs, not
    clinical gates.
29. **Sample sheet** — the file declaring which barcode/index maps to which sample;
    the provenance anchor demux checks against.
30. **samtools / flagstat** — SAM/BAM toolkit; `flagstat` reports mapping and pairing
    counts.
31. **Sanger sequencing** — orthogonal method used to fill callability gaps in
    reportable regions (the "surface-and-fill", not silent-fail, doctrine).
32. **Ti/Tv** — transition/transversion ratio; a callset-level sanity trend
    (~3.0 WES, ~2.0 WGS), never a per-variant gate.
33. **VCF** — Variant Call Format: per-sample list of differences from the reference
    with per-genotype fields (DP, GQ, AD).
34. **VerifyBamID2** — cross-sample contamination estimator emitting FREEMIX (MIT
    license; distinct from the GPLv3 original `statgen/verifyBamID`).
35. **WES / WGS** — whole-exome / whole-genome sequencing (contrasted with a targeted
    panel).

## Software & architecture

1. **Adapter** — a concrete implementation of a port (e.g. `SqliteRepository`
   implements the `Repository` port).
2. **AnalysisRun (`arun_`)** — one gate execution; the anchor every finding, card,
   and event references ([provenance.md](../data/provenance.md)).
3. **Content hash** — a sha256 over an entity's stored bytes, making immutable
   records (findings, cards, artifacts) tamper-evident and de-duplicable.
4. **Event ledger (EventLedger)** — the append-only, authoritative record of every
   gate step; in-memory plus optional JSONL (ADR-0002).
5. **Finding** — an immutable, content-hashed, cited observation emitted by a rule;
   carries a gate, category, evidence, and a suggested verdict.
6. **Origin label** — provenance tag on every artifact: `real-giab` / `synthetic` /
   `contrived` ([strategy.md](../data/strategy.md)).
7. **Port (repository port)** — a framework-agnostic interface the core depends on;
   `Repository` abstracts persistence so the core never touches a DB directly
   (ADR-0003).
8. **Projection / projector** — a rebuildable, disposable view derived from the
   event ledger; `project_events` maps events → DB rows, so the DB is a pure
   function of the log ([provenance.md](../data/provenance.md)).
9. **ProvenanceEvent (`evt_`)** — one append-only event (e.g. `finding.emitted`,
   `verdict.decided`) with actor, inputs/outputs, and typed payload.
10. **rebuild-db** — command that replays a JSONL ledger into a fresh relational
    projection, deterministically and idempotently.
11. **Runbook profile** — the operator-owned, per-assay × sample-type threshold
    configuration; no hardcoded universal thresholds (ADR-0005).
12. **Signature (IssueSignature, `sig_`)** — a rule-version-independent hash of an
    issue's semantics, so recurring issues are tracked across rule changes.
13. **Synthesizer** — the narration layer (`stub` or `claude`); writes prose but
    never sets a verdict (ADR-0001).
14. **Triage agent** — the advisory retrieval-grounded agent that suggests likely
    cause / next action; off the deterministic critical path (ADR-0009/0012).

## The product

1. **Decision card** — one per (sample × analysis-run): the verdict, headline,
   rationale, per-gate results, cited findings, and next steps
   ([schemas.md](../data/schemas.md)).
2. **The three gates** — **preflight** (intake: barcode/identity/sanity), **qc**
   (per-sample yield/Q30/coverage/contamination/swap), **variant** (per-variant
   confidence + annotation, Phase 2) (ADR-0013).
3. **Verdict** — one of **proceed / hold / rerun / escalate**; computed
   deterministically by rules (never by the LLM). RERUN is reserved for
   operational/file-system failures; a data-quality problem is a HOLD.
4. **Confidence** — a heuristic score, **omitted until grounded** (nullable); never a
   calibrated probability (CLAUDE.md guardrails, T-019).
5. **Surface and decide** — the verdict policy: the gate surfaces cited evidence and
   a recommendation; the human decides and acts (ADR-0013).
6. **TriageNote** — the advisory agent's output (likely cause, suggested action,
   citations); flagged advisory and never sets a verdict.

---

*Genomics numbers here are guideline examples treated as configurable defaults, not
clinical thresholds; tool licenses are summarized — see
[data/licensing.md](../data/licensing.md) for verification status.*
