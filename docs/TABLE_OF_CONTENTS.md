# Documentation — Table of Contents

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-07 (MST) |
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
| [reference/domain-primer.md](reference/domain-primer.md) | 📝 | Rare-disease panels, GIAB HG002, gnomAD, ClinVar — for non-specialists |
| [reference/glossary.md](reference/glossary.md) | 📝 | Terms across bioinformatics, software, and clinical |

## Requirements (what the system must do)
| Doc | Status | Purpose |
|---|---|---|
| [requirements/scope-and-wishlist.md](requirements/scope-and-wishlist.md) | ✅ | In-scope, wishlist (with readiness), out-of-scope |
| [requirements/functional.md](requirements/functional.md) | 📝 | Capabilities (REQ-F-NNN) |
| [requirements/nonfunctional.md](requirements/nonfunctional.md) | 📝 | Reliability, provenance, security, performance (REQ-NF-NNN) |
| [requirements/constraints.md](requirements/constraints.md) | 📝 | Timeline, budget, licensing, domain-safety (REQ-C-NNN) |

## Design (how it is built)
| Doc | Status | Purpose |
|---|---|---|
| [design/architecture.md](design/architecture.md) | 📝 | System shape overview, event model, major tradeoffs |
| [design/system-context.md](design/system-context.md) | 📝 | System context: external actors and systems |
| [design/components.md](design/components.md) | 📝 | Components and their responsibilities |
| [design/data-flow.md](design/data-flow.md) | 📝 | How data moves through the gates |
| [design/interfaces.md](design/interfaces.md) | 📝 | Ports, adapters, and the read API |
| [design/storage.md](design/storage.md) | 📝 | Stores, ledgers, and corpora |
| [design/workflows.md](design/workflows.md) | 📝 | Key runtime workflows (gate, triage, HITL) |
| [design/deployment.md](design/deployment.md) | 📝 | Deployment topologies (local / Slurm / cloud) |
| [design/configuration.md](design/configuration.md) | 📝 | Config layer + deployment/agent profiles |
| [design/structure.md](design/structure.md) | 📝 | Repo + data layout |
| [design/frontend-design-brief.md](design/frontend-design-brief.md) | ✅ | Carry-over brief for the UI design session |

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

## Data (the artifacts and their lineage)
| Doc | Status | Purpose |
|---|---|---|
| [data/strategy.md](data/strategy.md) | ✅ | Data strategy: sourcing, origin labels, real/synthetic tracks |
| [data/schemas.md](data/schemas.md) | 📝 | Artifact contracts: fields, types, missing-semantics |
| [data/qc_metrics.md](data/qc_metrics.md) | ✅ | QC metric set and gate thresholds (the decided runbook) |
| [data/qc_metrics-sources.md](data/qc_metrics-sources.md) | ✅ | Grounded reference: verified field names + cited thresholds |
| [data/qc_metrics-rare-disease.md](data/qc_metrics-rare-disease.md) | ✅ | Rare-disease gold standards: depth/breadth, cancer/pathogen comparison, tool licenses |
| [data/provenance.md](data/provenance.md) | 📝 | I/O lineage model and ledger format |
| [data/licensing.md](data/licensing.md) | 📝 | Per-tool licenses in the stack |

## Quality (is it correct, what could go wrong)
| Doc | Status | Purpose |
|---|---|---|
| [quality/evaluation.md](quality/evaluation.md) | 📝 | What "good" means, checks, failure modes |
| [quality/risks.md](quality/risks.md) | 📝 | Technical / product / data / demo risks + mitigations |

## Demo
| Doc | Status | Purpose |
|---|---|---|
| [demo/demo_plan.md](demo/demo_plan.md) | 📝 | Flow, expected I/O, fallback path |

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
| `src/pipeguard/` overall | `design/architecture.md` |
| `models.py`, `parsers.py` (artifact I/O) | `data/schemas.md` |
| `runbook.py`, `rules.py` (QC gate) | `data/qc_metrics.md` |
| the event bus / ledger (planned) | `data/provenance.md`, ADR-0002 |
| the config layer / profiles (planned) | `design/configuration.md`, ADR-0005 |
| the synthesizer / agents | ADR-0001, ADR-0006 |
| any machine output / log format | ADR-0007, `data/schemas.md` |
| anything: "why is it this way?" | `adr/` |
