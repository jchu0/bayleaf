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

## 3. Analysis-output file-structure convention

*Scope: a single germline DNA **panel** run (nf-core/sarek vocabulary), sized for an M4 Mac Mini / 32 GB — panel slices, not WGS. See [nf-core-conventions.md](../data/nf-core-conventions.md), [strategy.md](../data/strategy.md).*

### 3.1 The one idea: two tiers of on-disk state

1. **The per-tool output tree** — the natural NGS artifact layout (`fastq → fastp → BAM → mosdepth → variants`). Rich, tool-shaped, sarek-named. The **shared substrate** the agent layer observes.
2. **The gate run-dir (`run/`)** — a **flat directory of exact-named CSVs** `load_run` ingests; a *derived, lossy projection* of tier 1 via a deterministic flatten step (`scripts/gate_giab.py:186-205` `write_run_dir`).

The gate's deterministic critical path reads **only tier 2**. Agents read **both tiers and write into neither** in a way that changes a verdict.

### 3.2 (A) Already on disk / already frozen

1. **The flat `run/` ingest contract is frozen in practice** and is the stable interface. `load_run` (`parsers.py:187-217`) reads five exact filenames, each `.exists()`-gated so a missing file is a *signal, not a crash* — **none is strictly required**: `qc_metrics.csv`, `SampleSheet.csv`, `sample_metadata.csv`, and optional `demux_stats.csv`, `pipeline.log`.
2. **The real GIAB panel tree exists** under `data/real-giab/` (origin `real-giab`, git-ignored), produced for real by `gate_giab.py` (`run_fastp`, `run_mosdepth`, `parse_coverage`, `parse_fastp`). On-disk directory names are **`fastq/`, `mosdepth/`, `run/`** (+ top-level `.bam`/`.vcf.gz`). Confirmed values: `run/qc_metrics.csv = HG002,88.22,99.31,55.8,0.0057,` against mosdepth `total_region` mean `55.76`.

What each artifact maps to (unchanged):

| Tree artifact | Reaches the gate via | Read by `load_run`? |
|---|---|---|
| `run/qc_metrics.csv` | `parse_qc_metrics` | **Yes** — `sample_id,q30,pct_reads_identified,mean_coverage,dup_rate,cluster_pf` |
| `run/SampleSheet.csv` | `parse_sample_sheet` | **Yes** — `[BCLConvert_Data]`/`[Data]`, `Sample_ID/index/index2` |
| `run/sample_metadata.csv` | `parse_sample_metadata` | **Yes** — `subject_id/tissue/library_prep/submitted_by` |
| `run/demux_stats.csv`, `run/pipeline.log` | `parse_demux_stats` / `parse_log` | **Yes if present** (optional) |
| `fastq/*.fastp.json`, `mosdepth/*.mosdepth.summary.txt` | *flattened* → the CSV fields above | No — upstream input to the flatten step |
| `*.bam`, `*.vcf.gz`, `*.thresholds.bed.gz` | — | **No — never opened by the core** |

### 3.3 (B) BUILD NOW

**Documentation only — no build work.** Freeze and record the flat `run/` contract (this section) against the real GIAB slice. **Download nothing**: the panel window is `chr20_region = 250,000 bp` (~13.9 Mbases in-panel) — real, truth-backed, already on disk, comfortably inside 32 GB, and the core gate never touches reads (`load_run` opens only KB-scale CSVs; the one heavy `mosdepth`/`fastp` step runs once in the derivation script, off the gate path). Synthesizing a WGS/large FASTQ buys *lower* fidelity for *more* effort; reserve synthetic/contrived data for rule-triggering edge cases, not for establishing structure.

### 3.4 (C) TARGET-STATE

1. **A generalized per-run convention.** If a canonical layout is standardized, **keep the on-disk names already produced (`fastq/`, `mosdepth/`, `run/`)** — do not relabel to `reads/`/`alignment/`/`coverage/` and call it "adopt now," since nothing produces those names and the core never opens them; a rename is churn for zero functional gain. If a rename is genuinely wanted, mark it target-state and change `gate_giab.py`/fetch paths in the **same diff**.
2. **Ingest additionally reading** `pipeline_info/software_versions.yml`, `multiqc_data.json`, `execution_trace_<ts>.txt`, and sarek `csv/*.csv` recaps. The parser reads **none** of these today — they live only in the aspirational [nf-core-conventions.md](../data/nf-core-conventions.md) mapping. Do not pretend they are wired.
3. **`ArtifactRef(path, kind, sample_id, checksum, …)` registry** — the `report_data_sources` provenance analog, unimplemented today. This is a **deterministic ingest-boundary task, not agent work** (see §5); if ledger-tracked, it emits `artifact.ingested` events from the core.
4. **`pipeline_provenance`** (sarek `params_hash`/`execution_trace`) capture — the input the pipeline-repair agent (#2) needs — is Phase-2 (see [provenance.md](../data/provenance.md)).

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

## Open questions for the maintainer

*Each carries a recommendation; the workflow's own resolution is noted where it took one.*

1. Export source of truth per claim (RESOLVED as proposed; confirm). BUILD-NOW export serializes the live in-memory `_evaluate` cards, honestly labeled as a deterministic re-derivation and version-stamped (rule_pack_version + metric_registry_version + origin), NOT as ledger-derived audit provenance. TARGET-STATE audit export reads the projection built by a one-shot emit-once command. Confirm you accept "two paths, two honesty labels" rather than forcing one — the guardrail critique wanted one source of truth, but the two serve different claims (demo convenience vs. audit).

2. `origin` provenance for BUILD-NOW rows. Origin isn't persisted or reliably on the in-memory cards today. Proposal: read it from a per-run marker/manifest in the run dir, default `unknown`, and gate intake-identity export to non-real origins. Is a per-run origin marker file acceptable, or should origin ride the sample_metadata/run manifest?

3. PHI posture for the hackathon. The only "real" data is GIAB HG002, a publicly consented reference genome (not PHI), so G-PII/G-DEID are forward-looking. Confirm we can ship intake-identity export for the demo on that basis, with the de-id gate documented for when real patient runs are ingested — or do you want `submitted_by` dropped/hashed even for HG002 now (recommend: drop it now, it's never an ML feature).

4. Metric event grain for the durable path. Proposal: one `metric.parsed` event PER SAMPLE carrying the MetricValue list (matches the card grain + existing per-sample event pattern), projector fans out to rows — NOT one event per MetricValue. Confirm the grain before anyone implements the projector rule.

5. `metric_values` primary key. Proposal: composite natural key `(run_id, sample_id, metric_key)` with `content_hash` as an indexed column (matches FindingRow/CardRow). The source section proposed `content_hash` as PK; since content_hash omits run_id (covers sample_id+metric_key+analysis_run_id), the composite key is safer. Confirm.

6. Is the "deterministic archivist core" worth shipping in the demo at all, or is it fully subsumed by the BUILD-NOW `/api/export` endpoint? (Recommendation: subsumed — ship the endpoint under its plain name, keep the Archivist as spec-only.)

7. Agent-slot priority for tomorrow: flip the existing QC-triage agent live for the demo (recommended) vs. start agent #2 pipeline-repair (blocked on `pipeline_info/execution_trace` capture that doesn't exist). Confirm the "polish what works" call.

---

*Marker legend — distinguish claim types where confusion is likely:*
**Fact** · **Assumption** · **Decision** · **TODO**.
