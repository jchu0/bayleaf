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

## Out of scope

1. Any **clinical / diagnostic / therapeutic** decision-making — this is a research/demo tool with production intent, not a clinical system.
2. Building or modifying the upstream **clinical pipeline** — we sit on top of it.
3. Licensed data sources (e.g. HGMD) — open sources only (GIAB, gnomAD, ClinVar).
