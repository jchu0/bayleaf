# ADR-0003 — Deployment-agnostic ports & adapters

| Field | Value |
|---|---|
| **Status** | Accepted · Realized (event-bus / run-store / notify / artifact-store ports + metric-registry seam built; job-runner + cloud/Slurm compute adapters wishlist) |
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
   adapters ([ADR-0010](ADR-0010-ticketing-notify-read-api.md)); **artifact store = the
   `ArtifactStore` protocol (`artifacts/`, T-039)** with a zero-dep `LocalArtifactStore` and an
   **OFF-by-default `S3ArtifactStore`**. Each flips at the edge, never from the core.
2. **Metric registry is a versioned-artifact seam** (`metrics/`) — a swappable authority the
   rules read through, not a hardcoded table.
3. **Artifact-store port (T-039), a materialize-to-local boundary UPSTREAM of the gate.** A store's
   sole job is `fetch(run_ref) -> local Path`; the unchanged `load_run` then reads that dir, so the
   store LOCATES a run's bytes and never influences a verdict (rules decide, [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md)).
   `LocalArtifactStore` is the identity over an on-disk run (the pre-port behavior). `S3ArtifactStore`
   mirrors the notify seam's safety shape: `boto3` is a lazy, optional `[s3]` extra; the live pull is
   opt-in behind `PIPEGUARD_S3_LIVE`; ANY error (absent boto3, absent creds, an API failure, an
   unconfigured bucket) degrades to the local store — so a configured bucket/creds alone never pull and
   the demo/tests stay offline. A thin `run_gate_from_store` convenience lives in the package, so no
   code is added to `engine.py`. The 7 other data-platform connectors (wishlist #13 — Box/Drive/OneDrive/
   DNAnexus/Databricks/Snowflake/BigQuery/Redshift) implement this same port but are deferred: each needs
   its own SDK + auth + fixtures, and the warehouses need a query→artifact adapter shape.
4. **Still wishlist:** the **job runner** and the **cloud/Slurm compute adapters + Terraform**.
   Nextflow remains the intended compute-portability layer (no pipeline wired yet). The FastAPI
   read-API ([ADR-0014](ADR-0014-productionization-fastapi-react.md)) consumes the core through these
   seams without adding framework imports to `src/pipeguard/`.

## Revisit when

- We commit to a single production deployment target.
