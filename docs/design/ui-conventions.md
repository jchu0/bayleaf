# UI & Product Conventions

| Field | Value |
|---|---|
| **Status** | Active — the durable convention registry (so a rule is stated once, not per session) |
| **Last updated** | 2026-07-11 (MST) |
| **Audience** | software / design / reviewers |
| **Related** | [design/frontend/README.md](frontend/README.md) (tokens + per-screen spec), [design/builder-cards/README.md](builder-cards/README.md) (pipeline-card design), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) (rules decide / AI advises), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md) (RBAC + draft→approve), [functional.md](../requirements/functional.md), [scale-aware memory], [explicit-edit+audit memory] |

## Why this doc exists

The maintainer keeps re-stating the same cross-cutting rules. This is the **single place** each is
recorded so it holds app-wide and across sessions. When a new durable UI/product rule is given, add
it here (with a stable `UIC-N` id) **and** implement against it — do not wait to be told twice.

**Status legend:** ✅ Adopted (in code) · 🟡 Partial (some screens) · 🔜 To-build (recorded, not yet built).

**Implementation (2026-07-10, commit `6b571a4`, "Wave 10").** UIC-1..15 shipped in one parallel
batch (4 shared-primitive agents behind a barrier, then 9 per-screen agents on disjoint files);
statuses below are updated to match, each grounded in the diff/code path noted. UIC-16 stayed
partial at the time — only its canvas/palette half had shipped. tsc + oxlint clean; verified
in-browser across every touched screen.

**UIC-16 closed (2026-07-11, commit `12a9913`).** The deferred larger-card + four-side-typed-port
rework shipped: `frontend/src/components/BuilderShared.tsx` gained one geometry source of truth
(`portSide()`/`layoutPorts()`/`cardHeight()`, `NODE_W = 232`) that both `BuilderCanvas.tsx`'s
render and its wire-endpoint math call, so a wire can never detach from its port. Only item 4 of
[builder-cards/README.md §5](builder-cards/README.md#5-open--todo--spec-vs-shipped-updated-2026-07-11)
(registering a handful of still-unregistered reserved kinds, e.g. `fastp_html`/`samtools_stats`)
remains open — see that doc for the grounded detail; UIC-16 below is marked ✅ on the strength of
the larger-card + four-sided-port ask, which is what this row exists to track.

---

## Cross-cutting UI conventions

### UIC-1 — No page "flavor text"; the nav names the page · ✅
Remove the eyebrow label (e.g. "Workspace", "Triage", "Operations") **and** the descriptive
subtitle from page headers. The left-nav selector already tells the operator which page they are on;
the prose is noise on every visit. **Keep only** explicit *safety / limitation* warnings — e.g. the
Metric-catalog note ("Illustrative / operator-configurable metric vocabulary — NOT clinical … a
'registered' metric is not a gate until the runbook adds it"), the "phase-2 seam / not wired"
labels, and the de-identification / "view-gate not enforcement" banners. Move genuinely useful
explanatory prose into the usage docs ([docs/usage/](../usage/)), not the page chrome.
Applies to: every screen with a `PageHeader` eyebrow/subtitle. Provenance/Settings/Inbox/Review-queue
were called out by name. **Shipped** across Run views/Provenance/Review queue/Submit/Settings/Admin/
Inbox/Builder plus Monitoring/Agent-triage/Intake (the explicit safety/limitation banners were kept,
per the rule).

### UIC-2 — Tabs must read as tabs · ✅
The current underline-only `Tabs` is not visually suggestive enough. Frame tabs as **tabs** — a
boxed/segmented tab shape (top-rounded, a connected active tab, a baseline the active tab breaks
through), so it's unmistakably a view selector, not highlighted text. Still distinct from
`SegmentedControl` (compact toggle settings). Update `components/Tabs.tsx` once; every consumer
(Runs / Review-queue / Admin / RunDetail / Provenance / Inbox) inherits it. **Shipped**: `Tabs.tsx`
restyled to framed (top-rounded, active tab connected via `-mb-px`/`border-b-card`); every consumer
inherits it with no per-caller API change.

### UIC-3 — Checkbox multi-select convention (app-wide) · ✅
Every checkbox list uses ONE selection model:
1. **Shift-click range-select** — shift-clicking a checkbox selects everything from the topmost
   currently-selected checkbox to the shift-clicked one; if nothing is selected, from the first
   checkbox to the shift-clicked one.
2. **Select-all / clear-all** affordance (scoped to the visible page, so a batch-confirm count is
   never surprising).
3. **Hierarchical lists** (parent → children, e.g. run/flowcell → sample tickets): the **parent**
   checkbox sits at the far **left**, and the vertical group line starts **under it**, enclosing the
   child checkboxes — a clear hierarchy:
   ```
   [ ] RUN-2026-06-14-GIAB-A
    │  [ ] T-6171  (card)
    │  [ ] T-2841  (card)
   ```
   Toggling the parent **auto-toggles all children**; children reflect their own state otherwise.
Applies to: Review queue (canonical), Submit samples, Settings agent table, Inbox notes, Accession.
**Shipped** as a shared `hooks/useRangeSelect.ts` (anchor→target shift-click + `setMany()` for
parent→children) + `components/Check.tsx`; adopted in Review queue, Submit, and
`SettingsModelTier.tsx` (verified: `grep -rl useRangeSelect frontend/src` returns those three
screens plus the hook's own file). Inbox's mass-delete (self notes) predates this hook (T-113) and
was not migrated onto it in this pass — same selection *behavior*, a different implementation; a
follow-up could consolidate it onto `useRangeSelect` for one source of truth.

### UIC-4 — Edit/save gate on consequential toggles · ✅
A toggle whose accidental flip matters (notification on/off, model live/stub, agent enable) must be
**gated behind an explicit Edit → Save**: it still *displays* as a toggle (so state is legible) but
is not directly mutable until the row/panel is put in edit mode and saved. Prevents an accidental
single click from, e.g., turning off notifications. Pairs with the audit rule ([explicit-edit+audit
memory]). Already the pattern in Admin role edits + Settings threshold overrides; extend to Settings
notifications + agent tiering. **Shipped**: `SettingsNotifications.tsx` toggles and
`SettingsModelTier.tsx` agent rows (model + live) both now stage into a draft behind an explicit
Save/Cancel (Cancel discards, verified no leak) — Settings' notification/agent-tiering gap is
closed; Admin role edits + threshold overrides already had it (T-092/T-051).

### UIC-5 — Pagination is 25 / 50 / 100 everywhere · ✅
Any list that can grow uses the shared `components/Pager.tsx` with a 25/50/100 per-page control
(default 25). No infinite/unbounded rows (see scale-aware rule). Applies to: notifications/Inbox,
Submit sample table, Accession, Review queue, Monitoring, Admin, Provenance event-trail/artifacts.
**Shipped** — Inbox's notification list and Submit's sample table gained the real 25/50/100
control this batch (the last two named consumers); Accession/Review-queue/Monitoring/Admin/
Provenance already had it from earlier waves (T-114/T-116/T-117).

### UIC-6 — Every page is admin-assignable · ✅
The page-access catalog ([access.ts](../../frontend/src/access.ts)) must include **every** operator
page so an admin can grant/deny each one per user (G1). `admin` stays governed by `isAdmin` (never
page-gated); the `ACCESS_FLOOR` (Runs + Decision cards) is un-removable. Page access is a **view
gate, not authorization** — the API still checks wire role; keep that banner. **Shipped**:
`access.ts`'s `PageId` catalog now covers every operator page (12, `admin` intentionally excluded).

### UIC-7 — Themes: multiple light + dark complements · ✅
Beyond a single light/dark, offer **3 light + 3 dark** theme complements (a palette picker in user
Settings, `PrefsContext` + `data-theme`/a `data-palette` attribute driving the `@theme` vars). Each
must keep the functional verdict/gate colors legible and AA+ contrast. The theme is a personal pref
(localStorage), never affects the gate. **Shipped**: `index.css` `data-palette` blocks for Clinical/
Sand/Slate (light) and Midnight/Carbon/Indigo (dark); `PrefsContext` carries the palette choice
alongside the existing theme/density prefs; a picker lives in `UserSettingsDialog`. Verdict/gate
colors are inherited (not re-themed per palette) so a palette choice can never make a verdict
illegible; contrast hand-checked, not machine-audited (a labelled limitation, not a claim of a
formal AA+ audit).

---

## Screen-specific conventions

### UIC-8 — Decision cards · ✅
- The Claude-**generated** narration + "recommended next steps" must be **framed as one block under
  the metric tables** (currently free-floating). Visually group them (a bordered "AI narration
  (advisory)" panel) so evidence/tables read first, narration second (ADR-0001 separation).
- The per-card **Layout** control is removed from the card top (layout now lives in user Settings /
  `PrefsContext`); **default = split**.
- **Shipped**: `RunDetail.tsx` groups narration + next-steps into one bordered "AI narration
  (advisory)" panel under the tables; the per-card Layout control is removed (Settings/`PrefsContext`
  owns it, default split).

### UIC-9 — Provenance hashes + event trail · ✅
- Render a content hash as the **id/name** followed by a **`:` delimiter** then "show full" that
  expands to the **full** hash — do not show a leading partial before expansion (the id name is the
  human handle; the hash is the on-demand detail). Confirm this reads well; if a short prefix is
  genuinely more scannable, keep the prefix but still use the `:` delimiter (never a space).
- "Show full" must **not distort card formatting** (reserve the width / wrap in a mono `overflow-x`
  block, never reflow neighbors).
- The **event trail** renders copyable **code blocks** for any code/command, and **captures errors**
  (stderr / failure payloads) in the same copyable block.
- **Shipped**: `provenance/Fingerprint.tsx` renders `fingerprint:` + a show-full toggle to the full
  digest in an `overflow-x` mono block; `provenance/CodeBlock.tsx` (new) backs `EventTrail.tsx`'s
  copyable code/error rendering.

### UIC-10 — Review queue · ✅
- Hierarchy per UIC-3 (run checkbox left, line under it, parent toggles children).
- A **clear-from-view** for review-queue cards, mirroring Monitoring's recurring-issue cards: a
  **reversible**, localStorage-persisted clear/restore (never a DB purge), with a "Cleared · N"
  section to restore.
- **Escalations are role/access-based** — who can escalate / who an escalation routes to is gated by
  role + page access (ties to UIC-6 + the route-to-human role gate).
- **Shipped**: `ReviewQueue.tsx` renders the run checkbox left of a group line enclosing the sample
  tickets (`setMany` auto-toggles children), a reversible localStorage clear/restore with a
  "Cleared · N" section, and escalation gated by role + page access.

### UIC-11 — Submit samplesheet · ✅
- Per-page control (25/50/100) on the sample table (UIC-5).
- **`sample_metadata.csv` is NOT optional** — it is how samples are *identified* (study/clinical
  extension of the Illumina SampleSheet, which is a sequencing structure). Data-safety rules:
  1. Join on `Sample_ID` **plus** at least one more corroborating column (never a single-column
     match) to resist a 1-index-off mixup.
  2. Show a **join-review view** — the SampleSheet ⋈ sample_metadata result — behind an **approval
     gate** (a human confirms the identity join before the run proceeds). Sample identity mixups are
     the highest-consequence error here.
  3. The join + any edit is **logged and editable** (audit).
  (Accession screen (G1) is where subject/clinical metadata is composed; this is its intake join.)
- **Shipped**: `Submit.tsx`'s `canSubmit` requires `join.metadataPresent && joinApproved`;
  `lib/accession.ts`'s `computeIdentityJoin()` corroborates `Sample_ID` + tissue (never a
  single-column match) and classifies each row matched/weak/conflict/duplicate/unmatched; approval
  is bound to a join **signature** so any edit (a re-attached sheet, an added/removed row) auto-
  invalidates a prior approval; every join action appends to a client-side `SubmitAuditEntry` log.
  See [REQ-NF-025](../requirements/nonfunctional.md).

### UIC-12 — Settings · ✅
- Notification systems: **edit/save-gated** toggles (UIC-4) so notifications aren't accidentally
  disabled.
- Agent & model tiering: allow **removing** agents; **checkbox-based mass-edit** (UIC-3) to change
  several at once; drop redundant per-row UI icons; distinguish **active vs available** agents; explore
  a more robust **popout panel** for tiering.
- Remove flavor text (UIC-1); keep explicit limitation warnings (e.g. the Metric-catalog note).
- **Shipped**: `SettingsNotifications.tsx` toggles are edit/save-gated; `SettingsModelTier.tsx`
  splits Active vs Available agents (node-author now surfaces as Available, T-046), adds
  checkbox mass-select + remove, and paginates. **Still open**: the "more robust popout panel" was
  explore-level language, not a hard requirement — a plain staged-edit row shipped instead; a
  dedicated popout stays a future refinement, not tracked as a gap.

### UIC-13 — Admin · ✅
- **Act-as is password-gated** and logged **immutably** — impersonating another user is a
  high-trust action; require re-auth (a credential-request tool, never a plaintext password field —
  see the security guardrail) and write an un-editable audit entry.
- Move **password reset** + **role allocation** into a dedicated **user-edit screen** (a per-user
  detail view) so future user-management features have a home, instead of inline table controls.
- **Shipped, with a labelled demo gap**: Act-as now requires a password-confirm modal before
  impersonating and appends to an append-only `localStorage` audit log, merged into Admin's
  Activity feed. The re-auth step is a **demo password field, explicitly labelled in-code and
  in-UI as a production seam** — real re-auth is an IdP step-up (OAuth/OIDC) or a credential-request
  tool; a plaintext password field never ships long-term (the maintainer's own security guardrail).
  Password-reset + role allocation moved into a dedicated per-user Edit view.

### UIC-14 — Kanban board (Inbox) · 🟡
Standard QOL features, wired to the user/RBAC system:
- **@-mention** other users in a ticket.
- A ticket **body** + a **comment section**, and a **unique id per item** (visible, referenceable).
- Assignment / status connected to the overall user + review system (an Inbox ticket that maps to a
  review-queue ticket shares identity).
- **Shipped**: kanban cards show a visible unique id, a body + comment section with @-mentions
  resolved to roster display names, and an assignee. **Still open (cosmetic, noted at commit time)**:
  a ticket derived from the review queue shows its raw internal id rather than the queue's `T-XXXX`
  display id — a follow-up, not silently dropped.

### UIC-15 — Nav order (Operate group) · ✅
Within Operate, keep Notification → Action → Steps, but the **step order is Intake gate → Decision
cards** with **Runs at the BOTTOM** of the group (Runs is a list/index, not a step): e.g.
Inbox · Review queue · Sample accessioning · Submit · Intake gate · Decision cards · Runs.
**Shipped**: `Sidebar.tsx`'s `useNav` reorders Operate so Runs sits last.

### UIC-16 — Pipeline builder · ✅ — see [builder-cards/](builder-cards/)
Canvas + card conventions are documented in [docs/design/builder-cards/](builder-cards/): the dot
grid spans the **entire** working canvas; the tools palette shows the **current** pipeline's tools
with a `>` expander to all available; **larger** cards with typed half-circle ports on **all four
sides**; edges are typed data-flow between ports; per-tool port maps grounded in each tool's real
I/O; Databricks-inspired aesthetic. **Shipped**: the alignment dot grid spans the full canvas at
every zoom level; the palette shows the current pipeline's tools with a "≫ ALL" expander; and
(2026-07-11, commit `12a9913`) cards grew to `NODE_W = 232` with typed half-circle ports on all
four sides, driven by one geometry source of truth (`BuilderShared.portSide()`/`layoutPorts()`)
shared by render and wire math. **One item stays open, not silently dropped**: a handful of
documented tool ports (`fastp_html`, `samtools_stats`, the mosdepth `*_dist`/`per_base` family,
`vcf_index`, `multiqc_html`) have no kind registered in `ARTIFACT_KINDS` yet and so stay reserved,
unrendered — [builder-cards/README.md §5](builder-cards/README.md#5-open--todo--spec-vs-shipped-updated-2026-07-11)
item 4.

### UIC-17 — Pipeline Builder: composable-only canvas + an "⋯ More" overflow toolbar · ✅
Two related, maintainer-directed rules from the same 2026-07-11 session
([journal](../journal/2026-07-11-builder-boundary-and-edges.md), commits `4df8f2e`→`3d531de`):
1. **A canvas holds only what the operator composes.** A non-composable, non-editable system
   element (nothing an operator can wire, duplicate, delete, or reconfigure) does not get a
   canvas card, however "terminal"-styled — it gets a **named, always-reachable, read-only view**
   opened from the toolbar instead. The Pipeline Builder's deterministic ingest + gate were the
   first case: removed from `BuilderCanvas.tsx` entirely (canvas node count 15→13) and replaced by
   `components/DecisionBoundaryModal.tsx`, opened via "⋯ More → Decision boundary."
2. **A crowded toolbar consolidates to one primary compose row + an "⋯ More" overflow**, not two
   stacked rows of flat controls. Keep the primary verbs (here: Save · Validate · Emit) directly
   visible and accent-styled; relocate occasional/context actions (export, hand-off, fork,
   cross-screen links) into the overflow, unchanged behavior, just regrouped. Any identity/state
   shown twice (here: the run id, once in a status pill and once in the linked-run strip)
   collapses to one place.
**Shipped**: `PipelineBuilder.tsx`'s toolbar is now one row + a `MoreHorizontal` overflow menu;
`BuilderCanvas.tsx` renders zero verdict palette and zero non-composable cards. Grounded in
[frontend/README.md §6](frontend/README.md#6-pipeline-builder--full-model),
[ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) Realized §3.

---

## Session feedback → convention map (2026-07-10 batch)

Every item from the maintainer's 2026-07-10 notes is recorded above; this table is the index.

| Note | Convention |
|---|---|
| Remove "Workspace"/"Triage" flavor text | UIC-1 |
| Tabs not visually suggestive | UIC-2 |
| Shift-click range select | UIC-3.1 |
| Run/sample checkbox hierarchy + auto-toggle | UIC-3.3, UIC-10 |
| Notifications edit/save gate | UIC-4, UIC-12 |
| Submit per-page 25/50/100 | UIC-5, UIC-11 |
| All pages admin-assignable | UIC-6 |
| More themes (3 light / 3 dark) | UIC-7 |
| Decision-card AI message framing; layout→settings, default split | UIC-8 |
| Provenance hash id:hash + copyable event-trail code blocks | UIC-9 |
| Review-queue clear-out + escalation RBAC | UIC-10 |
| sample_metadata required + join-review approval gate | UIC-11 |
| Agent tiering: remove/active-vs-available/mass-edit/popout | UIC-12 |
| Act-as password + immutable log; user-edit screen | UIC-13 |
| Kanban @mentions, comments, ids | UIC-14 |
| Intake gate above Runs; Runs to bottom | UIC-15 |
| Builder canvas dots, current-tools palette, larger cards, all-side ports | UIC-16 |
