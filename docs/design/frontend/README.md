# PipeGuard — Frontend Design Handoff (complete)

A single, current package for implementing the PipeGuard frontend in React. This supersedes
all earlier handoffs — the prototype here reflects the latest design across every screen.

---

## 1. What PipeGuard is
A provenance & QC **decision gate** for germline/somatic sequencing runs. Deterministic
rules compute a per-sample verdict — **proceed · hold · rerun · escalate** — across three
gate stages (**preflight · qc · variant**). Agents *advise* but never decide; every artifact
is traceable to its origin. The product's spine: **rules decide, AI advises, nothing on the
critical path can launder a verdict.**

## 2. How to use this package
- **`PipeGuard.html`** — the complete, self-contained clickable prototype. Open in any
  browser; works offline. This is the **design reference** — the source of truth for layout,
  color, type, spacing, and interaction.
- **`source/PipeGuard.dc.html`** — annotated prototype source. Its `<script>` logic class
  holds all mock data, the live-YAML generator, and every handler referenced below. Read it
  to see exact values. `source/support.js` is the prototype runtime — **reference only, do
  not port.**
- **`briefs/review-to-design-brief.md`** — the authoritative product brief.

### These are design references, NOT code to ship
Recreate every screen in the **existing React app** (`frontend/src/`), reusing its component
library and the token source of truth (`frontend/src/index.css` `@theme`,
`frontend/src/verdict.ts`). Do not lift the prototype's HTML/runtime into the app.

## 3. Fidelity
**High-fidelity.** Final layout, tokens, and interactions are intended as-shown. Where a
value isn't stated here, read it from `source/PipeGuard.dc.html`.

---

## 4. App shell
- **Login gate (Shipped 2026-07-09→10, T-081, commit `0f7e85f`).** The whole app now sits
  behind `screens/Login.tsx`: email/password (+ show/hide), a one-click demo-account picker
  (`l.santos` viewer / `a.rivera` reviewer / `m.chen` approver / `s.ops`/`admin@lab.org` admin,
  shared password `pipeguard`), a labelled CAPTCHA placeholder that gates submit, a "Forgot
  password?" stub, and a security-posture footer naming every production seam NOT built (real
  OAuth/OIDC, server-side password hashing, an httpOnly session cookie, real CAPTCHA, signed
  reset links, TLS). `App.tsx`'s `RequireAuth` guard redirects any unauthenticated route to
  `/login`, preserving the intended destination. This is a **demo-only client-side gate**, not
  production auth (see §8 Invariants + [risks.md RISK-035](../../quality/risks.md)).
- **Left nav (236px, dark `#141a21`).** Two groups:
  - **Operate:** Submit samplesheet · Runs · Intake gate · Decision cards · Review queue ·
    Provenance · Agent triage · Monitoring
  - **Configure:** Pipeline builder · Settings
  - Plus an **Admin** group (`/admin`, off the operator nav — see §11), gated on the login
    identity's `isAdmin`, not on any wire role.
- **User panel (nav footer).** Avatar + name → popover: **Role** row (reflects & toggles
  **reviewer/approver** RBAC — the same flag the Review queue and approval flows read),
  **Settings** (opens the Settings dialog), **Sign out**.
- **Top bar — run switcher (Shipped 2026-07-09, T-074, commit `17a3e56`).** The run-context
  pill opens a searchable combobox (filters by run id or platform), capped at 8 rows, with a
  "View all runs · N runs →" footer to the Runs list and an honest "No runs match" empty
  state. The pill's dot and every row's dot read the run's real lifecycle `status`
  (`needs_review`/`running`/`released`) via a shared `RUN_STATUS_META`, never inferred from
  attention count — a running run with 0 flagged samples reads "Sequencing," not a green
  "all clear."
- **Content:** light surface (`--bg #f5f7f9`, cards `--surface #fff`), max-width per screen.
- **Type:** IBM Plex Sans throughout; **IBM Plex Mono** for every id, path, hash, index,
  version, kind, size.
- **Theme + density (Shipped 2026-07-10, T-091, commit `08a42ad`).** The Settings dialog's
  Theme (light/dark/system) and Density (split/brief/dense) controls now take effect and
  persist to `localStorage` via a new `context/PrefsContext.tsx`; `system` follows the OS
  live. A full dark theme lives in `index.css` (`:root[data-theme="dark"]` overriding the
  `@theme --color-*` vars — page/card/surfaces/text/accent + dark verdict bg/border/fg +
  shadows), so every existing Tailwind utility retargets with no per-component change. Density
  is now **one** setting shared by the dialog and the Decision-cards Layout control (§5.4) —
  it survives across runs and a refresh.

---

## 5. Screens (current design)

### 5.1 Submit samplesheet  (`view: 'submit'`)
The pipeline's front door — registers a run + its samples **before processing**.
- Two methods (segmented): **Upload samplesheet** (drop CSV / Illumina v2 sheet → parsed
  chip) and **Pull from BaseSpace**.
- **BaseSpace requires connecting first** — a connect card (credentials) gates the run list;
  before connect, run details + samples are **blank** and populate only on **Import**.
- **Run details** (applies to all samples): run name, study/project, assay, sequencer.
- **Samples table** (editable): `# · sample name · sample type · i7 (index) · i5 (index2) ·
  study`; add / remove rows; sample type cycles a fixed set.
- Footer: guardrail note ("barcodes checked at preflight, not here"), **Save draft**,
  **Submit to pipeline** → Intake gate.
- **Shipped 2026-07-09 (T-057, commit `e77c2e6`):** Submit now hands off to a real execution
  boundary — `POST /api/runs` registers the run and triggers the pipeline driver
  (`scripts/run_giab_pipeline.py`) as a background subprocess; the UI polls
  `GET /api/runs/{id}/intake-status` and navigates to Decision cards on completion. This demo
  build only has real reads on disk for `HG002`; other samples are honestly reported as
  *skipped*, never fabricated. **Compose ≠ execute still holds at the core** — `src/pipeguard/`
  itself never runs a tool; only the API layer triggers the external driver (see §8). A
  BaseSpace connector remains wishlist (T-057).

### 5.2 Runs  (`view: 'overview'`)
Scale-kit list surface:
- **Search** (run id / platform), **status facet chips w/ counts** (All · Needs review ·
  Sequencing · Released), **sort** (Recent · Urgent), and a **date-range** control
  (calendar with From/To fields + presets; fixed-width trigger so digit-count changes don't
  reflow the row).
- **Per-page 25 / 50 / 100** (default 25), scrollable.
- **Run cards:** clean (no left color bar), mono run id, platform · date, N samples + status
  pill, attention chip, and a verdict bar with an **inline count legend**
  (e.g. "19 Proceed · 5 Hold · 2 Rerun · 2 Escalate"); hover lift. Running/released rows omit
  the legend. Seeded with 28 runs incl. a 28-sample `RUN-2026-07-08-WES28`.

### 5.3 Intake gate  (`view: 'intake'`)
Preflight sample-admission review. **Collapsible admission rows** (consistent bar lengths,
room for status + action). Header carries a **Refresh** control + "Updated {time}".

### 5.4 Decision cards  (`view: 'decision'`)
Per-sample verdict cards for a run.
- **First card open, rest collapsed**; **Expand all / Collapse all**; verdict **filter chips**.
- **QC metric readout** (the hero): a Metric · Observed · Threshold · Status table populated
  from `DecisionCard.metric_values` (flagged-first, gate-grouped) — recreate with the app's
  `MetricsPanel`. Plus a context rail and clear loading / empty / released / synthesis-error
  states.
- **Shipped 2026-07-09 (T-073, commit `12ffa30`):** the hero now shows all **three** gates
  (preflight → qc → variant) honestly — a gate with real metric rows shows them; a gate the
  runbook thresholds but the card didn't measure shows a `not_measured` placeholder; a gate
  with no metric table at all (preflight is rule-based — see the gate strip/evidence; variant
  extracts no metrics in this build) shows an explicit empty-state note instead of vanishing.
  Nothing is fabricated; the gate stays byte-for-byte unchanged.
- **Shipped 2026-07-10 (T-082, commits `a8fc73b`→`a9b06ad`):** the preflight/variant "no metric
  table" case above is now often a real one — `QCMetrics` gained 8 additional registered fields
  (PhiX aligned; breadth ≥20x/30x, mapped reads, on-target — extra QC; depth/GQ/Ts-Tv —
  variant), so a **contrived** demo card can render a full 13-metric, three-gate table (5
  originally-gated + 5 newly optional-gated + 3 ungated observations, the latter labelled with
  the registry's display name, e.g. "Ts/Tv ratio," not the raw key). The **real** GIAB HG002 card
  stays honest about what it actually measured — it now also shows real `breadth_20x`/`breadth_30x`
  from its own mosdepth, but nothing it doesn't produce is invented.
- **Gate dependency (Shipped 2026-07-10, T-087, commit `545c893`, "DC2 part 1" of the
  maintainer's two-tier gate model).** Sequencing-tier QC (preflight) gates sample processing;
  sample-tier QC gates downstream analysis (variant). A gate group whose **upstream** gate isn't
  clear now reads "**blocked · clear \<upstream\> first**" (a `hold`-toned pill, takes priority
  over "all clear"/`not_measured`) instead of silently reading as clear — so a QC hold no longer
  looks like the sample proceeded to variant calling. `api/card_readout.py`'s `GateReadout`
  carries the new `blocked_by: Gate | None`; **pure re-presentation** — the card's verdict
  already reflects the QC finding, no rule/gate logic changed (ADR-0001 intact). Part 2
  (user-clearable HOLD/ESCALATE, individually + in batches) is the next slice, not yet built.
- **Pill polish (Shipped 2026-07-10):** the top gate-results strip's "Passed" chip is now
  **green** (proceed tokens; T-089, commit `d5fdcb2`) rather than a neutral grey — a "Not run"
  (hard-blocked-upstream) chip stays grey. This is a **different** pill from the gate-dependency
  one above (top-strip chip = the card's own verdict; QC-readout Rollup chip = the gate
  dependency). The card's redundant 3px verdict-colored left spine is **dropped** (T-088, commit
  `24940e1`) — the verdict is already carried by badges/pills; the colored rail is now reserved
  for Pipeline-Builder tool cards (§6), which keep their own spine.

### 5.5 Review queue  (`view: 'queue'`)
Cross-run triage. **Reviewer/approver RBAC**, **first-open + Expand/Collapse all**,
collapsible tickets (header row is the toggle), per-ticket actions (suppress / escalate /
resolve).
- **Shipped 2026-07-09 (T-078, commit `e3e1995`):** 25/50/100 pagination + a numbered pager
  (mirrors Monitoring); tickets visually grouped under a sticky per-run subheader; the default
  filter flipped all → open so resolved tickets leave the active view but stay reachable via the
  Resolved facet chip.

### 5.6 Provenance  (`view: 'provenance'`)
Left→right stage DAG + a per-stage I/O inspector.
- Every artifact is a **link** — open in store, copy digest, download.
- Nodes **color by stage status only** (pass/warn); the origin / sample-type chips and the
  header legend were removed (sample type comes from the sample sheet).
- **Shipped 2026-07-09 (T-077, commit `71a06d6`):** download/open-in-store are now real —
  `GET /api/runs/{id}/artifacts/{name}` (traversal-hardened) backs both anchors. A "show full"
  toggle reveals all 64 hex chars of the digest. The QC node now shows a real input edge:
  the demux stage's output (`demux_stats.csv`/reads) doubles as the QC stage's input, so QC no
  longer reads as orphaned.
- **Shipped 2026-07-10 (T-080, commit `eb7d016`):** the digest column now reads "hash"/"content
  hash," not "sha256," on screen (defense-in-depth — the wire field and its value are unchanged).
- **Shipped 2026-07-10 (T-090, commit `de5fa94`, P1/P2):** clicking the artifact **name** and
  clicking **Download** used to hit the same URL and both forced a save. `GET
  /api/runs/{id}/artifacts/{name}` now serves **inline by default** (name-click views the file at
  its location) and attaches only when the Download link passes `?download=1` (traversal-hardening
  unchanged). P2: an explanatory hover on `sample_metadata.csv` ("Intake · LIMS/subject metadata
  sheet") vs `SampleSheet.csv` ("Demux · Illumina barcode/index manifest") surfaces the
  intake-vs-demux distinction that previously lived only in the stage grouping.

### 5.7 Agent triage  (`view: 'agent'`)
Advisory triage assistant. **Chat composer**: multi-line text window, **Enter** sends,
**Shift+Enter** newline, circular send, suggestion chips, and a **pop-out / minimize**
toggle. Helper line reinforces "advisory · can't change the verdict."
- **Shipped 2026-07-09 (T-078, commit `e3e1995`):** the case selector is now a
  Sample·Verdict·Gate·Headline·Findings table (was a non-scalable pill row), verdict-ranked,
  with the active row highlighted.

### 5.8 Monitoring  (`view: 'monitoring'`)
- **Recurring issue signatures**: **searchable**, **collapsible rows** on a fixed 5-column
  grid (chevron · signature · first→last seen · frequency · trend) so fields align; each row
  shows **firstSeen → lastSeen** dates and expands to detail.
- All rows **escalatable** to the pipeline-repair agent; **affected-run chips are links** →
  that run's Decision cards filtered to *Needs attention*.
- Windowed KPIs (incl. **Median review**), date-labelled throughput bars, 7/14/30d window.
- **Shipped 2026-07-09 (T-078, commit `e3e1995`):** a `DateRangePicker` after the window views
  refines the throughput chart client-side, with an honest caption that the KPIs/gate-pass rates
  stay window-scoped; the stacked bar gains a Y-axis gutter, a "samples" label, and gridlines.
- **Shipped 2026-07-10 (T-080, commit `eb7d016`):** the throughput bars are now a **constant
  width** (28px) inside a scrollable viewport, so they no longer stretch/squish as the run
  count or date range grows.
- **Shipped 2026-07-10 (T-072 frontend half, commit `34bca5d`):** the throughput card's per-run
  columns now paginate client-side too (25/50/100 + numbered pager, "Showing X–Y of N runs"),
  ported from the recurring-signatures pager pattern with independent state (its own per-page +
  page, reset on window/date-range/per-page change); `maxSamples` stays computed over the full
  filtered set so the y-axis doesn't jump between pages. **Frontend-only** — `GET
  /api/monitoring`'s `runs[]` payload itself stays uncapped server-side ([tasks
  T-072](../../planning/tasks.md) is still open for the backend half).

### 5.9 Pipeline builder  (`view: 'builder'`)  — see §6 for the full model
Node-graph editor that **emits `run_layout.yaml`**. Defaults to **View**; **Edit** unlocks
authoring.

### 5.10 Settings  (`view: 'settings'`)
- **Assay dropdown**; **thresholds are assay-specific** (table swaps per assay).
- **Read-only by default** → **Edit thresholds** unlocks fill-in inputs, swapping the bar to
  **Cancel · Save changes**; save is per-assay, **audited** (who · when), guarded (a gate
  can't cross its hard-fail; % clamp 0–100), and **approver-gated**.
- **Per-agent model tiering** (dropdowns, full versioned model names; roster incl. Fable 5).
- **Sample-type dropdown (Shipped 2026-07-10, T-095, commit `869cf55`).** The threshold matrix
  showed Whole-blood and Saliva as two side-by-side columns; a Sample-type dropdown beside the
  Assay selector now picks one tissue at a time and the table shows a single value column,
  cleaner and scaling as more sample types are added. Editing/save/approve, the per-tissue
  values, and the audit lifecycle are unchanged (still keyed on assay × sample type).
- **Notifications:** Slack, Microsoft Teams, Discord.
- **Settings dialog** (from the user panel): profile (name / email / role / time zone) +
  preferences (theme, density, email digest, desktop notifications), Cancel / Save.

---

## 6. Pipeline builder — full model

**Modes.** Defaults to **View** (read-only: palette tiles disabled, add guarded, "Author a
tool node" replaced by a read-only note). **Edit** enables all authoring.

**Canvas.** Large, pannable in any direction; loads centered on the pipeline. Dot-grid = 20px
snap grid. Top-right **minimap** (spine + gate + composed nodes — moved from bottom-right
2026-07-10, T-085, commit `14c9f3c`, so it no longer sits under the feedback bubble) — **grown to
a 210×108 proportional mirror** (was 168×46), 2026-07-10, T-084. Floating zoom + **Tidy**
(auto-layout) + **Connect** controls, plus (2026-07-10, T-084) a native ctrl-wheel/trackpad-pinch
zoom on the canvas itself (`{ passive: false }`, since React's `onWheel` can't `preventDefault`;
plain wheel still pans; clamped 0.6–1.4), and **Fit** now centers/zooms to the pipeline's actual
bounding box instead of only resetting the zoom level. **Tidy is flow-preserving** (2026-07-10,
T-085): each node lands in the column of its longest-path depth from a source
(upstream→downstream reads left→right, parallel nodes stacked in a column) instead of dropping
every card into one row and losing the connection structure. A **Cancel** button (shown only
while composing a draft) discards the in-progress build and returns to the linked pipeline in
View.

**Nodes.** Three kinds — `tool`, `agent`, `gate`:
- **Seeded germline chain** (fastp → bwa-mem2 → samtools markdup → {mosdepth, bcftools call →
  bcftools norm} → MultiQC) + reference nodes (genome / panel BED / truth VCF) + the QC-triage
  agent + the terminal gate. **Tool I/O corrected 2026-07-10 (T-083, commit `d8c1625`)** against
  the real pipeline (`scripts/run_giab_pipeline.py`): bcftools call gains a `panel_bed` input
  (`mpileup -R PANEL`), bcftools norm loses it (norm has no `-R`); samtools markdup now outputs
  `bam`·`bai`·`markdup_metrics` (was a phantom `samtools_stats` with no producer); bwa-mem2
  outputs `bam` only (the `.bai` comes from markdup's index); mosdepth gains
  `mosdepth_thresholds`; MultiQC's fan-in drops the phantom `samtools_stats`. **The seeded
  connector lines are now COMPUTED** from the tool/reference card geometry + typed ports (were
  hardcoded SVG path strings anchored to fixed pixels, which detached from a port the moment a
  card's port count changed) — the same anchoring the free-composition edges already used, so a
  connector can never detach again.
- **Free composition (Edit):** click a palette tool to add a node; **drag** to place
  (grid-snap); delete per-node. Composed cards are **visually identical to the seeded DAG
  cards** — the tool's own icon, version, and typed I/O ports.
- **Reference SOURCE cards from the palette (Shipped 2026-07-10, T-086, commit `c6a6210`).** A
  new **References** palette section — Reference FASTA, Panel BED, Truth VCF — adds a no-input
  node emitting its reference artifact (`reference_fasta`/`panel_bed`/`truth_vcf`), so an
  operator can drop a reference and **Connect** it into a tool's ref input; typed wiring keeps a
  fasta off a fastq port. Fills the earlier "no way to add bed/vcf/reference cards" gap. The
  palette's sections are now **collapsible** (chevron + per-section item count) so a growing tool
  list stays navigable; an active search overrides collapse so matches always show.
- **Shipped 2026-07-09 (T-075, commit `01ba673`):** "New → From template" now seeds this free
  composition with the germline chain as **editable** nodes/edges (`germlineTemplate()`),
  not a re-shown read-only copy of the seeded DAG — closing a gap where the demo's own
  pipeline couldn't be modified in Edit. Only the **original linked** pipeline still renders
  the read-only seeded DAG; any new or forked draft is fully editable.
- **Ports** render as **half-circles on the card edge**, becoming **full circles in Connect
  mode**. **Port-to-port connect:** toggle **Connect**, click an **output** circle, then an
  **input** circle on another card; the elbow edge anchors to those exact ports. Enforce
  **typed-port compatibility** (an output kind connects only to a matching input kind).
- **Gate** is terminal / singular / non-removable; reads the frozen five `run/` CSVs, not raw
  tool edges. **Agents are port-less** (off the critical path).

**Inspector (right panel).** Tabs **Params · Locators · I/O · Agents**:
- **Params** — schema-driven form (from bundled `nextflow_schema.json`).
- **Locators** — editable per output kind: `path|glob`, `parser`, `on_multiple`
  (first/all/error), `required`; `role`/`origin` read-only (**origin locked `unknown` —
  stamped at ingest, never authored**). Edits regenerate the console YAML live.
- **Reference cards** (genome / panel BED / truth VCF) open the **same inspector**: kind,
  editable **location** path, **role: reference**, pointer-only parser, origin unknown.

**Profile control.** Searchable **combobox** — built-in (`default`/`giab_panel`/`sarek`) +
**saved** profiles (versioned, w/ status) + **New profile from current graph**.
- **Open a saved pipeline (Shipped 2026-07-10, T-069, commit `adfd7aa`).** A toolbar **"Open"**
  action lists `GET /api/pipelines` (latest version per name) and hydrates the canvas
  (nodes/edges/locators/reference locators/profile/version/status) from a chosen graph. An
  **approved** graph opens **read-only**; re-saving mints a new draft rather than mutating it.
  Honest loading/empty/error states; a foreign envelope with no restorable builder topology
  (a different `schema_version`) loads empty with a labelled toast — never fabricated nodes.

**Save · version · approval.** Toolbar shows graph version + status pill
(**draft → pending approval → approved**), **Save**, approver-only **Approve**, and the RBAC
role toggle.

**Console (bottom, tabbed).** **Validate** (static typed checks; click a finding → focuses
the node) · **Diff** · **Dry run** (locator resolution → matched / ambiguous / missing;
resolves paths only, reads no bytes). **Emit / Copy / Download** produce the real
`run_layout.yaml`.
- **Real backend wiring once Saved (Shipped 2026-07-10, T-096, commit `4208f0b`, "closes the
  Dry-run/Diff limitation").** Before the graph is Saved, both tabs render the earlier
  client-side-only preview (Diff vs last **Emit** snapshot; Dry-run vs a mock run dir). Once
  Saved (the graph exists in the pipeline store), **Dry-run** gains a run-id input +
  "Resolve against run" → `POST /api/pipelines/{name}/dry-run?run_id=…`, rendering the REAL
  per-locator matched/ambiguous/missing/invalid resolution + summary; **Diff** gains "Diff vs
  approved baseline" → `GET /api/pipelines/{name}/diff`, rendering added/changed/removed vs the
  approved baseline (or "no baseline yet"). Save stamps `savedName` (+ clears prior results);
  New/Cancel reset it. **Compose ≠ execute still holds** — a dry-run globs paths, reads no
  bytes, runs nothing.
- **Dry-run's run-id field is now the reusable `RunSelector` (Shipped 2026-07-10, T-070, commit
  `3c6455e`)** — a searchable (id/platform), 8-row-capped combobox sharing the top-bar switcher
  idiom (real status dot via `RUN_STATUS_META`, F17, never `n_attention`), replacing the earlier
  plain text box. Self-fetches `api.runs()` lazily on first open; an honest "Couldn't load runs"
  on fetch failure, never a fabricated row. Its props leave it ready for other run-identity
  pickers (e.g. the Run hand-off modal below) as future consumers.

**Run.** A **hand-off** modal (composes ≠ executes): Emit `run_layout.yaml` → Nextflow/bioconda
runs (outside PipeGuard) → deterministic ingest writes `run/` → `run_gate` gates + records the
ledger → Decision cards. Primary action hands off to the engine; the UI never runs tools.
**Shipped 2026-07-10 (T-069, commit `adfd7aa`):** the modal now renders the REAL composed
`run_layout.yaml` the builder emits (`yamlFor`, labelled by profile + locator count), and its
button **copies** that YAML (+ fires the compose-only Emit) instead of the earlier fake "Hand
off to Nextflow" button — no network call, compose ≠ execute unchanged.

**Node-authoring agent** ("Author a tool node"). Drop tool docs (`--help` /
`nextflow_schema.json`) → an advisory agent proposes a typed `ToolNode`: editable **name**, an
**icon picker**, and a **scrollable flag checklist** (tickable CLI flags + editable default
values). Unknown artifact-kinds are **flagged, never invented**; the human reviews and accepts.
**Still a static `phase-2`-labelled preview** — unlike the two advisory-agent modals below, this
one is not wired to a backend endpoint (design note only, [tasks T-046](../../planning/tasks.md)).

**Advisory agents.** **Pipeline-repair** (proposes fixes for recurring signatures) and
**Archivist** (proposes cold-storage of released `run/` dirs) — both stub-first, human-approved,
off the critical path; never edit the pipeline or a verdict. **Wired to real data (Shipped
2026-07-10, T-069, commit `adfd7aa`) — both were static previews before this.**
`PipelineRepairModal` now loads `GET /api/monitoring` for a recurring-signature picker (default:
top-ranked) and `GET /api/monitoring/signatures/{sig}/repair` for the REAL `RepairProposal`
(summary/rationale/`attach_to`/`scope`/`signature_count`, cited corpus refs each labelled with a
**"heuristic" score, never "confidence"**); "Send to review queue" **navigates** to `/queue`
rather than creating a fabricated ticket (a signature-level fix has no `sample_id`/verdict to
attach one to); a fetch failure shows the shared honest fallback ("the agent is unavailable...");
zero recurring signatures shows "nothing to propose." `ArchivistModal` now loads `GET
/api/archive/index` for the REAL cross-run `ArchiveDigest` — n_runs/archive-ready counts, runs
held from archival (running/in-review), origins rendered verbatim (never relabelled), size,
recurring signatures, the proposed action, and the backend's own advisory disclaimer verbatim;
"Queue archive" stays an inert button (no write endpoint exists yet); a fetch failure shows an
honest "archivist agent is unavailable" state, never a fabricated digest.

---

## 7. Data contract (TypeScript sketch)
The graph is authoring state; the **verdict is computed at run time by `run_gate`**, never
stored on the graph. The graph's only grounded output is `run_layout.yaml`.

```ts
type Verdict = 'proceed' | 'hold' | 'rerun' | 'escalate';
type Gate = 'preflight' | 'qc' | 'variant';
type RunStatus = 'running' | 'review' | 'released';
type ArtifactKind = 'fastq'|'bam'|'bai'|'recal_cram'|'recal_table'|'mosdepth_summary'
  |'fastp_json'|'markdup_metrics'|'samtools_stats'|'vcf'|'gvcf'|'filtered_vcf'|'joint_vcf'
  |'ngscheckmate'|'multiqc_json'|'versions_yml'|'params_json'|'execution_trace';
type ReferenceKind = 'reference_fasta'|'panel_bed'|'truth_vcf';
type OriginTag = 'real-giab'|'synthetic'|'contrived'|'unknown';   // never relabels up

interface RunSummary { id:string; platform:string; date:string; samples:number;
  status:RunStatus; counts:Partial<Record<Verdict,number>>; attention:number }   // status is a REAL field, not inferred

interface Submission { runName:string; study:string; assay:string; platform:string;
  source:'upload'|'basespace'; samples:SampleRow[] }
interface SampleRow { sample:string; type:string; i7:string; i5:string; study:string }

interface LayoutLocator { kind:ArtifactKind|ReferenceKind; path?:string; glob?:string;
  parser:string|null; required:boolean; role:'output'|'reference';
  onMultiple:'first'|'all'|'error'; origin:OriginTag /* 'unknown' at emit */ }
interface RunLayoutConfig { schemaVersion:'run_layout/1'; profile:string;
  locators:Record<string,LayoutLocator> }

interface PipelineGraph { id:string; version:number; status:'draft'|'pending'|'approved';
  runbookProfile:string; nodes:Node[]; edges:Edge[] }     // reserve version+status now
interface ProposedFlag { flag:string; value:string; enabled:boolean; help:string }
interface AgentProposal { agent:'qc_triage'|'pipeline_repair'|'archivist'; advisoryOnly:true;
  summary:string; mode:'stub'|'claude' }
```

### Backend seams
`RunSummary.status` as a real field; list endpoints accept `page/limit(25|50|100)/sort/q/
verdict/dateFrom/dateTo`; a windowed Monitoring aggregate with `first_seen`/`last_seen`;
a `PipelineGraph` version+approval store (off the decision domain) with only approved graphs
emitting a blessed config; assay×sample-type `QCThreshold` with audited edits; BaseSpace
connect + `GET /basespace/runs` + import.

---

## 8. Invariants (never cross)
Rules decide / AI advises · **agents off the critical path** (port-less; the triage chat and
node-author agent never change a verdict) · **compose ≠ execute holds at the core**: `src/pipeguard/`
never runs a tool; Submit now hands off to a real **execution boundary**
(`POST /api/runs` → `api/routers/intake.py` triggers `scripts/run_giab_pipeline.py` as a
background subprocess, T-057, 2026-07-09) and Builder emits `run_layout.yaml` for a hand-off —
the API layer may trigger an external driver, but only the driver (never PipeGuard itself)
runs a genomics tool · the gate reads the frozen five
`run/` CSVs · **origin never relabels up** (stamped at ingest, never authored — incl.
provenance links, locators, reference cards) · reuse the existing event vocabulary · **no
confidence meter** · no clinical/diagnostic claims.

## 9. Tokens
Reuse `frontend/src/index.css` `@theme` + `frontend/src/verdict.ts`. Key families (exact hexes
in `source/PipeGuard.dc.html` `:root` and the app's theme): verdict 4-shade
(proceed/hold/rerun/escalate, each dot/bg/bd/fg); gate accents **preflight `#1f6feb` · qc
`#1f5fd0` · variant `#0e8f7e`**; severity (critical/warn/info); accent `#1f5fd0`; neutrals
`--bg/--surface/--surface-2/--surface-3/--border/--border-strong/--text/--text-2/--text-3`.
Shape: chips ~20px radius, buttons/inputs 8px, cards 11–14px; card shadow
`0 1px 2px rgba(16,24,40,.05)`.

## 10. Files
- `PipeGuard.html` — complete self-contained prototype (open in a browser).
- `source/PipeGuard.dc.html` — annotated source (all data + handlers).
- `source/support.js` — prototype runtime (reference only; do not port).
- `briefs/review-to-design-brief.md` — authoritative product brief.

Suggested repo drop: `docs/design/frontend/handoffs/` — point Claude Code here to implement
against `frontend/src/`.

---

## 11. Admin (`/admin`) — governance, off the operator nav

**Shipped 2026-07-09 (T-066, commit `ce396f7`); gating corrected 2026-07-10 (T-081, commit
`0f7e85f`).** Not part of the original design pass above (added during the maintainer-feedback
batch); tracked here because it shares the login/RBAC surface §4 now fronts. A screen at `/admin`,
visible only when the LOGGED-IN identity's `isAdmin` is true (a frontend-only governance
capability layered over viewer/reviewer/approver — an admin is an approver who also holds
governance; **not** "any approver," which was the original, now-corrected framing). Three tabs:

1. **Users & roles** — an explicit **client-mock** roster (there is no backend user store;
   `api/auth.py` is a header dev-shim) with a per-user role selector and an "Act as" control wired
   to `RoleContext.setActor` (switches id+role together) so an operator can preview any seeded
   actor's RBAC surface, plus a persistent "dev auth shim, not an identity system" banner.
   **Shipped 2026-07-10 (T-092, commit `5774143`, "A1"):** a role change no longer applies on
   every click of a 3-way toggle (a stray click could reassign a role) — the control is now a
   dropdown, and a change **stages into a draft** ("unsaved" badge) behind an explicit **Save
   role changes / Discard** bar; only Save commits it (and re-syncs the live actor if its own
   role changed). "Act as" now **confirms** before impersonating, naming the target user + role,
   since it is already admin-panel-gated. Still the same client-mock roster — this hardens the
   legitimate UI path, not the underlying security boundary ([risks.md RISK-035](../../quality/risks.md)).
2. **Activity log** — a REAL, zero-new-backend audit feed merging `GET /api/settings/thresholds`
   + `GET /api/pipelines` + `GET /api/review/tickets` into one append-only when/actor/kind/target/
   status table, facet-filterable by kind. **Shipped 2026-07-10 (T-093, commit `8a14661`, "A2"):**
   the feed now paginates (25/50/100 + a numbered pager, "Showing X–Y of Z," resets on filter
   change — was a flat, uncapped list that got messy as it grew) and each row is a compact
   summary that expands on click to a labelled Detail/Target/Actor/When panel (one open at a
   time); no backend change.
3. **System** — REAL reads of `GET /api/health` + the runbook's gate count + the metric-registry
   version/gated-count, labelled illustrative-not-clinical. **Shipped 2026-07-10 (T-094, commit
   `7c56564`, "A3/A4"):** gained an **Artifact-store** stat card (`local` · the
   `PIPEGUARD_ARTIFACT_STORE` s3 seam) and an **Observability** section linking the read-API's
   `/metrics` exporter, Prometheus (`:9090`), and the Grafana "PipeGuard — QC decision gate"
   dashboard (`:3000`, built T-036/T-079) as off-demo-path links (Grafana blocks framing; the
   telemetry stack is off the offline demo path), with a note on bringing up the compose stack.
   Users & roles also gained a per-user **password/email-reset** action — a labelled production
   seam (no live mail) that toasts what would happen (a signed, expiring reset link emailed to
   the user).

Admin decides **who** may perform an off-gate product write and whose id lands in an audit
`*_by` field — it never sets, overrides, or displays a verdict/finding/confidence, and carries
**no confidence meter** (§8 Invariants hold here too).
