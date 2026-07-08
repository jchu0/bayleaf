# ADR-0003 — Deployment-agnostic ports & adapters

| Field | Value |
|---|---|
| **Status** | Accepted · Realized (event-bus / run-store / notify ports + metric-registry seam built; cloud/Slurm adapters wishlist) |
| **Date** | 2026-07-07 (MST) · updated 2026-07-08 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0005](ADR-0005-config-layer-and-profiles.md), [ADR-0010](ADR-0010-ticketing-notify-read-api.md), [ADR-0014](ADR-0014-productionization-fastapi-react.md), [design/architecture.md](../design/architecture.md) |

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

## Realized (2026-07-08)

1. **Ports built with local adapters:** event bus = `EventLedger` (in-memory + JSONL,
   `provenance.py`, [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md)); run store =
   the `Repository` protocol (`persistence/repository.py`) with a `SqliteRepository` adapter +
   a `rebuild-db` replay; notify = the `NotifyPort` protocol (`notify/`) with stub + Slack
   adapters ([ADR-0010](ADR-0010-ticketing-notify-read-api.md)). Each flips at the edge, never
   from the core.
2. **Metric registry is a versioned-artifact seam** (`metrics/`) — a swappable authority the
   rules read through, not a hardcoded table.
3. **Still local-only / wishlist:** artifact store, job runner, and the cloud/Slurm adapters +
   Terraform. Nextflow remains the intended compute-portability layer (no pipeline wired yet).
   The FastAPI read-API ([ADR-0014](ADR-0014-productionization-fastapi-react.md)) consumes the
   core through these seams without adding framework imports to `src/pipeguard/`.

## Revisit when

- We commit to a single production deployment target.
