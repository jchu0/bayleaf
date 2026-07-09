# Scope & Wishlist

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | all (contributors and Claude Code) |
| **Related** | [ADRs](../adr/), [functional.md](functional.md), [planning/tasks.md](../planning/tasks.md), [journal 2026-07-08](../journal/2026-07-08-build.md) |

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

## Built as of 2026-07-08

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
   (in-scope 3).
5. **Dashboard — all prototype screens built** in the React frontend: run overview, intake/preflight,
   decision cards + triage, review queue, provenance, monitoring, settings (in-scope 6);
   plus the Streamlit offline fallback.
6. **Both AI seams** (synthesizer, QC-triage agent) present, stub-first ($0), env-flippable to live.
7. **Read-API policy + telemetry seams** (T-027) — `GET /api/runbook` (flattened thresholds,
   illustrative-not-clinical + a `units_note`) and `GET /metrics` (Prometheus text exposition;
   verdict/gate counters; no new dependency), plus a frontend metrics panel surfacing each card's
   registry-normalized `metric_values` (in-scope 6; base for wishlist #17).

Still open in-scope: the **granular config profile** is documented, not shipped (see wishlist #1);
the **variant gate** is Phase 2; **evaluation** vs. GIAB/synthetic truth is ongoing.

## Wishlist (documented, deferred)

| # | Item | Research | Blocked on | Notes |
|---|---|---|---|---|
| 1 | Granular agent profile | Low | config layer + agents | Design captured (ADR-0005/0012); build after core |
| 2 | Jira / Teams / Discord notify adapters | Low | — (notify port **built**, T-015b) | Port + Slack adapter shipped; remaining channels are just new `NotifyPort` adapters. Wiring notify into the read-API/ticketing flow is the follow-on |
| 3 | Cloud deploy + Terraform (AWS / HealthOmics) | Low–med | containerization | Write as target-state IaC before any apply |
| 4 | Pipeline-repair agent (agent #2) | Low–med | QC-triage + escalation | Next agent after QC (ADR-0012) |
| 5 | pgvector read-clustering / contaminant-QC | **High** | vector store + research | Nearly a separate project; empirical, unproven. The intended vector store is **Postgres `pgvector`** — the end-goal single store (D3/#19), not a separate system |
| 6 | NLP variant-miner (PubMed/PMC + ClinVar) | **High** | corpus + review flow | "Candidate variants for expert curation", never auto-actionable |
| 7 | RNA-seq modality | Med | new pipeline + gate | Extension beyond the germline DNA panel |
| 8 | Fine-tuning (LoRA on an open-weight model) | High | experience-ledger scale | Future; for now capture structured data only (ADR-0007) |
| 9 | No-code pipeline runner (schema-driven form + optional LLM NL layer) | Low | command API + frontend | **No model** — nf-core `nextflow_schema.json` → form; NL via LLM + structured output |
| 10 | Pipeline canvas — stage/DAG view + per-run data-I/O drill-down | Low–med | frontend + provenance ledger | Read-only; visualizes provenance; a lean version may land in the MVP dashboard |
| 11 | Visual pipeline builder — compose tools + snap-in agents (± RNA-seq) | **High** | canvas + config + agents | **Flagship north-star** — integrates the canvas (#10), reuses provenance + logging + corpora, and answers the event's "pipeline translator" idea. The **artifact-kind → output-path config file** (a variant-gate-substrate seam, T-032) is the machine-readable base a canvas would generate. Nearly its own product |
| 12 | In-app user feedback on the system | Low | frontend | Product-refinement telemetry to guide iteration |
| 13 | Data-platform connectors (Box, Drive, OneDrive, S3, DNAnexus, Databricks, Snowflake, BigQuery, Redshift) | Low–med each | artifact-store port | Adapters; breadth work |
| 14 | Configurable de-identification module (HIPAA / PHI) | Med | connectors + policy | **Prerequisite** for any real patient-data integration; the demo stays public/synthetic |
| 15 | CNV / mosaicism calling (dedicated callers) | High | callers + validation | Out of gate scope; coverage/AB signals enable *advisory* agent observations without a caller |
| 16 | User-defined custom QC metrics | Med | config/runbook model | Adjusting thresholds is in scope; defining new metric types is future |
| 17 | Telemetry connectors (Datadog + other APM) | Low | — (Prometheus `/metrics` seam **built**, T-027) | The `GET /metrics` base is shipped (verdict/gate counters, hand-rolled exposition, no dep); remaining is wiring APM/scrape connectors on top |
| 18 | Multi-user / multi-tenancy (auth + RBAC + per-user/org isolation) | Low–med | read-API + user model + scoped persistence | Today is **single-user** (all runs/cards global), which is fine for the demo. A lab/org boundary would add auth on the read-API, a user/role model, and scope the ledger/DB by tenant. Complements the de-id module (#14) for real deployments; the `human:<id>` actor already in the event vocabulary is the natural attribution seam |
| 19 | Columnar ML export (Parquet) + **Postgres/`pgvector` as the single end-goal store** (D3) | Low–med | export endpoint (T-030); Repository→Postgres | SQLite stays the operational projection **now** (row-oriented, zero-dep, `rebuild-db`-able). **End-goal (D3): Postgres as the single operational + vector store** — its built-in `pgvector` subsumes #5 — rather than Postgres **+** a separate DuckDB. Export = a **single file on demand** (CSV/JSONL now; **Parquet** for columnar ML), *not* masses of loose files — the DB is the store, the file is a disposable artifact. **DuckDB demoted to optional** local-analytics. Circle back if time |
| 20 | Run scheduling / cancellation / hold — **step-specific** (control plane) | Low–med | command/control API + run-state model + orchestrator hook | Today PipeGuard is **advisory / read-only** (observe + advise). This crosses into **actuation**: hold analysis auto-trigger when pre-run metrics look bad, cancel on an early-surfaced intake error, or pause at a specific pipeline step. Frame it as the **preflight gate acting as an actuator** — a deterministic HOLD (or a human hold) prevents the next step from running; step-level hold/cancel integrates with the workflow engine (Nextflow, [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md)) checkpoint/resume. **Invariant preserved:** rules/human decide, the system actuates only on an explicit, recorded decision (every actuation = a ledger event); no AI auto-actuation ([ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)). The dashboard evolves into a **mission-control** view; a prerequisite is capturing **per-step pipeline execution state (start→end) as ledger events** projected to the UI (the OLTP substrate, Re:1a). *Interact* with Nextflow (resume/checkpoint) — don't reinvent it. Builds on the command API in #9 |

## Out of scope

1. Any **clinical / diagnostic / therapeutic** decision-making — this is a research/demo tool with production intent, not a clinical system.
2. Building or modifying the upstream **clinical pipeline** — we sit on top of it.
3. Licensed data sources (e.g. HGMD) — open sources only (GIAB, gnomAD, ClinVar).
4. Real patient data (PHI) during the hackathon — public/synthetic only. A configurable
   **de-identification module** (wishlist #14) is a prerequisite for any future PHI
   integration under HIPAA and data-use agreements.
