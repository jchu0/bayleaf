# Backend contracts for the frontend — new fields & endpoints (2026-07-09)

| Field | Value |
|---|---|
| **Purpose** | Pin the concrete field/endpoint names a parallel backend build shipped, so the design handoff + its eventual React implementation cite **real** names, not placeholders. Companion to [2026-07-09-review-to-design.md](2026-07-09-review-to-design.md) — the backend half of several items that brief tagged "needs a new field/endpoint". |
| **Audience** | claude design (+ whoever implements the handoff) |
| **Status** | Shipped + tested (offline suite green). All additive/backward-compatible — nothing below changes an existing response with no params. |
| **Related** | [architecture.md](../architecture.md) · [data-platform-and-archivist.md](../data-platform-and-archivist.md) · [functional.md](../../requirements/functional.md) · [ADR-0016](../../adr/ADR-0016-postgres-port.md) · [journal](../../journal/2026-07-09-backend-parallel-build.md) |

> These are **available now** in `api/`. The frontend does not consume them yet (no `frontend/`
> files were touched) — wiring them up is the design→implementation step. Each entry says what
> the UI should do with it.

## 1. `RunSummary` gains `status` + `platform` + `run_date` (fixes the "Released" mislabel)

`GET /api/runs` (list) and `GET /api/runs/{id}` → `summary` now include three additive fields:

| Field | Type | Meaning |
|---|---|---|
| `status` | `"running" \| "needs_review" \| "released"` | Honest run **lifecycle** (NOT a verdict): `running` until the run's completion event lands, then `needs_review` if any sample is actionable, else `released`. |
| `platform` | `string \| null` | Instrument platform from the SampleSheet `[Header]` (e.g. `"NovaSeq"`). |
| `run_date` | `string \| null` | Raw ISO date string from the `[Header]` (not a datetime); `null` if absent. |

**Frontend:** RunOverview should read `summary.status` directly instead of inferring "Released"
from `n_attention === 0` (review point #b / brief §5b) — a still-running run with 0 attention is
`running`, not `released`. Put `platform` + `run_date` in the run subtitle. `status` values map
cleanly to a status pill (`running`/`needs_review`/`released`).

## 2. `GET /api/runs` query params (pagination + search + sort)

All optional; **no params → byte-identical to today** (safe to adopt incrementally):

- `verdict` — keep runs with ≥1 sample of that verdict. Unknown → `400`.
- `q` — run_id substring filter.
- `sort` — one of `run_id,-run_id,run_date,-run_date,n_samples,-n_samples,n_attention,-n_attention` (default `run_id` asc). Unknown → `400`.
- `page`, `limit` — 1-based; pagination applies **only when `limit` is given**. `<1` → `422`.
- Response headers: `X-Bayleaf-Total-Count` (always, pre-pagination) + `X-Bayleaf-Page` / `X-Bayleaf-Limit` (when `limit` given). All three are CORS-exposed.

**Frontend:** the runs list scale kit (brief §1/§5b) wires to these. Body stays `RunSummary[]`;
read the total off the header. Works for either scale model (infinite-scroll or pages).

## 3. `GET /api/monitoring` — server-side, windowed aggregate (kills the N-fan-out)

`GET /api/monitoring?window={7d|14d|30d|all}&signatures_limit={int}` → one pre-aggregated payload:

```
{ window, n_runs_excluded_no_date, n_signatures_total,
  overall: { n_runs, n_samples, n_attention, verdict_counts:{proceed,hold,rerun,escalate}, auto_proceed_pct },
  runs:       [ { run_id, run_date, n_samples, counts:{} } ],   // chronological by run_date
  gates:      [ { gate, flagged, total } ],                     // for pass-rate
  signatures: [ { signature, rule_id, title, gate, count } ] }  // recurring, ranked
```

Notes: `auto_proceed_pct` is a **heuristic** throughput ratio (`null` when 0 samples), *not* a
calibrated confidence — label it as such in the UI. Dated windows drop runs lacking a header date
(counted in `n_runs_excluded_no_date`). Unknown `window` → `400`; `signatures_limit < 1` → `422`.

**Frontend:** Monitoring.tsx should drop its `Promise.all(runs.map(api.run))` N-fan-out and read
this instead (brief §5d); the stale "not yet windowed" label goes away — the window is real now.

> Honest caveat: windows anchor on wall-clock now; the committed fixtures are dated 2026-07-07..09,
> so dated windows only stay populated near July 2026. `window=all` is always correct.

## 4. `POST/GET /api/pipelines` — Pipeline Builder save/version (draft→approve reserved)

A product-domain store off the decision gate. The stored `PipelineGraph` is a **tolerant versioned
envelope** — `graph` is arbitrary JSON kept as-is, so the builder's node/edge shape can churn
without a migration.

- `POST /api/pipelines` → `201`. Body (`extra="forbid"`): `{ name (slug), schema_version (default "builder/0.1"), graph (any JSON object), profile? }`. The client **must not** send `id`/`version`/`status`/`*_by` (→ `422`). Response: `{ id, name, version, schema_version, created_at, status }` — `version` is server-authored + monotonic per `name`; `status` is `"draft"` on save.
- `GET /api/pipelines` → latest version of each distinct name. `GET /api/pipelines/{name}` → all versions (404 if none).
- Stored envelope also carries the **reserved review flow** (per the builder-versioning decision): `status` ∈ `draft|pending_review|approved` (default `draft`) + `submitted_by`/`reviewed_by`/`approved_by` — **server-authored** when auth lands, never client-set (so no identity/PII via the body). The approve transition + auth are a not-yet-built seam.

**Frontend:** the Builder's Save/version/approval affordances (brief §4b–§4h) wire here. Design a
title→slug step (`name` is charset-locked). The draft→approve UI can rely on `status` + the `*_by`
fields existing on read; the transition endpoint is still to come.

## 5. Batch 2 (later 2026-07-09) — auth, RBAC surfaces, card readout, Tier-0 params

**5a. Auth headers (RBAC).** Every write/transition below is gated by a role. Send two request
headers on those calls: `X-Bayleaf-Actor: <user-id>` + `X-Bayleaf-Role: viewer|reviewer|approver`
(today's UI `a.rivera` / `Reviewer` becomes these). With no headers the backend uses a permissive
**dev-default** (`dev` / `approver`) so nothing breaks — but a real deployment enforces them. Read
the role to show/hide approve controls. Insufficient role → `403`. (Dev shim; ADR-0017.)

**5b. `/api/runs` Tier-0 params** (additive on the runs list): `status=running|needs_review|released`
filter; `q` now matches **run_id OR platform** (case-insensitive — the "search run id or platform"
box); sort aliases `recent|urgent|date` (plus the canonical tokens). **Per-status facet counts** ride
on an `X-Bayleaf-Status-Counts` header (JSON `{running,needs_review,released}`, CORS-exposed) — the
All/Needs-review/Sequencing/Released chips read totals from it, independent of the active page/filter.
Note: the backend value is `needs_review` (map to your `review` label on display).

**5c. Decision-card QC readout.** `GET /api/runs/{id}/cards/{sid}/qc-readout` → `{ header, readout }`:
`readout` is gate-grouped rows `{ metric, label, observed_display, threshold_display, status: pass|borderline|fail|not_gated, flagged }` (borderline = missed the gate but not past hard-fail); `header`
carries sample_type / origin / library_prep + a `not_captured` list (never fabricated). This is the
hero QC table (brief §5a). Core card unchanged — it's a projection.

**5d. Settings authoring** (`/api/settings/thresholds`). `POST` (role reviewer+) saves a **draft**
config-override `{ name (slug), payload (JSON) }` → `201 { id, name, version, status, submitted_by }`;
`GET` = latest per name; `GET /{name}` = versions; `POST /{name}/approve` (approver-only) → approved +
`approved_by`. Versioned, audited, sanity-guardrailed. Does **not** change the live runbook yet.

**5e. Review-queue / tickets** (`/api/review/tickets`). `POST` (reviewer+) creates `{ run_id, sample_id,
gate, verdict, rule_id, title, priority }`; `GET?status=&run_id=&rule_id=` lists; `POST /{id}/action`
`{ action: acknowledge|resolve|escalate|suppress|reopen }` (resolve/suppress approver-only) transitions
`open→in_review→resolved` with an actor+timestamp audit trail. Off the gate. This is the escalation
target for Monitoring (count ≥ 3) and the triage queue.

**5f. Pipeline lifecycle** (extends §4). `POST /api/pipelines/{name}/submit` (reviewer+, draft→pending_review),
`/approve` (approver-only, → approved + diff baseline), `/dry-run?run_id=` (READ-ONLY — resolves each
locator vs a real run dir → `matched|ambiguous|missing`; **never runs anything**), `GET /{name}/diff`
(working vs last-emitted). Only an approved graph is "blessed."

## What is NOT built (so design plans around it)

1. **Decision-card CORE enrichment** — per-gate sub-verdict rollup, the linked-sample cross-link
   (S4↔S5 swap), sample-provenance metadata, context-rail fields. These touch the core card and were
   deliberately off this burst (gate-output risk); the §5c readout is the projection-safe subset that
   shipped.
2. **Tier-2 north-star** (T-057): run submissions/ingest + samplesheet upload, the BaseSpace connector,
   conversational multi-turn triage chat, the pipeline-repair + archivist agents, and the run hand-off.
   The hand-off/ingest ones must preserve **compose ≠ execute** (emit + hand off, never run).
3. **Real auth** behind `X-Bayleaf-*` (today a dev shim) + the **median-review-time** KPI wiring
   (the review store already records the timestamps).
4. Any `frontend/` change — untouched; consuming all of the above is the implementation step.
