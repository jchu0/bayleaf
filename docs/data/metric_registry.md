# Metric Registry

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | bioinformatics / software |
| **Related** | [schemas.md](schemas.md) (§6 units contract), [provenance.md](provenance.md), [qc_metrics.md](qc_metrics.md), [nf-core-conventions.md](nf-core-conventions.md), [ADR-0015](../adr/ADR-0015-layered-data-contract.md) |

## Overview

The **canonical metric vocabulary** — the stable layer above drifting MultiQC/tool keys.
`MetricValue` records observed values; the **registry defines what they mean** (canonical
unit, direction, source contract). It is a **versioned artifact** (pinned per `AnalysisRun`
as `metric_registry_version`). This is why a MultiQC key change never silently breaks a gate.

**Realized in code (T-024/T-025).** The registry is a real
[`metric_registry.yaml`](../../src/pipeguard/metrics/metric_registry.yaml) loaded by a typed,
frozen [`MetricRegistry`](../../src/pipeguard/metrics/registry.py)
(`entry`/`resolve_alias`/`normalize`/`denormalize`/`observe`), and it is **on the QC critical
path today**: the rule engine maps each parsed `QCMetrics` field to its `our_key`, normalizes
via `observe`, and gates on `MetricValue.normalized_value`
([mapping.py](../../src/pipeguard/metrics/mapping.py) → [rules.py](../../src/pipeguard/rules.py)).
*(The `pipeguard.metrics` module docstrings still read "additive only" — stale; the wiring
has landed.)*

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
| `qc.duplication` | qc | duplication | fraction | lower_is_better | picard_markduplicates | `PERCENT_DUPLICATION` |
| `qc.pct_mapped` | qc | alignment | fraction | higher_is_better | samtools | flagstat mapped |
| `qc.on_target` | qc | enrichment | fraction | higher_is_better | picard_collecthsmetrics | `PCT_SELECTED_BASES` |
| `qc.mean_target_coverage` | qc | coverage | x | higher_is_better | picard_collecthsmetrics | `MEAN_TARGET_COVERAGE` |
| `qc.breadth_20x` | qc | coverage | fraction | higher_is_better | picard_collecthsmetrics / mosdepth | `PCT_TARGET_BASES_20X` / `20_x_pc` |
| `qc.breadth_30x` | qc | coverage | fraction | higher_is_better | picard_collecthsmetrics | `PCT_TARGET_BASES_30X` |
| `qc.zero_cov_targets` | qc | coverage | fraction | lower_is_better | picard_collecthsmetrics | `ZERO_CVG_TARGETS_PCT` |
| `qc.fold_enrichment` | qc | enrichment | ratio | target_band | picard_collecthsmetrics | `FOLD_ENRICHMENT` |
| `qc.fold_80` | qc | uniformity | ratio | lower_is_better | picard_collecthsmetrics | `FOLD_80_BASE_PENALTY` |
| `identity.ngscheckmate_match` | qc | identity | bool | higher_is_better | ngscheckmate | `ngscheckmate_matched.txt` |
| `identity.sex_concordance` | qc | identity | bool | higher_is_better | ngscheckmate / mosdepth | declared_sex vs coverage |
| `contamination.freemix` | qc | contamination | fraction | lower_is_better | verifybamid2 *(optional, non-sarek-default)* | `FREEMIX` |
| `variant.dp` | variant | depth | x | higher_is_better | vcf | `FORMAT/DP` |
| `variant.gq` | variant | genotype_quality | phred | higher_is_better | vcf | `GQ` |
| `variant.allele_balance` | variant | genotype_quality | fraction | target_band | vcf | `AD` → AB |
| `variant.titv` | variant | sanity | ratio | target_band | bcftools / picard | `ts/tv` |

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
