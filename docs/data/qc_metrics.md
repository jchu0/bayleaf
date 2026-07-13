# QC Metrics — Runbook

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-12 (MST) — gap-analysis WS-01 (`QC-MISSING`/`QC-EXPECTED-<key>` fail-closed rules, `CheckCoverage` honesty), WS-05 (`RunbookSet` per-sample resolution), WS-06 Gap 2 (Ts/Tv `target_band` gate), WS-02/WS-04 (FREEMIX + SNP-F1 gated, parser-wired not pipeline-produced; corrected the `CheckCoverage` contamination-flip claim against a direct code check) |
| **Audience** | bioinformatics / software |
| **Related** | [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) (compose ≠ execute), [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) (route-to-human, D2), [ADR-0004](../adr/ADR-0004-vcf-first-giab-substrate.md) (no invented pathogenicity), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md) (RBAC review queue), [qc_metrics-sources.md](qc_metrics-sources.md) (field names), [qc_metrics-rare-disease.md](qc_metrics-rare-disease.md) (cited thresholds), [metric_registry.md](metric_registry.md) (unit normalization + wiring status), [schemas.md](schemas.md) (§6 units contract, `VariantCall`, `SampleMetrics`/`RawObservation`), [audit/gap_analysis/README.md](../../audit/gap_analysis/README.md) (the workstream tracker), [audit/gap_analysis/ws-02-identity-provenance.md](../../audit/gap_analysis/ws-02-identity-provenance.md), [audit/gap_analysis/ws-04-giab-concordance.md](../../audit/gap_analysis/ws-04-giab-concordance.md), [journal 2026-07-10](../journal/2026-07-10-provenance-qc-builder-auth.md), [journal 2026-07-10 (wave 6)](../journal/2026-07-10-wave6-route-to-human-deid.md), [journal 2026-07-11](../journal/2026-07-11-d2-d3-share-egress.md), [journal 2026-07-12](../journal/2026-07-12-gap-analysis-remediation-verification.md) |

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
5. **Normalize units** — fastp fields are fractions (0–1); MultiQC are percentages. This is
   now handled by the [metric registry](metric_registry.md): every metric crosses the gate as
   its canonical `normalized_value`, and thresholds are stored + compared in that same unit
   ([schemas.md](schemas.md) §6 units contract) — a percent-for-fraction mix-up can't silently
   move a gate.

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
| Ti/Tv (callset sanity) | Picard / bcftools | ~3.0 WES, ~2.0 WGS — trend, not per-variant gate | HOLD (advisory); **genuinely gated** as of 2026-07-12 (WS-06 Gap 2) via a `target_band` threshold — see below |
| Het/Hom SNV ratio | bcftools | < 3 (GE) | HOLD |
| Flagged variant: gnomAD AF + ClinVar | `INFO/AF`, `CLNSIG` | rare-disease AF cutoffs; ClinVar 5-tier | ESCALATE / HOLD |

The ClinVar half of that last row now has a concrete, **off-by-default** implementation — the
**route-to-human policy (VAR-RTH-001)** below. It routes to a human (ESCALATE) rather than gating
on AF; the gnomAD AF cutoff itself is still design-only (no code path reads `INFO/AF`).

## Verdict policy (ADR-0013)

1. Borderline (near the configured default) → **HOLD**.
2. Provenance / identity (barcode, contamination, sex, swap) → **ESCALATE**.
3. Operational / file-system failures (network, missing files, distributed-FS race
   conditions, step crash) → **RERUN**.
4. Clean → **PROCEED**. Worst verdict wins.
5. Depth vs breadth are surfaced as distinct signals. Every decision + resolution is
   recorded to the experience corpora (ADR-0009).

## Pipeline / operational rules (PIPE-001, EXEC-001)

Two preflight-gate rules realize the operational-failure branch of the verdict policy
(item 3 → **RERUN**) from what the run *itself produced*, not from re-running anything:

1. **PIPE-001** — a free-text failure marker for the sample in `pipeline.log`
   (matched against `runbook.log_failure_markers`).
2. **EXEC-001** — its **structured sibling**: it reads the Nextflow/nf-core execution
   trace (`trace.txt`, a task table) instead of grepping a free-text log. A task belongs
   to the sample by an **exact** nf-core `tag` match (so a zero-padded id can't cross-fire
   a substring), and counts as failed when its status is in `runbook.trace_failure_statuses`
   (default `["FAILED", "ABORTED"]` — illustrative/configurable, **not** a clinical set)
   **or** its exit code is nonzero. It emits a CRITICAL `PIPELINE` finding citing `trace.txt`
   + the exit code, and maps to **RERUN** under the same operational-failure policy (verdict
   policy 3) as PIPE-001 — the verdict rationale is unchanged, only the evidence source is.

Both rules **read** an artifact the pipeline dropped; bayleaf composes, it does not
execute — the gate never runs a process ([ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)).
`trace.txt` is an **optional** input: present only for runs that had a process failure
(see [`data/README.md`](../../data/README.md)).

## Route-to-human policy (VAR-RTH-001) — OFF BY DEFAULT (2026-07-10, ADR-0018 D2)

A **variant-gate** rule, distinct from the call-quality rows in Gate 3 above: it does not gate
DP/GQ/allele-balance, it **routes a sample to mandatory human review** when an annotated candidate
carries a clinically-significant ClinVar classification. Realizes the maintainer's decision that a
route-to-human action belongs on the gate as a **role-based human-review routing rule** (ADR-0018
D2) — the highest clinical-sensitivity call in the system, so its scope is drawn tightly:

1. **Disarmed by default.** `Runbook.route_to_human` (`runbook.RouteToHumanPolicy`) carries an
   empty `significances` tuple — `.armed` is `False` — so the **stock runbook never routes** and
   the pinned demo scenario (and every other verdict) is byte-for-byte unchanged. An operator arms
   it by configuring the ClinVar `CLNSIG` values (e.g. `("Pathogenic", "Likely_pathogenic")`) that
   should route, and optionally a `review_statuses` star-rating floor (a stricter arming — a
   single-submitter call does not route unless its review status is on the allow-list).
2. **Rules decide to ROUTE; a human decides the outcome (ADR-0001).** When armed and a
   `VariantCall` for the sample matches (significance folded case-/separator-insensitively for
   matching only — the cited value stays verbatim), `rules._check_route_to_human` emits a
   **CRITICAL** `Finding` — category `variant` (lands on the **variant** gate, `Gate.VARIANT`),
   `rule_id="VAR-RTH-001"`, `suggested_verdict=ESCALATE` (route to a human — the most conservative
   action). It **quotes ClinVar verbatim** as cited `Evidence` (`source_field="CLNSIG"`, the
   accession + release version as the citation, the review status as the threshold field) — it
   authors **no pathogenicity determination of its own** (ADR-0004). A qualified human adjudicates
   via the existing RBAC-gated review queue ([ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md));
   no new access pattern.
3. **Not a clinical-significance gate.** The action space is only `{route-to-human}` — there is no
   Pathogenic/Benign verdict and no probability. It escalates *toward* human judgment; the variant
   **QC** gate (DP/GQ/AB, Gate 3 table above) is untouched — this is a distinct, additive
   review-routing rule on the same gate.
4. **Reads, never runs.** The rule reads `RunArtifacts.variant_calls` (`VariantCall`, parsed from
   an externally-produced `variants.csv` by `parsers.parse_variant_calls`) — bayleaf never runs
   an annotator (compose ≠ execute, ADR-0003). Empty for every run today, so a run without
   `variants.csv` is unaffected (belt-and-suspenders: `evaluate_sample` on a run with variant calls
   but a disarmed policy yields the exact finding set it would without any variant data).

**Status.** Built and unit/end-to-end tested (`tests/test_route_to_human.py`, 10 cases). **Off by
default for every run except one deliberately-armed demo fixture (2026-07-11):**
`data/RUN-2026-07-11-CLINVAR-RTH/` (`origin=contrived`) carries a `route_to_human` marker + a
`variants.csv` spiking a verbatim-cited ClinVar Pathogenic BRCA1 candidate HG002 does not actually
carry, and is the one committed run that ESCALATEs via `VAR-RTH-001` when evaluated through the API
(`api.main._active_runbook` arms the policy **per run**, see [ADR-0018 Realized](../adr/ADR-0018-variant-interpretation-advisory-evidence.md#realized-2026-07-11)).
Every other committed run (incl. the pinned demo scenario) still carries no marker and stays
disarmed. See [schemas.md](schemas.md) for the `VariantCall`/`RouteToHumanPolicy` field contracts.

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

## Implementation status (T-082, 2026-07-10)

The tables above are the **cited guideline runbook** (design intent); `runbook.py` (code) is a
concrete, illustrative default that does not always match a cited figure verbatim (e.g. the
implemented `qc.breadth_20x` gate is `0.90`/`hard_fail 0.80`, not the ACGS `≥99%` example above —
an intentional MVP flat default, not a drift bug; assay-tuned profiles are the config-driven
future, REQ-F-015). As of T-082, the **Gate 2/3 rows below are wired end-to-end** (parsed from a
richer `qc_metrics.csv` → registered `MetricValue` → runbook-gated or surfaced as an observation),
each **optional** (`required=False`: a present-but-failing value gates; an absent one is silently
skipped, never NA-flagged — so a lean real run stays clean while a rich contrived run is scored):

1. **Breadth ≥20x / ≥30x** (`qc.breadth_20x`/`qc.breadth_30x`) — now two separate gated rows
   (was one combined row above), `required=False`.
2. **% mapped** (`qc.pct_mapped`) — `required=False`.
3. **On-target rate** (`qc.on_target`) — `required=False`.
4. **Depth (DP)** (`variant.dp`) — `required=False`, the first **Gate 3** threshold implemented.

**2026-07-10 addition (ADR-0018 D2):** the **route-to-human policy (VAR-RTH-001)**, above, is a
fifth Gate-3 rule — not a `QCThreshold`/metric-registry gate like 1–4, but a policy-driven `Finding`
read from `RunArtifacts.variant_calls`. **Off by default**; one committed fixture arms it
(`data/RUN-2026-07-11-CLINVAR-RTH/`, 2026-07-11 — see the Status note above).

5. **Ti/Tv (`variant.titv`) — target-band gate (2026-07-12, gap-analysis WS-06 Gap 2).** A sixth
   Gate-3 rule, and the first `QCThreshold` to use the new **`target_band`** shape (both-tails:
   PASS inside `[target_low, target_high]`, WARN/HOLD inside `[hard_low, hard_high]` but outside
   the target band, CRITICAL/RERUN outside the hard band) — a `one_sided` gate can only catch one
   tail, so an out-of-spec Ts/Tv in EITHER direction (too low → excess false-positive artifact; too
   high → over-aggressive filtering) could never score before this. `required=False`: a run
   without a `variant.titv` value (the pinned demo + HG002, still) NA-flags nothing and every
   existing verdict stays byte-identical. Band `[target: 2.0–2.1, hard: 1.8–2.8]` — an
   **illustrative whole-genome heuristic, NOT a clinical threshold**, operator-configurable
   (CLAUDE.md life-science guardrail 3). Metric catalog reads **13 gated / 8 ungated** of 21
   registered `our_key`s (was 11/9 of 20) — see [metric_registry.md](metric_registry.md) Wiring
   status.
6. **Contamination (FREEMIX, `contamination.freemix`) and SNP concordance
   (`concordance.snp_f1`) — gated 2026-07-12 (gap-analysis WS-02/WS-04).** A seventh and eighth
   optional threshold, both `required=False`. **Gated + parser-wired, NOT pipeline-produced**: a
   real parser reads a present `.selfSM`/hap.py `summary.csv` (`ingest.nfcore._extract_verifybamid`/
   `_extract_happy`), but no pipeline committed in this repo runs verifybamid2 or hap.py today —
   both ship only as standalone Nextflow modules (`pipelines/optional_modules/`) outside the
   drift-locked `pipelines/germline/` reference. See [metric_registry.md](metric_registry.md)
   Wiring status for the full honesty note.

**Ungated observations** (registered + wired, no threshold, never NA-flagged, never a finding):
% PhiX aligned (`preflight.phix_aligned`), Genotype quality (`variant.gq`) — populate the
**Gate 1** and **Gate 3** groups with real numbers for the first time (previously always an empty
note for every run). **Ti/Tv (`variant.titv`), Contamination (`contamination.freemix`), and SNP
concordance (`concordance.snp_f1`) moved out of this list** — they are now genuinely gated (items 5
and 6 above), not merely ungated observations. **Still not computed by any parser at all**
(registered in [metric_registry.md](metric_registry.md), no code path whatsoever): zero-coverage
targets, fold-enrichment, fold-80, NGSCheckMate identity, sex concordance, allele balance — these
rows above remain design-only.

## Runbook resolution — `RunbookSet` (WS-05, 2026-07-12)

The runbook was, until this addition, always a single object — every sample in a run scored
against the same thresholds regardless of assay or specimen type. `runbook.RunbookSet` (a pure,
deterministic resolver) fixes that:

1. **`RunbookKey(assay, sample_type, platform)`** — frozen/hashable, normalized (strip + lowercase);
   a `None` axis is a wildcard.
2. **`RunbookSet{default, profiles}`** — `resolve(sample, platform)` reads `assay` from
   `sample.extra["assay"]` (falling back to `library_prep` — there is no first-class `assay` field
   on `Sample` yet, a deferred intake/LIMS seam), `sample_type` from `sample.tissue`, `platform`
   from `RunArtifacts.platform`.
3. **Binary-weight precedence** (`assay=4 > sample_type=2 > platform=1`) is a total order — no
   ties; the most-specific matching profile wins, else the full `default` runbook. `resolve()`
   never returns `None` and never falls back to an empty gate.
4. **`rules.evaluate_run`** is widened to accept `Runbook | RunbookSet` (a bare `Runbook` is used
   AS-IS, unchanged); `evaluate_sample`/`aggregate_verdict` are **UNCHANGED** — they always receive
   a concrete, already-resolved `Runbook` (ADR-0001 preserved: this is a config-resolution layer,
   never a verdict-authoring one). `engine.run_gate`/`run_gate_from_dir` accept a `RunbookSet` too.
5. **`GERMLINE_PANEL_RUNBOOK`** — same gating thresholds as the default runbook, plus
   `expected_metrics=("qc.breadth_20x", "qc.breadth_30x")` (both producible, so it passes WS-01's
   construction-time validator). `DEFAULT_RUNBOOK_SET` ships it armed on `assay="germline-panel"` —
   the **first production consumer** of WS-01's `expected_metrics` mechanism, which shipped
   dormant (no runbook in the tree populated it) until this addition.
6. **Verified end-to-end, not just asserted:** the SAME germline-panel sample (passing the frozen-
   five QC, `breadth_20x`/`breadth_30x` omitted) **PROCEEDs** under the stock `DEFAULT_RUNBOOK` but
   **HOLDs** under `DEFAULT_RUNBOOK_SET`, driven by `QC-EXPECTED-QC.BREADTH_20X` +
   `QC-EXPECTED-QC.BREADTH_30X` — through both `evaluate_run` and the full `run_gate` card path.
   The pinned demo (`data/mock_run_01`) is **byte-identical** on the plain-`Runbook` path and via
   `DEFAULT_RUNBOOK_SET` (no mock/GIAB sample declares `assay="germline-panel"` — the shipped
   `library_prep`s are TruSeq/Nextera — so the panel profile is dormant-but-deployed).
7. **Deferred, honestly labelled (not half-wired):** the Settings→runbook config-apply loop
   (`api/main.py::_active_runbook` still returns one run-level `Runbook`, commented as the WS-05
   Gaps B/C/D follow-on) and the assay×tissue frontend UI.

## Fail-closed rules — `QC-MISSING` / `QC-EXPECTED-<key>` (WS-01, 2026-07-12)

Two rules that close the gap between "no rule objected" and "examined and clean" — the review
finding that a run with zero findings unconditionally aggregated to **PROCEED**, including a run
whose QC was never examined at all:

1. **`QC-MISSING`** (in `_check_presence`, the symmetric partner of `PROV-002`) — a sheet-declared
   sample with **no QC row at all** now emits a WARN-severity finding mapping to **HOLD**, citing
   `qc_metrics.csv`, guarded on `sheet is not None` (so an intake-only / not-yet-sequenced sample is
   never false-HOLDed). Live end-to-end, needs no configuration: `aggregate_verdict([])` can no
   longer PROCEED a sample whose safety gate was never run.
2. **`QC-EXPECTED-<key>`** (`rules._check_expected_metrics`, reading `Runbook.expected_metrics`) —
   any registry `our_key` a profile explicitly expects to have examined, but which is absent from
   the sample's metrics, emits a WARN → HOLD finding — restoring signal a `required=False`
   threshold silently drops when a value is simply missing. `Runbook.expected_metrics` is validated
   at construction against `metrics.mapping.producible_metric_keys()` (the keys the parser can
   actually emit) and de-duplicated, so a typo or an unwired registered-only key can't HOLD every
   sample forever with a message that misdirects toward the pipeline — it fails loud at
   config-load instead. **Shipped as a mechanism only until 2026-07-12** — no runbook in the tree
   populated `expected_metrics`, so it never fired in production; `RunbookSet`'s
   `GERMLINE_PANEL_RUNBOOK` (above) is its first live consumer.
3. **`aggregate_verdict` is untouched by either rule** (ADR-0001) — both are ordinary `Finding`s
   the existing verdict-aggregation logic already knew how to fold in; the `DEFAULT_RUNBOOK` (no
   `expected_metrics`) is byte-for-byte inert to rule 2.

**Honest, related surfacing (WS-01 PR2–4):** `models.CheckCoverage` (`rules.compute_check_coverage`)
now accompanies every `DecisionCard` with a deterministic "N of M check categories ran; X not
examined" count over a fixed category catalog (provenance/metadata/qc/contamination/identity/
pipeline) — carried un-hashed, never a verdict — replacing the stub's old "all checks passed"
prose and the RunDetail clean-card panel's matching claim. Contamination and identity still read
as honestly **not examined**, even now that WS-02 wires FREEMIX (2026-07-12) — the flip did **not**
land as originally planned. `compute_check_coverage`'s `artifact_present[Category.CONTAMINATION]`
stays hardcoded `False` (`rules.py` `_EXPECTED_CATEGORIES` block), and the generic threshold loop
that scores `contamination.freemix` (`_evaluate_metric`/`_evaluate_target_band`) tags **every**
`QCThreshold` finding `category=Category.QC` — never `Category.CONTAMINATION` — so a `QC-FREEMIX`
finding never lands in `found_categories` for that category either. **Verified directly**: a sample
carrying only a WARN-triggering FREEMIX value (`0.0312`) produces a `QC-FREEMIX` finding but
`compute_check_coverage` still returns `contamination` in `not_examined`
(`uv run python` against `rules.evaluate_sample` + `rules.compute_check_coverage` — no fixture
exercises this combination in `tests/`). The category-flip described in the original WS-01 design
comment remains **unbuilt** — a real fix needs either a category-aware tag on the contamination/
identity thresholds or a bespoke rule (the WS-02 design's original `CONTAM-001` proposal), neither
of which WS-02 implemented (it reused the existing generic QC-scoring loop by design — see
[metric_registry.md](metric_registry.md) Wiring status). NGSCheckMate identity remains unparsed
entirely (no `.selfSM`-equivalent parser exists yet), so `identity` stays not-examined regardless.

**Two data tracks stay honest about depth of coverage:** a **contrived** run (the synthetic
generator, `mock_run_02/03`/`scale_30`) emits all 8 additional metrics (comfortably passing) for a
full 13-metric, three-gate readout; the **real** GIAB HG002 run (`scripts/run_giab_pipeline.py`)
only emits what its own tools actually produced — `breadth_20x`/`breadth_30x` from its own
mosdepth (real: 99.24%/97.07%, both PASS) — `cluster_pf` and everything else above stays blank/no
finding, never invented.

**Labeling honesty (audit P3-10 / P3-1).** Three as-built clarifications, so the tables above are not
read as more than what runs:
1. **Duplication source is fastp, not Picard.** The Gate 2 table cites Picard `PERCENT_DUPLICATION`
   as the literature/reference field, but the as-built live driver
   (`scripts/run_giab_pipeline.py::parse_fastp`) parses the duplication rate from **fastp.json**
   (`duplication.rate`); the reference germline pipeline dedups with `samtools markdup`, whose metrics
   file is not the gated source. The registry entry now names fastp as the source (Picard/MultiQC keys
   stay supported alternates via aliases).
2. **The variant gate is narrow: depth + a Ts/Tv sanity band (+ an optional, GIAB-only concordance
   floor), not a full variant-quality gate.** Of Gate 3, **Depth (DP)** (`variant.dp`, one-sided),
   **Ts/Tv** (`variant.titv`, `target_band`, as of 2026-07-12), and, as of 2026-07-12 (WS-04),
   **SNP-F1 concordance** (`concordance.snp_f1`, one-sided FLOOR — gated + parser-wired but not
   pipeline-produced, see item 6 above) are thresholds. SNP-F1 is only ever populated for a sample
   with a bound GIAB truth set (HG002-style benchmark runs); every other sample carries no value and
   is never NA-flagged (`required=False`). GQ (`variant.gq`) stays an ungated observation;
   allele-balance and gnomAD AF are **not computed** (no parser).
3. **cluster_pf HOLD is structural and expected.** `cluster_pf` is `required=True` yet a reads-only
   fastq→BAM path structurally can't produce this run-level SAV/InterOp metric, so every reads-based run
   HOLDs on it — the honest "cluster_pf-missing" signal the pinned demo relies on (HG002 → HOLD), not a
   QC failure. Making PROCEED reachable on the live path means sourcing cluster_pf from a real SAV/InterOp
   feed — a **deferred** policy decision, **not** a `required` flip (ADR-0001).

## Config model & test-data validation

Thresholds live in an operator-owned runbook **profile** keyed on **assay × sample
type** (whole blood / saliva) — the resolution mechanism for this is now built (`RunbookSet`,
above); the two profiles below are about *which thresholds a profile carries*, a separate,
still-open question from *how a sample resolves to one*. We ship two:
1. A **guideline-default profile** — the cited defaults above.
2. A concrete **test-data profile** tuned to our GIAB HG002 panel-subset. Its prerequisite —
   fetching a small real GIAB slice ([T-017](../planning/tasks.md)) — is **done**: the fetch
   script ([`scripts/fetch_giab_hg002.py`](../../scripts/fetch_giab_hg002.py)) is validated
   end-to-end (truth VCF + panel-region reads; see [strategy.md](strategy.md)). Tuning the
   profile to what that dataset actually achieves is the remaining step, still with **no
   hardcoded universals**.
