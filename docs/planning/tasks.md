# Task & Progress Tracker

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-08 (MST) |
| **Purpose** | Top-layer session input (read alongside the ToC): tracks development, timeline, and flags parallel-safe work so non-blocking items can fan out to background agents. |

## Timeline

Due **Mon Jul 13, 2026, 6:00 pm MST** (9:00 pm ET). Day buckets, not hour
estimates — adjusted as we go.

| Day (MST) | Bucket | Focus |
|---|---|---|
| Tue Jul 7 | Design / research | Concept lock, docs, ADRs, Phase 0 |
| Wed–Thu Jul 8–9 | Build | Provenance/event seam, real-QC ingest, AI layer, dashboard |
| Fri Jul 10 | Harden | Eval vs truth data, error handling, security, doc refresh |
| Sat Jul 11 | Demo | Demo plan, one-pager/deck, UI states |
| Sun Jul 12 | Flex | Overflow, agent #2, risks, dry run |
| Mon Jul 13 | Buffer / submit | Final checks; submit before 6 pm |

## How to use

- **Statuses:** `todo` · `in-progress` · `blocked` · `done`.
- **Parallel-safe** = no unfinished dependency and an isolated area of the repo;
  safe to run concurrently or hand to a background agent.
- Keep this current in the same change as the work. It is the shared board across
  sessions — read it (with the [table of contents](../TABLE_OF_CONTENTS.md)) at
  session start to see what is claimable.

## Roadmap (phases)

| Phase | Focus | State |
|---|---|---|
| 0 | Foundation & hygiene (uv, mypy, ruff, hooks) | done |
| 1 | Design capture + provenance/event seam | in-progress |
| Port | Productionization: FastAPI read-API + React frontend (ADR-0014) | in-progress |
| 2 | Persistence + real QC data | in-progress |
| 3 | Scoped agents + real confidence (triage agent T-015 done) | in-progress |
| 4 | Cloud & IaC | wishlist |

## Task board

| ID | Task | Phase | Status | Parallel-safe | Depends on |
|---|---|---|---|---|---|
| T-001 | Documentation workflow + ADRs 0001–0007 | 1 | done | — | — |
| T-002 | `data/qc_metrics.md` (grounded, cited, breadth-first runbook) | 1 | done | yes | — |
| T-002b | Concrete test-data QC profile (tune to GIAB panel subset) | 2 | todo | no | T-017 |
| T-003 | `reference/domain-primer.md` + `reference/glossary.md` | 1 | todo | yes | — |
| T-004 | `requirements/{functional,nonfunctional,constraints}.md` | 1 | todo | yes | — |
| T-005 | `design/architecture.md` ✅; system-view docs (context, components, data-flow, interfaces, storage, workflows, deployment) remain | 1 | in-progress | partial | T-002 |
| T-006 | `design/configuration.md` (profiles) | 1 | todo | yes | — |
| T-007 | `design/structure.md` (repo + data map) | 1 | todo | yes | — |
| T-008 | `data/licensing.md` remains (provenance.md ✅, schemas.md ✅, metric_registry.md ✅) | 1 | in-progress | yes | — |
| T-009 | `quality/{evaluation,risks}.md` remain (demo/demo_plan.md ✅) | 1 | in-progress | yes | T-002 |
| T-010 | ADRs 0008–0014 (issue-taxonomy, corpora, ticketing/API, tooling, agent-scoping, gate-architecture, productionization) | 1 | done | yes | — |
| T-011 | Fresh production-framed `README.md` (committed; architecture.md now exists — final polish/demo-prep remains) | 1 | in-progress | no | T-005 |
| T-012 | Phase 0 tooling: uv + `pyproject.toml` single source, mypy/ruff, hooks (batch full-eval → Phase 2/T-009) | 0 | done | no | — |
| T-013 | GIAB HG002 subset fetch script + synthetic perturbation generator | 2 | todo | partial | T-002, T-008 |
| T-014 | Event bus + provenance ledger (in-memory + JSONL; DB projection → T-023 ✅) | 1 | done | no | ADR-0002 |
| T-015 | QC-triage agent (advisory, stub-first, corpus + retrieval, /triage API) | 3 | done | no | T-014 |
| T-015b | Slack notify port for the triage/review flow (deferred from T-015) | 3 | todo | no | T-015 |
| T-016 | Data strategy doc + label mock_run_01 origin | 1 | done | yes | — |
| T-017 | Small real test FASTQ→BAM data (panel-region subset) for coverage/contam gates | 2 | todo | partial | T-002 |
| T-018 | Frontend design brief + clickable prototype (`design/frontend/`) | 1 | done | yes | — |
| T-019 | Align confidence to "omit until grounded" (models.py `confidence` → Optional/None, drop demo Confidence tile, update README:32/:105) — part of the models→schemas.md rework | 1 | done | no | T-008 |
| T-020 | FastAPI read-API over the core (`api/`; production seam, ADR-0010/0014) | Port | done | no | — |
| T-021 | React frontend scaffold + design tokens (`frontend/`; Vite + Tailwind, ADR-0014) | Port | done | no | T-020 |
| T-022 | React screens: run overview · decision cards · triage · provenance · monitoring · settings ✅; intake/review-queue remain (backend-blocked) | Port | in-progress | partial | T-021 |
| T-023 | SQLite persistence: Repository port + event→row projector + rebuild-db (ADR-0002/0003) | 2 | done | no | T-014 |
