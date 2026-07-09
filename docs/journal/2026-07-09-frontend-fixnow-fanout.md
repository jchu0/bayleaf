# Journal — 2026-07-09 (MST) — Frontend fix-now backlog, fanned out per screen

| Field | Value |
|---|---|
| **Focus** | Clear the fix-now bucket of the frontend fidelity/scale backlog (T-045) as parallel product-dev work, one write-agent per screen. |
| **Outcome** | All 6 screens' fix-now items shipped in one parallel wave (disjoint files, no collisions), verified centrally (tsc/lint/build clean + screenshots) and committed (02db752). |

## Discussion

**Why fan out.** After the design brief split the backlog into fix-now / phase-2 /
design-question, the maintainer noted the fix-now items are "less design, more product dev" —
mechanical, per-screen, and independent. A textbook case for CLAUDE.md Workflow-4 (parallelize
by default), so long as the **no-two-agents-touch-the-same-file** rule holds.

**Partition to avoid collisions.** Assigned each of 6 write-agents a screen + explicit,
disjoint file ownership: decision-cards owns `RunDetail`/`EvidenceTable`/`verdict.ts`; runs owns
`RunOverview`/`States`; the other four own only their screen file and *reuse* the shared tokens
without editing them. Agents were told to edit only (no git, no concurrent tsc/lint/build — the
orchestrator verifies centrally) and to **skip anything needing a new backend field** and report
it, rather than fabricate data.

**Result.** Clean run — 9 files, no collisions, `tsc`+`oxlint`+`build` green on the first
central pass. Screenshot-verified the highest-value fixes: Decision-cards **Dense** now renders a
real compact one-line row (was an empty body) with per-verdict left-stripes; Pipeline-Builder
edges now touch their ports; Settings' Lean/Granular actually changes the view (Lean hides the
metric catalog) with editable threshold inputs; Monitoring gained drill-throughs + a top-N cap +
an *honest* "all-time · not yet windowed" label (no false 14d).

**Honest limits.** The Monitoring repair-agent button is gated at count ≥ 3, which the small
demo data never reaches — the same low-volume-hides-features theme (item 12) the phase-2 synthetic
volume + scale kit will surface. Data-blocked items (run status/date/platform, sample_type,
server-side pagination/windowing, per-agent model tiering) were correctly skipped and stay in
T-045 as phase-2. Invariants held: nothing added sets or routes a verdict; copy stays honest.

## Decisions

| Decision | Distilled to |
|---|---|
| Ship the fix-now backlog as a parallel per-screen fan-out (disjoint files, central verify) | [tasks.md](../planning/tasks.md) T-045; this journal |

## Open questions & TODO

- T-045 **phase-2** (scale kit + synthetic volume + windowed backend aggregates + the QC metric
  readout + Pipeline-Builder editable locators/save/version) and **design-question** items remain
  → the claude-design brief.

## Distilled into

- [docs/planning/tasks.md](../planning/tasks.md) — T-045 fix-now bucket marked done
- [docs/design/frontend/handoffs/2026-07-09-review-to-design.md](../design/frontend/handoffs/2026-07-09-review-to-design.md) — the source backlog
