# ADR-0003 — Deployment-agnostic ports & adapters

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-07 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | ADR-0002, ADR-0005 |

## Context

Target environments differ by segment: research labs commonly run on-prem HPC /
Slurm, while biotech/CRO work trends cloud-native (e.g., AWS HealthOmics). We are
not sure which we will deploy to, and we do not want that uncertainty to leak
into the core.

## Decision

The core (rules, synthesis, provenance, dashboard) is deployment-agnostic behind
a small set of ports — event bus, artifact store, run store, job runner, and
notify — each with a local adapter now. Compute portability for the upstream
genomics pipeline is delegated to **Nextflow**, which runs the same workflow
locally, on Slurm, or on AWS Batch / HealthOmics via executor config. Cloud and
Slurm adapters (and Terraform) are future work.

## Assumptions

- We may target either HPC/Slurm or cloud-native; both are real market segments.
- Nextflow's executor abstraction covers compute portability.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Commit to AWS now (LocalStack, EventBridge, RDS) | Couples the core to an unchosen target; HPC/Slurm is arguably more representative |
| Commit to HPC/Slurm now | Same coupling problem in the other direction |

## Consequences

| | |
|---|---|
| **Gains** | One codebase serves both segments; deployment is a config choice, not a rewrite |
| **Costs** | A port/adapter layer to define and keep honest |
| **Follow-ups** | Adapters + Terraform are wishlist; document the ports in `design/architecture.md` |

## Revisit when

- We commit to a single production deployment target.
