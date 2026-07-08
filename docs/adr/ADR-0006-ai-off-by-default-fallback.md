# ADR-0006 — AI off by default with a deterministic fallback

| Field | Value |
|---|---|
| **Status** | Accepted · Realized (synthesizer + triage stub-first with fallback; notify port inherits the contract) |
| **Date** | 2026-07-07 (MST) · updated 2026-07-08 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0005](ADR-0005-config-layer-and-profiles.md), [ADR-0010](ADR-0010-ticketing-notify-read-api.md), [ADR-0012](ADR-0012-agent-scoping-model-tiering.md) |

## Context

Live AI calls cost money (a fixed ~$200 product API budget, separate from dev
tooling) and add latency and a failure mode. The system must remain usable,
testable, and demoable offline, and must not degrade if the API is unavailable
mid-run — a real risk on conference networks and during grading.

## Decision

Every AI component (the synthesizer and, later, each scoped agent) is **off by
default** and selected by configuration. Each has a deterministic fallback: if
the component is disabled or the call fails (including a safety refusal), the
deterministic verdict and findings still stand and only the narrative/triage is
absent. The `anthropic` dependency is imported lazily so the package installs and
tests pass without it. Model selection is configurable to trade cost for quality.

## Assumptions

- API budget and reliability constraints hold for the project.
- A missing narrative is acceptable UX; a missing verdict is not.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| AI on by default | Burns budget in dev/CI; makes the demo hostage to network/API reliability |
| Pre-recorded AI responses only | Loses the live reasoning central to the pitch; kept only as an optional cache |

## Consequences

| | |
|---|---|
| **Gains** | Dev/CI cost nothing and run offline; the demo has a built-in safety net; enabling AI is a one-line config change |
| **Costs** | Every AI path needs a maintained deterministic fallback |
| **Follow-ups** | Every new agent inherits this contract, bounding blast radius as agent count grows |

## Realized (2026-07-08)

1. **Synthesizer + QC-triage agent** are stub-first and off by default (`get_synthesizer`,
   `get_triage_agent`): each lazy-imports `anthropic`, is selected by a `PIPEGUARD_*` env var,
   and falls back to the deterministic stub on *any* error — including a safety refusal. Model
   choice is configurable via `PIPEGUARD_*_MODEL`.
2. **The notify port ([ADR-0010](ADR-0010-ticketing-notify-read-api.md)) inherited the same
   contract:** stub-first, `slack_sdk` lazy-imported (deliberately not a dependency), live send
   guarded behind `PIPEGUARD_SLACK_LIVE`, degrading to the offline stub on any error — so the
   default demo and the test suite never open a socket.

## Revisit when

- AI becomes load-bearing enough that a deterministic fallback is insufficient
  (would reopen ADR-0001).
