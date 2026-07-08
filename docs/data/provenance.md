# Provenance & Event Ledger

| Field | Value |
|---|---|
| **Status** | Active (Phase 1 seam built; DB projection + `rebuild-db` implemented) |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | software / bioinformatics |
| **Related** | [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md), [schemas.md](schemas.md), `src/pipeguard/provenance.py`, `src/pipeguard/engine.py`, `src/pipeguard/persistence/` |

## Overview

The gate is event-driven (ADR-0002): every gate execution is an **AnalysisRun**,
and every meaningful step emits an **append-only ProvenanceEvent** into an
**EventLedger**. The **event log is authoritative**; a queryable relational DB is a
*rebuildable projection* of it (Phase 2, with strict-replay determinism). Phase 1
ships the in-memory ledger with optional JSONL persistence.

## The AnalysisRun anchor

One `AnalysisRun` (`arun_…`) per gate execution is the anchor every finding, card,
and event references. Phase 1 records the **gate provenance** — `rule_pack_version`,
the runbook's metric set, `generated_by`, and start/complete timestamps. The
**pipeline provenance** (sarek `params_hash` / `execution_trace`) is a Phase-2
addition that needs real sarek data (see [nf-core-conventions](nf-core-conventions.md)).

## Event vocabulary

`EventType` mirrors the schemas.md event vocabulary:

1. **Emitted today** by `run_gate`: `analysis_run.started` → per sample
   (`sample.registered`, `finding.emitted`, `verdict.decided`) → `analysis_run.completed`.
   When a `notifier` is wired (off by default), one `notification.emitted` per actionable
   card follows completion — auditing the outbound side effect (ADR-0010).
2. **Reserved** (emitted as their producers land): `run.registered`,
   `artifact.ingested`, `metric.parsed` (Phase 2 ingest), `ticket.actioned`,
   `resolution.recorded` (ticketing phase).

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
from pipeguard import run_gate, load_run, EventLedger
ledger = EventLedger(path="run.events.jsonl")
cards = run_gate(load_run("data/mock_run_01"), ledger=ledger)
# ledger.events -> the full trail; ledger.by_type(EventType.VERDICT_DECIDED) -> per-sample
```

## The DB projection (implemented — Phase 2)

The relational projection promised above now exists in `src/pipeguard/persistence/`:
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
   python -m pipeguard.persistence.rebuild run.events.jsonl pipeguard.sqlite
   # or: make rebuild-db LEDGER=run.events.jsonl DB=pipeguard.sqlite
   ```

Only the current event vocabulary is projected (`analysis_run.started/completed`,
`sample.registered`, `finding.emitted`, `verdict.decided`); reserved event types
are still recorded verbatim in `provenance_events` and gain projected rows when
their producers land.

## Deferred to Phase 2

1. **Strict-replay determinism** (byte-identical rebuild) — the projection is
   deterministic and idempotent today; byte-identical hardening remains.
2. `artifact.ingested` / `metric.parsed` events once **MetricValue/MetricRegistry**
   ingest lands with real QC data (and their projected tables).
3. **pipeline_provenance** on the AnalysisRun from sarek `pipeline_info/`.

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
