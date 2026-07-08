# Documentation — Table of Contents

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | all (contributors and Claude Code) |

**Start here.** This index is the map of what exists. Read it first, then open
only the files relevant to your task — bulk-load only when the task genuinely
needs broad context. Conventions: [DOCUMENTATION_HABITS.md](DOCUMENTATION_HABITS.md).
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
| [design/frontend/frontend-design-brief.md](design/frontend/frontend-design-brief.md) | ✅ | UI design brief (v1 + v2 additions) — the stable spec |
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

## Meta
| Doc | Status | Purpose |
|---|---|---|
| [DOCUMENTATION_HABITS.md](DOCUMENTATION_HABITS.md) | ✅ | How we document |
| [_templates/](_templates/) | ✅ | Skeletons — check before creating any new doc |
| [journal/](journal/) | ✅ | Dated raw session logs, distilled into the docs above |

## Doc-to-code map
Which doc to open for a given part of the system.

| If you're touching… | Read… |
|---|---|
| `src/pipeguard/` overall | [`design/architecture.md`](design/architecture.md) (+ ADR-0002, ADR-0013) |
| `models.py`, `parsers.py` (artifact I/O) | `data/schemas.md` |
| `runbook.py`, `rules.py` (QC gate) | `data/qc_metrics.md` |
| `metrics/` (registry + `MetricValue`) | `data/metric_registry.md`, `data/schemas.md` |
| `notify/` (outbound notify port) | ADR-0010, ADR-0001 (advisory, never decides) |
| `scripts/fetch_giab_hg002.py` (real data) | `scripts/README.md`, `data/strategy.md`, `data/licensing.md` |
| the event bus / ledger | `data/provenance.md`, ADR-0002 |
| the config layer / profiles | ADR-0005 + [`architecture.md`](design/architecture.md) §Swappable seams |
| the synthesizer / agents | ADR-0001, ADR-0006 |
| any machine output / log format | ADR-0007, `data/schemas.md` |
| anything: "why is it this way?" | `adr/` |
