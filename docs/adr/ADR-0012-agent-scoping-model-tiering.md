# ADR-0012 — Agent scoping and per-agent model tiering

| Field | Value |
|---|---|
| **Status** | Accepted · Partially realized (QC-triage agent #1, pipeline-repair agent #2, and the archivist librarian all built — advisory + off-path; per-agent model tiers realized as `BAYLEAF_*_MODEL` env knobs) |
| **Date** | 2026-07-07 (MST) · updated 2026-07-09 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0005](ADR-0005-config-layer-and-profiles.md), [ADR-0006](ADR-0006-ai-off-by-default-fallback.md), [ADR-0008](ADR-0008-issue-taxonomy-suppression-escalation.md), [ADR-0009](ADR-0009-corpora-retrieval-upskilling.md) |

## Context

Agents differ in task difficulty, call frequency, cost, and blast-radius needs.
A single model for every agent is either wasteful (expensive model on cheap,
frequent narration) or insufficient (cheap model on hard, systemic diagnosis).

## Decision

1. **Build one deep agent first** — QC-triage — then **pipeline-repair as agent #2**.
   Expand only after the core flow, provenance, and persistence are solid.
2. All agents are **advisory, off the deterministic critical path, and
   least-privilege** (each sees only its stage's data).
3. **Model is per-agent, selected via the config profile** (ADR-0005):
   a. pipeline-repair (rare, hard reasoning) → Opus 4.8 at high/xhigh/max effort,
      or ultracode.
   b. interface / narration agents (frequent, low-stakes) → Sonnet 5 / Haiku 4.5.
4. Every agent inherits **off-by-default + deterministic fallback** (ADR-0006).
   Rare expensive calls + frequent cheap calls keep the API budget efficient.

## Assumptions

- Task-difficulty tiering maps cleanly onto model tiering.
- Sensible per-agent defaults (overridable via config) are enough to ship; robust
  per-agent evaluation can wait.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| One model for all agents | Wasteful or underpowered depending on the choice |
| Many agents up front | Cost, complexity, and evaluation burden before the core exists |

## Consequences

| | |
|---|---|
| **Gains** | Cost/quality efficiency, small blast radius, easy tuning via config |
| **Costs** | Per-agent config and defaults to maintain |
| **Follow-ups** | Defaults land with the config layer and the agents |

## Realized (2026-07-09)

1. **Agent #1 (QC-triage) built** (`triage/`): advisory, off the deterministic critical path,
   selected via `BAYLEAF_TRIAGE_AGENT=stub|claude`, off by default with a stub fallback on any
   error incl. a safety refusal ([ADR-0006](ADR-0006-ai-off-by-default-fallback.md)). Its model
   defaults to a cheaper tier (`claude-sonnet-5` via `BAYLEAF_TRIAGE_MODEL`) than the Opus
   narration default — the per-agent model tiering this ADR called for.
2. **Agent #2 (pipeline-repair) built** (`pipeline_repair/`): the rare, hard cross-run-reasoning
   case Decision §3a reserves the top tier for. Advisory and off-gate — `advisory` is pinned and it
   holds no verdict authority ([ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md)); it consumes a
   `RecurringSignature` from the monitoring rollup, retrieves a curated remediation corpus
   (`knowledge/pipeline_repair.jsonl`, grounded in
   [ADR-0008](ADR-0008-issue-taxonomy-suppression-escalation.md)'s issue taxonomy;
   [ADR-0009](ADR-0009-corpora-retrieval-upskilling.md)), and emits a cited
   `RepairProposal{summary, attach_to, scope}` (`attach_to`/`scope`/citations are deterministic from
   the corpus, never the LLM). Selected via `BAYLEAF_PIPELINE_REPAIR_AGENT=stub|claude`, off by
   default with a degrade-to-stub fallback ([ADR-0006](ADR-0006-ai-off-by-default-fallback.md)). Its
   model defaults to the **Opus-high tier** (`claude-opus-4-8` via `BAYLEAF_PIPELINE_REPAIR_MODEL`)
   — exactly the expensive-but-rare tier §3a reserves for hard, systemic diagnosis. Invoked
   **on-demand** (`GET /api/monitoring/signatures/{signature}/repair`); the
   [ADR-0008](ADR-0008-issue-taxonomy-suppression-escalation.md) ~3× auto-escalation trigger that
   would route into it stays **deferred**.
3. **Archivist librarian built** (`api/archivist.py`): the low-stakes, *organizational* (not
   diagnostic) interface tier — Decision §3b's frequent/cheap case. Indexes and summarizes released
   runs into an advisory `ArchiveDigest`. Selected via `BAYLEAF_ARCHIVIST_AGENT=stub|claude`, off
   by default with a degrade-to-stub fallback. Its model defaults to the **Haiku tier**
   (`claude-haiku-4-5` via `BAYLEAF_ARCHIVIST_MODEL`) — the cheapest tier, matching the low blast
   radius of an organizing task.
4. **Per-agent model tiering realized** as the `BAYLEAF_*_MODEL` env knobs — Opus-high for
   pipeline-repair, Sonnet for QC-triage, Haiku for the archivist — the task-difficulty→model-tier
   mapping this ADR decided. Still env knobs today, **not yet** a composed config profile
   ([ADR-0005](ADR-0005-config-layer-and-profiles.md)).

## Revisit when

- An agent's default model underperforms in practice.
