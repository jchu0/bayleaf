# 2026-07-13 (MST) — Agent-hardening design set + label casing

**Topic:** Design-first groundwork for hardening the System agents page and the agent layer
(no product code yet — the maintainer chose "design docs/ADRs first, then build"), plus a small
UI casing fix.

## Done

1. **Label casing → sentence case** (concrete change): "Sample Metadata" → **"Sample metadata"**,
   "System Agents" → **"System agents"** across `access.ts`, `Sidebar.tsx`, the two `PageHeader`
   titles, and the TopBar comment. Captured as **UIC-21** in
   [ui-conventions.md](../design/ui-conventions.md) (ref label = "Review queue"). `tsc -b` green.
2. **Node-author grounding check:** the frontend *is* wired to the live endpoint
   (`api.ts` → `/api/builder/node-proposal`, backend live on `claude-sonnet-5`). The maintainer's
   "not working / not live" was an earlier backend started without `BAYLEAF_NODE_AUTHOR_AGENT=claude`.
   Real gap = the minimal authoring **UX**, not wiring.
3. **"Operator profile" bar finding:** it's a **view-only, non-persisted** lean/granular toggle
   (gates Metric-catalog detail), redundant with the persisted **"Card density"** pref in
   `UserSettingsDialog`. Decision: consolidate into Card density; no settings-based *agent* scoping
   exists to remove (scope-by-wiring supersedes the idea).

## Design artifacts authored (all Proposed)

Anchored to the maintainer's stated ideas; six artifacts:

1. **[ADR-0023 — agent taxonomy & action boundary](../adr/ADR-0023-agent-taxonomy-and-action-boundary.md)**
   — the keystone. **Advisory agents** (unchanged, off the gate, ADR-0001/0006) vs. **tool-agents**
   wired into the graph that MAY take *bounded operational* actions (auto-retry) under a hard
   **action boundary**: never a verdict/finding/confidence/data write. Monitoring agent = first
   tool-agent; per-issue-class policy; capped; every action logged to an issue store that feeds
   pipeline-repair.
2. **[ADR-0024 — scope-by-wiring](../adr/ADR-0024-scope-by-wiring.md)** — an agent's file access =
   union of the output folders of the tools it's wired to; server-enforced (advances ADR-0022 from
   advisory hint); resolved from the **operator-configured data root** (the T7 volume note — data
   roots are never repo-local); reuses the `GET /api/files` sandbox + `deid.scrub_text`; access ≠
   authority. Retires settings-based agent scoping + folds the profile bar into Card density.
3. **[ADR-0025 — versioned/reversible agent config](../adr/ADR-0025-versioned-reversible-agent-config.md)**
   — tool-card config is an immutable, **git-backed tagged revision**; rollback = re-pin; a run pins
   the exact config tag so an action is attributable + reversible; structured for ML.
4. **[design/system-agents-chat.md](../design/system-agents-chat.md)** — chat surface (left
   agent-select panel + window over pipeline-repair/archivist) + `chat_store` (typed
   `ChatSession`/`ChatMessage`, off-gate store pattern); view-scoped archive/delete = **soft-delete,
   record retained for ML**.
5. **[design/agent-capabilities.md](../design/agent-capabilities.md)** — archivist read-only DB
   retrieval (de-id, cited); pipeline-repair issues+resolutions store + tool/bayleaf docs corpora;
   node-author authoring popup + doc-upload + **schema-delta-as-proposal** (human-approved, never
   auto-mutated) + **scaffolds-as-assets** (generalized to all agents).
6. **[design/monitoring-agent.md](../design/monitoring-agent.md)** — the monitoring tool-agent:
   tool-card config (issue-class checklist + free-text watch specs, dynamic), retry-vs-report,
   issue-store schema, leans on Nextflow `errorStrategy`/the durable `job_store` rather than
   reinventing retry.

## Invariants preserved / introduced

1. ADR-0001/0006 intact for advisory agents; the new *action boundary* is the guardrail that lets
   a tool-agent act without touching decisions/data.
2. Everything persisted is typed + retained for ML (per the structure-for-ML principle); editable
   assets are versioned/reversible.

## Next (deferred to build phase, on approval)

- Implement in the ADR-0023→0024→0025 dependency order; each design doc has an "open questions"
  section to resolve at build time (e.g. OOM retry needing a resource bump; archivist query DSL vs
  fixed parameterized queries; scaffold format).

**Related:** [TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md) (rows added) ·
[agents.md](../design/agents.md) · ADR-0001/0006/0022.
