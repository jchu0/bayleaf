# ADR 0005 — Config layer and deployment/agent profiles

- **Status:** accepted
- **Date:** 2026-07-07 (MST)
- **Related:** 0003, 0006, design/configuration.md

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

## Alternatives considered
- Hardcode one configuration — rejected: serves only one segment.
- Feature flags scattered per module — rejected: no coherent, testable bundle;
  drifts quickly.

## Consequences
One codebase serves both segments; a deployment or agent-tier change is a config
choice. The multi-agent cost/separation tradeoff becomes a product feature, not
an architecture fork. New adapters and agents slot into a profile rather than the
core. AI stays off by default within any profile (ADR-0006).
