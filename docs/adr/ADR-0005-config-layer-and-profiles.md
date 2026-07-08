# ADR-0005 — Config layer and deployment/agent profiles

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-07 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | ADR-0003, ADR-0006 |

## Context

Two segments want different things. A budget-constrained research lab wants a
lean footprint on HPC/Slurm; a biotech/CRO wants granular agent separation and
observability, often cloud-native. Deployment target, agent topology, synthesis
on/off, notification channel, and QC thresholds all vary — and hardcoding any of
them forecloses a segment.

## Decision

Introduce a configuration layer with **profiles**. Config resolves in layers
(built-in defaults → selected profile → environment → runtime overrides),
validated with pydantic-settings. A `Profile` composes a coherent bundle:
deployment adapters, agent topology (lean vs granular), synthesis settings,
notify channel, and runbook thresholds. The deployment axis and the agent axis
correlate with the two segments (research/HPC/lean ↔ biotech/cloud/granular). We
ship the **lean** profile and document **granular**.

## Assumptions

- The research/biotech split captures the meaningful variance in how this is run.
- Profiles compose cleanly over the ports from ADR-0003.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Hardcode one configuration | Serves only one segment |
| Scattered per-module feature flags | No coherent, testable bundle; drifts quickly |

## Consequences

| | |
|---|---|
| **Gains** | One codebase serves both segments; the multi-agent cost/separation tradeoff becomes a product feature, not an architecture fork |
| **Costs** | A config layer and profile definitions to maintain and validate |
| **Follow-ups** | The layer + profiles are detailed here and in `design/architecture.md` §Swappable seams (consolidated; no standalone `configuration.md`); AI stays off by default within any profile (ADR-0006) |

## Revisit when

- A third deployment or agent shape does not fit the profile model.
