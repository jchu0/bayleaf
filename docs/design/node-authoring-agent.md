# Node-Authoring Agent — build Pipeline Builder tool cards from dropped tool docs

| Field | Value |
|---|---|
| **Status** | Proposed — design note for review (Phase 2). Roster agent #5. |
| **Last updated** | 2026-07-09 (MST) |
| **Audience** | all (contributors and Claude Code) |
| **Related** | [design/agents.md](agents.md) (roster #5) · [design/frontend/pipeline-builder-brief.md](frontend/pipeline-builder-brief.md) · [design/frontend/README.md](frontend/README.md) (§4 node model) · [design/frontend/handoffs/2026-07-09-review-to-design.md](frontend/handoffs/2026-07-09-review-to-design.md) (§4h, §6) · [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) · [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md) · [ADR-0009](../adr/ADR-0009-corpora-retrieval-upskilling.md) · [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) · [scope-and-wishlist.md](../requirements/scope-and-wishlist.md) (#9, #11) · [planning/tasks.md](../planning/tasks.md) (T-044, T-046) |

> **Proposed for review.** Originated as maintainer review point #11 and was scoped in the
> review→design brief (§4h). This note graduates it from a brief line to a tracked design item.
> It is **advisory and off the gate** (ADR-0001); it authors a *card*, never a run.

## The one job

Given a tool's documentation dropped by the operator (an nf-core `nextflow_schema.json`, a
`--help` dump, a Nextflow module, or a README), **propose a typed `ToolNode` card** for the
Pipeline Builder palette — tool name + version, typed input/output ports mapped to the
`ArtifactKind` vocabulary, a schema-driven param form, and candidate output locators — for the
operator to **review, edit, and accept**. This flips the builder from *configure the seeded
tools* to *bring your own tools*, the real unlock behind custom profiles (#4), typed ordering
(#7), and pipeline versioning (#8).

## Why it is tractable and safe (unusually so for a generative feature)

The Pipeline Builder already supplies the two properties that make agent-authored components safe:

1. **A rigid, typed target.** The agent fills a validated `ToolNode` shape (see README §4 data
   contract), not free-form UI. Constrained, schema-bounded generation.
2. **A validation backstop.** A wrong proposal cannot corrupt a pipeline: the typed-wiring
   invariant rejects an incompatible edge at compose time (it springs back), and the gate is a
   terminal node with no data-edge input. The worst case is the operator edits or rejects the
   proposed card — blast radius zero.

## The flow

1. **Drop docs** → the agent extracts: tool name + version; the param set; the candidate input
   and output artifacts.
2. **Propose** a `ToolNode` as a **review card** in the builder (ports, params, candidate
   locators) — flagged clearly as an AI proposal.
3. **Human ratifies**: edit ports/params/locators, accept → it joins the palette (and, with #8,
   a saved custom pipeline version). Reject → nothing changes.

## The hard part: mapping tool I/O → the `ArtifactKind` vocabulary

Mapping a tool's outputs to `fastq / bam / vcf / mosdepth_summary / …` is the one fuzzy step.
Rules:
- The agent **suggests** kinds with a short rationale + a confidence signal.
- **Unknown or ambiguous kinds are flagged for the human, never invented** (the same
  data-honesty guardrail as everywhere — never fabricate; label uncertainty).
- The type system is the backstop: even a ratified-but-wrong kind is caught when the operator
  tries to wire it.

## Layered build — stub-first, then Claude (mirrors the other agents)

A surprising amount needs **no LLM**, so this is the same stub|claude split as triage/feedback
(ADR-0006/0012), and it reuses wishlist **#9** (the nf-core schema-driven form):

1. **Deterministic importer (the stub, $0):** an `nextflow_schema.json` → a param form is a
   pure parse — that is exactly what nf-core schemas are for (wishlist #9). This alone delivers
   most of the value with zero API cost and no fabrication risk.
2. **LLM layer (opt-in Claude):** adds value only for the fuzzy parts — the `ArtifactKind`
   mapping, and parsing unstructured `--help`/README when no schema exists. Lazy `anthropic`,
   degrade to the deterministic path on any error, off by default (`PIPEGUARD_*_AGENT=stub|claude`).

So this is not net-new scope — it is **#9 (schema form) + an ArtifactKind-mapping layer,
surfaced inside the builder**.

## Guardrails (advisory, off the critical path — ADR-0001)

- **Authors a card, never a run.** It proposes a `ToolNode`; it never draws an edge, never
  places a node on the gate, never sets/routes/restates a verdict. Compose ≠ execute holds.
- **Human-in-the-loop by construction** — the proposal is inert until the operator accepts it.
- **Stub-first / off by default** with a deterministic fallback (ADR-0006); the LLM path degrades
  to the deterministic importer on any error (incl. a safety refusal).
- **No fabricated kinds/params** — unknowns are surfaced, not guessed (data-handling guardrail).
- No clinical/diagnostic claims; a tool card is metadata, not a recommendation.

## Build order (when it graduates)

1. The **review-card UX + palette-injection seam** in the Pipeline Builder (needed either way,
   independent of the agent).
2. The **deterministic nf-core schema importer** (#9) — real value, $0.
3. The **LLM ArtifactKind-mapping + unstructured-docs layer** (opt-in Claude).

## Status / next

Proposed; **roster agent #5** in [agents.md](agents.md). Passes the agent-intake checklist
(one job; advisory-only; grounded in the tool's own docs; stub-first with a deterministic
fallback). Tracked as **T-046** (Phase 2). When built, it is covered by the existing agent ADRs
(0001/0006/0009/0012) — no new ADR unless a load-bearing decision emerges during build.
