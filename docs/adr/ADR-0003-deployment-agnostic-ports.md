# ADR-0003 — Deployment-agnostic ports & adapters

| Field | Value |
|---|---|
| **Status** | Accepted · Realized (event-bus / run-store / notify / artifact-store ports + metric-registry seam built; **Nextflow compute is now executable** — a card-graph→Nextflow compiler + a Nextflow-first intake driver, plus a baked-in `standard`/`slurm` executor-profile layer (W4) — the `slurm` profile is CONFIG-verified, not CLUSTER-verified; job-runner + AWS-Batch/HealthOmics compute adapters stay wishlist) |
| **Date** | 2026-07-07 (MST) · updated 2026-07-08 (MST) · updated 2026-07-09 (MST) · updated 2026-07-11 (MST) · updated 2026-07-11 (MST, W4 executor profiles) · updated 2026-07-11 (MST, W4 continuation — N-sample driver parse) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0005](ADR-0005-config-layer-and-profiles.md), [ADR-0010](ADR-0010-ticketing-notify-read-api.md), [ADR-0014](ADR-0014-productionization-fastapi-react.md), [ADR-0016](ADR-0016-postgres-port.md), [ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md) (the approval gate W1 adds to the execution path this ADR realizes), [design/architecture.md](../design/architecture.md), [design/nextflow-codegen.md](../design/nextflow-codegen.md), [journal 2026-07-11 audit+W1-W4+E2E](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md), [journal 2026-07-11 w-deferrals](../journal/2026-07-11-w-deferrals.md) |

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
   the `Repository` protocol (`persistence/repository.py`) with a `SqliteRepository` adapter
   **and a guarded, OFF-by-default `PostgresRepository`** (selected by `get_repository()` from
   `PIPEGUARD_REPOSITORY`, degrade-to-SQLite; [ADR-0016](ADR-0016-postgres-port.md)) + a
   `rebuild-db` replay that targets either backend; notify = the `NotifyPort` protocol
   (`notify/`) with stub + Slack + Teams + Discord adapters
   ([ADR-0010](ADR-0010-ticketing-notify-read-api.md)); **artifact store = the
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
   Nextflow remains the intended compute-portability layer. The FastAPI
   read-API ([ADR-0014](ADR-0014-productionization-fastapi-react.md)) consumes the core through these
   seams without adding framework imports to `src/pipeguard/`.

## Realized (2026-07-09) — a narrow, demo-scoped job-runner instance

`api/routers/intake.py` (T-057, commit `e77c2e6`, [design/architecture.md](../design/architecture.md))
adds `POST /api/runs`: an in-process job registry (dict + lock, no queue/retry/durability) that
triggers `scripts/run_giab_pipeline.py` — at the time, a bioconda-toolchain driver, not Nextflow —
as a background subprocess, then exposes `GET /api/runs/{id}/intake-status` to poll it. This is the
first time the API layer actually **triggers** an external pipeline run rather than only
composing config for one; the core invariant is unchanged (`src/pipeguard/` never runs a tool —
[ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md)). It is **not** the wishlist job-runner
*port* above (no adapter abstraction, hard-coded to one script, HG002-fixture-scoped) — noted
here only so "no pipeline wired yet" isn't read as still true.

**Superseded 2026-07-11 — see the new "Realized (2026-07-11)" section below.** The
"bioconda-toolchain driver, not Nextflow" line above was accurate on 2026-07-09; it no longer is —
the driver now runs the SAME toolchain *through* Nextflow.

## Realized (2026-07-11) — Nextflow becomes executable: codegen + a Nextflow-first driver

Two pieces make the "compute portability is delegated to Nextflow" **Decision** above executable
rather than aspirational (full design in
[design/nextflow-codegen.md](../design/nextflow-codegen.md)):

1. **A card-graph → Nextflow compiler, `src/pipeguard/nextflow/`** (T-123, commits
   `10f1816`/`be69d6b`). Pure text codegen — it emits `main.nf`/`modules/*.nf`/`nextflow.config`
   for a typed Builder graph and never invokes a tool (compose ≠ execute holds at the core). A
   curated `catalog.py` (this pipeline's 7 germline-chain tools: bioconda + biocontainer
   packaging, typed ports, a real `script:` AND a `stub:` so `-stub-run` validates the DAG with no
   data/tools) backs `compiler.py`'s `compile_graph()`; an uncatalogued tool compiles to a
   labelled placeholder that fails loudly on a real run, never a fabricated command. The seeded
   germline chain compiles to the **committed reference pipeline**
   (`pipelines/germline/`, regenerated by `scripts/generate_reference_pipeline.py`), pinned
   byte-for-byte by a drift test — so "what the Builder emits" and "the canonical repo pipeline"
   are the same artifact by construction. Exposed over the wire by
   `POST /api/pipelines/compile` (JSON preview or a `.zip`) + a Builder "Export to Nextflow" UI.
2. **The intake driver is now Nextflow-first** (T-123, commits `8f9d527`/`e4ba174`).
   `scripts/run_giab_pipeline.py` no longer calls fastp/bwa-mem2/samtools/… directly — it runs
   `nextflow run pipelines/germline/main.nf` (the exact pipeline item 1 compiles) via
   `subprocess.run`, then parses the pipeline's PUBLISHED QC outputs into the frozen-five run dir.
   `POST /api/runs` (the "Realized (2026-07-09)" section above) is unchanged at the API-boundary
   level — it still triggers this same background subprocess — only what that subprocess does
   internally changed.
3. **Verified live** on real GIAB HG002 reads (Nextflow 26.04 + a JRE + the bioconda toolchain in
   a local conda env, not a repo dependency): `completed=7 failed=0`, QC parsed (Q30 88.2%,
   coverage 54.2×, 553 variants), gate → HG002 HOLD (cluster_pf missing, the honest expected
   result — a run-level SAV metric a fastq→BAM path can't produce).
4. **Still local-profile only.** This realizes Nextflow *execution* (the `-profile conda` path);
   the Decision's Slurm/AWS-Batch/HealthOmics **executor config** — and the wishlist job-runner
   port's adapter abstraction — remain unbuilt. The compiler's catalog is curated (this pipeline's
   germline chain), not a claim that any arbitrary Builder card is runnable.

## Realized (2026-07-11, W4) — an executor-profile layer: local-serial / Slurm, config-verified not cluster-verified

Same day, a further increment (T-129, commit `5f0d5ec`) narrows item 4 above — a non-local
executor profile now exists, though it has not been run against a real cluster. Full detail in
[design/nextflow-codegen.md §Executor profiles](../design/nextflow-codegen.md#executor-profiles-local-serial--slurm-w4-nextflowconfig--the-intake-driver).

1. **Two baked-in `nextflow.config` profiles**, alongside the pre-existing `conda`/`docker`/
   `singularity`/`stub`: `standard` (the demo default — local single-thread-serial:
   `queueSize=1`/`maxForks=1`/`cpus=1`) and `slurm` (`process.executor='slurm'`, with queue /
   `clusterOptions` / in-flight cap all **env-driven** —
   `PIPEGUARD_SLURM_QUEUE`/`_CLUSTER_OPTIONS`/`_QUEUE_SIZE` — never a baked guess). One sbatch job
   is submitted per process instance.
2. **The driver auto-selects.** `run_giab_pipeline.py`'s `_detect_profile()`: `sbatch` on `PATH` →
   `-profile slurm`; absent → `-profile standard`. The compiled bundle is identical either way —
   only the executor chosen at the `nextflow run` command line changes (compose ≠ execute — the
   compiler never bakes an executor choice into the emitted graph).
3. **Per-sample fan-out, at the compiler/pipeline level.** Every catalogued process now carries
   the nf-core `[meta, files]` map and runs once per samplesheet row (`ProcessSpec.per_sample`,
   default `True`; `MultiQC` is the one cross-sample aggregator). `main.nf`'s reads channel is
   built from a samplesheet (`--input samplesheet.csv`), not a bare `--read1`/`--read2` pair. The
   live intake driver still submits a **one-row** sheet (HG002) — a degenerate fan-out of 1.
   **Narrowed 2026-07-11 (W4 continuation, commit `9ab7fca`):** the driver's POST-run parse
   (turning a publish dir into gate-able run-dir rows) is now genuinely N-sample capable —
   `discover_samples`/`parse_publish_dir`/`write_run_dir_multi` turn N per-sample published
   outputs into one run dir with N frozen-five rows, offline-verified against fixture publish
   dirs (7 tests, `tests/test_run_giab_multisample.py`). What remains not built is the LIVE half:
   the driver still hands Nextflow a single-row sheet (no second real sample's reads on disk in
   this sandbox), so a genuinely live multi-sample run — an N-row sheet through a real Nextflow
   fan-out, parsed by the logic above against Nextflow's real output — has never been exercised.
   See [design/nextflow-codegen.md §Multi-sample driver
   parse](../design/nextflow-codegen.md#multi-sample-driver-parse-2026-07-11-w4-continuation).
4. **Honest limit, stated precisely: CONFIG-verified, not CLUSTER-verified.** This sandbox (and
   the maintainer's local verification environment) has no `sbatch` on `PATH`, so every live run
   to date — including the HG002 verification the "Realized (2026-07-11)" section above
   describes — has taken the `standard` local-serial branch. The `slurm` profile's Nextflow
   syntax has been read and reasoned through, but it has **never been submitted to, or executed
   by, a real Slurm cluster.** AWS-Batch/HealthOmics executor config remains fully unbuilt.

## Revisit when

- We commit to a single production deployment target.
- We **cluster-verify** the `slurm` profile against a real Slurm cluster (a non-local profile is
  now *configured*, per the 2026-07-11 W4 addendum — this trigger is narrower than it was: it
  fires on actually running it, not on declaring it), or configure and verify an AWS Batch /
  HealthOmics executor, closing the remaining compute-portability gap item 4 (2026-07-11 section)
  names.
