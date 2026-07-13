# nf-core / Nextflow Conventions → bayleaf Schema

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-12 (MST) — §4 corrected: the "pending real MultiQC parsing" claim was stale; `ingest/nfcore.py` (WS-03) now does it, proven on real HG002, but not yet the production intake path |
| **Audience** | bioinformatics / software |
| **Related** | [schemas.md](schemas.md) (the records we derive), [metric_registry.md](metric_registry.md) (the registry §4 argues for), [qc_metrics.md](qc_metrics.md), [ADR-0004](../adr/ADR-0004-vcf-first-giab-substrate.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md), [design/nextflow-codegen.md](../design/nextflow-codegen.md) (this vocabulary now feeds a real DSL2 generator, not only this doc's mapping notes), [audit/gap_analysis/ws-03-ingestion-adapter.md](../../audit/gap_analysis/ws-03-ingestion-adapter.md), [journal 2026-07-12](../journal/2026-07-12-gap-analysis-remediation-verification.md) |

## Framing

nf-core schemas validate a pipeline's **inputs** ("will it run?"); a decision-gate
validates a pipeline's **outputs** ("should we trust the result?"). We **adopt the
vocabulary** for interoperability and **diverge on semantics** (thresholds, verdicts,
integrity). Reference pipeline: nf-core/sarek (germline DNA panel).

**Update (2026-07-11):** this doc's package/module conventions (bioconda + biocontainer dual
packaging, `process`/`conda`/`container` directives, `emit:` channel names) are no longer only
notes on someone else's convention — `src/bayleaf/nextflow/catalog.py` follows them directly to
generate a REAL, runnable DSL2 pipeline from a Builder card graph, and
`scripts/run_giab_pipeline.py` now runs that generated pipeline via `nextflow run` for the intake
driver. See [design/nextflow-codegen.md](../design/nextflow-codegen.md). **Same-day follow-up
(W4):** §2's `[meta, files]` channel convention below was, at first, only a documented target —
the initial generator threaded `${params.sample}` directly rather than a real `meta` map. W4
closes that gap too: every catalogued process now carries `tuple val(meta), …` and tags by
`${meta.id}`, so the generated pipeline genuinely adopts §2, not just the packaging conventions
above it (MultiQC is the one deliberate exception, per §2's own aggregator framing — it collects
across samples and so drops `meta`, matching real nf-core aggregator modules).

**Reserved-port honesty + the frontend↔catalog no-drift discipline (2026-07-12).** A tool's
`emit:` channels and a Builder card's shown output ports are **the same set, kept in lockstep** —
the frontend `BuilderShared.tsx` (`BTOOLSPEC`/`CARD_PORTS`/`ARTIFACT_KINDS`) and the backend
`catalog.py` `ProcessSpec` must agree on every port kind. Two guardrails enforce this:
1. **Every shown port is a real channel or it is removed — no superficial reserved slots.** A port
   only exists if the tool's actual command produces (output) or consumes (input) that artifact.
   Kinds with no real producer were removed rather than left dangling: `bwa-mem2` `read_group` (a
   computed `@RG` string, not a file), `mosdepth` `per_base` (suppressed by `--no-per-base`),
   `bcftools norm` `panel_bed` (norm is genome-wide), `MultiQC`
   `fastqc_zip`/`bcftools_stats`/`picard_hsmetrics`/`ngscheckmate`. The one deliberately-retained
   reserved port is `fastp` `adapter_fasta`.
2. **An arity mismatch is a compile error, not a silent divergence.** If the frontend advertises
   more output ports than the catalog `ProcessSpec` declares, the compiler's **output-drift guard**
   422s `POST /api/pipelines/compile` — which is exactly what happened when the Builder showed all
   five mosdepth outputs but `catalog.py` declared only two; declaring the three real mosdepth
   byproducts (`mosdepth_regions`/`mosdepth_global_dist`/`mosdepth_region_dist` — all products of the
   same `mosdepth --by … --thresholds` command) closed the drift and re-enabled Export-to-Nextflow of
   the default Builder view. The full promoted/removed/left-reserved model lives in
   [design/nextflow-codegen.md §The catalog](../design/nextflow-codegen.md#the-catalog-catalogpy) and
   [design/builder-cards/README.md §5](../design/builder-cards/README.md#5-open--todo--spec-vs-shipped-updated-2026-07-11).

## 1. Sample sheet → `Sample`

sarek `assets/schema_input.json` columns: `patient` (subject/individual, **required**),
`sample` (biological sample, **required**), `sex` (`XX|XY|NA`), `status` (`0`=normal /
`1`=tumor), `lane`, `fastq_1/2`, plus re-entry columns (`bam/cram`, `vcf`,
`variantcaller`, `contamination`). Row constraints: `required:[patient,sample]`,
`uniqueEntries:[patient,sample,lane]`. nf-schema validates via `nextflow_schema.json`
→ `assets/schema_input.json` (Draft-2020-12), each column carrying `type`/`format`/
`pattern`/`meta:[...]`/`errorMessage`.

- **ADOPT:** `patient` (= our `subject_key`), `sample`, `sex`, `status`, `lane`,
  `num_lanes` as typed `Sample` fields; adopt per-field `errorMessage` for intake validation.
- **DIVERGE:** nf-schema checks input *shape*; the gate also needs sample-sheet-vs-reality
  mismatch + missing-metadata detection. For germline panel, `status`≈always 0; `sex`
  is high-value (drives sex-chromosome coverage + swap checks).

## 2. The `meta` map

Channels carry `[meta, files]`; modules use `meta.id` for `tag`/`prefix`. **Only
`meta.id` and `meta.single_end` are nf-core-guaranteed keys** — everything else is
pipeline-local. sarek's meta adds `sample, patient, sex, status, lane, num_lanes`.

- **ADOPT:** model `Sample` as "the meta map, typed and persisted"; `meta.id` = join key.
- **DIVERGE:** do **not** parse `meta` at runtime assuming keys exist — reconstruct
  `Sample` from the **samplesheet + csv recap** (§6), which are stable contracts.

## 3. Version & provenance capture → `AnalysisRun` manifest

Per-process `versions.yml` (nested `{"proc": {tool: version}}`). Run-level
`pipeline_info/`: `software_versions.yml` (merged), `params_<ts>.json` (resolved config
— the full surface), `execution_trace_<ts>.txt` (per-task hash/status/exit/realtime/
peak_rss), `execution_report/timeline/dag`, `manifest_<ts>.bco.json` (BioCompute Object).

- **ADOPT — this is `AnalysisRun` almost verbatim:** `tool_versions` (from
  `software_versions.yml`), `params_hash` (from `params_<ts>.json`, for reproducibility
  diffing), `pipeline_name/version`, `nextflow_version`, `session_id`, git `commit`.
  **`execution_trace.txt` status/exit is a far better pipeline-failure signal than a
  log-substring scan** — **now built** (EXEC-001, `rules._check_execution_trace`): the
  structured trace drives the `PIPELINE` / operational-RERUN rules **alongside** the
  free-text log scan (PIPE-001), not in place of it (see Takeaway 4).
- **DIVERGE:** flatten the version map for **comparison** (`tool → version`) + keep
  `params_hash`, so we can diff "same reference/aligner/thresholds as the validated baseline?"

## 4. MultiQC → `MetricValue` + a metric registry

`multiqc_data/multiqc_data.json` keys: `report_general_stats_data` (`{sample: {metric:
value}}`), `report_saved_raw_data` (`{"multiqc_<module>": {sample: {metric: value}}}`),
**`report_data_sources`** (`{Module: {section: {sample: source_file}}}` — the provenance
bridge), `report_general_stats_headers`.

Concrete keys (module → key): **fastp** `after_filtering_q30_rate`,
`filtering_result_passed_filter_reads`, `pct_duplication`, `pct_surviving`, `pct_adapter`;
**FastQC** `percent_duplicates`, `percent_gc`, `total_sequences`; **mosdepth**
`median_coverage`, `mean_coverage`, `{N}_x_pc` (% ≥ N×); **Picard CollectHsMetrics
(panel — directly relevant)** `MEAN_TARGET_COVERAGE`, `PCT_TARGET_BASES_30X`,
`FOLD_ENRICHMENT`, `PCT_SELECTED_BASES`, `AT_DROPOUT`/`GC_DROPOUT`, `ZERO_CVG_TARGETS_PCT`;
MarkDuplicates `PERCENT_DUPLICATION`.

- **ADOPT:** `MetricValue(sample_id, metric_key, value, unit, module, source_file)`
  mirrors `report_general_stats_data`; `report_data_sources` populates `Evidence.source`
  + locator **for free** (real file pointer per metric).
- **DIVERGE — validates the registry decision (P6):** MultiQC keys are **version/module
  unstable** (e.g. fastp `after_filtering_q30_rate` reading zero, MultiQC issue #936). Pin
  a canonical registry `our_key → {module, json_key, source_file, unit}` rather than
  trusting General-Stats column names. This also replaces the fixed `QCMetrics` columns.
  **Now implemented** as [`metric_registry.yaml`](../../src/bayleaf/metrics/metric_registry.yaml)
  + a typed `MetricRegistry`, on the QC critical path (see [metric_registry.md](metric_registry.md)).
  **Update (gap-analysis WS-03/WS-06, 2026-07-12): real MultiQC/fastp/mosdepth parsing now
  exists** — [`src/bayleaf/ingest/nfcore.py`](../../src/bayleaf/ingest/nfcore.py)'s
  `ingest_results_dir()` parses a published nf-core `results/` dir straight into registry-keyed
  `SampleMetrics`, and `RunArtifacts.qc: list[QCMetrics | SampleMetrics]` (a transition Union) lets
  the gate consume either shape byte-identically — proven end-to-end against **real** HG002 output
  (`tests/test_ingest.py::test_real_nextflow_results_ingest_and_gate`, env-gated on a live run's
  `results/` dir). **Honest gap, unresolved:** this adapter is not yet what any *production* code
  path calls — `POST /api/runs` still drives `scripts/run_giab_pipeline.py`'s own bespoke
  `parse_fastp`/`parse_mosdepth` into the flat `QCMetrics` shape (via the frozen-five
  `qc_metrics.csv`); the two parsers are proven **equivalent** on the same real output, not yet
  **unified**. A `POST /api/runs/ingest` endpoint to call `ingest_results_dir` from outside stays
  deferred. See `CLAUDE.md` code map item 1g and
  [qc_metrics.md](qc_metrics.md#runbook-resolution--runbookset-ws-05-2026-07-12) for the sibling
  runbook-side work this landed beside.

## 5. `nextflow_schema.json` → `RunbookProfile` shape

Structure: `$schema` Draft-2020-12, params stay flat but grouped via `$defs` + `allOf`;
each param supports `type/default/description/enum/pattern/minimum/maximum/format/
fa_icon/help_text/hidden/errorMessage`. The one schema drives CLI validation, the web
launcher **form**, and `--help`.

- **ADOPT:** model `RunbookProfile` on this shape — grouped, typed, self-documenting
  thresholds → **auto-generated config forms** (React). Persist the
  resolved profile like `params_<ts>.json`; every `DecisionCard` cites its exact version.
- **DIVERGE:** JSON-Schema `minimum`/`maximum` is a hard boolean; the gate needs the
  **three-way HOLD/RERUN/PROCEED** (`gate`/`hard_fail`/`borderline_band`/`higher_is_better`).
  Borrow the envelope; keep gate keywords first-class.

## 6. sarek germline outputs → `ArtifactRef`

`csv/*.csv` recaps (`mapped.csv`, `markduplicates.csv`, `recalibrated.csv`,
`variantcalled.csv` — `patient,sample,...,path`) are machine-readable manifests. Reports:
`reports/{fastqc,fastp,mosdepth,markduplicates,samtools,bcftools,vcftools,ngscheckmate}/`.
Coverage → `mosdepth.summary.txt` (`total`/`total_region` row). **Contamination/identity:
sarek germline uses NGSCheckMate (`ngscheckmate_matched.txt`) for swap/relatedness +
sex-vs-coverage; GATK `CalculateContamination` (`*.contamination.table`) is somatic-only.**
Naming grammar: `<sample>.<caller>[.<stage>].<ext>`.

- **ADOPT:** parse the `csv/*.csv` recaps directly (not tree-globbing);
  `ArtifactRef(path, kind, sample_id, patient_id, caller, stage, checksum, size)` with
  `kind ∈ {fastq, recal_cram, recal_table, mosdepth_summary, fastp_json, markdup_metrics,
  samtools_stats, vcf, gvcf, filtered_vcf, joint_vcf, ngscheckmate, multiqc_json,
  versions_yml, params_json, execution_trace}`.
- **DIVERGE:** nf-core has **no artifact registry** (provenance implicit in paths) — add
  explicit `ArtifactRef` with `checksum`/`kind` so a `Finding` cites "computed from *this*
  file at *this* hash." Recaps list only primary files; parse `reports/` by naming grammar.

## Mapping summary

| bayleaf record | nf-core source of truth | Key fields |
|---|---|---|
| `Sample` | samplesheet cols + meta | `patient`(=subject_key), `sample`, `sex`, `status`, `lane`, `num_lanes` |
| `ArtifactRef` | `csv/*.csv` recaps + `reports/` grammar | `path`, `kind`, `sample_id`, `patient_id`, `caller`, `stage`, `checksum` |
| `MetricValue` | `multiqc_data.json` general-stats / raw-data / sources | `sample_id`, `metric_key`, `value`, `unit`, `module`, `source_file` |
| `AnalysisRun` manifest | `pipeline_info/` (versions, params, trace) | `pipeline_version`, `nextflow_version`, `params_hash`, `tool_versions`, `session_id`, `commit` |
| `RunbookProfile` | `nextflow_schema.json` `$defs`/keywords | grouped typed thresholds + `gate`/`hard_fail`/`borderline_band`/`higher_is_better` |

## Takeaways

1. Adopt vocabulary, not the validation *stance* (inputs vs outputs).
2. `Sample` ← samplesheet + csv recap, not the runtime meta map (only `id`/`single_end` guaranteed).
3. `MetricValue` mirrors `report_general_stats_data`, but **pin a canonical metric registry** (keys drift).
4. `AnalysisRun` is `pipeline_info/` typed; the structured `execution_trace.txt` status/exit check is **built** (EXEC-001, `rules._check_execution_trace`) and **complements** — does not replace — the free-text log-substring failure scan (PIPE-001): both coexist as preflight operational-failure checks.
5. `ArtifactRef` ingests the `csv/*.csv` recaps + adds `checksum`/`kind` for gate-grade provenance.
6. `RunbookProfile` borrows the form-generating schema shape but keeps the three-way gate keywords.
7. **Panel-specific:** prefer Picard **CollectHsMetrics** over WGS metrics; use **NGSCheckMate** + sex-vs-coverage as the germline contamination/mix-up signals (`CalculateContamination` is somatic-only in sarek).

Primary sources: [sarek usage](https://nf-co.re/sarek/latest/docs/usage) · [sarek output](https://nf-co.re/sarek/latest/docs/output) · [schema_input.json](https://github.com/nf-core/sarek/blob/master/assets/schema_input.json) · [nextflow_schema.json](https://github.com/nf-core/sarek/blob/master/nextflow_schema.json) · [meta-map](https://nf-co.re/docs/developing/components/meta-map) · [module guidelines](https://nf-co.re/docs/guidelines/components/modules) · [nf-schema spec](https://nextflow-io.github.io/nf-schema/latest/nextflow_schema/nextflow_schema_specification/) · [MultiQC reports](https://github.com/MultiQC/MultiQC/blob/main/docs/markdown/reports/reports.md) · [MultiQC scripts](https://docs.seqera.io/multiqc/usage/scripts)
