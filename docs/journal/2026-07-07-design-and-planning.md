# Journal — 2026-07-07 (MST) — Design & planning pass

| Field | Value |
|---|---|
| **Focus** | Step back from session-1 implementation; lock the concept, architecture, tech stack, and documentation workflow before further build. |
| **Participants** | James Hu, Claude Code |
| **Outcome** | Concept locked; documentation workflow stood up and tested on itself; 13 ADRs recorded (0001–0013). |

## Discussion

**Framing.** Rare-disease **germline DNA panel**, short-read Illumina. The layer
sits on top of a clinical pipeline, so we simulate upstream rather than touch
licensed products. Dropped RNA-seq (STAR/salmon) from the core for legibility.

**Data strategy.** **VCF-first** so pipeline plumbing never blocks the product.
Substrate is **GIAB HG002** — open, real Illumina reads, gold-standard truth VCF +
high-confidence BED, which doubles as evaluation ground truth. Two tracks: real
GIAB (correctness) and **synthetic perturbations** (labeled failure modes: sample
swap, duplicate/missing barcodes, low reads-PF, low Q30, coverage dropout,
low-support variant, contamination, step failure). Planted issues live in the
operational layer only; clinical variants stay grounded in ClinVar/GIAB truth.
End-to-end generation via nf-core/sarek is a later stretch.

**Architecture.** Event-driven core with an in-process bus and an append-only
provenance ledger — the event log *is* the provenance record and the AI's
multi-stage observation surface. Deployment-agnostic **ports & adapters**;
**Nextflow** carries compute portability across local / Slurm / AWS Batch /
HealthOmics. Cloud broker, LocalStack, Terraform, AWS are wishlist.

**Product thesis (maintainer's words).** The AI layer is a cross-layer
**triage/observability accelerant that cuts diagnosis time** — replacing "comb the
logs ad nauseam." It reduces friction; it does not replace tooling. Deterministic
tools/rules are the gates (preflight, QC gate, variant gate — the three-gate model was formalized later this pass in ADR-0013); AI advises at each.

**Agents.** Build **one deep** agent (QC-triage), not many shallow — it proves the
pattern. Agent #2 = pipeline-repair, for recurring/systemic issues. All agents
advisory and off the critical path. "Upskilling" = retrieval over an experience
ledger, **not** fine-tuning.

**Issue handling.** Every issue gets a category + stable signature; a user can
acknowledge/suppress an issue class (with expiry/review) so they are never
re-prompted for a known-accepted condition — kills the "throw a person at it as
glue" anti-pattern. Escalation triggers at ~3 recurrences of a signature and is
human-gated (likely tiered dashboard access / RBAC). Support both class-level
fixes and per-instance "see-one/fix-one" approvals — never blind auto-apply. This
feeds the error-logging and resolution corpora.

**Corpora.** Two, behind one retrieval interface: curated **knowledge corpus**
(tool docs, QC-metric definitions, failure signatures, runbook) and an append-only
**experience ledger**. Stored as JSON/JSONL, pydantic-validated, pgvector-able later.

**Ticketing / HITL.** Don't rebuild ticketing. Cards-as-tickets in-app (status
lifecycle = the review queue) + outbound **notify ports** (Slack demo;
Jira/Teams/Discord config-driven) + an inbound **read API** for integrators (the
seam that becomes the FastAPI backend).

**ML-ready data (new this pass).** Provenance/logging also exists to produce
clean, structured, labeled data for downstream ML — a purpose, not an aesthetic.
Captured as ADR-0007.

**Config layer + profiles.** A profile composes deployment adapters + agent
topology + synthesis + notify + thresholds. Deployment and agent axes correlate
with segments (research/HPC/lean ↔ biotech/cloud/granular). Ship lean, document
granular.

**Tooling / hygiene.** `pyproject.toml` as the sole dependency source; **uv**;
**mypy** + **ruff**; hook tiers (pre-commit: ruff/secret-scan/mypy; pre-push:
pytest; batch: full eval + pip-audit). Coding standards: type hints everywhere,
meaningful docstrings, why-comments, typed env config. Use Nextflow's own
container/image system (Docker/Singularity/conda per process, nf-core containers,
Seqera Wave/Fusion) rather than a custom image layer.

**Documentation workflow.** "Necessary" (not minimal) stack in folders; ADRs
renamed to `docs/adr/ADR-NNNN-*` so the ID survives a move; requirement IDs
`REQ-F/NF/C-NNN`; dated entries (MST); a **table of contents** as the session
entry point (scan, don't slurp — but bulk-load when the task genuinely needs it);
`docs/_templates/` with a check-before-create rule; **journal → canonical**
distillation; a **task tracker** (`docs/planning/tasks.md`) with parallel-safe
flags. Templates and the journal reformatted to a professional/tabular style.

**Git attribution.** Removed the "no AI attribution" rule; adding
`Co-Authored-By: Claude` going forward. Retroactive backfill approved (option B):
all commits on `main` get the trailer via history rewrite + force-push, executed
this pass. `archive/session-1` keeps the untouched originals (local only).

## Decisions

| Decision | Distilled to |
|---|---|
| Deterministic gate, advisory AI | [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) |
| Event-driven core + provenance ledger | [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md) |
| Deployment-agnostic ports; Nextflow portability | [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md) |
| VCF-first on GIAB HG002; dual real+synthetic data | [ADR-0004](../adr/ADR-0004-vcf-first-giab-substrate.md) |
| Config layer + profiles | [ADR-0005](../adr/ADR-0005-config-layer-and-profiles.md) |
| AI off by default + deterministic fallback | [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md) |
| ML-ready structured outputs | [ADR-0007](../adr/ADR-0007-ml-ready-structured-outputs.md) |
| Issue taxonomy + signature suppress/escalate | [ADR-0008](../adr/ADR-0008-issue-taxonomy-suppression-escalation.md) |
| Two corpora (knowledge + experience) as JSON/JSONL | [ADR-0009](../adr/ADR-0009-corpora-retrieval-upskilling.md) |
| Ticketing = cards + notify ports + read API | [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md) |
| pyproject/uv single source; mypy/ruff; hook tiers | [ADR-0011](../adr/ADR-0011-tooling-and-reproducibility.md) |
| Agent scoping + per-agent model tiering | [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) |
| Documentation workflow (templates, ToC, tracker, naming) | this pass |
| Gate architecture + surface-and-decide verdict policy | [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md) |
| QC runbook (breadth-first, per-assay, cited) | [qc_metrics.md](../data/qc_metrics.md) (+ grounding: qc_metrics-sources / -rare-disease / nf-core-conventions) |
| Data schema + metric registry (records, events, persistence) | [schemas.md](../data/schemas.md) · [metric_registry.md](../data/metric_registry.md) |

## Open questions & TODO

- **QC metrics** need a dedicated `data/qc_metrics.md`, grounded in real
  fastp/MultiQC/mosdepth fields (panel depth targets, uniformity, reads-PF,
  barcode/index metrics, contamination, variant-support). Top priority next batch.
- **Schema design** (records for the ledgers, corpora, and cards) is a dedicated
  upcoming discussion before `data/schemas.md` is written.
- Fine-tuning (LoRA on an open-weight model) is a future possibility; for now,
  structure and capture only (ADR-0007).
- System-view docs to add next: context, components, data-flow, interfaces,
  storage, workflows, deployment (design/).
- Wishlist parked for `scope-and-wishlist.md`: pgvector read-clustering /
  contaminant-QC, NLP variant-miner (PubMed/PMC + ClinVar; "candidate variants for
  expert curation"), RNA-seq, cloud deploy + Terraform, Jira/Teams/Discord
  adapters, granular agent profile.

## Distilled into

- [`docs/adr/`](../adr/) — ADRs 0001–0013.
- [`CLAUDE.md`](../../CLAUDE.md) · [`DOCUMENTATION_HABITS.md`](../DOCUMENTATION_HABITS.md) · [`TABLE_OF_CONTENTS.md`](../TABLE_OF_CONTENTS.md) · [`_templates/`](../_templates/) · [`planning/tasks.md`](../planning/tasks.md).
- [`requirements/scope-and-wishlist.md`](../requirements/scope-and-wishlist.md) · [`data/strategy.md`](../data/strategy.md).
- [`data/qc_metrics.md`](../data/qc_metrics.md) (+ `-sources`, `-rare-disease`, `nf-core-conventions`) · [`data/schemas.md`](../data/schemas.md) · [`data/metric_registry.md`](../data/metric_registry.md).
- [`design/frontend/frontend-design-brief.md`](../design/frontend/frontend-design-brief.md) + the `PipeGuard.html` prototype.
