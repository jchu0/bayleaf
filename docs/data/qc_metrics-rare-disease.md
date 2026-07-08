# QC Gold Standards — Rare-Disease Germline (lit review)

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | bioinformatics / software |
| **Related** | [qc_metrics.md](qc_metrics.md), [qc_metrics-sources.md](qc_metrics-sources.md), [licensing.md](licensing.md) (consumes the §4 verified-license table), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md) |

## How to read this

Literature review of modern clinical QC gold standards for **rare-disease germline
sequencing**, focused on the depth/coverage question and how rare disease differs
from cancer and pathogen surveillance. Feeds `qc_metrics.md`. Every number carries
a primary source + a label: **[HARD]** mandated/operational gate · **[EXAMPLE]**
worked example that became a de-facto benchmark · **[DEFERS]** source defers to
per-assay validation · **[ROT]** tool default / rule-of-thumb · **[SUMMARY]**
confirmable only from abstract/summary · **[NOT FOUND]** absent from the source.

## Headline: where rare disease differs, and the depth question

**Most important finding:** no major clinical guideline (ACMG 2013/2021, ACGS 2015,
EuroGentest 2016, CAP/AMP) sets a *universal hard depth number* — they **defer the
minimum to per-assay validation** and give worked examples. A gate that hard-codes
"fail if < 20×" asserts something *stronger* than the guidelines. The
guideline-faithful model: each assay has a **validated, stated** minimum; the gate
checks the run against *that* value, and below-threshold reportable regions trigger
**HOLD + orthogonal/Sanger fill-in**, not silent fail.

**"Does rare disease need high depth like cancer?"** → Confirmed in *magnitude* for
panels, refuted in *rationale*, and refuted for exome/genome:

| | Rare-disease germline | Somatic / cancer | Pathogen / viral |
|---|---|---|---|
| **Typical depth** | WGS ~30× · WES ~100× · panel ~100–500× | tumor panel ~500–1000× · **ctDNA ~5,000–30,000×** | per-base **≥10–20×** consensus floor |
| **Why** | constitutional variants (het ≈50% VAF): ~15–20× local depth already gives >99% het sensitivity. Panels go deep for **breadth/uniformity + CNV/mosaic**, not low-VAF | detect **low-VAF** somatic (down to ~0.1% ctDNA). **Depth ∝ 1/VAF** | haploid **consensus** of the dominant sequence |
| **Distinguishing QC axis** | **breadth / callability of reportable regions** + genotype confidence (GQ, AB ≈0.5) + **family/identity** | LOD VAF, tumor purity, UMI dedup | genome % ≥N×, consensus completeness |

So a rare-disease panel's depth *number* looks cancer-like (~500×), but the *reason*
is breadth-insurance, not VAF sensitivity; WES/WGS germline is 15–1000× shallower
than cancer. The one genuine cancer-like exception is **mosaicism** detection
(low-VAF → higher depth), which is assay-specific [DEFERS].

## 1. Depth & coverage by modality

**Guidelines give examples, not universal numbers:**

| Metric | Value | Modality | Source (label) |
|---|---|---|---|
| Universal minimum depth | **NONE — set & validated per assay** | all | ACMG 2013/2021; ACGS 2015; EuroGentest 2016; CAP/AMP **[DEFERS]** |
| Per-base min, panel | **10–20×** | panel | ACMG 2013 **[EXAMPLE]** |
| Mean depth, exome proband | **100×** | WES | ACMG 2013 **[EXAMPLE]** |
| Mean depth, exome trio | **70×** | WES | ACMG 2013 **[EXAMPLE]** |
| Breadth, exome | **90–95% of target ≥10×** | WES | ACMG 2013 **[EXAMPLE]** |
| Breadth, panel | **99% of target ≥20×** | panel | ACGS 2015 **[EXAMPLE]** ("e.g.") |
| Mean depth, genome | **30×** | WGS | ACMG 2013 **[EXAMPLE]** |

Primary sources (verified verbatim from full text): **ACMG 2013** (Rehm et al.,
*Genet Med* 15:733, DOI 10.1038/gim.2013.92, [PMC4098820](https://pmc.ncbi.nlm.nih.gov/articles/PMC4098820/))
— §E.2.1 examples above; governing deferral: *"it is not possible to recommend a
specific minimum threshold for coverage … laboratories will need to choose …
thresholds in accordance with … analytical validation."* **ACGS 2015** targeted-NGS
BPG (current; [PDF](https://www.acgs.uk.com/media/10789/bpg_for_targeted_next_generation_sequencing_-_approved_dec_2015.pdf))
— *"minimum read depth should be evidence based and … established during …
validation"* [DEFERS]; *"e.g. 99% of the target … at a minimum read depth of 20x"*
[EXAMPLE]. **EuroGentest/ESHG 2016** (Matthijs et al., *EJHG* 24:2, [PMC4795226](https://pmc.ncbi.nlm.nih.gov/articles/PMC4795226/))
— no universal number; **Type A/B/C callability** system (Type A: *">99% reliable
calls … fills all gaps with Sanger"*). **ACMG 2021** paywalled [SUMMARY] — same
example-based framework; don't cite specifics.
*Integrity flag: an auto-extracted Jennings-2017 depth quote was fabricated —
discarded; CAP/AMP (Jennings 2017, Aziz 2015) contain no depth number [DEFERS].*

**Whole genome — the firmest operational numbers:**

| Metric | Value | Source (label) |
|---|---|---|
| **Breadth (headline gate)** | **≥95% of genome at ≥15×**, MQ>10, dedup | Genomics England **[HARD, programme]** |
| Yield | **≥85 Gb**; quality **≥Q30** | Genomics England **[HARD]** |
| Mean depth (100kGP pilot) | **32× (range 27–54)** | NEJM 100kGP **[SUMMARY]** |
| Mean-coverage cutoff (member labs) | **30× or 40×** ("universal cutoffs could not be established") | Marshall/MGI 2020 **[EXAMPLE/DEFERS]** |
| % Callability | **>95%** autosomal | Marshall/MGI 2020 |
| Het sensitivity | **>99.5%** at 40× mean | Sun et al. 2021 **[empirical]** |

GE 100kGP: [AggV2 sample QC](https://re-docs.genomicsengland.co.uk/sample_qc/)
— *"at least 95% of the genome at 15X … (mapping quality >10)"*, *"at least 85Gb"*,
*"sequencing quality of at least 30"*. **Marshall 2020** (*npj Genom Med* 5:47,
[PMC7585436](https://pmc.ncbi.nlm.nih.gov/articles/PMC7585436/)): *"30× or 40× mean
coverage as a cutoff"*, *"universal cutoffs could not be established."* **Sun 2021**
(*BMC Med Genomics* 14:102) is the mechanistic link: ~30–40× mean is chosen so ≥95%
of the genome clears the ~15–20× local floor for reliable het calling — **not** for
VAF. **Souche 2022** European WGS consensus: no numeric depth; coding quality *"at
least similar to … WES."*

## 2. Other rare-disease QC thresholds

**Contamination** (germline norms ~1–3%):

| Metric | Threshold | Source (label) |
|---|---|---|
| VerifyBamID contamination, WGS | **>3% → fail** | Genomics England **[HARD]** |
| Contamination-exclusion (community) | **1–3%** | Zhang 2020 VerifyBamID2 **[ROT]** |

GE: *"Samples with >3% contamination are considered as failing"* (+ AggV2 *"freemix
< 0.03"*). VerifyBamID2 (Zhang 2020, *Genome Res* 30:185, [PMC7050530](https://pmc.ncbi.nlm.nih.gov/articles/PMC7050530/)):
*"1%–3% used by many studies."* → defensible **hard-fail 3%**, borderline ~1.5–3%.

**Sample identity / sex / relatedness** (elevated in rare disease — trio/family):

| Metric | Threshold | Source (label) |
|---|---|---|
| SNP-array/identity concordance | **>90%** | Genomics England **[HARD]** |
| Sex prediction (X het/hom) | tool default (peddy 0.6) | peddy **[ROT]** |
| Parent–child relatedness | **IBS0 < 0.012** | Pedersen & Quinlan 2017 **[ROT]** |
| Sex/pedigree **discordance** | any mismatch → flag | peddy **[HARD, categorical]** |

peddy (Pedersen & Quinlan 2017, *AJHG* 100:406, [PMC5339084](https://pmc.ncbi.nlm.nih.gov/articles/PMC5339084/));
numeric X-het cutoff **[NOT FOUND]** in the paper (0.6 is a code default) — the
actionable event is categorical **discordance**.

**Variant-level filters** (rare-disease anchor: Pedersen et al. 2021, *npj Genom
Med* 6:60, [PMC8282602](https://pmc.ncbi.nlm.nih.gov/articles/PMC8282602/) — GQ≥20,
0.2≤AB≤0.8, DP≥10 → ~10 candidates/exome, 18/genome):

| Metric | Threshold | Source (label) |
|---|---|---|
| Genotype quality | **GQ ≥ 20** | Pedersen 2021 **[ROT]** |
| Depth per genotype (WGS) | **DP ≥ 10** | Pedersen 2021 **[ROT]** |
| Allele balance, het | **0.2 ≤ AB ≤ 0.8** (≈0.5) | Pedersen 2021 **[ROT]** |
| GATK SNP hard filters | `QD<2.0, FS>60, MQ<40, MQRankSum<−12.5, ReadPosRankSum<−8.0, SOR>3.0` | GATK **[ROT]+[DEFERS]** |
| GATK INDEL hard filters | `QD<2.0, FS>200, ReadPosRankSum<−20, SOR>10` | GATK **[ROT]+[DEFERS]** |

**Ti/Tv** (callset sanity, never a per-variant gate): WES/coding **~3.0** (3.0–3.3),
WGS **~2.0** (2.0–2.1), *">4 too high"* — Wang & Guo 2015 (*Bioinformatics* 31:318,
[PMC4308666](https://pmc.ncbi.nlm.nih.gov/articles/PMC4308666/)). Noisy on small
panels → trend, not gate. GE: **Het/Hom SNV ratio < 3** [HARD].

**Callability / gap handling — the rare-disease hallmark:**

| Requirement | Source (label) |
|---|---|
| WGS ≥95% of genome at ≥15× | Genomics England **[HARD]** |
| Type A: >99% reliable calls, **all gaps Sanger-filled** | EuroGentest 2016 **[HARD per tier]** |
| Low-coverage reportable regions → describe / recommend Sanger | ACGS 2015; ACMG 2013 **[RECOMMENDATION]** |
| *"actual coverage achieved … must be provided in each patient report"* | ACMG 2013 §G.4 **[HARD reporting]** |
| Confident/callable-region framework | GA4GH/GIAB — Krusche 2019 (*Nat Biotechnol* 37:555) |

Cancer/pathogen have no equivalent "complete reportable range + orthogonal fill-in"
doctrine — this is distinctly rare-disease.

## 3. Preflight / intake run-QC signals

Illumina publishes **RUO performance specs (PhiX-based)**, not clinical gates;
standards defer run-acceptance to lab validation (Gargis 2012 Nex-StoCT). Encode
**metric + vendor expected value** as reference; keep accept/HOLD/reject as config.

| Metric | Expected value | Type | Source |
|---|---|---|---|
| **%≥Q30, NovaSeq 6000 v1.5** | 2×50 **≥90%**, 2×100/150 **≥85%**, 2×250 **≥75%** | **[SPEC]** | NovaSeq spec M-GL-00271 |
| **%≥Q30, MiSeq** | v2 2×150 **>80%**, 2×250 **>75%**; v3 2×75 **>85%** | **[SPEC]** | MiSeq M-GL-00006 |
| **% PhiX Aligned > 90%** | **→ total clustering failure** (genuine "didn't sequence it" reject) | **[HARD-ish]** | Illumina KB 000009236 |
| Error rate (PhiX) | ~0.1–0.5% good; *"below 1%"* | **[ROT]** | needs PhiX spike |
| %PF (patterned flow cells) | lower by design (~77% normal) → monitor %occupancy + %PF | **[DEFERS]** | Illumina KB 000001511 |
| Yield (Gb) | compare to spec sheet | **[SPEC/ROT]** | vendor |

## 4. Tool licenses (verified verbatim from LICENSE files)

| Tool | License | Invoke as external process (MIT/BSD product)? | Caveat |
|---|---|---|---|
| **VerifyBamID2** (Griffan) | **MIT** | **Yes** | Do **not** confuse with `statgen/verifyBamID` (original) = **GPLv3** |
| **peddy** (brentp) | **MIT** | **Yes** | Retain notice if redistributing |
| **PLINK 1.9 / 2.0** (chrchang) | **GPL-3.0** | **Yes, with caveat** | CLI = mere aggregation, fine; **bundling the binary triggers GPLv3 on that binary** |
| **Picard** (broadinstitute) | **MIT** | **Yes** | Retain notice if redistributing the JAR |

**Bottom line:** all compliant for external-process invocation. GPLv3 PLINK is fine
via CLI (arm's-length subprocess = not a derivative work; FSF
[MereAggregation](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation)); the
only obligation arises **if you redistribute the PLINK binary** (e.g. baked into a
Docker image). Cleanest: install `plink` from upstream, invoke what's on `PATH`.
Your code stays MIT.

## 5. Confidence & runbook implications

**Verified verbatim (highest):** ACMG 2013 examples + deferral; ACGS 2015 example +
deferral; EuroGentest Type A/B/C; GE AggV2 gates; Pedersen 2021 filters; Wang/Guo
Ti/Tv; GATK filters; all tool licenses; NovaSeq/MiSeq Q30 spec sheets.
**[SUMMARY] (re-verify before shipping as hard claims):** ACMG 2021 specifics,
CAP/AMP (paywalled), NEJM 100kGP depth, all somatic/ctDNA depths, GATK's own Ti/Tv.
**[NOT FOUND]:** a universal panel mean-depth number; a numeric peddy X-het cutoff
in-paper; a cited clinical bacterial-isolate depth; a vendor numeric %PF/error-rate
acceptance cutoff.

**What differs for rare disease:** (1) depth is **breadth-driven, not VAF-driven**;
(2) **callability + orthogonal fill-in is a first-class gate** (HOLD-with-remediation,
not silent fail) — no cancer/pathogen equivalent; (3) **family/identity QC elevated**;
(4) germline-only sanity metrics (AB≈0.5, Ti/Tv, Het/Hom<3); (5) **everything defers
to per-assay validation**.

**Direct runbook implications (actionable for `runbook.py` / `qc_metrics.md`):**
1. **Biggest gap: gate on _breadth_, not just `mean_coverage`.** Add `% target ≥20×`
   (panel/WES) or `% genome ≥15×` (WGS) + a per-base callable floor with gap → HOLD/Sanger.
2. **`mean_coverage` gate 30/hard-fail 15 is the _WGS_ number.** For a panel, 30× is a
   *failing* panel (target 100–500×). Set depth **per-modality**.
3. **`q30` gate must be read-length/platform-aware.** 85% ≈ NovaSeq 2×150 floor, but
   MiSeq v2 2×150 spec is only >80% → an 85% gate false-fails normal MiSeq runs.
4. **Add `% PhiX aligned > 90%` as a preflight hard-reject** (clustering failure).
5. Model thresholds as **per-assay-validated** (guideline examples = configurable
   defaults + citations), not global constants.
