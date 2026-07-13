# Journal — 2026-07-10 (MST) — frontend UI-feedback pass: theme revert, builder-canvas fix, Monitoring/Review-queue polish, Inbox

> **Naming note (read first):** the fan-out task that spawned this sweep asked to label this
> batch **"Batch 7"** in the code-map narrative, following the Batch 5/Batch 6 convention. That
> convention has since moved on without the requester's knowledge: `CLAUDE.md`'s own code map
> already narrates a **"Batch 7"** (commits `34bca5d`→`adfd7aa`, T-069/T-070/T-072) and a
> **"Batch 8"** (commits `5763be1`→`f8a6f35`, T-098–T-100), plus **"Wave 2"–"Wave 6"** for the
> commits since (Wave 6 = `b4c3672`, the in-progress ADR-0018/variant-interpretation design this
> task explicitly excludes). Re-using "Batch 7" here would silently overwrite/collide with an
> already-real batch in the historical record. Verified via `git log --oneline -30` before
> writing anything: this session's four commits (`52124d3`→`d832553`) land immediately **after**
> Wave 6. So this entry — and every doc it touches — labels the work **"Wave 7"** instead, and
> keeps the requested journal *filename* (`2026-07-10-frontend-batch7.md`) as asked, since the
> filename itself doesn't collide with anything on disk.

| Field | Value |
|---|---|
| **Focus** | Doc-keeper SWEEP for four maintainer-feedback frontend commits landed on `main`: a theme revert + themeable left nav (GA1/GA2), a Pipeline-Builder canvas regression fix + minimap viewport tracking (PB3), Monitoring/Review-queue polish (M7/RQ1), and a brand-new Inbox notification/triage workspace (GA3). Explicitly out of scope: ADR-0018, `docs/design/variant-interpretation.md`, and any `src/bayleaf/`/`api/` files — Wave 6 owns those. |
| **Participants** | maintainer (UI feedback); doc-keeper subagent |
| **Outcome** | All four commits' owed docs updated in one pass: `CLAUDE.md` code map (new "Wave 7" paragraph), `docs/planning/tasks.md` (T-105–T-108), `docs/design/architecture.md` (new paragraph + screen-count fix + Related), `docs/design/frontend/README.md` (§4/§5.5/§5.8/§5.11-new/§6/§9/§11), `docs/requirements/functional.md` (REQ-F-077 + REQ-F-073 amendment), `docs/requirements/scope-and-wishlist.md` (item 5 amendment + screen-count fix). No backend/core files touched (verified below). |

## Discussion

### Grounding — what the four commits actually did
Read each commit's full diff (`git show <sha>`) rather than trusting only the commit body, per
the "ground every claim in code" rule:

1. **`52124d3` — Theme revert + themeable nav.** `frontend/src/index.css`: light-mode neutrals
   reverted from the Batch-8 (`5763be1`) warm japandi sand/greige back to a **cool clinical**
   palette (`--color-page:#eef1f5`, `--color-card:#f9fbfd`, `--canvas-dot:#d3dae4`, …) — the
   maintainer's call that japandi "didn't read clinical/biotech," while deliberately keeping OFF
   the pre-Batch-8 glaring pure-white (`#fff`→`#f9fbfd`). Separately, the left nav gained its own
   `--color-nav*` var family in the BASE `@theme` (light: white nav, dark text, `--color-nav-
   active-text` accent-tinted) with the ORIGINAL dark-nav values moved into the
   `:root[data-theme='dark']` override — so the nav is now genuinely themeable (light in light
   mode, the unchanged dark nav in dark mode), where it was previously dark in both. Verified
   `frontend/src/components/Sidebar.tsx`'s diff replaces every hardcoded `#hex` with the new
   vars end-to-end; a few whites on colored badges intentionally stay literal.
2. **`eab5ff2` — Builder-canvas fix (PB3).** Two fixes to `BuilderCanvas.tsx`: (a) a **double
   dot-grid regression** — Batch 8 (`5763be1`, T-098) had moved the grid onto the scroll-surface
   `<div>` so it would "span the whole canvas," but the content-plane `<div>` still painted its
   own copy too, so a static dot layer visibly slid over a moving one. This commit removes the
   scroll-surface grid entirely; a single grid now lives on the content plane and pans/zooms with
   the pipeline. **This means the T-098 claim ("now painted on the scroll surface … spans the
   entire canvas") is now WRONG and had to be corrected everywhere it was written down** (README
   §6, `CLAUDE.md`, `architecture.md` — see below). (b) A new **minimap viewport rectangle**:
   `updateVp()` maps the scroll viewport → inner canvas coords (accounting for the 360/480 margin
   + zoom, same convention `fitToDag` already used) → minimap pixels, recomputed on scroll/Fit/
   mount/zoom; a `<span>` overlay renders it, clamped into the minimap box. Read the diff line by
   line to confirm the math and the `onScroll={updateVp}` wiring.
3. **`478129d` — Monitoring + Review queue (M7/RQ1).** `Monitoring.tsx`: the X-axis date format
   changed `shortDate()` from `MM-DD` to `DD-MM-YY` (slicing the ISO date apart and reassembling),
   rendered at a `-35°` angle (`XAxis` `tick.angle`, `height: 46`, chart `height` 200→224 to seat
   the ticks); the single always-on `Line dataKey="flagged"` became a `TREND_LINES` array of five
   entries (proceed/hold/rerun/escalate/flagged) filtered by a new `trendOn` toggle-state record,
   defaulting to `{flagged: true, others: false}`, rendered as clickable `aria-pressed` legend
   chips replacing the old static swatch legend; `LEGEND_ORDER`/`VERDICT_BAR` imports dropped as
   dead code. `ReviewQueue.tsx`: the per-ticket and batch "Resolve" buttons' Tailwind classes
   changed from the `proceed-*` (green) token set to a neutral `border-line-strong bg-card
   text-text` set with an accent hover — read both diff hunks to confirm only the class strings
   changed, no logic.
4. **`d832553` — Inbox (GA3), a brand-new surface.** Read `InboxContext.tsx` (282 lines),
   `inbox.ts` (84 lines), `NotificationBell.tsx` (109 lines) in full, plus the diffs to
   `App.tsx`/`Sidebar.tsx`/`TopBar.tsx`/`Layout.tsx`. Confirmed: (a) `InboxItem`s are **derived**
   from `api.listTickets({status:'open'})` + `{status:'in_review'})` — the already-off-gate
   review-queue endpoint, no new backend route; (b) the operator's overlay (read/flag/priority/
   column/due/note) and self-authored reminders persist to two `localStorage` keys **scoped per
   `actor.id`** (`bayleaf.inbox.overlay.<id>` / `bayleaf.inbox.self.<id>`), re-read whenever
   `actorId` changes — i.e. Admin's "Act as" (`RoleContext.setActor`) genuinely swaps to that
   person's board, not a shared one; (c) `unreadCount` excludes the `done` column (the kanban
   archive) and drives both the Sidebar "Inbox" badge and the top-bar bell badge from the same
   context, so they can never drift apart; (d) `/inbox` mounts inside `InboxProvider` (wrapped
   around `<Layout>` in `App.tsx`, inside `RequireAuth`) with four tabs (Inbox/Board/Calendar/
   Notes) per the commit body; (e) `inbox.ts`'s `localYmd`/`todayYmd` deliberately avoid
   `toISOString()` (UTC) so a reminder due "today" can't read as overdue across a UTC-date
   rollover — confirmed by reading the function bodies. Nothing in this file touches a verdict,
   finding, or confidence field; `source`/`SOURCE_META` reuse the verdict palette only as a
   *visual* borrow (escalate/rerun/hold dot colors), never a decision input.

### What is genuinely new vs. re-presentation
Three of the four commits (theme, builder-canvas, monitoring/review-queue) are refinements to
**already-documented** capabilities (REQ-F-073 theme/density, wishlist #11 Pipeline Builder,
existing Monitoring/Review-queue capabilities) — no new REQ-F rows needed for those, matching the
precedent that not every polish commit gets one (e.g. T-098's japandi swap didn't get its own
REQ-F either). **Inbox is different: a genuinely new, off-gate, testable capability** — a new
route, a new context, a new nav item, a new visual-token module — so it gets its own
**REQ-F-077**.

### Doc-update-map sweep
Walked [TABLE_OF_CONTENTS.md#doc-update-map](../TABLE_OF_CONTENTS.md#doc-update-map) against
these four commits:
- 🔴 journal (this file) — unconditional, done.
- 🔴 `planning/tasks.md` — four new task rows (T-105–T-108), done.
- 🟠 "`api/` endpoint or `frontend/` screen — new/changed capability" →
  `design/architecture.md` + `design/data-platform-and-archivist.md` + `requirements/
  functional.md` (REQ-F). Did `architecture.md` (new paragraph, screen-count fix, Related) and
  `functional.md` (REQ-F-077 + a REQ-F-073 amendment). **Waived `data-platform-and-archivist.md`**
  — its §4 is specifically the pagination/export/run-browser scale-kit catalog; none of these
  four commits touch that pattern (Inbox has no numbered-pager list yet; confirmed by reading
  `Inbox.tsx`'s tab bodies — filterable stream, kanban, calendar, notes, no `SegmentedControl`/
  pager). Same waiver precedent as the Wave-3 ConfirmDialog sweep, which also skipped this file
  for the same reason (confirmed: `grep -n "T-102" docs/design/data-platform-and-archivist.md` =
  no hits).
- ⚪ "Scope / wishlist / 'built' changes" → `requirements/scope-and-wishlist.md`. Amended item 5
  (Inbox as a new Operate-group surface; also fixed a **pre-existing** stale "9 operator screens"
  count — `architecture.md` already correctly tracks 10 post-Submit-rebuild, i.e. this drift
  predates this session but sits on the exact line this batch's edit touches, so fixed it in the
  same change per the "fix the drift you find" rule).
- ⚪ `CLAUDE.md` code map — new Wave-7 paragraph in §4, plus corrected the now-false T-098
  scroll-surface dot-grid claim in the Batch-8 paragraph (same precedent as the Batch-8 sweep's
  own correction of Batch 7's T-072 claim: fix superseded claims in place, don't just contradict
  them from a later paragraph).
- No `data/schemas.md`, `provenance.md`, `metric_registry.md`, `qc_metrics.md`, or ADR trigger
  fired — confirmed no `src/bayleaf/`/`api/` file appears in any of the four diffs
  (`git show --stat` on each, reproduced above; also `git diff --stat b4c3672 d832553 -- src/
  api/ tests/` is empty).
- `quality/risks.md` — considered and **waived** for Inbox's per-operator `localStorage` state:
  it is low-stakes, non-destructive personal-organization data (read/flag/priority/notes), not an
  access-control or data-integrity risk, and the same client-only-state pattern (Prefs T-091,
  Monitoring's clear/restore-signatures T-100) never got a dedicated RISK row either (confirmed:
  `grep -n "PrefsContext\|clear-from-view" docs/quality/risks.md` = no hits). RISK-035 already
  covers the login/RBAC client-side posture Inbox's per-actor scoping rides on top of; no new
  risk category.
- `quality/evaluation.md` — waived; the frontend has no test runner (`package.json` scripts are
  `dev`/`build`/`tsc`/`lint`/`preview` only, confirmed), so no test census to recount, matching
  every prior frontend-only batch's practice ("tsc + oxlint clean").

### Stale-claim fix (the actual drift, not just new content)
Found and fixed one real drift while grounding this sweep: three docs (CLAUDE.md, architecture.md,
frontend README §6) asserted the Pipeline-Builder dot grid "now spans the whole scroll surface"
(a T-098/Batch-8 claim) — commit `eab5ff2` REMOVED that scroll-surface grid two commits later the
same day to fix the double-layer bug it caused. Left uncorrected, this is exactly the "#1 drift"
class the operating contract calls out: a claim contradicted by the current code. Corrected all
three locations in place, noting the regression→fix arc rather than deleting the history.

## Decisions

| Decision | Distilled to |
|---|---|
| Label this work "Wave 7" in every doc, not "Batch 7"/"Batch 8" as the originating instruction assumed — those labels are already used by commits `34bca5d`→`adfd7aa` and `5763be1`→`f8a6f35` respectively; reusing either would corrupt the historical narrative. The journal *filename* stays as requested (`2026-07-10-frontend-batch7.md`) since a filename doesn't collide. | `CLAUDE.md` §4 Wave-7 paragraph; `architecture.md`; `tasks.md` T-105–T-108; this file |
| Inbox is a genuinely new capability (REQ-F-077), distinct from the outbound `notify/` port (ADR-0010) — it never leaves the browser, is entirely derived from already-off-gate review-queue tickets, and never sets/reads a verdict or confidence | `requirements/functional.md` REQ-F-077; `architecture.md` |
| No new RISK row for Inbox's per-operator `localStorage` state — matches the established client-only-state precedent (Prefs, cleared-signatures), neither of which got one | this file (waiver recorded here; no risks.md edit) |

## Open questions & TODO

- Inbox state is entirely client-side and per-browser — it is not synced across devices, and
  clearing site data (or a different browser/machine) loses an operator's triage/board/reminders.
  This is the same class of limitation as `PrefsContext` (T-091) and the Monitoring clear/restore
  signatures (T-100); a durable version would need a server-side per-user preference/notification
  store, which does not exist yet (no task row opened for this — flagging here as a TODO, not
  inventing a task id for scope not yet asked for).
- `subject_id`/`tissue` (T-101/Wave 4) and this batch's Inbox both add real client-side state with
  no backend persistence — worth a future pass surveying which "client-only, not yet
  server-synced" seams exist across the app, if the maintainer wants a consolidated view.
- The Pipeline-Builder minimap viewport rectangle (`eab5ff2`) is a pure visual affordance; no
  functional/task gap remains open from this commit.

## Distilled into

- [CLAUDE.md](../../CLAUDE.md) §4 — new Wave-7 paragraph; corrected the stale T-098 dot-grid claim.
- [docs/planning/tasks.md](../planning/tasks.md) — T-105, T-106, T-107, T-108.
- [docs/design/architecture.md](../design/architecture.md) — new Wave-7 paragraph, screen-count
  fix (10→11), Related field, Invariant 6 cross-reference.
- [docs/design/frontend/README.md](../design/frontend/README.md) — §4 (theme + nav groups +
  Inbox nav item), §5.5 (RQ1), §5.8 (M7), new §5.11 (Inbox), §6 (PB3 fix + corrected dot-grid
  claim), §9 (palette correction), §11 (Admin Act-as ⋈ Inbox crosslink).
- [docs/requirements/functional.md](../requirements/functional.md) — new REQ-F-077 (Inbox);
  REQ-F-073 amended (nav now themeable too).
- [docs/requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — item 5
  amended (Inbox + the 9→11 screen-count fix).
