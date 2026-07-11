# Journal — 2026-07-11 (MST) — Pipeline Builder: edge clarity, toolbar consolidation, off-canvas decision boundary

| Field | Value |
|---|---|
| **Focus** | Six frontend-only passes over the Pipeline Builder (commits `a03704f`→`3d531de`), maintainer-directed: make multi-connection edges legible, consolidate a cluttered two-row toolbar, make the deterministic gate/ingest terminals movable then (on further maintainer synthesis) remove them from the canvas entirely into a read-only "Decision boundary" view. |
| **Participants** | maintainer, engineering (Claude Code, direct-to-`main`). |
| **Outcome** | Builder canvas now holds ONLY composable content (tools/refs/input/output) + the movable advisory agent — 15 nodes → 13. The deterministic ingest→gate boundary is viewable on demand via a new `DecisionBoundaryModal.tsx` in the toolbar's "⋯ More" menu. No verdict palette remains anywhere in the Builder. `Save`/`Emit`/compile still serialize only `{nodes:userNodes, edges:userEdges}` — unchanged. |

This session continues the same day's earlier card-redesign/editable-pipeline work
([2026-07-11-pipeline-builder-editable-cards.md](2026-07-11-pipeline-builder-editable-cards.md), ADR-0019)
and the UIC-16 card-geometry closure (commit `12a9913`, see [journal 2026-07-11 D2/D3](2026-07-11-d2-d3-share-egress.md)
for that day's other threads). It does **not** duplicate those entries — it picks up where they left
off, on the same canvas, later the same day.

## Discussion

**Pass 1 — split multi-connection ports + occlusion-aware layout (`a03704f`, 09:02).** Two edge-clarity
problems on the typed-port graph, both layout-only (the graph model — `ins`/`outs`/`idx` — and the save
contract untouched):
1. *Split ports so edges never merge.* Any port (in or out) wired to N cards used to render as ONE laid
   point that N wires all converged on, so unrelated wires visually merged at the card edge (e.g.
   `samtools-markdup`'s `bam` output feeding both mosdepth and bcftools-call looked like one thick line).
   Generalized the existing reference-source multi-port rule to every port: a wired port now splits into N
   laid **sub-ports**, one per edge, each independently nearest-side-anchored at its own target
   (`anchorForEdge(id, dir, idx, eid)`, keyed by the edge's own index — its `eid`). Verified in the live DOM:
   18 wires → 36 unique endpoints, zero shared start/end. Split halves still share a `pidx` so the box-row
   UI groups them back into one numbered row (e.g. `bam · out · [4][5]`) — card heights unaffected.
2. *Prefer layouts where wires aren't hidden behind cards.* An offline occlusion scorer (coordinate descent
   over the real `routeEdge` polyline, penalizing displacement) found one minimal move — the Panel BED
   reference card's x-position, 800→1150 — that cleared 3 of 7 occlusions (its own wire to mosdepth was
   routing behind markdup; two `reference_fasta` fan-out lanes also cleared). Residual 4 are inherent
   long-reach fan-in/fan-out wires (fastp→MultiQC, reference_fasta fan-out) — left honest rather than
   force-routed; fixing them is a constraint-router problem, out of scope for a coordinate-descent nudge.

**Pass 2 — toolbar consolidation + kind-coloured wires (`4df8f2e`, 09:13).** The toolbar had drifted to
~14 flat controls across two rows, with the run identity rendered twice (once in a status pill, once in
the linked-run strip). Restructured into one row: mode toggle · New · Open · Cancel (draft-only) ·
doc name · a **state-only** lock/draft pill (dropped the repeated run id) · a compact
`v{version} · status · Approve (approver+pending only) · role toggle` cluster · the profile combobox · a
divider · the **primary compose flow** (Save · Validate · Emit, Emit stays accent-primary) · a new
**"⋯ More"** overflow (Export to Nextflow, Run hand-off always; Fork/Provenance/Decision-cards
linked-view-only) — every handler/destination byte-identical, just relocated. The linked-run strip below
became the single home of the run identity, shown once. Separately (unrelated code path, same commit):
each `userEdge` now strokes with `kindColor(srcKind)` — the same fastq-violet/bam-blue/vcf-teal/
reference/QC-gold family the seeded wires and port borders already used — instead of a flat accent, so a
composed wire's data type reads at a glance. The advisory agent→tool dotted edges stay a visually distinct
dashed accent (never a data kind) — data vs advisory stays legible.

**Pass 3 — movable ingest/gate/agent + drop the hardcoded tethers (`73b2a68`, 09:34, maintainer request).**
Two changes, `BuilderCanvas.tsx` only: (a) removed the hardcoded dotted terminal connectors
(norm→ingest, MultiQC→ingest, ingest→gate — fixed-pixel SVG paths keyed to `INGEST_X`/`GATE_X`) and the
gate's fake dashed `run/` input half-circle — these were display-only decoration, never real graph edges,
and had started reading as a fabricated data path once the rest of the wiring became dynamic/typed.
(b) Made the three special cards (ingest, gate, agent) **movable like tool cards** via canvas-local
`termPos` state — explicitly **not** the graph (`movable ≠ composable`, ADR-0001): verified `Save` still
posts only `{nodes:userNodes, edges:userEdges}` and `germlineTemplate()` emits no `g_gate`/`i_ingest`/
`a_qc_triage` node. This pass turned out to be an intermediate step — see Pass 6.

**Pass 4 — duplicate-key fix (`c0420f2`, 09:47).** A pre-existing (since Pass 1) transient React
duplicate-key warning: the port/box leaf lists keyed off `pidx`/`cidx`, which are stable in the *settled*
layout but can transiently collide on the very first render (before edges resolve and multi-edge ports
split). Fixed by keying these stateless, fully-derived leaves by array index instead — safe because
handlers read `p.idx`/`n.id`, never the React key. No behavior/layout change; verified zero DOM key
collisions in a fresh tab (15 nodes / 33 ports at this point, before Pass 6 dropped the terminals).

**Pass 5 — agent-attach edit-only + remove both gate verdict bars (`4d4823d`, 10:02, maintainer notes
2 of 3).** (1) Agent attach/detach is now **edit-only**: a new `advisoryEditable={!isView}` prop gates the
tool card's corner advisory badge — in Edit it toggles attach/detach (every eligible tool shows a badge,
filled when attached, dashed when available); in View it becomes a read-only indicator rendered **only**
for already-attached tools (no handler; a press falls through to card-select). (2) Removed **both** gate
verdict bars still left in the Builder — the linked-run strip's `GATE VERDICT` label + color bar +
proceed/hold/escalate counts, and the `GateCard`'s own segment bar + verdict-readout footer (`GATE_H`
156→116) — leaving only the three preflight/qc/variant checkpoint dots (category colors, not the verdict
palette). After this pass the Builder carried **no verdict palette anywhere**. The maintainer's "note 3 of
3" — how the ingest/gate connector-ports should be represented — was explicitly deferred pending a design
call; that call landed the same session, below.

**Pass 6 — THE KEY DECISION: move the deterministic boundary off the canvas (`3d531de`, 10:19, maintainer
synthesis).** Rather than keep iterating on how the ingest/gate cards should look on-canvas, the
maintainer's synthesis was: *a fixed boundary card still eats real estate in an already-cluttered area, so
remove the deterministic terminals from the canvas entirely and surface them as viewable content on
demand.* Concretely:
1. **Removed** `IngestBand` and `GateCard` — their renders, function definitions, the `ShieldCheckSmall`
   glyph, the ingest/gate minimap rects, and the now-dead `INGEST_*`/`GATE_*` constants and
   `GATE_CHECKPOINTS`/`Database`/`Lock` imports (the checkpoints list itself is kept, exported from
   `BuilderShared`, and reused by the new modal). Collapsed the three-terminal `termPos` state down to an
   agent-only `agentPos`; `startTermDrag`→`startAgentDrag`; dropped `TERM_SELECT`. Canvas node count
   **15 → 13**. The advisory **agent stays on the canvas** — still movable and attachable (edit-only, from
   Pass 5), its fan-out ports and dotted links intact. The gate's leftover escalate-red spine tone left
   with the card — there is no longer any escalate/verdict color anywhere in the Builder (the only
   remaining "red" is the delete-x, not a gate verdict).
2. **New `frontend/src/components/DecisionBoundaryModal.tsx`** — a read-only left→right view (Composed
   pipeline → Deterministic ingest → Decision gate → Verdict) reusing the same `GATE_CHECKPOINTS` category
   colors, with explicit copy making the boundary legible: *"rules decide; not part of what you
   compose"* and *"every run passes through ingest → gate automatically."* Opened from a new "**Decision
   boundary**" item in the toolbar's ⋯ More menu (always available, not linked-view-gated, since it is
   pure static explanatory content, not run-specific data).
3. `NewPipelineModal`'s blank-canvas copy was de-staled to match (it used to describe the on-canvas
   terminals).

**Why this is the cleanest ADR-0001 story for the UI.** The gate and ingest were never composable nodes —
they don't accept a data edge from a tool, they can't be duplicated/deleted/reconfigured, and no click on
them changes anything about the pipeline. Wearing tool-card affordances (movable, selectable, occupying a
canvas coordinate) implied a false peer relationship with the things the operator actually composes. Taking
them off the canvas and making them a **named, always-reachable, read-only explainer** instead is not a
new decision so much as the UI finally matching the decision ADR-0001 already made: rules decide the
verdict; the canvas is where you compose the pipeline that *feeds* that decision, not where the decision
lives. See [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) Realized §, item 3 (added this
session).

**Verification (stated per claim, not just asserted).** Every commit message records its own live-verified
check (grep'd from `git log`, not re-derived here): Pass 1 — 18 wires / 36 unique DOM endpoints, occlusion
7→4 (`git show a03704f`); Pass 2 — 5 distinct kind colors on solid wires (`git show 4df8f2e`); Pass 3 — 3
terminal tethers → 0, 3 advisory edges preserved (`git show 73b2a68`); Pass 4 — 15 nodes / 33 ports, 0 key
collisions in a fresh tab (`git show c0420f2`); Pass 5 — console verified clean, no dup-key regression
(`git show 4d4823d`); Pass 6 — canvas renders no ingest/gate, agent retained, ⋯ More → Decision boundary
opens/closes on Escape, console clean (`git show 3d531de`). All six: `tsc` + `oxlint` clean. `Save`/`Emit`/
`POST /api/pipelines/compile` still serialize only `{nodes: userNodes, edges: userEdges}` throughout — the
ingest/gate/agent canvas positions were never part of that payload before this session and are not now.

## Decisions

| Decision | Distilled to |
|---|---|
| Remove the deterministic ingest + gate from the Pipeline-Builder canvas entirely; surface them as a read-only "Decision boundary" view in the toolbar's ⋯ More menu, reachable on demand rather than occupying canvas space | [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) Realized §, item 3 (new) — a UI-level reinforcement of the existing decision, not a new ADR |
| Toolbar consolidates into one compose bar (Save · Validate · Emit primary) + an "⋯ More" overflow for occasional actions, with the linked-run identity shown exactly once | [design/frontend/README.md](../design/frontend/README.md) §6 · [design/ui-conventions.md](../design/ui-conventions.md) UIC-17 (new) |
| Agent attach/detach is edit-only; View shows attachment as a read-only indicator on attached tools only | [design/frontend/README.md](../design/frontend/README.md) §6 |

## Open questions & TODO

- The occlusion scorer's residual 4 unresolved wire-behind-card cases (fastp→MultiQC fan-in,
  reference_fasta fan-out) are left honest, not force-routed — a real constraint router is future work if
  it becomes a legibility problem at higher node counts.
- `design/frontend/pipeline-builder-brief.md` (the original design brief) still describes an on-canvas gate
  node + ingest band — treated as a maintainer design deliverable (like `briefs/`/`handoffs/`), not
  updated in this sweep; the *living* docs (`design/frontend/README.md`, `design/builder-cards/README.md`,
  `design/ui-conventions.md`) now carry the current, shipped state and note the divergence.
- No backend/API/`src/pipeguard/` change in this session — confirmed via `git show --stat` on all six
  commits (every diff scoped to `frontend/src/components/BuilderCanvas.tsx`,
  `frontend/src/components/BuilderShared.tsx`, `frontend/src/screens/PipelineBuilder.tsx`, and the new
  `frontend/src/components/DecisionBoundaryModal.tsx`).

## Distilled into

- [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) (Realized §, item 3).
- [design/frontend/README.md](../design/frontend/README.md) §6 (Toolbar, Edge clarity, Nodes, Advisory
  agents sections updated).
- [design/builder-cards/README.md](../design/builder-cards/README.md) (§5 cross-reference to the
  off-canvas boundary + the split-port/occlusion refinement).
- [design/ui-conventions.md](../design/ui-conventions.md) (new UIC-17).
- [design/architecture.md](../design/architecture.md) (new Wave-12 bullet, Component map §4).
- [requirements/functional.md](../requirements/functional.md) REQ-F-045 (addendum correcting the stale
  "gate is a terminal locked node" on-canvas claim).
- [planning/tasks.md](../planning/tasks.md) (new task row T-124).
