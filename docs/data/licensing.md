# Licensing — the tool & data stack

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | software / all |
| **Related** | [requirements/constraints.md](../requirements/constraints.md), [qc_metrics-rare-disease.md](qc_metrics-rare-disease.md), [strategy.md](strategy.md), [ADR-0004](../adr/ADR-0004-vcf-first-giab-substrate.md) |

## Overview

Per-component licensing for the genomics tools and reference data PipeGuard sits on top
of, and why the design keeps **PipeGuard's own code MIT-licensable**. The load-bearing
decision is **external-process invocation**: PipeGuard reads tool *outputs* and, when it
runs a tool, does so as an arm's-length subprocess — it does not link or vendor tool
code, so a tool's copyleft does not reach PipeGuard's source
([constraints.md](../requirements/constraints.md) REQ-C-020/021).

> **Verification status matters.** Only the four tools in
> [qc_metrics-rare-disease.md](qc_metrics-rare-disease.md) §4 are **verified verbatim**
> from their LICENSE files in-repo. Everything else below is **reported** and must be
> confirmed against the upstream LICENSE before any redistribution/distribution claim
> ([constraints.md](../requirements/constraints.md) REQ-C-023). Reported ≠ verified.

## The licensing model

1. **PipeGuard's own code → MIT** (intended). It orchestrates and reads outputs.
2. **CLI / subprocess use of a tool = mere aggregation** — even a GPLv3 tool (e.g.
   PLINK) is fine invoked over the shell (FSF
   [MereAggregation](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation)).
3. **The one trap: bundling a GPL binary.** Baking a GPLv3 tool's binary into a
   distributed image triggers GPLv3 obligations *on that binary*. Prefer installing from
   upstream and invoking what is on `PATH`; keep the genomics toolchain
   (bioconda/containers) separate from the app's `uv` toolchain.
4. **No linking, no vendoring of tool source** into `src/pipeguard/`.

## Tools — verified verbatim in-repo

Source: [qc_metrics-rare-disease.md](qc_metrics-rare-disease.md) §4 (read from LICENSE
files).

| Tool | License | External-process OK for MIT product? | Caveat |
|---|---|---|---|
| **VerifyBamID2** (Griffan) | **MIT** | Yes | Do **not** confuse with `statgen/verifyBamID` (original) = **GPLv3** |
| **peddy** (brentp) | **MIT** | Yes | Retain notice if redistributing |
| **Picard** (broadinstitute) | **MIT** | Yes | Retain notice if redistributing the JAR |
| **PLINK 1.9 / 2.0** (chrchang) | **GPL-3.0** | Yes, with caveat | CLI = mere aggregation; **bundling the binary triggers GPLv3 on it** |

**Bottom line (verified subset):** all compliant for external-process invocation; the
only obligation arises if the PLINK binary is redistributed.

## Tools — reported, confirm upstream before relying on them

**⚠ Unverified.** Licenses below are as commonly reported; treat as *to-confirm*, not as
distribution-ready claims. Confirm each against its upstream LICENSE file and record the
result here (move the row up to "verified" when done).

| Tool | Reported license | Notes / why used |
|---|---|---|
| fastp | MIT *(reported)* | read trim/QC JSON (Q30, dup) |
| bwa-mem2 | MIT *(reported)* | short-read alignment — invoked only by [`scripts/run_giab_pipeline.py`](../../scripts/run_giab_pipeline.py) (the real-GIAB fastq→variants E2E driver, [strategy.md](strategy.md)), never a `uv` app dependency |
| mosdepth | MIT *(reported)* | coverage depth + breadth |
| samtools / bcftools / htslib | MIT/Expat *(reported)* | BAM/VCF stats, alignment dup-marking (`markdup`) + variant calling (`mpileup`\|`call`\|`norm`) in the same driver |
| MultiQC | **GPL-3.0** *(reported)* | QC aggregator — **same binary-bundling caveat as PLINK**; CLI use is fine |
| GATK4 | Apache-2.0 *(reported; older GATK had restrictive terms)* | variant calling |
| DeepVariant | BSD-3-Clause *(reported)* | variant calling |
| FreeBayes | MIT *(reported)* | variant calling |
| NGSCheckMate | **confirm upstream** | sample-swap/identity — license not yet checked |
| Nextflow | Apache-2.0 *(reported)* | pipeline runtime (compute portability, ADR-0003) |
| nf-core/sarek | MIT *(reported)* | pipeline whose conventions the schema mirrors |

## Vendor / proprietary — not open source

| Tool | License | Implication |
|---|---|---|
| **BCL Convert / bcl2fastq** (Illumina) | **Proprietary (Illumina EULA)** | Demux software is vendor-licensed; **not redistributable**. PipeGuard only reads its *outputs* (demux stats / FASTQ), never ships it. |

## Reference data sources

Open sources only; **no licensed data** (e.g. HGMD) — [constraints.md](../requirements/constraints.md)
REQ-C-022.

| Source | Reported terms | Use |
|---|---|---|
| **GIAB / HG002** (NIST) | Open / public *(reported)* | truth VCF + high-confidence BED; eventual real-data eval |
| **gnomAD** | Open / permissive *(reported — confirm current terms)* | population-frequency annotation |
| **ClinVar** (NCBI/NLM) | Public domain *(reported — US-gov data)* | clinical-significance annotation only |

> **Data guardrail.** gnomAD/ClinVar are used to *annotate and surface*, never to assert
> pathogenicity ([domain-primer.md](../reference/domain-primer.md) §4). No PHI or licensed
> clinical database is used.

## Open items (LICENSE-TODO)

1. **TODO** — verify each *reported* tool license verbatim from its upstream LICENSE and
   promote the row; resolve **NGSCheckMate** specifically.
2. **TODO** — confirm current **gnomAD** data terms and **GIAB** redistribution terms
   before publishing any bundled dataset.
3. **Decision** — keep genomics tools out of any distributed image (install from
   upstream, invoke on `PATH`) so no copyleft binary is redistributed.

---

*Marker legend:* **Fact** (verified verbatim in-repo — the four §4 tools) ·
**Assumption** (rows marked *reported*) · **Decision** · **TODO**. A *reported* license
is not a cleared license; confirm before any distribution claim.
