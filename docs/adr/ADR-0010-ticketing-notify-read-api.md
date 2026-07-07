# ADR-0010 — Ticketing: cards-as-tickets, notify ports, read API

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-07 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0003](ADR-0003-deployment-agnostic-ports.md), [ADR-0005](ADR-0005-config-layer-and-profiles.md), [ADR-0008](ADR-0008-issue-taxonomy-suppression-escalation.md) |

## Context

We need human-in-the-loop tracking, notifications, and integration with external
tools — without reinventing a ticketing system, and while keeping the interaction
surface that lets operators act on surfaced outputs.

## Decision

1. **Decision cards are the tickets.** Each carries a status lifecycle
   (`open → in-review → resolved`); the set of open cards is the dashboard review queue.
2. **Outbound `notify` port** with adapters: Slack for the demo (Slack MCP makes
   it cheap); Jira / Teams / Discord are config-driven, wishlist.
3. **Inbound read API** exposing runs, decisions, and tickets so integrators pull
   from us (e.g. Jira syncs via the API) instead of us building N connectors. This
   is the same seam that becomes the FastAPI backend.

## Assumptions

- Integrators prefer pulling via a stable API over bespoke per-tool pushes.
- The card status lifecycle is enough structure for HITL tracking.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Build a ticket engine | Reinvents a solved wheel; scope |
| One-off integration per external tool | N connectors to build and maintain |

## Consequences

| | |
|---|---|
| **Gains** | HITL tracking + notifications + integration from one model; pulls the FastAPI read API forward as a real seam |
| **Costs** | Status lifecycle, the notify port, and the read API to build |
| **Follow-ups** | Resolved cards feed the experience ledger (ADR-0009) |

## Revisit when

- An integrator needs push/webhook-out semantics beyond the read API.
