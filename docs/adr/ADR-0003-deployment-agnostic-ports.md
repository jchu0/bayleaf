# ADR-0003 — Deployment-agnostic ports & adapters

| Field | Value |
|---|---|
| **Status** | Accepted · Realized (event-bus / run-store / notify / artifact-store ports + metric-registry seam built; **Nextflow compute is now executable** — a card-graph→Nextflow compiler + a Nextflow-first intake driver, plus a baked-in `standard`/`slurm` executor-profile layer (W4) — the `slurm` profile is CONFIG-verified, not CLUSTER-verified; job-runner + AWS-Batch/HealthOmics compute adapters stay wishlist) |
| **Date** | 2026-07-07 (MST) · updated 2026-07-08 (MST) · updated 2026-07-09 (MST) · updated 2026-07-11 (MST) · updated 2026-07-11 (MST, W4 executor profiles) · updated 2026-07-11 (MST, W4 continuation — N-sample driver parse) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0005](ADR-0005-config-layer-and-profiles.md), [ADR-0010](ADR-0010-ticketing-notify-read-api.md), [ADR-0014](ADR-0014-productionization-fastapi-react.md), [ADR-0016](ADR-0016-postgres-port.md), [ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md) (the approval gate W1 adds to the execution path this ADR realizes), [design/architecture.md](../design/architecture.md), [design/nextflow-codegen.md](../design/nextflow-codegen.md), [HISTORY.md § ADR-0003](../HISTORY.md#adr-0003--nextflow-becomes-executable-deployment-agnostic-ports) (dated build chronology), [journal 2026-07-11 audit+W1-W4+E2E](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md), [journal 2026-07-11 w-deferrals](../journal/2026-07-11-w-deferrals.md) |

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

## Realized (current status)

> Dated, commit-by-commit build chronology (2026-07-08 ports → 2026-07-09 job-runner instance →
> 2026-07-11 Nextflow-execution + W4 executor profiles) lives in
> [HISTORY.md § ADR-0003](../HISTORY.md#adr-0003--nextflow-becomes-executable-deployment-agnostic-ports).
> This section is the current state + the honest limits.

1. **Ports built with local adapters.** Event bus = `EventLedger` (in-memory + JSONL, `provenance.py`,
   [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md)); run store = the `Repository`
   protocol (`persistence/repository.py`) with a `SqliteRepository` **and** a guarded OFF-by-default
   `PostgresRepository` (`get_repository()` from `BAYLEAF_REPOSITORY`, degrade-to-SQLite;
   [ADR-0016](ADR-0016-postgres-port.md)) + a `rebuild-db` replay targeting either; notify =
   `NotifyPort` (`notify/`) with stub + Slack + Teams + Discord adapters
   ([ADR-0010](ADR-0010-ticketing-notify-read-api.md)); **artifact store** = `ArtifactStore`
   (`artifacts/`, T-039) with a zero-dep `LocalArtifactStore` and an OFF-by-default `S3ArtifactStore`
   (`boto3` a lazy `[s3]` extra; live pull opt-in behind `BAYLEAF_S3_LIVE`; ANY error degrades to
   local, so a configured bucket alone never pulls and the demo/tests stay offline). Each flips at the
   edge, never from the core. The artifact-store port is a **materialize-to-local boundary UPSTREAM of
   the gate** — `fetch(run_ref) -> local Path`; the unchanged `load_run` reads that dir, so the store
   LOCATES bytes and never influences a verdict ([ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md)).
   The metric registry is a versioned-artifact seam (`metrics/`) the rules read through, not a
   hardcoded table.
2. **Nextflow is now executable** — the "compute portability is delegated to Nextflow" Decision is
   realized, not aspirational (full design in [design/nextflow-codegen.md](../design/nextflow-codegen.md)):
   (a) `src/bayleaf/nextflow/` compiles a typed Builder graph → `main.nf`/`modules/*.nf`/
   `nextflow.config` — **pure text codegen, never invokes a tool** (compose ≠ execute holds at the
   core). A curated `catalog.py` (the 7 germline-chain tools; an uncatalogued tool → a labelled
   placeholder that fails loudly, never a fabricated command) backs `compile_graph()`; the seeded
   chain compiles to the committed reference pipeline (`pipelines/germline/`), pinned byte-for-byte by
   a drift test. Exposed by `POST /api/pipelines/compile` + a Builder "Export to Nextflow" UI.
   (b) The intake driver (`scripts/run_giab_pipeline.py`, via `POST /api/runs`) now runs `nextflow run
   pipelines/germline/main.nf` and parses the published QC outputs — **out-of-core**, exactly as before
   (the core still never runs a tool). **Verified live** on real GIAB HG002 reads: `completed=7
   failed=0`, gate → HG002 HOLD (cluster_pf missing — the honest expected result for a fastq→BAM path).
3. **Executor profiles: local-serial / Slurm — CONFIG-verified, not CLUSTER-verified.** `nextflow.config`
   bakes in `standard` (demo default: local single-thread-serial, `queueSize=1`/`maxForks=1`/`cpus=1`)
   and `slurm` (`process.executor='slurm'`, queue / `clusterOptions` / cap all env-driven via
   `BAYLEAF_SLURM_QUEUE`/`_CLUSTER_OPTIONS`/`_QUEUE_SIZE`, never a baked guess). The driver
   auto-selects (`sbatch` on PATH → `slurm`, else `standard`); the compiled bundle is identical either
   way. **Honest limit:** no `sbatch` in the sandbox or the maintainer's env, so every live run to date
   took the `standard` branch — the `slurm` profile has been read/reasoned but **never submitted to a
   real Slurm cluster**; AWS-Batch/HealthOmics executor config is fully unbuilt.
4. **Per-sample fan-out** at the compiler/pipeline level (every catalogued process carries the nf-core
   `[meta, files]` map, `ProcessSpec.per_sample` default `True`; `MultiQC` the one aggregator). The
   driver's post-run parse (`discover_samples`/`write_run_dir_multi`) is N-sample capable and
   offline-verified against fixture publish dirs (7 tests) — but the **LIVE half is unbuilt**: only
   HG002 has reads on disk, so a genuinely live multi-sample Nextflow fan-out has never been exercised.
5. **Still wishlist:** the **job runner** adapter abstraction (`POST /api/runs` is a narrow,
   HG002-scoped instance, not the port), the **cloud/Slurm compute adapters + Terraform**, and the 7
   other data-platform connectors (wishlist #13 — Box/Drive/OneDrive/DNAnexus/Databricks/Snowflake/
   BigQuery/Redshift implement the artifact-store port but each needs its own SDK + auth + fixtures).
   The FastAPI read-API ([ADR-0014](ADR-0014-productionization-fastapi-react.md)) consumes the core
   through these seams without adding framework imports to `src/bayleaf/`.

## Revisit when

- We commit to a single production deployment target.
- We **cluster-verify** the `slurm` profile against a real Slurm cluster (a non-local profile is
  now *configured* but never cluster-run — Realized item 3; this trigger is narrower than it was:
  it fires on actually running it, not on declaring it), or configure and verify an AWS Batch /
  HealthOmics executor, closing the remaining compute-portability gaps Realized items 3–5 name.
