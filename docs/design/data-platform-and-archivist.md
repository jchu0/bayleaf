# Data Platform, Output Structure & the Archivist Agent

| Field | Value |
|---|---|
| **Status** | Draft — for maintainer review |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | all (contributors and Claude Code) |
| **Related** | [design/agents.md](agents.md) · [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) · [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md) · [ADR-0007](../adr/ADR-0007-ml-ready-structured-outputs.md) · [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md) · [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md) · [ADR-0015](../adr/ADR-0015-layered-data-contract.md) · [data/provenance.md](../data/provenance.md) · [data/schemas.md](../data/schemas.md) · [data/metric_registry.md](../data/metric_registry.md) · [planning/tasks.md](../planning/tasks.md) |

> **Draft for review.** Produced by a multi-agent design workflow (four design perspectives +
> three adversarial critiques — scope-realism, guardrails, over-engineering — then synthesized)
> and fact-checked against the code: `get_run_bundle`, the reserved `metric.parsed` /
> `artifact.ingested` event types, GET-only CORS, the `@lru_cache` on `_evaluate`, the five
> `.exists()`-gated ingest CSVs, and the `MetricValue.source_*` fields all verified present.
> Line numbers are approximate (some drifted after recent merges); **symbol references are
> verified**. Everything is tiered **(A) already built · (B) build now · (C) target-state** so
> nothing is rebuilt or over-built. Decisions to confirm are in *Open questions* at the end.

## Overview

This doc lets the maintainer review four coupled surfaces as one system: **(a)** the queryable data-platform + export design, **(b)** the analysis-output file-structure convention, **(c)** the dashboard run-browser / pagination / export UX, and **(d)** the Archivist agent (#3). It folds in three adversarial critiques (scope-realism, guardrails, over-engineering) and settles the contradictions between the four source sections.

Everything below is tagged by tier so nothing gets rebuilt and nothing gets over-built:

- **(A) ALREADY BUILT** — in the repo, tested, reused as-is. Do not re-design.
- **(B) BUILD NOW (MVP)** — the hackathon slice. `api/` + `frontend/` only; **zero `src/pipeguard/` change**; zero token spend; zero guardrail risk.
- **(C) TARGET-STATE** — documented, deferred. The durable, provenance-anchored production path.

**The one reframe that drives every scope call.** The "queryable data platform" is roughly 80% already built (event ledger → deterministic projector → `SqliteRepository`, plus `MetricValue`, the metric registry, and `get_run_bundle`). The judge-facing story — *query + export + ML-ready* — is servable **today from objects the API already holds in memory**, because `_evaluate(run_id)` (`api/main.py:72`, `@lru_cache`) returns full `DecisionCard`s carrying `metric_values`, `headline`, `rationale`, and `next_steps`. The durable event-sourced ML platform (persisting metrics into the ledger, DB-backed cross-run SQL) is real and valuable but is **(C)**, not the demo. Building the durable pipeline to move data the API already has in hand is the single biggest source of over-scope in the source sections, and two of them contradict each other on it — this doc resolves that in favor of the cheap, honest path.

Related: [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) (rules decide, AI advises), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md) (event ledger authoritative, DB a rebuildable projection), [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md), [ADR-0007](../adr/ADR-0007-ml-ready-structured-outputs.md) (ML-ready records), [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) (agent scoping/tiering), [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md), [ADR-0015](../adr/ADR-0015-layered-data-contract.md); [provenance.md](../data/provenance.md), [schemas.md](../data/schemas.md), [metric_registry.md](../data/metric_registry.md), [strategy.md](../data/strategy.md), [nf-core-conventions.md](../data/nf-core-conventions.md); task board [planning/tasks.md](../planning/tasks.md).

---

## 1. (A) Already built — reuse, do not re-design

The event→projection machinery and the ML-record shapes exist and are tested. Documenting them so no one re-proposes them:

1. **Event ledger (authoritative).** `EventLedger` (`provenance.py`) — append-only `list[ProvenanceEvent]`, optional JSONL persistence (one `model_dump_json()` line per event). When file-backed, the JSONL is the system of record ([ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md)).
2. **Deterministic projector → 5-table SQLite projection (rebuildable).** `project_events` (`persistence/projector.py`) is the *one* place events become rows, used by both the live path and `rebuild-db`, which is what makes the DB a pure function of the ledger. Tables: `runs`, `samples`, `findings`, `decision_cards`, `provenance_events` (`persistence/sqlite.py:38-99`).
3. **Repository port + adapter.** `Repository` (`persistence/repository.py`) with `SqliteRepository`; reads `list_runs`, `get_run`, `list_samples`, `list_findings`, `list_decision_cards`, `list_events`, and **`get_run_bundle(run_id) -> RunBundle`** (run + samples + findings + cards + full event trail in one hop). Today the only filter is `run_id`.
4. **First-class filter columns already exist.** `findings.gate/severity/rule_id/signature` and `decision_cards.verdict` are real SQL columns — "add query dimensions" overstates the gap; the *columns* are there, only read-method **filter params** and **populated data** are missing.
5. **The date spine already exists in the DB.** `runs.started_at` / `completed_at` are real columns (`records.py` `RunRow`). A run date is a *surfacing* gap on the API's `RunSummary`, not a data gap.
6. **Reserved event vocabulary already declared.** `EventType.METRIC_PARSED = "metric.parsed"` and `EventType.ARTIFACT_INGESTED = "artifact.ingested"` are already enum members (`provenance.py:31-32`), recorded verbatim in `provenance_events` and awaiting a projector rule. The durable path (§2.2) **reuses reserved vocabulary — it invents no new event type.**
7. **The ML-ready record already exists at runtime.** `MetricValue` (`models.py:331`, [ADR-0007](../adr/ADR-0007-ml-ready-structured-outputs.md)) is frozen, has a `content_hash` identity, and **snapshots `canonical_unit` + `metric_registry_version` inline** so each row is standalone-interpretable. It also already carries `source_artifact_id` / `source_field` / `source_locator` (the metric→artifact provenance link, currently unpopulated). It is built in `engine.py:146` (`metric_values_for`) and lives on `DecisionCard.metric_values` — **fully present in the in-memory cards the API already holds.** Its `content_hash` covers `sample_id + metric_key + analysis_run_id`, so it is a safe per-sample-per-metric identity.
8. **Metric registry** (`pipeguard.metrics`, [metric_registry.md](../data/metric_registry.md)) — the controlled vocabulary that normalizes raw tool numbers into `MetricValue`. Reused as-is.
9. **QC-triage agent (#1) — done.** `src/pipeguard/triage/` (advisory, off-path, off-by-default, Sonnet-tier, deterministic-stub fallback; [ADR-0009](../adr/ADR-0009-corpora-retrieval-upskilling.md)/[ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md)). This is the AI narration judges will actually see; the Archivist reuses its pattern.

**Honest one-liner:** the *schema and projection machinery are built*; what's missing is (i) data flowing into the DB on a running path, and (ii) filter params + a serializer on the read side. **(i) is not needed for the demo** — the in-memory cards already carry findings, verdicts, and metric values.

---

## 2. Queryable data platform + export

### 2.1 (B) BUILD NOW — read-only export over the cards the API already computes

This is the whole "query + export + ML-ready" judge story, from data already in hand, touching only `api/` + `frontend/`.

**a. One export endpoint, serialized from the in-memory `_evaluate` result** (not the lossy projection, not a live-wired DB):

```
GET /api/export?format=csv|jsonl&grain=decision|feature
    [&run_id=…  |  &since=…&before=…&verdict=…&q=…]
→ text/csv | application/x-ndjson
  Content-Disposition: attachment; filename="pipeguard-export-<scope>-<ts>.<ext>"
```

- `grain=decision` → one row per (run, sample): verdict + full narrative (`headline`/`rationale`/`next_steps`) + findings. This is **richer** than any DB export could be today, because those fields are dropped by the projection (`records.py:73-105`) but are present in memory.
- `grain=feature` → one `MetricValue` per line/row, `canonical_unit` + `metric_registry_version` inline = **the ML corpus**, in the long format [ADR-0007](../adr/ADR-0007-ml-ready-structured-outputs.md) designates (no pivot needed).
- GET-only, preserving the read-only CORS posture (`allow_methods=["GET"]`, `api/main.py:34`; [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md)/[ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md)).
- Formats: **stdlib `csv` + `json` only.** No `pyarrow`/Parquet, no `pandas`. Any consumer wanting a wide feature matrix pivots on their side.

**b. Honest-labeling of the export source (guardrail G-EXPORT-SOURCE).** This export is a **live deterministic re-derivation at export time**, not a read of a recorded decision. That is acceptable *because the gate is deterministic and we stamp its version pins*, but we must not claim it is ledger/projection-derived audit provenance. Every export row and its accompanying manifest header carry: `rule_pack_version`, `metric_registry_version`, `generated_by`, `origin`, and an export timestamp — self-describing and reproducible. Audit-grade, ledger-anchored export is (C) §2.2.

**c. Filter params on `/api/runs`, honored by an in-memory slice** (backward-compatible — the bare array still works):
- `verdict` — servable now from `RunSummary.counts` / `n_attention` (already present, `api/main.py:39-45`); honest semantics = "runs *containing* ≥1 card of this verdict."
- `q` — `run_id` substring.
- `since` / `before` — date bracket (needs the `started_at` surfacing in §4).
- No page envelope, no `limit`/`offset`, no cursor — dozens of runs; return the array, group client-side (§4).

**d. Guardrail requirements baked into the BUILD-NOW export:**
- **Origin travels with every row (G-ORIGIN).** Each export row + the manifest header carry the `origin` tag (`real-giab` | `synthetic` | `contrived`), sourced from a per-run marker/manifest in the run dir; default `unknown` and treated conservatively if absent. Data-handling guardrail 1.
- **Operator PII stripped (G-PII).** `submitted_by` is operator PII and has no business as an ML feature — **drop or hash it** in every export. `subject_id` is only exported for non-real origins (see G-DEID).
- **De-id gate on intake identity (G-DEID).** Persisting/exporting `subject_id`/`tissue` cohort keys is **restricted to public/synthetic/contrived origins until de-identification lands** (wishlist, not built). For the hackathon this is a non-issue in practice: the only "real" data is **GIAB HG002, a publicly consented reference genome — not PHI**; the gate is a forward-looking guardrail for when real *patient* runs are ingested.
- **Provenance-incomplete labeling (G-SOURCE).** Until `MetricValue.source_*` fields are populated, feature-export rows are labeled provenance-incomplete so downstream ML doesn't treat a `mean_coverage` as fully traceable to its `mosdepth.summary.txt`.
- **Single-tenant assumption stated (G-TENANT).** `/api/export` returns all matching runs to any caller; there is no authz/tenant scoping (multi-user is wishlist). Fine for the single-user demo — **stated so no one exposes it multi-tenant without adding authz.**
- **Don't close the ML loop into the gate (G-LOOP).** A model trained on the feature corpus to *predict* verdicts must never be wired back into the gate — that would be AI setting a verdict ([ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)). Noted in the corpus README.

### 2.2 (C) TARGET-STATE — the durable, emit-once persistence path

The production ML platform. Real and valuable; deferred. **Every piece is a projection of a new ledger event, never a direct DB write** ([ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md) §6), and the critical guardrail correction from the guardrails critique is folded in:

1. **Emit-once, idempotent write path — NOT wired into the API request.** The naive "inject `EventLedger(path=…)` into `_evaluate`" is **forbidden**: `_evaluate` is `@lru_cache` and re-runs `run_gate` live per request, so wiring durable writes there re-appends a full event trail on every cache miss/eviction/restart, corrupting the append-only ledger and double-counting on `rebuild-db`. Instead, a **dedicated one-shot gate-run/ingest command** writes the ledger exactly once (`actor="rule_engine"`), off the API path; the API and export **read the projection**. This single decision reconciles the export-source contradiction, keeps the ledger gate-owned, and preserves emit-once semantics.
2. **Persist QC metrics via `metric.parsed` (reserved type already exists).** Emit **one `metric.parsed` event per sample** carrying its `MetricValue` list (mirrors the card grain and the existing per-sample event pattern — not one event per metric), and extend `project_events` to fan it out into a new `metric_values` table. **PK = composite natural key `(run_id, sample_id, metric_key)`; keep `content_hash` as an indexed column** (matches the `FindingRow`/`CardRow` pattern; avoids making a value-derived hash the PK). Columns: the `MetricValue` fields + `origin` + standard `created_at`/`schema_version`. Index `(metric_key, normalized_value)` for threshold filters. This unblocks durable cross-run ML.
3. **Persist intake by widening `sample.registered` — do NOT mint a `sample.intake` event.** Same entity, same timing, same `(run_id, sample_id)` grain; a sibling event is pure duplication. Widen the payload with `subject_id`/`tissue`/`library_prep`/`submitted_by` (+ `index`/`index2`, `reads`/`pct_reads`) and add columns to `samples` (+ `origin`). `subject_id` becomes a cohort join key. Gated by G-DEID/G-PII above; the durable JSONL ledger path must be **gitignored / PHI-safe** if real intake ever lands.
4. **Persist `origin`** at ingest (its own field on `runs`/`samples`, via the event→projection path) so it survives into the DB, not just the export.
5. **Extend `Repository` filters** additively: `verdict`, `gate`, `severity`, `signature`, `started_at` range, and a metric predicate `(metric_key, op, value)`. Widens `_select` and the read methods; the port stays framework-agnostic ([ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md)).
6. **ML surface = long-format `MetricValue` JSONL**, one record per line (mirrors the ledger's one-record-per-line discipline). **No `v_ml_features` pivot VIEW** — SQLite has no `PIVOT`, a hand-maintained `CASE`/`MAX` view must be edited every time the registry grows, and it duplicates the export function. Consumers pivot in pandas/polars.
7. **Audit-grade export reads the projection/ledger** (not a live recompute). Accepts the projection's current lossiness, or later snapshots richer card content into a card-snapshot event.
8. **Parquet/columnar feature-store** — explicitly deferred ([ADR-0007](../adr/ADR-0007-ml-ready-structured-outputs.md) §Revisit).

### 2.3 Event-sourced invariants (load-bearing constraints)

1. **Event first → projector rule second → rebuildable third.** No new queryable column may be a direct DB write; `rebuild-db` must reconstruct it from the ledger, or the ledger stops being authoritative.
2. **Enriching the vocabulary is not retroactive.** Only runs recorded *after* `metric.parsed`/widened-intake events exist will have those rows; historical JSONL cannot be back-projected. `rebuild-db` will not conjure metrics for old runs.
3. **Export is a pure read consumer** — never writes the ledger or DB; any schema change bumps `schema_version` and is realized by deterministic re-projection, not a mutation of authoritative data.
4. **No agent writes the authoritative ledger** (see §5). ArtifactRef/export records go to a separate, explicitly non-authoritative store; if artifact registration is ever ledger-tracked, it is **deterministic core ingest** (`actor="system"`/`"rule_engine"`), never agent work.
5. **Confidence stays a heuristic** if ever added to export (life-science guardrail 2); today `MetricValue` and `decision_cards` carry none, so MVP export sidesteps it.

**Key files:** `src/pipeguard/engine.py:146` (emit `metric.parsed`), `src/pipeguard/provenance.py` (event already reserved), `src/pipeguard/persistence/{records,projector,sqlite,repository}.py` (new table + filters), `src/pipeguard/models.py:331` (`MetricValue`, reused), `api/main.py:72-116` (BUILD-NOW export endpoint; TARGET-STATE repo read).

---

## 3. Analysis-output file-structure convention (expanded)

*Scope: a single germline DNA **panel** run (nf-core/sarek vocabulary), sized for an M4 Mac Mini / 32 GB — panel slices, not WGS. This expands §3; it is **additive** and changes no producing script. The deterministic gate's flat `run/` five-CSV ingest contract is **frozen**. See [nf-core-conventions.md](../data/nf-core-conventions.md), [strategy.md](../data/strategy.md).*

### 3.0 How to read this section — three tiers

Every artifact/name below is tagged with one tier so the doc doubles as a "what is real vs. aspirational" map:

- **(A) Already-on-disk** — a path the scripts produce or consume **today**; frozen, verbatim.
- **(B) Build-now** — **documentation only**; zero producing-script changes; the gate contract stays byte-for-byte.
- **(C) Target-state** — future; **nothing here is a hackathon task**. Each item lands *only in the same diff that changes its producing script*, and names not grounded in-repo are tagged `(VERIFY)`.

The single fact that makes the whole tiering safe: the gate opens **only** the five flat `run/` CSVs (`parsers.py:187-217`), so *any* storage/naming/CRAM/grouping decision in tier C is verdict-safe and therefore non-urgent (§3.6).

### 3.1 The one idea: two tiers of on-disk state (unchanged)

1. **The per-tool output tree** — the natural NGS artifact layout (`fastq → fastp → BAM → mosdepth → variants`). Rich, tool-shaped. The **shared substrate** the agent/archivist layer *observes*.
2. **The gate run-dir (`run/`)** — a **flat directory of exact-named CSVs** `load_run` ingests; a *derived, lossy projection* of tier 1 via a deterministic flatten step (`scripts/gate_giab.py:186-205` `write_run_dir`).

**Invariant:** the gate's deterministic critical path reads **only tier 2**. Agents read **both tiers and write into neither** in a way that changes a verdict.

### 3.2 (A) Already on disk — the real flat GIAB layout

Everything lands under git-ignored `data/real-giab/` (origin `real-giab`), produced/consumed by `scripts/gate_giab.py` + `scripts/fetch_giab_hg002.py`. **On-disk directory names are `fastq/`, `mosdepth/`, `run/`** (+ top-level `.bam`/`.vcf.gz`) — these are frozen and are **not** renamed (see §3.5 and §3 note: no relabel to `reads/`/`alignment/`/`coverage/`). All filenames below are quoted verbatim from the scripts (no `(VERIFY)` needed).

```
data/real-giab/                                             # (A) git-ignored; origin real-giab
├── HG002.GRCh38.panel.bam                                  # (A) NIST novoalign BAM, region-sliced to panel BED  [INDEX-ONLY]
├── HG002.GRCh38.panel.bam.bai                              # (A) index (travels with the BAM)
├── HG002_GRCh38_1_22_v4.2.1_benchmark.panel.vcf.gz         # (A) panel-restricted NIST TRUTH VCF = answer key (input, not run output)  [INDEX-ONLY]
├── HG002_GRCh38_1_22_v4.2.1_benchmark.panel.vcf.gz.tbi     # (A) tabix index
│
├── fastq/                                                  # (A) — kept verbatim
│   ├── HG002.R1.fastq.gz                                   # (A) raw reads — read-EXTRACTED from the BAM (samtools collate|fastq), not a demux  [INDEX-ONLY]
│   ├── HG002.R2.fastq.gz                                   # (A)
│   ├── HG002.R1.trim.fastq.gz                              # (A) fastp-trimmed  [INDEX-ONLY]
│   ├── HG002.R2.trim.fastq.gz                              # (A)
│   ├── HG002.fastp.json                                    # (A) FLATTEN-INPUT → q30 / pct_reads_identified / dup_rate
│   └── HG002.fastp.html                                    # (A) human report — produced-but-unread  [INDEX-ONLY]
│
├── mosdepth/                                               # (A) — kept verbatim
│   ├── HG002.panel.mosdepth.summary.txt                    # (A) FLATTEN-INPUT → mean_coverage (see §3.3 for exact column)
│   ├── HG002.panel.thresholds.bed.gz                       # (A) FLATTEN-INPUT → breadth ≥20x / ≥30x
│   ├── HG002.panel.thresholds.bed.gz.csi                   # (A) mosdepth index
│   ├── HG002.panel.mosdepth.global.dist.txt               # (A) produced-but-unread  [INDEX-ONLY]
│   ├── HG002.panel.mosdepth.region.dist.txt               # (A) produced-but-unread  [INDEX-ONLY]
│   ├── HG002.panel.regions.bed.gz                          # (A) produced-but-unread  [INDEX-ONLY]
│   └── HG002.panel.regions.bed.gz.csi                      # (A)
│                                                           #     (--no-per-base suppresses *.per-base.bed.gz)
└── run/                                                    # (A) TIER 2 — the ONLY thing the gate core opens
    ├── qc_metrics.csv                                      # (A) GATE-READ  → parse_qc_metrics
    ├── SampleSheet.csv                                     # (A) GATE-READ  → parse_sample_sheet
    └── sample_metadata.csv                                 # (A) GATE-READ  → parse_sample_metadata
    #   demux_stats.csv, pipeline.log — OPTIONAL, read-if-present by load_run; NOT written by our script today
```

**Fetched whole-genome originals** (also `real-giab`, pulled by `fetch_giab_hg002.py`, may be cached on disk; the 122 GB reads-BAM is **never** stored whole — only its `.bai` is fetched, md5-enforced): `HG002.GRCh38.2x250.bam.bai`, `HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz` + `.tbi`, `HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed` (whole-genome high-confidence BED — faithfulness claims valid only inside it).

**Confirmed value:** `run/qc_metrics.csv` first row = `HG002,88.22,99.31,55.8,0.0057,` for columns `sample_id,q30,pct_reads_identified,mean_coverage,dup_rate,cluster_pf` (mosdepth `total_region` mean `55.76` → `55.8`; `cluster_pf` deliberately blank — a run-level SAV/InterOp metric, not read-derivable).

### 3.3 Ingest mapping — artifact → disposition (frozen)

Three dispositions: **GATE-READ** = opened by `load_run` (always a tier-2 flat `run/` CSV); **FLATTEN-INPUT** = opened *once, upstream, off the gate path* by the derivation step and reduced into a `run/` CSV; **INDEX-ONLY** = opened by no code path (an archivist would only register a pointer + checksum). Only the GATE-READ row is on the deterministic critical path.

| Artifact (verbatim) | Producing tool | Disposition | Reaches the gate via |
|---|---|---|---|
| `run/qc_metrics.csv` | `write_run_dir` (flatten) | **GATE-READ** | `parse_qc_metrics` — `sample_id,q30,pct_reads_identified,mean_coverage,dup_rate,cluster_pf` |
| `run/SampleSheet.csv` | `write_run_dir` | **GATE-READ** | `parse_sample_sheet` — `[BCLConvert_Data]`/`[Data]` |
| `run/sample_metadata.csv` | `write_run_dir` | **GATE-READ** | `parse_sample_metadata` — `subject_id/tissue/library_prep/submitted_by` |
| `run/demux_stats.csv`, `run/pipeline.log` | (optional) | **GATE-READ if present** | `parse_demux_stats` / `parse_log` (`.exists()`-gated; not written by our script) |
| `fastq/HG002.fastp.json` | fastp | **FLATTEN-INPUT** | `parse_fastp` → `q30`, `pct_reads_identified`, `dup_rate` |
| `mosdepth/HG002.panel.mosdepth.summary.txt` | mosdepth | **FLATTEN-INPUT** | `parse_coverage` → `mean_coverage` |
| `mosdepth/HG002.panel.thresholds.bed.gz` | mosdepth | **FLATTEN-INPUT** | breadth ≥20x / ≥30x (registry metrics) |
| `HG002.GRCh38.panel.bam` (+ `.bai`) | samtools view/index | **INDEX-ONLY** | — never opened by the core |
| `…benchmark.panel.vcf.gz` (+ `.tbi`) | bcftools view + tabix | **INDEX-ONLY** | — answer key; never opened by the core |
| `fastq/*.fastq.gz`, `fastq/*.fastp.html`, mosdepth `*.dist.txt` / `*.regions.bed.gz` | samtools/fastp/mosdepth | **INDEX-ONLY** | — produced-but-unread |

**The flatten-step contract (frozen).** `gate_giab.py` (`run_fastp`/`run_mosdepth` → `parse_fastp`/`parse_coverage` → `write_run_dir`, lines ~186-205) reads the tool outputs once, upstream, and reduces them to `run/qc_metrics.csv`. Field derivations (all normalized to the runbook percent/rate convention):

1. `q30` ← fastp `summary.after_filtering.q30_rate` ×100.
2. `pct_reads_identified` ← fastp `filtering_result.passed_filter_reads ÷ summary.before_filtering.total_reads` ×100. **Accuracy caveat:** this is a fastp *pass-filter* (quality) rate on already-demuxed reads — **not** an Illumina barcode-identification/"reads assigned to a known barcode" metric, which is what the column name conventionally implies. The true run-level Illumina metric (`cluster_pf`) sits blank right beside it. Document the column's actual semantics; do not read it as demux barcode-assignment.
3. `dup_rate` ← fastp `duplication.rate` ×100.
4. `mean_coverage` ← mosdepth `*.mosdepth.summary.txt`, `total_region` row, the **`mean` column = 4th field (`fields[3]`, 0-indexed)**. (Not the 3rd 1-based column, which is `bases`, a raw base count in the billions — the code indexes 0-based.)
5. `cluster_pf` ← left blank (run-level SAV/InterOp, not read-derivable).

Breadth uses `thresholds.bed.gz` columns **`c[6]` = ≥20X** and **`c[7]` = ≥30X** (0-indexed; header `#chrom start end region 1X 10X 20X 30X`), summed over windows ÷ panel length.

### 3.4 (B) Build now — documentation only

**No build work.** Freeze and record the flat `run/` contract (this section) against the real GIAB slice. Change **no** producing script: keep emitting exactly `data/real-giab/{fastq/, mosdepth/, run/}`, top-level `HG002.GRCh38.panel.bam(.bai)`, and `…benchmark.panel.vcf.gz(.tbi)`. Zero renames, zero moves. The gate keeps running against `run/`, byte-for-byte. Everything in §3.5 is parked, not built.

### 3.5 (C) Target-state — grouped per-run tree, storage seams, findability

**None of this is built or scheduled.** It is documented so the *same convention* survives being pointed at a real sarek / exome / WGS run. Each line lands only with its producing-script change; ungrounded names carry `(VERIFY)`.

**3.5.1 A grouped per-run tree (illustrative; keeps the current subdir names).** A per-run root would key on the `analysis_run` UUIDv7. It reuses `fastq/`, `mosdepth/`, `run/` verbatim (no relabel), adds a `benchmark/` grouping for the answer key (a *conceptual* reclassification — the truth VCF is input, not run output), and reserves slots for stages **we do not run**. Per GROUND, `nf-core-conventions.md` documents only `pipeline_info/`, `multiqc/` (`multiqc_data/`), `csv/`, and `reports/{fastqc,fastp,mosdepth,markduplicates,samtools,bcftools,vcftools,ngscheckmate}/`; `preprocessing/` and `variant_calling/` are **not** grounded in-repo, so they are `(VERIFY)`.

```
data/runs/<run_id>/                                         # (C) per-run root = analysis_run UUIDv7  [DEFER — demo is one run/one sample]
├── run/                                                    # (A-shape) TIER 2 — unchanged, still the ONLY thing the gate opens
│   ├── qc_metrics.csv                                      #     (five-CSV contract frozen; only the parent dir would move)
│   ├── SampleSheet.csv
│   └── sample_metadata.csv
├── fastq/                                                  # (A-name kept) reads + fastp — verbatim, NOT renamed to reads/
│   ├── HG002.R{1,2}.fastq.gz
│   ├── HG002.R{1,2}.trim.fastq.gz
│   ├── HG002.fastp.json
│   └── HG002.fastp.html
├── mosdepth/                                               # (A-name kept) coverage evidence — verbatim, NOT renamed to reports/mosdepth/ or coverage/
│   ├── HG002.panel.mosdepth.summary.txt
│   └── HG002.panel.thresholds.bed.gz (+ .csi)
├── HG002.GRCh38.panel.bam (+ .bam.bai)                     # (A) alignment slice  [→ .cram/.crai once M5-verified — DEFER, §3.5.2]
├── benchmark/                                              # (C) the ANSWER KEY (origin real-giab) — NOT an output of this run
│   ├── HG002_GRCh38_1_22_v4.2.1_benchmark.panel.vcf.gz (+ .tbi)
│   └── HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed
├── variant_calling/(VERIFY)  <caller>/HG002/               # (C)(VERIFY) sarek-plausible, ungrounded — EMPTY in our runs (we run no caller)
│   └── … <sample>.<caller>.vcf.gz / .g.vcf.gz / .filtered.vcf.gz (+ .tbi)   # illustrative only; home is an OPEN decision
├── pipeline_info/                                          # (C) grounded sarek name — software_versions.yml, params_<ts>.json, execution_trace_<ts>.txt
├── multiqc/                                                # (C) grounded sarek name — multiqc_report.html, multiqc_data/multiqc_data.json
├── csv/                                                    # (C) grounded sarek name — variantcalled.csv (patient,sample,…,path)
└── MANIFEST.sha256                                         # (C) one checksum+origin+kind line per artifact (§3.5.3) — DEFER
```

Two class-name decisions that deliberately do **not** fight sarek or the current code:

1. **No `reads/`, no `coverage/`, no `reports/mosdepth/` rename.** Renaming `fastq/`→`reads/` invents a *third* name matching neither the code nor sarek; `mosdepth/`→`reports/mosdepth/` is cosmetic sarek-alignment for a pipeline we never run. Both are **cut** (not merely deferred). Keep `fastq/`, `mosdepth/` verbatim.
2. **The truth VCF is `benchmark/`, not `variant_calling/`.** Our only VCF is the NIST answer key; filing it under `variant_calling/` would misrepresent provenance. `variant_calling/` stays reserved for a real run's *called* output and is **empty in our runs**.

**3.5.2 Storage seams (all DEFER).** BAM→CRAM, FASTQ drop-policy, VCF/gVCF handling — see the storage recommendation. On the M4/panel nothing needs reclaiming; these are scale seams for exome/WGS, each a future-note, none a task.

**3.5.3 Findability (all DEFER).** (a) A unified naming grammar `{sample}.{assay}.{build}.{stage}[.{tool-native}].{ext}` extending sarek's `<sample>.<caller>[.<stage>].<ext>` — a rename touching every producing function, deferred; today's glob (`mosdepth/HG002.panel*.summary.txt`) already suffices. (b) An **ArtifactRef registry** (one row per artifact: `run_id, sample_id, kind, path, sha256, origin, …`; `kind` from the 18-value enum in `nf-core-conventions.md` §6) that turns "where is HG002's filtered VCF?" into one lookup — **unimplemented / target-state**, a rebuildable projection off the event ledger (ADR-0002/0003), off the critical path. (c) `MANIFEST.sha256` over all derived artifacts as its source rows. All three are the librarian layer that would stop "that one VCF" getting lost in a sea of objects; none is built.

**3.5.4 The deferred variant-calling ingest branch (CUT for now).** A real run that produced a call set could add one FLATTEN-INPUT (`bcftools stats` text → a `parse_vcf_stats` analog appending `ts_tv_ratio`/`n_variants`/`het_hom_ratio` columns to the *existing* `qc_metrics.csv`, entered through the metric registry like every current metric). **This is cut, not built:** we run **no caller** (GROUND), so there is no run-produced VCF to stat — the only VCF on disk is the NIST *answer key*, and statting it into `qc_metrics.csv` would mislabel answer-key properties as run QC and wire illustrative thresholds over metrics with no real demo data. Wire it *only if/when* a real caller is added, in the same diff.

### 3.6 Invariant restated — the gate never opens the big binaries

1. `load_run` opens exactly the five `run/` files (`parsers.py:187-217`); **no BAM/CRAM/VCF/`.bed.gz` handle exists anywhere in `parsers.py`**. The heavy `mosdepth`/`fastp` reads happen once, upstream, in `gate_giab.py`, off the gate path, and are flattened into `run/qc_metrics.csv`.
2. Everything in §3.5 is read only by the archivist/UI/agents for indexing/display/provenance — the tier-1 substrate the agent layer observes but never writes into in a way that changes a verdict.
3. **Therefore the whole tier-C design is verdict-safe:** relocating to a per-run root, converting BAM→CRAM, dropping regenerable FASTQ, or renaming files **cannot move a verdict**, because no core code path opens those files. The only rename that even touches the gate is the `run/` *parent-dir* move, and it leaves the CSV contents and filenames untouched.

---

## 4. Dashboard run-browser / pagination / export UX

*All work lands in `api/` + `frontend/`; `src/pipeguard/` untouched. Baseline: the only browse surface is `RunOverview` at `/`, one eager unparameterized `api.runs()` into a flat card grid; `Monitoring`/`ReviewQueue`/`Intake` go further and `Promise.all` full `RunDetail` for every run on mount.*

### 4.1 (B) BUILD NOW

1. **New `/runs` `RunsBrowser` screen.** Replaces the flat `runs.map(...)` grid; demote `/` to a compact recent-activity view or redirect to `/runs`.
2. **Add `started_at` to `RunSummary`** (absent today, `api/main.py:39-45`), **sourced from the run-dir filesystem mtime** (or parsed from `run_id` if dated) — unblocks month bucketing and date filter with **no persistence**.
3. **Default view = current calendar month, client-side.** Fetch the summary array once (cheap at dozens of runs), render the current month under a month header, reveal earlier months from data already in hand. This realizes the "lazy-load by calendar month, show more only on query/filter" ask **without** server pagination.
4. **Filter bar**, tiered by what the data supports today:
   - **Verdict / attention** — servable now from `RunSummary.counts`/`n_attention`.
   - **`run_id` substring search** — cheap from run-dir enumeration.
   - **Date/month** — from the new `started_at`.
   - **Metric-threshold and subject/sample filters** — shown as **disabled "coming soon" facets**, not faked (they need persisted metrics / rich `samples` — see §2.2, §5).
5. **Export UI.** Per-run "Export" on `RunDetail`/each card, and "Export all matching filters" on `RunsBrowser` (batch = the current filter query with `format=` appended). Both hit the §2.1 endpoint. Client download is a ~10-line `URL.createObjectURL` + `<a download>` helper — **no `file-saver` dependency** (the frontend has no download code today).

### 4.2 (C) TARGET-STATE

1. **Server-side keyset pagination** on `(started_at, run_id)` backed by `Repository.list_runs()` predicates; the page-envelope seam makes the client swap internal. Only earns its complexity at thousands of runs.
2. **Rebind the N+1 aggregation screens** (`Monitoring`/`ReviewQueue`/`Intake`) to the windowed `/api/runs` (default current month) instead of `Promise.all` over every run. **Left for target-state** to keep the guaranteed-working demo path untouched.
3. **List virtualization** — only once a single month holds hundreds of runs. Explicitly **not** for the demo (pure risk, zero payoff at dozens of cards).
4. **Metric-threshold + subject/sample filters** come online with the metric-persistence path and richer projected columns.

### 4.3 Honest scale framing

The run *list* is not the demo's scaling problem — the eager full-detail fan-out is. The right MVP move is month-bucketing over the already-fetched array; do **not** build cursor pagination, page envelopes, "load older" paging controls, or virtualization for a few-dozen-run demo.

---

## 5. The Archivist agent (#3) — design-now / build-later

*Specced strictly within the existing agent model — advisory, off-path, off-by-default, stub-first — mirroring the QC-triage agent (`src/pipeguard/triage/`). See the standalone roster block for the drop-in version; this section carries the rationale and the guardrail proof.*

### 5.1 Scope

The Archivist is the **librarian over the data platform and the output tree**: it indexes, organizes, summarizes, tags, and prepares exports of run / QC / sample-sheet data *across* runs. It is a **reader over the two surfaces the rules pipeline ignores** — the run-dir output tree at the ingest boundary, and the ledger/projection + cards at the completion boundary. It never enters `load_run → evaluate_run`.

### 5.2 Hard boundaries — provably unable to influence a decision (load-bearing)

These are the invariants from [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)/[ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md)/[ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md)/[ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md). Violating any one voids the design.

**MUST NOT:**
1. **Never set, change, restate, or *influence* a verdict, confidence, or finding** — including by ordering/highlighting a selection so it reads as a gate recommendation. Enforced structurally: `ArchiveNote` pins `advisory: Literal[True] = True` and has **no verdict/decision/confidence field** (mirrors `TriageNote`, `triage/models.py:92`).
2. **Never sit on the deterministic critical path** — never invoked inside `run_gate`/`load_run`/`evaluate_run`; its failure can never drop, delay, or alter a verdict.
3. **Never mutate the authoritative event ledger or source records** ([ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md)). It writes **only** to a separate, non-authoritative export/index/manifest location. **This resolves the contradiction** between the two source sections: the earlier suggestion that the archivist emit `ArtifactRef` registration events into the ledger is **rejected** — if artifact registration must be ledger-tracked it is a **deterministic core ingest step** (`actor="system"`), not agent work. The `export.emitted` reserved event is **dropped**; a plain manifest file keeps the ledger gate-owned.
4. **Never fabricate or re-derive QC numbers.** It exports what was persisted; where the store is lossy it exports the gap honestly (no backfilling, no invented metric or pathogenicity, no synthesized verdict).
5. **Never become the system of record;** its exports are downstream, disposable copies.
6. **Never require the LLM to function.** The deterministic stub fully produces index + export; the LLM only phrases summaries ([ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md) L30 analog: a missing narrative is acceptable UX; a missing export manifest is not).
7. **LLM least-privilege (G-PII/G-DEID).** The summary layer sees **only de-identified aggregates/counts** — raw `subject_id`/`tissue`/`submitted_by` never enter a prompt ([ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) least-privilege).
8. **NL→filter never silently applied.** Any natural-language→filter convenience must **echo the executed predicate verbatim and cite the exact record ids** the summary covers, so a mis-parsed scope can't render as authoritative fact.

**MAY:** read the projection through the `Repository` port and the file-backed JSONL (read-only); register `ArtifactRef` pointers + checksums to a non-authoritative index; index/roll up deterministically; summarize in prose fully traceable to the records; tag organizational metadata as a separate layer; select + assemble exports (CSV/JSONL + manifest) with `content_hash`/`schema_version`/origin/citations preserved and confidence labeled a heuristic.

### 5.3 Shape — deterministic module first, agent scaffold deferred

1. **The near-term deliverable is the deterministic substrate, and it is a data-platform task, not an agent task** — and **it is exactly the §2.1 export endpoint under a plainer name**. Do not stand up an `ArchivistAgent`/`StubArchivistAgent`/`ClaudeArchivistAgent`/env-tier/`ArchiveNote`/`ExportManifest` package for the hackathon.
2. **Do not add an archivist-owned `query.py`** — the "retriever-analog" is the extended `Repository` port itself; a bespoke query layer duplicates it.
3. **Do not build a `knowledge/` corpus or a `Retriever`.** The triage `Retriever` grounds *prose* in curated text; the Archivist grounds in the *typed, queryable store*. Its "retrieval" is `Repository.list_*(filters)`. If export READMEs later need glossary text, pull from [metric_registry.md](../data/metric_registry.md) / [schemas.md](../data/schemas.md), not a new corpus.
4. **When the LLM layer is eventually built**, it mirrors the triage triad verbatim (lazy `import anthropic`, `self._fallback = StubArchivistAgent(...)`, every degradation path — refusal / empty text / blanket `except` — returns the stub) and phrases **only** digests/READMEs over deterministically-computed numbers. Model tier: cheapest (Haiku, per [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) — an organizing task, not diagnosis), off by default behind `PIPEGUARD_ARCHIVIST_AGENT=stub|claude`.

### 5.4 Triggers, roster, structure

1. **Batch / on-demand only**, over an already-populated store — never per-sample, never on the critical path. Invoked as a standalone entry point (the `triage_card()` analog) via CLI and/or a read-only `GET` endpoint mirroring the triage endpoint's advisory posture (`api/main.py:113-124`), like the notifier (`notify/`, [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md)).
2. **Roster: genuine agent #3, behind #2.** #1 QC-triage **done**; #2 pipeline-repair **planned/deferred** (Opus-tier, needs `pipeline_info/execution_trace` capture that doesn't exist). The Archivist is a data-platform convenience over already-decided runs — spec now, build after the durable substrate and #2.
3. **Structure follows the `triage/` precedent** — a top-level package, **not** an `agents/` folder. The `agents/<scope>/` restructure (T-026, [planning/tasks.md](../planning/tasks.md)) is deferred until agent #2 lands; keep `synthesis/` (narration) and `notify/` (port) out of the agent bucket.

---

## 6. Cross-cutting guardrail register

For quick review, the guardrail requirements that survived and their homes:

| ID | Requirement | Where enforced |
|---|---|---|
| G-EXPORT-SOURCE | BUILD-NOW export is a labeled live re-derivation, version-stamped; audit export reads the projection | §2.1b, §2.2.7 |
| G-IDEMPOTENT | Durable writes are emit-once via a one-shot command, never in the `@lru_cache` API path | §2.2.1 |
| G-NO-AGENT-LEDGER | No agent writes the authoritative ledger; ArtifactRef reg is deterministic core | §2.3.4, §5.2.3 |
| G-ORIGIN | `origin` on every metric/sample row + manifest | §2.1d, §2.2.2-4 |
| G-PII / G-DEID | Drop/hash `submitted_by`; intake identity gated to non-real origins until de-id; PHI-safe ledger path | §2.1d, §2.2.3, §5.2.7 |
| G-SOURCE | Feature rows labeled provenance-incomplete until `MetricValue.source_*` populated | §2.1d |
| G-TENANT | Single-tenant assumption stated; no authz on `/api/export` | §2.1d |
| G-LOOP | Verdict-prediction models never wired back into the gate | §2.1d |
| G-ADVISORY | Archivist `advisory=True`, no decision field, off-path, stub-fallback, LLM sees de-id aggregates only | §5.2 |

---

## 7. Bottom line

Keep this as the target-state spec, but for the hackathon **build exactly one thing**: a read-only `GET /api/export` over the cards the API already holds, with a month-scoped `RunsBrowser`, a filter bar, and a download button. That is the entire *query + export + ML-ready* story, demoable this session, at a small fraction of the proposed surface — and it is the exact deterministic seam the durable persistence and the Archivist would both have grown into, so it is not throwaway.

---

## Appendix A — Archivist agent: drop-in roster block

*The standalone spec §5 refers to — ready to lift into [agents.md](agents.md) when the agent is built.*

ARCHIVIST AGENT (#3) — drop-in roster block for docs/design/agents.md

STATUS: design-now / build-later. Spec now; build the deterministic export/index substrate first (it is the same code as the BUILD-NOW `/api/export` endpoint); attach the off-by-default LLM narration last, only once a populated store exists. Priority: behind #1 QC-triage (done) and #2 pipeline-repair (planned/deferred).

SCOPE: the librarian over the data platform and output tree. Reads across the ledger/projection + cards (completion boundary) and, later, the run-dir output tree (ingest boundary) — the two surfaces the rules pipeline ignores. It indexes/rolls up runs, samples, findings, cards, and events (by month/verdict/gate/signature/origin); registers output-tree `ArtifactRef` pointers+checksums to a NON-authoritative index; tags organizational metadata as a separate layer; and prepares CSV/JSONL exports + a manifest (the ML-ready `MetricValue` corpus + the per-run/batch export the frontend lacks). It never enters `load_run → evaluate_run`.

HARD BOUNDARIES — provably unable to influence a decision (ADR-0001/0002/0006/0012); any one violation voids the design:
1. Never set/change/restate/influence a verdict, confidence, or finding — including via ordering/highlighting a selection as a recommendation. Structural: `ArchiveNote` pins `advisory: Literal[True] = True` with NO verdict/decision/confidence field (mirrors `TriageNote`, triage/models.py:92).
2. Never on the deterministic critical path — never invoked inside run_gate/load_run/evaluate_run; its failure can never drop/delay/alter a verdict.
3. Never mutate the authoritative ledger or source records — writes ONLY to a separate non-authoritative export/index/manifest store. No `export.emitted` event; a manifest file keeps the ledger gate-owned. If artifact registration must be ledger-tracked, it is a deterministic CORE ingest step (actor="system"), never agent work.
4. Never fabricate/re-derive QC numbers — exports what was persisted; exports lossy gaps honestly (no backfill, no invented metric/pathogenicity/verdict).
5. Never become the system of record; exports are disposable downstream copies.
6. Never require the LLM — the deterministic stub fully produces index+export; the LLM only phrases summaries.
7. LLM least-privilege — summary layer sees only de-identified aggregates/counts; raw subject_id/tissue/submitted_by never enter a prompt.
8. NL→filter never silently applied — echo the executed predicate verbatim and cite the exact record ids covered.

MAY: read the Repository port + JSONL (read-only); register ArtifactRef pointers to a non-authoritative index; deterministically index/aggregate; summarize traceable prose; tag metadata; assemble CSV/JSONL exports + manifest with content_hash/schema_version/origin/citations preserved and confidence labeled a heuristic.

SHAPE: for the hackathon it is a PLAIN DETERMINISTIC module — `index(repo, filters)` + `export(rows, format)` over the extended `Repository` port, stdlib csv+json only. Do NOT stand up ArchivistAgent/StubArchivistAgent/ClaudeArchivistAgent/env-tier, `ArchiveNote`/`ExportManifest`/`query.py`, or a `knowledge/` corpus (its "retrieval" IS `Repository.list_*(filters)`; grounding is the typed store, not curated text). When the LLM layer is eventually added, mirror the triage triad verbatim (lazy `import anthropic`, `self._fallback = StubArchivistAgent(...)`, every degradation path returns the stub).

TRIGGERS: batch/on-demand only over a populated store; standalone entry point (the `triage_card()` analog) via CLI and/or a read-only GET endpoint mirroring api/main.py:113-124; runs strictly after gate completion, like notify/.

MODEL TIER: cheapest (Haiku), env `PIPEGUARD_ARCHIVIST_MODEL`; off by default behind `PIPEGUARD_ARCHIVIST_AGENT=stub|claude` (default stub) — an organizing task, not diagnosis (ADR-0012).

ROSTER PLACEMENT: genuine agent #3, behind #2. Follows the top-level `triage/` package precedent, NOT an `agents/` folder — the agents/<scope>/ restructure (T-026) is deferred until #2 lands; keep synthesis/ and notify/ out of the agent bucket.

---

## Appendix B — Phasing at a glance

SINGLE HIGHEST-LEVERAGE SLICE TO BUILD FIRST: `GET /api/export` serializing the in-memory `_evaluate` cards — `grain=decision` (CSV, full narrative + findings) and `grain=feature` (JSONL, one `MetricValue`/line with `canonical_unit`+`metric_registry_version` inline = the ML corpus). It makes all three judge asks (query, export, ML-ready) real simultaneously from data the API already computes; touches only `api/`+`frontend/`; zero `src/pipeguard/` change; zero persistence wiring; zero token spend; zero guardrail risk.

BUILD-NOW (this session; `api/`+`frontend/` only):
1. The export endpoint above, version-stamped and origin/PII-guarded (§2.1). [highest leverage]
2. `started_at` on `RunSummary` from run-dir mtime — unblocks month bucketing with no persistence.
3. Optional in-memory filter params on `/api/runs` (`verdict` from counts, `q` run_id substring, `since`/`before`) — backward-compatible; bare array still works.
4. `/runs` `RunsBrowser`: fetch summary array once, month-bucket client-side, filter bar, per-run + batch Export buttons, ~10-line `createObjectURL`/`<a download>` helper. Metric-threshold + subject/sample facets shown disabled ("coming soon").

NEAR-TERM (after the demo; the durable ML substrate, in dependency order):
5. One-shot emit-once gate-run/ingest command that writes the JSONL ledger once and builds the projection — NOT wired into the `@lru_cache` API path (the ledger-corruption fix).
6. `metric.parsed` per-sample event (reserved type already exists) → projector fan-out to a `metric_values` table, PK `(run_id, sample_id, metric_key)` + `content_hash` column + `origin`.
7. Widen `sample.registered` payload (NOT a new `sample.intake` event) → enriched `samples` projection with `subject_id`/intake + `origin`.
8. Additive `Repository` filter predicates (verdict/gate/severity/signature/date/metric); audit-grade export reads the projection; long-format `MetricValue` JSONL as the ML surface.

DEFER (documented target-state, do not build under deadline):
9. Server-side keyset/cursor pagination + page envelope; list virtualization; rebinding the N+1 `Monitoring`/`ReviewQueue`/`Intake` screens.
10. `ArtifactRef` registry + `pipeline_info`/MultiQC ingestion + generalized output-tree layout (keep on-disk `fastq/`/`mosdepth/`/`run/` names).
11. Parquet/columnar feature-store; card-snapshot event for full-content audit export.

CUT (do not build; trim from spec surface for this hackathon):
12. The Archivist *agent* scaffold (agent/stub/Claude/env-tier package, `ArchiveNote`/`ExportManifest`, `query.py`, `knowledge/` corpus) — keep only the one-paragraph roster spec; its near-term value IS BUILD-NOW #1.
13. `v_ml_features` pivot VIEW; `export.emitted` reserved event; NL→filter LLM convenience; any LLM narration in the export path; `pyarrow`/`pandas`/`file-saver` deps.
14. Output-tree directory rename to `reads/`/`alignment/`/`coverage/` (churn for zero gain).

SCHEDULE NOTE: with the Archivist cut and QC-triage done, the highest-value use of the "agent layer" slot is flipping the existing QC-triage agent live for the demo (`PIPEGUARD_TRIAGE_AGENT=claude`, stub fallback intact) — not starting agent #2 or #3.

---

## Appendix C — Tool-output catalog + storage policy

*The end-to-end germline-panel artifact catalog behind §3, produced by the output-layout workflow and fact-checked. `(VERIFY)` marks nf-core/sarek-convention filenames not grounded in our repo — confirm against a real sarek run before citing as canonical. Tool licenses are "reported, not verified" in-repo and are not asserted here.*

## Tool-Output Catalog — Germline DNA Panel Run (nf-core/sarek-style)

The end-to-end artifacts a real germline panel run emits, stage by stage. PipeGuard runs **no alignment and no variant-calling of its own** — it consumes pre-aligned/pre-called GIAB inputs and re-derives only three QC stages. Filenames shown as `HG002.*` are quoted verbatim from our scripts (no tag); generic `<sample>.*` names are the tool/sarek convention; `(VERIFY)` marks a filename I could not confirm against the repo (version-dependent or general knowledge).

**Demo status legend:** **OURS** = our demo produces/consumes this today · **FULL** = only a full upstream sarek run makes it; we sit on top and never generate it · **PARTIAL** = we touch a *related* artifact with a nuance (e.g. we slice a pre-existing BAM, or region-subset rather than QC-filter).

| # | Stage | Typical tool | Real output artifact(s) — with extensions | Purpose | Demo status |
|---|---|---|---|---|---|
| 1 | **Demultiplex** | BCL Convert (modern) / bcl2fastq (legacy) | Per-sample `<Sample>_S<n>_L00<lane>_R1_001.fastq.gz` (+`_R2`, ±`_I1/_I2`); BCL Convert `Reports/{Demultiplex_Stats,Quality_Metrics,Adapter_Metrics,Top_Unknown_Barcodes,fastq_list}.csv`, `RunInfo.xml`; legacy bcl2fastq `Stats/Stats.json`, `Stats/DemuxSummaryF1L1.txt` | Convert per-cycle BCL + SAV/InterOp to per-sample FASTQ; record barcode-assignment / cluster-PF | **FULL** (we don't demux; we hand-author `run/SampleSheet.csv` and leave `cluster_pf` blank) |
| 2 | **Read QC + trim** | fastp (± FastQC → MultiQC) | `HG002.fastp.json`, `HG002.fastp.html`, `HG002.R{1,2}.trim.fastq.gz`; FastQC `<sample>_R1_fastqc.html` / `.zip` | Adapter/quality trim; emit Q30, %-pass-filter, duplication | **OURS** (fastp: read `q30_rate`, `passed_filter_reads`, `duplication.rate`; `.html` unread). FastQC = FULL |
| 3 | **Alignment** | BWA-MEM2 / bwa-mem / DRAGMAP (sarek); GIAB's BAM used **novoalign** | Sorted `<sample>.bam` + `.bai`; sarek `<sample>.recal.cram` (VERIFY) + `.crai` (decode needs the *matching* `<ref>.fa` + `.fai`) | Align reads to GRCh38 | **FULL** (no alignment of our own). **PARTIAL:** we *slice* the pre-aligned novoalign BAM → `HG002.GRCh38.panel.bam` + `.bam.bai` via `samtools view -M -L` (region-restriction, not alignment) |
| 4 | **Duplicate marking** | GATK4 / Picard MarkDuplicates (sarek); samtools markdup | Marked `<sample>.md.cram` (VERIFY) + index; metrics `<sample>.md.cram.metrics` (VERIFY); samtools `<sample>.flagstat`, `<sample>.stats` | Flag PCR/optical dups; emit dup-rate + alignment stats | **FULL**. (Our dup-rate comes from fastp, not a mark-dup step.) Note: dedup suits hybrid-capture, is routinely **skipped for amplicon**; our reads are a WGS slice, not true capture |
| 5 | **Coverage** | mosdepth (± Picard HsMetrics for panels) | `HG002.panel.mosdepth.summary.txt` (READ → mean cov: `total_region` row, `mean` = 4th field / `fields[3]` 0-indexed), `HG002.panel.thresholds.bed.gz` (READ → breadth: `c[6]`=≥20X, `c[7]`=≥30X, 0-indexed) + `.csi`; unread siblings `.mosdepth.global.dist.txt`, `.mosdepth.region.dist.txt`, `.regions.bed.gz` + `.csi`; `--no-per-base` suppresses `.per-base.bed.gz`; Picard `<sample>.hs_metrics.txt` (VERIFY) | Per-region depth + breadth over the panel BED | **OURS** (mosdepth `--by … --thresholds 1,10,20,30 --no-per-base`). Picard HsMetrics = FULL |
| 6 | **Variant calling (germline)** | DeepVariant / GATK HaplotypeCaller / FreeBayes (in-repo); sarek adds Strelka2 (germline), Mutect2 (somatic) | `<sample>.<caller>.vcf.gz` + `.tbi`; gVCF `<sample>.<caller>.g.vcf.gz` + `.tbi`; joint `joint_germline.vcf.gz` (VERIFY) + `.tbi`; DeepVariant `<sample>.visual_report.html` (VERIFY); Strelka2 `variants/variants.vcf.gz`, `variants/genome.S1.vcf.gz` (VERIFY) | Call SNVs/indels; gVCF preserves per-site confidence for joint genotyping | **FULL** (no calling of our own). **PARTIAL:** we *consume* NIST's pre-called truth `HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz` + `.tbi` as the gold-standard answer key |
| 7 | **Filter / normalize** | bcftools (filter/norm) + GATK **hard-filter** (panel default) | `<sample>.filtered.vcf.gz` + `.tbi`; normalized `<sample>.norm.vcf.gz` + `.tbi` | Drop low-quality calls; left-align/split multiallelics | **FULL** for QC-filtering. **PARTIAL:** our `bcftools view -R panel.bed -Oz` + `tabix -p vcf` → `HG002_…_benchmark.panel.vcf.gz` + `.tbi` is **region-subsetting the truth VCF**, not quality-filtering (bgzip never called directly; `-Oz` block-gzips). Note: **VQSR is cohort/WGS-only — NOT applicable to a single-sample/small panel** (needs many variants to train); and GATK hard-filters target HaplotypeCaller annotations, so do **not** pair them with a DeepVariant set (DeepVariant emits its own PASS/RefCall — filter via `bcftools view -f PASS`) |
| 8 | **Annotation** (optional) | VEP / snpEff (sarek); in-repo names gnomAD (pop AF) + ClinVar (clinical significance) as *sources* | VEP `<sample>.vep.vcf.gz` + `.tbi`, `<sample>.vep.summary.html` (VERIFY); snpEff `<sample>.snpeff.vcf.gz`, `snpEff_summary.html`, `snpEff_genes.txt` (VERIFY) | Attach consequence / pop-frequency / clinical-significance | **FULL**. gnomAD/ClinVar surface context, never set a gate verdict |
| 9 | **QC aggregation** | MultiQC | `multiqc_report.html`; `multiqc_data/multiqc_data.json` (keys `report_general_stats_data`, `report_saved_raw_data` keyed `multiqc_<module>`, `report_data_sources`, `report_general_stats_headers`), `multiqc_general_stats.txt`, `multiqc_sources.txt`, `multiqc.log`, per-module `multiqc_<module>.txt` | Roll every tool's QC into one cross-sample report + machine-readable JSON | **FULL** (parser reads none; `HG002.fastp.html` is single-tool, not an aggregate) |
| 10 | **Pipeline provenance** | Nextflow / nf-core | `pipeline_info/`: `software_versions.yml`, `params_<ts>.json`, `execution_trace_<ts>.txt`, `execution_report_<ts>.html`, `execution_timeline_<ts>.html`, `pipeline_dag_<ts>.{html,svg,mmd}` (VERIFY), `manifest_<ts>.bco.json`; `csv/` recaps `mapped.csv`, `markduplicates.csv`, `recalibrated.csv`, `variantcalled.csv` (cols `patient,sample,…,path`) | Record exact tool versions, resolved params, per-task hashes/runtimes, BioCompute Object | **FULL** (we run no nextflow; parser reads none). **PARTIAL:** PipeGuard keeps its **own** provenance — append-only JSONL event ledger + rebuildable SqliteRepository (ADR-0002), not `pipeline_info/` |

### Index / checksum companions

Every large binary carries a small companion the core can hash/index without opening the payload.

| Payload | Index | Checksum posture in our repo |
|---|---|---|
| `<sample>.bam` | `.bai` (or `.csi`) | GIAB reads-BAM `.bai` md5 **pinned + enforced** in `giab_hg002_manifest.json` |
| `<sample>.cram` | `.crai` | sarek per-file `.md5` not emitted by default (VERIFY) |
| `<sample>.vcf.gz` / `.g.vcf.gz` | `.tbi` (`.csi` only for contigs >512 Mbp) | GIAB v4.2.1 truth publishes **no** checksums → trust-on-first-use with a logged **sha256** |
| mosdepth `*.bed.gz` | `.csi` (mosdepth default) | derived, git-ignored; not separately checksummed |
| reference `<ref>.fa` | `.fai` (`.dict` is a GATK/Picard *calling* companion, **not** needed to decode CRAM) | reference fetched, not committed |

### What OUR demo actually writes today

Net CLI set invoked: **mosdepth, samtools (collate/fastq/view/index), fastp, bcftools, tabix** — all under git-ignored `data/real-giab/`. Only `run/{qc_metrics,SampleSheet,sample_metadata}.csv` is **GATE-READ**; `HG002.fastp.json` + `HG002.panel.mosdepth.summary.txt` + `HG002.panel.thresholds.bed.gz` are **FLATTEN-INPUT** (read once off-path); everything else (BAM/`.bai`, truth VCF/`.tbi`, raw+trim FASTQ, `fastp.html`, mosdepth dist/regions) is **INDEX-ONLY**.

### Accuracy flags (do not over-assert)

1. **mosdepth mean is `fields[3]` (0-indexed = 4th column)**, not "column 3" 1-based (that would be `bases`).
2. **`.dict` is NOT a CRAM-decode prerequisite** — samtools decodes from the reference FASTA + `.fai` (via M5/`REF_CACHE`); `.dict` is a GATK/Picard calling companion.
3. **VQSR** is cohort/WGS-shaped — hard-filtering is the panel default; **GATK hard-filters** do not apply to a DeepVariant call set.
4. **`pct_reads_identified`** is a fastp pass-filter rate, not an Illumina barcode-identification metric (column-name/semantics mismatch).
5. **Tool licenses** for fastp/mosdepth/samtools/bcftools/MultiQC/sarek are "reported, not verified" in-repo — no license is asserted here.
6. `(VERIFY)` sarek names (`<sample>.md.cram(.metrics)`, `joint_germline.vcf.gz`, `.recal.cram`, VEP/snpEff, HsMetrics) and the `preprocessing/`/`variant_calling/` dir names are general nf-core/sarek knowledge — confirm against a real sarek run before citing as verbatim.

### Storage policy (summary)

Sizing frame: target host is an M4 Mac Mini / 32 GB running **panel slices, not WGS** (sliced artifacts are tens–low-hundreds of MB). So this is ~90% convention + reproducibility discipline, ~10% disk pressure — **nothing needs deleting today**; the policies below are scale seams for a future exome/WGS run.

1. **FASTQ retention → KEEP now, regenerable at scale.** Raw `R1/R2` and trimmed `R1/R2` are **regenerable intermediates**: raw ← BAM (`samtools collate | samtools fastq`, deterministic); trimmed ← raw (`fastp`, fixed params, deterministic). The **irreplaceable keeper is `HG002.fastp.json`** — sole provenance of Q30 / pass-filter / duplication that flow into `run/qc_metrics.csv`. On the panel, keep raw + trimmed (cheap, handy for re-running fastp); leave fastp's default gzip (chasing `-9` trades CPU for a few MB — not worth it). A "drop regenerable FASTQ once `fastp.json` is captured" rule is a **policy to document, not to auto-run in the MVP**.

2. **BAM → CRAM → DEFER.** Panel-slice saving is tens of MB, so on 32 GB this is negative-value now and adds a **silent-decode-failure footgun**. If ever done: (a) commit to **lossless-of-record explicitly** — lossy quality-score binning is out of scope; (b) size it honestly — **lossless CRAM saves ≈ 20–40% over BAM**, not the ~50–60% that assumes lossy binning (BAM is already BGZF and quality scores dominate the file, so reference compression only shrinks the base-sequence minority); (c) decoding needs the **identical GRCh38 FASTA the BAM was aligned against + its `.fai`** — **not** `.dict` (that is a GATK/Picard calling companion) — keyed by each `@SQ` **M5**; our BAM is NIST **novoalign** output, so **verify the `@SQ` M5 tags resolve against the pinned reference before converting**, or decode fails silently later; (d) preserve the original BAM sha256 before conversion, keep CRAM as the archival copy, treat BAM as regenerable (re-sliceable from the accession).

3. **VCF / gVCF.** We produce **no called VCF** (we run no caller) — the only VCF on disk is the NIST **answer key** (input, origin `real-giab`), not run output. Keep the panel truth slice `…benchmark.panel.vcf.gz` + `.tbi` and the high-confidence BED as **keepers** (faithfulness claims valid only inside the BED). Every VCF stays **bgzip'd** (`.vcf.gz` via `bcftools -Oz` — bgzip is never called directly) with a **tabix `.tbi`** companion (`.csi` only for contigs >512 Mbp — not our GRCh38 panel); **no bare `.vcf`** in the tree. **gVCF is N/A** — we emit none, and "drop after joint-genotyping" is cohort/WGS framing that a single-sample panel may never execute; keep it only as a scale note.

4. **Indexes + checksums are first-class companions.** An index always travels with its payload (`.bam.bai` / `.cram.crai`, `.vcf.gz.tbi`, `.fa.fai`) — a missing index turns a KB seek into a full-file scan for the UI/agent. On checksums, honor the two grounded facts: the manifest **pins the reads-BAM `.bai` md5 (enforced)**, and the un-checksummed v4.2.1 truth artifacts are **trust-on-first-use with a logged sha256**. Target-state (DEFER): extend that discipline to **derived** artifacts via a single run-level **`MANIFEST.sha256`** (`<sha256>  <relpath>  <origin>  <kind>`) computed at write time — one file is cheaper to scan than a per-file `.md5`, it keeps the **origin label** (`real-giab`/`synthetic`/`contrived`) glued to every artifact (ADR-0007), and it doubles as the source rows for the (unbuilt) ArtifactRef registry.

5. **Keep vs. regenerate (panel scale — reclaim nothing; policy is for exome/WGS).**
   - **KEEP:** `run/*.csv` (gate input); `HG002.fastp.json`; `mosdepth …summary.txt` + `…thresholds.bed.gz`; benchmark truth slice + BED; provenance/index; and — *when a run calls* — called + filtered VCF + indexes.
   - **Regenerable:** raw + trimmed FASTQ; `fastp.html`; mosdepth `global.dist`/`region.dist`/`regions.bed.gz` (unread); BAM after any CRAM conversion.
   - **N/A here:** gVCF (we emit none); CRAM (deferred).
   - Guiding line: **keep evidence + the answer key + provenance/index; treat reads and format-duplicates as regenerable.** The 122 GB source BAM is never stored whole (structurally refused; only sliced).

---

## Open questions for the maintainer

*Each carries a recommendation; the workflow's own resolution is noted where it took one.*

1. Export source of truth per claim (RESOLVED as proposed; confirm). BUILD-NOW export serializes the live in-memory `_evaluate` cards, honestly labeled as a deterministic re-derivation and version-stamped (rule_pack_version + metric_registry_version + origin), NOT as ledger-derived audit provenance. TARGET-STATE audit export reads the projection built by a one-shot emit-once command. Confirm you accept "two paths, two honesty labels" rather than forcing one — the guardrail critique wanted one source of truth, but the two serve different claims (demo convenience vs. audit).

2. `origin` provenance for BUILD-NOW rows. Origin isn't persisted or reliably on the in-memory cards today. Proposal: read it from a per-run marker/manifest in the run dir, default `unknown`, and gate intake-identity export to non-real origins. Is a per-run origin marker file acceptable, or should origin ride the sample_metadata/run manifest?

3. PHI posture for the hackathon. The only "real" data is GIAB HG002, a publicly consented reference genome (not PHI), so G-PII/G-DEID are forward-looking. Confirm we can ship intake-identity export for the demo on that basis, with the de-id gate documented for when real patient runs are ingested — or do you want `submitted_by` dropped/hashed even for HG002 now (recommend: drop it now, it's never an ML feature).

4. Metric event grain for the durable path. Proposal: one `metric.parsed` event PER SAMPLE carrying the MetricValue list (matches the card grain + existing per-sample event pattern), projector fans out to rows — NOT one event per MetricValue. Confirm the grain before anyone implements the projector rule.

5. `metric_values` primary key. Proposal: composite natural key `(run_id, sample_id, metric_key)` with `content_hash` as an indexed column (matches FindingRow/CardRow). The source section proposed `content_hash` as PK; since content_hash omits run_id (covers sample_id+metric_key+analysis_run_id), the composite key is safer. Confirm.

6. Is the "deterministic archivist core" worth shipping in the demo at all, or is it fully subsumed by the BUILD-NOW `/api/export` endpoint? (Recommendation: subsumed — ship the endpoint under its plain name, keep the Archivist as spec-only.)

7. Agent-slot priority for tomorrow: flip the existing QC-triage agent live for the demo (recommended) vs. start agent #2 pipeline-repair (blocked on `pipeline_info/execution_trace` capture that doesn't exist). Confirm the "polish what works" call.


**NGS output layout (from the §3 expansion) — additional questions (none block build-now; all are naming/semantics or target-state):**

Decisions to escalate to the maintainer (each is target-state or a naming/semantics call; none blocks build-now, which is documentation only):

1. **sarek renames — keep current names or align later?** The doc §3.4 already forbids relabeling `fastq/`/`mosdepth/`/`run/` to `reads/`/`alignment/`/`coverage/` as "adopt now." Recommendation: **keep them verbatim**; `reads/` is *cut* (invented third name, matches neither code nor sarek), `mosdepth/`→`reports/mosdepth/` is *cut* (cosmetic). Confirm you want the current names frozen and any future rename made only in the same diff as its producing script.

2. **VCF home is an OPEN decision — reserve it.** DESIGN 2 proposed `variant_calling/deepvariant/HG002/…`; DESIGN 3 proposed a `variants/` sibling. They conflict, and **we run no caller**, so there is no run-produced VCF to home. Recommendation: **reserve the decision until a real caller exists**; document `variant_calling/` (VERIFY, ungrounded) as the illustrative empty slot, and keep the truth VCF in a `benchmark/` grouping (it is *input*, not run output).

3. **Keep gVCF? — N/A today.** We emit no gVCF; "drop after joint-genotyping" is cohort/WGS framing a single-sample panel may never reach. Confirm gVCF handling only becomes real if/when a caller + joint step is added.

4. **Keep raw FASTQ? — regenerable.** Raw + trimmed FASTQ are deterministic intermediates (BAM→FASTQ, then fastp); the keeper is `fastp.json`. Recommendation: **keep on the panel (cheap), do not auto-delete in the MVP**; adopt a drop-regenerable-intermediates policy only at exome/WGS scale.

5. **BAM→CRAM intent + M5 verification.** If we ever convert: confirm **lossless-of-record** (not lossy quality-binning), expect only **≈20–40%** savings (not ~50%), and require an on-toolchain check that the NIST novoalign BAM's `@SQ` **M5** tags resolve against the pinned GRCh38 reference (+ `.fai`; `.dict` not needed to decode) before conversion — else silent decode failure later.

6. **ArtifactRef registry + `MANIFEST.sha256` — build when agents exist.** Both are DEFER: glob already gives findability at panel scale; the registry is an O(1)/agent-friendly upgrade for an archivist that is currently spec-only. Confirm it stays a rebuildable projection off the event ledger, off the critical path.

7. **`pct_reads_identified` semantic mismatch — rename the column or document it?** The value is a fastp *pass-filter* (quality) rate, but the column name implies Illumina *barcode-identification* (reads assigned to a known barcode). Decide whether to rename the metric key or annotate the runbook so no one reads it as a demux assignment rate.

8. **`run_id` identity.** The target per-run root keys on the `analysis_run` UUIDv7 and assumes multi-sample runs share a root with per-sample subdirs. Confirm the 1:1 mapping (one filesystem run root ↔ one `analysis_run` event) before any per-run layout is built.

9. **Unverified sarek filenames.** `<sample>.md.cram` / `.md.cram.metrics`, `joint_germline.vcf.gz`, `.recal.cram`, VEP/snpEff outputs, Picard `hs_metrics.txt`, and the `preprocessing/`/`variant_calling/` dir names are tagged `(VERIFY)` — confirm against a real sarek output tree before any of them is cited as canonical. Likewise, fastp/mosdepth/samtools/bcftools/MultiQC/sarek licenses are "reported, not verified" in-repo — do not assert them.

---

*Marker legend — distinguish claim types where confusion is likely:*
**Fact** · **Assumption** · **Decision** · **TODO**.
