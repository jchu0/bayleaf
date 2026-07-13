# Metric Registry

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-13 (MST) — live-genomics pass (`478d579`): `contamination.freemix`/`concordance.snp_f1` parsers proven against REAL, calibrated VerifyBamID2/hap.py tool output (not just a format-mimicking fixture) — see the honesty note below; the "not pipeline-produced" caveat and the 21/13/8 counts are unchanged. Prior: 2026-07-12 (MST) — WS-02/WS-04: `contamination.freemix` (VerifyBamID2) and new key `concordance.snp_f1` (hap.py) gated + parser-wired (not pipeline-produced); registered/gated/ungated counts 20/11/9 → 21/13/8 |
| **Audience** | bioinformatics / software |
| **Related** | [schemas.md](schemas.md) (§6 units contract), [provenance.md](provenance.md), [qc_metrics.md](qc_metrics.md), [nf-core-conventions.md](nf-core-conventions.md), [ADR-0015](../adr/ADR-0015-layered-data-contract.md), [ADR-0004](../adr/ADR-0004-vcf-first-giab-substrate.md) (never fabricate truth), [audit/gap_analysis/ws-02-identity-provenance.md](../../audit/gap_analysis/ws-02-identity-provenance.md), [audit/gap_analysis/ws-04-giab-concordance.md](../../audit/gap_analysis/ws-04-giab-concordance.md), [audit/gap_analysis/ws-06-registry-extensibility-and-metric-bugs.md](../../audit/gap_analysis/ws-06-registry-extensibility-and-metric-bugs.md), [journal 2026-07-10](../journal/2026-07-10-provenance-qc-builder-auth.md), [journal 2026-07-12](../journal/2026-07-12-gap-analysis-remediation-verification.md) |

## Overview

The **canonical metric vocabulary** — the stable layer above drifting MultiQC/tool keys.
`MetricValue` records observed values; the **registry defines what they mean** (canonical
unit, direction, source contract). It is a **versioned artifact** (pinned per `AnalysisRun`
as `metric_registry_version`). This is why a MultiQC key change never silently breaks a gate.

**Realized in code (T-024/T-025).** The registry is a real
[`metric_registry.yaml`](../../src/bayleaf/metrics/metric_registry.yaml) loaded by a typed,
frozen [`MetricRegistry`](../../src/bayleaf/metrics/registry.py)
(`entry`/`resolve_alias`/`normalize`/`denormalize`/`observe`), and it is **on the QC critical
path today**: the rule engine maps each parsed `QCMetrics` field to its `our_key`, normalizes
via `observe`, and gates on `MetricValue.normalized_value`
([mapping.py](../../src/bayleaf/metrics/mapping.py) → [rules.py](../../src/bayleaf/rules.py)).

## Entry shape

```yaml
metric_registry_version: 1
metrics:
  <our_key>:
    display_name: str
    gate: preflight | qc | variant
    category: str                 # free-form descriptive label, not an enum (e.g. base_quality, yield, alignment, enrichment, coverage, identity, contamination, run_qc) — matches MetricEntry.category in registry.py
    canonical_unit: fraction | percent | x | ratio | phred | count | bool
    value_type: float | int | bool
    direction: higher_is_better | lower_is_better | target_band
    source:
      module: str                 # e.g. picard_collecthsmetrics
      source_file: str            # where the value is parsed from
      json_path | raw_field: str  # exact key/field
    raw_units_allowed: [str]
    parser: str
    parser_version: str
    aliases: [str]                # prior/variant MultiQC keys that map here
```

## Seed registry (panel-relevant metrics)

| our_key | gate | category | canonical_unit | direction | module | source_field |
|---|---|---|---|---|---|---|
| `preflight.phix_aligned` | preflight | run_qc | percent | higher_is_better | sav_interop | PhiX Aligned |
| `qc.q30` | qc | base_quality | fraction | higher_is_better | fastp | `after_filtering_q30_rate` |
| `qc.reads_passing_filter` | qc | yield | fraction | higher_is_better | fastp | `filtering_result_passed_filter_reads` / `pct_surviving` |
| `qc.cluster_pf` | qc | yield | fraction | higher_is_better | sav_interop | `Cluster PF` |
| `qc.duplication` | qc | duplication | fraction | lower_is_better | fastp *(as-built; Picard/MultiQC alt via aliases)* | fastp.json `duplication.rate` |
| `qc.pct_mapped` | qc | alignment | fraction | higher_is_better | samtools | flagstat mapped |
| `qc.on_target` | qc | enrichment | fraction | higher_is_better | picard_collecthsmetrics | `PCT_SELECTED_BASES` |
| `qc.mean_target_coverage` | qc | coverage | x | higher_is_better | mosdepth | mosdepth.summary.txt `total_region.mean` |
| `qc.breadth_20x` | qc | coverage | fraction | higher_is_better | mosdepth | mosdepth.thresholds.bed.gz `ge_20x_bases/region_bases` |
| `qc.breadth_30x` | qc | coverage | fraction | higher_is_better | mosdepth | mosdepth.thresholds.bed.gz `ge_30x_bases/region_bases` |
| `qc.zero_cov_targets` † | qc | coverage | fraction | lower_is_better | picard_collecthsmetrics | `ZERO_CVG_TARGETS_PCT` |
| `qc.fold_enrichment` † | qc | enrichment | ratio | target_band | picard_collecthsmetrics | `FOLD_ENRICHMENT` |
| `qc.fold_80` † | qc | uniformity | ratio | lower_is_better | picard_collecthsmetrics | `FOLD_80_BASE_PENALTY` |
| `identity.ngscheckmate_match` † | qc | identity | bool | higher_is_better | ngscheckmate | `ngscheckmate_matched.txt` |
| `identity.sex_concordance` † | qc | identity | bool | higher_is_better | ngscheckmate / mosdepth | declared_sex vs coverage |
| `contamination.freemix` ‡ | qc | contamination | fraction | lower_is_better | verifybamid2 *(optional, non-sarek-default)* | `FREEMIX` |
| `variant.dp` | variant | depth | x | higher_is_better | vcf | `FORMAT/DP` |
| `variant.gq` | variant | genotype_quality | phred | higher_is_better | vcf | `GQ` |
| `variant.allele_balance` † | variant | genotype_quality | fraction | target_band | vcf | `AD` → AB |
| `variant.titv` | variant | sanity | ratio | target_band | bcftools / picard | `ts/tv` |
| `concordance.snp_f1` ‡ | variant | concordance | fraction | higher_is_better | hap.py *(optional, GIAB-truth-only)* | `METRIC.F1_Score` (SNP+PASS row) |

**†** = **NOT COMPUTED** (audit P3-10): registered-only, no parser wired at all — the `module`/`source_field` above name the *designed* source, not a value produced today.
**‡** = **PARSER-WIRED, NOT PIPELINE-PRODUCED** (WS-02/WS-04, 2026-07-12): a real parser exists and reads a present output file into a gated `MetricValue` — but no pipeline committed in this repo runs the producing tool today. See **Wiring status** below.

## Rules

1. `metric_registry_version` bumps **deliberately** and is pinned on every `AnalysisRun`.
2. `aliases[]` maps prior/variant MultiQC keys to the canonical `our_key` — the shield
   against MultiQC key drift.
3. `canonical_unit` is the single source for normalization; `MetricValue.normalized_value`
   is computed against it (and snapshotted onto every record for ML-self-containment).
   `denormalize` is the exact inverse over the same closed conversion table — used to render a
   canonical threshold back into a metric's raw/display unit (a `0.85` fraction gate shown as
   `85%`) with no hardcoded factor.
4. Thresholds may only key on registered `our_key`s (controlled vocabulary) — **realized:**
   `runbook.QCThreshold` carries an `our_key` and stores `gate`/`hard_fail` in the metric's
   **canonical** unit (Q30 `0.85`, coverage in `x`), and a test asserts every threshold
   `our_key` is registered. The rules compare `MetricValue.normalized_value` against it, so a
   threshold and the value it gates are always on the same scale (the fuller
   `RunbookProfile.thresholds` config record in [schemas.md](schemas.md) #19 keeps the same
   rule).

## Read endpoint (W16/T-038)

`GET /api/metrics/registry` exposes the registered metric vocabulary read-only (every type + whether it is **gated** by the runbook today or **registered-but-not-yet-gated**), reading `default_registry()` / `DEFAULT_RUNBOOK`. Surfaced in the Settings "Metric catalog" panel. It never authors or edits a metric/threshold (ADR-0001).

## Wiring status (T-082, 2026-07-10; counts updated 2026-07-12, WS-02/WS-04 + WS-06 Gap 2)

Of the 21 registered `our_key`s, **13 are gated** by a `runbook.QCThreshold` — the original 5
`required=True` (Q30, reads-passing-filter, mean-target-coverage, cluster-PF, duplication) plus
8 `required=False` ("optional": `qc.breadth_20x`, `qc.breadth_30x`, `qc.pct_mapped`,
`qc.on_target`, `variant.dp` — score a value that IS present, never NA-flag one that's absent)
plus, as of the gap-analysis WS-06 Gap-2 fix (2026-07-12), a sixth `required=False` threshold on
**`variant.titv`** — the first threshold to use the new `kind="target_band"` shape (a both-tails
gate: PASS inside `[target_low, target_high]`, WARN/HOLD inside `[hard_low, hard_high]` but
outside the target band, CRITICAL/RERUN outside the hard band — a `one_sided` gate can only catch
one tail, so Ts/Tv could never score before this). The band (target `[2.0, 2.1]`, hard
`[1.8, 2.8]`) is an **illustrative whole-genome heuristic, operator-configurable, NOT clinical**
(CLAUDE.md life-science guardrail 3). A seventh and eighth `required=False` threshold landed the
same day: **`contamination.freemix`** (WS-02) and **`concordance.snp_f1`** (WS-04) — see the
honesty note below before treating either as "computed."

**WS-02/WS-04 honesty (2026-07-12) — gated + parser-wired, NOT pipeline-produced.**
`contamination.freemix` (VerifyBamID2 FREEMIX, one_sided lower-is-worse, gate 0.02 → WARN/HOLD,
hard_fail 0.05 → CRITICAL/RERUN) and `concordance.snp_f1` (hap.py SNP-F1 vs GIAB truth, one_sided
FLOOR, gate 0.99 → WARN/HOLD, hard_fail 0.95 → CRITICAL/RERUN) moved out of the NOT-COMPUTED set:
`ingest.nfcore._extract_verifybamid`/`_extract_happy` are real parsers that read a present
`.selfSM` / hap.py `summary.csv` into a genuine `MetricValue`, and each threshold is
`required=False` because verifybamid2/hap.py are **not in the germline base profile** — an absent
value is never NA-flagged, only a present one scores. Both are illustrative/operator-configurable,
not clinical (CLAUDE.md life-science guardrail 3). **But no pipeline committed in this repo
produces either input today.** `verifybamid2.nf`/`happy.nf` are real, standalone Nextflow modules
(`pipelines/optional_modules/`, real `script:` + `stub:`) that are **not wired into
`pipelines/germline/main.nf`** — that reference pipeline is drift-locked byte-for-byte to the
card-graph compiler's own output (`tests/test_nextflow_compile.py::test_committed_reference_pipeline_matches_the_compiler`),
and the compiler has no input-gated-conditional concept for an optional add-on tool yet. A live
FREEMIX or SNP-F1 number therefore requires an operator to run the standalone module by hand
(verifybamid2 additionally needs an SVD/UD ancestry resource panel; hap.py needs the GIAB truth
VCF + high-confidence BED — both **labelled pipeline inputs, never fabricated**, ADR-0004) and
place its output where `ingest_results_dir` looks for it. This is the same "gate-wired but not
gate-called" honesty pattern already recorded for the WS-03 ingest adapter itself — one layer
earlier in the pipeline (see [CLAUDE.md](../../CLAUDE.md) code map item 1g).

**Proven on real, calibrated tool output (2026-07-13, `478d579`) — a step up from "parser-wired,
fixture-tested," the "not pipeline-produced" caveat above unchanged.** The offline WS-02/WS-04
tests above prove the ingest→gate WIRING against hand-built fixtures that mimic the real file
*format*; they explicitly deferred "does a real tool's own output parse the same way" to a live
pass. That pass ran 2026-07-13 (an operator ran the standalone modules by hand, per the gap above):
VerifyBamID2 2.0.3 **genome-wide** on the full HG002 2×250 BAM produced a FREEMIX that passed the
marker sanity check **natively** (no `--DisableSanityCheck`, unlike a chromosome-capped heuristic) —
i.e. a genuinely **calibrated** value, 0.000220096 — and the real germline pipeline (chr20/21/22,
300,175 variants) produced a hap.py `summary.csv` scored against the GIAB v4.2.1 truth (SNP/PASS
F1 = 0.989276). The tiny derived outputs (294 B + 893 B) are committed verbatim under
`tests/fixtures/giab_real/` (origin `real-giab`; the 122 GB BAM stays on the external SSD, never
committed) and read through the same public `ingest_results_dir → run_gate` path in
`tests/test_real_giab_calibrated.py` — a permanent, CI-runnable proof, not a one-off manual check.
This closes the gap between "the parser handles the real *shape*" and "the parser handles a real
*tool's own* output" — it does **not** close the separate, unrelated gap that no pipeline in this
repo runs either tool automatically (that gap is exactly as open as before this pass).

The other **8 are ungated** (registered, no threshold) — of those, only 2
(`preflight.phix_aligned`, `variant.gq`) are actually wired end-to-end from `QCMetrics` →
`MetricValue` (`metrics/mapping.py`, T-082) and surfaced as observations in the card readout via
the registry's `display_name` (not the raw `our_key`, T-082 follow-up). The remaining 6
(`qc.zero_cov_targets`, `qc.fold_enrichment`, `qc.fold_80`, `identity.ngscheckmate_match`,
`identity.sex_concordance`, `variant.allele_balance`) remain registered-only with **no parser at
all** — an honest, unchanged gap, not newly introduced by WS-02/WS-04. Verified against
`src/bayleaf/metrics/mapping.py` `_QCMETRICS_MAP` (13 entries, **unaffected** by WS-02/WS-04 —
freemix/snp_f1 flow through the WS-03 `ingest.nfcore` adapter, not the flat-CSV
`_QCMETRICS_MAP` path, so `producible_metric_keys()` is unchanged), `src/bayleaf/runbook.py`'s
`qc_thresholds` (13 `QCThreshold(...)` entries), and
`tests/test_api.py::test_metric_catalog_lists_registered_metrics_and_gated_flag` (asserts
`n_registered == 21`, `n_gated == 13`, and the ungated count `== 8` over
`GET /api/metrics/registry`).
