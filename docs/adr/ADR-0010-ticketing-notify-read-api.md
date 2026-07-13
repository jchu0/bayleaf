# ADR-0010 — Ticketing: cards-as-tickets, notify ports, read API

| Field | Value |
|---|---|
| **Status** | Accepted · Notify port BUILT + wired + live-Slack verified (T-015b); read API BUILT (FastAPI, ADR-0014); off-gate feedback write BUILT (`POST /api/feedback`, T-042/W12); **review-queue Ticket status lifecycle BUILT** (`open → in_review → resolved` with reviewer/approver RBAC — `api/routers/review_queue.py` + `api/review_store.py`, [ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md)); Jira write-adapter deferred |
| **Date** | 2026-07-07 (MST) · updated 2026-07-08 (MST) · 2026-07-09 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](ADR-0003-deployment-agnostic-ports.md), [ADR-0005](ADR-0005-config-layer-and-profiles.md), [ADR-0008](ADR-0008-issue-taxonomy-suppression-escalation.md), [ADR-0014](ADR-0014-productionization-fastapi-react.md), [ADR-0016](ADR-0016-postgres-port.md), [ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md), [data/schemas.md](../data/schemas.md) |

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

1. **Outbound notify port BUILT and wired (T-015b).** `src/bayleaf/notify/` is a stub-first
   `NotifyPort` (`StubNotifier` / `SlackNotifier`) wired into `run_gate(..., notifier=)` as an
   optional, off-by-default, off-critical-path hook that runs *after* the verdict is decided
   ([ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md)). Only actionable (non-PROCEED) cards
   notify; each real notification emits an auditable `notification.emitted` event
   ([ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md)) whose payload holds no secrets.
   Messages are per-verdict, evidence-cited, and run-id-carrying, with a research/demo
   disclaimer. **Live Slack send is opt-in via `BAYLEAF_SLACK_LIVE` and was verified
   end-to-end against a real workspace** (a token/channel alone never sends; any error degrades
   to the offline stub). A `python -m bayleaf.notify` demo CLI exists.
   **Webhook adapters added (T-035):** `TeamsNotifier` + `DiscordNotifier` extend the same
   `NotifyPort` with a stdlib `urllib.request` POST to an incoming-webhook URL — no SDK, no
   new dependency. Each keeps Slack's safety shape but with its **own** per-adapter live flag
   (`BAYLEAF_TEAMS_LIVE` / `BAYLEAF_DISCORD_LIVE`, default OFF), so arming one channel
   never arms another; unarmed or with no URL configured, they degrade to the offline stub
   (no socket). The webhook URL is a secret — env-only, never logged, and stripped from the
   `notification.emitted` event payload (only `adapter/status/delivered/verdict` + the
   payload `content_hash` are recorded). Discord's body is capped at its 2000-char limit.
   `get_notifier()` maps `slack|teams|discord`.
2. **Inbound read API BUILT** as the FastAPI backend (`api/`,
   [ADR-0014](ADR-0014-productionization-fastapi-react.md)) — exactly the seam this ADR
   anticipated, wrapping the framework-agnostic core. It stays **read-only over the decision
   domain**: no endpoint mutates a verdict, finding, provenance event, or the ledger.
2a. **Off-gate feedback write BUILT (T-042/W12, extended by T-043/[ADR-0016](ADR-0016-postgres-port.md)).**
   The one write endpoint, `POST /api/feedback`, is deliberately *not* a decision write — it
   appends product telemetry (a per-decision agree/disagree signal + a global product note, each
   tagged with the originating UI `source`) through a **pluggable `FeedbackStore`**
   (`api/feedback_store.py`: jsonl default | sqlite | postgres, `BAYLEAF_FEEDBACK_STORE`, its
   own table separate from the decision projection) in a module that never imports the core, so
   it can never call `run_gate` or touch provenance ([ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md)).
   It carries no operator identity (`extra="forbid"` structural guard), resolves `origin`
   server-side, and leaks neither path/DSN nor message on failure. An advisory **feedback-triage
   agent** (`api/feedback_agent.py`) categorizes the corpus out-of-band. The **card
   status-transition writes** (Jira/ticketing) remain the deferred write phase — feedback is
   telemetry, not a ticket mutation.
3. **Cards-as-tickets: status lifecycle now BUILT.** `DecisionCard` is the operator-facing unit and
   the dashboard review queue. The explicit `open → in_review → resolved` status lifecycle
   (the `Ticket` model, schemas.md §17) is now realized as a **writable review queue** with
   reviewer/approver RBAC: `api/routers/review_queue.py` exposes a `Ticket` (`TicketStatus
   open|in_review|resolved`) driven by a `_ACTION_RULES` state machine over
   acknowledge/escalate/resolve/suppress/reopen, via `POST /api/review/tickets` + `GET` +
   `POST /{id}/action`, backed by the pluggable `api/review_store.py` (jsonl/sqlite/postgres,
   degrade-to-JSONL). It stays off the deterministic gate
   ([ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md)) and is gated by the shared identity/RBAC
   primitive ([ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md)). Still MVP-deferred: the
   **Jira** write-adapter (a write action that creates persistent tickets — needs an idempotency
   guard keyed off the card `content_hash` so re-runs don't spam duplicates), class-wide suppression
   muting of *future* tickets for a `rule_id` (`suppress` today resolves the one ticket + marks the
   class handled), and the resolved-cards → experience-ledger loop
   ([ADR-0009](ADR-0009-corpora-retrieval-upskilling.md)). (Teams/Discord notify adapters are also
   built — see item 1, T-035.)

## Revisit when

- An integrator needs push/webhook-out semantics beyond the read API.
