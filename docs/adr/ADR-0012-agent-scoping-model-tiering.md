# ADR-0012 — Agent scoping and per-agent model tiering

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-07 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0005](ADR-0005-config-layer-and-profiles.md), [ADR-0006](ADR-0006-ai-off-by-default-fallback.md) |

## Context

Agents differ in task difficulty, call frequency, cost, and blast-radius needs.
A single model for every agent is either wasteful (expensive model on cheap,
frequent narration) or insufficient (cheap model on hard, systemic diagnosis).

## Decision

1. **Build one deep agent first** — QC-triage — then **pipeline-repair as agent #2**.
   Expand only after the core flow, provenance, and persistence are solid.
2. All agents are **advisory, off the deterministic critical path, and
   least-privilege** (each sees only its stage's data).
3. **Model is per-agent, selected via the config profile** (ADR-0005):
   a. pipeline-repair (rare, hard reasoning) → Opus 4.8 at high/xhigh/max effort,
      or ultracode.
   b. interface / narration agents (frequent, low-stakes) → Sonnet 5 / Haiku 4.5.
4. Every agent inherits **off-by-default + deterministic fallback** (ADR-0006).
   Rare expensive calls + frequent cheap calls keep the API budget efficient.

## Assumptions

- Task-difficulty tiering maps cleanly onto model tiering.
- Sensible per-agent defaults (overridable via config) are enough to ship; robust
  per-agent evaluation can wait.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| One model for all agents | Wasteful or underpowered depending on the choice |
| Many agents up front | Cost, complexity, and evaluation burden before the core exists |

## Consequences

| | |
|---|---|
| **Gains** | Cost/quality efficiency, small blast radius, easy tuning via config |
| **Costs** | Per-agent config and defaults to maintain |
| **Follow-ups** | Defaults land with the config layer and the agents |

## Revisit when

- An agent's default model underperforms in practice.
