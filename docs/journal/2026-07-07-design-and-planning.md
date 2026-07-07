# Journal — 2026-07-07 (MST) — Design & planning pass

| Field | Value |
|---|---|
| **Focus** | Step back from session-1 implementation; lock the concept, architecture, tech stack, and documentation workflow before further build. |
| **Participants** | James Hu, Claude Code |
| **Outcome** | Concept locked; documentation workflow stood up and tested on itself; 7 ADRs recorded. |

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
tools/rules are the gates (QC gate, variant gate); AI advises at each.

**Agents.** Build **one deep** agent (QC-triage), not many shallow — it proves the
pattern. Agent #2 = pipeline-repair, for recurring/systemic issues. All agents
advisory and off the critical path. "Upskilling" = retrieval over an experience
ledger, **not** fine-tuning.

**Issue handling.** Every issue gets a category + stable signature; a user can
acknowledge/suppress an issue class (with expiry/review) so they are never
re-prompted for a known-accepted condition — kills the "throw a person at it as
glue" anti-pattern. Recurring signatures escalate to the repair agent.

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
meaningful docstrings, why-comments, typed env config.

**Documentation workflow.** "Necessary" (not minimal) stack in folders; ADRs
renamed to `docs/adr/ADR-NNNN-*` so the ID survives a move; requirement IDs
`REQ-F/NF/C-NNN`; dated entries (MST); a **table of contents** as the session
entry point (scan, don't slurp — but bulk-load when the task genuinely needs it);
`docs/_templates/` with a check-before-create rule; **journal → canonical**
distillation; a **task tracker** (`docs/planning/tasks.md`) with parallel-safe
flags. Templates and the journal reformatted to a professional/tabular style.

**Git attribution.** Removed the "no AI attribution" rule; adding
`Co-Authored-By: Claude` going forward. Retroactive attribution of past commits
(history rewrite + force-push) is pending maintainer confirmation.

## Decisions

| Decision | Distilled to |
|---|---|
| Deterministic gate, advisory AI | ADR-0001 |
| Event-driven core + provenance ledger | ADR-0002 |
| Deployment-agnostic ports; Nextflow portability | ADR-0003 |
| VCF-first on GIAB HG002; dual real+synthetic data | ADR-0004 |
| Config layer + profiles | ADR-0005 |
| AI off by default + deterministic fallback | ADR-0006 |
| ML-ready structured outputs | ADR-0007 |
| Issue taxonomy + signature suppress/escalate | pending |
| Two corpora (knowledge + experience) as JSON/JSONL | pending |
| Ticketing = cards + notify ports + read API | pending |
| pyproject/uv single source; mypy/ruff; hook tiers | pending (Phase 0) |
| Documentation workflow (templates, ToC, tracker, naming) | this pass |

## Open questions & TODO

- **QC metrics** need a dedicated `data/qc_metrics.md`, grounded in real
  fastp/MultiQC/mosdepth fields (panel depth targets, uniformity, reads-PF,
  barcode/index metrics, contamination, variant-support). Top priority next batch.
- Retroactive commit attribution: co-author trailer vs author change; rewrite +
  force-push yes/no. (maintainer to confirm)
- System-view docs to add next: context, components, data-flow, interfaces,
  storage, workflows, deployment (design/).
- Wishlist parked for `scope-and-wishlist.md`: pgvector read-clustering /
  contaminant-QC, NLP variant-miner (PubMed/PMC + ClinVar; "candidate variants for
  expert curation"), RNA-seq, cloud deploy + Terraform, Jira/Teams/Discord
  adapters, granular agent profile.

## Distilled into

- ADRs 0001–0007 (`docs/adr/`).
- `CLAUDE.md`, `docs/DOCUMENTATION_HABITS.md`, `docs/TABLE_OF_CONTENTS.md`,
  `docs/_templates/`, `docs/planning/tasks.md`.
- Pending decisions above remain to be distilled into ADRs next pass.
