# Journal — 2026-07-07 (MST) — Design & planning pass

- **Focus:** Step back from session-1 implementation and lock the concept,
  architecture, tech stack, and documentation workflow before further build.

## What happened

Session 1 shipped a working vertical slice (deterministic rule engine + swappable
synthesizer + Streamlit dashboard) but got ahead of design and docs. This session
was deliberately design/research-only. Key reasoning captured below.

**Framing.** Locked on rare-disease **germline DNA panel**, short-read Illumina.
The layer sits *on top of* a clinical pipeline, so we simulate upstream rather than
touch licensed clinical products. Dropped RNA-seq (STAR/salmon) from the core — the
panel/variant-calling story is DNA. Rejected mixing modalities for legibility.

**Data strategy.** Go **VCF-first** so pipeline plumbing never blocks the product
(ADR-0004). Substrate is **GIAB HG002** — open, real Illumina reads, gold-standard
truth VCF + high-confidence BED, which doubles as evaluation ground truth. Two data
tracks: real GIAB (correctness/faithfulness) and **synthetic perturbations**
(labeled failure modes: sample swap, duplicate/missing barcodes, low reads-PF, low
Q30, coverage dropout, low-support variant, contamination, pipeline step failure).
Planted issues live in the operational layer only; clinical variants stay grounded
in ClinVar/GIAB truth. End-to-end generation via **nf-core/sarek** is a later
stretch (don't reinvent Nextflow; add usage docs when we get there).

**Architecture.** Event-driven core with an in-process bus and an append-only
**provenance ledger** — the event log *is* the provenance record, which also gives
the AI layer its multi-stage observation points (ADR-0002). Deployment-agnostic
**ports & adapters**; **Nextflow** carries compute portability across local /
Slurm / AWS Batch / HealthOmics, so we don't pick a cloud now (ADR-0003). Cloud
broker, LocalStack, Terraform, and AWS are wishlist.

**The product thesis (in the maintainer's words):** the AI layer is a cross-layer
**triage/observability accelerant that cuts diagnosis time** — replacing "comb the
logs ad nauseam." It reduces friction to the meat of the matter; it does not
replace tooling. Deterministic tools/rules are the gates (QC gate, variant gate);
AI advises at each (ADR-0001).

**Agents.** Build **one deep** agent, not many shallow (proves the pattern). Agent
#1 = QC-triage: subscribes to gate events, least-privilege inputs, grounded in two
corpora, outputs an advisory triage note with citations, hands off via a notify
port, and appends resolutions to an experience ledger ("upskilling" = retrieval,
**not** fine-tuning). Agent #2 = **pipeline-repair**, scoped to recurring/systemic
issues. All agents advisory and off the critical path (ADR-0001, ADR-0006).

**Issue handling (strong maintainer priority).** Every issue gets a **category +
stable signature**. A user can **acknowledge/suppress an issue class** (with
expiry/review) so they are never re-prompted for a known-accepted condition — kills
the "throw a person at it as glue" anti-pattern. **Recurring signatures escalate**
to the pipeline-repair agent. (ADR pending.)

**Corpora.** Two, behind one retrieval interface: a curated **knowledge corpus**
(tool docs, QC-metric definitions, failure signatures, runbook) and an append-only
**experience ledger** (issue → diagnosis → action → outcome, seeded from synthetic
cases). Stored as **JSON/JSONL**, pydantic-validated, pgvector-able later. (ADR pending.)

**Ticketing / HITL.** Don't rebuild ticketing. Three layers: cards-as-tickets
in-app (status lifecycle = the review queue) + outbound **notify ports** (Slack for
the demo; Jira/Teams/Discord config-driven) + an inbound **read API** so
integrators pull from us (the same seam that becomes the FastAPI backend). (ADR pending.)

**Config layer + profiles.** A profile composes deployment adapters + agent
topology + synthesis + notify + thresholds; layered resolution via pydantic-settings.
Deployment axis and agent axis correlate with segments (research/HPC/lean ↔
biotech/cloud/granular). Ship lean, document granular (ADR-0005).

**Tooling / hygiene.** `pyproject.toml` as sole dependency source; **uv** project;
**mypy** + **ruff**; pre-commit (ruff, secret scan, mypy) / pre-push (pytest) /
batch (full eval incl. real-SRA validation, pip-audit). Coding standards: type
hints everywhere, meaningful docstrings, why-comments, typed env config. (Phase 0.)

**Documentation workflow.** "Necessary" (not minimal) stack in folders; ADR-per-file
to avoid infinite scroll; dated entries (MST); a **table of contents** as the
session entry point (scan, don't slurp); `docs/_templates/` with a check-before-create
rule; **journal → canonical** distillation; doc-to-code map. This journal entry and
the foundation docs are the first test of that workflow.

## Decisions made
- Deterministic gate, advisory AI — ADR-0001.
- Event-driven core + provenance ledger — ADR-0002.
- Deployment-agnostic ports; Nextflow portability — ADR-0003.
- VCF-first on GIAB HG002; dual real+synthetic data — ADR-0004.
- Config layer + profiles — ADR-0005.
- AI off by default + deterministic fallback — ADR-0006.
- Issue taxonomy + signature-based suppress/escalate — ADR pending.
- Two corpora (knowledge + experience) as JSON/JSONL — ADR pending.
- Ticketing = cards + notify ports + read API — ADR pending.
- pyproject/uv single source; mypy/ruff; hook tiers — ADR pending (Phase 0).
- Documentation workflow (templates, ToC, dating, journal→canonical) — this pass.

## Open questions / TODO
- **QC metrics** deserve a dedicated `docs/data/qc_metrics.md`, grounded in real
  fastp/MultiQC/mosdepth output fields (panel depth targets, uniformity, reads-PF,
  barcode/index metrics, contamination, variant-support). Top priority next batch.
- Push `archive/session-1` to `jchu0`, or keep local-only? (maintainer to confirm)
- Confirm "environment" coding standard = config-management + bioconda tool env (both).
- Fresh `README.md` (production-framed) — pending, with the architecture doc.
- Wishlist parked in scope-and-wishlist.md: pgvector read-clustering / contaminant-QC,
  NLP variant-miner (PubMed/PMC + ClinVar, "candidate variants for expert curation"),
  RNA-seq, cloud deploy + Terraform, Jira/Teams/Discord adapters, granular agent profile.

## Distilled into
- ADRs 0001–0006 (`docs/design/decisions/`).
- `CLAUDE.md` (working agreement, coding standards, doc rules, design invariants).
- `docs/DOCUMENTATION_HABITS.md`, `docs/TABLE_OF_CONTENTS.md`, `docs/_templates/`.
- Remaining decisions above are ADR-pending; to be distilled next pass.
