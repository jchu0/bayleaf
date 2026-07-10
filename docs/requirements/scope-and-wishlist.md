# Scope & Wishlist

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-09 (MST) |
| **Audience** | all (contributors and Claude Code) |
| **Related** | [ADRs](../adr/), [functional.md](functional.md), [planning/tasks.md](../planning/tasks.md), [journal 2026-07-08](../journal/2026-07-08-build.md), [journal 2026-07-09 frontend batch-2](../journal/2026-07-09-frontend-batch2.md), [journal 2026-07-09 GIAB E2E](../journal/2026-07-09-giab-e2e-pipeline.md), [journal 2026-07-09 frontend batch-3](../journal/2026-07-09-frontend-batch3.md) |

## Overview

What we are building, what is deferred, and what is explicitly excluded. Wishlist
items carry a **research level** and a **readiness** flag so it is clear that most
are blocked on unbuilt core seams, not on research.

## In scope (MVP)

1. Deterministic QC + variant **decision gate** (proceed / hold / rerun / escalate) with cited findings.
2. **Provenance ledger** — every I/O recorded, origin-labelled, ML-ready.
3. **VCF-first** inputs on a GIAB HG002 substrate + a **synthetic** failure-mode generator.
4. **One QC-triage agent** (advisory, off critical path) grounded in the knowledge + experience corpora.
5. **Config layer + lean profile**; the granular profile is documented, not shipped.
6. **Dashboard**: review queue (cards-as-tickets), evidence, monitoring; a **Slack** notify adapter.
7. Rigorous **evaluation** vs. GIAB truth + synthetic failure modes.

## Built as of 2026-07-09

The MVP core is standing; these in-scope pieces are now built and verified (see
[functional.md](functional.md) + [tasks.md](../planning/tasks.md)):

1. **Deterministic decision gate** with cited findings, provenance ledger, and SQLite projection (in-scope 1–2).
2. **Metric registry on the QC-gate critical path** (T-024/T-025) — metrics normalized to
   canonical decimals before thresholding; verdicts byte-identical (in-scope 1;
   [architecture.md](../design/architecture.md), [metric_registry.md](../data/metric_registry.md)).
3. **Outbound notify port + Slack adapter** (T-015b) — wired into `run_gate` (off by default),
   per-verdict evidence-cited messages, `notification.emitted` events, live Slack opt-in
   (`PIPEGUARD_SLACK_LIVE`), `python -m pipeguard.notify` CLI (in-scope 6).
4. **Real GIAB HG002 through the FULL gate** (T-002b) — `scripts/gate_giab.py`: `samtools fastq |
   fastp` + `mosdepth` derive real Q30 88.2% / dup 0.006% / reads-PF 99.3% / coverage 55.8× →
   PROCEED, registry-normalized like a mock run; fetch validated end-to-end, data never committed
   (in-scope 3). **Now also executed end-to-end from raw reads** (T-063, `scripts/
   run_giab_pipeline.py`): the real fastqs run through the actual Pipeline-Builder chain (`fastp →
   bwa-mem2 → samtools markdup → {mosdepth, bcftools call}`), landing in the operator UI exactly
   like a mock run (`RUN-2026-07-08-GIAB-HG002`, `origin=real-giab`) — HOLD on the honest
   cluster-PF-missing signal (a run-level SAV metric a fastq→BAM path can't produce). Contamination
   (verifybamid2) still not computed (see [tasks.md](../planning/tasks.md) T-071).
5. **Dashboard — 9 operator screens, rebuilt to the refreshed design prototype** (T-062,
   2026-07-09, superseding T-022b's 1:1 migration), **plus an admin panel** (T-066, `/admin`,
   approver-gated): submit samplesheet, run overview, intake/preflight, decision cards, review
   queue, provenance (compute-DAG), agent triage, monitoring, settings — in a nav restoring the
   3-group Operate/Analyze/Configure split (T-064, reversing T-062's 2-group call per maintainer
   feedback) — **plus the Pipeline Builder** (T-044/#11, with free composition + Connect mode +
   a "New pipeline" affordance since T-062/T-065); plus the Streamlit offline fallback. The admin
   panel's Users & roles tab is an explicit **client-mock** (no backend user store — `api/auth.py`
   stays a header dev-shim, ADR-0017); Activity log + System are real reads. Seeded with volume
   for UI/UX testing: `scripts/seed_giab_demo.py` (T-064) adds ~24 synthetic (`origin=contrived`)
   GIAB-named runs, 29 discoverable runs total. Three product writes that 4xx'd against the real
   API (threshold slug, pipeline submit chain, ticket-resolve RBAC) are now fixed and surfaced via
   a Toast on failure (T-067) — the first real frontend↔backend write reconciliation pass.
6. **AI seams — the synthesizer (narrator) plus four advisory agents** — QC-triage, off-gate
   feedback-triage, **pipeline-repair (#2, T-058 — now also fed by structured execution-trace
ingestion, EXEC-001/T-061) and archivist (#3, T-059)** — all present,
   stub-first ($0), env-flippable to live, and **off the deterministic gate** (ADR-0001). The
   **archivist** (`api/archivist.py`, data-platform §5, Haiku) is an advisory "librarian":
   `GET /api/runs/{id}/archive-digest` + `GET /api/archive/index` index/summarize already-decided
   runs into an `ArchiveDigest` (organizational, **not** diagnostic; never opens/moves/relabels a
   file). The designed node-authoring agent (roster #5, T-046) remains its $0 deterministic stub.
7. **Read-API policy + telemetry seams** (T-027) — `GET /api/runbook` (flattened thresholds,
   illustrative-not-clinical + a `units_note`), `GET /metrics` (Prometheus text exposition), and
   `GET /api/runs/{id}/artifacts` (per-stage data I/O with real sha256/size/origin, powering the
   provenance compute-DAG), plus a frontend metrics panel surfacing registry-normalized
   `metric_values` (in-scope 6; base for wishlist #17).
8. **In-app feedback + the DB seam** (T-042/T-043, ADR-0016) — the app's first write
   (`POST /api/feedback`, off-gate telemetry: per-decision thumbs + a global FAB) through a
   pluggable `FeedbackStore` (jsonl/sqlite/postgres) + an advisory feedback-triage agent; the
   `Repository` Postgres adapter shipped guarded/off-by-default (verified against real Postgres 16).

Still open in-scope: the **granular config profile** is documented, not shipped (see wishlist #1);
the **variant gate** is Phase 2; **evaluation** vs. GIAB/synthetic truth is ongoing.

## Wishlist (documented, deferred)

| # | Item | Research | Blocked on | Notes |
|---|---|---|---|---|
| 1 | Granular agent profile | Low | config layer + agents | Design captured (ADR-0005/0012); build after core |
| 2 | Jira / Teams / Discord notify adapters | Low | — (notify port **built**, T-015b) | Port + Slack (T-015b), **Teams + Discord webhook adapters shipped (T-035)** — stdlib `urllib.request` POST, per-adapter live flag, stub-default. **Jira deferred** (a write action → needs a `content_hash` idempotency guard; ticketing/write-action phase). Wiring notify into the read-API/ticketing flow is the follow-on |
| 3 | Cloud deploy + Terraform (AWS / HealthOmics) | Low–med | containerization | Write as target-state IaC before any apply |
| 4 | Pipeline-repair agent (agent #2) | Low–med | — (QC-triage **built**) | ✅ **BUILT** (T-058, ADR-0008/0012) — advisory, **off the gate**: a recurring `Finding.signature` from the monitoring rollup → a cited `RepairProposal{summary, attach_to(stage), scope(gate)}` grounded in a curated remediation corpus (no invented thresholds; `advisory=True`, no verdict). Stub-first ($0) / `PIPEGUARD_PIPELINE_REPAIR_AGENT` (Opus-high). On-demand `GET /api/monitoring/signatures/{signature}/repair`; the ~3× auto-escalation stays deferred. **Structured-issue feed via execution-trace ingestion now BUILT (EXEC-001, T-061):** a Nextflow/nf-core `trace.txt` is READ on the gate (composes ≠ executes), a failed task → a cited EXEC-001 `Finding` → RERUN that flows to this agent through the recurring-signature rollup — so the repair agent now sees **pipeline-executor** failures, not only PipeGuard's own gate findings (closes the "blocked on `execution_trace` capture" gap the earlier scope flagged). The Pipeline **Builder's** "Hand off to Nextflow" run modal stays a static preview (`RunHandoffModal`, T-069) — compose ≠ execute: EXEC-001 only **reads** a trace, it never **runs** a pipeline. (A *different*, narrower execution path now exists on the **Submit** screen — `POST /api/runs`, 2026-07-09, see item 9 — but it triggers one fixed bioconda script, not a Nextflow hand-off, and doesn't touch the Builder.) Core module [`src/pipeguard/pipeline_repair/`](../../src/pipeguard/pipeline_repair/) |
| 5 | pgvector read-clustering / contaminant-QC | **High** | vector store + research | Nearly a separate project; empirical, unproven. The intended vector store is **Postgres `pgvector`** — the end-goal single store (D3/#19), not a separate system |
| 6 | NLP variant-miner (PubMed/PMC + ClinVar) | **High** | corpus + review flow | "Candidate variants for expert curation", never auto-actionable |
| 7 | RNA-seq modality | Med | new pipeline + gate | Extension beyond the germline DNA panel |
| 8 | Fine-tuning (LoRA on an open-weight model) | High | experience-ledger scale | Future; for now capture structured data only (ADR-0007) |
| 9 | No-code pipeline runner (schema-driven form + optional LLM NL layer) | Low | command API + frontend | **No model** — nf-core `nextflow_schema.json` → form; NL via LLM + structured output. The deterministic `schema → form` importer is also the **$0 stub core of the node-authoring agent** ([design/node-authoring-agent.md](../design/node-authoring-agent.md), roster #5 / T-046). **The samplesheet-submission form now has a real backend** (2026-07-09, commit `e77c2e6`, T-057): `POST /api/runs` (new `api/routers/intake.py`) registers a run and triggers `scripts/run_giab_pipeline.py` as a background subprocess; `Submit.tsx` submits → polls `GET /api/runs/{id}/intake-status` → navigates to Decision cards. Demo-scoped to the `HG002` fixture (other samples honestly skipped, never fabricated a run). This is still narrower than a general no-code runner — it hands off to one hard-coded script, not a schema-driven form-to-any-pipeline path — so item 9 stays open at large, but the "no backend to submit to" gap this line used to flag is closed |
| 10 | Pipeline canvas — stage/DAG view + per-run data-I/O drill-down | Low–med | frontend + provenance ledger | Read-only; visualizes provenance; a lean version may land in the MVP dashboard |
| 11 | Visual pipeline builder — compose tools + snap-in agents (± RNA-seq) | **High** | canvas + config + agents | ✅ **MVP BUILT** (T-044) — the editable superset of the Provenance canvas: a left→right germline DAG the operator *configures* (select/params/locators/agent-toggle) that emits `run_layout.yaml` across three profiles. **Composes, never executes** (primary action Emit). Hard invariants rendered as visible guarantees: agents are port-less side-nodes (agent→gate data edge unrepresentable), the gate is a terminal locked node with no verdict control, every emitted locator origin is `unknown`. Built from the refreshed design handoff ([`pipeline-builder-brief.md`](../design/frontend/pipeline-builder-brief.md) / `design/frontend/README.md`). **Save/version backend shipped** (T-049) — `POST/GET /api/pipelines`, a product store off the gate (pluggable JSONL/SQLite/Postgres, ADR-0016) that keeps the graph as a tolerant versioned envelope. **Approve lifecycle + RBAC now realized** (T-052/T-054, ADR-0017): a shared auth primitive (`api/auth.py`) + `submit`/`approve` (approver-only) transitions, a **read-only** `dry-run` locator resolver (compose≠execute), and `diff`-vs-last-emitted. **Free composition + Connect mode now BUILT** (T-062, 2026-07-09, Wave 3) — palette add/drag/delete of user nodes, a typed-port Connect mode (kind-matched only, INV-e), a minimap, and editable Locators with live YAML regen. **A document-level "New pipeline" affordance now BUILT** (T-065) — a toolbar "+ New" opens Blank-graph or From-template as an explicit fresh Draft; View-default still guards the linked pipeline. **Frontend↔backend save/submit/approve write path now fixed** (T-067) — Save chains save→submit so Approve no longer 409s; reconciles from the response and toasts real failures. Save/Approve **were already** optimistic-local (client-first, not yet reading back the full server response — a labelled limitation, not a fabricated success); Save/Submit specifically now do reconcile per T-067. **Still open (tracked, T-069):** the already-built Dry-run/Diff/Export/Archivist backend seams (T-054/T-059) are unwired in the UI — `RunHandoffModal`/`PipelineRepairModal`/`ArchivistModal` remain static previews — and saved-profiles (a named locator set beyond the 3 built-in profiles) has no backend seam yet; wiring Dry-run is itself blocked on a run-selector (T-070, no "pick a run_id" component exists anywhere in the frontend). Remaining phase-2 seams (in-app run/hand-off execution, RNA-seq, the node-authoring agent's live LLM path — its Builder modal is a static `phase-2`-labelled preview, T-046) designed/mocked but not built; auth is a dev shim pending a real provider |
| 12 | In-app user feedback on the system | Low | frontend | ✅ **BUILT** (T-042, extended by T-043/ADR-0016) — off-gate `POST /api/feedback` (the app's first write) + per-decision thumbs + a global FAB, a pluggable JSONL/SQLite/Postgres store, and an advisory feedback-triage agent. Product-refinement telemetry to guide iteration |
| 13 | Data-platform connectors (Box, Drive, OneDrive, S3, DNAnexus, Databricks, Snowflake, BigQuery, Redshift) | Low–med each | artifact-store port | **Port + first adapters shipped (T-039):** the `ArtifactStore` port (`src/pipeguard/artifacts/`, [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md)) — a *materialize-to-local-dir* boundary UPSTREAM of the gate (locates artifacts, never touches a verdict) — with a zero-dep `LocalArtifactStore` and an **S3 adapter OFF by default** (lazy `boto3` in an optional `[s3]` extra; live pull gated by `PIPEGUARD_S3_LIVE`; degrades to local on any error, so a bucket/creds alone never pull). **Deferred (breadth, each its own task):** the other 7 connectors — each needs its own SDK + auth + fixtures before it is demo-safe, and the warehouses (Databricks/Snowflake/BigQuery/Redshift) need a **query→artifact** adapter shape, not a straight object pull. Held back deliberately to avoid heavy-SDK/scope bloat |
| 14 | Configurable de-identification module (HIPAA / PHI) | Med | connectors + policy | **Prerequisite** for any real patient-data integration; the demo stays public/synthetic. **Export-seam slice shipped (T-040):** a config-driven de-id *policy* ([`api/deid.py`](../../api/deid.py)) realizes G-PII + G-DEID at `GET /api/export` — per-field `DROP`/`HASH`/`GATE_BY_ORIGIN`/`PASSTHROUGH` + an origin-gated, pseudonymized cohort-key opt-in (`include=identity`). Explicitly a **demo de-id SEAM, NOT HIPAA de-identification** (salted-hash pseudonymization ≠ Safe-Harbor scrub). **Still wishlist:** the full module — ingest-side 18-identifier scrub, free-text NLP redaction, date-shift / k-anonymity, DUA/BAA, audit trail (see data-platform §2.1d / §5.2.7) |
| 15 | CNV / mosaicism calling (dedicated callers) | High | callers + validation | Out of gate scope; coverage/AB signals enable *advisory* agent observations without a caller |
| 16 | User-defined custom QC metrics | Med | config/runbook model | Adjusting thresholds is in scope; defining new metric types is future |
| 17 | Telemetry connectors (Datadog + other APM) | Low | — (Prometheus `/metrics` seam **built**, T-027) | The `GET /metrics` base is shipped (verdict/gate counters, hand-rolled exposition, no dep). **Pull/scrape connector bundle shipped** (T-036): Datadog OpenMetrics + Prometheus + OTel-Collector configs (+ optional compose demo) in [`deploy/telemetry/`](../../deploy/telemetry/), documented in [ops/telemetry-connectors.md](../ops/telemetry-connectors.md) — config + docs only, no dep. **Deferred (own task):** an in-app push exporter (ddtrace/DogStatsD or `opentelemetry-*` + OTLP) behind a `PIPEGUARD_*_LIVE` opt-in — that is where a heavy dep + credentials + outbound surface would enter |
| 18 | Multi-user / multi-tenancy (auth + RBAC + per-user/org isolation) | Low–med | read-API + user model + scoped persistence | Today is **single-user** (all runs/cards global), which is fine for the demo. A lab/org boundary would add auth on the read-API, a user/role model, and scope the ledger/DB by tenant. Complements the de-id module (#14) for real deployments; the `human:<id>` actor already in the event vocabulary is the natural attribution seam. The per-run **`origin` → `study_id`** field (D11) is the study-scoping seam a tenant/study boundary would build on. **An admin UI now exists over today's single-user reality** (T-066, `/admin` → Users & roles): explicitly a **client-mock roster** — there is still no backend user store (`api/auth.py` stays a header dev-shim, ADR-0017) — it lets a demo operator switch the acting `Actor{id,role}` via "Act as" to exercise RBAC, not a real identity/tenant boundary |
| 19 | **Postgres/`pgvector` as the single end-goal store** (D3) — columnar Parquet export **shipped** (T-030); **Postgres adapter shipped** OFF-by-default (T-043/ADR-0016 — `PostgresRepository` + `get_repository()` + the `[postgres]` extra, verified green against real Postgres 16) | Low–med | ~~Repository→Postgres~~ (built) | SQLite stays the operational projection **now**. Export is a **single file on demand** — CSV/JSONL/**Parquet all shipped** (Parquet via an optional `pyarrow` extra) so a user brings any reader (pandas/polars/DuckDB), *not* masses of loose files. **End-goal (D3): Postgres as the single operational + vector store** — its built-in `pgvector` subsumes #5 — not Postgres **+** a separate DuckDB (**DuckDB demoted to optional**) |
| 20 | Run scheduling / cancellation / hold — **step-specific** (control plane) | Low–med | command/control API + run-state model + orchestrator hook | Today PipeGuard is **advisory / read-only** (observe + advise). This crosses into **actuation**: hold analysis auto-trigger when pre-run metrics look bad, cancel on an early-surfaced intake error, or pause at a specific pipeline step. Frame it as the **preflight gate acting as an actuator** — a deterministic HOLD (or a human hold) prevents the next step from running; step-level hold/cancel integrates with the workflow engine (Nextflow, [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md)) checkpoint/resume. **Invariant preserved:** rules/human decide, the system actuates only on an explicit, recorded decision (every actuation = a ledger event); no AI auto-actuation ([ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)). The dashboard evolves into a **mission-control** view; a prerequisite is capturing **per-step pipeline execution state (start→end) as ledger events** projected to the UI (the OLTP substrate, Re:1a). *Interact* with Nextflow (resume/checkpoint) — don't reinvent it. Builds on the command API in #9 |

## Scoping pass — 2026-07-08 (non-agent wishlist)

A fanout scoped every non-agent wishlist item against the real seams. **8 are being built now**
in isolated feature branches (merge what finishes); the rest are clarified target-state.

**BUILD (feature branches, none touches the deterministic core):**

| # | Item | Branch | Tracker |
|---|---|---|---|
| W2 | Notify webhook adapters (Teams/Discord) | `feat/notify-webhook-adapters` | T-035 |
| W17 | Telemetry connector configs (over `/metrics`) | `feat/telemetry-connectors` | T-036 |
| W10 | Provenance stage/DAG canvas (read-only) | `feat/provenance-stage-canvas` | T-037 |
| W16 | Metric-catalog read-only view | `feat/metric-catalog-view` | T-038 |
| W13 | ArtifactStore port + Local + S3 adapter **(built ✅ — port + Local + guarded S3)** | `feat/artifact-store-port-s3` | T-039 |
| W14 | Config-driven de-id export policy ✅ (`api/deid.py` — per-field DROP/HASH/GATE_BY_ORIGIN + origin-gated `include=identity` cohort-key opt-in; demo seam, not HIPAA; no new dep) | `feat/deid-export-policy` | T-040 |
| W3 | Container deploy slice (+ unapplied Terraform) | `feat/container-deploy-slice` | T-041 |
| W12 | In-app user feedback ✅ **BUILT** (T-042) — off-gate telemetry: per-decision agree/disagree thumbs + a global product FAB → `POST /api/feedback` → gitignored JSONL. The app's first write endpoint (read-API stays read-only over the decision domain) | `feat/in-app-feedback` | T-042 |

**SCOPE-ONLY (documented target-state, not built now):** W5 (contaminant-QC, High research),
W6 (variant-miner, High research), W7 (RNA-seq modality, XL new pipeline+gate), W8 (LoRA
fine-tuning, needs ledger scale), W9 (nf-core schema form, XL), W15 (CNV/mosaicism calling,
needs callers+validation), W18 (multi-tenancy — touches the core, XL), W20
(run-control/mission-control — needs a Nextflow hook + command API). These stay as the wishlist
rows above; the Jira ticket-create half of W2 is deferred to the ticketing/write-action phase.

## Out of scope

1. Any **clinical / diagnostic / therapeutic** decision-making — this is a research/demo tool with production intent, not a clinical system.
2. Building or modifying the upstream **clinical pipeline** — we sit on top of it.
3. Licensed data sources (e.g. HGMD) — open sources only (GIAB, gnomAD, ClinVar).
4. Real patient data (PHI) during the hackathon — public/synthetic only. A configurable
   **de-identification module** (wishlist #14) is a prerequisite for any future PHI
   integration under HIPAA and data-use agreements.
