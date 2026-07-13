# Handoff: bayleaf Pipeline Builder (wishlist #11) → design tool

> *Design handoff for wishlist #11, produced by a multi-perspective design workflow and
> fact-checked against the repo's architecture + the operator-UI handoff. Paste-and-go:
> hand this to the design tool. It extends [`README.md`](README.md) — reuse its shell,
> tokens, and primitives verbatim.*


## Overview

The Pipeline Builder is the **editable face of the operations layer**: a node-graph editor where an operator composes a germline-panel pipeline from typed tool nodes, snaps in bayleaf's advisory QC-triage agent, and — as the machine-readable output — **emits the run-layout config bayleaf reads to locate a run's artifacts** (the artifact-kind → path/glob map, `run_layout.yaml`). It is the hackathon's "pipeline translator" idea made visual, and it is the **editable superset of the read-only Provenance canvas (#10)**: the same horizontal left→right stage DAG and the same click-to-open per-node I/O drawer, plus authoring affordances on top.

This document is the design target for one new screen (`view: 'builder'`). It extends — and must stay visually continuous with — [`docs/design/frontend/README.md`](README.md) (the operator-UI handoff). **Reuse that handoff's app shell, tokens, and primitives verbatim.** Only the surfaces below are net-new.

Three boundaries are load-bearing and must read as *visible UI guarantees*, not just prose:

1. **The builder composes and configures; it does not execute.** No control in this view runs a tool. Compute portability is delegated to Nextflow (ADR-0003); the primary action is **Emit config**, never "Run."
2. **The deterministic gate still decides.** Nothing a user composes, and no agent they snap in, can set, override, restate, or *route* a verdict. If a composed capability needs to *decide*, it is a **rule**, not a builder feature.
3. **Agents are advisory and off the critical path.** They attach *after* the decision (they observe the gate's decision-card output), never inside it, and they can never drop, delay, or alter a verdict.

> **Not a clinical decision system.** Research/demo tool with production intent — no diagnostic, therapeutic, or safety claims. Thresholds are illustrative/configurable, not clinical. There is **no confidence meter** anywhere (carried from the operator UI; confidence is deliberately omitted until grounded).

---

## How this extends the operator UI (read this first)

The builder does not invent a visual paradigm. It is the read-only Provenance canvas with authoring affordances bolted onto the **same** node card + I/O-drawer treatment. Two things change from Provenance and both are called out below: (1) the builder screen breaks the shell's max-width cap because a node editor is wide, and (2) before a run exists, nodes are in a neutral `draft` state with no pass/warn/fail color.

**One canonical topology.** The builder ships its own **8-stage germline chain + gate** (below). It does **not** literally reuse the coarser 6-node Provenance `STAGES` array (`intake → demux → QC → align → variant-call → gate`) — that is a summary view of a run, and seeding from it would produce the wrong graph. The builder carries its own default template with seeded coordinates (see Design-system hints). When the builder binds to a real run (linked VIEW), it renders *this* 8-stage topology populated from the ledger projection.

Canonical stage chain (left → right):

```
demux → read_qc(trim) → align → markdup → coverage → variant_call(call) → filter → qc_aggregate
        └────────────────────── composed tool nodes ──────────────────────┘
                                                          │ (metric-bearing outputs located by config)
                                                          ▼
                                            [ deterministic ingest · write_run_dir → run/ (5 CSVs) ]
                                                          ▼
                                                       [ GATE ]  ← terminal, singular, non-removable
```

---

## Product model (the builder's own vocabulary)

### Reused verbatim from the operator UI

1. **Verdicts** (per sample): `proceed` / `hold` / `rerun` / `escalate`, with their exact 4-shade semantics. `rerun` = operational failure only; `hold` = borderline data quality. Shown only on the terminal gate node in linked VIEW.
2. **Gates** (three, in sequence): `preflight` (`#1f6feb`) · `qc` (`#1f5fd0`) · `variant` (`#0e8f7e`). In the builder these are **three checkpoint facets of one terminal gate node**, not separate nodes (see gate representation below).
3. **Primitives:** verdict badge, gate-grouped evidence table, GateResult strip, status chips (`ok`/`warn`/`blocked`), **origin tags** (`real-giab`/`synthetic`/`contrived`/`unknown`), citations. **No confidence meter.**

### New to the builder

1. **Tool node** — one genomics stage (fastp, bwa, mosdepth, bcftools, MultiQC, …) as a card with typed artifact-kind I/O ports, params, tool + version, a `bayleafStatus` badge, and — the load-bearing part — a **run-layout locator per output port** describing where that artifact-kind lands on disk.
2. **Typed edge** — a data flow. An output port of kind X connects only to an input port of kind X. No coercion.
3. **Agent node** — an advisory snap-in (QC-triage MVP). Structurally different from a tool node: **it has no data ports**, so it can never sit on a data path to the gate.
4. **Gate node** — the terminal, singular, non-removable sink that owns the three checkpoints. It has no editable verdict/threshold field and **no incoming data edge from tool outputs** — it reads the frozen five `run/` CSVs (see the ingest boundary).
5. **Ingest boundary** — a fixed, non-composable system element between the pipeline and the gate, captioned `deterministic ingest · write_run_dir → run/ (5 CSVs)`. It is *why* composition can't move the verdict: tool outputs are only *located* by the config, then flattened deterministically into the frozen five CSVs the gate reads.
6. **The deliverable** — a typed, profiled `run_layout.yaml` (artifact-kind → path/glob map). This is the **sole emitted, grounded artifact**. The graph itself is non-authoritative draft state.

---

## Primary user

1. **Primary — the pipeline operator who wires a run.** Same persona as the operator UI: technical, time-pressured, thinks in artifacts, tools, and file layouts. They come to *declare where a run's outputs live* (author/adjust the run-layout config), sanity-check that a pipeline's typed I/O connects end-to-end, and snap in QC-triage before hand-off. They want the graph to tell them "what's unconfigured / what won't connect" in seconds — the same attention-first posture as Decision cards.
2. **Secondary — the bench scientist who wants no terminal** (the no-code intent behind wishlist #9). They don't hand-edit YAML. The Node inspector is therefore a **schema-driven form** (from a bundled `nextflow_schema.json`), never a code editor.

---

## Design principles — invariants rendered as UI

The doctrine (rules-decide / agents-advise / no-confidence-meter) is already settled by ADR-0001 and the operator handoff. Here it compresses to a table of how each invariant is *rendered*, so a design tool builds it as structure, not as a caption to be read and forgotten.

| Invariant | Rendered as UI |
|---|---|
| **Rules decide; the graph never does** | The gate node exposes no threshold/verdict controls; its inspector is threshold-read-only and links out to Settings → runbook. |
| **The gate is the sole, terminal, non-removable authority** | One gate node pinned rightmost; delete/duplicate are refused by the *editor* (not just the validator); a lock glyph marks it. |
| **The gate reads flattened CSVs, not raw tool outputs** | A fixed **ingest band** sits between the pipeline and the gate; no tool output edges directly into the gate. |
| **Agents are advisory + off the critical path** | Agent nodes are side-attached dashed pills with **zero data ports** — you *cannot draw* an agent→gate edge because the port does not exist. |
| **Compose ≠ execute** | Primary action is **Emit**, not "Run"; no control triggers a tool; a resolved path becomes a ledger event only later, when the gate runs through `run_gate`. |
| **Origin is non-launderable** | Every emitted locator's `origin` is `unknown` at emit time; guarded values are disabled in the picker with a tooltip. |
| **No confidence meter** | Absent by construction, everywhere. |

Two functional-design principles carry over unchanged: **states are first-class** (every region has explicit loading / empty / error / draft / linked treatments wired to the real query layer), and **rule-derived data survives AI failure** (if an agent errors it degrades to its stub; the graph, validation, and emit are unaffected).

---

## Core views

The builder is **one screen** (`view: 'builder'`) composed of regions, not several routes. It inherits the shell wholesale — **236px dark left nav** (`#141a21`) + **56px top bar** + light content (`#eef1f4`) — with one documented exception.

**Nav placement (committed):** add one item, **"Pipeline builder"** (`view: 'builder'`, glyph `git-branch`), in the **Configure** group, **above Settings**. The read-only Provenance canvas stays in Analyze; its editable sibling lives in Configure. Cross-link both ways: an **"Edit this pipeline"** affordance on Provenance opens the builder; the builder's linked-run strip deep-links back to Provenance + Decision cards.

**The shell exception (committed):** the builder screen is a **full-content-width three-pane workspace and the canvas scrolls horizontally** — it does **not** honor the 720–1080px cap that every other view uses. This is the single most consequential layout decision; it is settled here. (The standalone read-only Provenance page #10 remains 1080-capped as its own view; the builder's *linked-run VIEW* is this same full-width workspace showing run data, not the Provenance page.)

### Region 0 — the workspace frame

1. **Sub-header toolbar (44px)**, below the 56px top bar: a **VIEW | EDIT** segmented toggle (left), the **profile switcher** (`default` / `giab_panel` / `sarek`), and the action cluster **Tidy · Validate · Emit** (right). This is where VIEW|EDIT and the verbs live — the top bar is already full (back / title / run-switcher / search / bell) and gains nothing new.
2. **Linked-run strip (48px)**, below the toolbar, **only in VIEW/linked** — the run's segmented verdict bar + deep-links.
3. **Three panes** filling the content area: **Palette (240px, collapsible to a 44px rail)** · **Canvas (flex, min 480px, horizontal + vertical scroll)** · **Node inspector (360px, appears on selection, otherwise hidden)**.
4. **Validate/Emit console** — a dockable bottom drawer spanning the canvas: collapsed handle **36px**, expanded **240px**, **default collapsed**.

### (a) The Canvas — the node-graph editor · MVP

1. **Purpose.** Compose and inspect the pipeline as a left→right DAG. This is the spine every other region hangs off.
2. **What ships (deliberately narrow MVP).** The germline-panel default chain ships **pre-laid-out** from a bundled template (seeded coordinates given below). The operator **selects nodes, edits params/locators, re-points the fixed stage inputs, and toggles the QC-triage agent + gate on/off.** It is a **configure-a-known-pipeline** experience — **not** free composition. Drag-arbitrary-node-from-palette, free edge-drawing, and auto-layout are Phase 2.
3. **Node treatment (extends the Provenance stage/node card).** Each node is a 208px card (radius 12px, shadow `0 1px 2px rgba(16,24,40,.05)`, 3px left-rail status tint) showing: (i) tool name (Plex Sans) + version (Plex Mono, e.g. `fastp 0.23.4`); (ii) typed I/O ports on left (in) / right (out); (iii) a `bayleafStatus` badge (see below); (iv) a status dot.
4. **`bayleafStatus` badge.** Whether bayleaf **runs** the stage (`ours` — read_qc, coverage), **consumes** its artifacts (`full` — demux, markdup, annotate, qc_aggregate), or provides a **demo substitute** (`partial` — align slice, bcftools caller, region-subset filter). Field values are `ours | full | partial`; the badge *labels* render `ours` / `consumes` / `substitute` for operator legibility.
5. **Draft status (the one semantic shift from Provenance).** In the editor, before anything runs, tool nodes are in a single neutral state — label **`draft`**, background `--surface-3 #e6eaef`, dashed border `--border-strong #d2d9e0`, text `--text-3 #8b95a1`. **No verdict/quality color, because nothing executed.** The Provenance `ok / warn / blocked` coloring only lights up in linked VIEW (region e). The gate's draft state is labelled **`pending — no verdict`**.
6. **The gate node.** A distinct **non-deletable, non-duplicable** terminal node at the right end, min-height 96px, carrying three stacked checkpoint chips (preflight `#1f6feb` · qc `#1f5fd0` · variant `#0e8f7e`) and a **lock glyph**. It exposes **no data ports fed by tool edges** and **no threshold/verdict control**. It sits *after* the ingest band. Selecting it opens a threshold-read-only inspector linking to Settings → runbook.
7. **The ingest band.** A slim, greyed, non-composable system element (`--surface-3`, dashed border) between the last tool column and the gate, captioned `deterministic ingest · write_run_dir → run/ (5 CSVs)`. Metric-bearing tool outputs (`fastp_json`, `mosdepth_summary`, `vcf`/`filtered_vcf`, `ngscheckmate`) draw a thin neutral "located-by-config" connector *into* the band; the band draws one connector into the gate. This makes G1 legible: **no composition choice rewires what the gate reads.**
8. **Agent nodes.** Rendered **side-attached** as dashed advisory pills above the spine (details in the node & agent model), connected by a dashed advisory line to the node they observe — never inline in the flow.
9. **Canvas background & guides.** Background `--surface-2 #eef1f4` with a 1px dot grid (`#d9dfe6`, 20px pitch = the snap grid). Faint per-column lane guides (1px dashed `#e4e8ed`) appear **only during a node drag**. No minimap in MVP.
10. **States.** loading (shimmer node skeletons along the spine, ~1.3s), empty ("No pipeline yet — seed from the germline-panel template" dashed CTA), error (template/schema failed to load → Retry, template still offered), ready (the DAG).

### (b) The Palette / library · MVP

1. **Layout.** Left rail (240px, collapsible), sectioned with the shell's eyebrow labels (~10.5px uppercase), each node a compact draggable tile (icon tile radius 9–12px). Search box at top reuses the shell affordance.
2. **Sections.** (i) **Tool nodes, grouped by stage** — Demultiplex (BCL Convert) · Read QC + trim (fastp / FastQC) · Alignment (bwa-mem2 / DRAGMAP) · Duplicate marking (MarkDuplicates / samtools markdup) · Coverage (mosdepth / Picard **CollectHsMetrics** — panel-preferred) · Variant calling (DeepVariant / HaplotypeCaller / **bcftools-demo**) · Filter/normalize (bcftools norm/filter) · Annotation (VEP / snpEff — context only) · QC aggregation (MultiQC). Each tile shows the tool name + the artifact-kinds it emits. (iii) **Contamination** (NGSCheckMate + sex-vs-coverage) is a panel-optional tool tile. (iv) **Agent nodes** — **QC-triage (#1, MVP)**; greyed "planned" tiles for **Pipeline-repair (#2, requires trace capture)** and **Archivist (#3, spec-only)**, not draggable. (v) **The gate node** — a single pinned tile; dragging it is a no-op if one already exists.
3. **MVP note.** In the narrow MVP the palette is present but authoring is confined to configuring/toggling the pre-seeded chain; unrestricted palette-drag-to-canvas is Phase 2.

### (c) The Node inspector · MVP (the load-bearing config surface)

1. **Layout.** Right rail (360px), appears on select, fade-rise ~.28s. Header: icon tile + tool name + version (mono). Tabs: **Params · Locators · I/O · Agents**.
2. **Params.** A **schema-driven form generated from the tool's bundled `nextflow_schema.json`** (the same auto-generated-config-form pattern the runbook profiles use): typed inputs with label, help text, default, units. Required fields validate inline (missing → field-level amber marker, never a blocking modal). **Never a raw code editor. Schema is bundled/pinned — no live network fetch** (offline-first).
3. **Locators (the deliverable's per-node source).** For each output kind, the editable locator fields the config emits: **`path | glob`** (mono), **`parser`** (dispatch key; `null` = pointer-only, never opened), **`required`**, **`role: output | reference`**, **`on_multiple: first | all | error`**, **`origin`**. This panel *is* the artifact-kind → path map for one node.
4. **I/O.** Mirrors the read-only provenance drawer: rows of `name · sha256 · size · origin` (mono). In a draft the hash/size/origin cells are `—` placeholders (declared ports, no bytes yet); in linked VIEW they fill from the ledger.
5. **Agents.** Toggle the QC-triage snap-in for this node's checkpoint; `stub | claude` state (default `stub`, OFF, $0).
6. **Guardrails surfaced here.** (i) The mapping **locates inputs, never judges them** — a caption states repointing a path changes inputs, not thresholds. (ii) **Origin is not relabelable:** the `origin` picker disables the guarded values (`real-giab`/`synthetic`/`contrived`) with a tooltip — *"Config locates inputs; it cannot relabel provenance. Origin is stamped at ingest from the run's marker."* It stays `unknown` in the editor. (iii) The gate node's inspector is threshold-read-only.
7. **States.** unconfigured (required fields empty → amber markers), configured, error (schema unavailable → still show the Locators panel so paths can be hand-authored).

### (d) The Validate + emit console · MVP

1. **Purpose.** Check the composition is well-typed and complete (statically, zero filesystem I/O), then produce the `run_layout.yaml`.
2. **Validation list** — grouped most-severe-first (reuse finding-severity `critical #cf3238 · warn #c1560f · info #1f6feb`). MVP checks are **all static** (see the validation rules): typed-port mismatches (in practice prevented at connect-time), missing required config, gate-reachability (are the metric-bearing artifacts the ingest needs produced?), DAG/cycle, agent-off-path, locator well-formedness, origin=unknown. Each row is click-to-focus → selects the offending node and opens its inspector. Copy is declarative ("expects/received"), never prescriptive, e.g. `mosdepth_summary required — no locator defined`.
3. **Config preview** — a live, read-only **`run_layout.yaml` preview** (mono) with the **profile switcher** (`default` / `giab_panel` / `sarek`). Actions: **Copy** and **Download**. The `BAYLEAF_RUN_LAYOUT` env value is shown as a mono hint.
4. **The primary action of the whole builder: `Emit config`** — not "Run." Emit writes/exports the config only; it triggers no execution. Copy states: schema is design-now; the running system's *consumption* of an arbitrary emitted layout (the loader + selector) is Phase 2, so the live gate does not yet auto-consume this file.
5. **States.** clean (green "Typed I/O connects · config ready to emit"), issues (the list), empty (nothing composed yet).

### (e) The linked-run VIEW / hand-off strip · MVP = link-out

1. **Purpose.** Connect a composed pipeline to a *real* run and its provenance/decision cards — without pretending the builder runs anything.
2. **No linked run (MVP default / EDIT mode).** A neutral strip: *"This composition emits a config. Compute runs in Nextflow."* Emitting offers **Copy config** / **Download**. No in-app execution in MVP.
3. **Linked run present (VIEW mode).** The strip shows the run's **segmented verdict bar** + counts and **deep-links: "Open Provenance"** and **"Open Decision cards."** This is where the canvas node status dots light up draft → real `ok/warn/blocked` from the ledger projection, the I/O drawers fill with real `name · sha256 · size · origin`, and the gate node shows the run's verdict summary. **Authoring is locked** here; a **"Fork to new draft"** action clones the layout back into an editable draft (the only VIEW→EDIT bridge; it never mutates the run).
4. **Provenance obligation (made legible).** When a run executes against the emitted layout, every resolved absolute path is recorded as a provenance-ledger event, and the gate ingests **through** the config — but the verdict is still a pure function of parsed values through rules + runbook. The strip should make the causal chain obvious: *builder emits config → Nextflow runs → deterministic ingest writes run/ (5 CSVs) → `run_gate` gates + records the ledger trail → decision cards.*
5. **Run is a Phase-2 hand-off stub, not an MVP verb.** When the job-runner port (wishlist, ADR-0003) exists, the strip gains a "Run" affordance that hands the emitted config to Nextflow/bioconda; the builder never reimplements an engine/scheduler. Copy: *"Run executes in Nextflow. bayleaf reads the results and gates them."*
6. **States.** unlinked (MVP default), linking (spinner ~1s), linked (the strip + colored canvas), error (run/ledger unreachable → Retry; rule-derived cards still linkable).

---

## The node & agent model

This is the conceptual heart: the typed node/edge model, how agents attach without touching the verdict, and how the graph serializes to the config. The type system is shaped so violating the four invariants is *unrepresentable*, not merely validated against.

### Node kinds

Three kinds only: `tool`, `agent`, `gate`. Data flows (`edges`) connect **tool→tool** and **tool→(ingest)→gate**. Agents are never nodes on a data edge.

### The typed port + embedded locator (the config seam)

Ports are typed by the artifact-kind vocabulary (the same controlled set as `ArtifactRef.kind`), extended with first-class `bam`/`bai` (the giab_panel path slices a pre-aligned BAM with `samtools view -M -L`) and the disjoint reference kinds:

```ts
type ArtifactKind =
  | 'fastq'
  | 'bam' | 'bai'                 // first-class: giab_panel slices a pre-aligned BAM
  | 'recal_cram' | 'recal_table' // sarek/default profile shape (do NOT coerce bam<->recal_cram)
  | 'mosdepth_summary' | 'fastp_json' | 'markdup_metrics' | 'samtools_stats'
  | 'vcf' | 'gvcf' | 'filtered_vcf' | 'joint_vcf' | 'ngscheckmate'
  | 'multiqc_json' | 'versions_yml' | 'params_json' | 'execution_trace';

type ReferenceKind = 'reference_fasta' | 'panel_bed' | 'truth_vcf'; // role:'reference', never gated
```

Every output port carries the locator that maps its kind to a `path`/`glob`. **Wiring a tool-node's output port to an output-folder *is* writing an artifact-kind → path locator** — that is why serialization (below) is nearly mechanical.

### Typed edges

A connection is a typed data flow: an *output* port of kind X connects to an *input* port of kind X. **No coercion** (`bam → vcf` is not a legal edge; a caller node between them is required). Because incompatible connections are refused at draw time (they spring back — no edge is created), **an edge never carries an "invalid" state**; there is no persisted red-dashed error edge and no `Edge.valid` field.

### The agent snap-in (advisory, off-path)

1. **Structurally port-less.** An `AgentNode` has **no `outputs` / data ports**. It therefore cannot be the `from` of any edge, which makes "an agent on the path to the gate" *unrepresentable*. This is the structural enforcement of "off the critical path" — not a lint rule.
2. **It attaches to what it OBSERVES.** `attachTo` names the host node it reads; `scope` names the checkpoint. An agent attached to the gate observes the gate's **emitted decision card (output), never an input** — the advisory connector originates from the gate's *output* boundary, so a mockup can never render the pill on the gate's input edge as though it were feeding the decision.
3. **What it may read:** the per-tool output tree, decision cards (the gate's output, after the fact), and the read-side `Repository.list_*(filters)` projection — **never** the authoritative ledger. **What it must not do:** set/change/restate/influence a verdict/finding/confidence; sit on the critical path; mutate the ledger or source records; fabricate/re-derive QC numbers; be required for a run to complete. Least-privilege: only de-identified aggregates enter any prompt.
4. **OFF by default.** `mode` defaults to `stub` ($0, nothing leaves the machine); `BAYLEAF_<AGENT>_AGENT=stub|claude` flips it. Any error (including a safety refusal) degrades to the stub. Toggling to `claude` never changes graph validity or the verdict.
5. **Roster (fixed).** `qc_triage` (#1, DONE, sonnet-mid) is MVP. `pipeline_repair` (#2, blocked on `execution_trace` capture — the agent most relevant to a builder, but it only *proposes* remediation, never auto-applies/re-runs/gates) and `archivist` (#3, spec-only) are greyed palette items. A new agent must pass the agents.md intake checklist before it can exist.
6. **Visual treatment.** A rounded pill (chip radius 20px, height 28px), dashed 1.5px `--accent #1f5fd0` border, `--accent-weak #eaf0fc` fill, an "ADVISORY" eyebrow (~10.5px uppercase), a `stub | claude` state dot, side-attached above the spine, connected by a **dashed** advisory line (no port glyphs). No confidence meter.

### The gate node + the ingest boundary

The three checkpoints (`preflight` / `qc` / `variant`) are **facets of one terminal gate node**, not three separate stage overlays. (The "overlay on demux/coverage/varcall" treatment is the read-only #10 convention; in the builder, the gate is one node carrying three checkpoint chips.)

Structural consequences — each is a validation rule:

1. **You cannot compose it away.** `singular:true` + `removable:false` (editor refuses delete/duplicate) ⇒ every valid graph terminates in exactly one gate.
2. **You cannot feed it a raw tool edge.** The gate has **no incoming `DataEdge` from tool outputs**. Tool outputs are *located* by the config; a **deterministic ingest (`write_run_dir`) flattens the located artifacts into the frozen five `run/` CSVs**; the gate reads *those* (`gate.reads = [samplesheet.csv, reads.csv, coverage.csv, variants.csv, pipeline.csv]`). This indirection is exactly why "composing which artifacts reach the gate" cannot move the verdict.
3. **You cannot route the verdict through anything.** The verdict is not a data kind, so no edge can originate from the gate; nothing "post-processes" it.
4. **You cannot inject a decision.** There is no verdict-kind or agent-kind input port, so no composition can inject a pre-made verdict. `aggregate_verdict()` is the only writer.

**Visual treatment:** terminal node, tinted by the resulting verdict 4-shade in linked VIEW (neutral `pending` in draft), carrying the verdict badge and a **lock** glyph. `rerun` (operational) vs `hold` (data-quality) keep their distinct copy/iconography.

### Graph → config serialization

The graph is **non-authoritative authoring state**. Its **sole emitted, grounded deliverable is `run_layout.yaml`** (the artifact-kind → path map). There is **no second committed/versioned/content-hashed "pipeline definition" artifact** — that would be a workflow-definition authority bayleaf does not own (Nextflow's job). Persist the graph for reload if you like (a draft/session blob), but not as a durable bayleaf-owned contract.

Derivation (graph element → config element):

| Graph element | Emits into `RunLayoutConfig.locators` |
|---|---|
| A tool output port, kind K, `role:'output'` | `locators[K] = port.locator` (appended if `cardinality:'many'`) |
| A `reference` output, kind K, `role:'reference'` | `locators[K] = { …, role:'reference' }` — located, never gated |
| A port with `parser:null` | pointer-only entry — recorded, never opened |
| `on_multiple` on a globbed port | carried verbatim; `'error'` refuses ambiguity at ingest |
| `origin` on a port | carried as declarative annotation only — **always `unknown` at emit** |
| edges / agents / gate | **not** in the config — the config *locates inputs, never judges them* |

**Emission is compose-time; execution is not.** Writing `run_layout.yaml` triggers nothing. When a run is actually gated it must go through `run_gate` so the append-only trail (`analysis_run.started → sample.registered → finding.emitted → verdict.decided → analysis_run.completed`) is emitted and each resolved path is recorded. **Do not** produce a verdict by a side path that skips the ledger, and **do not** inject a file-backed `EventLedger` into the `@lru_cache`'d `_evaluate` path (it re-appends the whole trail per cache-miss and corrupts the append-only ledger). Reuse the existing event vocabulary (`metric.parsed`, `artifact.ingested`) — invent no new event type.

### Validation — invalid graphs cannot emit (all MVP checks are static, zero I/O)

Emission is total only over a validated graph. On any `severity:'error'`, `validate` returns the errors and **nothing is written** — no partial YAML, no ledger event.

1. **V1 — Typed-port compatibility.** Enforced at connect-time (incompatible drop springs back). The validator re-checks any existing edge: `edge.kind === from.kind === to.kind`, `from` is an output, `to` is an input. `code: V1_PORT_KIND_MISMATCH`.
2. **V2 — Required config satisfied.** Every `paramSchema`-required field set; every `required:true` input either connected by an edge or given a `locator` (locator *present* — not resolved against disk; disk resolution is Phase-2 Dry-run). `code: V2_MISSING_REQUIRED`.
3. **V3 — The gate is reachable via ingest.** The graph must **produce the metric-bearing artifact-kinds the ingest needs** (`fastp_json`, `mosdepth_summary`, `vcf`/`filtered_vcf`, optionally `ngscheckmate`) — i.e. some node's output locator supplies each required kind that flattens into the five CSVs. "Path to the gate" is a path to *ingest*, **not** a raw edge terminating at the gate. `role:'reference'` artifacts do not count. `code: V3_GATE_UNREACHABLE`.
4. **V4 — Gate is terminal, singular, non-removable.** Exactly one gate; `removable:false`; **no** incoming tool `DataEdge` and **no** outgoing edge. Delete/duplicate rejected by the editor. `code: V4_GATE_INVARIANT`.
5. **V5 — Agents strictly off the path.** No agent node has a data port; no edge originates from or targets an agent; every agent carries `advisoryOnly:true`; an agent may only *observe*. `code: V5_AGENT_ON_PATH`.
6. **V6 — Origin non-launderable.** Every emitted output/reference locator's `origin` is `unknown` at emit (compose ≠ execute; no per-run marker exists yet). No locator may set a guarded value. `code: V6_ORIGIN_LAUNDER`.
7. **V7 — Ambiguity flagged.** A globbed port with `on_multiple:'error'` is surfaced as an **info** note (static can't detect a multi-match; it *will* hard-error at ingest if ambiguous). `code: V7_AMBIGUOUS_GLOB`.
8. **V8 — DAG only.** No cycle. `code: V8_CYCLE`.
9. **V-loc — Locator well-formedness.** Exactly one of `path`/`glob`; `role:'reference'` ⇒ never wired to a gated input; `parser:null` ⇒ pointer-only. `code: VLOC_MALFORMED`.
10. **V10 — Emission all-or-nothing.** `emit` runs only on zero errors; on any error nothing is written. A `run_layout.yaml` on disk is therefore always the product of a fully valid graph. `code: V10_EMIT_BLOCKED`.

*(Deferred to Phase 2 with the loader: locator resolution against a real run dir, the "missing-input finding preview," and any check requiring filesystem I/O.)*

---

## Interactions & states

### Interactions (IDs stable — cite them)

1. **INT-1 — Select / configure a pre-seeded node (MVP core).** Click selects (2px `--accent` ring); the inspector opens (region c). Edit params (schema-driven form) and locators; re-point an input; toggle the gate/agent. This is the MVP's primary loop — *configure a known pipeline*, not free composition.
2. **INT-2 — Connect / re-point typed ports.** Press-drag from an output port; on drag-start, kind-compatible input ports lift to an accent glow, incompatible ones dim. Within ~16px of a compatible port the edge snaps and commits (fade-rise). **Release on an incompatible port springs the edge back — no edge is created** — and the target port flashes `#cf3238` with a mono toast `fastq → vcf — incompatible artifact-kind`. (There is no persisted invalid edge.)
3. **INT-3 — Inspector.** Reuses the #10 click-to-drill I/O drawer as a right-side inspector. Tabs Params · Locators · I/O · Agents. Deselect on blank-click or `Esc`.
4. **INT-4 — Edit params / locators.** Params = schema-driven form (inline field-level validation). Locators = one Appendix D §5 locator per kind. Origin picker disables guarded values with the PHI helper copy.
5. **INT-5 — Snap the QC-triage agent.** Drag the QC-triage pill onto a stage/gate; it docks as an advisory badge (no data port), `stub` by default. Attaching to the gate observes the decision-card output.
6. **INT-6 — Validate + Emit (the only MVP verbs).** **Validate** = static, typed, zero I/O (rules V1/V2/V3/V4/V5/V6/V8/V-loc). **Emit** = serialize the graph → `run_layout.yaml`, Copy/Download. **No Run, no Dry-run in MVP** (both are Phase 2 — see phasing).
7. **INT-7 — Pan / zoom (navigation, not authoring).** Space-drag / middle-drag to pan; scroll / `⌘-scroll` to zoom (~0.4×–2×); `F` fit, `⌘0` reset. (Auto-layout / "Tidy," free drag-authoring, and the minimap are Phase 2.)
8. **INT-8 — Bind a run (link-out).** Selecting a run in the top-bar run switcher binds `runId`, flips to VIEW, and colors the canvas from the ledger projection (ST-6). "Fork to new draft" clones back to an editable draft.

### States (first-class — each wired to a real fetch/query)

```
Empty ──seed template──▶ Draft ──Validate──▶ Valid draft ──Emit──▶ (file)
                            │
                    bind runId (link-out)
                            ▼
                   Linked-to-run VIEW (read-only)
```

1. **ST-1 — Empty.** Centered dashed drop target (radius 14px) + CTA "Seed from the germline-panel template." Palette/inspector muted until the first node lands.
2. **ST-2 — Loading.** Shimmer skeletons (~1.3s): ~6 palette rows, skeleton lanes on the canvas. Backed by the real template/tool-registry fetch; a failed fetch degrades to ST-4, not a frozen skeleton.
3. **ST-3 — Invalid graph.** The offending node gets a critical ring + `alert-triangle`; the validation console lists rule-derived, declarative messages; click a row → pan/select the element. Idempotent — re-validate clears resolved findings live.
4. **ST-4 — Emit error.** Non-destructive banner + Retry: `Couldn't write run_layout.yaml — disk/permission error. Your graph is unchanged.` The composed graph is never lost; the last-good serialized config is shown for manual copy. If an *agent* errors it degrades to its stub ("advisory unavailable") — the graph, validation, and emit are unaffected.
5. **ST-5 — Draft (composed-but-not-run).** Header badge `Draft — not run`. No `runId`, no provenance events. Tool nodes read `draft`; I/O cells are `—`; the gate reads `pending — no verdict`. Emit enabled; (Phase-2) Run enabled only if Validate passes.
6. **ST-6 — Linked-to-a-run (read-only VIEW).** Bound to a `runId` (top-bar run switcher pill). Node statuses flip to real `ok/warn/blocked`; I/O drawers fill with real `name · sha256 · size · origin`; the gate shows the actual verdict badge + three checkpoint tags. Authoring locked; "Fork to new draft" is the only bridge back.

### Builder state object (README-style, verbatim target)

```js
mode: 'edit',                 // 'view' | 'edit' (default 'view' when a runId is bound)
runId: null,                  // bound run for VIEW; null for a fresh draft
profile: 'giab_panel',        // 'default' | 'giab_panel' | 'sarek' | '/path/to/custom.yaml'
selectedNode: null,           // node id | null
selectedEdge: null,           // edge id | null
inspectorTab: 'params',       // 'params' | 'locators' | 'io' | 'agents'
paletteOpen: true,
drawerOpen: false,            // validate/emit console (default collapsed)
zoom: 1, pan: { x: 0, y: 0 },
dragging: null,               // { kind:'node'|'edge', … } | null
validation: [],               // GraphError[] (empty = clean)
dirty: false,                 // unsaved edits since last emit
```

---

## Data contract (one contract)

This is the single canonical contract. The graph is authoring state; **the verdict is never stored on it** — it is computed at run time by `run_gate`. The graph's *deliverable* is the `RunLayoutConfig`.

```ts
// ---- shared vocab ----
type ArtifactKind =
  | 'fastq' | 'bam' | 'bai' | 'recal_cram' | 'recal_table'
  | 'mosdepth_summary' | 'fastp_json' | 'markdup_metrics' | 'samtools_stats'
  | 'vcf' | 'gvcf' | 'filtered_vcf' | 'joint_vcf' | 'ngscheckmate'
  | 'multiqc_json' | 'versions_yml' | 'params_json' | 'execution_trace';
type ReferenceKind = 'reference_fasta' | 'panel_bed' | 'truth_vcf';

type OriginTag  = 'real-giab' | 'synthetic' | 'contrived' | 'unknown';
type StageKind  = 'demux' | 'read_qc' | 'align' | 'markdup'
                | 'coverage' | 'variant_call' | 'filter' | 'annotate' | 'qc_aggregate';
type PortRole   = 'output' | 'reference';        // 'reference' = never gated
type NodeStatus = 'ok' | 'warn' | 'blocked';     // linked-VIEW only
type RunStatus  = 'ours' | 'full' | 'partial';   // badge labels: ours / consumes / substitute

// ---- ports & typed dataflow ----
interface Port {
  id: string;                        // stable within node, e.g. 'out.vcf'
  kind: ArtifactKind | ReferenceKind;
  role: PortRole;
  direction: 'in' | 'out';
  required: boolean;
  cardinality: 'one' | 'many';
  locator?: LayoutLocator;           // on output ports — the machine-readable seam
  label?: string;
}

interface Edge {                     // typed dataflow ONLY; agents/gate-verdict are NOT edges
  id: string;
  from: { node: string; port: string };  // an output port
  to:   { node: string; port: string };  // an input port
  kind: ArtifactKind | ReferenceKind;     // === both ports' kind (incompatible edges can't be created)
}

// ---- the three node kinds ----
interface ToolNode {
  id: string;                        // 'n_fastp'
  type: 'tool';
  tool: string;                      // 'fastp'
  version: string;                   // '0.23.4' (pinned; surfaces in versions_yml)
  stage: StageKind;                  // 'read_qc'
  bayleafStatus: RunStatus;        // 'ours' | 'full' | 'partial'
  inputs: Port[];
  outputs: Port[];
  params: Record<string, string | number | boolean | object>;
  paramSchemaRef: string;            // bundled nextflow_schema.json id (no live fetch)
  status?: NodeStatus;               // linked-VIEW only; absent in draft
  ui: { x: number; y: number };      // canvas coords — non-load-bearing
}

interface AgentNode {
  id: string;                        // 'a_qc_triage'
  type: 'agent';
  agent: 'qc_triage' | 'pipeline_repair' | 'archivist';  // sanctioned roster only
  attachTo: string;                  // host node it OBSERVES (for the gate: its decision-card OUTPUT)
  scope?: 'preflight' | 'qc' | 'variant';
  advisoryOnly: true;                // literal — mirrors triage/models.py advisory:Literal[True]
  enabledBy: string;                 // 'BAYLEAF_TRIAGE_AGENT'
  mode: 'stub' | 'claude';           // default 'stub'
  tier?: string;                     // 'sonnet-mid'
  ui: { x: number; y: number };
  // structurally has NO ports, NO verdict/confidence/finding field — cannot decide
}

interface GateNode {
  id: string;                        // 'g_gate'
  type: 'gate';
  terminal: true;
  removable: false;
  singular: true;
  gates: ['preflight', 'qc', 'variant'];
  reads: string[];                   // the frozen five run/ CSVs — NOT raw tool outputs
  runbookProfile: string;            // 'research' | 'biotech-panel' (ADR-0005)
  emitsLedger: true;                 // run_gate: analysis_run.started -> … -> completed
  status?: NodeStatus;               // linked-VIEW only
  ui: { x: number; y: number };
  // NO ports; verdict is COMPUTED at run time, never persisted on the graph
}

// ---- the graph (non-authoritative authoring state) ----
interface PipelineGraph {
  id: string;                        // 'PIPE-2026-07-08-GERMLINE-PANEL'
  schemaVersion: 'builder/0.1';      // draft-format tag, NOT a durable bayleaf contract
  template?: string;                 // 'nf-core/sarek:germline-panel'
  runbookProfile: string;
  nodes: (ToolNode | AgentNode | GateNode)[];
  edges: Edge[];                     // typed dataflow only
  emits: { runLayoutProfile: string };
}

// ---- the EMITTED deliverable: artifact-kind -> path map (run_layout.yaml) ----
interface LayoutLocator {
  kind: ArtifactKind | ReferenceKind;
  path?: string;                     // exactly one of path | glob
  glob?: string;
  parser: string | null;             // dispatch key; null = pointer-only, never opened
  required: boolean;
  role: PortRole;                    // 'reference' = never gated
  onMultiple: 'first' | 'all' | 'error';
  origin: OriginTag;                 // ALWAYS 'unknown' at emit; stamped at ingest from the run marker
}
interface RunLayoutConfig {
  schemaVersion: 'run_layout/1';
  profile: 'default' | 'giab_panel' | 'sarek' | string;  // custom -> /path/to.yaml
  locators: Record<string, LayoutLocator>;               // selected via BAYLEAF_RUN_LAYOUT
}
```

---

## Design-system hints

### Reuse verbatim

1. **Shell:** 236px dark nav (`#141a21`) + 56px top bar + light content (`#eef1f4`); new `git-branch` nav item under **Configure**, above Settings.
2. **Type:** IBM Plex Sans (UI) + **IBM Plex Mono for every id, path, hash, version, kind, size**. Titles ~22/600; node headline ~13.5–16; port labels 11 mono; eyebrows ~10.5 uppercase.
3. **Palette / semantics:** the core light palette, verdict 4-shade, gate accents (preflight `#1f6feb` · qc `#1f5fd0` · variant `#0e8f7e`), finding severity (`critical #cf3238 · warn #c1560f · info #1f6feb`), origin tags — all exactly as in the operator handoff.
4. **Two color channels stay strictly separate:** status/verdict semantics (node left-rail tint, gate chips) vs artifact-kind. **Artifact-kind is NOT color-coded** (see below) — it is carried by the mono port label, so it can never be confused with the gate/severity channel.
5. **Primitives:** the stage/node card (the editable node), origin tags, status chips (`ok/warn/blocked` in linked VIEW), verdict badge (gate node, linked VIEW), the click-to-open I/O drawer, the schema-driven config form. Shape/elevation/motion tokens: chips 20px, buttons/inputs 8px, cards 11–14px, icon tiles 9–12px; card shadow `0 1px 2px rgba(16,24,40,.05)`; fade-rise ~.28s, shimmer ~1.3s, spinner ~1s.

### New builder tokens + the canvas measurement table

Artifact-kind is conveyed by the **mono port label**, not by color (this resolves the overload where kind-dots collided with the gate/severity tokens). Port dots and edges are neutral; `role:'reference'` is the one visual distinction, carried by a hollow ring.

| Element | Spec |
|---|---|
| Workspace | full content width (breaks the 720–1080 cap); Palette **240px** (collapse → 44px) · Canvas **flex, min 480px**, horizontal + vertical scroll · Inspector **360px** (on selection) |
| Sub-header toolbar | **44px** (VIEW\|EDIT toggle · profile switcher · Tidy·Validate·Emit) |
| Linked-run strip | **48px**, VIEW only |
| Validate/Emit drawer | handle **36px**; expanded **240px**; **default collapsed** |
| Node card | **W 208px**, min-H **76px**, header row 44px, **+22px per port row** beyond two on a side; radius **12px**; 3px left-rail status tint |
| Node icon tile | **28px**, radius 8px |
| Gate node | W 208px, min-H **96px** (three checkpoint chips + lock glyph) |
| Ingest band | slim system element W **160px**, `--surface-3`, dashed border, non-composable |
| Port dot | **6px** dia, **16px** hit target; row height **22px**; label mono **11px** |
| Reference port | **6px hollow ring** (1.5px stroke, transparent fill) — "never gated" |
| Column pitch | **300px** (208 node + 92 gap); spine **y=200** |
| Agent pill | side-attached **~96px above** host center; chip radius 20px, H 28px, dashed 1.5px `--accent`, fill `--accent-weak` |
| Reference rail | **y=372** (below the spine) |
| Edge | **orthogonal elbow**, stroke **1.5px `--border-strong #d2d9e0`**; hover/selected 2px `--accent #1f5fd0`; **no kind-color**. Kind label = mono pill shown on hover/selection |
| Reference edge | **1px dashed `--text-3 #8b95a1`** |
| Advisory connector | **1.5px dashed `--accent #1f5fd0`**, no port glyphs |
| Canvas background | `--surface-2 #eef1f4` + 1px dot grid `#d9dfe6` at **20px pitch** (= snap grid) |
| Lane guides | 1px dashed `#e4e8ed` per column, visible **only during a node drag** |
| Minimap | **cut for MVP** |

### Seeded coordinates for the default germline template

The default 8-stage chain + gate + QC-triage agent, spine at y=200 (columns pitched 300px). A static mockup can render this frame directly.

| Node | id | stage | x | y |
|---|---|---|---|---|
| Demultiplex | `n_demux` | demux | 40 | 200 |
| Read QC + trim | `n_fastp` | read_qc | 340 | 200 |
| Alignment | `n_bwa` | align | 640 | 200 |
| Duplicate marking | `n_markdup` | markdup | 940 | 200 |
| Coverage | `n_mosdepth` | coverage | 1240 | 200 |
| Variant calling | `n_call` | variant_call | 1540 | 200 |
| Filter / normalize | `n_norm` | filter | 1840 | 200 |
| QC aggregation | `n_multiqc` | qc_aggregate | 2140 | 200 |
| *(ingest band)* | — | — | 2420 | 200 |
| **Gate** | `g_gate` | gate | 2560 | 200 |
| QC-triage agent | `a_qc_triage` | — | 2560 | 104 |
| Reference: genome | `r_fasta` | reference | 640 | 372 |
| Reference: panel BED | `r_bed` | reference | 1240 | 372 |
| Reference: truth VCF | `r_truth` | reference | 2560 | 372 |

### Glyph assignments (de-collided — one glyph, one referent)

`git-branch` → **nav item only**. Stages: demux `split` · read_qc `scissors` · align `git-merge` · markdup `copy` · coverage `bar-chart-2` · variant_call `dna` · filter `funnel` · annotate `tag` · qc_aggregate `layers`. Gate `shield-check` (+ `lock` for non-removable). Agents: qc_triage `activity` · pipeline_repair `wrench` · archivist `archive`. Inspector params `sliders`.

---

## Anchor scenario

### Draft — `PIPE-2026-07-08-GERMLINE-PANEL` (profile `giab_panel`, HG002)

A composed germline-panel pipeline for HG002, seeded from `nf-core/sarek:germline-panel`. Seven wired tool nodes `fastq → … → filtered_vcf`, the QC-triage agent snapped on the gate's `qc` checkpoint, the terminal gate, and the `run_layout.yaml` it emits. (In the `giab_panel` realization the sample sheet is hand-authored, so **demux is omitted** — FASTQ enters as a locator-resolved source at `n_fastp`.) The `giab_panel` path slices a **pre-aligned BAM**, so it uses first-class `bam`/`bai`, not `recal_cram`.

**a. Tool nodes (left → right).**

| id | tool `version` | stage | status | inputs (kind) | outputs (kind → file) | key params |
|---|---|---|---|---|---|---|
| `n_fastp` | fastp `0.23.4` | read_qc | **ours** | `fastq` ×many (source) | `fastp_json → qc/HG002.fastp.json`; `fastq → HG002.R{1,2}.trim.fastq.gz` | `qualified_quality_phred:15`, `length_required:50`, `detect_adapter_for_pe:true` |
| `n_bwa` | bwa-mem2 `2.2.1` | align | **partial** | `fastq`, `reference_fasta`◦ | `bam(+bai) → align/HG002.bam` | `read_group:"@RG\tID:HG002\tSM:HG002\tPL:ILLUMINA\tLB:panel"`, `sort:coordinate` |
| `n_markdup` | samtools markdup `1.20` | markdup | **full** | `bam` | `bam → align/HG002.md.bam`; `markdup_metrics → qc/HG002.markdup.txt`; `samtools_stats → qc/HG002.stats` | `remove_duplicates:false` |
| `n_mosdepth` | mosdepth `0.3.8` | coverage | **ours** | `bam`, `panel_bed`◦ | `mosdepth_summary → mosdepth/HG002.panel.mosdepth.summary.txt` (+`thresholds.bed.gz` breadth `c[6]≥20X`,`c[7]≥30X`) | `by:panel.bed`, `thresholds:"1,10,20,30"`, `mapq:20`, `no_per_base:true` |
| `n_call` | bcftools mpileup/call `1.20` | variant_call | **partial** | `bam`, `reference_fasta`◦ | `vcf → variants/HG002.bcftools.vcf.gz(+.tbi)` | `mpileup:{min_MQ:20,min_BQ:20,max_depth:250}`, `call:{multiallelic:true,variants_only:true}` |
| `n_norm` | bcftools norm/filter `1.20` | filter | **partial** | `vcf`, `reference_fasta`◦, `panel_bed`◦ | `filtered_vcf → variants/HG002.norm.filtered.vcf.gz(+.tbi)` | `regions_file:panel.bed`, `norm:"-m -both"` |
| `n_multiqc` | MultiQC `1.21` | qc_aggregate | **full** | `fastp_json`,`markdup_metrics`,`samtools_stats`,`mosdepth_summary` | `multiqc_json → multiqc_data/multiqc_data.json` | `force:true` |

◦ = `role:'reference'` port (hollow ring, dashed reference edge, never gated).

**b. Typed edges (solid, neutral).**
1. `fastq`: `n_fastp.out.fastq → n_bwa.in.fastq`
2. `bam`: `n_bwa.out.bam → n_markdup.in.bam`
3. `bam`: `n_markdup.out.md_bam → n_mosdepth.in.bam`
4. `bam`: `n_markdup.out.md_bam → n_call.in.bam`
5. `vcf`: `n_call.out.vcf → n_norm.in.vcf`
6–9. `fastp_json` / `markdup_metrics` / `samtools_stats` / `mosdepth_summary` → `n_multiqc.in`
Reference edges (dashed `#8b95a1`): `reference_fasta → {n_bwa, n_call, n_norm}`; `panel_bed → {n_mosdepth, n_norm}`.
`n_fastp.in.fastq` has no upstream node (demux omitted) — it is a required input resolved by the `fastq` locator.
**Located-by-config → ingest → gate:** `fastp_json`, `mosdepth_summary`, `filtered_vcf` are located by the config into the ingest band → `write_run_dir` → the five `run/` CSVs → `g_gate`. **No tool node edges directly into the gate.**

**c. Agent snap-in.**
```json
{ "id": "a_qc_triage", "type": "agent", "agent": "qc_triage",
  "attachTo": "g_gate", "scope": "qc", "advisoryOnly": true,
  "enabledBy": "BAYLEAF_TRIAGE_AGENT", "mode": "stub", "tier": "sonnet-mid" }
```
A dashed advisory side-pill anchored above the gate. It observes the gate's **`qc` decision-card output** (never an input) and suggests likely-cause + next-action, cited. Off the critical path; `mode:'stub'` by default ($0); it has no ports and cannot connect to the verdict.

**d. Terminal gate node.**
```json
{ "id": "g_gate", "type": "gate", "terminal": true, "removable": false, "singular": true,
  "gates": ["preflight", "qc", "variant"],
  "reads": ["run/samplesheet.csv", "run/reads.csv", "run/coverage.csv",
            "run/variants.csv", "run/pipeline.csv"],
  "runbookProfile": "biotech-panel", "emitsLedger": true }
```
The gate reads the **frozen five flat `run/` CSVs** produced by deterministic ingest (`write_run_dir`) — *not* the raw tool outputs — so no composition choice can move the verdict. At run time `run_gate` emits `analysis_run.started → sample.registered → finding.emitted → verdict.decided → analysis_run.completed`.

**e. The emitted `run_layout.yaml` (the deliverable — every `origin` is `unknown`).**
```yaml
schema_version: run_layout/1
profile: giab_panel                 # BAYLEAF_RUN_LAYOUT=giab_panel
locators:
  # origin is 'unknown' for EVERY locator at emit time: compose != execute, no per-run
  # marker exists yet. Guarded origins (real-giab/synthetic/contrived) are stamped ONLY at
  # ingest from the run's origin marker — never authored here. Config cannot launder provenance.
  fastq:            { glob: "fastq/*_R{1,2}_001.fastq.gz",             parser: null,             required: true,  role: output,    on_multiple: all,   origin: unknown }
  fastp_json:       { path: "qc/HG002.fastp.json",                      parser: fastp_json,       required: true,  role: output,    on_multiple: error, origin: unknown }
  bam:              { glob: "align/*.md.bam",                           parser: null,             required: true,  role: output,    on_multiple: error, origin: unknown }
  markdup_metrics:  { path: "qc/HG002.markdup.txt",                     parser: markdup_metrics,  required: false, role: output,    on_multiple: error, origin: unknown }
  mosdepth_summary: { path: "mosdepth/HG002.panel.mosdepth.summary.txt", parser: mosdepth_summary, required: true, role: output,   on_multiple: error, origin: unknown }
  filtered_vcf:     { glob: "variants/*.norm.filtered.vcf.gz",          parser: vcf,              required: true,  role: output,    on_multiple: error, origin: unknown }
  multiqc_json:     { path: "multiqc_data/multiqc_data.json",           parser: null,             required: false, role: output,    on_multiple: error, origin: unknown }
  reference_fasta:  { path: "reference/GRCh38.fa",                       parser: null,             required: true,  role: reference, on_multiple: error, origin: unknown } # never gated
  panel_bed:        { path: "reference/panel.bed",                       parser: null,             required: true,  role: reference, on_multiple: error, origin: unknown } # never gated
  truth_vcf:        { path: "reference/HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz", parser: null,   required: false, role: reference, on_multiple: error, origin: unknown } # answer key, never gated
```

**f. What typed-validate catches (concrete).** Re-pointing `n_mosdepth.out (mosdepth_summary)` at `n_call.in (expects bam)` is refused at draw time — the edge springs back (no edge created), a mono toast reads `mosdepth_summary → bam — incompatible artifact-kind`. Dragging any connector *out of* `a_qc_triage` is impossible — the agent exposes no ports, so "nothing composed can set/route a verdict" is enforced by shape, not a lint rule. Deleting `g_gate` is refused by the editor (V4).

### Linked run — `RUN-2026-07-07-A` (the richest state, ST-6)

Bind the anchor graph to the operator UI's own demo run (5 samples: S1/S2/S3 proceed, S4 escalate@preflight index-swap, S5 hold@QC). In VIEW:

1. **Node status** flips from `draft` to real `ok/warn/blocked` from the ledger projection: for the escalated **S4**, upstream nodes read `blocked` (barcode i5 mismatch → probable S4/S5 index swap; QC/variant not evaluated); for the held **S5**, `n_mosdepth` (coverage) reads `warn` (mean depth 29.2× / callability 91.8% just under the saliva-adjusted gate).
2. **I/O drawers** fill with real `name · sha256 · size · origin` rows (origins now the run's *actual* guarded tags, stamped at ingest — e.g. `real-giab`).
3. **The gate node** carries the run's **segmented verdict bar** (proceed 3 · hold 1 · escalate 1) and its three checkpoint tags, and deep-links to Decision cards + Provenance.
4. **Authoring is locked**; "Fork to new draft" clones the layout back into an editable draft without mutating the run.

This exercises the states the draft alone never reaches (real node colors, real hashes, a verdict on the gate) and ties the builder to the operator UI's canonical anchor.

---

## Phasing

**Phase 1 — MVP: "a GUI that writes the file."** One editor screen; the germline-panel default chain **pre-laid-out** (seeded coordinates) that you **configure, re-point, and toggle** (not free composition); node inspector with the **run-layout locator editor** + a schema-driven params form from a **bundled** `nextflow_schema.json`; **static typed validation only (zero filesystem I/O)**; **Emit `run_layout.yaml`** across the three profiles (the sole grounded deliverable; schema is design-now at `src/bayleaf/layout/run_layout.yaml`); the **QC-triage agent** as an advisory side-pill (rendered + serialized, not executed); the terminal gate reached via the ingest band; **linked-run VIEW as read-only link-out** to Provenance + Decision cards; all states off the real query layer. **MVP verbs are Validate + Emit only.**

**Phase 2+ — design the seam, don't build now.** Free composition (drag arbitrary nodes, free edge-drawing, add/remove/reorder), **auto-layout/Tidy**, pan/zoom-as-authoring, and the minimap; **Dry-run** (locator resolution against a real run dir) — depends on the loader; the **config loader + `load_run` refactor + `BAYLEAF_RUN_LAYOUT` selector** (first `pydantic-settings` use in `src/`) so the running system consumes an emitted layout; **in-app Run** as a job-runner hand-off to Nextflow/bioconda (+ Slurm/cloud adapters + Terraform, all wishlist under ADR-0003 — the builder never reimplements an engine); **round-trip import** (reconstruct a graph from an existing `run_layout.yaml`) and **live `nextflow_schema.json` fetch** (need a command API + network; break offline-first); **Pipeline-repair (#2)** (blocked on `execution_trace` capture) and **Archivist (#3)** once each clears agent intake; the **RNA-seq modality (#7)** (additive stages/kinds — STAR/salmon `salmon_quant` — + a new port lane); **RBAC** (Viewer/Composer/Publisher), a #9 no-code **form mode**, and an **NL→structured-input** layer.

**Hard out-of-scope — invariants the builder must never cross.** Nothing composed may set/override/restate/route a verdict/confidence (agents have no ports); no agent on the critical path (a failure never drops/delays/alters a verdict; stub fully produces the output); a run reaches the verdict **only through `run_gate`** (never a side path that skips provenance); **never** inject a file-backed `EventLedger` into the `@lru_cache`'d `_evaluate`; the config **locates, never judges** (no path triggers tool execution); **origin never relabels up** (guarded values stamped at ingest, never authored); reuse existing event vocab (invent no new event type; no agent writes the authoritative ledger); no compute/engine/scheduler logic and no FastAPI/React imports in `src/bayleaf/`; **no confidence meter**; no clinical/diagnostic/therapeutic claims.

---

## Out-of-scope + reader footnote

The literal ticket id "T-032" does not appear in the repo. The run-layout config seam this spec relies on lives at **Appendix D §5** of `docs/design/data-platform-and-archivist.md` (lines 671–686) and is confirmed by the D7/D8 decision (line 71). The gate's three checkpoints and the read-only stage DAG come from the frontend README §5 (Provenance canvas), which #11 extends. Structural enforcements referenced: `advisory:Literal[True]` (`src/bayleaf/triage/models.py`), `aggregate_verdict` as the sole verdict writer (`src/bayleaf/synthesis/base.py`), the five gate-ingested CSVs (`parsers.py:187-217`), the append-only trail (`engine.py` / `provenance.py`, ADR-0002).

---

## Open questions for the maintainer

1. Canvas width: the builder editor is committed as a FULL-content-width, horizontally-scrolling three-pane workspace (the one shell exception to the 720–1080 cap); the standalone read-only Provenance page #10 stays 1080-capped. Confirm the builder may be that exception.
2. Nav placement: committed to Configure (above Settings). Confirm vs the defensible alternative of Operate (next to Intake) — only the group label would move.
3. Default topology vs Provenance STAGES: the builder ships its own 8-stage germline chain (+ gate) rather than reusing the coarse 6-node Provenance STAGES array, and the linked VIEW renders this 8-stage topology from the ledger. Confirm we do NOT need STAGES extended to match (i.e. the two views can legitimately differ in granularity).
4. Ingest band: confirm the explicit non-composable "deterministic ingest · write_run_dir → run/ (5 CSVs)" band between the pipeline and the gate is the right way to render G1 (the gate reads flattened CSVs, not raw tool edges), vs. leaving ingest implicit with just a gate caption.
5. Edge routing: orthogonal elbow chosen over bezier — confirm.
6. Kind color: artifact-kind is intentionally NOT color-coded (mono label only; reference = hollow ring), which supersedes the earlier kind→color table that collided with the gate/severity tokens. Confirm dropping kind-color entirely.
7. bayleafStatus: field values are ours|full|partial with badge display labels ours/consumes/substitute. Confirm the display mapping (or collapse field values to the display strings).
8. bam vs recal_cram: bam/bai are promoted to first-class kinds and the giab_panel anchor uses them (it slices a pre-aligned BAM); default/sarek profiles keep recal_cram and the two are never coerced. Confirm.
9. Emitted references' origin: set to unknown at emit (chosen, for strict non-launderability) even though references point at fixed files. Confirm the conservative choice vs allowing a fixed reference origin in the config.
10. sarek profile emit: since sarek is "illustrative/not wired," should Emit for that profile be allowed, or shown read-only/clearly labelled as target-state?
11. Pre-run label: tool nodes use a single `draft` state; the gate uses `pending — no verdict`. Confirm these two labels (superseding the earlier draft/composed/pending drift).
