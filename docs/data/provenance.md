# Provenance & Event Ledger

| Field | Value |
|---|---|
| **Status** | Active (Phase 1 seam built; DB projection + `rebuild-db` implemented) |
| **Last updated** | 2026-07-11 (MST) |
| **Audience** | software / bioinformatics |
| **Related** | [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md), [ADR-0016](../adr/ADR-0016-postgres-port.md) (pluggable-store family), [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) (`data.exported` share egress), [schemas.md](schemas.md), [qc_metrics.md](qc_metrics.md), `src/bayleaf/provenance.py`, `src/bayleaf/engine.py`, `src/bayleaf/rules.py`, `src/bayleaf/persistence/`, `api/share_store.py`, `api/main.py` (`share_run`), [journal 2026-07-11 d2-d3](../journal/2026-07-11-d2-d3-share-egress.md), [journal 2026-07-11 share-store persistence](../journal/2026-07-11-share-store-persistence.md) |

## Overview

The gate is event-driven (ADR-0002): every gate execution is an **AnalysisRun**,
and every meaningful step emits an **append-only ProvenanceEvent** into an
**EventLedger**. The **event log is authoritative**; a queryable relational DB is a
*rebuildable projection* of it (Phase 2, with strict-replay determinism). Phase 1
ships the in-memory ledger with optional JSONL persistence.

## The AnalysisRun anchor

One `AnalysisRun` (`arun_…`) per gate execution is the anchor every finding, card,
and event references. Phase 1 records the **gate provenance** — `rule_pack_version`,
the runbook's metric set, `generated_by`, and start/complete timestamps. Recording the full
**pipeline-provenance manifest** on the AnalysisRun (sarek `params_hash`; the
`execution_trace` artifact ref + hash) is still a Phase-2 addition that needs real sarek data
(see [nf-core-conventions](nf-core-conventions.md)) — but note the execution trace *itself* is
**already read as a gate input** (EXEC-001; see the Event-vocabulary note below). Reading the
trace on the gate and recording it as provenance metadata here are two different things.

## Event vocabulary

`EventType` mirrors the schemas.md event vocabulary:

1. **Emitted today** by `run_gate`: `analysis_run.started` → per sample
   (`sample.registered`, `finding.emitted`, `verdict.decided`) → `analysis_run.completed`.
   When a `notifier` is wired (off by default), one `notification.emitted` per actionable
   card follows completion — auditing the outbound side effect (ADR-0010).
2. **Reserved** (emitted as their producers land): `run.registered`,
   `artifact.ingested`, `metric.parsed` (Phase 2 ingest), `ticket.actioned`,
   `resolution.recorded` (ticketing phase).
3. **Emitted by the read-API, not the gate** — `data.exported` (2026-07-11, ADR-0018 D3):
   `POST /api/runs/{run_id}/share` (`api/main.py`, approver-gated) applies the conservative
   Safe-Harbor-**style** scrub (`api/safe_harbor.redact_record`) to a run's already-decided
   cards and records the egress as a `DATA_EXPORTED` `ProvenanceEvent` — an **egress transform
   only**; it reads already-computed `DecisionCard`s and never a rule/verdict/gate input
   (ADR-0001). Its `outputs` carries one `EntityRef(entity_type="share_bundle",
   content_hash=…)` pinned to a sha256 of the exact emitted bytes, so the trail entry can't
   drift from what actually left. **Not written to the gate's own `EventLedger`** — see below.

## A second, separate sink for share events (`api/share_store.py`)

`data.exported` events do **not** append to the same `EventLedger` the gate produces. The gate's
ledger is a **deterministic re-derivation** per run (`api.main._evaluate` is `@lru_cache` — the
same run dir always replays to the same trail) and must stay byte-stable and cacheable. A share is
the opposite: a **live, actor-driven side effect** that must survive both that cache and a process
restart, so it can't be folded into a cached re-derivation. `api/share_store.py` is therefore a
**standalone, pluggable sink** — a `ShareStore` Protocol keyed on `ProvenanceEvent`, queried by
`for_run(run_id)` (oldest-first) — env-selected via `BAYLEAF_SHARE_STORE=jsonl|sqlite|postgres`
(default `jsonl`), matching the shape of the other four off-gate sinks
(feedback/pipeline/review/settings, [ADR-0016](../adr/ADR-0016-postgres-port.md)):

1. **`JsonlShareStore`** (default) — append-only, gitignored JSONL (`BAYLEAF_SHARE_PATH`,
   default `share.events.jsonl` at the repo root; tolerant reads — a missing file is `[]`, a
   corrupt line is skipped, not fatal).
2. **`SqliteShareStore`** — a `share_events` table (stdlib `sqlite3`, `BAYLEAF_SHARE_DB`).
3. **`PostgresShareStore`** — a `share_events` table (`[postgres]` extra, `DATABASE_URL`),
   verified against a live `postgres:16` (`tests/test_persistence_postgres_live.py`).

Each row carries the indexed columns (`id`/`created_at`/`run_id`/`event_type`/`actor`) plus the
full event as a JSON/JSONB document, so a read round-trips a `ProvenanceEvent` exactly. **The DB
adapters degrade to JSONL on any construction failure** (missing extra, no DSN, unreachable
server), logged by exception *type* only — never the DSN (the same discipline `get_repository()`
and `get_share_store()`'s siblings use). `get_share_store()` selects the adapter from the
environment. **Multi-worker safety (a file lock / connection pool) is a documented seam, not
built** — the same honest single-worker limit `api/feedback_store.py` already carries.

`GET /api/runs/{id}` **merges** the run's recorded share events into the returned `RunDetail.events`
live, sorted by `created_at`, so a share appears in the trail immediately — without ever mutating
the cached `RunDetail` the `@lru_cache`'d `_evaluate` returns (the merge happens on a copy, at read
time). The frontend renders it via `EVENT_META['data.exported']` (`frontend/src/provenance.ts`,
ShieldCheck icon, "Data shared") and a dedicated `summarizeEvent` case ("De-identified share · N
rows · \<policy\> scrub · origin \<o\>").

**Note — normalization is already on the gate, the event is not.** The metric registry is
live on the QC critical path (T-024/T-025): the rule engine builds registry-backed, normalized
`MetricValue`s during evaluation and gates on `normalized_value` (see
[metric_registry.md](metric_registry.md), [schemas.md](schemas.md) §6). `metric.parsed` stays
**reserved** only because those `MetricValue`s are built in-memory from the parsed metrics, not
yet emitted as ledger events — that (and `artifact.ingested`) lands with artifact-level QC
ingest in Phase 2.

**Note — the execution trace is read on the gate, not emitted as an event.** The structured
Nextflow/nf-core trace (`trace.txt` → `TraceRecord[]`, [schemas.md](schemas.md)) is now
**ingested as a gate input**: a failed task (status in the runbook failure set or a nonzero
exit) becomes an **EXEC-001** `Finding` (category `pipeline` → preflight gate, suggested
**RERUN**), cited from `trace.txt` with `source_kind=execution_trace`. Because it lands as a
*finding*, it rides the **existing** vocabulary — `finding.emitted` → `verdict.decided` — and
adds **no new `EventType`**. The trace is an **input artifact the gate READS**, not a provenance
event (composes ≠ executes, ADR-0001/0003); recording it as provenance *metadata* on the
AnalysisRun (the manifest under [The AnalysisRun anchor](#the-analysisrun-anchor), plus any
`artifact.ingested` event) stays Phase-2.

Each event carries `analysis_run_id` / `run_id` / `sample_id`, an `actor`
(`system` | `rule_engine` | `agent` | `human:<id>`), typed `payload`, and
`inputs`/`outputs` as **EntityRef**s (`entity_type` + `id` + `content_hash` for
immutable entities). A `finding.emitted` event carries the finding's
`content_hash` and rule-version-independent `signature`; a `verdict.decided` event
carries the card's `content_hash`.

## The ledger

`EventLedger` is append-only. In-memory by default; pass a path and it also writes
**one JSON line per event** to a JSONL file — the authoritative record. `run_gate`
accepts an optional `ledger`; omit it and events still flow into a throwaway
in-memory ledger (so anchoring/hashing always happen), pass one to capture or
persist them.

```python
from bayleaf import run_gate, load_run, EventLedger
ledger = EventLedger(path="run.events.jsonl")
cards = run_gate(load_run("data/mock_run_01"), ledger=ledger)
# ledger.events -> the full trail; ledger.by_type(EventType.VERDICT_DECIDED) -> per-sample
```

## The DB projection (implemented — Phase 2)

The relational projection promised above now exists in `src/bayleaf/persistence/`:
a **rebuildable projection of the ledger**, reached only through a repository port
so the core never touches a DB directly (ADR-0003).

1. **`Repository` port** — the mandatory DB-agnostic interface (save/list runs,
   samples, findings, cards; append/list events; `get_run_bundle`; `reset`).
   `SqliteRepository` is the default adapter (stdlib `sqlite3`, no new dependency);
   a Postgres adapter can implement the same port later.
2. **Tables** (schema-versioned via `PRAGMA user_version`): `runs`, `samples`,
   `findings`, `decision_cards`, `provenance_events`. `content_hash`/ids are
   preserved verbatim; nested/unindexed data (`gate_provenance`, event
   `inputs`/`outputs`/`payload`) is stored as JSON; timestamps are UTC ISO-8601.
3. **One projector, two callers** — `project_events(events, repo)` is the only
   event→row mapping. `run_gate(..., repo=…)` runs it live after a gate execution,
   and `rebuild_db(ledger_path, repo)` runs it over a replayed JSONL file, so the
   DB is a *pure function of the log* regardless of path. A row carries only what
   an event snapshotted — nothing is invented.
4. **`rebuild-db`** replays a ledger into a fresh projection deterministically
   (clears first, so a rebuild is reproducible and rebuilding twice is idempotent):

   ```bash
   python -m bayleaf.persistence.rebuild run.events.jsonl bayleaf.sqlite
   # or: make rebuild-db LEDGER=run.events.jsonl DB=bayleaf.sqlite
   ```

Only the current event vocabulary is projected (`analysis_run.started/completed`,
`sample.registered`, `finding.emitted`, `verdict.decided`); reserved event types
are still recorded verbatim in `provenance_events` and gain projected rows when
their producers land.

## Deferred to Phase 2

1. **Strict-replay determinism** (byte-identical rebuild) — the projection is
   deterministic and idempotent today; byte-identical hardening remains.
2. `artifact.ingested` / `metric.parsed` **events** (and their projected tables) once
   artifact-level QC ingest lands — the `MetricValue`/`MetricRegistry` normalization they would
   record already runs on the gate (above), just not yet as emitted events.
3. **pipeline_provenance** *manifest* on the AnalysisRun from sarek `pipeline_info/`
   (`params_hash` + the `execution_trace` artifact ref/hash). The execution trace is
   **already read as a gate input** today (EXEC-001 → RERUN); what remains here is recording
   it as provenance *metadata* — no new event type is involved.

## Phase 1 scope notes (deliberate divergences from schemas.md)

1. **AnalysisRun is per-run here**, not per-sample. schemas.md models it per-sample
   (with `sample_id` / `input_artifact_ids`); Phase 1 creates one per gate execution —
   the gate manifest (rule pack, runbook) is identical across a run's samples, so a
   single anchor suffices and all cards share it. Per-sample AnalysisRuns arrive with
   real per-sample pipeline provenance in Phase 2.
2. **Records carry a Phase-1 subset of fields.** `Evidence` omits `artifact_id` /
   `metric_value_id` / `corpus_id`; `DecisionCard` omits `model` / `supersedes_card_id`;
   `ProvenanceEvent` omits `trace_id` / `correlation_id` / `ticket_id`; `gate_provenance`
   ships `{rule_pack_version, runbook_metrics}` rather than the full manifest. Each fills
   in as its producer (metric ingest, tickets, sarek provenance) lands in Phase 2.
