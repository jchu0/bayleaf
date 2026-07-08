# ADR-0002 — Event-driven core with a provenance ledger

| Field | Value |
|---|---|
| **Status** | Accepted · Realized (EventLedger + JSONL + DB projection built; byte-identical replay is Phase 2) |
| **Date** | 2026-07-07 (MST) · updated 2026-07-08 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0003](ADR-0003-deployment-agnostic-ports.md), [ADR-0007](ADR-0007-ml-ready-structured-outputs.md), [ADR-0010](ADR-0010-ticketing-notify-read-api.md), [ADR-0015](ADR-0015-layered-data-contract.md), [data/provenance.md](../data/provenance.md), [data/schemas.md](../data/schemas.md) |

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

## Revisit when

- Throughput or scale needs a real broker, or provenance must be durable across
  hosts.
