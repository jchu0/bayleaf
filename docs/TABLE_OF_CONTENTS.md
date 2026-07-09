# Documentation — Table of Contents

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-09 (MST) |
| **Audience** | all (contributors and Claude Code) |

**Start here.** This index is the map of what exists — and its
**[Doc-update map](#doc-update-map)** is the authority on which docs a change obligates.
**Read lean, write complete:** open only the files relevant to your task (bulk-load only when
it genuinely needs broad context), but before you finish, sweep the Doc-update map and update
every doc your change made stale. Conventions: [DOCUMENTATION_HABITS.md](DOCUMENTATION_HABITS.md).
Claimable work: [planning/tasks.md](planning/tasks.md).

Status legend: ✅ written · 🚧 in progress · 📝 planned.

## Planning
| Doc | Status | Purpose |
|---|---|---|
| [planning/tasks.md](planning/tasks.md) | ✅ | Phases + task board with parallel-safe flags |

## Reference (learn the domain)
| Doc | Status | Purpose |
|---|---|---|
| [reference/domain-primer.md](reference/domain-primer.md) | ✅ | Rare-disease panels, GIAB HG002, gnomAD, ClinVar — for non-specialists |
| [reference/glossary.md](reference/glossary.md) | ✅ | Terms across bioinformatics, software, and clinical |

## Requirements (what the system must do)
| Doc | Status | Purpose |
|---|---|---|
| [requirements/scope-and-wishlist.md](requirements/scope-and-wishlist.md) | ✅ | In-scope, wishlist (with readiness), out-of-scope |
| [requirements/functional.md](requirements/functional.md) | ✅ | Capabilities (REQ-F-NNN) |
| [requirements/nonfunctional.md](requirements/nonfunctional.md) | ✅ | Reliability, provenance, security, performance (REQ-NF-NNN) |
| [requirements/constraints.md](requirements/constraints.md) | ✅ | Timeline, budget, licensing, domain-safety (REQ-C-NNN) |

## Design (how it is built)
| Doc | Status | Purpose |
|---|---|---|
| [design/architecture.md](design/architecture.md) | ✅ | System shape: three gates, component map, data flow, invariants, swappable seams, deployment |
| [design/agents.md](design/agents.md) | ✅ | Agent-layer hub: roster, shared invariants (captured once), intake checklist for new agent ideas |
| [design/data-platform-and-archivist.md](design/data-platform-and-archivist.md) | ✅ | Data-platform + export + run-browser + Archivist agent design (draft for review; tiered already-built / build-now / target-state) |
| [design/node-authoring-agent.md](design/node-authoring-agent.md) | ✅ | Roster agent #5 (proposed) — advisory node-authoring agent: dropped tool docs → a typed `ToolNode` card for the Pipeline Builder palette; stub-first (= wishlist #9), Claude only for `ArtifactKind` mapping |
| [design/frontend/frontend-design-brief.md](design/frontend/frontend-design-brief.md) | ✅ | UI design brief (v1 + v2 additions) — the stable spec |
| [design/frontend/pipeline-builder-brief.md](design/frontend/pipeline-builder-brief.md) | ✅ | Wishlist #11 flagship — pipeline-builder design handoff (node/agent canvas → run-layout config), paste-and-go for a design tool |
| [design/frontend/handoffs/](design/frontend/handoffs/) | ✅ | Dated review→design handoff deltas (episodic) |
| [design/frontend/](design/frontend/) | ✅ | Frontend prototype (`PipeGuard.html`) + design README |

> **Consolidated, not split.** The system-view slices once planned as separate docs
> (system-context, components, data-flow, interfaces, storage, workflows, deployment,
> configuration, structure) live as sections of
> [architecture.md](design/architecture.md) plus the ADRs — config/profiles →
> [ADR-0005](adr/ADR-0005-config-layer-and-profiles.md); ports/interfaces →
> [ADR-0003](adr/ADR-0003-deployment-agnostic-ports.md); storage/ledger →
> [ADR-0002](adr/ADR-0002-event-driven-core-provenance-ledger.md) +
> [provenance.md](data/provenance.md); repo/data layout → the code map in `CLAUDE.md`.
> We chose one coherent system doc over near-duplicate stubs (MVP-first); split a slice
> back out only if it outgrows its section.

## Decision records (ADR)
One decision per file, in [adr/](adr/). Self-identifying `ADR-NNNN-*` names.

| ADR | Title |
|---|---|
| [ADR-0001](adr/ADR-0001-deterministic-gate-advisory-ai.md) | Deterministic gate, advisory AI |
| [ADR-0002](adr/ADR-0002-event-driven-core-provenance-ledger.md) | Event-driven core with a provenance ledger |
| [ADR-0003](adr/ADR-0003-deployment-agnostic-ports.md) | Deployment-agnostic ports & adapters |
| [ADR-0004](adr/ADR-0004-vcf-first-giab-substrate.md) | VCF-first inputs on a GIAB substrate |
| [ADR-0005](adr/ADR-0005-config-layer-and-profiles.md) | Config layer and deployment/agent profiles |
| [ADR-0006](adr/ADR-0006-ai-off-by-default-fallback.md) | AI off by default with a deterministic fallback |
| [ADR-0007](adr/ADR-0007-ml-ready-structured-outputs.md) | ML-ready structured outputs |
| [ADR-0008](adr/ADR-0008-issue-taxonomy-suppression-escalation.md) | Issue taxonomy, suppression, escalation |
| [ADR-0009](adr/ADR-0009-corpora-retrieval-upskilling.md) | Knowledge + experience corpora, retrieval upskilling |
| [ADR-0010](adr/ADR-0010-ticketing-notify-read-api.md) | Ticketing: cards, notify ports, read API |
| [ADR-0011](adr/ADR-0011-tooling-and-reproducibility.md) | Tooling and reproducibility |
| [ADR-0012](adr/ADR-0012-agent-scoping-model-tiering.md) | Agent scoping and per-agent model tiering |
| [ADR-0013](adr/ADR-0013-gate-architecture-verdict-policy.md) | Gate architecture (preflight/QC/variant) + surface-and-decide verdict policy |
| [ADR-0014](adr/ADR-0014-productionization-fastapi-react.md) | Productionize with FastAPI + React; Streamlit as the demo fallback |
| [ADR-0015](adr/ADR-0015-layered-data-contract.md) | Layered, immutable data contract across the gate (the data-structure decisions + why) |
| [ADR-0016](adr/ADR-0016-postgres-port.md) | Postgres port (guarded, off-by-default): the `Repository` Postgres adapter + a pluggable feedback store |

## Data (the artifacts and their lineage)
| Doc | Status | Purpose |
|---|---|---|
| [data/strategy.md](data/strategy.md) | ✅ | Data strategy: sourcing, origin labels, real/synthetic tracks |
| [data/schemas.md](data/schemas.md) | ✅ | Record contracts + persistence (the data spine) |
| [data/metric_registry.md](data/metric_registry.md) | ✅ | Canonical metric vocabulary (stable layer over MultiQC keys) |
| [data/qc_metrics.md](data/qc_metrics.md) | ✅ | QC metric set and gate thresholds (the decided runbook) |
| [data/qc_metrics-sources.md](data/qc_metrics-sources.md) | ✅ | Grounded reference: verified field names + cited thresholds |
| [data/qc_metrics-rare-disease.md](data/qc_metrics-rare-disease.md) | ✅ | Rare-disease gold standards: depth/breadth, cancer/pathogen comparison, tool licenses |
| [data/nf-core-conventions.md](data/nf-core-conventions.md) | ✅ | nf-core/sarek conventions → schema records (sample sheet, versions, MultiQC, artifacts) |
| [data/provenance.md](data/provenance.md) | ✅ | Event seam: AnalysisRun anchor, event vocabulary, append-only ledger |
| [data/licensing.md](data/licensing.md) | ✅ | Per-tool + data-source licenses; external-process invocation model |

## Quality (is it correct, what could go wrong)
| Doc | Status | Purpose |
|---|---|---|
| [quality/evaluation.md](quality/evaluation.md) | ✅ | What "good" means, checks (EVAL-NNN) grounded in the test suite, failure modes |
| [quality/risks.md](quality/risks.md) | ✅ | Technical / product / data / demo risks + mitigations (RISK-NNN) |

## Demo
| Doc | Status | Purpose |
|---|---|---|
| [demo/demo_plan.md](demo/demo_plan.md) | ✅ | Narrative, walkthrough, the three "wow" moments, expected I/O, fallbacks |
| [demo/run-of-show.md](demo/run-of-show.md) | ✅ | Timed live run-of-show (5:00) — script, pre-flight checklist, fallback ladder |
| [demo/one-pager.md](demo/one-pager.md) | ✅ | Judge-facing one-pager (problem, differentiators, why-it's-real, guardrails) |

## Ops (run it in an environment)
| Doc | Status | Purpose |
|---|---|---|
| [ops/telemetry-connectors.md](ops/telemetry-connectors.md) | ✅ | Point Datadog / Prometheus / OTLP APMs at the shipped `GET /metrics` seam (pull model, scrape-safe, no PHI); config bundle in [`deploy/telemetry/`](../deploy/telemetry/) |

## Meta
| Doc | Status | Purpose |
|---|---|---|
| [DOCUMENTATION_HABITS.md](DOCUMENTATION_HABITS.md) | ✅ | How we document |
| [_templates/](_templates/) | ✅ | Skeletons — check before creating any new doc |
| [journal/](journal/) | ✅ | Dated raw session logs, distilled into the docs above |

## Doc-update map

**This table is the single authority on which docs a change obligates** (it replaces the old "Doc-to-code map" and the two prose lists in DOCUMENTATION_HABITS). You may still **read lean**; after any change, **sweep this table and update every doc whose trigger fired, in the same change** — a doc you never had to open can still be one you now owe. Match the concrete condition in column 2. Tiers: 🔴 fires most sessions · 🟠 module-triggered · ⚪ occasional.

| Tier | When you do / touch X | Owe an update to… (why) |
|---|---|---|
| 🔴 | **ANY working session — build, design, decision, or review (unconditional; the one row with no "N/A")** | **`journal/YYYY-MM-DD-<topic>.md`** — this session's reasoning + one Decisions row per decision made. New file per day from `_templates/journal.md`. Write it as you go; distil durable parts into the canonical docs below at session end. No journal entry = incomplete session. |
| 🔴 | A task changes status (`todo/in-progress/blocked/done`) or is created | `planning/tasks.md` — the task row, roadmap phase, and `Last updated`. |
| 🔴 | You create / move / rename / delete a doc, or flip its status (📝→🚧→✅) | `TABLE_OF_CONTENTS.md` — the section row, the status legend, **and this map** if a code↔doc link changed. |
| 🔴 | `src/pipeguard/models.py`, `parsers.py`, or `persistence/` — new/renamed field, type, ID prefix, `schema_version`, missing-field semantics | `data/schemas.md` — the pydantic contract SQLAlchemy mirrors. Cross-check `provenance.md` (event vocab is duplicated) + `metric_registry.md` §units. *(Confirmed drift: the export/Parquet contract shipped without this.)* |
| 🔴 | You add / remove / rename any test under `tests/`, or define an EVAL case | `quality/evaluation.md` — it hardcodes a test census ("N tests / M files"); any change silently falsifies it. Fix the count + per-file breakdown + any `EVAL-NNN`. |
| 🟠 | `runbook.py` or `rules.py` — a threshold, a metric in the set, a gate assignment, verdict policy | `data/qc_metrics.md` (the decided runbook). If the *decision policy* changed → also `ADR-0013`; if grounding changed → cascade to `qc_metrics-sources.md`. |
| 🟠 | `src/pipeguard/metrics/` — registry, aliases, unit, direction | `data/metric_registry.md` (+ `schemas.md` §units). |
| 🟠 | `provenance.py` / `engine.py`, the `EventType` vocabulary, or the JSONL ledger format | `data/provenance.md` (+ `schemas.md` event vocab — **duplicated, update both**; `ADR-0002`). |
| 🟠 | A new **advisory agent anywhere** (`synthesis/`, `triage/`, or an off-gate one like `api/feedback_agent.py`), a model tier, or a corpus | `design/agents.md` (roster + invariants) + the relevant ADR (`0001/0006/0009/0012`). If hub and ADR disagree, the ADR wins — update the ADR first. |
| 🟠 | `api/` endpoint or `frontend/` screen — new/changed capability | `design/architecture.md` + `design/data-platform-and-archivist.md` + `requirements/functional.md` (REQ-F). If `/metrics` / `_render_prometheus` gains or renames a series → also re-verify the exposed-series table and the no-PHI claim in `ops/telemetry-connectors.md`. |
| ⚪ | You **make** a load-bearing decision (or realize/supersede one) | A **new `adr/ADR-NNNN-*.md`** (one decision/file) or an existing ADR's Decision/Status + a journal Decisions row. **Never bury a decision in a design-doc appendix or a "D1-Dn" list.** *(Confirmed drift: D1-D14 + a 261-line design landed as appendices.)* |
| ⚪ | Scope / wishlist / "built" changes | `requirements/scope-and-wishlist.md` (+ mirror `functional.md`, `tasks.md`). A new wishlist item is a scope-guardrail checkpoint — push back if scope over-broadens. |
| ⚪ | Files moved across `src/`/`app/`/`data/`/`docs/`/`tests/`, a module added, **or a trigger in this map rotted** | `CLAUDE.md` "Current code map" + **this map** (the self-referential row: when layout moves, this table's triggers go stale — fix them here). |

**Catch-all** (any module not listed above whose behavior/contract you changed): update the doc that owns it — see the "Necessary documentation stack" table. **Also occasional:** demo flow / exact commands / port change → `demo/run-of-show.md` + `demo/one-pager.md` + `README.md`; a new tool/dependency → `data/licensing.md` + `requirements/constraints.md`; a new *type* of doc with no template → create `_templates/<type>.md` **first**, then the doc.

**Coupled clusters — one code change moves several docs together:** `schemas.md ⇄ provenance.md` (duplicated event vocab) · `qc_metrics.md ⇄ qc_metrics-sources.md` · `scope-and-wishlist.md ⇄ functional.md ⇄ tasks.md` · `metric_registry.md ⇄ schemas.md §units`. *The journal (row 1) is the router — every session logs here, then distils into the canonical docs above; it is never itself the source of truth.*
