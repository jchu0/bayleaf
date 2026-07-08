# Architecture — System Shape

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | software / bioinformatics / reviewers |
| **Related** | [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md), [schemas.md](../data/schemas.md), [provenance.md](../data/provenance.md) |

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
                                          │                                   │
                                          ├────────▶ provenance: EventLedger ◀┘  (append-only,
                                          │            (analysis_run/finding/       ADR-0002)
                                          │             verdict events)
                            triage agent ─┘  (advisory, off the critical path, ADR-0009)
                                                          │
      ┌───────────────────────────────────────────────────┤
      ▼                          ▼                         ▼
 app/ Streamlit           api/ FastAPI  ───────────▶  frontend/ React
 (offline fallback)       (read-API seam, ADR-0010)   (Vite+Tailwind, ADR-0014)
```

1. **Core (`src/pipeguard/`), framework-agnostic.**
   - `parsers` → a typed `RunArtifacts` bundle (tolerant: a missing field is a signal).
   - `rules` — the trust anchor: computes cited, immutable `Finding`s; never guesses.
   - `models` — the pydantic data contract; `Finding`/`Evidence` are frozen + content-hashed,
     each `Finding` derives its gate + a rule-version-independent signature.
   - `runbook` — operator-configurable QC thresholds + gate policy.
   - `synthesis` — verdict aggregation (deterministic) + narration (stub or Claude).
   - `identifiers` — UUIDv7 ids, content hashing, UTC time.
2. **Provenance seam (`provenance.py`, ADR-0002).** `run_gate` emits an append-only
   event trail into an `EventLedger` (in-memory + JSONL), anchored to one `AnalysisRun`.
   The event log is authoritative; the relational DB is a rebuildable projection via the
   `Repository` port + `rebuild-db` (SqliteRepository built; ADR-0002).
3. **Triage agent (`triage/`, ADR-0009/0012).** Advisory `TriageNote` grounded in a
   curated knowledge corpus via a retrieval interface — OFF the deterministic critical path.
4. **Delivery layers (thin, over the core).** `app/` Streamlit (offline demo / fallback);
   `api/` FastAPI read-API (the production seam); `frontend/` React (run overview → decision
   cards + triage → provenance → monitoring/settings).
5. **Outbound notify seam (`notify/`, ADR-0010).** An optional `run_gate(notifier=…)` hook
   turns each *actionable* card (HOLD/RERUN/ESCALATE; clean cards are skipped) into a
   notification, tailored per verdict category (identity risk / re-run / borderline-QC) with
   the cited observed-vs-expected evidence. Like every other seam it **formats what the gate
   decided, never a verdict** (ADR-0001): stub-first ($0, in-memory), Slack adapter off by
   default, live post armed only by `PIPEGUARD_SLACK_LIVE`, and every send recorded as a
   `notification.emitted` ledger event. `python -m pipeguard.notify <run_dir>` is the CLI.

## Data flow

`load_run` → `evaluate_run` (rules → `Finding[]` per sample) → `run_gate` (synthesize each
sample → `DecisionCard`; emit the event trail; anchor cards to the `AnalysisRun`) → the
FastAPI read-API serves cards + events + config → the React frontend renders them. The
triage agent is invoked on demand per flagged card and never re-enters the verdict path.

## Invariants

1. **Rules decide; AI is advisory** — never sets/overrides a verdict or confidence (ADR-0001).
2. **AI is OFF by default** with a deterministic fallback; both AI seams flip via env, $0 by default (ADR-0006).
3. **Event log is authoritative**; the DB is a disposable, rebuildable projection (ADR-0002).
4. **Core stays framework-agnostic** — no Streamlit/FastAPI/React imports in `src/pipeguard/`; ports & adapters (ADR-0003).
5. **Findings are immutable + content-hashed**; confidence is omitted until grounded.

## Swappable seams (the flex points)

| Seam | Switch | Default |
|---|---|---|
| Synthesizer (narration) | `PIPEGUARD_SYNTHESIZER=stub\|claude` | stub ($0) |
| Triage agent | `PIPEGUARD_TRIAGE_AGENT=stub\|claude` | stub ($0) |
| Notify (outbound) | `PIPEGUARD_NOTIFIER=stub\|slack`; `PIPEGUARD_SLACK_LIVE=1` to arm the live post | stub ($0, no network) |
| Repository (persistence) | `Repository` port; SqliteRepository built → Postgres later | SQLite + JSONL |
| Deployment | ports & adapters; Nextflow compute portability (ADR-0003) | local |

## Deployment

Local today: Streamlit (offline) + FastAPI (`uvicorn`) + React (Vite). The ports-&-adapters
boundary and Nextflow (compute) carry portability to Slurm / AWS later (ADR-0003, wishlist).
The core has no cloud/DB coupling; the repository adapter (`SqliteRepository`) is built,
and a Postgres adapter + IaC are Phase-2+ concerns.
