# Handoff: PipeGuard operator UI → React

## Overview

PipeGuard is an AI-assisted **provenance & QC decision gate** for genomics pipeline
runs. For each sample in a sequencing run it recommends **proceed / hold / rerun /
escalate**, always with the supporting evidence, and uses AI to accelerate triage.
Domain: rare-disease germline DNA panel, Illumina short-read. The primary user is a
bioinformatics pipeline operator — technical, time-pressured, needs to see "what
needs my attention" in seconds.

This package is the design target for the **React frontend**. It covers eight screens,
the full verdict/gate model, all loading/empty/error states, and a complete set of
believable mock data that every number and citation on screen traces back to.

---

## About the design files

The files in this bundle are **design references created in HTML** — a clickable,
high-fidelity prototype showing intended look and behavior. **They are not production
code to copy directly.** The task is to **recreate these designs in the target
codebase's React environment**, using its established patterns and component library.

The brief specifies the intended stack: **React + a component library (shadcn/ui or
Mantine)**. Design in composable components and standard patterns; theme-aware and
responsive are nice-to-haves. If the target repo already has a component library and
tokens, map PipeGuard's primitives onto them rather than porting the inline styles
verbatim.

Two source files are provided:

- **`PipeGuard.html`** — a single self-contained file. **Open it in any browser** (no
  build step, no server, works offline). This is the visual + interaction reference.
  Use the **"State"** control in the top bar to preview loading / empty / error, and the
  **run switcher** (top bar) to move between runs.
- **`source/PipeGuard.dc.html`** — the annotated source. The `<script>` logic class at
  the bottom holds the **complete mock-data model** (`SAMPLES`, `TICKETS`, `STAGES`,
  `INTAKE`, `CONFIG`, `MONITORING`, `AGENT`, `RUNS`, thresholds). Treat this as the
  data contract: it is the source of truth for the shapes your React views must render.
  (`source/support.js` is the prototype's render runtime — reference only, do not port.)

---

## Fidelity

**High-fidelity (hifi).** Final colors, typography, spacing, layout, and interactions
are all intended as specified. Recreate the UI faithfully using the codebase's existing
libraries and patterns — match the layout, hierarchy, verdict color semantics, and
states precisely. Exact hex values, type sizes, and spacing are listed under
[Design tokens](#design-tokens); pull real values from `source/PipeGuard.dc.html` when
in doubt.

---

## Product model (read this first)

Everything on screen is organized around three ideas. Internalize these before building.

### Verdicts (per sample)
| Verdict | Meaning | Color |
|---|---|---|
| **proceed** | Cleared the gate; release downstream | green |
| **hold** | Borderline **data quality** — a human judgment call (not a rerun) | amber |
| **rerun** | **Operational / file-system failure** (crash, non-zero exit, missing artifact) — requeue | orange |
| **escalate** | Provenance / identity / chain-of-custody problem — stop, notify | red |

> **Critical distinction:** RERUN is reserved for operational failures (e.g. an
> alignment step segfaulted). A borderline data-quality problem (e.g. depth just under
> threshold) is a **HOLD**, never a rerun. This drives copy and iconography throughout.

### Gates (three, in sequence)
Every finding and verdict is labelled with the **gate** it came from. A sample blocked
at an earlier gate is not evaluated at later gates.

1. **Preflight** — did the run sequence, is the barcode/identity right, is the sample
   admitted? (color `#1f6feb`)
2. **QC** — depth, breadth/callability, Q30, mapping, contamination, genotype/sex
   concordance. (color `#1f5fd0`)
3. **Variant** — DP/GQ, Ti/Tv, Het/Hom, novel-vs-gnomAD, ClinVar. (color `#0e8f7e`)

### First-class primitives (build these as reusable components)
- **Verdict badge** — dot + label, tinted by verdict.
- **Gate-grouped evidence table** — rows of `source · locator · value · expected ·
  status`, with a `source_kind` chip (artifact / metric / trace / params / note) and
  bad/diff cells highlighted.
- **GateResult strip** — a per-gate result card (gate tag · verdict chip · one-line
  rationale) shown across the top of each decision card.
- **Status chips** — pass / borderline / fail, and ticket status open / in-review /
  resolved.
- **Origin tags** — `real-giab` / `synthetic` / `contrived` on provenance I/O.
- **Citations** — labelled references to findings and to a knowledge/experience corpus.
- **NOTE:** there is **no confidence meter**. Confidence is deliberately omitted until
  it can be grounded — do not add one.

---

## Screens / views

The app is a fixed-sidebar dashboard: a **236px dark left nav** + a **56px top bar** +
a scrolling content area. Nav is grouped into **Operate** (Runs, Intake gate, Decision
cards, Review queue), **Analyze** (Provenance, Agent triage, Monitoring), and
**Configure** (Settings). The top bar has: back button, page title, **run switcher**
(pill with status dot + mono run id), a search box (`/` affordance, non-functional in
prototype), a **State** preview control (dev affordance — see note below), and a
notifications bell with a count badge.

> The **"State"** control in the top bar is a **prototype-only** affordance for demoing
> loading/empty/error. In production this is not a user control — states are driven by
> real data-fetch status. Do not ship it; wire the states to your data layer instead.

### 1. Runs (home / overview) — `view: 'overview'`
- **Purpose:** entry point. Which runs need me?
- **Layout:** centered column, max-width 1080px. Header (title + subtitle + "Gate
  online" status dot). Filter chips row: **All runs / Needs attention / Released** (each
  with a count). Below, a vertical list of **run cards**.
- **Run card:** left — mono run id + `platform · date`; center — sample count + status
  pill + a **segmented verdict bar** (proportional proceed/hold/rerun/escalate
  segments, colored, with tooltips); right — an amber "N need attention" flag (when
  `attention > 0`) + a chevron. Whole card is clickable → opens Decision cards for that
  run.
- **States:** loading (4 shimmer skeleton rows), error (artifact store 503 with Retry),
  empty (no runs match filter, "Show all runs" clears it), ready (the list).

### 2. Intake gate — `view: 'intake'`
- **Purpose:** the **preflight** checkpoint, *before* processing. Did the flow cell
  actually sequence, and which samples are admitted?
- **Layout:** max-width 1000px. Header with a 3-step progress indicator
  (**1 Preflight** active → 2 QC → 3 Variant). Two cards:
  - **Run sequencing QC** — a 3-column grid of metric tiles (PhiX aligned, Cluster PF,
    Run Q30, Error rate, Cluster density, Total yield), each with value, gate threshold,
    and pass/fail chip. Header carries a green "Run admitted" pill.
  - **Sample admission** — one row per sample: mono id, a horizontal **yield bar** (% of
    run), `reads · % of run` caption, a status chip, and — for a **genuinely-sparse**
    sample — a **manual-override toggle** ("Admit anyway" ⇄ "Admitted (override)").
- **States:** has-intake (above) / no-intake (dashed empty card).

### 3. Decision cards (the hero) — `view: 'decision'`
- **Purpose:** the per-sample call and exactly why. Sorted **most-urgent-first**
  (escalate → rerun → hold → proceed).
- **Layout:** max-width 1080px. Header + a **Layout switcher** (Split / Brief / Dense —
  three density treatments of the same card body). Then:
  - **5 summary tiles** — count per verdict bucket (total / proceed / hold / rerun /
    escalate), mono numerals colored by verdict.
  - **Attention banner** (amber) when samples need attention → "Open review queue".
  - **Verdict filter chips** (All / Proceed / Hold / Escalate…) with counts.
  - **Decision cards list.** Each card is **expand/collapse**:
    - **Header (always visible):** chevron, verdict badge, mono sample id, one-line
      **headline**, sample-type chip, and an **origin chip** (`gateVerb` + origin tag,
      e.g. "admitted synthetic").
    - **Body (when open):** a **GateResult strip** (preflight/QC/variant, each a card
      with gate tag + verdict chip + one-line rationale), then the **QC readout** —
      a **columnar evidence table by gate** (Metric · Observed · Threshold · Status),
      **flagged-first**, with a per-gate rollup. Identity leads the QC gate
      (**NGSCheckMate genotype concordance** + sex concordance; FREEMIX is a demoted,
      optional non-default extra). Depth vs breadth (callability, zero-cov, fold-80) are
      shown as **distinct signals**. A **context rail** carries sample, run, the linked
      swap-pair, and the narration source. Findings list (rule id · gate · severity ·
      title · detail · cited evidence rows). Recommended **next steps**.
- **States:** loading ("sequencing in progress" + skeletons), error (synthesis failed —
  rule-derived verdicts still safe to act on, Re-run synthesis), released (green "Run
  released", nothing to review), empty (filter no match), ready (cards).

### 4. Review queue (human-in-the-loop) — `view: 'queue'`
- **Purpose:** cards-as-tickets, **open → in-review → resolved**.
- **Layout:** max-width 940px. Status filter chips. Ticket cards: id, run/sample, gate,
  verdict badge, issue-class, title, summary, "opened N ago", priority.
- **Actions:** **acknowledge**, **suppress an issue class** (so it stops re-prompting),
  **escalate**, **resolve**. Resolved tickets show `resolvedBy` + resolution note.
- **Recurring-signature detection:** when an issue class recurs (e.g. PROV-001 seen 3×
  in 14 days), the ticket surfaces a **pipeline-repair agent** escalation with two
  approval scopes: **fix-one** (this instance) and **fix-class** (the whole signature).
- **RBAC:** actions are gated by **reviewer vs approver** — reflect the tiering in the
  UI (the current user, `a.rivera`, is a **Reviewer**).

### 5. Provenance (read-only) — `view: 'provenance'`
- **Purpose:** the visual face of the provenance ledger.
- **Layout:** max-width 1080px. A horizontal **DAG**: intake → demux → QC → align →
  variant-call → gate, with the three **gate checkpoints** labelled (preflight on demux,
  qc on QC, variant on varcall). Each stage node shows tool + status (ok / warn /
  blocked). Click a stage → a **data I/O drill-in**: inputs & outputs with **name,
  sha256 hash, size, and origin tag** (`real-giab` / `synthetic` / `contrived`).

### 6. Agent triage — `view: 'agent'`
- **Purpose:** the AI triage note for a flagged issue. **Advisory framing** — the AI
  advises, the human decides.
- **Layout:** max-width 800px. For the flagged sample (S4 / PROV-001): **likely cause**,
  **suggested action**, **citations to findings** (SampleSheet, demux_stats,
  pipeline.log, metadata) and **citations to a knowledge/experience corpus** (KB /
  incident / SOP entries). An **offline ⇄ live** toggle and an **"Ask the agent"** chat
  input (appends to a thread — canned in the prototype).

### 7. Monitoring — `view: 'monitoring'`
- **Purpose:** operational health.
- **Layout:** max-width 1040px. KPI tiles (runs 7d, samples 7d, auto-proceed %, median
  review time), **gate pass-rate** bars (preflight/QC/variant), a **verdicts-over-time**
  stacked-bar throughput chart per run, and a **recurring-issue signatures** list with
  counts + trend arrows.

### 8. Settings (light) — `view: 'settings'`
- **Purpose:** mostly informational config.
- **Layout:** max-width 720px. Operator **profile** (lean vs granular), **Slack** notify
  toggle, **model tiering** (e.g. sonnet), narration **synthesis** source, and an
  **editable runbook thresholds** table keyed on **assay × sample type**
  (blood vs saliva columns), with per-metric direction (≥ / ≤), value, unit, and step.

---

## Interactions & behavior

- **Navigation:** left-nav items switch `view`. The top-bar **back** button pops a
  `history` stack. Clicking a run card (Runs) or "Open review queue" (banner) navigates
  with context.
- **Run switcher:** top-bar pill opens a menu of runs (id + status); selecting sets
  `runId` and re-derives every view from that run's data.
- **Decision cards:** header click toggles `open[sampleId]`; chevron rotates. Layout
  switcher sets `cardLayout` (`split` | `brief` | `dense`). Verdict chips set a filter.
- **Intake:** the per-sample override toggle flips `overrides[sampleId]` (admit a sparse
  sample).
- **Queue:** acknowledge / suppress / escalate / resolve mutate `tickets[id]`,
  `suppressed`, `escalated`; repair-agent approvals mutate `repair`. Respect RBAC
  (reviewer can acknowledge/suppress/escalate; resolve/approve-class implies approver).
- **Agent:** live toggle flips `agentLive`; the chat input appends to `agentThread`.
- **Provenance:** clicking a stage sets `stage` and shows its I/O.
- **Settings:** profile / slack / model / synth / threshold edits are local state.
- **Transitions:** content areas fade+rise on mount (`opacity 0→1`,
  `translateY(6px)→0`, ~.28s ease). Skeletons shimmer (~1.3s linear loop). A spinner
  rotates for in-progress. Keep these subtle.
- **States are first-class.** Every list/detail view has explicit loading, empty, and
  error treatments (documented per screen above). Build them as real states off your
  fetch layer, not afterthoughts.

---

## State management

The prototype keeps everything in one component's state; in React, split by concern
(route/view state, per-run derived data from a query layer, and local UI toggles). Key
state, verbatim from the prototype:

```js
view: 'overview',                // active screen
runId: 'RUN-2026-07-07-A',       // selected run — drives all derived views
filter: 'all',                   // runs list filter: all | attention | released
selected: 'S4',                  // focused sample
open: { S4:true, S5:true, ... }, // decision-card expand/collapse per sample
cardLayout: 'split',             // split | brief | dense
stage: 'demux',                  // provenance selected stage
tickets: { 'T-1042':'open', 'T-1041':'in-review', 'T-1039':'resolved', ... },
suppressed: {}, escalated: {}, repair: {},   // queue action state
overrides: { S4:true },          // intake manual-admit toggles
history: [],                     // back-nav stack
agentThread: [], agentInput: '', agentLive: false,   // agent triage panel
sfilter:'all', qFilter:'all',    // sample / queue filters
demo: 'ready',                   // PROTOTYPE-ONLY state preview (ready|loading|empty|error)
profile:'granular', slackOn:true, model:'sonnet', synth:'stub',  // settings
```

**Data fetching (production):** verdicts, evidence, provenance I/O, and monitoring come
from the artifact store / rule engine. Model each screen's loading/error against a real
query (the prototype's error copy — "artifact store returned 503 reading /runs",
"synthesis failed … verdicts are rule-derived and safe to act on" — is intentional and
worth keeping). Narration (headline/rationale) is AI-synthesized and can fail
**independently** of the rule-derived verdict — the error state must still show the
verdicts.

---

## Data model (the contract)

The full mock data lives in `source/PipeGuard.dc.html`. Match these shapes. Abbreviated:

```ts
type Verdict = 'proceed' | 'hold' | 'rerun' | 'escalate';
type Gate = 'preflight' | 'qc' | 'variant';
type Status = 'pass' | 'borderline' | 'fail';

interface Run {
  id: string; platform: string; date: string; samples: number;
  status: 'review' | 'running' | 'released';
  counts: Partial<Record<Verdict, number>>;   // for the segmented bar
  attention: number;                           // # needing operator action
}

interface Metric { label: string; value: string; gate: string; status: Status; note?: string; }

interface EvidenceRow {
  source: string; locator: string; value: string; expected: string;
  bad?: boolean; diff?: boolean;               // cell highlight flags
  // source_kind (artifact|metric|trace|params|note) is derived from `source`
}

interface Finding {
  rule: string; gate: Gate; cat: string;       // provenance|metadata|qc|pipeline
  sev: 'critical' | 'warn' | 'info';
  title: string; detail: string; evidence: EvidenceRow[];
  operational?: boolean;
}

interface GateResult { g: Gate; v: Verdict | 'blocked'; r: string; }  // per-gate strip

interface Sample {
  id: string; verdict: Verdict; gateOrigin: Gate | 'all';
  subject: string; sampleType: string; tissue: string; prep: string; by: string;
  reads: string; pctReads: string; linked?: string; linkedNote?: string;
  headline: string; rationale: string; steps: string[]; varNote: string;
  gates?: GateResult[];
  metrics: { pre: Metric[]; qc: Metric[]; var: Metric[] };
  findings: Finding[];
}

interface Ticket {
  id: string; run: string; sample: string; gate: Gate; verdict: Verdict;
  rule: string; issueClass: string; title: string; opened: string;
  priority: 'high' | 'medium' | 'low'; summary: string;
  recurrence?: { count: number; window: string; runs: string };
  resolvedBy?: string; resolution?: string;
}
// Also: STAGES (provenance DAG + I/O), INTAKE (run QC + sample admission),
// CONFIG (assay × sample-type thresholds), MONITORING (kpis/gatePass/throughput/
// recurring), AGENT (triage note + citations). All in the source logic class.
```

### The anchor scenario (`RUN-2026-07-07-A`, 5 samples)
The demo run every number traces to — reproduce it exactly:
- **S1, S2** — proceed (blood, cleared all three gates with margin).
- **S3** — proceed (saliva, saliva-adjusted thresholds).
- **S4** — **escalate** at preflight: barcode i5 (`AGGCGAAG`) ≠ sample sheet
  (`GGCTCTGA`), and that observed i5 is exactly S5's declared i5 → probable **S4/S5
  index swap**; `subject_id` also missing. QC/variant not evaluated (blocked upstream).
- **S5** — **hold** at QC: mean depth 29.2× and callability 91.8% both just under gate
  (saliva off-target), Q30 marginal. A judgment call, not a rerun.

A second review run (`RUN-2026-07-05-C`) demonstrates a **rerun** (S2 alignment
segfault — operational) and another **hold** (S4 borderline callability). Released runs
(`-06-A`, `-03-D`) show the all-proceed / released state.

---

## Design tokens

**Type:** `IBM Plex Sans` (UI) + `IBM Plex Mono` (IDs, values, hashes, barcodes,
numerals). Base UI size 14px. Titles ~22px/600; card headlines ~13.5–16px; captions
11–12px; section eyebrows ~10.5px uppercase, letter-spacing ~.5px. Mono is used for
every identifier and measured value.

**Core palette (light):**
```
--bg:#f5f7f9    --surface:#ffffff  --surface-2:#eef1f4  --surface-3:#e6eaef
--border:#e4e8ed   --border-strong:#d2d9e0
--text:#1b232c  --text-2:#586472   --text-3:#8b95a1
--accent:#1f5fd0   --accent-weak:#eaf0fc   --accent-strong:#1a4fac
page background (app shell): #eef1f4
```

**Verdict semantics (base / bg / border / fg):**
```
proceed  --proceed:#1a854e  bg #e9f6ee  bd #b6ddc4  fg #0f6b3c
hold     --hold:#b07714     bg #fbf2df  bd #eed9a9  fg #875809
rerun    --rerun:#c1560f    bg #fceee2  bd #f1cfac  fg #93420a
escalate --escalate:#cf3238 bg #fce9ea  bd #f2c2c4  fg #a3232a
```

**Finding severity:** `critical #cf3238` · `warn #c1560f` · `info #1f6feb`.
**Gate accents:** preflight `#1f6feb` · qc `#1f5fd0` · variant `#0e8f7e`.

**Left nav (dark):** bg `#141a21`, border `#202832`, text `#c3ccd6`, section labels
`#6b7683`, logo gradient `linear-gradient(155deg,#2f6bd6,#1a4fac)`.

**Shape & elevation:** radii — chips/pills 20px, buttons/inputs 8px, cards 11–14px,
icon tiles 9–12px. Card shadow `0 1px 2px rgba(16,24,40,.05)`; menu/popover shadow
`0 12–16px 32–40px rgba(16,24,40,.16–.18)`. Sidebar 236px; top bar 56px; content
columns max-width 720–1080px per screen (listed above).

**Motion:** fade-rise on mount ~.28s ease; shimmer skeleton ~1.3s linear; spinner ~1s
linear. Keep all motion subtle and functional.

---

## Assets

- **Fonts:** IBM Plex Sans + IBM Plex Mono (Google Fonts). Self-host or use your app's
  existing font pipeline.
- **Icons:** all icons are inline **Feather/Lucide-style** line SVGs (1.6–2.4 stroke).
  Use **`lucide-react`** (pairs with shadcn/ui) — the prototype's glyphs map to Lucide
  names (layers, funnel, file-check, git-branch, activity, sliders, bell, chevrons,
  alert-triangle, check-circle, refresh, etc.). No raster/image assets are used.
- **No Anthropic brand assets** are used; nothing to carry over there.

---

## Files in this bundle

- `README.md` — this document (self-sufficient; implement from this alone).
- `PipeGuard.html` — self-contained clickable prototype. **Open in a browser** — the
  visual + interaction reference.
- `source/PipeGuard.dc.html` — annotated source; the `<script>` logic class holds the
  **complete mock-data model** (the data contract).
- `source/support.js` — the prototype's render runtime (reference only; do not port).
- `frontend-design-brief.md` — the original product brief (audience, principles, scope).

## Explicitly out of scope (this pass)

The editable pipeline builder, deep settings, and data-platform integrations. Keep to
the core flow above.
