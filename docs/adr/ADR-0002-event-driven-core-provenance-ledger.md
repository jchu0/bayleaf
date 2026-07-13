# ADR-0002 — Event-driven core with a provenance ledger

| Field | Value |
|---|---|
| **Status** | Accepted · Realized (EventLedger + JSONL + DB projection built; byte-identical replay is Phase 2) |
| **Date** | 2026-07-07 (MST) · updated 2026-07-08 (MST) · updated 2026-07-11 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0003](ADR-0003-deployment-agnostic-ports.md), [ADR-0007](ADR-0007-ml-ready-structured-outputs.md), [ADR-0010](ADR-0010-ticketing-notify-read-api.md), [ADR-0015](ADR-0015-layered-data-contract.md), [ADR-0018](ADR-0018-variant-interpretation-advisory-evidence.md) (`data.exported` share egress), [data/provenance.md](../data/provenance.md), [data/schemas.md](../data/schemas.md) |

## Context

Bioinformatics operations lose track of what ran, on what input, and why — the
"comb the logs until it resolves" problem. The AI layer also needs to observe
multiple pipeline stages (QC gate, variant gate, and more later), not just one.
Provenance for all I/O is a hard requirement of the domain.

## Decision

Build the core around an event-driven contract: pipeline stages emit typed
events, and an append-only **provenance ledger** records every input and output
with its origin and a content hash. Agents and the dashboard subscribe to events.
For now the event bus is **in-process** and the ledger is a local append-only log
(JSONL); a cloud broker is a later adapter, not part of the MVP.

## Assumptions

- Multiple stage-observation points will be needed; an append-only ledger is
  sufficient provenance for the MVP.
- Event throughput is modest at hackathon scale.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Synchronous pipeline only | No natural provenance record; later observers mean re-plumbing |
| Cloud queue/broker now (SQS/EventBridge) | Distributed-systems overhead with no MVP payoff; deferred behind the bus interface |

## Consequences

| | |
|---|---|
| **Gains** | One mechanism serves robustness, auditability, and agent integration; new observers are new subscribers |
| **Costs** | An event contract and ledger schema to design and maintain |
| **Follow-ups** | Specify ledger format + hashing in `data/provenance.md`; keep records ML-ready per ADR-0007 |

## Realized (2026-07-08)

1. **Event-driven core built.** `run_gate` (`engine.py`) emits a typed, append-only trail
   — `analysis_run.started → sample.registered → finding.emitted → verdict.decided →
   analysis_run.completed`, plus an optional `notification.emitted`
   ([ADR-0010](ADR-0010-ticketing-notify-read-api.md)) — into an in-process `EventLedger`
   (`provenance.py`) with optional JSONL persistence. The `EventType` vocabulary matches
   schemas.md.
2. **Ledger-authoritative, DB-as-projection realized.** `persistence/` projects the same
   event stream through one `project_events` used by *both* the live path and `rebuild_db`,
   into a `SqliteRepository` reached only via the `Repository` port
   ([ADR-0003](ADR-0003-deployment-agnostic-ports.md)). Byte-identical strict-replay
   determinism is the remaining Phase-2 hardening; a cloud broker remains a later adapter.
3. **A tenth `EventType` added, deliberately outside the gate's own ledger (2026-07-11,
   ADR-0018 D3).** `data.exported` records a de-identified share/report egress
   (`POST /api/runs/{id}/share`) as an auditable event in the same append-only vocabulary as a
   decision — but it is emitted by the read-API, not `run_gate`, and it is an **egress
   transform only** (reads already-decided `DecisionCard`s, never a rule/verdict/gate input;
   ADR-0001 holds). It is intentionally recorded to a **separate** sink,
   `api/share_store.py` (a `ShareStore` Protocol; `BAYLEAF_SHARE_STORE=jsonl|sqlite|postgres`,
   default `jsonl`) rather than the gate's `EventLedger`, because the gate ledger is a
   deterministic per-run re-derivation (`api.main._evaluate` is `@lru_cache`) that must stay
   byte-stable and cacheable, while a share is a live, actor-driven side effect that must
   survive both that cache and a process restart. `GET /api/runs/{id}` merges the two ledgers'
   events at read time (sorted by `created_at`) so a share appears in the same trail the
   operator already reads. See
   [data/provenance.md](../data/provenance.md#a-second-separate-sink-for-share-events-apishare_storepy).
   **Persistence parity (2026-07-11, later the same day).** The sink shipped JSONL-only at
   first, the one off-gate sink without a DB adapter (unlike feedback/pipeline/review/settings,
   ADR-0016) — brought to parity the same day: `api/share_ledger.py` was renamed and rebuilt on
   the canonical store pattern (`ShareStore` Protocol + Jsonl/Sqlite/Postgres adapters +
   `get_share_store()`), degrade-to-JSONL on any DB failure, verified against a live
   `postgres:16`. See [ADR-0016](ADR-0016-postgres-port.md) item 6.

## Revisit when

- Throughput or scale needs a real broker, or provenance must be durable across
  hosts.
