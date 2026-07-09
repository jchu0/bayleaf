# ADR-0010 — Ticketing: cards-as-tickets, notify ports, read API

| Field | Value |
|---|---|
| **Status** | Accepted · Notify port BUILT + wired + live-Slack verified (T-015b); read API BUILT (FastAPI, ADR-0014); card status lifecycle deferred |
| **Date** | 2026-07-07 (MST) · updated 2026-07-08 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](ADR-0003-deployment-agnostic-ports.md), [ADR-0005](ADR-0005-config-layer-and-profiles.md), [ADR-0008](ADR-0008-issue-taxonomy-suppression-escalation.md), [ADR-0014](ADR-0014-productionization-fastapi-react.md), [data/schemas.md](../data/schemas.md) |

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

## Realized (2026-07-08)

1. **Outbound notify port BUILT and wired (T-015b).** `src/pipeguard/notify/` is a stub-first
   `NotifyPort` (`StubNotifier` / `SlackNotifier`) wired into `run_gate(..., notifier=)` as an
   optional, off-by-default, off-critical-path hook that runs *after* the verdict is decided
   ([ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md)). Only actionable (non-PROCEED) cards
   notify; each real notification emits an auditable `notification.emitted` event
   ([ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md)) whose payload holds no secrets.
   Messages are per-verdict, evidence-cited, and run-id-carrying, with a research/demo
   disclaimer. **Live Slack send is opt-in via `PIPEGUARD_SLACK_LIVE` and was verified
   end-to-end against a real workspace** (a token/channel alone never sends; any error degrades
   to the offline stub). A `python -m pipeguard.notify` demo CLI exists.
   **Webhook adapters added (T-035):** `TeamsNotifier` + `DiscordNotifier` extend the same
   `NotifyPort` with a stdlib `urllib.request` POST to an incoming-webhook URL — no SDK, no
   new dependency. Each keeps Slack's safety shape but with its **own** per-adapter live flag
   (`PIPEGUARD_TEAMS_LIVE` / `PIPEGUARD_DISCORD_LIVE`, default OFF), so arming one channel
   never arms another; unarmed or with no URL configured, they degrade to the offline stub
   (no socket). The webhook URL is a secret — env-only, never logged, and stripped from the
   `notification.emitted` event payload (only `adapter/status/delivered/verdict` + the
   payload `content_hash` are recorded). Discord's body is capped at its 2000-char limit.
   `get_notifier()` maps `slack|teams|discord`.
2. **Inbound read API BUILT** as the FastAPI backend (`api/`,
   [ADR-0014](ADR-0014-productionization-fastapi-react.md)) — exactly the seam this ADR
   anticipated, wrapping the framework-agnostic core.
3. **Cards-as-tickets: partial.** `DecisionCard` is the operator-facing unit and the dashboard
   review queue. The explicit `open → in-review → resolved` status lifecycle
   (`ReviewItem`/`Ticket`, schemas.md §17), the **Jira** adapter (a write action that creates
   persistent tickets — needs an idempotency guard keyed off the card `content_hash` so
   re-runs don't spam duplicates; deferred to the ticketing/write-action phase), and the
   resolved-cards → experience-ledger loop ([ADR-0009](ADR-0009-corpora-retrieval-upskilling.md))
   remain MVP-deferred. (Teams/Discord notify adapters are now built — see item 1, T-035.)

## Revisit when

- An integrator needs push/webhook-out semantics beyond the read API.
