# UI & Product Conventions

| Field | Value |
|---|---|
| **Status** | Active — the durable convention registry (so a rule is stated once, not per session) |
| **Last updated** | 2026-07-10 (MST) |
| **Audience** | software / design / reviewers |
| **Related** | [design/frontend/README.md](frontend/README.md) (tokens + per-screen spec), [design/builder-cards/README.md](builder-cards/README.md) (pipeline-card design), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) (rules decide / AI advises), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md) (RBAC + draft→approve), [functional.md](../requirements/functional.md), [scale-aware memory], [explicit-edit+audit memory] |

## Why this doc exists

The maintainer keeps re-stating the same cross-cutting rules. This is the **single place** each is
recorded so it holds app-wide and across sessions. When a new durable UI/product rule is given, add
it here (with a stable `UIC-N` id) **and** implement against it — do not wait to be told twice.

**Status legend:** ✅ Adopted (in code) · 🟡 Partial (some screens) · 🔜 To-build (recorded, not yet built).

---

## Cross-cutting UI conventions

### UIC-1 — No page "flavor text"; the nav names the page · 🔜
Remove the eyebrow label (e.g. "Workspace", "Triage", "Operations") **and** the descriptive
subtitle from page headers. The left-nav selector already tells the operator which page they are on;
the prose is noise on every visit. **Keep only** explicit *safety / limitation* warnings — e.g. the
Metric-catalog note ("Illustrative / operator-configurable metric vocabulary — NOT clinical … a
'registered' metric is not a gate until the runbook adds it"), the "phase-2 seam / not wired"
labels, and the de-identification / "view-gate not enforcement" banners. Move genuinely useful
explanatory prose into the usage docs ([docs/usage/](../usage/)), not the page chrome.
Applies to: every screen with a `PageHeader` eyebrow/subtitle. Provenance/Settings/Inbox/Review-queue
were called out by name.

### UIC-2 — Tabs must read as tabs · 🔜
The current underline-only `Tabs` is not visually suggestive enough. Frame tabs as **tabs** — a
boxed/segmented tab shape (top-rounded, a connected active tab, a baseline the active tab breaks
through), so it's unmistakably a view selector, not highlighted text. Still distinct from
`SegmentedControl` (compact toggle settings). Update `components/Tabs.tsx` once; every consumer
(Runs / Review-queue / Admin / RunDetail / Provenance / Inbox) inherits it.

### UIC-3 — Checkbox multi-select convention (app-wide) · 🟡
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

### UIC-4 — Edit/save gate on consequential toggles · 🟡
A toggle whose accidental flip matters (notification on/off, model live/stub, agent enable) must be
**gated behind an explicit Edit → Save**: it still *displays* as a toggle (so state is legible) but
is not directly mutable until the row/panel is put in edit mode and saved. Prevents an accidental
single click from, e.g., turning off notifications. Pairs with the audit rule ([explicit-edit+audit
memory]). Already the pattern in Admin role edits + Settings threshold overrides; extend to Settings
notifications + agent tiering.

### UIC-5 — Pagination is 25 / 50 / 100 everywhere · 🟡
Any list that can grow uses the shared `components/Pager.tsx` with a 25/50/100 per-page control
(default 25). No infinite/unbounded rows (see scale-aware rule). Applies to: notifications/Inbox,
Submit sample table, Accession, Review queue, Monitoring, Admin, Provenance event-trail/artifacts.

### UIC-6 — Every page is admin-assignable · 🟡
The page-access catalog ([access.ts](../../frontend/src/access.ts)) must include **every** operator
page so an admin can grant/deny each one per user (G1). `admin` stays governed by `isAdmin` (never
page-gated); the `ACCESS_FLOOR` (Runs + Decision cards) is un-removable. Page access is a **view
gate, not authorization** — the API still checks wire role; keep that banner.

### UIC-7 — Themes: multiple light + dark complements · 🔜
Beyond a single light/dark, offer **3 light + 3 dark** theme complements (a palette picker in user
Settings, `PrefsContext` + `data-theme`/a `data-palette` attribute driving the `@theme` vars). Each
must keep the functional verdict/gate colors legible and AA+ contrast. The theme is a personal pref
(localStorage), never affects the gate.

---

## Screen-specific conventions

### UIC-8 — Decision cards · 🟡
- The Claude-**generated** narration + "recommended next steps" must be **framed as one block under
  the metric tables** (currently free-floating). Visually group them (a bordered "AI narration
  (advisory)" panel) so evidence/tables read first, narration second (ADR-0001 separation).
- The per-card **Layout** control is removed from the card top (layout now lives in user Settings /
  `PrefsContext`); **default = split**.

### UIC-9 — Provenance hashes + event trail · 🔜
- Render a content hash as the **id/name** followed by a **`:` delimiter** then "show full" that
  expands to the **full** hash — do not show a leading partial before expansion (the id name is the
  human handle; the hash is the on-demand detail). Confirm this reads well; if a short prefix is
  genuinely more scannable, keep the prefix but still use the `:` delimiter (never a space).
- "Show full" must **not distort card formatting** (reserve the width / wrap in a mono `overflow-x`
  block, never reflow neighbors).
- The **event trail** renders copyable **code blocks** for any code/command, and **captures errors**
  (stderr / failure payloads) in the same copyable block.

### UIC-10 — Review queue · 🟡
- Hierarchy per UIC-3 (run checkbox left, line under it, parent toggles children).
- A **clear-from-view** for review-queue cards, mirroring Monitoring's recurring-issue cards: a
  **reversible**, localStorage-persisted clear/restore (never a DB purge), with a "Cleared · N"
  section to restore.
- **Escalations are role/access-based** — who can escalate / who an escalation routes to is gated by
  role + page access (ties to UIC-6 + the route-to-human role gate).

### UIC-11 — Submit samplesheet · 🟡
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

### UIC-12 — Settings · 🟡
- Notification systems: **edit/save-gated** toggles (UIC-4) so notifications aren't accidentally
  disabled.
- Agent & model tiering: allow **removing** agents; **checkbox-based mass-edit** (UIC-3) to change
  several at once; drop redundant per-row UI icons; distinguish **active vs available** agents; explore
  a more robust **popout panel** for tiering.
- Remove flavor text (UIC-1); keep explicit limitation warnings (e.g. the Metric-catalog note).

### UIC-13 — Admin · 🔜
- **Act-as is password-gated** and logged **immutably** — impersonating another user is a
  high-trust action; require re-auth (a credential-request tool, never a plaintext password field —
  see the security guardrail) and write an un-editable audit entry.
- Move **password reset** + **role allocation** into a dedicated **user-edit screen** (a per-user
  detail view) so future user-management features have a home, instead of inline table controls.

### UIC-14 — Kanban board (Inbox) · 🔜
Standard QOL features, wired to the user/RBAC system:
- **@-mention** other users in a ticket.
- A ticket **body** + a **comment section**, and a **unique id per item** (visible, referenceable).
- Assignment / status connected to the overall user + review system (an Inbox ticket that maps to a
  review-queue ticket shares identity).

### UIC-15 — Nav order (Operate group) · 🔜
Within Operate, keep Notification → Action → Steps, but the **step order is Intake gate → Decision
cards** with **Runs at the BOTTOM** of the group (Runs is a list/index, not a step): e.g.
Inbox · Review queue · Sample accessioning · Submit · Intake gate · Decision cards · Runs.

### UIC-16 — Pipeline builder · see [builder-cards/](builder-cards/)
Canvas + card conventions are documented in [docs/design/builder-cards/](builder-cards/): the dot
grid spans the **entire** working canvas; the tools palette shows the **current** pipeline's tools
with a `>` expander to all available; **larger** cards with typed half-circle ports on **all four
sides**; edges are typed data-flow between ports; per-tool port maps grounded in each tool's real
I/O; Databricks-inspired aesthetic.

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
