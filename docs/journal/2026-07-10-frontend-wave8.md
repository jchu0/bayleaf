# Journal — 2026-07-10 (MST) — frontend Wave 8: Tabs/nav reorg, Submit/Intake polish, Inbox notes+folders, Provenance rewrite, Builder on-canvas editing

| Field | Value |
|---|---|
| **Focus** | Doc-keeper SWEEP for six maintainer-feedback frontend commits landed on `main` (`1bc0072`→`109557e`, verified `git diff --stat 04adeac 109557e -- src/ api/ tests/` = empty, i.e. frontend-only): a canonical `Tabs` view-selector replacing `FacetChip` + a nav reorder + Review-queue selection redesign (G4/G5/RQ2/RQ3); Submit bulk-edit (S1-S3); Intake gate preflight metadata (IG1); Inbox refinements (IB1-3,5-8, IB4 deferred); a Provenance rewrite into Lineage/Event-trail/Artifacts tabs (PV1) + a shared `Pager`; Pipeline-Builder on-canvas editing — selection, rename, wire-delete, undo/redo, marquee, context menus, alignment guides, drag-to-connect (PB2, P1-P7). Named **"Wave 8"** in the code-map narrative per the task instruction, continuing after "Wave 7" (T-105–T-108) without colliding with the already-used "Batch 7/8" labels. |
| **Participants** | maintainer (UI feedback); doc-keeper subagent |
| **Outcome** | All six commits' owed docs updated in one pass: `CLAUDE.md` code map (new "Wave 8" paragraph), `docs/planning/tasks.md` (T-110–T-115), `docs/design/architecture.md` (new Wave-8 bullet + Related), `docs/design/frontend/README.md` (§4/§5.1/§5.3/§5.5/§5.6 rewritten/§6/§11 crosslink), `docs/requirements/functional.md` (REQ-F-042 screen-count/Provenance-description fix + REQ-F-063/REQ-F-074/REQ-F-077 amendments + new REQ-F-078/REQ-F-079), `docs/requirements/scope-and-wishlist.md` (item 5 amendment + wishlist item 11 amendment). No `src/pipeguard/`, `api/`, `tests/`, or ADR file touched (verified below); no design deliverables (`briefs/`, `handoffs/`, `source/`, `PipeGuard.html`) touched. |

## Discussion

### Grounding — what the six commits actually did
Read each commit's full diff (`git show <sha>` / `git show <sha> --stat`) rather than trusting
only the commit body, per the "ground every claim in code" rule.

1. **`1bc0072` — Tabs (G5), nav reorg (G4), Review-queue selection (RQ2/RQ3).**
   `frontend/src/components/Tabs.tsx` is a new canonical underline tab bar (`role="tablist"`,
   generic `TabItem<T>`, optional count badge) — its own top comment says it explicitly:
   "distinct on purpose from `SegmentedControl`, which stays for compact toggle SETTINGS (7d/14d/
   30d window, theme, density); Tabs is now the one 'which view am I in' idiom." Confirmed
   `frontend/src/components/FacetChip.tsx` is deleted (`git show --stat`: `38 ---`) and
   `SegmentedControl.tsx` still exists (`ls frontend/src/components/`). Applied to Runs (status),
   Review queue (status), Admin (activity-log kind), RunDetail (sample verdict) — read the diffs
   on `RunOverview.tsx`/`ReviewQueue.tsx`/`Admin.tsx`/`RunDetail.tsx` confirming each swap.
   `Sidebar.tsx`'s diff moves the Inbox nav item from the bottom to the top of the Operate group
   with a comment explaining the new order: Notification (Inbox) → Action (Review queue) → Steps
   (Submit → Runs → Intake → Decision cards) — "work/issue-tracking pages sit above the process
   flow." `ReviewQueue.tsx`'s diff adds a page-scoped `pageClearable`/`allShownSelected`/
   `selectAllShown` (RQ2 — deliberately scoped to the page, not the whole filtered set, "so the
   batch-confirm count is never surprising") and reworks each run group into a `border-l-2` rail
   (`groupHasSelection ? 'border-accent' : 'border-line-strong'`) with a fixed `w-4` checkbox
   gutter shared by the subheader select-all and every ticket row (RQ3) — read the before/after
   hunks confirming the old floating-checkbox layout is gone.
2. **`24fe2e3` — Submit dropdown/checkbox/bulk-add (S1-S3).** `Submit.tsx`'s diff removes
   `cycleType()` (a click-to-cycle button) — confirmed the sample-type column is now a real
   `<select>` (read the JSX further down the diff, not shown in the excerpt above but present in
   the full file). `removeSample(i)` (a per-row delete) is replaced by `toggleSampleSel`/
   `toggleAllSel`/`removeSelected` — a `Set<number>` selection, a header checkbox with a real
   `indeterminate` DOM property set via a `ref` callback, and an `await confirm({...})` (danger
   tone, names the count, "nothing is deleted downstream") before removal — S2 exactly as the
   commit body describes. `addSample()` (one row) becomes `addSamples(n)`, clamped
   `Math.max(1, Math.min(500, ...))`, driven by a new count `<input type=number>` + Add button —
   S3. Selection is cleared on parse/BaseSpace-import (`setSelected(new Set())` appears in both
   `handleFile` and `handleBaseSpaceImport`, confirmed in the diff).
3. **`1052e15` — Intake preflight metadata (IG1).** `Intake.tsx`'s diff adds a `MetaField`
   component (skeleton-on-pending, italic "not captured" on a loaded-but-null value — never a
   fabricated placeholder) and a `useEffect` that lazy-fetches `api.qcReadout(run.run_id, id)`
   **only for rows that are open** (`isOpen = openMap[id] ?? (sparse || flaggedAtIntake)`) — the
   commit body's "scale-aware, never N+1 for a 100-sample run" claim checks out against the guard
   condition. The yield bar gains `max-w-[340px]` (was full-width), matching the Runs verdict-bar
   convention already documented elsewhere. Six fields render: Sample type / Library prep / Origin
   (from the lazy-loaded `CardHeader`) plus run-level Platform / Run date / Verdict (already on
   hand, no fetch).
4. **`2865dac` — Inbox refinements (IB1-3,5-8).** `InboxContext.tsx`'s diff adds `folder`/
   `updatedAt` to `ItemMeta`/`InboxItem`, a new `folders: string[]` state persisted under a new
   `pipeguard.inbox.folders.<actorId>` key (mirroring the existing per-operator overlay/self-item
   key pattern), `markAllUnread`, `updateSelfItem`, and `setFolder`/`addFolder`/`renameFolder`/
   `deleteFolder` actions — confirmed against the diff hunks read above. The commit body's
   per-item claims (IB2 mark-all-unread, IB3 calendar composer wording, IB5 notes read-only-
   until-Edit, IB6 created/edited timestamps, IB7 delete-in-edit + mass-delete, IB8 folder
   manager/filter, IB1 Google/Outlook connectors as labelled phase-2 seams) are corroborated by
   the `Inbox.tsx` diff (459 lines changed) — not read hunk-by-hunk given the size, but the
   `InboxContext.tsx` state additions above are the load-bearing plumbing every one of those UI
   claims depends on, and they check out. **IB4 (per-reminder Slack/Discord/Teams/email
   notification + cadence) is explicitly deferred** — the commit body says so directly ("the
   largest, next") and no notification-channel code appears in either diff.
5. **`0e64fad` — Provenance rewrite (PV1) + shared `Pager`.** Read `frontend/src/provenance.ts`
   in full (232 new lines) and the head of `components/provenance/EventTrail.tsx`: the module
   comment states the event vocabulary is derived "ONLY from what the ledger actually emits
   (engine.py:90-171) — five event types" — cross-checked against
   `src/pipeguard/provenance.py`'s `EventType` enum, which has **six** members
   (`ANALYSIS_RUN_STARTED`, `SAMPLE_REGISTERED`, `FINDING_EMITTED`, `VERDICT_DECIDED`,
   `ANALYSIS_RUN_COMPLETED`, plus `NOTIFICATION_EMITTED`) — `run_gate` itself only emits the
   first five; `NOTIFICATION_EMITTED` is a separate notify-port event, so the frontend's "five
   emitted, everything else generic" framing is accurate, and `EventTrail`'s unknown-type fallback
   is real defensive code, not an unverified claim. `types.ts:145` confirms `RunDetail.events:
   ProvenanceEvent[]` already existed on the wire type before this commit — the commit body's
   load-bearing claim ("zero backend change, this data already ships") is grounded, not asserted.
   `git show --stat` confirms the file set: `Pager.tsx` (new, 93 lines, extracted per the commit
   body from Runs/Monitoring/Admin/AgentTriage duplication), `provenance/Artifacts.tsx`,
   `EventTrail.tsx`, `Fingerprint.tsx`, `Lineage.tsx` (new), and `Provenance.tsx` **shrinks** from
   ~485 lines of its old self into a thin container (net diff shows deletions alongside the new
   views) — consistent with "a thin container… over a Tabs view switch."
6. **`109557e` — Pipeline-Builder on-canvas editing (PB2, P1-P7).** Read
   `frontend/src/hooks/useTopologyHistory.ts` in full (72 lines): its own comment states the scope
   precisely — "Scope: canvas topology only (nodes/edges). Locator/reference authoring
   (locEdits/refLoc) is not yet undoable" — confirming the commit body's "undo covers topology
   only" deferral is accurate, not just claimed. The hook is a bounded ring buffer (`cap = 50`,
   `past.current.length > cap` shift), snapshotting `{nodes, edges}` via `record()` called before
   a mutation, with `undo`/`redo` swapping snapshots through the existing `setNodes`/`setEdges`
   setters rather than owning state itself — a minimally-invasive design, as its comment says.
   `git show --stat` confirms new files `BuilderContextMenu.tsx` (87 lines), `SelectionActionBar.tsx`
   (146 lines), plus large diffs to `BuilderCanvas.tsx` (+416/-…), `BuilderInspector.tsx`
   (+363/-…), `BuilderShared.tsx` (+64), and `PipelineBuilder.tsx` (+582/-141) — matching the
   commit body's P1–P7 feature list (selection+inspector+rename, wire delete, undo/redo+keyboard,
   marquee+`SelectionActionBar`, context menus, alignment guides+snap, drag-to-connect). The
   commit body also documents a **fix, not a feature**: `BuilderShared`'s `ARTIFACT_KINDS` read
   `GIAB_LOC` before its declaration — a module-init temporal-dead-zone bug `tsc` didn't catch but
   that blanked the app at runtime — resolved by reordering the two declarations. Confirmed
   `frontend/src/components/Truncate.tsx` exists (`ls`) but **`grep -rn "Truncate"
   frontend/src --include='*.tsx' --include='*.ts' -l` returns only the file itself** — the
   primitive was added (per the task instruction's framing, "G2") but is not yet imported/used
   anywhere in the app. Recorded as an explicit open item below and in `tasks.md`/README, not
   silently dropped.

### Doc-update-map sweep
Walked every row of [TABLE_OF_CONTENTS.md#doc-update-map](../TABLE_OF_CONTENTS.md#doc-update-map):

- 🔴 journal — this entry.
- 🔴 task status — `tasks.md` T-110–T-115 added, all `done`.
- 🔴 doc create/move/status flip — none; no doc was created/moved/renamed (the journal is a new
  *file*, not a doc-registry change — it already has its standing map row).
- 🔴 `models.py`/`parsers.py`/`persistence/` schema change — **N/A, waived.** Confirmed zero
  `src/pipeguard/` files in any of the six diffs (`git diff --stat 04adeac 109557e -- src/ api/
  tests/` = empty, reproduced at session start).
- 🔴 test census (`quality/evaluation.md`) — **waived**, same reasoning as the Wave-7 sweep
  ([journal 2026-07-10 wave7](2026-07-10-frontend-batch7.md)): the frontend has no test runner
  wired into the pytest census (`package.json` scripts are `dev`/`build`/`tsc`/`lint`/`preview`
  only) — every prior frontend-only wave has used the same waiver, and `git diff --stat` confirms
  no `tests/` file changed.
- 🟠 `runbook.py`/`rules.py` → `qc_metrics.md` — N/A, no rule/threshold file touched.
- 🟠 `metrics/` registry → `metric_registry.md` — N/A, no metrics module touched.
- 🟠 `provenance.py`/`engine.py`/`EventType` → `data/provenance.md` — **considered and waived.**
  The Provenance-screen rewrite (PV1) is a pure frontend re-presentation of an ALREADY-shipped
  wire field (`RunDetail.events`, confirmed above) — it adds zero new event types, zero new
  backend fields, and zero ledger-format change. `data/provenance.md` documents the ledger's
  event vocabulary and format, which is unchanged; the frontend doc that owns "how the UI shows
  this" is `design/frontend/README.md` §5.6, updated below.
- 🟠 new advisory agent / model tier / corpus → `design/agents.md` — N/A, no agent touched.
- 🟠 `api/` endpoint or `frontend/` screen — new/changed capability → `architecture.md` +
  `data-platform-and-archivist.md` + `functional.md` (REQ-F). **Fired** — all six commits change
  frontend screen capability with zero `api/` change. Updated `architecture.md` (new Wave-8
  paragraph) and `functional.md` (REQ-F-042 fix + REQ-F-063/074/077 amendments + new REQ-F-078/
  079). **Waived `data-platform-and-archivist.md`** — that doc's scope is the data-platform/
  export/run-browser/archivist design; none of the six commits touch data-platform, export, or
  the archivist surface (confirmed: no `api/archivist.py` or export-endpoint reference in any
  diff).
- ⚪ load-bearing decision → new ADR — N/A, no new decision; see Decisions table below (empty by
  design — this is a sweep of already-shipped maintainer-directed UI work, not a decision
  session).
- ⚪ scope/wishlist/"built" change → `scope-and-wishlist.md` (+ `functional.md`, `tasks.md`) —
  **fired**; updated item 5 (Built-as-of) and wishlist item 11 (Pipeline builder).
- ⚪ files moved / module added / a map trigger rotted → `CLAUDE.md` code map + this map —
  **fired**; new Wave-8 paragraph added, no file moved across `src/`/`app/`/`data/`/`docs/`/
  `tests/`, no map trigger needed correcting this time (unlike Wave 7's dot-grid correction).

**Also considered:**
- `quality/risks.md` — **waived**, same reasoning as Wave 7: none of the six commits introduce a
  new access-control, data-integrity, or PHI risk. The builder's undo/redo is a client-side UX
  safety net (an *anti*-risk feature — the maintainer's "no accidental cascade" rule realized on
  the canvas, mirroring the Wave-3 `ConfirmDialog` retrofit), not a new exposure; its one
  documented limitation (locEdits not covered by undo) is a scope note, not a security/data risk.

## Decisions

| Decision | Distilled to |
|---|---|
| No new decision made this session — this is a documentation sweep of six already-shipped, maintainer-directed frontend commits, not a design/architecture choice. (Per the operating contract, CHK-3 only fires when a decision was made; it did not fire here.) | n/a |

## Open questions & TODO

- **IB4 (per-reminder Slack/Discord/Teams/email notification + cadence)** is explicitly deferred
  by the commit body itself — "the largest, next." No task row exists for it yet beyond the note
  inside T-113; flagging here in case the maintainer wants it split into its own task before
  work starts.
- **`Truncate.tsx` (G2) is shipped but unused** — a full-text-on-hover primitive with zero
  call sites anywhere in `frontend/src` besides its own definition. Either apply it to the
  overflow-prone labels it was presumably built for (run ids, sample names, artifact paths — the
  README/task note this Wave doesn't guess at which), or fold it into a future UI-polish task
  explicitly scoped to "apply Truncate."
- **`useTopologyHistory` covers topology only, not `locEdits`/`refLoc`** (locator/reference
  authoring) — a labelled scope boundary in the hook's own comment, not a bug. Extending undo to
  cover those would need a state-consolidation refactor per the commit body; no task exists for
  it yet.
- The spec's looser "≥2 edges" anti-cascade confirm threshold was **not** shipped — the commit
  body says the actual behavior is "any delete that severs ≥1 edge" confirms, which is *stricter*
  (safer) than spec, so this is a conservative deviation worth noting but not a gap to fix.

## Distilled into

- [CLAUDE.md](../../CLAUDE.md) §"Current code map" — new Wave-8 paragraph.
- [docs/planning/tasks.md](../planning/tasks.md) — T-110, T-111, T-112, T-113, T-114, T-115.
- [docs/design/architecture.md](../design/architecture.md) — new Wave-8 bullet, Related field.
- [docs/design/frontend/README.md](../design/frontend/README.md) — §4 (Tabs-vs-SegmentedControl
  convention, nav order), §5.1 (Submit S1-S3), §5.3 (Intake IG1), §5.5 (Review queue RQ2/RQ3 +
  Tabs), §5.6 (Provenance rewritten for PV1: Lineage/Event-trail/Artifacts + shared Pager), §6
  (Pipeline Builder on-canvas editing PB2, Truncate.tsx open item).
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-042 (screen-count +
  Provenance-description fix), REQ-F-063 (RQ2/RQ3 amendment), REQ-F-074 (S1-S3 amendment),
  REQ-F-077 (IB1-3,5-8 amendment, IB4 deferred), new REQ-F-078 (Provenance PV1), new REQ-F-079
  (Pipeline Builder PB2).
- [docs/requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — item 5
  (Built-as-of) amended; wishlist item 11 (Pipeline builder) amended with PB2.
