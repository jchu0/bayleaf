# Handoff: PipeGuard Pipeline Builder → React

## Overview

The **Pipeline Builder** is the editable face of PipeGuard's operations layer: a
node-graph editor where an operator composes a germline-panel pipeline from typed tool
nodes, snaps in the advisory QC-triage agent, and — as the machine-readable output —
**emits `run_layout.yaml`**, the artifact-kind → path/glob map PipeGuard reads to locate
a run's artifacts. It is the **editable superset of the read-only Provenance canvas**:
the same left→right stage DAG and click-to-open per-node I/O drawer, plus authoring
affordances.

It is **one screen** (`view: 'builder'`) that extends the PipeGuard operator UI. Three
boundaries are load-bearing and are rendered as **visible UI guarantees**, not just
copy:

1. **Composes; does not execute.** No control runs a tool. The primary action is
   **Emit config**, never "Run."
2. **The deterministic gate still decides.** Nothing composed — and no agent snapped in —
   can set, override, restate, or route a verdict.
3. **Agents are advisory and off the critical path.** Agent nodes have **zero data
   ports**, so an agent→gate data edge is unrepresentable.

There is **no confidence meter** anywhere (carried from the operator UI; confidence is
deliberately omitted until grounded).

> This package **extends** the operator-UI handoff. Read
> **`operator-ui-handoff-README.md`** (included) first — the builder **reuses its app
> shell, tokens, and primitives verbatim**. Only the surfaces below are net-new.

---

## About the design files

The files here are **design references created in HTML** — a clickable, high-fidelity
prototype of intended look + behavior. **They are not production code to ship.** Recreate
the screen in the target codebase's **React** environment, reusing its patterns and
component library. The operator UI's brief specifies **React + shadcn/ui or Mantine**,
`lucide-react` icons — build on the same.

- **`PipeGuard.html`** — self-contained; **open in any browser**, then go to
  **Configure → Pipeline builder** in the left nav. Toggle **Edit / View** in the
  sub-header; open the **Validate & emit console** at the bottom; select any node to open
  the inspector; switch the **profile** (default / giab_panel / sarek) to change the
  emitted YAML.
- **`source/PipeGuard.dc.html`** — annotated source. The `<script>` logic class holds the
  builder's **mock data** (`bTools`, edges, seeded coordinates, the three
  `run_layout.yaml` strings, validation rows). Treat it as the data contract.
  (`source/support.js` is the prototype runtime — reference only, do not port.)
- **`pipeline-builder-brief.md`** — the authoritative product spec (full rationale,
  invariants, phasing). This README is the implementation-facing digest of it.
- **`operator-ui-handoff-README.md`** — the base operator UI this screen extends.

## Fidelity

**High-fidelity (hifi).** Final layout, colors, typography, spacing, and interactions.
Recreate faithfully using the codebase's libraries. Exact values are under
[Design tokens](#design-tokens); pull specifics from `source/PipeGuard.dc.html` when in
doubt.

---

## How it extends the operator UI

The builder does not invent a visual paradigm — it is the Provenance stage/node card + I/O
drawer with authoring affordances. **Reuse the shell wholesale**: 236px dark nav
(`#141a21`) + 56px top bar + light content (`#eef1f4`).

- **Nav:** add one item — **"Pipeline builder"** (`view: 'builder'`, `git-branch` glyph)
  — in the **Configure** group, **above Settings**. Cross-link: an "Edit this pipeline"
  affordance on Provenance opens the builder; the builder's linked-run strip deep-links
  back to Provenance + Decision cards.
- **Two deltas from every other view** (both intentional): (1) the builder is a
  **full-content-width three-pane workspace and the canvas scrolls horizontally** — it
  does **not** honor the 720–1080px max-width cap; (2) before a run exists, tool nodes are
  a neutral **`draft`** state with **no** pass/warn/fail color (the `ok/warn/blocked`
  coloring only lights up in linked **View**).

---

## The screen — regions & layout

Below the app's 56px top bar, the builder is a vertical stack:

1. **Sub-header toolbar (44px)** — `Edit | View` segmented toggle · the graph id
   (`PIPE-2026-07-08-GERMLINE-PANEL`, mono, truncates) · a state badge
   (**Draft — not run** / **Linked · RUN-…**) · spacer · **profile switcher**
   (`default / giab_panel / sarek`) · action cluster **Tidy · Validate · Emit** (Emit is
   the primary/filled button). VIEW|EDIT and the verbs live here, not the top bar.
2. **Linked-run strip (48px)** — **VIEW mode only**: "Linked to RUN-…", the run's
   segmented verdict bar + counts, and deep-links **Open Provenance**, **Open Decision
   cards**, **Fork to new draft**.
3. **Three panes** (fill remaining height): **Palette (240px, collapsible to a 44px
   rail)** · **Canvas (flex, min 480px, scrolls H+V)** · **Node inspector (360px, appears
   on selection, otherwise hidden)**.
4. **Validate/Emit console** — dockable bottom drawer: **36px** collapsed handle,
   **240px** expanded, **default collapsed**.

### (a) Canvas — the node-graph editor
Left→right DAG on a dot-grid (`#dbe1e8`, 20px pitch = the snap grid). The MVP ships the
germline chain **pre-laid-out** (seeded coordinates below); the operator **selects nodes,
edits params/locators, re-points inputs, toggles the agent/gate** — a *configure-a-known-
pipeline* experience, **not** free composition (that's Phase 2).

- **Tool node** — 208px card, radius 12px, shadow `0 1px 2px rgba(16,24,40,.05)`, a **3px
  left-rail status tint**. Shows: tool name (Plex Sans) + version (Plex Mono); typed I/O
  ports (mono kind labels) on left (in) / right (out); a **`pipeguardStatus` badge**
  (`ours` → "ours" · `full` → "consumes" · `partial` → "substitute"); a status/draft
  label. **Reference input ports render as a hollow ring** ("never gated").
- **Draft vs linked:** in **Edit** every tool node is neutral `draft` (surface-3 bg,
  dashed border, `draft` label). In **View** it flips to `ok/warn/blocked` (solid border,
  colored left-rail, real label).
- **Gate node** — terminal, rightmost, **non-deletable / non-duplicable** (lock glyph),
  min-height 96px, carrying the three checkpoint chips (preflight `#1f6feb` · qc `#1f5fd0`
  · variant `#0e8f7e`). **No data-edge inputs, no threshold/verdict control.** Draft label
  `pending — no verdict`; in View it shows the run's segmented verdict bar.
- **Ingest band** — a slim greyed **non-composable** system element between the last tool
  and the gate, captioned `deterministic ingest · write_run_dir → run/ (5 CSVs)`.
  Metric-bearing outputs draw thin "located-by-config" connectors into it; the band draws
  one connector into the gate. This is why composition can't move the verdict.
- **Agent node** — a dashed **advisory pill** side-attached above the spine (accent
  border, `--accent-weak` fill, "ADVISORY" eyebrow, `stub|claude` dot), connected by a
  **dashed** advisory line to the node it observes. **No ports.**
- **Edges** — orthogonal elbow, 1.5px `--border-strong`; kind label is the mono port
  label (artifact-kind is **not** color-coded). Reference edges are 1px dashed `#8b95a1`.
- **Zoom** controls float bottom-left (−/%/+/Fit). Pan/zoom is navigation; drag-authoring
  and auto-layout are Phase 2.

### (b) Palette (240px, collapsible)
Search box on top; sectioned with the shell's eyebrow labels: **Tool nodes** (by stage) ·
**Contamination** (NGSCheckMate) · **Agents** (QC-triage active; Pipeline-repair &
Archivist greyed "planned") · **Gate** (single pinned tile). In the MVP the palette is
present but authoring is confined to the pre-seeded chain.

### (c) Node inspector (360px) — the load-bearing config surface
Appears on selection. Header (icon + tool + version + close). Tabs **Params · Locators ·
I/O · Agents**:
- **Params** — a **schema-driven form** generated from the tool's bundled
  `nextflow_schema.json` (label, help, value). Never a code editor; schema is
  bundled/pinned (offline-first).
- **Locators** — for each output kind, the editable fields the config emits:
  **`path | glob`**, **`parser`** (`null` = pointer-only), **`required`**,
  **`role: output | reference`**, **`on_multiple: first | all | error`**, **`origin`**.
  This panel *is* the artifact-kind → path map for one node. **`origin` is locked to
  `unknown`** with the note *"Config locates inputs; it cannot relabel provenance. Origin
  is stamped at ingest from the run's marker."*
- **I/O** — rows `name · sha256 · size · origin`; `—` placeholders in draft, filled from
  the ledger in View.
- **Agents** — toggle QC-triage for this node's checkpoint; `stub | claude` (default
  `stub`, $0).
- Selecting the **gate** opens a **threshold-read-only** inspector (runbook table) linking
  to Settings → runbook. Selecting the **agent** shows its advisory config
  (`attachTo`/`scope`/`tier`/`mode`).

### (d) Validate + emit console (bottom drawer)
- **Validation list** — grouped most-severe-first (reuse severity `critical #cf3238 ·
  warn #c1560f · info #1f6feb`). All MVP checks are **static, zero filesystem I/O** (V1–V8,
  below). Each row is click-to-focus → selects the offending node.
- **Config preview** — a live, read-only **`run_layout.yaml`** for the selected profile,
  with **Copy** / **Download** and the `PIPEGUARD_RUN_LAYOUT` env hint.
- **Emit config** — the builder's primary action. Writes/exports the config only;
  triggers **no** execution.

### (e) Linked-run VIEW (MVP = link-out)
Binding a `runId` flips to **View**: node dots light `draft → ok/warn/blocked` from the
ledger projection, I/O drawers fill with real `name · sha256 · size · origin`, the gate
shows the run's verdict summary, and **authoring is locked**. **Fork to new draft** is the
only VIEW→EDIT bridge (clones the layout; never mutates the run). No in-app execution in
MVP; when a run is gated it goes through `run_gate` (builder emits config → Nextflow runs →
deterministic ingest writes run/ → `run_gate` gates + records the ledger → decision cards).

---

## The node & agent model

Three node kinds only: `tool`, `agent`, `gate`. Data edges connect **tool→tool** and
**tool→(ingest)→gate**. Agents are never on a data edge. The type system is shaped so
violating an invariant is *unrepresentable*, not merely validated:

- **Typed ports + embedded locator.** Ports are typed by the `ArtifactKind` vocabulary.
  Every **output** port carries the locator mapping its kind to a `path`/`glob` — wiring
  an output *is* writing an artifact-kind → path entry, which is why serialization is
  nearly mechanical.
- **Typed edges, no coercion.** An output of kind X connects only to an input of kind X.
  Incompatible drops **spring back** at draw time — no edge is created, so there is no
  persisted "invalid edge" state.
- **Agent = port-less.** An `AgentNode` has no `outputs`/data ports; it `attachTo` the node
  it **observes** (`scope` = checkpoint). Attached to the gate, it observes the gate's
  emitted **decision-card output**, never an input. `mode` defaults to `stub`; any error
  degrades to the stub; toggling to `claude` never changes graph validity or the verdict.
  Sanctioned roster only: `qc_triage` (MVP), `pipeline_repair`/`archivist` (greyed).
- **Gate = terminal, singular, non-removable.** No incoming tool `DataEdge`; it reads the
  frozen five `run/` CSVs (`samplesheet, reads, coverage, variants, pipeline`) produced by
  `write_run_dir`. Verdict is a data kind you can't route, and there's no verdict/agent
  input port to inject one. `aggregate_verdict()` is the only writer.
- **Serialization.** The graph is **non-authoritative authoring state**; its **sole
  emitted, grounded deliverable is `run_layout.yaml`**. Persist the graph for reload if you
  like, but not as a durable PipeGuard-owned contract. Emission is compose-time and
  triggers nothing.

---

## Interactions & states

**Interactions (stable IDs):** INT-1 select/configure a pre-seeded node (MVP core loop) ·
INT-2 connect/re-point typed ports (incompatible springs back + a mono toast
`fastq → vcf — incompatible artifact-kind`) · INT-3 inspector (Esc / blank-click to
deselect) · INT-4 edit params/locators (origin picker disables guarded values) · INT-5
snap the QC-triage agent · INT-6 **Validate + Emit** (the only MVP verbs) · INT-7 pan/zoom
(navigation) · INT-8 bind a run → View.

**States (each wired to a real fetch):** ST-1 empty (seed-template CTA) · ST-2 loading
(shimmer skeletons) · ST-3 invalid graph (critical ring + declarative console messages) ·
ST-4 emit error (non-destructive banner + Retry; agent errors degrade to stub) · ST-5
draft (composed-but-not-run; I/O `—`, gate `pending — no verdict`) · ST-6 linked-to-a-run
(read-only View).

### Validation rules (all static, zero I/O — invalid graphs cannot emit)
`V1` typed-port compatibility · `V2` required config satisfied · `V3` gate reachable via
ingest (the metric-bearing kinds `fastp_json`, `mosdepth_summary`, `vcf`/`filtered_vcf`,
optional `ngscheckmate` are produced) · `V4` gate terminal/singular/non-removable · `V5`
agents strictly off-path · `V6` origin `unknown` on every emitted locator · `V7` ambiguous
glob (info) · `V8` DAG only · `V-loc` locator well-formedness · `V10` emission
all-or-nothing.

### Builder state object (verbatim target)
```js
mode: 'edit',            // 'view' | 'edit' (default 'view' when a runId is bound)
runId: null,             // bound run for VIEW; null for a fresh draft
profile: 'giab_panel',   // 'default' | 'giab_panel' | 'sarek' | '/path/to/custom.yaml'
selectedNode: null,      // node id | null
inspectorTab: 'params',  // 'params' | 'locators' | 'io' | 'agents'
paletteOpen: true,
drawerOpen: false,       // validate/emit console (default collapsed)
zoom: 1,
validation: [],          // GraphError[] (empty = clean)
dirty: false,
```
*(The prototype uses the same shape prefixed `b*` — `builderMode`, `bProfile`,
`bSelected`, `bTab`, `bPaletteOpen`, `bDrawerOpen`, `bZoom`.)*

---

## Data contract (one contract)

The graph is authoring state; **the verdict is never stored on it** — it is computed at run
time by `run_gate`. The graph's deliverable is the `RunLayoutConfig`.

```ts
type ArtifactKind =
  | 'fastq' | 'bam' | 'bai' | 'recal_cram' | 'recal_table'
  | 'mosdepth_summary' | 'fastp_json' | 'markdup_metrics' | 'samtools_stats'
  | 'vcf' | 'gvcf' | 'filtered_vcf' | 'joint_vcf' | 'ngscheckmate'
  | 'multiqc_json' | 'versions_yml' | 'params_json' | 'execution_trace';
type ReferenceKind = 'reference_fasta' | 'panel_bed' | 'truth_vcf'; // role:'reference', never gated
type OriginTag  = 'real-giab' | 'synthetic' | 'contrived' | 'unknown';
type NodeStatus = 'ok' | 'warn' | 'blocked';   // linked-VIEW only
type RunStatus  = 'ours' | 'full' | 'partial'; // badge labels: ours / consumes / substitute

interface Port {
  id: string; kind: ArtifactKind | ReferenceKind; role: 'output' | 'reference';
  direction: 'in' | 'out'; required: boolean; cardinality: 'one' | 'many';
  locator?: LayoutLocator;                    // on output ports — the machine-readable seam
}
interface Edge {                              // typed dataflow ONLY
  id: string; from: {node:string;port:string}; to: {node:string;port:string};
  kind: ArtifactKind | ReferenceKind;         // === both ports' kind (incompatible can't be created)
}
interface ToolNode {
  id: string; type: 'tool'; tool: string; version: string; stage: StageKind;
  pipeguardStatus: RunStatus; inputs: Port[]; outputs: Port[];
  params: Record<string, string|number|boolean|object>;
  paramSchemaRef: string;                     // bundled nextflow_schema.json id (no live fetch)
  status?: NodeStatus;                        // linked-VIEW only; absent in draft
  ui: { x: number; y: number };
}
interface AgentNode {                         // structurally NO ports, NO verdict/confidence field
  id: string; type: 'agent'; agent: 'qc_triage'|'pipeline_repair'|'archivist';
  attachTo: string; scope?: 'preflight'|'qc'|'variant'; advisoryOnly: true;
  enabledBy: string; mode: 'stub'|'claude'; tier?: string; ui: {x:number;y:number};
}
interface GateNode {                          // NO ports; verdict COMPUTED at run time, never persisted
  id: string; type: 'gate'; terminal: true; removable: false; singular: true;
  gates: ['preflight','qc','variant']; reads: string[]; // the five run/ CSVs, NOT raw tool outputs
  runbookProfile: string; emitsLedger: true; status?: NodeStatus; ui: {x:number;y:number};
}
interface PipelineGraph {
  id: string; schemaVersion: 'builder/0.1'; template?: string; runbookProfile: string;
  nodes: (ToolNode|AgentNode|GateNode)[]; edges: Edge[]; emits: { runLayoutProfile: string };
}
// ---- the EMITTED deliverable ----
interface LayoutLocator {
  kind: ArtifactKind | ReferenceKind;
  path?: string; glob?: string;               // exactly one of path | glob
  parser: string | null;                      // dispatch key; null = pointer-only
  required: boolean; role: 'output' | 'reference';
  onMultiple: 'first' | 'all' | 'error';
  origin: OriginTag;                          // ALWAYS 'unknown' at emit; stamped at ingest
}
interface RunLayoutConfig {
  schemaVersion: 'run_layout/1';
  profile: 'default' | 'giab_panel' | 'sarek' | string;
  locators: Record<string, LayoutLocator>;    // selected via PIPEGUARD_RUN_LAYOUT
}
```

### Emitted `run_layout.yaml` (giab_panel — every `origin` is `unknown`)
```yaml
schema_version: run_layout/1
profile: giab_panel                 # PIPEGUARD_RUN_LAYOUT=giab_panel
locators:
  fastq:            { glob: "fastq/*_R{1,2}_001.fastq.gz",  parser: null,             required: true,  role: output,    on_multiple: all,   origin: unknown }
  fastp_json:       { path: "qc/HG002.fastp.json",           parser: fastp_json,       required: true,  role: output,    on_multiple: error, origin: unknown }
  bam:              { glob: "align/*.md.bam",                parser: null,             required: true,  role: output,    on_multiple: error, origin: unknown }
  markdup_metrics:  { path: "qc/HG002.markdup.txt",          parser: markdup_metrics,  required: false, role: output,    on_multiple: error, origin: unknown }
  mosdepth_summary: { path: "mosdepth/HG002.summary.txt",    parser: mosdepth_summary, required: true,  role: output,    on_multiple: error, origin: unknown }
  filtered_vcf:     { glob: "variants/*.norm.filtered.vcf.gz", parser: vcf,            required: true,  role: output,    on_multiple: error, origin: unknown }
  multiqc_json:     { path: "multiqc_data/multiqc_data.json", parser: null,            required: false, role: output,    on_multiple: error, origin: unknown }
  reference_fasta:  { path: "reference/GRCh38.fa",           parser: null,             required: true,  role: reference, on_multiple: error, origin: unknown }
  panel_bed:        { path: "reference/panel.bed",           parser: null,             required: true,  role: reference, on_multiple: error, origin: unknown }
  truth_vcf:        { path: "reference/HG002_benchmark.vcf.gz", parser: null,          required: false, role: reference, on_multiple: error, origin: unknown }
```
`default` uses `recal_cram`/`recal_table` (never coerced to `bam`); `sarek` is
illustrative/target-state. All three are in the prototype's profile switcher.

---

## Design tokens

**Reuse verbatim** from the operator UI: type (IBM Plex Sans + **IBM Plex Mono** for every
id, path, hash, version, kind, size), the core light palette, verdict 4-shade, gate accents
(preflight `#1f6feb` · qc `#1f5fd0` · variant `#0e8f7e`), finding severity, origin tags,
the stage/node card, status chips, the I/O drawer, the schema-driven form. Shape/motion:
chips 20px, buttons/inputs 8px, cards 11–14px, icon tiles 8–12px; card shadow
`0 1px 2px rgba(16,24,40,.05)`; fade-rise ~.28s, shimmer ~1.3s.

**Two color channels stay separate:** status/verdict (node left-rail, gate chips) vs
artifact-kind. **Artifact-kind is NOT color-coded** — it rides the mono port label;
`role:'reference'` is the one visual distinction (a hollow ring).

**New builder measurements**

| Element | Spec |
|---|---|
| Workspace | full content width (breaks the cap); Palette **240px** (collapse → 44px) · Canvas **flex, min 480px** (H+V scroll) · Inspector **360px** |
| Sub-header toolbar | **44px** · Linked-run strip **48px** (VIEW only) · Console drawer handle **36px** / expanded **240px** (default collapsed) |
| Tool node | **W 208px**, header row ~44px, +22px per port row; radius **12px**; 3px left-rail status tint |
| Gate node | W 208px, min-H **96px** (3 checkpoint chips + lock) · Ingest band **W 160px**, `--surface-3`, dashed |
| Port dot | **6–7px** dia, ~16px hit target; **reference = hollow ring**; label mono ~11px |
| Column pitch | **300px**; spine **y=200** · reference rail below the spine |
| Edge | orthogonal elbow, **1.5px `--border-strong`**; reference **1px dashed `#8b95a1`**; advisory **1.5px dashed `--accent`** |
| Canvas | `--surface-2` bg + 1px dot grid `#dbe1e8` at **20px** pitch (= snap grid) |

**Glyphs (one glyph, one referent):** `git-branch` = nav item. demux `split` · read_qc
`scissors` · align `git-merge` · markdup `copy` · coverage `bar-chart-2` · variant_call
`dna` · filter `funnel` · qc_aggregate `layers`. Gate `shield-check` (+ `lock`). Agents:
qc_triage `activity` · pipeline_repair `wrench` · archivist `archive`.

### Anchor scenario the prototype renders (`giab_panel`, HG002)
Seven wired tool nodes `fastp → bwa-mem2 → samtools markdup → {mosdepth, bcftools call →
bcftools norm} → MultiQC`, three reference nodes (genome / panel BED / truth VCF), the
QC-triage agent on the gate's `qc` checkpoint, the ingest band, and the terminal gate.
(In `giab_panel` the sample sheet is hand-authored, so **demux is omitted** — FASTQ enters
as a locator-resolved source at fastp — and it slices a pre-aligned **bam**, not
`recal_cram`.) **Linked to `RUN-2026-07-07-A`**: nodes flip to real `ok/warn/blocked`
(`mosdepth` reads `warn` — depth/callability borderline for S5), I/O fills with real
hashes, and the gate shows `proceed 3 · hold 1 · escalate 1`. The full node/param/locator
table is in `pipeline-builder-brief.md` (§ Anchor scenario).

---

## Phasing

**MVP (this prototype)** — one editor screen; the germline chain **pre-laid-out** that you
**configure / re-point / toggle** (not free composition); the inspector's locator editor +
schema-driven params form (bundled schema); **static typed validation only**; **Emit
`run_layout.yaml`** across three profiles; the QC-triage agent rendered + serialized (not
executed); the terminal gate reached via the ingest band; linked-run **VIEW as read-only
link-out**; all states off the real query layer. **MVP verbs are Validate + Emit only.**

**Phase 2+ (design the seam, don't build now)** — free composition (drag arbitrary nodes,
free edge-drawing), auto-layout/Tidy, pan/zoom-as-authoring, minimap; **Dry-run** (locator
resolution vs a real run dir); the config **loader + `PIPEGUARD_RUN_LAYOUT` selector** so
the running system consumes an emitted layout; **in-app Run** as a hand-off to
Nextflow/bioconda; round-trip import; live `nextflow_schema.json` fetch;
**Pipeline-repair** & **Archivist** agents; RNA-seq modality; RBAC + no-code form mode.

**Hard out-of-scope — invariants the builder must never cross.** Nothing composed may
set/override/restate/route a verdict/confidence (agents have no ports); no agent on the
critical path; a run reaches the verdict **only through `run_gate`** (never a side path
that skips provenance); the config **locates, never judges** (no path triggers execution);
**origin never relabels up** (guarded values stamped at ingest, never authored); reuse the
existing event vocabulary (invent no new event type; no agent writes the authoritative
ledger); **no confidence meter**; no clinical/diagnostic claims.

---

## Files in this bundle

- `README.md` — this document (self-sufficient; implement from this alone).
- `PipeGuard.html` — self-contained clickable prototype. **Open in a browser → Configure →
  Pipeline builder.**
- `source/PipeGuard.dc.html` — annotated source; the logic class holds the builder's mock
  data and the emitted-YAML strings.
- `source/support.js` — prototype runtime (reference only; do not port).
- `pipeline-builder-brief.md` — the authoritative product spec (full rationale + phasing).
- `operator-ui-handoff-README.md` — the operator UI this screen extends (shell, tokens,
  primitives to reuse).
