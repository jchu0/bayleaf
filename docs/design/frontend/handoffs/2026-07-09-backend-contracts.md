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
- Response headers: `X-PipeGuard-Total-Count` (always, pre-pagination) + `X-PipeGuard-Page` / `X-PipeGuard-Limit` (when `limit` given). All three are CORS-exposed.

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

## What is NOT built (so design plans around it)

1. **Config/settings authoring store** (the Settings `draft→save→approve` + sanity-guardrails
   backend) — deferred (T-047), because its validation is coupled to design's settings surface.
2. **The pipeline approve transition + auth/RBAC enforcement** — fields are reserved; the state
   machine + real principals are the next backend step once the flow is designed.
3. Any `frontend/` change — untouched; consuming all of the above is the implementation step.
