# Documentation — Table of Contents

- **Status:** active
- **Last updated:** 2026-07-07 (MST)
- **Audience:** all (contributors and Claude Code)

**Start here.** This index is the map of what exists. Read it first, then open
only the files relevant to your task — do not load the whole repo into context.
Working conventions are in [DOCUMENTATION_HABITS.md](DOCUMENTATION_HABITS.md).

Status legend: ✅ written · 🚧 in progress · 📝 planned.

## Reference (learn the domain)
| Doc | Status | Purpose |
|---|---|---|
| [reference/domain-primer.md](reference/domain-primer.md) | 📝 | Rare-disease panels, GIAB HG002, gnomAD, ClinVar — for non-specialists |
| [reference/glossary.md](reference/glossary.md) | 📝 | Terms across bioinformatics, software, and clinical |

## Requirements (what the system must do)
| Doc | Status | Purpose |
|---|---|---|
| [requirements/functional.md](requirements/functional.md) | 📝 | Capabilities the system must provide |
| [requirements/nonfunctional.md](requirements/nonfunctional.md) | 📝 | Reliability, provenance, security, performance |
| [requirements/scope-and-wishlist.md](requirements/scope-and-wishlist.md) | 📝 | In-scope, wishlist, and out-of-scope with rationale |

## Design (how it is built)
| Doc | Status | Purpose |
|---|---|---|
| [design/architecture.md](design/architecture.md) | 📝 | System shape, components, data flow, event model, tradeoffs |
| [design/configuration.md](design/configuration.md) | 📝 | Config layer + deployment/agent profiles |
| [design/structure.md](design/structure.md) | 📝 | Repo + data layout, doc-to-code map |
| [design/decisions/](design/decisions/) | ✅ | Architecture Decision Records (one per file) |

## Data (the artifacts and their lineage)
| Doc | Status | Purpose |
|---|---|---|
| [data/schemas.md](data/schemas.md) | 📝 | Artifact contracts: fields, types, missing-semantics |
| [data/qc_metrics.md](data/qc_metrics.md) | 📝 | QC metric set and gate thresholds |
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

## Decisions index
| ADR | Title |
|---|---|
| [0001](design/decisions/0001-deterministic-gate-advisory-ai.md) | Deterministic gate, advisory AI |
| [0002](design/decisions/0002-event-driven-core-provenance-ledger.md) | Event-driven core with a provenance ledger |
| [0003](design/decisions/0003-deployment-agnostic-ports.md) | Deployment-agnostic ports & adapters |
| [0004](design/decisions/0004-vcf-first-giab-substrate.md) | VCF-first inputs on a GIAB substrate |
| [0005](design/decisions/0005-config-layer-and-profiles.md) | Config layer and deployment/agent profiles |
| [0006](design/decisions/0006-ai-off-by-default-fallback.md) | AI off by default with a deterministic fallback |

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
| anything: "why is it this way?" | `design/decisions/` |
