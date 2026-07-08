# Scope & Wishlist

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-07 (MST) |
| **Audience** | all (contributors and Claude Code) |
| **Related** | [ADRs](../adr/), [journal 2026-07-07](../journal/2026-07-07-design-and-planning.md) |

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

## Wishlist (documented, deferred)

| # | Item | Research | Blocked on | Notes |
|---|---|---|---|---|
| 1 | Granular agent profile | Low | config layer + agents | Design captured (ADR-0005/0012); build after core |
| 2 | Jira / Teams / Discord notify adapters | Low | notify port | Adapter interface first; Discord webhook is trivial |
| 3 | Cloud deploy + Terraform (AWS / HealthOmics) | Low–med | containerization | Write as target-state IaC before any apply |
| 4 | Pipeline-repair agent (agent #2) | Low–med | QC-triage + escalation | Next agent after QC (ADR-0012) |
| 5 | pgvector read-clustering / contaminant-QC | **High** | vector store + research | Nearly a separate project; empirical, unproven |
| 6 | NLP variant-miner (PubMed/PMC + ClinVar) | **High** | corpus + review flow | "Candidate variants for expert curation", never auto-actionable |
| 7 | RNA-seq modality | Med | new pipeline + gate | Extension beyond the germline DNA panel |
| 8 | Fine-tuning (LoRA on an open-weight model) | High | experience-ledger scale | Future; for now capture structured data only (ADR-0007) |
| 9 | No-code pipeline runner (schema-driven form + optional LLM NL layer) | Low | command API + frontend | **No model** — nf-core `nextflow_schema.json` → form; NL via LLM + structured output |
| 10 | Pipeline canvas — stage/DAG view + per-run data-I/O drill-down | Low–med | frontend + provenance ledger | Read-only; visualizes provenance; a lean version may land in the MVP dashboard |
| 11 | Visual pipeline builder — compose tools + snap-in agents (± RNA-seq) | **High** | canvas + config + agents | **Flagship north-star** — integrates the canvas (#10), reuses provenance + logging + corpora, and answers the event's "pipeline translator" idea. Nearly its own product |
| 12 | In-app user feedback on the system | Low | frontend | Product-refinement telemetry to guide iteration |
| 13 | Data-platform connectors (Box, Drive, OneDrive, S3, DNAnexus, Databricks, Snowflake, BigQuery, Redshift) | Low–med each | artifact-store port | Adapters; breadth work |
| 14 | Configurable de-identification module (HIPAA / PHI) | Med | connectors + policy | **Prerequisite** for any real patient-data integration; the demo stays public/synthetic |
| 15 | CNV / mosaicism calling (dedicated callers) | High | callers + validation | Out of gate scope; coverage/AB signals enable *advisory* agent observations without a caller |
| 16 | User-defined custom QC metrics | Med | config/runbook model | Adjusting thresholds is in scope; defining new metric types is future |
| 17 | Telemetry connectors (Datadog + other APM) | Low | telemetry seam | System-telemetry export; a Prometheus `/metrics` seam on the backend is the intended base |

## Out of scope

1. Any **clinical / diagnostic / therapeutic** decision-making — this is a research/demo tool with production intent, not a clinical system.
2. Building or modifying the upstream **clinical pipeline** — we sit on top of it.
3. Licensed data sources (e.g. HGMD) — open sources only (GIAB, gnomAD, ClinVar).
4. Real patient data (PHI) during the hackathon — public/synthetic only. A configurable
   **de-identification module** (wishlist #14) is a prerequisite for any future PHI
   integration under HIPAA and data-use agreements.
