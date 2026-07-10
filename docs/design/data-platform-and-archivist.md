# Data Platform, Output Structure & the Archivist Agent

| Field | Value |
|---|---|
| **Status** | Draft — for maintainer review |
| **Last updated** | 2026-07-09 (MST) |
| **Audience** | all (contributors and Claude Code) |
| **Related** | [design/architecture.md](architecture.md) · [design/agents.md](agents.md) · [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) · [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md) · [ADR-0007](../adr/ADR-0007-ml-ready-structured-outputs.md) · [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md) · [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md) · [ADR-0015](../adr/ADR-0015-layered-data-contract.md) · [data/provenance.md](../data/provenance.md) · [data/schemas.md](../data/schemas.md) · [data/metric_registry.md](../data/metric_registry.md) · [data/strategy.md](../data/strategy.md) · [planning/tasks.md](../planning/tasks.md) · [journal/2026-07-09-giab-e2e-pipeline.md](../journal/2026-07-09-giab-e2e-pipeline.md) · [journal/2026-07-09-frontend-batch3.md](../journal/2026-07-09-frontend-batch3.md) |

> **Draft for review.** Produced by a multi-agent design workflow (four design perspectives +
> three adversarial critiques — scope-realism, guardrails, over-engineering — then synthesized)
> and fact-checked against the code: `get_run_bundle`, the reserved `metric.parsed` /
> `artifact.ingested` event types, the GET + single off-gate POST (feedback/pipelines) CORS
> posture (no PUT/DELETE/PATCH), the `@lru_cache` on `_evaluate`, the five
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

## Decisions taken (2026-07-08 maintainer review)

The maintainer reviewed this design + the §3 output-layout expansion and settled the open
questions. **This is the authoritative record** (it supersedes the *Open questions* section
below where they conflict; the questions are kept for traceability).

1. **Build now (D1/D2).** The only hackathon build is the read-only `GET /api/export` +
   month-scoped `RunsBrowser` + download button. Agents stay **spec-only** today; the
   agent-layer buildout is tomorrow.
2. **Persistence direction (D3 — proposed, confirm).** SQLite stays the operational projection
   now. **End-goal = Postgres as the single operational store, using its built-in `pgvector`
   as the vector store** (subsumes wishlist #5) — *not* Postgres **plus** a separate DuckDB.
   The export is a **single tabular/columnar file on demand** (CSV / JSONL / **Parquet** —
   Parquet is a **first-class option now** via an optional `pyarrow` extra, so a user brings
   any reader: pandas / polars / DuckDB), never "masses of loose files": the DB is the store,
   the file is a disposable export artifact. **DuckDB demoted to optional** (a local-analytics
   convenience). See wishlist #19/#5.
3. **Pipeline state → "mission control" (Re:1a).** Capture **per-step pipeline execution
   state, start→end**, as append-only ledger events, projected to the dashboard — the OLTP
   substrate that lets the dashboard evolve into a mission-control view. Target-state; pairs
   with run-control (wishlist #20).
4. **Durable metrics (D4/D5).** One `metric.parsed` event **per sample**; `metric_values`
   primary key = composite `(run_id, sample_id, metric_key)` with `content_hash` as an indexed
   column.
5. **Export honesty + PII (D6/D10/D11).** Two export paths, two honesty labels; drop/hash
   `submitted_by` even for HG002; carry **origin** from a per-run marker (default `unknown`),
   which gates whether intake-identity fields are exported (§2.1d). Origin is the seam that
   **evolves toward a study-specific id** (`study_id`) for study-scoped grouping/isolation
   (relates to multi-tenancy, wishlist #18).
6. **Output layout + archive (D7/D8).** Keep the `fastq/` `mosdepth/` `run/` names.
   **BAM→CRAM for archiving is CONFIRMED** (overrides the earlier "defer"). A run's **archive**
   = FASTQ(`.gz`) · CRAM(+`.crai`) · VCF output(s)(+`.tbi`) · QC metrics — **plus, do not
   forget:** the intake sheets (`SampleSheet.csv` + `sample_metadata.csv`), pipeline provenance
   (software versions + params + execution trace), the MultiQC report, **PipeGuard's own
   decision cards** (the verdicts that run produced), a `MANIFEST.sha256` carrying origin
   labels, and the **reference identity (genome build + per-`@SQ` M5) required to decode the
   CRAM later**. A **config file maps artifact-kind → output path** so PipeGuard
   reads any layout (ties to the config layer [ADR-0005](../adr/ADR-0005-config-layer-and-profiles.md)
   + the canvas builder, wishlist #11).
7. **Variant-gate substrate (General + D8/D13).** Add a **real disease-gene panel** over GIAB
   HG002 (truth-backed) + a **simple, pluggable caller** — PipeGuard mostly *reads* the VCFs a
   caller emits (point it at the VCF folder; the caller is bring-your-own). The variant **gate
   rules stay Phase 2**; the panel + caller + VCF ingest are design-now (build-now-if-time).
   **Design done — see Appendix D.** The build-now-if-time slice (`gate_giab.py --call` +
   EVAL-030) is **approved if time remains** after the export slice. **Guardrail (load-bearing):**
   HG002 is a *benchmark genome, not a patient*; any surfaced variant is a ClinVar-classified
   **test fixture**, never a diagnosis, and truth claims hold only inside the high-confidence BED.
8. **Naming (D14).** `pct_reads_identified` is a fastp pass-filter rate, not a barcode-ID
   metric — document now, rename the metric key eventually.
9. **Run-control (D12) + agent slot (D9).** Run-control stays wishlist #20 (revisit flex day).
   QC-triage (not agent #2) is the agent focus; test it live at end-of-day after the build.

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
10. **Product-domain stores — separate from the decision Repository (shipped 2026-07-09).** Two off-gate **product** writes persist through their own pluggable sinks, mirroring the persistence seam but never mixing with the decision projection (item 3's `Repository`): the **feedback store** (`api/feedback_store.py`, `PIPEGUARD_FEEDBACK_STORE`) and the **Pipeline Builder graph store** (`api/pipeline_store.py`, `PIPEGUARD_PIPELINE_STORE`) — each **jsonl (default) / sqlite / postgres**, **degrade-to-JSONL** if a DB selection fails, and **never logs the DSN** ([ADR-0016](../adr/ADR-0016-postgres-port.md)). Their rows are product state: they never become a run / sample / finding / card / ledger event and never re-enter the gate ([ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)). A saved `PipelineGraph` (`api/pipeline.py`) is a **tolerant, versioned envelope** — the builder's `graph` JSON is stored **as-is** (so its shape can churn without a migration) under a server-authored id + a monotonic per-name `version` — and it **reserves** a draft → save → approve review lifecycle: a `status` field (`draft`/`pending_review`/`approved`, default `draft`) plus `submitted_by`/`reviewed_by`/`approved_by`, **server-authored** when auth lands and **never client-set** (the `PipelineGraphIn` body is `extra="forbid"`, so no identity/PII enters through a save). The approve transition + auth are a documented, not-yet-built seam. Endpoints: `POST /api/pipelines` (201, server id + version), `GET /api/pipelines` (latest per name), `GET /api/pipelines/{name}` (all versions; 404 if none). **Update (later 2026-07-09):** the family grew to **four** product stores — a **settings/config-override store** (`api/settings_store.py`, `PIPEGUARD_SETTINGS_STORE`) and a **review-queue/ticket store** (`api/review_store.py`, `PIPEGUARD_REVIEW_STORE`) join feedback + pipeline, same pluggable/degrade/DSN-safe discipline — and the reserved draft→save→approve lifecycle is now **realized** by a shared RBAC primitive (`api/auth.py`, roles captured into the `*_by` fields) with real transition endpoints (pipeline `submit`/`approve`/`dry-run` (read-only)/`diff`, settings `approve`, ticket action lifecycle). Auth is a documented dev shim ([ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md)); config overrides still never mutate the live runbook.

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
- `GET /api/export` itself stays GET, over a CORS posture that now allows **GET + a single off-gate POST write verb** (the feedback/pipelines writes); no PUT/DELETE/PATCH (`allow_methods=["GET", "POST"]`, `api/main.py:66`; [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md)/[ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md)).
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
  - **Built (T-040 / W14): a config-driven de-id *policy* realizes G-PII + G-DEID at the export seam** ([`api/deid.py`](../../api/deid.py); routed through `_decision_rows`/`_feature_rows` in [`api/main.py`](../../api/main.py)). It is a **demo de-id SEAM, NOT HIPAA de-identification** — hashing is salted SHA-256 *pseudonymization*, a non-reversible heuristic, not the Safe-Harbor / Expert-Determination scrub of the full module (still wishlist #14, see §5.2.7). Four explicit field classes applied per row against the read-only `origin`: **`DROP`** (`submitted_by` operator PII — never a column, proving G-PII is policy-driven, not incidental omission); **`GATE_BY_ORIGIN`** (`subject_id`/`tissue` cohort keys — withheld for guarded origins `real-giab`+untagged `unknown`, and **pseudonymized** for non-real origins, so the opt-in `GET /api/export?include=identity` mode *shows* origin-gated hashed cohort keys rather than raw); **`HASH`** (always-pseudonymize); **`PASSTHROUGH`** (default for unnamed operational columns → a non-identity export is byte-identical to before). The default (no `include`) export is unchanged. Salt via `PIPEGUARD_DEID_SALT` (documented non-secret demo default). Policy id rides the `X-PipeGuard-Deid-Policy` header (no compliance claim). **Non-laundering (§5e):** `origin` is read-only from the per-run marker and the guarded-origin set is a fixed classification — **not** env-configurable — so config can never relabel a run *up* to `real-giab`. The policy is an export-path transform only; it never touches a verdict, finding, confidence, or gate input ([ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)).
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

### 3.2.1 (A, already-on-disk) A second real-GIAB producer: the full fastq→variants pipeline (`run_giab_pipeline.py`, 2026-07-09)

Where `gate_giab.py` (§3.2 above) reads the **pre-aligned** NIST panel BAM and gates on
coverage/breadth only, [`scripts/run_giab_pipeline.py`](../../scripts/run_giab_pipeline.py)
**actually executes** the Pipeline-Builder germline chain on the **raw** GIAB HG002 panel
fastqs: `fastp → bwa-mem2 mem → samtools fixmate/markdup → {mosdepth --by <panel>, bcftools
mpileup | call -mv | norm}`. This is a standalone driver of the bioconda toolchain — compose ≠
execute stays intact (ADR-0001/ADR-0003): the app never runs a tool, it only ingests the flat
`run/`-shaped output the script writes. Verified 2026-07-09 (`journal/2026-07-09-giab-e2e-pipeline.md`):
fastp v1.3.6 → bwa-mem2 v2.2.1 → samtools markdup (70,233 primary mapped) → mosdepth v0.3.14 →
bcftools v1.23.1, real metrics **Q30 88.2% · reads-PF 99.3% · 54.2× coverage · dup 0.006% ·
breadth 99.2% ≥20× · 553 normalized panel variants**.

**On-disk shape differs from §3.2 — a second, standalone-run-shaped location, not a nested
`run/`.** Git-ignored intermediates land under a new `data/real-giab/pipeline/` (a sibling of
`fastq/`/`mosdepth/`, alongside a git-ignored `data/real-giab/ref/` holding the chr20
GRCh38 reference + bwa-mem2 index the script needs). But the **flattened, gate-facing output**
does **not** nest under `data/real-giab/run/` like `gate_giab.py`'s — it lands as its own
**dashboard-discoverable run bundle** at the repo-standard `data/<run_id>/` path (currently
`data/RUN-2026-07-08-GIAB-HG002/`, matching the [strategy.md](../data/strategy.md) §Layout
convention every other run dir — mock, synthetic, or real — already uses), git-ignored under
`data/RUN-*-GIAB-*/` (`.gitignore`). It carries the same frozen-five artifacts as any run dir
(`SampleSheet.csv`, `sample_metadata.csv`, `demux_stats.csv`, `qc_metrics.csv`, `pipeline.log`)
plus an `origin` marker (`real-giab`), and is discovered/gated by the **unchanged** `run_gate` —
the same recompute the read-API serves (`GET /api/runs` finds it via the top-level `DATA_ROOT`
scan) — so it renders in the operator UI exactly like a mock run.

**Field derivations match §3.3 exactly** — same fastp/mosdepth semantics (`q30` /
`pct_reads_identified` / `dup_rate` from fastp; `mean_coverage` from mosdepth `total_region`
`fields[3]`; breadth from `thresholds.bed.gz` `c[6]`/`c[7]`) — the only difference is *this*
script's BAM is bwa-mem2-aligned + samtools-`markdup`-deduplicated by the script itself, not
consumed pre-aligned. `cluster_pf` is left blank for the same honest reason as §3.2 (a
run-level SAV/InterOp metric no fastq→BAM path can produce), and it is exactly that gap that
drives the run's real verdict to **HOLD** (`QC-CLUSTER_PF-NA`) rather than a rubber-stamped
PROCEED — a genuine demonstration of the gate catching a real data-completeness gap, not a
staged one.

**Scope note (corrects Appendix C below).** This is the first script in the repo that runs its
*own* alignment + variant calling rather than only consuming pre-aligned/pre-called GIAB
inputs. Appendix C's tool-output catalog and its "PipeGuard runs no alignment and no
variant-calling of its own" framing predate this script (2026-07-08) and describe
`gate_giab.py`'s narrower BAM-slice-only path; see the ★ notes added there.

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

1. `load_run` opens exactly six small text files under `run/` — the five flat CSVs/log (`parsers.py:187-217`) plus an optional `trace.txt` (a Nextflow execution trace, `parsers.py:301`, read-if-present → `[]` when absent, feeding EXEC-001); **no BAM/CRAM/VCF/`.bed.gz` handle exists anywhere in `parsers.py`**. The heavy `mosdepth`/`fastp` reads happen once, upstream, in `gate_giab.py`, off the gate path, and are flattened into `run/qc_metrics.csv`.
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
2. **Rebind the N+1 aggregation screens** (`Monitoring`/`ReviewQueue`/`Intake`) off the `Promise.all`-over-every-run fan-out. **Realized for monitoring (shipped 2026-07-09):** `GET /api/monitoring?window={7d|14d|30d|all}` now serves one pre-aggregated payload (§4.4), so the Monitoring screen renders from a single response; the `ReviewQueue`/`Intake` rebinding stays target-state, keeping the guaranteed-working demo path untouched.
3. **List virtualization** — only once a single month holds hundreds of runs. Explicitly **not** for the demo (pure risk, zero payoff at dozens of cards).
4. **Metric-threshold + subject/sample filters** come online with the metric-persistence path and richer projected columns.

### 4.3 Honest scale framing

The run *list* is not the demo's scaling problem — the eager full-detail fan-out is. The right MVP move is month-bucketing over the already-fetched array; do **not** build cursor pagination, page envelopes, "load older" paging controls, or virtualization for a few-dozen-run demo.

### 4.4 (Shipped 2026-07-09) — runs pagination/search + the windowed monitoring aggregate

Landed additively in `api/` (the core untouched; aggregation stays in the API layer per architecture guardrail 1), refining the §4.1/§4.2 plan. See also [architecture.md](architecture.md) §Component map (the `api/` surface).

1. **`/api/runs` filter + paging params.** `verdict` (runs containing ≥1 card of that verdict), `status` (the run-lifecycle label — `running`/`needs_review`/`released`; unknown → 400), `q` (**case-insensitive** substring match on `run_id` **OR** `platform` — the design's "search run id or platform" box), `sort` (closed vocabulary `{run_id,run_date,n_samples,n_attention}`, each with a `-` desc variant), and **optional** `page`/`limit`. With **no** params the JSON body is **byte-identical to before** — still a plain array; pagination engages only when `limit` is given, and the pre-slice total plus the active page/limit ride the `X-PipeGuard-Total-Count` / `X-PipeGuard-Page` / `X-PipeGuard-Limit` response headers (added to CORS `expose_headers`) so the body stays a list and the backward-compat contract holds. A fourth header, `X-PipeGuard-Status-Counts`, is **always** emitted — per-status facet counts (JSON) over the **full, unfiltered** set, so the UI's All / Needs-review / Sequencing / Released chips show totals independent of the active filter + page. This **supersedes** §2.1c's "no `limit`/offset" note (paging is header-based, still no body envelope) and §4.1.3's client-only bucketing (server paging is now available but not required for the demo). `RunSummary` also gained `platform` + `run_date` (from the SampleSheet `[Header]`) and the honest lifecycle `status` (`running`/`needs_review`/`released`) — see [architecture.md](architecture.md). **Platform variety in demo data (2026-07-09):** `scripts/seed_giab_demo.py`'s `RunSpec.platform` field rotates four real Illumina instrument names (NovaSeq X / NextSeq 2000 / NovaSeq 6000 / MiSeq) across its ~24 seeded runs, so the `q` platform-substring search and the platform column above are now exercised against genuinely varied values, not a single hardcoded default (the generator's `RunSpec.platform` otherwise defaults to `"NovaSeq"`, per [strategy.md](../data/strategy.md)).
2. **`GET /api/monitoring?window={7d|14d|30d|all default all}&signatures_limit={int}`.** One pre-aggregated dashboard payload — overall KPIs, per-run rows, per-gate flagged/total (for pass-rate), and ranked recurring signatures — replacing the frontend's N-fan-out of every run's detail. Windowed views place runs by their `[Header]` date; a run **lacking a header date** can't sit on the time axis and is dropped from a dated window, counted honestly in `n_runs_excluded_no_date` (`n_signatures_total` likewise reports the full distinct-signature count before `signatures_limit` caps the list). Aggregation reuses the existing `_aggregate_metrics()` (the same roll-up behind the Prometheus `/metrics` seam) and lives in the API layer, never the framework-agnostic core.
3. **Honesty label.** The overall roll-up's `auto_proceed_pct` (share of samples the gate cleared with no human touch) is a **heuristic throughput ratio, not a calibrated probability or confidence** (CLAUDE.md life-science guardrail 2). Counts are lifetime tallies over the in-window runs, not calibrated rates.

### 4.5 (Shipped 2026-07-09, T-062) — the Runs screen scale kit, reconciled against §4.1/§4.2

The frontend design-replication rebuild (Waves 1–3) landed the "scale kit" a different way than §4.1 first sketched — noted here so the plan above isn't read as the as-built shape:

1. **No separate `/runs` route.** `RunOverview.tsx` at `/` was enhanced in place (not replaced by a `RunsBrowser` at a new path) — §4.1 item 1 was **not adopted**.
2. **No month-bucketing / `started_at`.** Instead: search (`q`) + verdict/status facet chips (mono count badges, sourced client-side over the full fetched array) + a sort segmented control (recent/urgent/date) + a `DateRangePicker` (filters client-side on the existing `RunSummary.run_date`, §4.4/REQ-F-046 — no new `started_at` field was added) + client-side pagination. §4.1 items 2–3 were **not adopted**; the filter/search/paginate goal of item 4 **was**, just against the already-shipped `run_date`/`status` fields instead of a new `started_at`.
3. **Still consistent with §4.3's honest scale framing** — everything above runs over the one already-fetched `RunSummary[]` array (dozens of runs); no server keyset pagination, page envelope, or virtualization was built, matching §4.2 items 1/3 staying target-state (deliberately, not by omission).
4. **Export UI** (§4.1 item 5, per-run + batch) remains **not built** on `RunsBrowser`/`RunDetail` — the `GET /api/export` endpoint (§2.1) has no frontend download affordance yet (tracked under [T-030](../planning/tasks.md)'s open frontend half).

### 4.6 (Shipped 2026-07-09, T-076) — Monitoring recurring-signatures list, client-side pagination

A **different, smaller** scale fix than §4.4/§4.5 above, landed the same day (commit `e5d5043`): with the GIAB seed there are 50+ recurring issue signatures on `GET /api/monitoring`, and `Monitoring.tsx` rendered the entire (already server-unbounded — the frontend never sends `signatures_limit`) list. Ports the Runs-list pagination pattern verbatim: a 25/50/100 `SegmentedControl` + ‹/numbered/› pager + "Showing X–Y of N signatures," client-side over the fetched array, resetting to page 1 on window/search/per-page change. **This is not the same gap as [tasks T-072](../planning/tasks.md)**, which is the still-open, un-paginated per-run `rows: list[MonitoringRunRow]` on the same `GET /api/monitoring` response — a different list, still uncapped.

---

## 5. The Archivist agent (#3) — **BUILT (T-059, 2026-07-09)**

> **Built** as [`api/archivist.py`](../../api/archivist.py) (mirroring the feedback agent), realizing this design. Stub-first / $0 offline (`PIPEGUARD_ARCHIVIST_AGENT=stub|claude`, Haiku tier); advisory, off the gate. It takes a least-privilege `RunArchiveInput` (no `subject_id`/`tissue`/`submitted_by`) built from the projection and emits an `ArchiveDigest` (digest + export manifest + cross-run index); it never opens/moves/deletes a file or relabels an origin, and carries no verdict. Endpoints: `GET /api/runs/{id}/archive-digest` + `GET /api/archive/index`. The findability/registry pieces in §3.5 remain deferred; the sections below are the built agent's rationale + guardrail proof.

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
2. **Roster: genuine agent #3, behind #2.** #1 QC-triage **done**; #2 pipeline-repair **done** (T-058, Opus-tier `src/pipeguard/pipeline_repair/`; the `pipeline_info/execution_trace` capture it consumes now exists via EXEC-001 — `parsers.parse_execution_trace` + `models.TraceRecord`). The Archivist is a data-platform convenience over already-decided runs — spec now, build after the durable substrate and #2.
3. **Structure follows the `triage/` precedent** — a top-level package, **not** an `agents/` folder. #2 landed exactly this way (`src/pipeguard/pipeline_repair/`), so the `agents/<scope>/` restructure (T-026, [planning/tasks.md](../planning/tasks.md)) stays deferred (it is **not** triggered by #2 landing); keep `synthesis/` (narration) and `notify/` (port) out of the agent bucket.

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

STATUS: design-now / build-later. Spec now; build the deterministic export/index substrate first (it is the same code as the BUILD-NOW `/api/export` endpoint); attach the off-by-default LLM narration last, only once a populated store exists. Priority: behind #1 QC-triage (done) and #2 pipeline-repair (done, T-058).

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

ROSTER PLACEMENT: genuine agent #3, behind #2. Follows the top-level `triage/` package precedent, NOT an `agents/` folder — #2 itself landed as a top-level package, so the agents/<scope>/ restructure (T-026) stays deferred (not triggered by #2 landing); keep synthesis/ and notify/ out of the agent bucket.

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

The end-to-end artifacts a real germline panel run emits, stage by stage. **This catalog was fact-checked 2026-07-08 against `gate_giab.py`, which consumes pre-aligned/pre-called GIAB inputs and re-derives only three QC stages — PipeGuard ran no alignment/calling of its own at that point.** That is now only half true: `scripts/run_giab_pipeline.py` (2026-07-09, §3.2.1) *does* run its own bwa-mem2 alignment, samtools `markdup` dedup, and bcftools variant calling, as a standalone bioconda driver outside the app (compose ≠ execute holds — the deterministic core `src/pipeguard/` still never runs a tool). Rows 3/4/6 below are marked ★ where this changes their demo status. Filenames shown as `HG002.*` are quoted verbatim from our scripts (no tag); generic `<sample>.*` names are the tool/sarek convention; `(VERIFY)` marks a filename I could not confirm against the repo (version-dependent or general knowledge).

**Demo status legend:** **OURS** = our demo produces/consumes this today · **FULL** = only a full upstream sarek run makes it; we sit on top and never generate it · **PARTIAL** = we touch a *related* artifact with a nuance (e.g. we slice a pre-existing BAM, or region-subset rather than QC-filter).

| # | Stage | Typical tool | Real output artifact(s) — with extensions | Purpose | Demo status |
|---|---|---|---|---|---|
| 1 | **Demultiplex** | BCL Convert (modern) / bcl2fastq (legacy) | Per-sample `<Sample>_S<n>_L00<lane>_R1_001.fastq.gz` (+`_R2`, ±`_I1/_I2`); BCL Convert `Reports/{Demultiplex_Stats,Quality_Metrics,Adapter_Metrics,Top_Unknown_Barcodes,fastq_list}.csv`, `RunInfo.xml`; legacy bcl2fastq `Stats/Stats.json`, `Stats/DemuxSummaryF1L1.txt` | Convert per-cycle BCL + SAV/InterOp to per-sample FASTQ; record barcode-assignment / cluster-PF | **FULL** (we don't demux; we hand-author `run/SampleSheet.csv` and leave `cluster_pf` blank) |
| 2 | **Read QC + trim** | fastp (± FastQC → MultiQC) | `HG002.fastp.json`, `HG002.fastp.html`, `HG002.R{1,2}.trim.fastq.gz`; FastQC `<sample>_R1_fastqc.html` / `.zip` | Adapter/quality trim; emit Q30, %-pass-filter, duplication | **OURS** (fastp: read `q30_rate`, `passed_filter_reads`, `duplication.rate`; `.html` unread). FastQC = FULL |
| 3 | **Alignment** | BWA-MEM2 / bwa-mem / DRAGMAP (sarek); GIAB's BAM used **novoalign** | Sorted `<sample>.bam` + `.bai`; sarek `<sample>.recal.cram` (VERIFY) + `.crai` (decode needs the *matching* `<ref>.fa` + `.fai`) | Align reads to GRCh38 | ★ **OURS, via `run_giab_pipeline.py`** (§3.2.1) — real `bwa-mem2 mem` on raw GIAB fastqs. `gate_giab.py`'s path stays **PARTIAL**: it *slices* the pre-aligned novoalign BAM → `HG002.GRCh38.panel.bam` + `.bam.bai` via `samtools view -M -L` (region-restriction, not alignment) |
| 4 | **Duplicate marking** | GATK4 / Picard MarkDuplicates (sarek); samtools markdup | Marked `<sample>.md.cram` (VERIFY) + index; metrics `<sample>.md.cram.metrics` (VERIFY); samtools `<sample>.flagstat`, `<sample>.stats` | Flag PCR/optical dups; emit dup-rate + alignment stats | ★ **OURS, via `run_giab_pipeline.py`** (§3.2.1) — real `samtools markdup` on its own bwa-mem2 BAM. `gate_giab.py`'s dup-rate still comes from fastp, not a mark-dup step. Note: dedup suits hybrid-capture, is routinely **skipped for amplicon**; our reads are a WGS slice, not true capture |
| 5 | **Coverage** | mosdepth (± Picard HsMetrics for panels) | `HG002.panel.mosdepth.summary.txt` (READ → mean cov: `total_region` row, `mean` = 4th field / `fields[3]` 0-indexed), `HG002.panel.thresholds.bed.gz` (READ → breadth: `c[6]`=≥20X, `c[7]`=≥30X, 0-indexed) + `.csi`; unread siblings `.mosdepth.global.dist.txt`, `.mosdepth.region.dist.txt`, `.regions.bed.gz` + `.csi`; `--no-per-base` suppresses `.per-base.bed.gz`; Picard `<sample>.hs_metrics.txt` (VERIFY) | Per-region depth + breadth over the panel BED | **OURS** (mosdepth `--by … --thresholds 1,10,20,30 --no-per-base`). Picard HsMetrics = FULL |
| 6 | **Variant calling (germline)** | DeepVariant / GATK HaplotypeCaller / FreeBayes (in-repo); sarek adds Strelka2 (germline), Mutect2 (somatic) | `<sample>.<caller>.vcf.gz` + `.tbi`; gVCF `<sample>.<caller>.g.vcf.gz` + `.tbi`; joint `joint_germline.vcf.gz` (VERIFY) + `.tbi`; DeepVariant `<sample>.visual_report.html` (VERIFY); Strelka2 `variants/variants.vcf.gz`, `variants/genome.S1.vcf.gz` (VERIFY) | Call SNVs/indels; gVCF preserves per-site confidence for joint genotyping | ★ **OURS (partially), via `run_giab_pipeline.py`** (§3.2.1) — real `bcftools mpileup \| call -mv \| norm` → `HG002.calls.vcf.gz`/`HG002.norm.vcf.gz` (553 normalized panel variants), git-ignored intermediates **not yet wired into `qc_metrics.csv`** or the gate (no `parse_vcf`/`parse_vcf_stats` exists — Appendix D §3.5.4, still Phase 2). `gate_giab.py`'s path stays **PARTIAL**: it *consumes* NIST's pre-called truth `HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz` + `.tbi` as the gold-standard answer key, unchanged |
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

**`gate_giab.py`'s path (§3.2).** Net CLI set invoked: **mosdepth, samtools (collate/fastq/view/index), fastp, bcftools, tabix** — all under git-ignored `data/real-giab/`. Only `run/{qc_metrics,SampleSheet,sample_metadata}.csv` is **GATE-READ**; `HG002.fastp.json` + `HG002.panel.mosdepth.summary.txt` + `HG002.panel.thresholds.bed.gz` are **FLATTEN-INPUT** (read once off-path); everything else (BAM/`.bai`, truth VCF/`.tbi`, raw+trim FASTQ, `fastp.html`, mosdepth dist/regions) is **INDEX-ONLY**.

**`run_giab_pipeline.py`'s path (§3.2.1, 2026-07-09).** Net CLI set invoked: **fastp, bwa-mem2, samtools (fixmate/markdup/index/view), mosdepth, bcftools (mpileup/call/norm/index)** — intermediates under git-ignored `data/real-giab/pipeline/` + `data/real-giab/ref/`. Only the flattened `qc_metrics.csv`/`SampleSheet.csv`/`sample_metadata.csv`/`demux_stats.csv` at `data/RUN-2026-07-08-GIAB-HG002/` are **GATE-READ**; the fastp JSON and mosdepth summary/thresholds it derives them from are **FLATTEN-INPUT**; the bwa-mem2/markdup BAM and the bcftools-called/normalized VCF are **INDEX-ONLY today** — produced, not read by any parser (no `parse_vcf`/`parse_vcf_stats` exists yet; Appendix D §3.5.4).

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

3. **VCF / gVCF.** In `gate_giab.py`'s tree (`data/real-giab/`) we produce **no called VCF** — the only VCF on disk is the NIST **answer key** (input, origin `real-giab`), not run output. Keep the panel truth slice `…benchmark.panel.vcf.gz` + `.tbi` and the high-confidence BED as **keepers** (faithfulness claims valid only inside the BED). Every VCF stays **bgzip'd** (`.vcf.gz` via `bcftools -Oz` — bgzip is never called directly) with a **tabix `.tbi`** companion (`.csi` only for contigs >512 Mbp — not our GRCh38 panel); **no bare `.vcf`** in the tree. **gVCF is N/A** — we emit none, and "drop after joint-genotyping" is cohort/WGS framing that a single-sample panel may never execute; keep it only as a scale note.

4. **Indexes + checksums are first-class companions.** An index always travels with its payload (`.bam.bai` / `.cram.crai`, `.vcf.gz.tbi`, `.fa.fai`) — a missing index turns a KB seek into a full-file scan for the UI/agent. On checksums, honor the two grounded facts: the manifest **pins the reads-BAM `.bai` md5 (enforced)**, and the un-checksummed v4.2.1 truth artifacts are **trust-on-first-use with a logged sha256**. Target-state (DEFER): extend that discipline to **derived** artifacts via a single run-level **`MANIFEST.sha256`** (`<sha256>  <relpath>  <origin>  <kind>`) computed at write time — one file is cheaper to scan than a per-file `.md5`, it keeps the **origin label** (`real-giab`/`synthetic`/`contrived`) glued to every artifact (ADR-0007), and it doubles as the source rows for the (unbuilt) ArtifactRef registry.

5. **Keep vs. regenerate (panel scale — reclaim nothing; policy is for exome/WGS).**
   - **KEEP:** `run/*.csv` (gate input); `HG002.fastp.json`; `mosdepth …summary.txt` + `…thresholds.bed.gz`; benchmark truth slice + BED; provenance/index; and — *when a run calls* — called + filtered VCF + indexes.
   - **Regenerable:** raw + trimmed FASTQ; `fastp.html`; mosdepth `global.dist`/`region.dist`/`regions.bed.gz` (unread); BAM after any CRAM conversion.
   - **N/A here:** gVCF (we emit none); CRAM (deferred).
   - Guiding line: **keep evidence + the answer key + provenance/index; treat reads and format-duplicates as regenerable.** The 122 GB source BAM is never stored whole (structurally refused; only sliced).

---

## Appendix D — Variant-gate substrate (panel · pluggable caller · VCF ingest · GIAB-truth eval · run-layout config)

**Status:** design proposal (substrate + read-side plumbing only). **Date:** 2026-07-08 MST.
**Add-to:** new appendix of the data-platform design doc.
**Crosslinks:** ADR-0013 (three checkpoints; variant gate = per-variant confidence + annotation), ADR-0004 (origin labels / no invented pathogenicity), ADR-0002 (provenance ledger), ADR-0001 (rules decide, AI narrates), ADR-0005 (config layer + profiles), wishlist #11 (no-code pipeline-builder canvas).

**What this appendix does and does not do.** It defines the *regions*, *fixtures*, *read-side ingest*, *demo caller*, *truth-evaluation*, and *run-layout config seam* that a future variant gate will consume. It does **not** build the gate. Per ADR-0013 §Realized(1) the variant gate is "modeled but no variant rules fire yet"; confirmed in code — `models.py` wires `Gate.VARIANT`/`Category.VARIANT` and `DecisionCard.gate_results` iterates all three gates, but `rules.py` emits **zero** `Category.VARIANT` findings. The deterministic VARIANT rules are **Phase 2**. Nothing in this appendix fires a verdict on its own.

---

### 0. Framing contract (load-bearing — read first)

This is the guardrail, not decoration. It operationalizes CLAUDE.md life-science guardrails 1–5 and ADR-0004.

**0a. HG002 is a consented benchmark genome, not a patient.** HG002/NA24385 is the healthy son of the GIAB Ashkenazi trio, PGP-consented for open, unrestricted dissemination, and is NIST Reference Material RM 8391/8392. It is git-ignored under `data/real-giab/` and never committed. **No phenotype or diagnosis is attached** — nothing in the substrate says "this genome has disease X." Per data-platform §2.1d (G-DEID), the only "real" data here is a publicly consented reference genome, not PHI.

**0b. The truth VCF is a genotype truth set, not a pathogenicity annotation.** It records SNV + small indel positions where HG002 differs from GRCh38, with truth genotypes (0/1, 1/1). It contains benign and non-benign alleles alike. It is **not** annotated for pathogenicity.

**0c. Any ClinVar-P/LP allele HG002 carries is a carrier / low-penetrance / pharmacogenomic allele — not "disease-causing."** In a healthy benchmark genome these are almost all recessive carrier (heterozygous), low-penetrance risk, or PGx alleles.

**0d. The only defensible claim under test** (never a claim about HG002's health):
> *"Can the pipeline correctly call and surface a variant that carries a ClinVar P/LP label, inside a region where GIAB/CMRG truth can score it?"*

**0e. Never invent pathogenicity or coordinates.** All pathogenicity is imported from ClinVar `CLNSIG` (grounded); no concrete variant coordinate is quoted anywhere in this doc. Any unconfirmed gene/coordinate/version carries a `(VERIFY)` tag (see §10). Clinical claims stay grounded in ClinVar/GIAB truth (ADR-0004).

**0f. Standard phrasing (use everywhere; the compressed form is banned).** Never write "HG002's pathogenic variant," "HG002 ClinVar P/LP fixture," "disease-causing variant," or a bare clinical "finding." Always write:
> *"a ClinVar-P/LP-labeled variant that HG002 genuinely carries in truth, used as a positive **test fixture** for the variant gate."*

---

### 1. Panel basis — recommendation (DESIGN-NOW)

The choice is among three bases; they are not mutually exclusive. The honest answer is a **layered panel** with a CMRG truth spine.

| Basis | Truth-backing on HG002 | Medical legibility | Weakness |
|---|---|---|---|
| **(a) GIAB CMRG v1.00** (VERIFY: ~273 genes, autosomal-only) | **Strongest** — ships its *own* curated small-variant truth VCF + BED | High (curated medically-relevant genes) | Fixed curated set; build/scope to VERIFY |
| **(b) ACMG-SF** (VERIFY: v3.2 = 81 genes) | **Partial** — only the fraction inside a truth BED is gradeable | **Highest** — recognizable "actionable disease genes" | Not self-sufficient for truth; needs intersection |
| **(c) Small curated rare-disease sub-panel** | Depends on gene choice | Medium/high | Arbitrary unless anchored to (a) or (b) |

**Recommendation — layered, CMRG-spine first:**
1. **Layer A — CMRG truth spine.** CMRG v1.00 ships its own BED + truth VCF, so it is the low-risk path *and* the only source that restores trustworthy curated truth **into** the difficult medically-relevant genes (segmental duplications, high-homology paralogs, tandem repeats) that the standard v4.2.1 benchmark deliberately excludes. Fixtures here grade against the **CMRG truth VCF**.
2. **Layer B — ACMG-SF framing.** Adds legibility ("we cover the actionable disease genes ACMG recommends reporting"). Grade only the portion inside a truth BED. The **per-gene callable fraction is itself an honest QC signal**, consistent with PipeGuard's breadth-not-just-depth doctrine.
3. **Layer C — demo sub-panel.** A small subset of Layer A guaranteed truth-backed and carrying ≥1 confirmed fixture (see 0f / §6d) so a future gate has something concrete to fire on.

**Why not ACMG-SF alone:** a meaningful fraction of SF genes are exactly the hard genes v4.2.1 cannot score, so an SF-only panel would surface regions where a call cannot be honestly graded TP/FP/FN — silently undercutting the "truth-backed" claim. CMRG is the spine, not an afterthought.

**Load-bearing correctness — two truths, two BEDs.** A region inherits its truth source from which BED it fell into:
- Region ∩ **v4.2.1 high-conf BED** → grade against the **v4.2.1 truth VCF**.
- Region ∩ **CMRG v1.00 BED** → grade against the **CMRG truth VCF**.

Never grade a CMRG region against v4.2.1 truth or vice-versa — outside its own BED each benchmark asserts nothing, so a call there is unscorable. **Tag each surviving interval with its truth source** (5th BED column or encoded label, e.g. `BRCA1|highconf`, `CYP21A2|cmrg` — gene names illustrative, VERIFY membership) so the future gate reads the right answer key.

#### 1.1 How to build the panel BED (concretely)
1. **CMRG spine — no coordinate resolution.** Take the CMRG v1.00 GRCh38 BED (VERIFY exact filename/accession/md5), optionally restrict by gene name. Truth-backed regions, essentially free.
2. **ACMG-SF layer — symbol → coordinate → BED → intersect.** (a) Symbols → **HGNC IDs** first (defeat alias ambiguity). (b) HGNC → GRCh38 intervals via **MANE Select + MANE Plus Clinical** (Plus Clinical adds transcripts carrying clinical variants off the single Select); parse the MANE/GENCODE/RefSeq **GFF3 on the GRCh38 no-alt analysis set**. (c) Pad splice sites `bedtools slop -b <pad>` (VERIFY: settle on one value, ±10–20 bp; record it in the header). (d) `bedtools sort | merge`. (e) Intersect with truth so every region is gradeable:
   ```bash
   bedtools intersect -a panel.padded.merged.bed \
     -b HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed > panel.highconf.bed
   bedtools intersect -a panel.padded.merged.bed \
     -b HG002_GRCh38_CMRG_v1.00.bed > panel.cmrg.bed   # VERIFY exact CMRG BED filename
   ```
   The shippable panel is the **union** `panel.highconf.bed ∪ panel.cmrg.bed`, each interval tagged by truth source. Anything surviving **neither** intersect is **off-benchmark / ungradeable** — keep it out of the graded panel but **report its per-gene fraction** as the callable-fraction QC signal.
3. **Two traps that silently corrupt the panel.** (a) **Contig naming** — GIAB artifacts are `chr`-prefixed GRCh38; MANE/GENCODE/RefSeq vary (`chr1` vs `1`). Force `chr`-prefixed before any intersect or every intersect returns empty. (b) **Reference build** — stay on the **GRCh38 no-alt analysis set**; do not mix in alt-contigs or CHM13/T2T without a deliberate decision (CMRG also has a CHM13 release — VERIFY which build).
4. **Format — match `scripts/panel_regions.example.bed`.** 0-based half-open, `chr`-prefixed, 4th column = gene symbol / region label; add truth-source tag. This preserves `scripts/gate_giab.py -L <panel.bed>` slicing (`samtools view -M -L`) with no new slicing code.

---

### 2. Pluggable caller + caller-agnostic VCF ingest (DESIGN-NOW; parser build DEFERs to Phase 2)

**2a. Contract — PipeGuard is the reader, not the caller.** A variant caller (DeepVariant, GATK HaplotypeCaller, bcftools, FreeBayes) runs inside *someone's* Nextflow pipeline and drops a standard VCF into a run directory. PipeGuard points at that folder and ingests whatever VCF is there. The caller is **BYO**; PipeGuard owns only the read + gate (maintainer's verbatim intent).

**2b. Config-driven path resolution.** Extend the existing directory entrypoint (`run_gate_from_dir('data/mock_run_01')`) — do not invent a new one. Resolve the VCF via the run-layout config (§5), keyed by a stable artifact-kind (`vcf`), by explicit path or glob (`*.vcf.gz`). No caller name, no caller flags — just a location.

**2c. Same discipline as the metric registry.** `metrics/registry.py` keys metrics by *semantic identity* (`q30`, `mean_coverage`, `dup_rate`), not by emitting tool; the gate reads **standard VCF FORMAT/INFO fields** (`DP`, `GQ`, `FILTER`, allele depths), which are caller-independent, not caller-specific quirks.

**2d. Tolerant parsing at the boundary (data-handling guardrail 2).** `DP`/`FILTER` are near-universal; `GQ` usual; **allele balance is derived from `AD`** (`AD_alt/(AD_ref+AD_alt)`) for GATK/bcftools but emitted directly as `VAF` by DeepVariant. `QUAL` is **caller-dependent** (ADR-0013) and therefore a weak cross-caller signal. A **missing field is a signal, not a crash** — record it absent, let the gate down-weight, never raise.

**2e. New code surface (scope-honest).** Today there is **no VCF handle anywhere in `parsers.py`** (data-platform §3.6 — the panel VCF/BAM are index-only pointers). Ingest would add one tolerant reader (`parse_vcf` → per-variant records) plus the deferred `parse_vcf_stats` (bcftools stats → `ts_tv_ratio`/`n_variants`/`het_hom_ratio`). Keep it on the **bioconda side** of the two-toolchain split (`pysam`/`cyvcf2` or shell `bcftools`), not a new `uv` app dependency, unless a pure-Python reader is justified. **Scope note:** `parse_vcf`'s only consumer is the Phase-2 rules; it is designed now but is **not** on the build-now-if-time path (the eval in §4 needs no core parser — see §4/§8).

#### 2.1 Demo caller — make the loop real
- **(Recommended) bcftools on the existing panel BAM slice → a genuine called VCF.** The panel slice **already exists on disk** (`data/real-giab/HG002.GRCh38.panel.bam(.bai)`, verified 2026-07-08). ~3 shell lines, tools already in the machine-local `hackathon` conda env:
  ```bash
  bcftools mpileup -f <GRCh38_no_alt_ref> -R scripts/panel_regions.example.bed \
      data/real-giab/HG002.GRCh38.panel.bam \
    | bcftools call -mv -Oz -o data/real-giab/HG002.GRCh38.panel.calls.vcf.gz
  bcftools index -t data/real-giab/HG002.GRCh38.panel.calls.vcf.gz
  ```
  Wire as a new `--call` step in `scripts/gate_giab.py` (it has a `main()` but **no `--call` today** — a small new flag, not a free ride). Independent of the truth VCF → the eval in §4 is **not circular**. Tag output `real-giab` (a real call on real reads), distinct from the truth VCF (the answer key).
- **(Fallback, smoke-only)** feed the on-disk panel-sliced truth VCF as "the caller's output" to exercise the *reader* only. **Circular for evaluation** (P/R/F1 = 1.0) — never the EVAL-030 subject.
- **(BYO, higher fidelity — CUT to a doc sentence)** DeepVariant is the drop-in upgrade a user brings (better SNV/indel accuracy; emits `GQ`+`VAF` directly). It changes nothing about PipeGuard: same folder, same standard VCF. Name it in docs; do not build it.

**Update (2026-07-09) — built, but not as specified above.** `scripts/run_giab_pipeline.py` (§3.2.1) shipped a demo caller — `bcftools mpileup | call -mv | norm` — but as a **new standalone script**, not a `--call` flag on `gate_giab.py`, and over a **bwa-mem2-realigned** BAM it produces itself from raw fastqs, not the pre-aligned novoalign panel-slice BAM this recommendation assumed. It is real and non-circular (independent of the truth VCF) but its output (`HG002.norm.vcf.gz`) is **not yet wired into `qc_metrics.csv` or the gate** — it is index-only today (§ "What OUR demo actually writes today" above). EVAL-030 (§4 below) remains unbuilt.

---

### 3. What the gate reads (Phase 2 — deterministic rules NOT built)

**3a. Per-variant fields consumed:** `DP`, `GQ`, **allele balance** (from `AD`, or `VAF`), and **`FILTER == PASS`**. Optionally `QUAL` (flagged caller-dependent) and cohort `parse_vcf_stats` sanity signals (`ts_tv_ratio`, `het_hom_ratio`, `n_variants`). **No gnomAD AF / ClinVar significance in the gate** — annotation, not gating (strategy.md).

**3b. Routed through the metric registry.** The keys **already exist** (see §8): `variant.dp`, `variant.gq`, `variant.allele_balance` (parser `vcf_allele_balance`), `variant.titv` (source `bcftools_stats`), each `gate: variant`. They are inert vocabulary — no locator, no parser wired, no rule consuming them. Phase 2 wires them; the registry needs no schema change.

**3c. Granularity — the real design decision.** Existing QC metrics are **per-sample scalars**; variant metrics are **per-variant** (~470 rows for the chr20 smoke panel). The gate must **aggregate per-variant → per-sample `Finding`s** — e.g. "12 / 470 panel variants have DP < 10× (min 4×)" → `Category.VARIANT` → `Gate.VARIANT`, cited and content-hashed like every `Finding` (`synthesis/base.py` aggregates; the LLM never sets a verdict, ADR-0001). **This aggregation IS the Phase-2 gate — registering keys is inert; *consuming* them is building the gate.** `DecisionCard.gate_results` already iterates all three gates, so a VARIANT finding lights up the modeled-but-empty gate with no schema change.

**3d. Surface-and-decide, no pathogenicity call.** The gate reports *technical call quality* (low-DP / low-GQ / skewed-AB / non-PASS) and contributes a RERUN/HOLD/PASS-style signal — **no claim about pathogenicity, actionability, or diagnosis** (ADR-0013 verdict policy). Thresholds are runbook-configurable, **illustrative not clinical**.

**3e. UI terminology — "call-quality finding."** Because the core emits objects named `Finding` and §0f bans the bare clinical "finding," the UI must render variant `Finding`s as **"call-quality finding"** (technical), never bare "finding," so a low-DP signal is never read as a clinical finding about the variant's meaning.

---

### 4. GIAB-truth evaluation (EVAL-030) — the credibility proof (BUILD-NOW-IF-TIME)

Compare the **called VCF** (§2.1) against the **GIAB truth VCF**, inside where truth is valid, and report SNV/indel-stratified precision / recall / F1. This is what proves the caller path works on real data — **zero core code, all bioconda.**

**4a. Confine to where truth is valid.** Truth (presence *and* absence) holds **only inside the high-confidence BED**:
```bash
bedtools intersect \
  -a scripts/panel_regions.example.bed \
  -b data/real-giab/HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed \
  > eval/gradeable_regions.bed
```
For a future disease-gene panel, add the **CMRG v1.00 BED** to this union so difficult medically-relevant genes (segdups/paralogs — *PMS2, CYP21A2, SMN1, HBA1/2* — VERIFY membership) that fall **outside** v4.2.1 high-conf become gradeable; report the **callable fraction** per gene as its own honest QC signal.

**4b. Normalize both sides — mandatory.** Representation differences (indel left-alignment, multiallelic packing) cause false mismatches. Run `bcftools norm -f <ref> -m -` on **both** called and truth VCFs, and confirm **contig naming matches** (`chr20` vs `20`) against the GRCh38 no-alt analysis set.

**4c. First cut — `bcftools isec`, restricted to the gradeable BED (guardrail fix).** `isec` inputs **must be restricted to `gradeable_regions.bed` first**, or every call *outside* the high-conf BED is miscounted as a false positive — but outside the BED GIAB asserts nothing, so such a call is **unscorable, not an FP**. Restrict both normalized VCFs, then intersect:
```bash
bcftools view -R eval/gradeable_regions.bed -Oz eval/calls.norm.vcf.gz  > eval/calls.graded.vcf.gz
bcftools view -R eval/gradeable_regions.bed -Oz eval/truth.norm.vcf.gz  > eval/truth.graded.vcf.gz
bcftools isec -p eval/isec eval/calls.graded.vcf.gz eval/truth.graded.vcf.gz
# 0000=FP(call-only) 0001=FN(truth-only) 0002/0003=TP(shared)
```
Derive `precision=TP/(TP+FP)`, `recall=TP/(TP+FN)`, `F1`. **Report calls falling outside `gradeable_regions.bed` as a separate "not-truth-backed / ungradeable" count — never folded into P/R/F1.** Caveat: `isec` is position/representation-sensitive and **undercounts** matches vs. haplotype-aware tools, especially for indels — quote it as an approximation.

**4d. Real number — hap.py or vcfeval** (GA4GH-standard, haplotype-aware). Grade `calls.vcf.gz` against the truth VCF restricted by `eval/gradeable_regions.bed`, stratified SNV vs. indel. This is the defensible headline P/R/F1. (hap.py already passes the confident regions, so it does not need the 4c pre-restriction fix.)

**4e. Register as EVAL-030.** Emit a **dated, `real-giab`-tagged** evaluation artifact whose **required output fields include the graded BED path and the fraction of the panel graded** (not just prose). Faithfulness claims are valid **only** inside the graded BED — state it explicitly on the artifact.

---

### 5. Run-layout config — the artifact-kind → path seam (schema DESIGN-NOW; loader/refactor DEFER)

**5a. The problem.** `load_run` (`parsers.py:187-217`) reads exactly one physical layout — five literal filenames at the run root. `scripts/gate_giab.py` hard-codes `mosdepth/`, `fastq/`, `run/` and *reshapes* a real layout into that flat contract (that reshaping is exactly what a config should absorb). Real pipelines (nf-core/sarek) scatter outputs by tool/caller. And the registry already declares `variant.*` with `source_file: vcf` but **nothing knows where the VCF is** — the path map is the missing half.

**5b. Design — a typed, profiled, tolerant `run_layout.yaml`** shipped in-package, mirroring `metric_registry.yaml` (frozen pydantic models, `importlib.resources`, versioned, pinned on `AnalysisRun`) and the ADR-0005 config layer. A **profile** is one named artifact-kind → locator map. `default` reproduces today's flat five-file contract **byte-for-byte** (offline suite + demo unchanged). `giab_panel` maps the on-disk `gate_giab.py` layout. `sarek` is illustrative/target-state (not wired). Locator fields: `path | glob`, `parser` (dispatch key; `null` = pointer-only, never opened), `required`, `role: output|reference` (reference never gated), `on_multiple: first|all|error`, `origin`. Selection follows the existing env pattern: `PIPEGUARD_RUN_LAYOUT=default|giab_panel|/path/to/custom.yaml`, default `default`. Missing **optional** artifact → `[]`/`None` (absence is a signal); missing **required** → deterministic "missing input" finding (never fabricates a pass).

**5c. Composition.**
- **With the metric registry:** clean split joined on the shared `parser` name. Registry = vocabulary of **values** (`variant.dp` = genotype depth, `parser: vcf_format`); layout = vocabulary of **locations** (where `vcf` physically sits). Neither can set a verdict.
- **With ADR-0005 profiles:** a layout *is* a profile — `default` = lean/demo; `giab_panel`/`sarek` = granular real-pipeline. Same typed-settings + env selector, no new config mechanism.
- **With wishlist #11 canvas:** this YAML is precisely the machine-readable seam a no-code builder would emit (wiring tool-nodes → output-folders *is* an artifact-kind → path map). Defining the schema now fixes the canvas's target: canvas becomes "a GUI that writes this file," not a parallel system. **Cross-reference wishlist #11; do not build the canvas here.**

**5d. Guardrails — this locates inputs, never judges them.** (i) **Read-side only** — no path triggers tool execution (running tools stays in bioconda/Nextflow, ADR-0003). (ii) **Cannot move a verdict** — a verdict is a pure function of parsed values through rules + runbook (ADR-0001); repointing a path changes inputs, not thresholds. (iii) **Origin travels** — resolving a path never strips provenance; the `origin` field is **declarative annotation, surfaced, never a gate input**; `role: reference` artifacts (truth VCF, panel BED) are pointers never gated. (iv) **Auditability** — every resolved absolute path is recorded as a provenance-ledger event (ADR-0002); `on_multiple: error` refuses ambiguity for must-be-unique kinds.

**5e. PHI enforcement at the ingest seam (forward-looking, required).** The caller-ingest seam (§2) and the `sarek`/glob layout are exactly where a **non-GIAB** VCF can enter. The moment a non-GIAB sample enters, the G-DEID / consent guardrails (data-platform §2.1d) are no longer hypothetical. Therefore: **origin must be enforced at ingest, not assumed.** A VCF resolved by glob has **unknown origin until tagged**; it may **not** be auto-tagged `real-giab`. Unknown-origin inputs default to a **non-real, PHI-guarded posture**, and a non-`real-giab` origin must trigger the de-id/consent path before any display. Config must not be able to relabel provenance to launder it.

**5f. Scope.** **Schema is DESIGN-NOW** (paste the YAML into this doc as the target seam — it is the right shape for wishlist #11). The **loader + `load_run` refactor + `PIPEGUARD_RUN_LAYOUT` selector are DEFER**: they refactor the one tested, offline-suite-pinned working path (`parsers.py:187`) for **zero demo-visible gain**, and `PIPEGUARD_RUN_LAYOUT` would be **pydantic-settings' first use in `src/`** (a crunch-week first-use risk to raise with the maintainer, per CLAUDE.md coding-standard 4 — named but not yet used in `src/`). If ever built, ship only `default` + `giab_panel` and wire the parser-dispatch table only for kinds with a real parser today (the five CSVs + `mosdepth_summary`); leave `vcf_stats`/`bam` as `parser: null` pointer-only; `sarek` + canvas are CUT.

---

### 6. Honest framing — exact labels the doc/UI must use (required)

**6a. Panel-level banner (always visible, inseparable from the panel):**
> *"Regions are a disease-gene panel evaluated on GIAB HG002, a consented benchmark reference genome — not a patient. Variants shown are test fixtures for the variant gate, not diagnoses."*

**6b. Per-variant fixture label (never omit, inseparable from the row):** **"ClinVar-labeled test fixture (HG002 benchmark)"** — never "HG002's pathogenic variant," never "disease-causing variant," never a bare clinical "finding." Call-quality signals render as **"call-quality finding"** (§3e). **The fixture label + banner must be inseparable from any rendered variant row — the variant cannot render without them** (highest screenshot-out-of-context risk).

**6c. Do not headline the most alarming actionable-cancer genes.** Do **not** headline *BRCA1/2* or *TP53* as demo fixtures unless HG002 is **confirmed** to carry a qualifying P/LP allele there (§6d) — "PipeGuard found a pathogenic BRCA1 variant in this genome" is the single highest misread risk.

**6d. Fixture selection must be allele-level, and no concrete fixture ships unconfirmed (hard rule).** Positional overlap is insufficient. **Normalize both sides** (`bcftools norm -f <ref> -m -`), then confirm HG002's ALT equals the ClinVar ALT. Gate ClinVar on `CLNSIG ∈ {Pathogenic, Likely_pathogenic}` **and** `CLNREVSTAT` **≥1★ (prefer ≥2★ = `criteria_provided,_multiple_submitters,_no_conflicts`)**. **Record the ClinVar release date** (it changes weekly). **No specific variant may be displayed as a positive fixture until confirmed against a dated ClinVar release *and* HG002 truth GT, allele-level, normalized.** P/LP positions HG002 does **not** carry are kept explicitly as **true-negative fixtures** (the gate must not fabricate them). Carry the full provenance every time a fixture is displayed: ClinVar accession (VCV/RCV) + `CLNSIG` + `CLNREVSTAT` star level + HG002 truth GT (0/1 or 1/1) + truth source (v4.2.1 or CMRG). Evidence, assumptions, and AI narration stay in **separate fields** (ADR-0001).

**6e. ClinVar has exactly two uses — they must never merge (required).** (1) **Eval-time fixture *selection*** (§6d) — legitimate; builds the test set. (2) **Runtime gate input** — **forbidden.** State explicitly: *"ClinVar is consumed only at evaluation / fixture-build time and as displayed annotation; it must never enter the runtime verdict path for a production sample."* Without this a future contributor could wire the fixture selector into the gate and smuggle pathogenicity into the verdict while nominally satisfying surface-and-decide.

**6f. Confidence wording.** Any confidence the future gate emits is a **heuristic, not a calibrated probability** — label it as such; thresholds are illustrative/configurable, not clinical.

---

### 7. Origin + provenance

Follows the strategy.md origin-labels table, ADR-0002, ADR-0004/0007.

1. **Committed, cited artifacts (derived region/fixture definitions — no reads, no PHI):**
   a. The **panel BED** (union of `highconf` + `cmrg` intervals, truth-source-tagged). Origin: **`derived`** with an explicit source list in the provenance header — it is computed from ACMG-SF + MANE + ClinVar (non-GIAB public sources) intersected with GIAB/CMRG BEDs, so tagging it bare `real-giab` would launder its mixed provenance. Header states: source gene list + version (ACMG-SF vX.Y / CMRG v1.00), MANE/GENCODE/RefSeq version + date, GRCh38 no-alt build, splice-padding value, the two truth BEDs + versions, build date (ISO-8601 MST).
   b. A small **fixtures manifest** (positions + ClinVar accession + `CLNSIG`/star + expected HG002 GT + truth source). Origin **`derived`** (ClinVar-sourced). Accessions and expected genotypes only — **no ClinVar or GIAB payload copied in.**
2. **Fetched, git-ignored artifacts (accessions + fetch script, never committed):** extend `scripts/giab_hg002_manifest.json` + `scripts/fetch_giab_hg002.py` to add the **CMRG v1.00 truth VCF + tbi + BED** (origin `real-giab`, public/open, md5-enforced — VERIFY exact GIAB FTP paths/filenames/md5s). The **ClinVar GRCh38 VCF** is a new fetched input (record release date). The v4.2.1 truth VCF/BED are already manifested and on disk.
3. **Boundary discipline:** the truth VCFs and ClinVar VCF stay **INDEX-/input-only** (data-platform §3.6) until a real `parse_vcf` / `parse_vcf_stats` path is built. The committed panel + fixtures manifest are the only new *repo* artifacts; everything with a payload stays under git-ignored `data/real-giab/`.

---

### 8. Registry-state reconciliation (correcting GROUND 1 §4)

GROUND 1 §4 states no per-variant metrics are defined; **this is now stale.** Verified 2026-07-08: `src/pipeguard/metrics/metric_registry.yaml` declares `variant.dp`, `variant.gq`, `variant.allele_balance` (parser `vcf_allele_balance`), `variant.titv` (source `bcftools_stats`), each `gate: variant`. They are **inert vocabulary** — no locator (§5), no parser wired, no rule in `rules.py` consuming them (grep confirms zero `Category.VARIANT` findings fire). Leaving them declared-but-inert is correct; *finishing* them (locator + parser + aggregation rule) is Phase 2.

**Invariant (must be stated wherever the registry is documented):** the variant metric keys are **all technical** (`dp / gq / allele_balance / titv`). **No `clinvar_significance` or `gnomad_af` metric may ever be registered as a gating metric.** ClinVar/gnomAD are annotation and evidence only (§3a, §6e), never a gate input.

---

### 9. Tiering — design-now / build-now-if-time / phase-2 / cut

| # | Item | Source | Tier | Why |
|---|---|---|---|---|
| 1 | Framing contract + exact UI labels (§0, §6) | D1 §3 | **DESIGN-NOW** | Highest-value output; pure prose guardrail |
| 2 | Two-truths / two-BEDs routing (§1) | D1 §1 | **DESIGN-NOW** | Load-bearing correctness; prevents a real future bug |
| 3 | Caller-agnostic contract + two traps (§2) | D2 §1 | **DESIGN-NOW** | Right architecture; document, don't wire |
| 4 | Run-layout YAML **schema** as documented seam (§5b) | D3 §2 | **DESIGN-NOW** | Right shape for sarek/canvas; fix the target without building |
| 5 | Panel basis recommendation (§1) | D1 §1 | **DESIGN-NOW** | Standalone recommendation to hand off |
| 6 | Demo caller (`gate_giab.py --call`, bcftools on the on-disk panel BAM) | D2 §2.1 | **BUILD-NOW-IF-TIME** | ~3 shell lines, external, non-circular. **Built differently (2026-07-09):** `run_giab_pipeline.py` (§3.2.1) ships a real bcftools caller over its own bwa-mem2 realignment, as a new script rather than a `gate_giab.py --call` flag; output still unwired into the gate (§2.1 Update) |
| 7 | GIAB-truth eval EVAL-030 (norm → gradeable BED → isec/hap.py → dated `real-giab` artifact) | D2 §4 | **BUILD-NOW-IF-TIME** | **Zero core code**; turns "we plan a gate" into "we call real variants, here's the measured accuracy vs NIST truth" |
| 8 | `parse_vcf` VCF reader into core | D2 §2e | **DEFER (→Phase 2)** | Only consumer is the Phase-2 rules; eval (7) needs no core parser |
| 9 | Fetch + register **CMRG v1.00 BED** (ships own truth) | D1 §1.1 | **DEFER** | Cheapest *truth-backed* panel option, but no consumer this week |
| 10 | Run-layout **loader + `load_run` refactor + `PIPEGUARD_RUN_LAYOUT`** | D3 §5 | **DEFER** | Refactors the one tested path for zero demo gain; pydantic-settings first use in `src/` |
| 11 | Wire `variant.*` keys as live inputs; per-variant→per-sample `Finding` aggregation | D2 §3 | **DEFER (→Phase 2)** | This *is* the gate |
| 12 | ACMG-SF layer (HGNC→MANE GFF3→slop/merge→intersect) | D1 §1.1 | **DEFER (→Phase 2)** | Multi-step pipeline, ~4 VERIFY items, no consumer |
| 13 | ClinVar P/LP fixture extraction (download/star-filter/norm/allele-match/intersect) | D1 §6d | **DEFER (→Phase 2)** | Correct method; weeks-of-polish for a manifest nothing reads yet |
| 14 | Variant-gate **RULES** (DP/GQ/AB/FILTER thresholds → cited `Finding`s → verdict) | D2 §3 | **PHASE-2** | The real work; runbook-sourced, surface-and-decide, ADR-0001 |
| 15 | `sarek` profile, `vcf_stats`/`bam` parsers, canvas generation | D3 §5 | **CUT** | Explicitly out of hackathon scope; name once |
| 16 | DeepVariant BYO path | D2 §2.1 | **CUT (to a doc sentence)** | One sentence in the caller-agnostic doc; not a task |

**Corrected build-order dependency (important):** Design 2's proposed `parser → caller → eval → rules` has a wrong edge — the eval (7) does **not** depend on the core parser (8). `hap.py`/`vcfeval`/`bcftools isec` are external CLIs that eat VCFs and emit P/R/F1 with **zero `src/` change**. So the parser (8) belongs **with** the rules (14) in Phase 2, not on the build-now path. The honest build-now-if-time is **caller (6) → eval (7), then stop.** The committed **BUILD-NOW remains the `/api/export` + RunsBrowser slice** — it owns the build budget; the variant thread touches `src/` only in Phase 2.

---

### 10. Items to VERIFY before shipping as hard claims

1. **GIAB HG002/GRCh38 small-variant version** — v4.2.1 assumed current; a T2T "Q100"/v5 draft is emerging (VERIFY latest for this build). Exact variant count (~4M) and BED coverage % (~94–95%) are approximate.
2. **CMRG** — `(VERIFY: 273 genes, autosomal-only)`, build (GRCh38 vs CHM13/T2T); exact FTP accession paths, filenames, md5s for the truth VCF/tbi/BED.
3. **ACMG-SF** — per-version gene counts `(VERIFY: v3.0=73 / v3.1=78 / v3.2=81; possible v3.3)`; pick and cite one version.
4. **Specific gene memberships** — *PMS2, CYP21A2, SMN1, HBA1/HBA2, STRC, GBA, NEB* as CMRG members and *BRCA1/2, MLH1, MSH2, LDLR, MYH7, MYBPC3, KCNQ1, RYR1/2, TP53* as ACMG-SF — all `(VERIFY membership)`, including at the §4a eval example genes.
5. **Specific HG002 P/LP fixtures** — **hard rule (§6d):** do not quote or display any concrete reportable/PGx variant for HG002 until confirmed against a dated ClinVar release + normalized, allele-level HG002 truth GT.
6. **Splice-padding policy** — settle on one value (±10–20 bp) and record it in the panel header.
7. **CMRG BED filename/accession** used in the §1.1 intersect (`HG002_GRCh38_CMRG_v1.00.bed` is a placeholder).

---

### 11. Relevant repo paths

- Existing smoke-test BED to augment: `/Users/jchu/IdeaProjects/claude_life_science_hackathon/scripts/panel_regions.example.bed`
- Manifest + fetch to extend (CMRG + ClinVar): `/Users/jchu/IdeaProjects/claude_life_science_hackathon/scripts/giab_hg002_manifest.json`, `/Users/jchu/IdeaProjects/claude_life_science_hackathon/scripts/fetch_giab_hg002.py`
- Panel-slice driver (reuse `-L`; add `--call`/`--eval`): `/Users/jchu/IdeaProjects/claude_life_science_hackathon/scripts/gate_giab.py`
- On-disk panel slice (verified 2026-07-08): `/Users/jchu/IdeaProjects/claude_life_science_hackathon/data/real-giab/HG002.GRCh38.panel.bam(.bai)`, `.../HG002_GRCh38_1_22_v4.2.1_benchmark.panel.vcf.gz(.tbi)`, `.../HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed`
- Core seams for Phase 2: `/Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/models.py` (`Gate.VARIANT`/`Category.VARIANT` defined), `.../src/pipeguard/rules.py` (no VARIANT findings yet), `.../src/pipeguard/metrics/metric_registry.yaml` (`variant.*` keys declared, lines ~290-352, no locator/parser/rule), `.../src/pipeguard/parsers.py:187` (hard-coded five-file `load_run`)
- Proposed new committed artifacts: `scripts/panel_regions.disease.bed` (+ provenance header), a fixtures manifest, `src/pipeguard/layout/run_layout.yaml` (schema only, DESIGN-NOW)

---

## Open questions for the maintainer

*Each carries a recommendation; the workflow's own resolution is noted where it took one.*

1. Export source of truth per claim (RESOLVED as proposed; confirm). BUILD-NOW export serializes the live in-memory `_evaluate` cards, honestly labeled as a deterministic re-derivation and version-stamped (rule_pack_version + metric_registry_version + origin), NOT as ledger-derived audit provenance. TARGET-STATE audit export reads the projection built by a one-shot emit-once command. Confirm you accept "two paths, two honesty labels" rather than forcing one — the guardrail critique wanted one source of truth, but the two serve different claims (demo convenience vs. audit).

2. `origin` provenance for BUILD-NOW rows. Origin isn't persisted or reliably on the in-memory cards today. Proposal: read it from a per-run marker/manifest in the run dir, default `unknown`, and gate intake-identity export to non-real origins. Is a per-run origin marker file acceptable, or should origin ride the sample_metadata/run manifest?

3. PHI posture for the hackathon. The only "real" data is GIAB HG002, a publicly consented reference genome (not PHI), so G-PII/G-DEID are forward-looking. Confirm we can ship intake-identity export for the demo on that basis, with the de-id gate documented for when real patient runs are ingested — or do you want `submitted_by` dropped/hashed even for HG002 now (recommend: drop it now, it's never an ML feature).

4. Metric event grain for the durable path. Proposal: one `metric.parsed` event PER SAMPLE carrying the MetricValue list (matches the card grain + existing per-sample event pattern), projector fans out to rows — NOT one event per MetricValue. Confirm the grain before anyone implements the projector rule.

5. `metric_values` primary key. Proposal: composite natural key `(run_id, sample_id, metric_key)` with `content_hash` as an indexed column (matches FindingRow/CardRow). The source section proposed `content_hash` as PK; since content_hash omits run_id (covers sample_id+metric_key+analysis_run_id), the composite key is safer. Confirm.

6. Is the "deterministic archivist core" worth shipping in the demo at all, or is it fully subsumed by the BUILD-NOW `/api/export` endpoint? (Recommendation: subsumed — ship the endpoint under its plain name, keep the Archivist as spec-only.)

7. ~~Agent-slot priority: QC-triage live for the demo vs. start agent #2 pipeline-repair (blocked on `pipeline_info/execution_trace` capture that doesn't exist).~~ **Superseded (2026-07-09):** #2 pipeline-repair is **built** (T-058) and the `execution_trace` capture now **exists** (EXEC-001, T-061); this open question is resolved.


**NGS output layout (from the §3 expansion) — additional questions (none block build-now; all are naming/semantics or target-state):**

Decisions to escalate to the maintainer (each is target-state or a naming/semantics call; none blocks build-now, which is documentation only):

1. **sarek renames — keep current names or align later?** The doc §3.4 already forbids relabeling `fastq/`/`mosdepth/`/`run/` to `reads/`/`alignment/`/`coverage/` as "adopt now." Recommendation: **keep them verbatim**; `reads/` is *cut* (invented third name, matches neither code nor sarek), `mosdepth/`→`reports/mosdepth/` is *cut* (cosmetic). Confirm you want the current names frozen and any future rename made only in the same diff as its producing script.

2. **VCF home is an OPEN decision — reserve it.** DESIGN 2 proposed `variant_calling/deepvariant/HG002/…`; DESIGN 3 proposed a `variants/` sibling. They conflict, and while `run_giab_pipeline.py` (§3.2.1) now runs a real caller, its output is an unhomed git-ignored intermediate (index-only, never wired into a run dir), so there is still no run-produced VCF placed in the documented output-tree convention to home. Recommendation: **reserve the decision until a wired, first-class called VCF exists**; document `variant_calling/` (VERIFY, ungrounded) as the illustrative empty slot, and keep the truth VCF in a `benchmark/` grouping (it is *input*, not run output).

3. **Keep gVCF? — N/A today.** We emit no gVCF; "drop after joint-genotyping" is cohort/WGS framing a single-sample panel may never reach. Confirm gVCF handling only becomes real if/when a caller + joint step is added.

4. **Keep raw FASTQ? — regenerable.** Raw + trimmed FASTQ are deterministic intermediates (BAM→FASTQ, then fastp); the keeper is `fastp.json`. Recommendation: **keep on the panel (cheap), do not auto-delete in the MVP**; adopt a drop-regenerable-intermediates policy only at exome/WGS scale.

5. **BAM→CRAM intent + M5 verification.** If we ever convert: confirm **lossless-of-record** (not lossy quality-binning), expect only **≈20–40%** savings (not ~50%), and require an on-toolchain check that the NIST novoalign BAM's `@SQ` **M5** tags resolve against the pinned GRCh38 reference (+ `.fai`; `.dict` not needed to decode) before conversion — else silent decode failure later.

6. **ArtifactRef registry + `MANIFEST.sha256` — build when agents exist.** Both are DEFER: glob already gives findability at panel scale; the registry is an O(1)/agent-friendly upgrade for an archivist that is currently spec-only. Confirm it stays a rebuildable projection off the event ledger, off the critical path.

7. **`pct_reads_identified` semantic mismatch — rename the column or document it?** The value is a fastp *pass-filter* (quality) rate, but the column name implies Illumina *barcode-identification* (reads assigned to a known barcode). Decide whether to rename the metric key or annotate the runbook so no one reads it as a demux assignment rate.

8. **`run_id` identity.** The target per-run root keys on the `analysis_run` UUIDv7 and assumes multi-sample runs share a root with per-sample subdirs. Confirm the 1:1 mapping (one filesystem run root ↔ one `analysis_run` event) before any per-run layout is built.

9. **Unverified sarek filenames.** `<sample>.md.cram` / `.md.cram.metrics`, `joint_germline.vcf.gz`, `.recal.cram`, VEP/snpEff outputs, Picard `hs_metrics.txt`, and the `preprocessing/`/`variant_calling/` dir names are tagged `(VERIFY)` — confirm against a real sarek output tree before any of them is cited as canonical. Likewise, fastp/mosdepth/samtools/bcftools/MultiQC/sarek licenses are "reported, not verified" in-repo — do not assert them.


**Variant-gate substrate (from the design workflow) — additional questions (none block build-now; the export slice owns the build budget):**

**Escalate to the maintainer before any variant build:**

1. **Attempt any variant-gate MVP this weekend? (the load-bearing decision.)** Recommendation: **no gate rules.** The deterministic VARIANT rules are the only piece that makes the panel/parser/config/fixtures pay off in the demo, and they are correctly Phase 2. The three designs collectively *are* the variant subsystem sliced into "small" hats; every slice's payoff is locked behind the deferred rules. Confirm you agree the committed BUILD-NOW stays `/api/export` + RunsBrowser and the variant thread stays out of `src/` until Phase 2.

2. **If any variant time remains after export lands, spend it on the eval — confirm.** The single highest-leverage, zero-`src/`-code item is EVAL-030: bcftools-call the on-disk panel BAM → grade vs NIST truth inside the high-conf BED → one dated `real-giab` P/R/F1 number. Confirm this (not the parser, not the config refactor, not the panel pipeline) is where surplus hours go. Caveat: it competes directly with export for the last hours — if export is not rock-solid, this waits.

3. **Demo caller choice.** Recommendation: **bcftools `mpileup | call`** on the existing panel BAM (real call, independent of truth → non-circular, tools already in the `hackathon` conda env). Alternatives: feed the on-disk truth panel VCF as input (smoke-test the reader only — circular, never for eval); DeepVariant BYO (higher fidelity, but a doc sentence, not a task). Confirm bcftools.

4. **Panel basis + whether to fetch CMRG now.** Recommendation: **CMRG v1.00 spine + ACMG-SF framing + tiny demo sub-panel**, but ship it as *design* — for the demo use the existing chr20 smoke panel (~470 truth records / ~71k reads). If you want a concrete "disease-gene" artifact, the bounded option is fetch+register the **CMRG v1.00 BED only** (no MANE, no ClinVar, no ACMG-SF). Decide: chr20 smoke panel only, or also fetch the CMRG BED (bounded, but no consumer this week)?

5. **pydantic-settings first use in `src/`.** The run-layout `PIPEGUARD_RUN_LAYOUT` selector would be the **first** pydantic-settings use in `src/` (CLAUDE.md coding-standard 4 names it as intended but it is unused today). Introducing a new config mechanism in crunch week is a poor bet — recommendation is DEFER the loader/refactor and ship only the schema in the doc. Confirm, or approve introducing pydantic-settings now.

6. **PHI posture at the ingest seam.** The caller-ingest / glob-layout seam is exactly where a non-GIAB patient VCF could enter, at which point G-DEID/consent stop being hypothetical. Recommendation: enforce origin **at ingest** — an ingested VCF may never be auto-tagged `real-giab`; unknown-origin inputs default to a PHI-guarded posture and trigger the de-id/consent path before display. Confirm this is the required posture (it keeps the HG002-only demo clean while making the production seam honest).

7. **ClinVar release pinning + splice padding (only if the panel/fixtures are pursued).** Which dated ClinVar release do we pin, and what star threshold (≥1★ vs ≥2★)? And settle one splice-padding value (±10–20 bp) recorded in the panel header. Plus resolve the open `(VERIFY)` items before any gene/coordinate/version ships as a hard claim: GIAB v4.2.1 currency (vs emerging Q100/v5), CMRG gene count/build/autosomal scope, ACMG-SF per-version counts, and specific gene memberships.

---

*Marker legend — distinguish claim types where confusion is likely:*
**Fact** · **Assumption** · **Decision** · **TODO**.
