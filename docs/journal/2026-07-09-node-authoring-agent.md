# Journal — 2026-07-09 (MST) — Node-authoring agent formalized (roster #5)

| Field | Value |
|---|---|
| **Focus** | Graduate the maintainer's "bring your own tools" concept (review point #11) from a line in the review→design brief into a tracked design item — roster agent #5 + a design note. |
| **Outcome** | New design note ([design/node-authoring-agent.md](../design/node-authoring-agent.md)); roster row #5 in [agents.md](../design/agents.md); T-046 in the tracker; crosslinked from the brief §4h, the ToC, and wishlist #9. No code — a proposed design item. |

## Discussion

**The idea.** Drop a tool's docs (nf-core `nextflow_schema.json`, `--help`, a Nextflow
module, or a README) → an **advisory agent proposes a typed `ToolNode` card** for the Pipeline
Builder palette (name + version, ports mapped to the `ArtifactKind` vocabulary, a schema-driven
param form, candidate locators). The human reviews / edits / accepts; it joins the palette. This
flips the builder from *configure the 7 seeded tools* to *bring your own tools* — the real unlock
behind custom profiles / typed ordering / versioning.

**Why it is safe to let an agent author components** (the load-bearing point). The Pipeline
Builder already supplies the two properties that de-risk generative authoring: (a) a **rigid,
typed target** — the agent fills a validated `ToolNode` shape, not free-form UI; and (b) a
**validation backstop** — the typed-wiring invariant rejects an incompatible edge at compose
time, and the gate is a terminal node with no data-edge input. Worst case, the operator edits or
rejects the proposed card. Blast radius zero. It stays advisory (ADR-0001): it authors a *card*,
never a run — draws no edge, never places a node on the gate, never touches a verdict.

**Layered, stub-first.** A surprising amount needs **no LLM**: `nextflow_schema.json` → a param
form is a pure parse, which **is wishlist #9**. So the build is the same stub|claude split as
triage/feedback (ADR-0006/0012): (1) a deterministic importer (the $0 stub, = #9), (2) an opt-in
Claude layer only for the fuzzy `ArtifactKind` mapping + unstructured `--help`/README, degrading
to the deterministic path on any error. Unknown kinds are **flagged for the human, never
invented** — the same data-honesty guardrail as everywhere. Build order: review-card UX +
palette-injection seam → importer (#9) → LLM layer.

## Decisions

| Decision | Distilled to |
|---|---|
| Node-authoring is roster **agent #5**, advisory + off-gate, proposed/design | [agents.md](../design/agents.md) roster; [node-authoring-agent.md](../design/node-authoring-agent.md) |
| It reuses wishlist **#9** (deterministic nf-core schema → form) as its $0 stub core | [scope-and-wishlist.md](../requirements/scope-and-wishlist.md) #9; the design note |
| Tracked as **T-046** (Phase 2); no new ADR until build (covered by 0001/0006/0009/0012) | [tasks.md](../planning/tasks.md) T-046 |

## Open questions & TODO

- The **review-card UX + palette-injection seam** in the Pipeline Builder is the first build
  step whenever this graduates (independent of the agent) — sits in the T-045 phase-2 /
  design-question bucket for claude-design.
- Whether to build the deterministic **#9 importer** on its own first (real value, $0) ahead of
  the agent framing — a scoping call for the maintainer.

## Distilled into

- [docs/design/node-authoring-agent.md](../design/node-authoring-agent.md) — the design note (canonical)
- [docs/design/agents.md](../design/agents.md) — roster #5
- [docs/planning/tasks.md](../planning/tasks.md) — T-046
- [docs/TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md) — indexed
