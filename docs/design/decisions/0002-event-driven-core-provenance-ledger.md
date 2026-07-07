# ADR 0002 — Event-driven core with a provenance ledger

- **Status:** accepted
- **Date:** 2026-07-07 (MST)
- **Related:** 0003, data/provenance.md

## Context
Bioinformatics operations lose track of what ran, on what input, and why — the
"comb the logs until it resolves" problem. The AI layer also needs to observe
multiple pipeline stages (QC gate, variant gate, and more later), not just one.
And provenance for all I/O is a hard requirement of the domain.

## Decision
Build the core around an event-driven contract: pipeline stages emit typed
events, and an append-only **provenance ledger** records every input and output
with its origin and a content hash. Agents and the dashboard subscribe to events.
For now the event bus is **in-process** and the ledger is a local append-only log
(JSONL); a cloud broker is a later adapter, not part of the MVP.

## Alternatives considered
- Synchronous pipeline only — rejected: no natural provenance record, and adding
  stage observers later would mean re-plumbing.
- Cloud queue/broker now (SQS/EventBridge) — rejected: distributed-systems
  overhead with no MVP payoff; deferred behind the bus interface.

## Consequences
The event log *is* the provenance record — one mechanism serves robustness,
auditability, and agent integration. New observation points are new subscribers.
Swapping the in-process bus for a cloud broker later is an adapter change, not a
rewrite. Ledger format and hashing are specified in data/provenance.md.
