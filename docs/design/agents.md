# Agent Layer — development hub

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-09 (MST) |
| **Audience** | all (contributors and Claude Code) |
| **Related** | [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) · [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md) · [ADR-0009](../adr/ADR-0009-corpora-retrieval-upskilling.md) · [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) · [ADR-0007](../adr/ADR-0007-ml-ready-structured-outputs.md) · [ADR-0016](../adr/ADR-0016-postgres-port.md) · [architecture.md](architecture.md) · [planning/tasks.md](../planning/tasks.md) |

## Overview

The single map of PipeGuard's **agent layer**: the roster, the invariants every
agent must honor (captured **once** here), and the intake checklist for a new
agent idea. This is a **hub, not a decision record** — the *why* behind each
choice stays in the ADRs; this page indexes them and tracks development so the
layer stays coherent as it grows past one agent.

**Why a dedicated hub now (and not before).** With a single agent (QC-triage) the
ADRs + [tasks.md](../planning/tasks.md) sufficed. We are now weaving in more agent
ideas (pipeline-repair, archivist, and more), and a roster + shared-invariant page
prevents each new agent from re-deriving the guardrails or drifting from the
pattern. It answers "where does this new agent idea go?" in one click. **Decision:**
keep this hub as an index that points to the ADRs; never let it duplicate or
override them (if the two disagree, the ADR wins and this page is stale).

## Shared invariants — every agent MUST honor these

These are non-negotiable and identical for all agents. A design that violates any
of them is a bug, not a variant.

1. **Advisory only; rules decide.** An agent narrates, suggests, triages, or
   organizes. It **never** sets or overrides a verdict, confidence, or QC decision
   ([ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)). If a capability
   needs to *decide*, it belongs in the deterministic rule engine, not an agent.
2. **Off the deterministic critical path.** The gate produces its verdict with the
   agent layer entirely absent. Agents attach *after* the decision, never inside it
   ([ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)).
3. **Off by default, with a deterministic fallback.** Every agent is stub-first
   ($0, nothing leaves the machine), imports the SDK lazily, and **degrades to a
   deterministic stub** on any error — including a safety refusal
   ([ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md)). Enabled per-agent by
   an env flag (`PIPEGUARD_<AGENT>_AGENT=stub|claude`).
4. **Grounded and cited.** Where an agent makes claims, it is grounded in a curated
   corpus via retrieval and carries citations; evidence, assumptions, and generated
   suggestions stay separate ([ADR-0009](../adr/ADR-0009-corpora-retrieval-upskilling.md)).
5. **Scoped and model-tiered.** One agent, one job. The model tier is chosen per
   agent by task difficulty, not one-size-fits-all
   ([ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md)).
6. **Structured, ML-ready output.** Agent outputs are structured records with
   provenance, so they feed the experience ledger and downstream ML
   ([ADR-0007](../adr/ADR-0007-ml-ready-structured-outputs.md)).

## Roster

| # | Agent | Scope (the one job) | Status | Design | Model tier |
|---|---|---|---|---|---|
| 1 | **QC-triage** | On a flagged card, suggest a likely cause + next action, cited | **done** (T-015) | [`triage/`](../../src/pipeguard/triage/), [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) | mid |
| 2 | **Pipeline-repair** | On a recurring issue signature, propose a concrete, human-reviewed remediation | **done** (T-058) — advisory, **off the gate**; consumes a `RecurringSignature` from the monitoring rollup → a cited `RepairProposal{summary, attach_to, scope}` grounded in a curated remediation corpus; on-demand (`GET /api/monitoring/signatures/{signature}/repair`), NOT the deferred ~3× auto-escalation | [`pipeline_repair/`](../../src/pipeguard/pipeline_repair/), [ADR-0008](../adr/ADR-0008-issue-taxonomy-suppression-escalation.md)/[0012](../adr/ADR-0012-agent-scoping-model-tiering.md) | high / Opus (cross-run failure reasoning, ADR-0012 §3a) |
| 3 | **Archivist** | Index / organize / summarize / prepare exports across runs (the "librarian" over the data platform) | **done** (T-059) — advisory, **off the gate**; indexes/summarizes already-decided runs → `ArchiveDigest` (digest + export manifest + cross-run index); organizational not diagnostic; least-privilege input (no PII); never opens/moves/deletes a file or relabels an origin | [`api/archivist.py`](../../api/archivist.py), [data-platform-and-archivist.md](data-platform-and-archivist.md) §5 | low / Haiku (organizational, not diagnostic) |
| 4 | **Feedback-triage** | Categorize the off-gate in-app feedback corpus (category / area / sentiment / priority + recurring themes) to guide product iteration | **done** (T-043) — advisory, **off the gate** (never touches a verdict); PII-safe (aggregate-only Claude path) | [`api/feedback_agent.py`](../../api/feedback_agent.py), [ADR-0016](../adr/ADR-0016-postgres-port.md) | low / Haiku (categorization) |
| 5 | **Node-authoring** (tool-onboarding) | From a tool's dropped docs (nf-core `nextflow_schema.json` / `--help` / module / README), **propose a typed `ToolNode` card** for the Pipeline Builder palette — human reviews, edits, accepts | proposed — **design note for review** (T-046, Phase 2); advisory, **authors a card never a run** (draws no edge, never on the gate); stub-first with a deterministic importer (= wishlist #9) | [node-authoring-agent.md](node-authoring-agent.md) | low–mid (deterministic core; Claude only for `ArtifactKind` mapping) |

New ideas land as a roster row first (see intake below), then graduate to a design
doc / ADR + implementation.

## Intake — adding a new agent idea

Before writing code, run the idea through this checklist (keeps the layer honest):

a. **State the one job** in a sentence. If it needs two, it is two agents.
b. **Advisory test.** Does it only advise/narrate/organize, or does it need to
   *decide*? If it decides, stop — that is a **rule**, not an agent (invariant 1).
c. **Critical-path test.** Confirm the gate's verdict is unchanged whether the
   agent runs or not (invariant 2).
d. **Grounding.** Does it need a knowledge/experience corpus + retrieval, or is it
   structured-data-over-the-projection (cheaper, no corpus)? (ADR-0009)
e. **Model tier.** Pick the cheapest tier that does the job (ADR-0012).
f. **Register it.** Add a roster row; for anything non-trivial, add a design doc
   or an ADR capturing the *why*.
g. **Build stub-first.** Deterministic stub + lazy SDK import + fallback + env flag
   (invariant 3), mirroring [`triage/`](../../src/pipeguard/triage/).

## Where the code lives

1. Today: [`src/pipeguard/triage/`](../../src/pipeguard/triage/) (agent.py +
   retrieval.py + knowledge corpus + models.py) is the reference shape for any new
   agent.
2. **Folder plan (T-026, deferred).** When agent #2 (pipeline-repair) lands, move
   `triage/` → `agents/triage/` and add `agents/pipeline_repair/`. We do **not**
   create the `agents/<scope>/` folder for a single agent — it would be churn.
   Keep [`synthesis/`](../../src/pipeguard/synthesis/) (narration) and
   [`notify/`](../../src/pipeguard/notify/) (an outbound port) **out** of the agent
   bucket — they are not agents ([ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)).

## Relationship to the rest of the system

Agents observe the **analysis-output tree** and the **data platform** — the run
artifacts, decision cards, and QC records already produced by the gate — and emit
advisory, structured suggestions. They never touch the decision path or the
authoritative event ledger as a decision-maker. The output-tree convention and the
archivist's substrate are specified in
[data-platform-and-archivist.md](data-platform-and-archivist.md).

---

*Marker legend — distinguish claim types where confusion is likely:*
**Fact** · **Assumption** · **Decision** · **TODO**.
