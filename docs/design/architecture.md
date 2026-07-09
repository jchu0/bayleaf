# Architecture — System Shape

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-09 (MST) |
| **Audience** | software / bioinformatics / reviewers |
| **Related** | [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md), [ADR-0016](../adr/ADR-0016-postgres-port.md), [schemas.md](../data/schemas.md), [metric_registry.md](../data/metric_registry.md), [provenance.md](../data/provenance.md) |

## Overview

PipeGuard is the **operations layer** on top of a bioinformatics pipeline. For each
sample in a sequencing run it recommends **proceed / hold / rerun / escalate** with
**cited evidence**, and an advisory AI agent accelerates triage ("comb the logs" → a
grounded suggestion). The load-bearing invariant: **rules decide; AI narrates and
advises** (ADR-0001). Domain: rare-disease germline DNA panel, Illumina short-read.

## The three-gate model (ADR-0013)

Every finding and verdict is labelled with the gate it came from:

1. **preflight** — intake: barcode/index integrity, sample identity, required metadata,
   pipeline/operational failures ("did we even sequence/produce usable data?").
2. **qc** — per-sample QC: yield/Q30, coverage depth *and* breadth, contamination,
   sample-swap (NGSCheckMate).
3. **variant** — variant-level (DP/GQ/allele balance, gnomAD/ClinVar) — Phase 2.

`RERUN` is reserved for operational/file-system failures; a data-quality problem is a
`HOLD` (surface-and-decide, not prescribe).

## Component map

```
 run dir ─▶ parsers ─▶ RunArtifacts ─▶ rules ─▶ Finding[] ─▶ synthesis ─▶ DecisionCard[]
                                        ▲ │                                   │  │
                    metric registry ────┘ │  (rules normalize each metric to  │  │
                    (canonical decimals,  │   a canonical decimal via the     │  │
                     ON the critical path)│   registry, then gate)            │  │
                                          ├────────▶ provenance: EventLedger ◀─┘  │ (append-only,
                                          │            (analysis_run/finding/       ADR-0002)
                                          │             verdict/notification events)
                            triage agent ─┘  (advisory, off the critical path, ADR-0009)
                                                          │           notify/ ◀────┘
      ┌───────────────────────────────────────────────────┤        (outbound, off by
      ▼                          ▼                         ▼         default, ADR-0010)
 app/ Streamlit           api/ FastAPI  ───────────▶  frontend/ React
 (offline fallback)       (read-API seam, ADR-0010)   (Vite+Tailwind, ADR-0014)
```

1. **Core (`src/pipeguard/`), framework-agnostic.**
   - `parsers` → a typed `RunArtifacts` bundle (tolerant: a missing field is a signal).
   - `metrics` — the **metric registry** (versioned `metric_registry.yaml` + `MetricValue`):
     resolves each source key to a canonical `our_key` and normalizes the value to a canonical
     unit. **ON the QC-gate critical path** (T-024/T-025): `rules` normalizes through it before
     thresholding, so drift in a source's raw unit can't silently move a verdict. See
     [metric_registry.md](../data/metric_registry.md) + [schemas.md](../data/schemas.md) §QC (units contract).
   - `rules` — the trust anchor: computes cited, immutable `Finding`s; never guesses. Gates each
     metric on its **canonical (normalized) value vs a canonical-decimal threshold** keyed on
     `our_key`; a missing field yields no `MetricValue` (a signal, not a crash).
   - `models` — the pydantic data contract; `Finding`/`Evidence` are frozen + content-hashed,
     each `Finding` derives its gate + a rule-version-independent signature.
   - `runbook` — operator-configurable QC thresholds (keyed on `our_key`, canonical decimals) + gate policy.
   - `synthesis` — verdict aggregation (deterministic) + narration (stub or Claude).
   - `identifiers` — UUIDv7 ids, content hashing, UTC time.
2. **Provenance seam (`provenance.py`, ADR-0002).** `run_gate` emits an append-only
   event trail into an `EventLedger` (in-memory + JSONL), anchored to one `AnalysisRun`.
   The event log is authoritative; the relational DB is a rebuildable projection via the
   `Repository` port + `rebuild-db`, selected by `get_repository()` — SqliteRepository *and* a
   guarded, off-by-default PostgresRepository (ADR-0002/0016).
3. **Advisory agents (OFF the deterministic critical path).** The QC-triage agent (`triage/`,
   ADR-0009/0012) grounds a `TriageNote` in a curated corpus; the off-gate feedback-triage agent
   (`api/feedback_agent.py`, ADR-0016) categorizes the in-app feedback corpus.
4. **Delivery layers (thin, over the core).** `app/` Streamlit (offline demo / fallback);
   `api/` FastAPI — the production read-API seam (ADR-0010/0014/0016); `frontend/` React —
   **all 8 operator screens built + migrated to the light-theme handoff, plus the Pipeline
   Builder**: run overview → intake/preflight → decision cards → agent triage → review queue →
   provenance → monitoring → settings → pipeline builder (a `DecisionCard` carries `run_id`).
   The `api/` surface (all additive / backward-compatible; the core is untouched — sorting,
   paging, aggregation, and product writes live in `api/`, never `src/pipeguard/`):
   - **Runs read-API.** `GET /api/runs` (+ `/{id}`, `/{id}/cards/{sample}`, `/{id}/artifacts`).
     Each `RunSummary` now carries `platform` + `run_date` (parsed from the SampleSheet
     `[Header]`) and an **honest run-lifecycle `status`** — `running` | `needs_review` |
     `released`, derived from provenance (`_run_status`): `running` until the run's
     `ANALYSIS_RUN_COMPLETED` event lands, then `needs_review` if any sample is actionable, else
     `released`. It is a run-lifecycle label, **NOT** a per-sample verdict (ADR-0001), and fixes
     a bug that mislabeled a still-running / 0-attention run *Released*. `GET /api/runs` also
     gained backward-compatible `verdict`/`q`/`sort`/`page`/`limit` params (bare call =
     byte-identical body; pagination only when `limit` is given, totals on `X-PipeGuard-*`
     response headers).
   - **Monitoring aggregate.** `GET /api/monitoring?window={7d|14d|30d|all}` returns one
     pre-aggregated dashboard payload (fleet KPIs, per-run rows, per-gate flagged/total, ranked
     recurring signatures) so the frontend renders from a single response instead of fanning out
     a detail fetch per run. Its `auto_proceed_pct` is a **heuristic** throughput ratio — a
     display number, not a calibrated probability (life-science guardrail 2). Aggregation
     reuses `_aggregate_metrics()` and stays in the API layer.
   - **Off-gate product writes.** `POST /api/feedback` → a pluggable `FeedbackStore`; `POST
     /api/pipelines` (+ `GET /api/pipelines`, `GET /api/pipelines/{name}`) → a pluggable
     pipeline-graph store (see Swappable seams). Both are **product state OFF the decision
     gate** — a saved graph or a feedback note never becomes a verdict, finding, or ledger
     event (ADR-0001).
5. **Outbound notify seam (`notify/`, ADR-0010).** An optional `run_gate(notifier=…)` hook
   turns each *actionable* card (HOLD/RERUN/ESCALATE; clean cards are skipped) into a
   notification, tailored per verdict category (identity risk / re-run / borderline-QC) with
   the cited observed-vs-expected evidence. Like every other seam it **formats what the gate
   decided, never a verdict** (ADR-0001): stub-first ($0, in-memory), Slack adapter off by
   default, live post armed only by `PIPEGUARD_SLACK_LIVE`, and every send recorded as a
   `notification.emitted` ledger event. `python -m pipeguard.notify <run_dir>` is the CLI.

## Data flow

`load_run` → `evaluate_run` (rules **normalize each metric through the registry**, then →
`Finding[]` per sample) → `run_gate` (synthesize each sample → `DecisionCard`; emit the event
trail; anchor cards to the `AnalysisRun`; optionally dispatch actionable cards through an
injected `notifier`) → the FastAPI read-API serves cards + events + config → the React
frontend renders them. The triage agent is invoked on demand per flagged card and never
re-enters the verdict path. The read-API shapes those cards for screens without re-entering the
core: it labels each run with an honest lifecycle `status` read from the provenance trail,
filters/sorts/paginates the run list, and pre-aggregates the monitoring roll-up
(`GET /api/monitoring`) so a dashboard renders from one response. The Pipeline Builder's
save/version writes (`POST /api/pipelines`) land in a **separate product store**, off the gate —
they never enter `load_run → evaluate_run` or the ledger.

## Invariants

1. **Rules decide; AI is advisory** — never sets/overrides a verdict or confidence (ADR-0001).
2. **AI is OFF by default** with a deterministic fallback; both AI seams flip via env, $0 by default (ADR-0006).
3. **Event log is authoritative**; the DB is a disposable, rebuildable projection (ADR-0002).
4. **Core stays framework-agnostic** — no Streamlit/FastAPI/React imports in `src/pipeguard/`; ports & adapters (ADR-0003).
5. **Findings are immutable + content-hashed**; confidence is omitted until grounded.
6. **Off-gate product state never re-enters the gate** — in-app feedback and saved Pipeline
   Builder graphs are written by dedicated `api/` seams to their own stores; no product write
   becomes a verdict, finding, or authoritative ledger event (ADR-0001).

## Swappable seams (the flex points)

| Seam | Switch | Default |
|---|---|---|
| Synthesizer (narration) | `PIPEGUARD_SYNTHESIZER=stub\|claude` | stub ($0) |
| Triage agent | `PIPEGUARD_TRIAGE_AGENT=stub\|claude` | stub ($0) |
| Notify (outbound) | `PIPEGUARD_NOTIFIER=stub\|slack`; `PIPEGUARD_SLACK_LIVE=1` to arm the live post | stub ($0, no network) |
| Metric registry (normalization) | versioned `metric_registry.yaml` + `our_key` mapping — add/remap a source metric without touching rules | canonical decimals; ON the critical path |
| Repository (persistence) | `Repository` port; SqliteRepository **and** guarded PostgresRepository built (ADR-0016), `get_repository()` selects | SQLite + JSONL (Postgres off by default) |
| Feedback sink (off-gate) | `FeedbackStore` port (`api/feedback_store.py`); jsonl/sqlite/postgres, degrade-to-JSONL (ADR-0016) | JSONL |
| Pipeline-graph store (off-gate product) | `PIPEGUARD_PIPELINE_STORE=jsonl\|sqlite\|postgres` (`api/pipeline_store.py`); mirrors the feedback sink — degrade-to-JSONL, never logs the DSN (ADR-0016) | JSONL |
| Deployment | ports & adapters; Nextflow compute portability (ADR-0003) | local |

Unlike the AI/notify seams (off by default, adapter-swapped at the edge), the **metric registry
is on the critical path** — its "flex" is that new tool keys or unit changes are absorbed by the
versioned YAML/mapping, not by editing `rules`, keeping verdicts byte-identical across the change.

## Deployment

Local today: Streamlit (offline) + FastAPI (`uvicorn`) + React (Vite). The ports-&-adapters
boundary and Nextflow (compute) carry portability to Slurm / AWS later (ADR-0003, wishlist).
The core has no cloud/DB coupling; **both** repository adapters are built — `SqliteRepository`
(default) and a guarded, off-by-default `PostgresRepository` (ADR-0016, with a
`deploy/postgres/docker-compose.yml` + a compose-gated live test verified green). IaC remains a
Phase-2+ concern.
