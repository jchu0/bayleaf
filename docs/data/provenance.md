# Provenance & Event Ledger

| Field | Value |
|---|---|
| **Status** | Active (Phase 1 seam built; DB projection Phase 2) |
| **Last updated** | 2026-07-07 (MST) |
| **Audience** | software / bioinformatics |
| **Related** | [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [schemas.md](schemas.md), `src/pipeguard/provenance.py`, `src/pipeguard/engine.py` |

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

## Deferred to Phase 2

1. The relational **DB projection** + `rebuild-db` replay (repository interface, ADR-0003).
2. **Strict-replay determinism** (byte-identical rebuild).
3. `artifact.ingested` / `metric.parsed` events once **MetricValue/MetricRegistry**
   ingest lands with real QC data.
4. **pipeline_provenance** on the AnalysisRun from sarek `pipeline_info/`.
