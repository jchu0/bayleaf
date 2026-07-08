# QC Metrics — Grounded Reference (sources)

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-07 (MST) |
| **Audience** | bioinformatics / software |
| **Related** | [qc_metrics.md](qc_metrics.md) (the runbook we derive from this), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) |

## How to read this

Grounding research for the QC gate: clinical rare-disease germline DNA panel,
targeted Illumina short-read, high depth. Pipeline: fastp → FastQC/MultiQC →
BWA-MEM2 → samtools/Picard → mosdepth → DeepVariant/GATK/FreeBayes → bcftools →
gnomAD/ClinVar.

Every **field name** below is verified verbatim against the tool's primary docs
(high confidence — these are facts). Almost every **threshold** is a vendor spec,
a consortium example, or a lab rule-of-thumb — those belong in operator-owned
`runbook.py`, never hard-coded as facts. Per-threshold confidence is in
**§Confidence & caveats**. This is the sources reference; `qc_metrics.md` is the
decided runbook that cites it.

## Load-bearing traps (encode before anything else)

1. fastp `filtering_result.passed_filter_reads` is **not** Illumina %PF (chastity) — different metric, different layer.
2. fastp `q30_rate`, `gc_content`, `duplication.rate` are **fractions 0–1**; MultiQC `pct_*` are ×100. ("85" vs "0.85" is a silent gate bug.)
3. samtools `properly paired` (SAM flag 0x2) ≠ Picard `PCT_READS_ALIGNED_IN_PAIRS` (mate merely also aligned).
4. Picard `PCT_SELECTED_BASES` (on+near-bait) ≠ `ON_TARGET_BASES` (target-interval count) — two on-target definitions.
5. VCF `QUAL` is **caller-dependent** (DeepVariant ≠ GATK ≠ FreeBayes); a "QUAL≥30" gate doesn't transfer. GATK germline filters on `QD<2.0`, not raw QUAL.
6. `FOLD_90_BASE_PENALTY` does **not** exist in Picard (only `FOLD_80_BASE_PENALTY`); `PCT_TARGET_BASES_100X` is the highest depth-tier key HsMetrics emits.

## A. Read / sequencing QC — fastp / FastQC / MultiQC

| Metric | Tool.field (exact) | Threshold (clinical panel) | Panel-dep? | Source |
|---|---|---|---|---|
| Yield / read-pairs | fastp `summary.before_filtering.total_reads`/`.total_bases`; post `summary.after_filtering.total_reads`. **No `read_pairs` key** (pairs = reads/2 PE) | Size to coverage, not a fixed count (rule-of-thumb) | Y | [fastp JSON](http://opengene.org/fastp/fastp.json) |
| % passing filter (fastp's own) | fastp `filtering_result.passed_filter_reads` (+ `low_quality_reads`, `too_many_N_reads`, `too_short_reads`); MultiQC `pct_surviving_reads` | >90–95% survival (rule-of-thumb) | Partly | [MultiQC fastp](https://docs.seqera.io/multiqc/modules/fastp/) |
| Illumina %PF (chastity) — separate | RTA/InterOp/SAV run-lane metric; **not in fastp** | >80% (rule-of-thumb, loading-driven) | Partly | [Illumina chastity](https://support-docs.illumina.com/IN/NextSeq_550-500/Content/IN/NextSeq/ChastityFilter_fNS.htm) |
| Q30 (% bases ≥Q30) | fastp `summary.before_filtering.q30_rate` (**fraction**); MultiQC `after_filtering_q30_rate` | Vendor spec, read-length/platform-dependent: NovaSeq 6000 v1.5 **≥90% @2×50, ≥85% @2×150, ≥75% @2×250**; MiSeq v2 2×150 >80% (corrected — see qc_metrics-rare-disease.md) | N (platform) | [NovaSeq spec M-GL-00271](https://knowledge.illumina.com/instrumentation/novaseq-6000/instrumentation-novaseq-6000-reference_material-list/000002669) |
| Adapter / trim rate | fastp `adapter_cutting.adapter_trimmed_reads`/`.adapter_trimmed_bases`; MultiQC `pct_adapter` | **No authoritative cutoff** (weak) | Y | [fastp README](https://github.com/OpenGene/fastp) |
| GC deviation | fastp `summary.before_filtering.gc_content` (**fraction**); "deviation" is a FastQC module, not fastp | ~40–41% human; FastQC WARN >15% / FAIL >30% (heuristic; mis-fires on panels) | Y | [FastQC GC](https://www.bioinformatics.babraham.ac.uk/projects/fastqc/Help/3%20Analysis%20Modules/5%20Per%20Sequence%20GC%20Content.html) |
| Library duplication | fastp `duplication.rate` (**fraction**, k-mer est); MultiQC `pct_duplication`; FastQC dup module | ≤10% ideal (rule-of-thumb); FastQC WARN >20% / FAIL >50% | **Y — most panel-dependent**; amplicon/PCR 30–80%+ by design | [fastp JSON](http://opengene.org/fastp/fastp.json) |

*fastp k-mer dup ≠ Picard MarkDuplicates (post-align). Prefer the Picard rate for a clinical dup gate.*

## B. Demux / provenance — BCL Convert + sample sheet

`Demultiplex_Stats.csv` columns (exact): `Lane, SampleID, Index, # Reads, # Perfect Index Reads, # One Mismatch Index Reads, # Two Mismatch Index Reads, % Reads, % Perfect Index Reads, % One Mismatch Index Reads, % Two Mismatch Index Reads`.

| Metric | Tool.field (exact) | Threshold | Panel-dep? | Source |
|---|---|---|---|---|
| % reads identified / sample | `Demultiplex_Stats.csv` → `# Reads`, `% Reads` | Lab-set min reads/sample (rule-of-thumb) | Y | [BCL Convert demux stats](https://support-docs.illumina.com/APP/AppBCLConvert_v2_0/Content/SW/BCLConvert/DemuxStatsFile__swBCL_swBS_appBCL.htm) |
| Per-sample read balance | derive from `% Reads` vs lane mean (no dedicated field) | within ~2× of mean (weak) | Y | (derived) |
| Index match perfect/mismatch | `# Perfect/One/Two Mismatch Index Reads`; sheet `BarcodeMismatchesIndex1/2` (default 1) | high perfect fraction (rule-of-thumb) | Y | [BCL Convert sheets](https://support-docs.illumina.com/SW/BCL_Convert/Content/SW/BCLConvert/SampleSheets_swBCL.htm) |
| Duplicate / missing index (provenance) | sheet `[BCLConvert_Data]`: `Sample_ID, index, index2`; barcode-collision detection | **Binary integrity gate** — zero collisions/missing; unique Sample_ID | N (hard requirement) | [BCL Convert metrics](https://support-docs.illumina.com/SW/BCL_Convert/Content/SW/BCLConvert/BCLConvert_MetricsOutput.htm) |
| Index hopping | `Index_Hopping_Counts.csv` (UDI only) | **0.1–2%** typical (only Illumina-published number) | Partly | [Illumina index hopping](https://www.illumina.com/techniques/sequencing/ngs-library-prep/multiplexing/index-hopping.html) |
| Undetermined % | "Undetermined" row `% Reads`; diagnose via `Top_Unknown_Barcodes.csv` | **No authoritative cutoff**; lab ~<5–10% (weak) | Y | [BCL Convert demux stats](https://support-docs.illumina.com/APP/AppBCLConvert_v2_0/Content/SW/BCLConvert/DemuxStatsFile__swBCL_swBS_appBCL.htm) |

*Casing trap:* input `Sample_ID`/`index`/`index2`; output `SampleID`/`Index`.

## C. Alignment — samtools flagstat / Picard

| Metric | Tool.field (exact) | Threshold | Panel-dep? | Source |
|---|---|---|---|---|
| % mapped | flagstat `mapped`(÷total); Picard `PCT_PF_READS_ALIGNED` | ≥95% (rule-of-thumb) | N | [samtools flagstat](http://www.htslib.org/doc/samtools-flagstat.html) |
| % properly paired | flagstat `properly paired` (0x2) ≠ Picard `PCT_READS_ALIGNED_IN_PAIRS` | **No authoritative cutoff**; ≥90% folklore (weak) | N/mild | [samtools flagstat](http://www.htslib.org/doc/samtools-flagstat.html) |
| Duplication | Picard MarkDuplicates `PERCENT_DUPLICATION` | <20% clinical exome; ≤10% common (rule-of-thumb) | **Y** (depth, PCR) | [Picard defs](http://broadinstitute.github.io/picard/picard-metric-definitions.html) |
| Median insert | Picard InsertSize `MEDIAN_INSERT_SIZE` | ~200–250 bp (distribution check) | Y | [Picard defs](http://broadinstitute.github.io/picard/picard-metric-definitions.html) |
| On-target rate | Picard HsMetrics `PCT_SELECTED_BASES`; `PCT_OFF_BAIT` | >80% hyb-capture, >90% amplicon (rule-of-thumb; kits 50–90%) | **Y** | [IDT coverage metrics](https://sfvideo.blob.core.windows.net/sitefinity/docs/default-source/white-paper/idt_targeted-ngs-coverage-metrics-that-matter_white-paper.pdf?sfvrsn=fcae707_9) |

## D. Coverage — mosdepth / Picard HsMetrics (the key panel category)

mosdepth: `{prefix}.mosdepth.summary.txt` (`chrom length bases mean min max`; `total_region` row = panel-wide mean), `.regions.bed.gz` (per-region, needs `--by`), `.thresholds.bed.gz` (**base counts ≥ threshold, not %** — divide by region length; needs `--thresholds`).

| Metric | Tool.field (exact) | Threshold (clinical panel) | Panel-dep? | Source |
|---|---|---|---|---|
| Mean/median target coverage | Picard `MEAN_TARGET_COVERAGE`/`MEDIAN_TARGET_COVERAGE`; mosdepth `mean` | Panel design goal ≥100–500× (rule-of-thumb). Analogs: exome 100× mean, WGS 30× mean | **Y** | [ACMG Rehm 2013](https://pmc.ncbi.nlm.nih.gov/articles/PMC4098820/) |
| % targets ≥20× | Picard `PCT_TARGET_BASES_20X`; mosdepth `--thresholds 20` | **20× = common het-calling floor** (ACMG "10–20×"); breadth **≥95–100%** (ACGS example: "99% of target ≥20×") | **Y** | [ACGS Targeted NGS 2015](https://www.acgs.uk.com/media/10789/bpg_for_targeted_next_generation_sequencing_-_approved_dec_2015.pdf) |
| % targets ≥100× | Picard `PCT_TARGET_BASES_100X` (highest key; tiers 1/2/10/20/30/40/50/100X) | No consortium number (weak) | Y | [Picard defs](http://broadinstitute.github.io/picard/picard-metric-definitions.html) |
| Zero-coverage targets | Picard `ZERO_CVG_TARGETS_PCT`; mosdepth 0× intervals | **Ideal 0%**; any gap in a reportable region must be flagged | Partly N | [ACMG Rehm 2013](https://pmc.ncbi.nlm.nih.gov/articles/PMC4098820/) |
| Uniformity (fold-80) | Picard `FOLD_80_BASE_PENALTY` (**FOLD_90 doesn't exist**) | ideal 1.0; <1.5–2 "good" (rule-of-thumb) | N mostly | [Picard defs](http://broadinstitute.github.io/picard/picard-metric-definitions.html) |

## E. Contamination / identity

| Metric | Tool.field (exact) | Threshold | Panel-dep? | Source |
|---|---|---|---|---|
| Cross-sample contamination | VerifyBamID2 `FREEMIX` in `{prefix}.selfSM` | Flag **≥2–3%** (basis: 1000G exclusion at α̂>2%); GATK sets no fixed number | **Y** (noisier on small panels) | [VerifyBamID2](https://github.com/Griffan/VerifyBamID) |
| Sex-check concordance | peddy `sex_check.csv` (`predicted_sex`, `error`) or plink `--check-sex` `.sexcheck` (`F`, `STATUS`) | predicted = reported (tool defaults: F<0.2 female / >0.8 male) | Y for reliability | [peddy](https://peddy.readthedocs.io/en/latest/output.html) · [plink](https://www.cog-genomics.org/plink/1.9/basic_stats) |
| Fingerprint / swap | Picard CrosscheckFingerprints `LOD_SCORE`, `RESULT` (EXPECTED/UNEXPECTED_MATCH/MISMATCH) | default `LOD_THRESHOLD=0` (sign decides); ±5 buffer rule-of-thumb | **Y** (|LOD| scales with SNPs) | [CrosscheckFingerprints](https://gatk.broadinstitute.org/hc/en-us/articles/360037594711-CrosscheckFingerprints-Picard) |

*Coverage-based sex check (chrX/chrY ratio) has no standardized field/threshold — NOT FOUND.*

## F. Variant-level — VCF / GATK / bcftools / gnomAD / ClinVar

VCF fields per **VCF v4.3 spec**. *`AD` is reserved as of 4.3 (Number=R); in 4.2 it's a GATK convention.*

| Metric | Tool.field (exact) | Threshold | Panel-dep? | Source |
|---|---|---|---|---|
| Per-variant depth | `FORMAT/DP` (per-sample); `INFO/DP` (combined) | ACMG 10–20× min; rare-disease trios used DP≥10 (rule-of-thumb) | Y | [VCF v4.3](https://samtools.github.io/hts-specs/VCFv4.3.pdf) |
| Genotype quality | `FORMAT/GQ` (phred, p(call wrong)) | **GQ≥20** (99%); some labs ≥30 | N | [Pedersen 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8282602/) |
| Variant QUAL | `QUAL` (phred, caller-dependent) | QUAL≥30 generic rule-of-thumb; **GATK uses `QD<2.0`** | caller-dep | [GATK hard filters](https://pmbio.org/module-04-germline/0004/02/02/Germline_SnvIndel_FilteringAnnotationReview/) |
| Allele balance (het) | `FORMAT/AD` (Number=R); AB=ALT/(REF+ALT) | het ≈0.5; band 0.2–0.8 (Pedersen); 0.3–0.7 lab convention | N | [Muyas 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6587442/) |
| Ti/Tv | Picard `DBSNP_TITV`/`NOVEL_TITV`; bcftools stats `ts/tv` | WGS ≈2.0–2.1; **WES/coding ≈2.8–3.3** (upper is folklore) | **Y** (noisy on small panels — trend, not gate) | [Picard defs](http://broadinstitute.github.io/picard/picard-metric-definitions.html) |
| Variant count | Picard `TOTAL_SNPS`/`TOTAL_INDELS`; bcftools `SN` | **No universal count** — per-assay baseline ± range (weak) | **Y** | [bcftools stats](https://samtools.github.io/bcftools/bcftools.html) |
| gnomAD pop AF | `INFO/AF`; gnomAD `popmax`(v2)→`grpmax`(v4); `faf95`/`faf99` | rare-disease AF<0.001 dominant, <0.01 recessive; prefer filtering-AF | N field / Y cutoff | [gnomAD v2.1](https://gnomad.broadinstitute.org/news/2018-10-gnomad-v2-1/) |
| ClinVar significance | `INFO/CLNSIG` + `INFO/CLNREVSTAT` (0–4 stars) | ACMG/AMP 5-tier (P/LP/VUS/LB/B + Conflicting) | N (vocabulary) | [ClinVar clinsig](https://www.ncbi.nlm.nih.gov/clinvar/docs/clinsig/) |

*GATK germline hard-filter set (SNPs): `QD<2.0, FS>60, MQ<40, MQRankSum<−12.5, ReadPosRankSum<−8.0, SOR>3.0`; indels `QD<2.0, FS>200, ReadPosRankSum<−20, SOR>10`. GATK-specific — DeepVariant/FreeBayes don't emit these.*

## Consortium hard-numbers (mostly WGS/exome — NOT panel numbers)

US/EU standards deliberately mandate **no universal panel coverage number**; they give examples and defer to per-assay validation. Firmest numbers are operational (Genomics England) and WGS-consortium (Marshall/MGI).

| Metric | Number | Document (status) |
|---|---|---|
| WGS mean coverage | ≥30–40× | Marshall 2020 / MGI (consortium) |
| WGS % bases ≥20× | ≥90% | Marshall 2020 / MGI |
| Contamination | <1% blood / ≤2% (MGI); **>3% = fail** (GE) | Marshall 2020; Genomics England |
| Panel horizontal coverage | "99% of target at ≥20×" (explicit *e.g.*) | ACGS 2015 (example) |
| Exome coverage | 100× mean, 90–95% ≥10×, 70× trio (examples) | ACMG Rehm 2013 |
| Validation accuracy | SNV error ≤2% @95%CI via ≥150 variants; het/hom ≤5% via ≥60 | ACGS 2015 (firm) |

## Confidence & caveats

**Well-established (verified verbatim):** all field names; Illumina Q30 platform spec; FastQC warn/fail constants (as heuristics that mis-fire on panels); index hopping 0.1–2%; ACMG/Marshall/GE/ACGS hard numbers; GATK germline hard-filter set; GQ≥20 / het≈0.5.

**Rule-of-thumb (runbook params, not facts):** mapping ≥95%, duplication ceilings, on-target %, coverage design goals, %≥100×, fold-80 <2, FREEMIX 2–3%, fingerprint ±5 LOD, QUAL≥30, GQ≥30, allele-balance band, per-sample balance, undetermined %.

**Panel-dependent — flag strongly:** all coverage depth/breadth goals, duplication, on-target, insert size, Ti/Tv (small-panel noise), gnomAD AF cutoffs, contamination sensitivity.

**Could NOT ground (do not invent):** numeric cutoff for % properly paired; undetermined-% limit; adapter-rate and panel duplication hard cutoffs; a panel-specific mean-coverage number from any consortium; a Ti/Tv acceptance number; coverage-based sex-check as a standardized metric. AMP/CAP (Roy 2018) is paywalled and prescribes no universal number — don't attribute "≥20×" to it (that floor is ACMG/community).
