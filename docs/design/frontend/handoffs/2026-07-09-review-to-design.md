# Review → Design handoff — 2026-07-09 (frontend, post-parallel-burst)

| Field | Value |
|---|---|
| **Purpose** | Hand a scoped, prioritized design brief to **claude design** after a burst of parallel frontend work. Folds the maintainer's 15 review points together with a 6-agent fidelity + scale audit of the built React app vs the design handoffs. |
| **Audience** | claude design (+ contributors) |
| **Sources** | The built app (`frontend/src/`), the operator-UI handoff (`../operator-ui-handoff-README.md`), the Pipeline Builder handoff (`../README.md`, `../pipeline-builder-brief.md`), the prototype (`../PipeGuard.html`). |
| **Status** | Brief — recreate faithfully in the React codebase; not code to ship verbatim. |

## 0. How to read this

> **These are observations of the live local React app, not a prototype diff.** The maintainer
> evaluated the *running app* as a product. The prototype (`PipeGuard.html`) is a reference **only**
> for the items explicitly tagged "see PipeGuard.html" (e.g. the console side-by-side layout, the
> port-linked edges, the Decision-card layout) — it is **not** a gold standard. Several gaps here
> (Tidy, drag-and-drop, the static canvas, no-op export verbs, read-only locators) exist in the
> prototype **too** — it's an MVP mockup as well — so those are **build-forward**, not a copy-back.

Every item is tagged one of three ways so you can triage effort:

- **`fix-now`** — a small, cheap gap in the live app. Some are **prototype-referenced** (recover the affordance the prototype already shows); others are **build-forward** (the prototype has the same limitation) — both are low effort, just don't assume "copy the prototype" always fixes it.
- **`phase-2`** — a real feature the handoff itself defers, or that needs backend support (a new field/endpoint) before the UI can be honest.
- **`design-question`** — needs a product/design decision; this is where your input matters most. Consolidated in §6.

**The through-line:** the live app reproduces the prototype's *low-volume* design and inherits its limitations, and three systemic things break as a product — (a) **no scale affordances anywhere**, (b) **the controls meant to absorb volume are inert or broken**, and (c) **several hero surfaces are display-only** (Settings can't edit, Pipeline Builder can't emit, Decision cards' density lever produces empty bodies). Fixing (b) is nearly free and is the highest-leverage work.

---

## 1. Cross-cutting themes (the "why" behind the per-screen list)

1. **No scale affordances.** All six data screens render a fully-materialized flat `.map()` — no search, verdict/facet filter, pagination, virtualization, or working density. The demo's 3 runs × ~5 samples is the only thing hiding it; a real run (20–30+ analytes), dozens of runs, or hundreds of findings turns every list into an unbounded scroll wall. **This is the #1 theme (maintainer item 12).**
2. **The volume controls are broken/inert.** Decision-cards' density switcher (Dense → empty body, Brief → stripped), Settings' Lean/Granular toggle (no-op), and Pipeline Builder's search/param/export verbs all do nothing.
3. **Display-only surfaces.** Settings can't author the config it exists to edit; Pipeline Builder can't produce its deliverable (`run_layout.yaml`); the Decision card's per-gate QC metric readout is unbuilt.
4. **Server-side work done in the client.** Monitoring N-fans-out every run's full `RunDetail` on mount and aggregates *lifetime* (not 7d/14d-windowed) totals with no bound.
5. **Missing states.** No skeletons/Retry on Runs, no empty-filter state on Decision cards, no "Run released" state, and a generic `ErrorBox` that hides all cards instead of a verdict-preserving synthesis-error state.

---

## 2. The scale kit — one shared component closes the biggest theme (maintainer #12)

Rather than bolt scale controls onto each screen, ship **one reusable list-surface kit** and drop it into the five unbounded lists. It should provide, composably:

- **Search** (by id / subject / free text), **facet filters** (per-verdict chips with counts: `Escalate (12)`), **sort** (recency / urgency), **pagination or virtualization** (windowed rows), and a **density** toggle (comfortable / compact).
- **Empty / loading / error** slots (skeleton rows + Retry, "no matches → clear filter").
- **Grouping** with sticky headers + per-group collapse (e.g. group Decision cards by verdict).

Drop it into: **Runs list · Decision-cards stream · Agent-triage flagged-sample selector · Monitoring recurring-signatures + throughput · Settings threshold/catalog tables.** `design-question`: pagination vs virtualization (infinite scroll reads better for a triage stream; a table wants pages) — pick per surface.

**Backend seam this needs (phase-2):** `GET /api/runs` and the run detail should accept `page/limit/verdict/q/sort`; Monitoring needs a **windowed aggregate endpoint** (7d/14d/30d) instead of the client fan-out.

---

## 3. Synthetic data at volume (maintainer #12 — the enabler)

The audit could only *reason* about scale because the data can't exercise it. Add synthetic volume so scale breaks surface visually and can be designed against:

- A **large run** (25–30 analytes) and a **high-finding sample** (a gate with 8–12 findings) to stress the Decision card, the QC readout, and the triage selector.
- **Dozens of runs** across a date range with a real `status` (running / review / released) + `platform` + `date`, to stress the Runs list, Monitoring windows, and sorting.
- Recurring signatures across many runs/dates to stress Monitoring's signature list + trend/window semantics.

This is partly a **data-model** ask (see Runs / Monitoring below): `RunSummary` must carry `platform`, `date`, and a real `status` end-to-end.

---

## 4. Pipeline Builder — the design scope (maintainer #1–#9, #11)

The MVP renders the seeded germline chain faithfully but is a **static mockup**: hardcoded 2560×460 canvas with literal node coords + 16 static edge paths, read-only locators, inert params, and no-op export verbs — it cannot produce `run_layout.yaml`. The design goal is to make it a real, scalable authoring surface while keeping the load-bearing invariants (composes ≠ executes; gate terminal + no verdict control; agents port-less).

### 4a. Fix-now gaps (some prototype-referenced, some build-forward)
- **#2 Port-anchored edges** *(prototype-referenced — "see PipeGuard.html")*. The build dropped the prototype's `-12px` port margins, so port dots sit ~12–16px *inside* the card padding and every edge stops short. Fix: restore the port offsets **and** compute edge endpoints from actual port anchor positions (not hardcoded `d` strings) so edges visibly link an **output port → the next node's input port**, and recompute on zoom/move. (This also unblocks #7/#3.)
- **Validation rows** are inert single-color `<div>`s that ignore each row's `sev` *(the prototype colors them by severity — recoverable)*. Make them severity-grouped (critical/warn/info), colored, and **click-to-focus** onto the offending node.
- **#1 Console layout** *(side-by-side is prototype-referenced; adjustable + pop-out are build-forward)*. Validation list and `run_layout.yaml` should sit **side-by-side** (see prototype); the console should also be **height-adjustable** (drag handle) and **pop-out** (detach to a modal / new window) for large YAML — neither the app nor the prototype does that yet. Today it's a fixed 240px pane.
- **Palette search** is a decorative `<div>` — make it a real filtering input. **Params** are uncontrolled `defaultValue`. **Copy/Download/Emit** are no-ops. Note: **these are no-ops in the prototype too** (`bCopy`/`bDownload`/`bTidy` are empty in the source) — so this is **build-forward** (make the deliverable-producing verbs actually work), not a copy-back from the prototype.

### 4b. #3 Real interactivity + the authoring model
The MVP is "configure a known pipeline." Layer up in this order:
1. **Editable Locators** (the load-bearing surface: `path|glob`, `parser`, `required`, `role`, `on_multiple`) → this is the one thing the screen exists to produce; wiring it + params → a **live** YAML preview is the core interactivity.
2. **Working Emit** (download/copy the real YAML; the VIEW-only linked-run strip + Fork-to-draft bridge).
3. **Phase-2 authoring**: drag from palette, free edge-drawing, a layout engine (replacing the hardcoded frame), a run picker for VIEW.

### 4c. #4 Profile → a searchable combobox (my recommendation)
Replace the 3-way segmented switch (can't scale past ~4, and the data contract already allows arbitrary custom layout paths) with a **combobox**: built-in profiles (`default` / `giab_panel` / `sarek`) + the user's saved profiles + **"＋ New profile from current graph."** The profile *is* the `run_layout` profile key backed by a saved `PipelineGraph`, so this is the entry point for users authoring their own pipelines (ties to #8).

### 4d. #7 Ordering — enforced by types, shown by lanes (my recommendation)
Illegal order (e.g. alignment after variant-calling) should be **unrepresentable, not merely validated**:
- **Typed-port compatibility is the real guard** (already an invariant): a variant caller's `bam` input has no upstream source if placed before alignment, so the edge is unwirable — order falls out of the type system. Surface it: an incompatible drop springs back with a mono toast (`fastq → vcf — incompatible artifact-kind`).
- **Stage-lane columns** for visual sense: each `StageKind` is an x-lane in pipeline order (read_qc → align → markdup → coverage → variant_call → filter → qc_aggregate → gate); nodes **snap to the 20px grid + their stage lane** on drag. Group/order the **palette by stage** too.

### 4e. #8 Save · version · approval (my recommendation)
The graph is "non-authoritative authoring state" whose only grounded output is `run_layout.yaml` — but the maintainer's ask (save-with-confirm, tracked builds → pipeline versions, an approval gate for tiered/multi-user) is a real product need. Recommend:
- A **`PipelineGraph` version record**: `{ id, version, saved_at, author, status }` (the `schemaVersion: builder/0.1` already exists). **Save-with-confirm** writes a new version; **Emit** stamps the graph version into the emitted YAML so a run is traceable to the exact pipeline that produced its layout.
- Persist graphs in a **pipeline-graphs store, off the decision domain** (mirror the feedback-store seam — its own table, never the `Repository`).
- **Approval gate** for tiered orgs: a graph moves `draft → pending-approval → approved` (mirror the review-queue **reviewer vs approver** RBAC we already built); only an **approved** graph emits a "blessed" config. **Reserve the `version` + `status` fields in the data model now** even if the workflow is phase-2.

### 4f. #5/#6 Known phase-2 (per the handoff)
Tidy/auto-layout is a no-op (phase-2); palette tiles have a `cursor-grab` but no DnD handlers → either **wire drag-and-drop** or drop the misleading cursor + restore the prototype's "free drag is Phase 2" footer note.

### 4g. #9 Other suggestions (mine, to consider)
Minimap for the wide canvas · **diff-vs-last-emitted** (see what changed before Emit) · inline **validation badges on offending nodes** (the V-checks) + click-to-focus · canvas node **search/highlight** · **linked-run history** (which runs used this graph/profile) · **undo/redo** · an **"explain this node"** popover (what the tool does + why `ours`/`consumes`/`substitute`) · collapse the reference rail.

### 4h. #11 The node-authoring agent (radical concept — I think it's a strong north-star)
Drop a tool's docs (a Nextflow module, `--help`, a `nextflow_schema.json`, or a README) → an **advisory agent proposes a typed `ToolNode`**: name + version, **input/output ports mapped to the `ArtifactKind` vocabulary**, a param form generated from the schema, and **candidate locators**. The human **reviews / edits / accepts**, and it joins the palette.
- **Advisory, never auto-wiring** — it *proposes* a card; it never draws an edge, never places the node on the gate, never touches a verdict. This mirrors the triage / feedback-agent pattern (stub-first, opt-in Claude, off-gate, degrade-to-stub).
- **The hard part is the `ArtifactKind` mapping** — the agent *suggests* kinds for a tool's outputs; **unknown kinds are flagged for the human, never invented** (same data-honesty guardrail as everywhere else). A wrong kind is caught by typed-wiring at compose time.
- Scope: a **phase-2 "node-authoring agent" (roster agent #5)**. It turns the builder from "configure the 7 seeded tools" into "bring your own tools," which is the real unlock behind #4/#7/#8.

---

## 5. Per-screen requests

### 5a. Decision cards (maintainer #10 — "doesn't match the prototype")
The audit confirms several divergences. **Fix-now:** re-add the **per-verdict left-stripe** (collapsed cards should read their verdict at a glance); restore the **sample-type + origin chips** in the header (the current chip shows the gate, not the origin tag); show **all cited evidence** (today truncated to `evidence[0]`, dropping the source-kind chip + Field/locator column); move the **GateResult strip** first-in-body as a full-width band; put **platform + date** back in the subtitle; **make the density lever work** — Dense currently renders an **empty body** (`showBody = open && density !== 'dense'`), Brief is stripped (rich content gated behind `density==='split'`); stop **auto-expanding every flagged card** + add **expand-all/collapse-all**; add the **empty-filter state**. **Phase-2:** build the **per-gate QC metric readout** (import the already-written `MetricsPanel`, populate `metric_values` as a Metric·Observed·Threshold·Status table, flagged-first) — *this is the hero content of the screen and it's unbuilt*; the **288px context rail** (needs new `DecisionCard` fields); a **Run-released** + **verdict-preserving synthesis-error** state; **pagination/virtualization** + in-run search at 20–30+ samples. **Design-question:** the body currently injects `TriagePanel` + `DecisionFeedback` (not in the spec) while omitting the spec'd **View-lineage / Ask-agent** rail buttons — reconcile which belongs; grouping-by-verdict with headers.

### 5b. Runs
**Fix-now:** four **shimmer skeleton** rows (not one pulsing line); an **error state with Retry**; the **status pill** in the center column; **verdict-bar segment tooltips**; a **clear-filter** action on empty. **Phase-2 (needs `RunSummary` fields):** carry **platform · date · a real status** (`running|review|released`) end-to-end — today "Released" is inferred from `n_attention===0`, so a still-running run with 0 attention is **mislabeled Released**; **pagination** + run **search/lookup**. **Design-question:** sort / date-range control; per-verdict facet chips (not just attention buckets); a density/compact control.

### 5c. Agent triage
**Fix-now:** give selector chips a **verdict dot/tint** (can't tell escalate from hold today); add a **max-height + scroll** to the Ask-the-agent thread; restore the **quick-ask preset chips**. **Phase-2:** the **flagged-sample selector** is a single flex-wrap row of pills — at 20–30 analytes it becomes a wall that pushes the triage card off-screen → give it search / verdict tabs / a scroll cap (reuse the scale kit); cap/scroll the **citation columns**. **Design-question:** a user-facing **offline/live source toggle** (§6) vs the current env-gated inference.

### 5d. Monitoring (maintainer #13 — "zero interactions; signatures need metadata")
The audit fully confirms it. **Fix-now:** add the **"Repair agent" escalation** button on a recurring signature (count ≥ 3 → the review queue) — the one interaction the screen specifies; restore the **"· 14d" window label**; **cap the signatures list top-N**; add **drill-throughs** (a throughput bar → that run's Decision cards; a signature → a rule-filtered queue). **Phase-2 (needs backend):** signature **metadata the maintainer asked for** — *when* (dates/times), *which runs*, **trend ▲/▼**, **hide-by-occurrence** — needs a time-series aggregate; move off the **client-side N-fanout** to a **windowed aggregate endpoint** (the KPIs + gate pass-rates currently accumulate over *all* history, unbounded); restore the **Median-review-time** KPI + the **7d/14d/30d** window control; window/cap the **verdicts-over-time** chart.

### 5e. Settings (maintainer #14)
**Fix-now:** make the **Lean/Granular toggle** actually change rendered density (the `profile` state is never read — Lean and Granular render identically); make the **QC-threshold steppers editable** (today read-only `<td>`s); fix the **copy** that claims "keyed per assay × sample type" when neither dimension is shown; add the per-model **cost column** the prototype shows. **Phase-2:** **key thresholds on assay × sample type** (blood/saliva columns; the dimension is dropped from the `QCThreshold` type end-to-end); surface the **Teams + Discord** notify options (backend shipped them, UI still shows only Slack); **per-agent model tiering** (synthesizer / triage / feedback — needs a defined agent×model matrix); scale the threshold + metric-catalog tables (unbounded dumps today). **Design-question (the maintainer's richer vision):** thresholds edited via **fill-and-save with sanity guardrails + a recorded/audited edit + RBAC** (rather than raw ± steppers) — needs decisions on bounds, who may edit, and the audit format. This is a real "config authoring" surface; recommend the same **draft → save → (approve)** shape as the pipeline-graph versioning (§4e) for consistency.

---

## 6. Design questions that need a product call (consolidated)

1. **Scale interaction model per surface** — infinite-scroll+virtualize (triage stream) vs paginated tables (Settings) vs load-more? Grouping-by-verdict with sticky headers on Decision cards?
2. **Decision card body** — reconcile the spec'd View-lineage/Ask-agent rail vs the shipped TriagePanel + DecisionFeedback; which is canonical?
3. **Settings threshold editing** — ± steppers vs fill-and-save-with-guardrails + audited edit + RBAC; bounds + who-may-edit + audit format.
4. **Per-agent model tiering** — the agent set (synthesizer / triage / feedback / …) × the model matrix.
5. **Pipeline Builder profile authoring** (#4) + **save/version/approval** (#8) — the version + approval-status model, and whether approved-only graphs may emit.
6. **The node-authoring agent** (#11) — worth building? It reshapes the builder from "configure 7 tools" to "bring your own."
7. **Offline/live agent source toggle** — user-facing control vs env-gated.

---

## 7. Suggested sequencing

1. **Fix-now cleanup (cheap):** the Decision-cards density lever + left-stripe/chips/evidence, the Pipeline-Builder port edges + validation coloring + wired export/params, Runs skeletons/Retry/status-pill, Settings toggle + editable steppers + honest copy, Monitoring's repair-agent button + window labels. A mix of prototype-recoverable affordances and small build-forward wiring — all low-effort live-app gaps.
2. **The scale kit + synthetic volume** (§2/§3) — one component + a data-model + a large synthetic run; the single highest-leverage design investment.
3. **The hero build:** the Decision-card **QC metric readout** (§5a) — the reason that screen exists.
4. **Backend-enabled phase-2:** windowed Monitoring aggregate, `RunSummary` status/date/platform, paginated list endpoints.
5. **Pipeline Builder authoring** (§4b–§4h): editable locators → live YAML → save/version → (phase-2) drag authoring + the node-authoring agent.

*Everything here preserves the load-bearing invariants: rules decide / AI advises; agents off the critical path (port-less in the builder); composes ≠ executes; origin never relabels up; no confidence meter; no clinical claims.*
