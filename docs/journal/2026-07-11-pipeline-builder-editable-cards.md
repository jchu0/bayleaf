# Journal — 2026-07-11 (MST) — Pipeline Builder: card redesign + editable pipeline + versioning lifecycle

| Field | Value |
|---|---|
| **Focus** | Redesign the Pipeline Builder node cards to a Databricks-style spec, then turn the read-only linked germline into a real editable, versionable pipeline surface. |
| **Participants** | maintainer, a Fable design agent (card design + iterative UI passes), engineering (render-switch + versioning slices), an Explore agent (architecture map). |
| **Outcome** | Cards fully redesigned; the germline is now editable/movable/removable UserNodes carrying run-status, with sources + FASTQ-input + file-output as first-class nodes and a lock+version lifecycle (ADR-0019 slices 1a/1b/1c). |

## Discussion

**Card redesign (many iterative Fable passes).** Started from a self-contained HTML mockup grounded in
`docs/design/builder-cards/*.md`, then ported it into the real `BuilderCanvas`/`BuilderShared`/`index.css`
over several maintainer-feedback rounds: larger cards + typed ports flush to the edge (a border-offset bug
where ports resolved against the padding box, fixed once) + wire-to-tip; kind-coloured wires; mono tool
names; theme-aware stage strips; card-state shading; a top-left legend. The port model gained a
`required|optional|reserved` state + a `CARD_PORTS` catalog; mosdepth gained 3 optional wireable outputs
(the only new graph ports). Later the layout was reworked to **ports on left/right only, balanced per side**,
with **three gray boxes** (REQUIRED / REFERENCE / OPTIONAL·RESERVED) carrying **REQ/REF/OPT/RSVD** tags in
aligned columns, connector **numbers moved outside** the card, and the run-status moved onto the **left
spine** (the 0–6 order badge was tried, then removed at the maintainer's call).

**Optional vs reserved.** Clarified: *optional* = connectable now (its kind has a producer); *reserved* =
documented but not-yet-wireable (no producer for its kind). Kept them distinct (OPT vs RSVD tags), didn't merge.

**Editable pipeline — the coupling.** Making the linked germline editable collided with the run-status: status
(`vstatus`) lived on the read-only seeded ToolCards, while editing lived only in the UserNode layer. An Explore
pass mapped the architecture: `showSeeded = isLinked` gates the seeded layer; the UserCard layer is always
rendered from `userNodes`; the gate/ingest are ungated, but the gate `run/` port + agent + terminal connectors
were under `showSeeded`. Save already serialized `userNodes`+`userEdges` (so saving the *linked* view saved an
empty topology — a real gap).

**The versioning model (maintainer design input → ADR-0019).** A run pins `{pipeline_name, version}`;
samples stay immutably linked to the version that produced them. A pipeline is **locked while its run is
active**, editable once complete/stopped; editing then **mints a new version** on Save while the run stays
pinned. Git is the model, the versioned `PipelineGraphStore` is the implementation, git-backing is the
production seam. The demo linked run is complete → editable.

**Implementation (by hand, after two background agents hung mid-task).** Slice 1a: `UserNode.vstatus`;
`germlineTemplate()` expanded to carry vstatus + include the reference sources as `ins:[]` nodes + ref edges;
a `showTerminals` split so the germline renders as editable UserCards while the terminals stay; the linked doc
now opens with `userNodes = germlineTemplate()` and `showSeeded=false`. Slice 1b: a `runLocked` gate on the
Edit toggle + a lock/editable indicator on the linked strip + a run-pinning message on Save. Slice 1c: a
FASTQ-input source (wired to fastp so the first card is fed) + a droppable File-output sink.

**Multi-session hazard.** A parallel session was concurrently adding Nextflow code-generation to
`BuilderModals.tsx`/`PipelineBuilder.tsx` (intermixed in shared files). Since `PipelineBuilder.tsx` imports the
parallel session's `NextflowExportModal`, the checkpoint commit (`cf8c0ae`) unavoidably carried both — noted in
the commit body. The repo's workflow is direct-to-`main`.

## Decisions

| Decision | Distilled to |
|---|---|
| Pipeline versioning + run-pinning + edit-lock lifecycle; git-model / versioned-store impl / git-backing seam | [ADR-0019](../adr/ADR-0019-pipeline-versioning-run-pinning-edit-lock.md) |
| Cards: left/right balanced ports, three gray boxes + REQ/REF/OPT/RSVD tags, numbers outside, spine=run-status | [design/builder-cards/README.md](../design/builder-cards/README.md) (needs a follow-up sweep) |
| Keep optional vs reserved distinct (connectable vs documented-not-wireable) | this journal + builder-cards specs |

## Open questions & TODO

- **Spine+branch layout** — the germline is still a single row; the maintainer prefers the mockup's two-row
  (spine + a branch row for mosdepth/MultiQC). A deferred layout pass (positions + the hardcoded fit/minimap/tidy consts).
- **Reference cards multi-port** — a reference source has ONE output but feeds several tools, so edges branch off
  edges (tangled). Give reference cards one output *port per consumer* to declutter.
- **Left nav collapse + usable canvas surface** — the inspector opening shrinks the workspace; add a left-nav
  collapse, and expand the placeable surface to match the visible canvas (INNER_W/INNER_H vs the drop area).
- **Slice 2 (backend)** — real `run → {name, version}` linkage + sample-version immutability + the git-backed store.
- **Docs sweep** — the builder-cards specs (§ port sides, boxes, tags), `design/frontend/README.md` §6, and
  `requirements/functional.md` (Pipeline Builder REQs) should be swept to match the shipped card + editable model.

## Distilled into

- [ADR-0019](../adr/ADR-0019-pipeline-versioning-run-pinning-edit-lock.md) (new).
- Commit `cf8c0ae` (slices 1a+1b + the card redesign); slice 1c follows.
