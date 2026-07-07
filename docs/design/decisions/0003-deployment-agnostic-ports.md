# ADR 0003 — Deployment-agnostic ports & adapters

- **Status:** accepted
- **Date:** 2026-07-07 (MST)
- **Related:** 0002, 0005, design/configuration.md

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

## Alternatives considered
- Commit to AWS now (LocalStack, EventBridge, RDS) — rejected: couples the core
  to one target we haven't committed to; HPC/Slurm is arguably more representative.
- Commit to HPC/Slurm now — rejected for the same coupling reason.

## Consequences
One codebase serves both segments; the deployment target is a configuration
choice, not a rewrite (see ADR-0005). Nextflow gives compute portability for
free. Nothing in the MVP requires cloud infrastructure. Provisioning/IaC is
deferred to the wishlist.
