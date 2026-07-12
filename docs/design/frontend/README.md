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
- **Left nav (236px).** Three groups (correcting an earlier 2-group simplification in this doc —
  the code has always shipped three since T-064):
  - **Operate (reordered 2026-07-10, T-110, "Wave 8," G4):** **Inbox** → **Review queue** →
    Submit samplesheet → Runs → Intake gate → Decision cards — Notification (Inbox) → Action
    (Review queue) → Steps (the process flow), work/issue-tracking pages now sit above the
    process flow (was Submit → Runs → Intake → Decision cards → Review queue → Inbox).
    **Sample accessioning now leads the Steps sub-sequence (2026-07-10, T-117, "Wave 9," G1):**
    accession → submit → runs → intake → decide — the CRM subject-registration step is upstream
    of the wetlab samplesheet, preserving G4's Notification→Action→Steps order rather than
    sitting atop the whole group (see §5.12).
  - **Page-access view-gate (2026-07-10, T-117, "Wave 9," G1).** A second frontend-only
    governance capability, layered over the wire roles exactly like `isAdmin`: `useNav` now
    filters every non-Admin nav item through `useAccess().canSee(page)` and drops any group left
    empty, and `App.tsx` wraps each gated route in `<RequirePage page=…>` →
    `components/PageAccessDenied.tsx`. **This gates VIEWS, not API enforcement** — `api/auth.py`'s
    `require_role` still authorizes every real write, unchanged. See §11 (Page access tab).
  - **Analyze:** Provenance · Agent triage · Monitoring
  - **Configure:** Pipeline builder · Settings
  - **View selectors are `Tabs`, not `FacetChip` (2026-07-10, T-110, "Wave 8," G5).** A new
    canonical underline `components/Tabs.tsx` (`role="tablist"`) is the one "which view am I in"
    idiom, replacing the rounded-full `FacetChip` pills — which read as *highlighted values*, not
    a control — in Runs (status), Review queue (status), Admin (activity-log kind), and RunDetail
    (sample verdict). **`FacetChip.tsx` is deleted**, fully replaced. `SegmentedControl` stays for
    compact toggle *settings* (7d/14d/30d window, theme, density) — the two are now a deliberate,
    documented split, not two components doing the same job.
  - Plus an **Admin** group (`/admin`, off the operator nav — see §11), gated on the login
    identity's `isAdmin`, not on any wire role.
  - **Themeable (Shipped 2026-07-10, T-105, commit `52124d3`, "Wave 7," GA2):** the nav used to
    be dark `#141a21` in both light and dark mode. A new `--color-nav*` var family (`--color-nav`,
    `-hover`, `-active`, `-active-text`, `-border`, `-text`, `-label`) is now LIGHT in the base
    `@theme` (white nav, dark text, an accent-tinted active pill) with the original dark-nav
    values moved into the `:root[data-theme="dark"]` override, so the nav renders light in light
    mode and the unchanged dark nav in dark mode; `Sidebar.tsx` consumes every var end-to-end (no
    hardcoded hex left, except a few whites intentionally kept on colored badges).
- **User panel (nav footer).** Avatar + name → popover: **Role** row (reflects & toggles
  **reviewer/approver** RBAC — the same flag the Review queue and approval flows read),
  **Settings** (opens the Settings dialog), **Sign out**.
- **Top bar — run switcher (Shipped 2026-07-09, T-074, commit `17a3e56`).** The run-context
  pill opens a searchable combobox (filters by run id or platform), capped at 8 rows, with a
  "View all runs · N runs →" footer to the Runs list and an honest "No runs match" empty
  state. The pill's dot and every row's dot read the run's real lifecycle `status`
  (`needs_review`/`running`/`released`) via a shared `RUN_STATUS_META`, never inferred from
  attention count — a running run with 0 flagged samples reads "Sequencing," not a green
  "all clear." A new `NotificationBell` (§5.11) sits beside it, replacing the old dead bell icon.
- **Content:** light surface — **Shipped 2026-07-10 (T-098, commit `5763be1`)**: softened from
  a cool near-white to a warm japandi sand/greige (`--color-page` `#f5f7f9`→`#f2efe7`,
  `--color-card` `#fff`→`#faf9f4`, insets/lines/text warmed to match, contrast kept AA+);
  functional verdict colors, the dark nav, and the blue accent are unchanged. **Reverted
  2026-07-10 (T-105, commit `52124d3`, "Wave 7," GA1)** — the japandi trial "didn't read
  clinical/biotech" per the maintainer; light mode is now a **cool clinical** palette
  (`--color-page #eef1f5`, `--color-card #f9fbfd`, insets/lines/text stepped through cool
  grays), deliberately kept off the pre-Batch-8 glaring pure-white (`#f9fbfd`, not `#fff`);
  functional verdict colors and the blue accent are unchanged. Max-width per screen.
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
- **Error toasts carry the real reason (Shipped 2026-07-10, Wave 4, T-101, commit `f8d9ea0`).**
  Every failed write/read used to throw a bare `${status} ${statusText}` (e.g. a flat "422
  Unprocessable Content"), so every error toast app-wide was equally uninformative. `api.ts`
  gained an `httpError()` helper that reads FastAPI's real error body — a 4xx `HTTPException`'s
  `detail` string, or a 422's `detail: [{msg}]` validation-error array — and includes it in the
  thrown `Error`, so every screen's write toast (Submit, Settings, Pipeline Builder, Review
  queue, Admin) now shows the backend's actual reason. No wire-contract change; pure
  client-side error surfacing.

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
- **Real file parsing, closes the "visual mock" limitation (2026-07-10, Wave 4, T-101, commit
  `1bb79b8`).** The Upload panel previously had no `<input type=file>` and a hardcoded "Parsed 4
  samples" chip — it now parses for real, on drop or Browse. Two formats, tolerantly: an
  **Illumina v2 SampleSheet** (`[Header]` key-values + a `[*_Data]` section — run name/study/
  assay/platform auto-detect from the header) and a **plain CSV**
  (`Sample_ID,Sample_Type,index,index2,Study`); a missing/renamed column degrades to an empty
  cell rather than crashing. The parsed chip only appears after a real parse and shows the actual
  filename, sample count, and detected run/study.
- **`sample_metadata.csv` attach — the LIMS/subject sheet, closes the "no way to submit
  sample_metadata.csv" gap (same commit).** A second "Attach metadata" slot parses
  `Sample_ID,Subject_ID,Tissue`, merges the tissue value into the sample's Sample-type column, and
  shows the subject id under each sample name. **`subject_id` is held client-side only** — a
  labelled seam, not yet sent anywhere: `POST /api/runs`'s `SubmitRunIn`/`SampleIn`
  (`api/routers/intake.py`) carry no subject field and reject unknown ones
  (`extra="forbid"`), so persisting it server-side is the next Submit step, gated by the
  data-platform design's G-PII/G-DEID guardrails
  ([data-platform-and-archivist.md](../data-platform-and-archivist.md)).
- **Scale-aware UI (same commit).** The samples table now paginates 25/page (numbered pager) so
  a 100+ sample mixed flowcell stays navigable, and the submit toast summarizes
  processed/skipped counts (lists up to 5 names, else "N samples") instead of `join()`-ing every
  name into one string. Verified live with a generated 100-sample mixed DNA/RNA sheet + a
  100-row metadata sheet: "Parsed 100 samples," run/study/assay auto-detected, "100 subjects
  mapped" with tissue merged, a 4-page pager, and a no-fixture-sample submission honestly 422s
  with the backend's real message (surfaced by the same commit's `api.ts` `httpError()` fix,
  §4).
- **Bulk-edit rework (Shipped 2026-07-10, "Wave 8," T-111, commit `24fe2e3`, S1-S3).**
  **S1** — the sample-type cell was a click-to-cycle button (read as a "next" control); it's now
  a real `<select>` dropdown. The current value is always an option even when a parsed tissue
  falls outside the controlled `SAMPLE_TYPES` vocabulary (union of the fixed set + the row's own
  value, so an unrecognized tissue from a parsed sheet never silently vanishes). **S2** — per-row
  trash icons are replaced by checkbox multi-select: a leading checkbox column, a header
  select-all with a real `indeterminate` state, selected-row highlight, and a single "Remove N"
  action gated behind a `useConfirm` (danger tone, states "nothing is deleted downstream" —
  draft-only). Selection clears whenever the sample set is replaced (parse or BaseSpace import).
  **S3** — "Add sample" becomes a bounded bulk add: a count input (clamped 1–500) + Add appends N
  blank rows at once, so a 100-sample plate isn't 100 clicks.
- **Accession → Submit handoff (Shipped 2026-07-10, "Wave 9," T-117, commit `66b14e4`, G1).** A
  new upstream **Sample accessioning** screen (§5.12, `/accession`) composes subject/sample
  metadata; its "Send to wetlab intake" writes a one-shot `{subject_id, tissue}` `localStorage`
  courier (`lib/accession.ts`) that Submit now reads on mount (`useEffect` + `readHandoff()`),
  pre-attaching subject metadata and merging tissue into the sample-type column exactly like an
  uploaded `sample_metadata.csv` would — then clears the courier. A footer cross-link ("Subject
  metadata is authored in Sample accessioning") always points there. `subject_id` stays
  client-side only, same seam as the pre-existing `sample_metadata.csv` attach above. `lib/csv.ts`
  now holds the one shared `splitCsv`/`colIndex` implementation both screens' parsers import
  (extracted behavior-identically out of this file).

### 5.2 Runs  (`view: 'overview'`)
Scale-kit list surface:
- **Search** (run id / platform), **status view `Tabs` w/ counts** (All · Needs review ·
  Sequencing · Released — a canonical `Tabs` selector since 2026-07-10, "Wave 8," T-110, G5; was
  `FacetChip` pills), **sort** (Recent · Urgent), and a **date-range** control
  (calendar with From/To fields + presets; fixed-width trigger so digit-count changes don't
  reflow the row).
- **Per-page 25 / 50 / 100** (default 25), scrollable.
- **Run cards:** clean (no left color bar), mono run id, platform · date, N samples + status
  pill, attention chip, and a verdict bar with an **inline count legend**
  (e.g. "19 Proceed · 5 Hold · 2 Rerun · 2 Escalate"); hover lift. Running/released rows omit
  the legend. Seeded with 28 runs incl. a 28-sample `RUN-2026-07-08-WES28`.
- **Shipped 2026-07-10 (T-099, commit `3c6dacb`):** the verdict bar is now capped
  `max-w-[300px]` (was full-row-width) with 2px gaps between segments so adjacent verdict tones
  (hold amber / rerun orange) read as distinct blocks instead of one bleeding gradient.
- **Canonical geometry (Shipped 2026-07-10, "Wave 9," T-116, commit `3e592d8`, G3).** This bar
  (and every other distribution/meter bar in the app) now renders through the shared
  `components/Bar.tsx` — see §9 Tokens for the full consolidation.

### 5.3 Intake gate  (`view: 'intake'`)
Preflight sample-admission review. **Collapsible admission rows** (consistent bar lengths,
room for status + action). Header carries a **Refresh** control + "Updated {time}".
- **Shrunk yield bar + preflight metadata grid (Shipped 2026-07-10, "Wave 8," T-112, commit
  `1052e15`, IG1).** The expanded admission card was sparse (a full-width yield bar + override
  only). (1) The yield bar is capped `max-w-[340px]` (mirroring the Runs verdict-bar convention),
  not a full-card sweep. (2) A preflight metadata grid — **Sample type / Library prep / Origin**
  (lazy-loaded from the per-sample `CardReadout` header **only when a row is expanded** — scale-
  aware, never N+1 for a 100-sample run), plus run-level **Platform / Run date** and the sample's
  **Verdict**. Real fields only, no analyzed/downstream data (preflight-appropriate); a null
  field reads "not captured" (honest, never fabricated), and a pending field shows a skeleton.

### 5.4 Decision cards  (`view: 'decision'`)
Per-sample verdict cards for a run.
- **First card open, rest collapsed**; **Expand all / Collapse all**; verdict view `Tabs`
  (2026-07-10, "Wave 8," T-110, G5; was verdict filter chips).
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
- **Actions now confirm first (Shipped 2026-07-10, "Audit retrofit," T-102, commit `d65c9c1`).**
  A new reusable **`ConfirmDialog`** (`components/ConfirmDialog.tsx`: a `ConfirmProvider`
  mounted at the app root + `useConfirm()`, an async `confirm(opts) → Promise<boolean>`; Escape
  and click-outside both cancel) realizes the maintainer's standing rule that no single
  accidental click may fire a cascading/state-changing write. **Resolve / Escalate / Reopen**
  confirm first, each naming its effect and that it's recorded in the audit log; **Suppress**
  uses a DANGER-toned confirm spelling out the cascade ("future occurrences of \<rule\> across
  runs are hidden until un-suppressed"); the **batch** Resolve/Suppress bar (T-097) confirms the
  selected count. **Acknowledge and un-suppress stay direct one-clicks** — deliberately: they're
  low-stakes and non-destructive (un-suppress only restores visibility; acknowledge is a soft
  "start reviewing"), so gating them too would just be friction without a real accidental-click
  risk. No backend/wire change — every confirmed action still calls the same
  `ticketAction`/`toggleSuppress` path it always did, so it lands in the Admin Activity audit
  feed exactly as before. The same `ConfirmDialog` primitive is reused by Admin's Act-as (§11)
  and is intended for the Settings/variant authoring surfaces ahead.
- **Resolve button now neutral (Shipped 2026-07-10, "Wave 7," T-107, commit `478129d`, "RQ1").**
  The per-ticket and batch "Resolve" buttons were styled with the `proceed-*` (green) token set,
  which read as "already resolved" rather than an action you could still take. Both are now a
  neutral outlined button (`border-line-strong bg-card text-text`, accent on hover) — the only
  primary (blue) action left in the ticket UI is "Acknowledge & review." Styling-only; the
  confirm gate above and the underlying `ticketAction` write are unchanged.
- **Tabs + selection redesign (Shipped 2026-07-10, "Wave 8," T-110, commit `1bc0072`,
  G5/RQ2/RQ3).** The status filter chips (All / Open / Resolved / …) are now the canonical
  `Tabs` component (§4), reading as a view selector rather than highlighted values. **RQ2:** a
  page-scoped global Select all / Clear all sits above the ticket list — scoped to the
  **currently visible page**, not the whole filtered set, so the batch-confirm count is never
  surprising. **RQ3:** the per-ticket selection checkboxes were a floating afterthought; each run
  group is now bound by a `border-l-2` left rail (lights accent when the group has a selection)
  with the subheader select-all and every ticket's checkbox aligned in one fixed gutter on the
  rail — a designed grouping, not a convenience placement.

### 5.6 Provenance  (`view: 'provenance'`)
**Rewritten 2026-07-10 ("Wave 8," T-114, commit `0e64fad`, PV1)** from a single left→right stage
DAG into a thin container over a persistent version-pins band + a `Tabs` (§4) switch of three
views — the maintainer's ask to make provenance ("an important aspect of the project") a
first-class investigative surface. **Needed zero backend change**: `RunDetail.events` (the real
append-only ledger) already shipped to the client and the pre-rewrite screen simply discarded it.
1. **Lineage** — the original left→right stage DAG + per-stage I/O drill-in below, preserved
   verbatim as the default view. Every artifact is a **link** — open in store, copy digest,
   download. Nodes **color by stage status only** (pass/warn); the origin / sample-type chips and
   the header legend were removed (sample type comes from the sample sheet).
   - **Wider cards + a scroll-position indicator (Shipped 2026-07-12, commit `e40784c`).** The
     9-stage lineage chain (the 3 post-variant stages added in W3) overflows the viewport, so the
     stage cards grew (grid column
     `minmax(104px→184px,1fr)`, `components/provenance/Lineage.tsx`) to read well instead of
     crushing, and the old static "Click a stage to inspect its data I/O" hint is replaced by a
     **real scroll indicator**: a `Stage X–Y of N` (or "All N stages in view") range readout +, only
     when the chain actually overflows, a scrollbar-style thumb whose position/width mirror the
     horizontal scroll. Measured from real element geometry (`ResizeObserver` + `onScroll`,
     `data-stage-n` per card), never a verdict/confidence signal — pure chrome, ADR-0001 untouched.
2. **Event trail** (new centerpiece, `components/provenance/EventTrail.tsx`) — a filterable
   (type / sample / actor + free-text search + oldest/newest order), paginated timeline of the
   REAL events emitted by `run_gate`. Expanding a row is the trace-back: `finding.emitted` → its
   cited evidence in place, `verdict.decided` → the decision card + a deep link, else the raw
   payload. The five event types `run_gate` actually emits are honored
   (`analysis_run.started`/`sample.registered`/`finding.emitted`/`verdict.decided`/
   `analysis_run.completed`); anything else the `EventType` enum could carry (e.g. the separate
   notify port's `notification.emitted`) renders generically, only if present — never faked into
   a promised row. 100% read-only: no verdict/confidence set; a finding/verdict shown is quoted
   verbatim from the event the rule engine authored (ADR-0001). Scale-aware: present-only filter
   options + 25/page pagination for a ~500-event run.
3. **Artifacts** (new, `components/provenance/Artifacts.tsx`) — a grouped-by-name artifact index
   (stage·role edge chips, origin, size, fingerprint, download), filterable by stage/origin/role
   — the same "every artifact is a link" affordances from Lineage, indexed instead of DAG-plotted.

Also lands the shared `components/Pager.tsx` (the "Showing X–Y of Z + per-page + prev/next"
idiom, previously duplicated across Runs/Monitoring/Admin/AgentTriage) — the event trail and
artifacts views consume it. A fetch-effect fix: `error` now clears on a runId switch, so jumping
runs via the top switcher never leaves a stale "unknown run" message on screen.

**Pre-rewrite history (still applies within Lineage/Artifacts):**
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
- **Shipped 2026-07-10 (T-099, commit `3c6dacb`):** the digest label reads "**fingerprint**"
  instead of "hash" (continuing T-080's defense-in-depth framing — a content digest is not a
  process/task/ledger id, those are `arun_…`/`evt_…`; the wire field is still `sha256` and its
  value is unchanged) and now shows the full value on hover of the label, in addition to the
  existing "show full" toggle and copy button.

### 5.7 Agent triage  (`view: 'agent'`)
Advisory triage assistant. **Chat composer**: multi-line text window, **Enter** sends,
**Shift+Enter** newline, circular send, suggestion chips, and a **pop-out / minimize**
toggle. Helper line reinforces "advisory · can't change the verdict."
- **Shipped 2026-07-09 (T-078, commit `e3e1995`):** the case selector is now a
  Sample·Verdict·Gate·Headline·Findings table (was a non-scalable pill row), verdict-ranked,
  with the active row highlighted.
- **Shipped 2026-07-10 (T-099, commit `3c6dacb`):** the flagged-samples table now caps at 10
  rows/page + a numbered pager ("Showing X–Y of N flagged") — a large mixed flowcell can flag
  dozens of samples; the active-sample selection persists across pages.
- **System-agent launchers (Shipped 2026-07-12, commit `69a2dab`).** The **Pipeline-repair** and
  **Archivist** advisory agents now launch from here (`AgentLauncher` tiles opening the same
  `PipelineRepairModal` / `ArchivistModal`, moved out of `BuilderModals`' Builder consumers). The
  taxonomy rule: these agents act on **runs / recurring signatures / the whole organization**, not
  on a single pipeline node, so their home is Agent triage — the Pipeline Builder palette now keeps
  only the two **node-scoped** authoring/observation agents (QC-triage, node-attachable; and
  Node-authoring). Each launcher opens a read-only, cited proposal; advisory + off-gate, neither
  sets a verdict (ADR-0001). See §6 "Advisory agents."

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
- **Shipped 2026-07-10 (T-072 frontend half, commit `34bca5d`) — since SUPERSEDED, see below:**
  the throughput card's per-run columns briefly paginated client-side too (25/50/100 + numbered
  pager, "Showing X–Y of N runs"), ported from the recurring-signatures pager pattern. This
  pager was **removed the same day** by the Recharts rework immediately below — kept here only
  as a historical note; do not implement a per-run pager on this chart.
- **Shipped 2026-07-10 (T-100 "Wave 2", commit `f8a6f35`) — Recharts rework, replaces the
  hand-rolled bar chart above.** Adds **recharts 3.9.2 (MIT)** as a new `frontend` dependency —
  the frontend's first real charting library, justified because a hover tooltip + a trend line +
  a stable frozen frame aren't practical to hand-roll without reinventing one (React-19-compatible,
  added at the maintainer's explicit request). The "Verdicts over time" card is now a Recharts
  `ComposedChart`: stacked per-verdict bars + a monotone "Flagged (trend)" line (hold+rerun+
  escalate) + a grounded hover tooltip (the run's real per-verdict counts, never synthesized) +
  dashed gridlines. It is **FROZEN to a ~14-day column frame** (constant per-column slot,
  `maxBarSize`-capped) and **scrolls sideways** beyond it — toggling 7d/14d/30d no longer resizes
  the card (height stays constant; only the plot width + scroll extent grow). **The per-run pager
  above is REMOVED, not narrowed** — per the maintainer, "it scrolls now, so paging the
  throughput columns made no sense"; the recurring-signatures pager is unaffected. Net effect on
  [tasks T-072](../../planning/tasks.md): the chart now renders **every** fetched run as a bar
  with no cap in either direction (no backend `page`/`limit` on `runs[]`, and no frontend
  render-cap either, now that pagination is gone) — an honest, maintainer-directed tradeoff, not
  a regression, but T-072 stays the accurate tracker of the still-open backend-cap gap.
  **Recurring signatures also gain (same commit):** a unique, stable display id per row
  (`SIG-<first 8 chars of the signature hash>`, disambiguating e.g. two PIPE-001 patterns) and a
  **clear-from-view / restore** control — a REVERSIBLE, `localStorage`-persisted, client-only
  view filter (never a DB purge, never an `api/` write) that moves a signature into a
  collapsible "Cleared · N" section; it stays searchable and escalatable there, and restores in
  one click.
- **Slanted DD-MM-YY dates + toggleable trend lines (Shipped 2026-07-10, "Wave 7," T-107, commit
  `478129d`, "M7").** The X-axis dates now slant -35° in **DD-MM-YY** (includes the year; was flat
  MM-DD, which crowded at density) — chart `height` 200→224 and `XAxis height` 46 to seat the
  angled ticks. The single always-on "Flagged (trend)" line becomes **five** toggleable trend
  lines — the four verdicts (proceed/hold/rerun/escalate) plus flagged (the non-proceed total) —
  each colored to match its stacked-bar segment; the old static swatch legend is now clickable
  `aria-pressed` toggle chips (default: flagged ON, the four verdict lines OFF, so the chart isn't
  cluttered on load).

### 5.9 Pipeline builder  (`view: 'builder'`)  — see §6 for the full model
Node-graph editor that **emits `run_layout.yaml`**. Defaults to **View**; **Edit** unlocks
authoring.

### 5.10 Settings  (`view: 'settings'`)
- **Assay dropdown**; **thresholds are assay-specific** (table swaps per assay).
- **Read-only by default** → **Edit thresholds** unlocks fill-in inputs, swapping the bar to
  **Cancel · Save changes**; save is per-assay, **audited** (who · when), guarded (a gate
  can't cross its hard-fail; % clamp 0–100), and **approver-gated**.
- **Agents & model tiering — now a scale-aware table with explicit edit (Shipped 2026-07-10,
  T-103, commit `7b579bb`, "Wave 5," ST1/ST2).** The old 3-item card (dropdowns applied on
  change) is now a TABLE of the full advisory-agent roster — **Agent · Purpose · Model · Status ·
  Edit** — capped 10 rows/page + a pager (the scale-kit pagination pattern, [data-platform-and-
  archivist.md §4.10](../data-platform-and-archivist.md)). Rows: card synthesizer, QC-triage,
  pipeline-repair, archivist, feedback-categorizer, node-author (§6 — **the Python agent core is
  now built, 2026-07-10, T-046**; this row + §6's static modal preview below predate that build
  and were not re-verified by it — see [design/node-authoring-agent.md](../node-authoring-agent.md)
  "What actually shipped"), and a **new metrics-expansion agent** row (ST2 — proposes new QC metrics to track +
  wiring; labelled **phase-2**, no backend agent or `PIPEGUARD_*` env var exists for it yet — this
  is a UI-only placeholder for a proposed idea, **not** a shipped roster addition; see
  [design/agents.md](../agents.md)). Each row shows its real `PIPEGUARD_*_MODEL` env var + model/
  cost + a Stub·$0/Live status; a pencil opens a staged draft (model + live toggle) with explicit
  Save/Cancel — nothing applies until Save (verified: Cancel discards, no leak), one row edits at
  a time. A **"New agent"** button crosslinks to `/builder` (the node-author agent's home) — the
  closest existing authoring surface; a full agent-designer stays a phase-2 seam. **Still
  client-only** — Save updates local React state only, not wired to any backend env or endpoint
  (the T-045 "UI-only" gap stays open; this is a presentation rebuild, not a persistence fix).
  Model tiering remains narration/advice only — verdicts stay rule-derived (ADR-0001). **ST2 part
  1** (runbook thresholds bound to assay × sample type) was independently verified **already
  correct** in `SettingsAssayTable.tsx` — per-assay rows, per-sample-type columns, save keyed by
  the assay slug; no change needed.
- **Sample-type dropdown (Shipped 2026-07-10, T-095, commit `869cf55`).** The threshold matrix
  showed Whole-blood and Saliva as two side-by-side columns; a Sample-type dropdown beside the
  Assay selector now picks one tissue at a time and the table shows a single value column,
  cleaner and scaling as more sample types are added. Editing/save/approve, the per-tissue
  values, and the audit lifecycle are unchanged (still keyed on assay × sample type).
- **Notifications:** Slack, Microsoft Teams, Discord.
- **Settings dialog** (from the user panel): profile (name / email / role / time zone) +
  preferences (theme, density, email digest, desktop notifications), Cancel / Save.

### 5.11 Inbox  (`view: 'inbox'`) — Shipped 2026-07-10, T-108, commit `d832553`, "Wave 7," GA3
**Brand new**, not part of the original design pass above — added at the maintainer's request to
replace the dead top-bar bell and give an operator an intentional way to organize what needs
doing ("a scrolling list isn't enough, users get lost, changing pages loses their place, no way
to flag/unflag"). Entirely **off the decision gate**, like the in-app feedback widget: it never
sets or reads a verdict, finding, or confidence, and it requires **no new backend endpoint** —
notifications are DERIVED, client-side, from the already-off-gate review queue's
`api.listTickets({status: 'open'|'in_review'})` (escalate/rerun/hold tickets, §5.5).

- **State (`context/InboxContext.tsx`).** The user's overlay on each item — read/unread, flag,
  priority, kanban column, due date, a note, **and (added 2026-07-10, "Wave 8," T-113) a folder**
  — plus any self-authored reminders, is stored in `localStorage` **scoped per operator** (keyed
  by `actor.id`; re-read whenever the acting identity changes, including Admin's "Act as," §11 —
  so a re-fetch never clobbers triage and a page change never loses it). `unreadCount` excludes
  the `done` kanban column (the archive) and drives both the Sidebar badge and the top-bar bell
  badge from the same context, so they can never drift apart.
- **Four tabs:**
  1. **Inbox** — a filterable stream (All / Unread / Flagged); each row expands to
     priority / board-column / due-date / note-to-self / "open in queue." **Mark all unread**
     (2026-07-10, T-113, IB2) sits alongside the existing "Mark all read."
  2. **Board** — a 4-column kanban (Inbox / To do / In progress / Done) with native
     drag-and-drop; moving a card marks it read and drops it from the unread count.
  3. **Calendar** — a month grid dotting due dates + a day-detail panel + an "add reminder"
     composer. **(2026-07-10, T-113, IB3)** the composer button drops the redundant date suffix
     ("Add for 07-10" → "Add reminder"); the selected day is implied by the composer subtitle (a
     friendly Weekday, Mon D). **Google/Outlook Calendar connectors are labelled phase-2 seams**
     (2026-07-10, T-113, IB1) — clicking one toasts the honest "not connected" status; there is
     no real OAuth flow.
  4. **Notes** — a note-to-self composer + inline-editable notes on any item. **Reworked
     2026-07-10 (T-113, IB5-8):** notes are now **read-only until Edit is clicked** (was a live
     always-editable textarea, gating accidental edits/deletes); each note shows "Created {ago}"
     and, once modified, "· edited {ago}" (IB6, `updatedAt` set on an explicit save); delete
     moves inside edit mode (confirmed) plus a checkbox multi-select + a confirmed "Delete N"
     mass delete (self notes only — ticket annotations aren't deletable here, IB7); and a
     **folder system** (IB8) — an add/delete folder manager (deleting a folder keeps its notes,
     moving them to Unfiled, never orphaning one), a folder select on the composer + a per-note
     "move to folder," and a folder filter over the list; renaming/deleting a folder re-points
     every filed item.
- **Top-bar bell (`components/NotificationBell.tsx`).** A quick-glance dropdown, deliberately
  distinct from the full workspace: recent items (unread-first), inline flag / mark-read, "Mark
  all read," "Open inbox →." Reads the same shared context as the workspace, so what you set here
  waits for you in Inbox.
- **Shared visual tokens (`inbox.ts`)** — source/priority/column/due-status meta, `timeAgo`,
  `dueStatus` — kept out of the `.tsx` files so a fast-refresh edit to a component never churns
  them, and the bell + workspace read identically. `dueStatus`/`todayYmd` deliberately use
  **local** `yyyy-mm-dd` (not `toISOString()`, which is UTC) so a reminder due "today" never
  reads as overdue across a UTC-date rollover.
- **Deferred: IB4** (per-reminder Slack/Discord/Teams/email notification + cadence, ≤3
  instances) — the largest remaining Inbox item, explicitly not part of the 2026-07-10 ("Wave
  8," T-113) pass. No notification-channel code exists yet; tracked in
  [tasks.md T-113](../../planning/tasks.md).
- **Distinct from the outbound `notify/` port** (ADR-0010, Slack/Teams/Discord, §6 of
  [architecture.md](../../design/architecture.md)) — that is a server-side push to an *external*
  channel triggered by `run_gate`; Inbox is a client-only, per-operator organization layer over
  data already visible in the Review queue, and never leaves the browser.
- **Honest limitation:** per-browser `localStorage` state, not synced across devices — clearing
  site data or switching machines loses an operator's triage/board/reminders, the same class of
  limitation as `PrefsContext` (§4, T-091) and the Monitoring clear/restore-signatures filter
  (§5.8, T-100).
- Verified live (light + dark): all four tabs, drag-and-drop moves a card and updates every
  badge, a calendar reminder lands as "Due today," bell-dropdown triage, no console errors. tsc +
  oxlint clean.

### 5.12 Sample accessioning  (`/accession`) — Shipped 2026-07-10, T-117, commit `66b14e4`, "Wave 9," G1
**Brand new**, not part of the original design pass above — added at the maintainer's request to
give `sample_metadata.csv` (subject/sample accessioning, the CRM step) its own screen distinct
from `SampleSheet.csv` (the wetlab samplesheet, §5.1). Sits **upstream** of Submit in the
Operate "Steps" order (§4): accession → submit → runs → intake → decide. Composes an
`AccessionRecord[]` and hands it off — it **never runs a tool** (compose ≠ execute).

- **Compose.** Drop a `sample_metadata.csv` (`parseAccessionCsv`, tolerant — a missing/renamed
  column degrades to an empty cell, never a crash, the same boundary discipline as Submit's
  parser) or add subjects by hand (bounded 1–500 at a time). A controlled table — Subject ID ·
  Sample ID · Tissue (dropdown, mirrors Submit's sample-type vocabulary) · Sex · Consent ·
  Collected-on · Accession # · Site/study · Notes — with a leading checkbox column, header
  select-all (real `indeterminate` state), and a confirmed "Remove N" (`useConfirm`, danger
  tone). Paginated via the shared `Pager` (§5.6).
- **PII/PHI seam banner (prominent, honest).** "Subject identifiers stay in your browser" — every
  field on this screen is **client-side only**; nothing is transmitted. The banner names the
  concrete guard: `POST /api/runs` (`api/routers/intake.py`'s `SubmitRunIn`/`SampleIn`) carries no
  subject field and is `extra="forbid"`, so it would reject one — real subject/PII persistence is
  gated behind the data-platform PII/de-identification design (a labelled, not-yet-built seam;
  [nonfunctional.md REQ-NF-023](../../requirements/nonfunctional.md)). **DOB and MRN are
  deliberately not collected** (PHI) — only lab-operational fields (collection date, accession #,
  site) exist, and even those never leave the browser.
- **Actions.** Export CSV (`toAccessionCsv`, round-trips through the parser, defaults to
  `sample_metadata.csv`); Save draft (`localStorage`, survives a refresh); **Send to wetlab
  intake** (behind `useConfirm`) → stashes a one-shot `{subject_id, tissue}` `localStorage`
  handoff that Submit (§5.1) reads on mount and pre-attaches, then clears.
- **Shared with Submit:** `lib/csv.ts` (`splitCsv`/`colIndex`/`csvCell`) — extracted
  behavior-identically out of `Submit.tsx` so both screens' parsers share one tolerant
  implementation instead of each minting its own.
- **Access-gated:** like every other operator page, `/accession` is wrapped in
  `<RequirePage page="accession">` (§11, Page access tab) — visible by default to every seeded
  demo account's access profile except the narrowest ones, per `access.ts`'s `ACCESS_PROFILES`.
- Verified in-browser: PII banner, upload/manual-add, export, save-draft, send-to-intake handoff
  landing in Submit with a toast. tsc --noEmit + tsc -b + oxlint clean; no backend touched.

---

## 6. Pipeline builder — full model

**Modes.** Defaults to **View** (read-only: palette tiles disabled, add guarded, "Author a
tool node" replaced by a read-only note). **Edit** enables all authoring. **Exception (Shipped
2026-07-10, T-099, commit `3c6dacb`):** the advisory-agent palette tiles are `alwaysEnabled` —
clickable in **View** too, since each only opens a read-only advisory modal/pill and never mutates
the graph, letting an operator consult an agent without switching the whole canvas into Edit.
Node-adding (tool/reference) tiles still require Edit. **Taxonomy narrowed 2026-07-12 (commit
`69a2dab`):** the palette's advisory-agent tiles are now only **QC-triage** (node-attachable) and
**Node-authoring** — **Pipeline-repair and Archivist moved OUT** to Agent-triage launchers (§5.7),
because they operate on runs/signatures/the organization, not on a single graph node.

**Toolbar — consolidated into a compose bar + overflow (Shipped 2026-07-11, commits
`4df8f2e`→`3d531de`, [journal](../../journal/2026-07-11-builder-boundary-and-edges.md)).** The
prior two-row toolbar (~14 flat controls, plus a duplicated run-identity strip) is now one row:
mode toggle · New · Open · Cancel (draft-only) · doc name · a **state-only** lock/draft pill (no
longer repeats the run id) · a compact `v{version} · status · Approve (approver + pending-only) ·
role toggle` cluster · the profile combobox · a divider · the **primary compose flow — Save ·
Validate · Emit** (Emit stays the accent-primary action) · a new **"⋯ More"** overflow: Export to
Nextflow and Run hand-off (always available), plus — **linked view only** — Fork to new draft,
Open Provenance, Open Decision cards, and (2026-07-11, `3d531de`) **Decision boundary** (see
Nodes below). Every handler/destination is byte-identical to before; only layout/grouping
changed. The **linked-run strip** below is now the single home of the run identity (`Linked to
{run}`, shown once, was duplicated with the status pill). Editable **wires now stroke by the
source port's data `kind`** (`kindColor`, the same fastq-violet/bam-blue/vcf-teal/reference/
QC-gold family the seeded wires and port borders already used) instead of a flat accent, so a
composed edge's data type reads at a glance; the advisory agent→tool dotted edges stay a
visually distinct dashed accent (never a data kind) — data vs advisory stays legible (ADR-0001).

**Edge clarity (Shipped 2026-07-11, commit `a03704f`).** Two layout-only passes over the
typed-port graph — the graph model (`ins`/`outs`/`idx`) and the save contract are untouched.
(1) **Split multi-connection ports:** any port wired to N cards now splits into N laid sub-ports,
one per edge, each independently nearest-side-anchored at its own target
(`BuilderCanvas.anchorForEdge(id, dir, idx, eid)`), so two edges leaving/entering the same
logical port never share an endpoint (verified in the live DOM: 18 wires → 36 unique endpoints);
split halves still group back into one numbered box row (e.g. `bam · out · [4][5]`). (2) An
offline occlusion scorer (coordinate descent over the real wire polyline) found one minimal
move — the Panel BED reference card's x-position, 800→1150 — that cleared 3 of 7 wires-routed-
behind-a-card occlusions; the residual 4 are inherent long-reach fan-in/fan-out wires
(fastp→MultiQC, reference_fasta fan-out), left honest rather than force-routed (a real
constraint router is future work, not attempted here).

**Legend accuracy (Shipped 2026-07-12, commit `e40784c`).** `BuilderLegend.tsx` was corrected on
two counts: (1) the **reserved** port-state swatch now samples the SAME alignment hue as
required/optional (only fill/border-style differ — dashed-hollow in its kind colour), matching how
reserved ports actually render on the cards, instead of drifting to the config hue and reading as a
separate scale; (2) the **Wires** legend gains a fourth row — **`advisory · off-gate`**, a dotted
accent line — so the real, distinct advisory agent→tool edge type (dotted accent, never a data
kind; ADR-0001) the legend had been omitting is now shown alongside the solid data wires, the solid
QC fan-in, and the dashed reference feed.

**Canvas.** Large, pannable in any direction; loads centered on the pipeline. Dot-grid = 20px
snap grid — **theme-aware since 2026-07-10 (T-098, commit `5763be1`)** via a new `--canvas-dot`
CSS var (cool+subtle in light — reverted from a warm japandi trial 2026-07-10, T-105, "Wave 7,"
see §4 — dim `rgba(150,165,185,.08)` in dark, was a hardcoded light hex that read as distracting
on the dark canvas). **T-098 also briefly moved the grid onto the scroll surface itself so it
would span the entire canvas including the margin gutters, not just the content plane — this
caused a visible double-grid regression** (the content plane kept painting its own copy too, so a
static dot layer visibly slid over a moving one) **and was reverted the same day (2026-07-10,
T-106, commit `eab5ff2`, "Wave 7," "PB3"): a SINGLE grid now lives on the content plane only,
so it pans/zooms WITH the pipeline** (the grid still doesn't cover the margin gutters — that
"spans the entire canvas" framing no longer applies). Top-right **minimap** (spine + gate + composed nodes — moved from bottom-right
2026-07-10, T-085, commit `14c9f3c`, so it no longer sits under the feedback bubble) — **grown to
a 210×108 proportional mirror** (was 168×46), 2026-07-10, T-084, and (2026-07-10, T-106, commit
`eab5ff2`, "PB3") now draws a **tracking viewport rectangle** showing where the scroll viewport
currently sits on the canvas (`updateVp()` maps scroll position → inner canvas coords, the same
360/480-margin + zoom convention `fitToDag` uses, → minimap pixels; recomputed on scroll/Fit/
mount/zoom-change, clamped into the minimap box) — previously the minimap mirrored node positions
with no indicator of where you were looking. Floating zoom + **Tidy**
(auto-layout) + **Connect** controls, plus (2026-07-10, T-084) a native ctrl-wheel/trackpad-pinch
zoom on the canvas itself (`{ passive: false }`, since React's `onWheel` can't `preventDefault`;
plain wheel still pans; clamped 0.6–1.4), and **Fit** now centers/zooms to the pipeline's actual
bounding box instead of only resetting the zoom level. **Tidy is flow-preserving** (2026-07-10,
T-085): each node lands in the column of its longest-path depth from a source
(upstream→downstream reads left→right, parallel nodes stacked in a column) instead of dropping
every card into one row and losing the connection structure. A **Cancel** button (shown only
while composing a draft) discards the in-progress build and returns to the linked pipeline in
View.

**On-canvas editing (Shipped 2026-07-10, "Wave 8," T-115, commit `109557e`, PB2, P1-P7).** Raises
the builder from "works" to "fluid to edit on the canvas." All work is over the local
`userNodes`/`userEdges`/`locEdits` draft — compose ≠ execute holds, dry-run/diff and the gate are
untouched.
- **P1 — selection + inspector + rename.** Click a node for a selection ring + a
  `UserNodeInspector` (name/icon/typed-port/locator/delete); double-click for inline rename.
- **P2 — wire deletion.** Click a wire (hit-path select) or its midpoint × to delete it.
- **P3 — undo/redo** (`hooks/useTopologyHistory.ts`, a bounded 50-entry ring) + toolbar buttons +
  keyboard (Delete/Esc/⌘Z/⌘⇧Z/⌘A/⌘D/arrows/c/f, guarded off inputs and off View mode). **Scope:
  topology only** — `locEdits`/`refLoc` (locator/reference authoring) are **not yet undoable**, a
  labelled limitation, not a bug (extending it needs a state-consolidation refactor).
- **P4 — marquee + group actions.** Shift/⌘-click or drag a marquee for multi-select, group move,
  and a `SelectionActionBar` (align/distribute/duplicate/delete).
- **P5 — context menus** (`BuilderContextMenu.tsx`) on a node, an edge, or the empty canvas.
- **P6 — live alignment guides + snap** while dragging.
- **P7 — drag-to-connect** from an output port directly to an input port (same typed/dedup
  validation as click-arm-click Connect mode).
- **Anti-cascade** (the maintainer's standing "no accidental single-click cascade" rule): any
  delete that severs ≥1 edge, or any multi-node delete, routes through `useConfirm` (danger tone,
  names the wire count) — an isolated node with no wires stays one-click. Every delete emits a
  "⌘Z to undo" toast, so all deletes are reversible. (The design spec's looser "≥2 edges"
  threshold was **not** shipped — the actual behavior is stricter/safer than spec.)
- **Fix:** a module-init temporal-dead-zone crash — `BuilderShared`'s `ARTIFACT_KINDS` read
  `GIAB_LOC` before its declaration, which `tsc` didn't flag but blanked the app at runtime — was
  resolved by reordering the two declarations.
- **`components/Truncate.tsx`** (a full-text-on-hover primitive, "G2") **was added this batch with
  no call sites yet anywhere in `frontend/src`** besides its own definition — shipped, not yet
  applied to any overflow-prone label (run ids, sample names, artifact paths). **Applied for the
  first time 2026-07-10 ("Wave 9," T-116, commit `3e592d8`)** — to the decision-card headline in
  `RunDetail.tsx` (§5.4) — but a broader sweep of the other truncated card strings remains
  explicitly **open**, not silently dropped; see [tasks.md T-116](../../planning/tasks.md).

**Nodes.** Two kinds on canvas — `tool`, `agent` — **since `gate` was removed from the canvas
2026-07-11** (see above; it is no longer a placeable/selectable node kind in the Builder, only
content inside the read-only Decision-boundary view).
- **Seeded germline chain** (fastp → bwa-mem2 → samtools markdup → {mosdepth, bcftools call →
  bcftools norm} → MultiQC) + reference nodes (genome / panel BED / truth VCF) + the QC-triage
  agent. **Tool I/O corrected 2026-07-10 (T-083, commit `d8c1625`)** against
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
  **Larger cards, four-sided ports (2026-07-11, UIC-16, commit `12a9913`):** cards grew from a
  fixed 168/208px chip to `NODE_W = 232` and ports now sit on **all four sides**, not just
  left/right — `BuilderShared.portSide(kind, dir)` places reference/panel inputs on **top** and
  QC/metric outputs on **bottom** (matching [builder-cards/README.md §2](../builder-cards/README.md#2-port-placement-convention)),
  while the primary sample-data lane keeps its left-in/right-out flow. Render and wire-endpoint
  math share one `layoutPorts()` call, so a wire can never detach from its port when a card's port
  count changes. `PipelineBuilder.tsx`/`BuilderInspector.tsx` and the on-canvas
  editing (align/distribute/undo, §"On-canvas editing" above) are untouched — only card geometry
  and port placement changed, not connection semantics.
- **Reserved-port render honesty (Shipped 2026-07-12, commit `e40784c`).** A **reserved** port is
  documented but has no runnable Nextflow channel yet, so it stays **non-connectable by design** (no
  `data-*`, no handlers — drag-to-connect's `elementFromPoint` and click-arm both ignore it). Rather
  than render it identically to a wireable port and let it silently fail, it is drawn **dashed /
  hollow** (`portVisualStyle`, its own kind colour) and, in **Connect mode**, becomes hoverable with
  a **not-allowed cursor + a "why it won't connect" tooltip** (`{kind} · {dir} — reserved: not
  wireable (no runnable Nextflow channel yet)`), so a user is never misled that it's armable.
  Edge-less ports also sort **clear of the wired band** so they don't crowd the active ports. (This
  replaces the earlier "reserved kinds are invisible" behavior — a reserved affordance is now shown
  honestly, not hidden.)
- **Reserved→real port cleanup (Shipped 2026-07-12, commit `1621e3f`).** Every *shown* Builder port
  now maps to a REAL Nextflow channel or was removed — no superficial slots. **Promoted
  reserved→optional** (each a real published output now in the compiler catalog): fastp
  `unpaired_fastq` (`--unpaired1/2`) + `failed_fastq` (`--failed_out`), bcftools-norm `vcf_index`
  (the `.csi` its index step already writes), MultiQC `multiqc_html` (`multiqc_report.html`).
  **Removed as non-real** (never a connectable file channel): bwa-mem2 `read_group` (a computed
  `@RG` *string*, not a file), mosdepth `per_base` (suppressed by `--no-per-base`), bcftools-norm
  `panel_bed` (norm is genome-wide), and the MultiQC `fastqc_zip`/`bcftools_stats`/`picard_hsmetrics`/
  `ngscheckmate` inputs (no catalogued tool produces them; MultiQC's inputs are fixed by its
  `ProcessSpec`). **The one genuinely-reserved port left is fastp `adapter_fasta`** — a real
  `--adapter_fasta` input held reserved only because the compiler's exact/positional input-drift
  guard would force every fastp node (incl. the seeded golden chain) to wire an adapter source; too
  invasive for this pass, kept non-armable with the tooltip above. See
  [builder-cards/README.md §5](../builder-cards/README.md#5-open--todo--spec-vs-shipped-updated-2026-07-11).
- **Deterministic ingest + gate moved OFF the canvas (Shipped 2026-07-11, commit `3d531de`,
  [journal](../../journal/2026-07-11-builder-boundary-and-edges.md), [ADR-0001](../../adr/ADR-0001-deterministic-gate-advisory-ai.md)
  Realized §3).** An intermediate pass the same day (`73b2a68`) first made the ingest/gate cards
  **movable** like tool cards (still canvas-local state, never the graph); the maintainer's
  follow-up synthesis was that a fixed boundary card still implies a false peer relationship with
  what an operator actually composes, and eats canvas real estate. Both cards — and the hardcoded
  dotted terminal tethers that used to connect them (norm→ingest, MultiQC→ingest, ingest→gate) —
  are now **removed from the canvas entirely** (node count 15→13). The deterministic
  ingest→gate→verdict handoff is instead a new read-only view,
  **`components/DecisionBoundaryModal.tsx`** (Composed pipeline → Deterministic ingest →
  Decision gate → Verdict, with the three preflight/qc/variant checkpoint dots — category
  colors, never the verdict palette — and copy stating "rules decide; not part of what you
  compose"), opened from the toolbar's **"⋯ More" → Decision boundary** item (always available,
  not linked-view-gated, since it is static explanatory content). It still reads the frozen five
  `run/` CSVs, not raw tool edges — that fact didn't change, only where it's shown. Both
  remaining gate-verdict bars (the linked-run strip's color bar + counts, and the old gate
  card's own segment bar) were removed the same day (`4d4823d`) — **the Builder now shows no
  verdict palette anywhere**; only the rule engine's own surfaces (Decision cards, Provenance)
  render a verdict. `Save`/`Emit`/`POST /api/pipelines/compile` still serialize only
  `{nodes: userNodes, edges: userEdges}` — the gate/ingest/agent canvas positions were never
  part of that payload, before or after this change.
- The **advisory agent stays on the canvas** — movable (canvas-local position, never the graph)
  and, since `4d4823d`, its tool-attach/detach is **edit-only**: in Edit every eligible tool
  shows a corner attach badge (filled when attached, dashed when available); in View the badge
  becomes a read-only indicator, rendered **only** for already-attached tools (no handler; a
  press falls through to card-select) — so a View operator sees the wiring without an inert
  clickable badge on every card. **Agents are port-less** (off the critical path).
- **Agent attachment is now a persisted OBSERVATION BINDING with a grant popover (Shipped
  2026-07-12, commit `69a2dab`).** The earlier ephemeral canvas-local `advisoryAttach: Set<string>`
  is replaced by a typed, persisted `AgentBinding { agent, node, grants }` (`types.ts`) stored in a
  **sibling save-envelope key** `graph.agent_bindings` (alongside locators). **The compiler NEVER
  dereferences it** — the compile/run payload stays `{nodes.map(toCompileNode), edges}` and
  `CompileRequest` is `extra=ignore`, so the emitted Nextflow is **byte-identical with or without any
  binding** (compose ≠ execute by construction; ADR-0001 — an attachment structurally cannot touch
  the pipeline or a verdict). Clicking a node's advisory badge opens a **grant popover** (canvas-plane
  sibling at the badge, so it pans/zooms with the card): toggles for the two observation **grants**
  plus **Detach**. Grants: **`outputs`** (default, on) = the node's published output artifacts;
  **`logs`** (opt-in, **off** by default) = the node's `.command.log`/`.err`, which carry subject-id
  PII and so are **de-identified + never seeded on by default** (PII guardrail). `defaultBindings()`
  seeds QC-triage over its default QC nodes granting `outputs` only; `reconcileBindings()` prunes any
  binding whose node was deleted or whose agent isn't attachable, normalising a foreign/older envelope
  to the known grant vocabulary (never resurrects a missing node). Only **QC-triage** is
  node-attachable today (the `ATTACHABLE_AGENT_IDS` set); the system agents (Pipeline-repair,
  Archivist) act on runs/signatures/orgs and live on Agent triage instead (§5.7). *(The backend
  agent-READ path that consumes these grants is a separate, later slice — see the other agent's
  design/API docs; this doc covers the authoring surface only.)*

**Inspector (right panel).** Tabs **Params · Locators · I/O · Agents**:
- **Header controls: Hide (rail) vs Close (Shipped 2026-07-12, commit `e40784c`).** The panel
  header now carries **two** distinct affordances (mirroring the left palette's collapse): a
  **Hide** chevron (points toward the panel's own right edge) that **collapses the inspector to a
  rail and stays collapsed across card selections** until the user explicitly reopens it — selecting
  another card while hidden must NOT reopen it — and the existing **Close (×)** that clears the
  selection. Hide keeps the selection; Close drops it.
- **Footer action row: `[Delete node] [Save]` (Shipped 2026-07-12, commit `e40784c` → renamed
  `7c5c073`).** In Edit, an editable subject (user node / tool / reference — never a gate/agent)
  shows one bottom action row: **Delete node** (user nodes only; tools/references aren't deletable)
  beside a flex-grow **Save** (renamed from **"Save card"** in `7c5c073`). This card-scoped Save
  commits THIS card's edits into the draft — distinct from the toolbar Save that persists the whole
  pipeline as a new version. Behavior (`onSaveCard`/`onDeleteNode`, edit-vs-view gating) is
  unchanged; only the layout moved Delete out of the node body and into the footer beside Save.
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

**Node-authoring agent** ("Author a tool node"). This section describes the ORIGINAL modal design
(drop tool docs `--help`/`nextflow_schema.json` → an editable `ToolNode` preview) — preserved as
originally written below (`still a static preview, unwired to any backend`, `retrieval over a
fixed 11-card curated corpus`), but **both of those framings are now stale — read this box first.**
What's new (2026-07-10, T-046): the agent's Python core is now built
(`src/pipeguard/node_author/`), and it is a **different, narrower mechanism** than this modal
originally assumed — retrieval over a curated corpus from a natural-language request, not a
doc-drop parser. **Superseded 2026-07-11 (W2, T-127):** a read-only `GET /api/builder/node-proposal`
endpoint now exists and `AuthorToolNodeModal` renders the REAL proposal — it is no longer a static,
unwired preview (see [design/frontend/README.md §6](#6-pipeline-builder--full-model) node-author
paragraph elsewhere for the wired behavior, and [design/agent-authoring-contract.md](../agent-authoring-contract.md)
for the full read/accept API). **Corrected: the corpus is 9 cards**, not 11 — the unwired Truth VCF
reference-node card was retired (11→10; its concept is now a generic "File input" Builder card),
then NGSCheckMate was retired-but-pinned from the proposable corpus (10→9, its card commented out so
the loader skips it while the `ngscheckmate` KIND stays in the vocabulary); see
[design/node-authoring-agent.md](../node-authoring-agent.md) item 7 and
[ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md). This modal's own original
design prose is unchanged below; see [design/node-authoring-agent.md](../node-authoring-agent.md)
"What actually shipped" for the grounded comparison and [tasks T-046](../../planning/tasks.md) for
status.

**Advisory agents (relocated to Agent triage 2026-07-12, commit `69a2dab` — see §5.7).**
**Pipeline-repair** (proposes fixes for recurring signatures) and **Archivist** (proposes
cold-storage of released `run/` dirs) — both stub-first, human-approved, off the critical path;
never edit the pipeline or a verdict. **They no longer launch from the Builder palette** (they act
on runs/signatures/the organization, not a single graph node); their `PipelineRepairModal` /
`ArchivistModal` now open from **Agent triage** launcher tiles. The wired-to-real-data behavior
below is unchanged — only the launch surface moved. **Wired to real data (Shipped
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
`0 1px 2px rgba(16,24,40,.05)`. **Light neutrals warmed to a japandi sand/greige palette
(Shipped 2026-07-10, T-098, commit `5763be1`), then REVERTED to a cool clinical palette the same
day (T-105, commit `52124d3`, "Wave 7," GA1 — the maintainer's call that japandi "didn't read
clinical/biotech")** — see §4 App shell for the exact hex deltas; contrast preserved,
verdict/gate/severity/accent families untouched throughout both changes. The app's actual CSS
variable names are `--color-page`/`--color-card`/`--color-card-2`/`--color-card-3`/
`--color-line`/`--color-line-strong`/`--color-text`/`--color-text-2`/`--color-text-3` (the
`--bg`/`--surface`/`--border`/`--text` family above is this design doc's shorthand naming, not
the app's literal token names — read `frontend/src/index.css` `@theme` for the ground truth). A
new theme-aware `--canvas-dot` token (cool+subtle in light as of the revert, dim
`rgba(150,165,185,.08)` in dark) now drives the Pipeline-Builder canvas dot grid (§6 Canvas). The
left **nav** is also now themeable (`--color-nav*`, §4 App shell, T-105) — previously dark in
both modes.

**Canonical Bar component (Shipped 2026-07-10, "Wave 9," T-116, commit `3e592d8`, G3).** Before
this, the app carried three bar heights (`h-2`/`h-[11px]`), two corner radii (5/6px), and two
segment-gap sizes across its distribution/meter bars. `components/Bar.tsx` now provides the ONE
geometry (`h-2 · rounded-[5px]`, 2px segment gaps) every bar in the app renders through: **
`SegmentBar`** (a proportional multi-segment distribution; zero-value segments drop out so a
strip never lies about the mix) backs the Runs verdict bar (§5.2), the Decision-cards
`DecisionVerdictBar` (§5.4), and the Review-queue `ReviewStatusBar` (§5.5); **`MeterBar`** (a
single value against a track) backs the Intake yield bar (§5.3) and the Monitoring gate-pass bars
(§5.8). Colors are passed as full Tailwind utility classes (not interpolated) so the compiler
emits them and theming holds in both light and dark.

## 10. Files
- `PipeGuard.html` — complete self-contained prototype (open in a browser).
- `source/PipeGuard.dc.html` — annotated source (all data + handlers).
- `source/support.js` — prototype runtime (reference only; do not port).
- `briefs/review-to-design-brief.md` — authoritative product brief.

Suggested repo drop: `docs/design/frontend/handoffs/` — point Claude Code here to implement
against `frontend/src/`.

**Type-check on push (Shipped 2026-07-12, commit `e40784c`).** The frontend now type-checks on
`git push` via a `frontend-tsc` **pre-push** hook running `tsc -b` in `frontend/` (same
heavy-check-on-push cadence as the `pytest` push hook). This closes a real gap: the root
`tsconfig` is references-only, so the old `tsc --noEmit` was a **no-op** and nothing actually ran
`tsc -b` — which is how a type error once reached `main` uncaught. The push now fails on any
frontend type error.

---

## 11. Admin (`/admin`) — governance, off the operator nav

**Shipped 2026-07-09 (T-066, commit `ce396f7`); gating corrected 2026-07-10 (T-081, commit
`0f7e85f`).** Not part of the original design pass above (added during the maintainer-feedback
batch); tracked here because it shares the login/RBAC surface §4 now fronts. A screen at `/admin`,
visible only when the LOGGED-IN identity's `isAdmin` is true (a frontend-only governance
capability layered over viewer/reviewer/approver — an admin is an approver who also holds
governance; **not** "any approver," which was the original, now-corrected framing). Four tabs
(a fourth, **Page access**, added 2026-07-10, "Wave 9," T-117 — see 11.2 below):

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
   **Upgraded 2026-07-10 (T-102, commit `d65c9c1`):** Act-as's confirm now uses the same
   reusable, branded **`ConfirmDialog`** the review queue adopted (§5.5) instead of the earlier
   native `window.confirm` — a UI-consistency change only; the confirmation copy and the
   admin-panel gating are unchanged. **Extended reach (2026-07-10, T-108, "Wave 7"):** "Act as"
   now also swaps which operator's **Inbox** (§5.11) is visible — `InboxContext` re-reads its
   `localStorage` overlay keyed on `actor.id` whenever the acting identity changes, so impersonating
   a user shows their real triage/board/reminders, not a shared one.
2. **Page access** (`components/AccessEditor.tsx`, new 2026-07-10, "Wave 9," T-117, commit
   `66b14e4`, G1) — assigns the client-side page-access view-gate (§4, §5.12) per user. A
   paginated (`Pager`) roster of the demo accounts; selecting one opens a staged **draft**: profile
   checkboxes (the 6 read-only `ACCESS_PROFILES` — accessioning/wetlab/analysis/review/approval/
   governance) plus a tri-state **Inherit/Allow/Deny** override select per individual page, with a
   live effective-nav preview computed from the draft before it's saved. Nothing applies until
   **Save** (behind `useConfirm`); a **Reset to defaults** restores the seeded `DEFAULT_ACCESS`
   map; a master **Enforcement On/Off** switch is the escape hatch (off shows every page to
   everyone). A persistent `ViewGateBanner` states, in the editor itself: **"Page access gates
   VIEWS, not API enforcement"** — the API still authorizes every write by wire role
   (`api/auth.py`, untouched); a production build would need to enforce page/read access
   server-side too (a labelled seam). Every save appends a client-side `AccessAuditEntry`
   (`localStorage`, no backend) that surfaces in the Activity log below, badged "client-side."
3. **Activity log** — a REAL, zero-new-backend audit feed merging `GET /api/settings/thresholds`
   + `GET /api/pipelines` + `GET /api/review/tickets` into one append-only when/actor/kind/target/
   status table, filterable by kind via a **`Tabs`** view selector (2026-07-10, "Wave 8," T-110,
   G5; was `FacetChip` pills). **Shipped 2026-07-10 (T-093, commit `8a14661`, "A2"):**
   the feed now paginates (25/50/100 + a numbered pager, "Showing X–Y of Z," resets on filter
   change — was a flat, uncapped list that got messy as it grew) and each row is a compact
   summary that expands on click to a labelled Detail/Target/Actor/When panel (one open at a
   time); no backend change. **Extended 2026-07-10 ("Wave 9," T-117):** a fourth `FeedKind`,
   `access`, merges in the client-side page-access audit trail above (§11, item 2) — each row carries a
   "client-side" badge so the append-only backend-persisted rows (threshold/pipeline/ticket) are
   never confused with the localStorage-only access-governance ones.
4. **System** — REAL reads of `GET /api/health` + the runbook's gate count + the metric-registry
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
