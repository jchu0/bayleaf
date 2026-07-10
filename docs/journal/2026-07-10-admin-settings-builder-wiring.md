# Journal — 2026-07-10 (MST) — Batch 6: Admin activity/System, Settings sample-type, Builder Dry-run/Diff wiring

| Field | Value |
|---|---|
| **Focus** | Doc-keeper SWEEP for 4 commits (`8a14661`→`4208f0b`, T-093–T-096) landed after the last sweep (`eb01915`, the Batch-5 sweep). Ground every claim in the real diffs (`git show <sha>`), then walk the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) and update every doc it obligates. |
| **Participants** | doc-keeper subagent (SWEEP mode) |
| **Outcome** | 4 commits swept, all frontend-only, all re-presentation/UX or wiring an already-built backend seam — **no verdict, gate, or ADR-0001 boundary changed**: Admin Activity-log pagination + expandable rows (T-093); Admin System gained Observability links + an Artifact-store card + a per-user password-reset action (T-094); Settings' runbook-threshold table replaced two side-by-side sample-type columns with a dropdown (T-095); and — the highest-value fix — the Pipeline Builder's Dry-run/Diff console tabs now call the REAL `POST /{name}/dry-run` / `GET /{name}/diff` endpoints once a graph is Saved (T-096), closing a "known, labelled limitation" carried in four docs since the T-062 rebuild. Docs updated: `CLAUDE.md` code map, `planning/tasks.md` (T-093–T-096 new rows + T-069/T-070 narrowed), `design/frontend/README.md` (§5.10/§6/§11), `design/architecture.md` (Admin bullet + new batch-6 bullet + deferrals paragraph), `requirements/functional.md` (REQ-F-045/062/066 amendments), `requirements/scope-and-wishlist.md` (wishlist #11 row), `design/data-platform-and-archivist.md` (new §4.7 + item-10 addendum). `quality/evaluation.md`, `quality/risks.md`, `data/*.md`, and the ADR set: waived (see Decisions). |

## Discussion

### Grounding pass (`git show`, before writing any doc)

Read `git show --stat` then the full diff for each of the 4 commits. All four touch only
`frontend/src/` — confirmed via `git diff --stat eb01915 4208f0b -- tests/ src/ api/` returning
empty, so no backend/test-census trigger fires this sweep.

1. **`8a14661` (T-093, "A2") — Admin: paginate the activity log + expandable rows.**
   `frontend/src/screens/Admin.tsx`'s `ActivityTab`: new `ActPerPage` (`'25'|'50'|'100'`) state +
   a `SegmentedControl`, `page`/`openKey` state (`useEffect(() => setPage(1), [filter, perPage])`
   resets on filter change), `rowKey(r)` (a composite `when|kind|target|detail` string, since
   rows have no server id) drives which row is expanded (one at a time). Each row is now a
   `<button>` summary (chevron rotates on open) that reveals a `<dl>` Detail/Target/Actor/When
   panel beneath it. A pager (‹ / `curPage / pages` / ›) plus "Showing X–Y of Z" appears when
   there's more than one page. **No backend change** — still the same `Promise.all([listThresholds,
   listPipelines, listTickets])` merge (confirmed unchanged in the diff — only the render path
   changed).
2. **`7c56564` (T-094, "A3/A4") — Admin: System observability + artifact store + password reset.**
   Same file. `SystemTab` gains a 4th `StatCard` ("Artifact store" · `local` ·
   `PIPEGUARD_ARTIFACT_STORE · s3 seam` — grounded: `src/pipeguard/artifacts/__init__.py` defines
   exactly this env var, T-039) and an `OBS` array of three links (`Prometheus /metrics` at
   `${apiBase}/metrics`, `Prometheus` at `localhost:9090`, `Grafana` at `localhost:3000` — grounded:
   `docs/ops/telemetry-connectors.md` already documents these same two ports from T-036/T-079, no
   drift), rendered as `target="_blank"` cards with a note to `docker compose -f
   deploy/telemetry/docker-compose.yml up`. `UsersTab` gains a `resetPassword(u)` handler that
   only calls `toast(...)` — no network call, no live mail, explicitly labelled a "production seam
   (no live mail here)" in the toast copy itself, so the UI doesn't imply a capability that isn't
   there.
3. **`869cf55` (T-095, "S1") — Settings: sample-type dropdown.**
   `frontend/src/components/SettingsAssayTable.tsx`: a new `sampleType: 'blood'|'saliva'` state
   + a `<select>` beside the existing Assay dropdown. The threshold-matrix grid drops from
   `grid-cols-[1.4fr_1fr_1fr]` (metric + two value columns) to `grid-cols-[1.6fr_1fr]` (metric +
   one value column keyed off `r[sampleType]`); `editCell(i, sampleType, value)` replaces the two
   separate `editCell(i, 'blood', …)`/`editCell(i, 'saliva', …)` call sites. Confirmed by reading
   the diff that the underlying `Row` shape (`{ blood, saliva, ... }`), the save/approve handlers,
   and the audit lifecycle are untouched — this is a pure display re-layout, not a data-model or
   RBAC change.
4. **`4208f0b` (T-096, "Item E") — Pipeline builder: wire Dry-run/Diff to the real endpoints.**
   The one commit worth the most doc attention — it closes a limitation repeated verbatim across
   **four** docs (`CLAUDE.md`, `design/architecture.md`, `requirements/functional.md` REQ-F-045,
   `requirements/scope-and-wishlist.md` wishlist #11) since the T-062 frontend rebuild landed with
   `api.ts`'s `dryRunPipeline`/`pipelineDiff` defined but never called. Confirmed both were
   already wired in `api.ts` (`POST /api/pipelines/{name}/dry-run?run_id=…`,
   `GET /api/pipelines/{name}/diff`, both built under T-054/REQ-F-061 — grepped, unchanged by this
   commit) — this commit is purely the frontend caller. `frontend/src/screens/PipelineBuilder.tsx`
   gains `savedName`/`dryRun`/`dryRunBusy`/`diff`/`diffBusy` state; `onBackendDryRun(rid)` /
   `onBackendDiff()` call `api.dryRunPipeline`/`api.pipelineDiff` and are only enabled once
   `savedName` is set (stamped by `onSave` right after `submitPipeline` succeeds — i.e. the graph
   genuinely exists in the pipeline store, not merely "the user clicked Save"). New/Cancel reset
   `savedName`/`dryRun`/`diff`, so a fresh draft doesn't show stale resolution results.
   `frontend/src/components/BuilderConsole.tsx`: the Dry-run tab gains a plain `<input>` for
   `run_id` (default `'mock_run_01'`, **not** a searchable/paginated picker — confirmed by reading
   the diff, this is a bare `useState('mock_run_01')` text box) + a "Resolve against run" button;
   when `props.dryRun` is set it renders the real `DryRunResult.locators[]` (matched/ambiguous/
   missing/invalid, via a new `RESOLVE_CHIP` color map distinct from the old client-preview
   `DRY_CHIP`), else it falls back to the pre-existing client-side `dry`/`dryStats` preview. Same
   pattern for Diff: `props.diff` (a real `DiffResult` with `added`/`changed`/`removed`/
   `unchanged_count`/`has_baseline`/`emitted_version`) renders when present, else the old
   `diffRows`-vs-last-Emit preview. Confirmed the maintainer's own verification note in the commit
   message is honest, not optimistic: "Dry-run returned 'v2 vs run mock_run_01 · missing 10'
   (honest — a frozen run dir has no raw pipeline paths); Diff returned '10 added' (never approved
   → no baseline)" — i.e. the wiring surfaces a *real*, unflattering result rather than a happy-path
   demo fake, which is exactly the honesty bar this project holds itself to.
   **What's still NOT wired** (grepped `frontend/src/` for `archive-digest`/`archive/index` call
   sites — only `api.ts`'s own definitions, no caller; grepped `BuilderModals.tsx` for `phase-2` —
   still present on `PipelineRepairModal`/`ArchivistModal`): `RunHandoffModal` /
   `PipelineRepairModal` / `ArchivistModal` remain static previews, and saved-profiles has no
   backend seam. This narrows [tasks T-069](../planning/tasks.md) rather than closing it, and
   [tasks T-070](../planning/tasks.md) (a reusable run-selector) is still open — the new Dry-run
   run-id field is a raw text box, not that component, and `RunHandoffModal` (T-069's first
   blocked consumer) still has no run-selection UI at all.

### Doc-update-map sweep

Walked every row of the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) against the 4
commits above:

- 🔴 unconditional journal row → this entry.
- 🔴 task-status row → `planning/tasks.md` gains T-093–T-096 (all `done`, `Port` phase; T-093/
  T-094 marked `partial` parallel-safe since both touch `Admin.tsx`); T-069 narrowed to
  `in-progress` (Dry-run/Diff sub-item now done, Export/Archivist-modal + saved-profiles remain);
  T-070 left `todo` with a note that a first raw (non-searchable) consumer now exists.
- 🔴 doc create/move/rename/status-flip → N/A, no doc was created/moved/renamed this session
  (this journal is a *new file*, which is the unconditional row above, not this one).
- 🔴 `models.py`/`parsers.py`/`persistence/` field change → **N/A, confirmed**: `git diff --stat
  eb01915 4208f0b -- src/ api/` is empty — none of the 4 commits touch `src/pipeguard/` or `api/`
  at all, only `frontend/src/`.
- 🔴 test census (`tests/`) → **N/A, confirmed**: `git diff --stat eb01915 4208f0b -- tests/` is
  empty. `quality/evaluation.md`'s hardcoded count is untouched by this batch; not re-derived
  since nothing could have falsified it.
- 🟠 `runbook.py`/`rules.py` → N/A, untouched (no backend change at all this batch).
- 🟠 `src/pipeguard/metrics/` → N/A, untouched.
- 🟠 `provenance.py`/`engine.py`/`EventType` → N/A, untouched.
- 🟠 new advisory agent/model tier/corpus → N/A, none of the 4 touch `triage/`,
  `pipeline_repair/`, or an off-gate agent module (the Archivist reads stay uncalled, not newly
  wired).
- 🟠 **`api/` endpoint or `frontend/` screen — new/changed capability** → **fires** (all 4
  commits). Updated `design/architecture.md`, `design/frontend/README.md`,
  `requirements/functional.md` (amendments to REQ-F-045/062/066), and — for T-093's Admin
  activity-log pagination specifically, a genuine instance of the already-tracked "scale kit"
  pattern (§4.5/§4.6) — `design/data-platform-and-archivist.md` gained a new §4.7 (T-094's
  observability/artifact-store/password-reset and T-095's sample-type dropdown are Admin-
  governance/Settings UI, not data-platform/scale-kit concerns, so they were routed to
  `architecture.md`/`functional.md` only, not a new data-platform section).
- ⚪ load-bearing decision → **checked, none made**: every commit either wires an
  already-decided backend seam (T-096 calls endpoints ADR-0001/0003/0014/0016/0017 + REQ-F-061
  already govern) or is pure UI re-presentation (T-093/T-094/T-095). No new/updated ADR.
- ⚪ scope/wishlist/"built" change → **fires**: T-096 closes a limitation
  `requirements/scope-and-wishlist.md`'s wishlist #11 row explicitly named ("Dry-run/Diff/
  Export/Archivist backend seams... are unwired in the UI... wiring Dry-run is itself blocked on
  a run-selector"). Corrected — Dry-run/Diff are wired; the run-selector claim was specifically
  about *that* being the blocker, which is no longer accurate (it shipped with a plain text
  input instead), so the row now separates "Dry-run/Diff: wired" from "T-070 (reusable picker):
  still open" rather than conflating them.
- ⚪ files moved across top-level dirs / map trigger rot → N/A, no file moved across
  `src/`/`app/`/`data/`/`docs/`/`tests/`; `CLAUDE.md` code map needed the routine content
  refresh (the map row above fired) — done.

## Decisions

| Decision | Distilled to |
|---|---|
| T-096 (Dry-run/Diff wiring) is a pure frontend consumption of an already-built, already-decided backend seam (T-054/REQ-F-061, ADR-0001/0003) — no new ADR; the "compose ≠ execute" invariant is unchanged (dry-run still globs paths, reads no bytes, `executed: false` is hard-coded server-side, confirmed unchanged by this diff) | [architecture.md](../design/architecture.md) §Component map batch-6 bullet, [functional.md](../requirements/functional.md) REQ-F-045 |
| No new `quality/risks.md` row: T-094's password-reset action and Prometheus/Grafana links are labelled production seams / off-demo-path links over already-shipped, already-documented ports ([telemetry-connectors.md](../ops/telemetry-connectors.md)) — no new exploitable surface, no live mail, no new claim introduced that isn't already true of the running system | none — explicit waiver, see the map-sweep list above |
| `quality/evaluation.md` test census: **not** re-derived — confirmed via `git diff --stat eb01915 4208f0b -- tests/` (empty) that no test file changed, so the count cannot have gone stale this batch | none — explicit waiver |

## Open questions & TODO

1. **T-069 is now a narrower deferral**, not closed: `RunHandoffModal`/`PipelineRepairModal`/
   `ArchivistModal` remain static `phase-2` previews and saved-profiles has no backend seam. Not
   re-scoped into a new task id — the existing T-069 row absorbs the narrowing (see tasks.md).
2. **T-070** (reusable run-selector) is unblocked-but-still-open: `BuilderConsole`'s Dry-run tab
   now has a *first* consumer for "pick a run_id" (a plain text input), which arguably lowers the
   urgency of building the full searchable/paginated component, but `RunHandoffModal` still has
   zero run-selection UI. Left as-is; flagging that the task's "why it matters" framing may be
   worth revisiting with the maintainer now that a manual workaround exists.
3. `docs/design/frontend/README.md` still has no template metadata table (Status/Last-updated/
   Audience/Related) — a pre-existing gap flagged in the Batch-5 journal, not fixed there either
   (would touch the whole file's structure, not just its content); flagging again rather than
   scope-creeping this sweep.

## Distilled into

- [docs/planning/tasks.md](../planning/tasks.md) — T-093 through T-096 new rows; T-069/T-070
  updated.
- [CLAUDE.md](../../CLAUDE.md) — Current code map item 4 (frontend paragraph), batch-6 addendum,
  deferrals line fixed.
- [docs/design/frontend/README.md](../design/frontend/README.md) — §5.10 (Settings), §6
  (Builder console), §11 (Admin Activity log + System).
- [docs/design/architecture.md](../design/architecture.md) — §Component map (Admin bullet
  extended; new batch-6 bullet; Dry-run/Diff limitation + deferrals paragraph fixed).
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-045, REQ-F-062,
  REQ-F-066 amended; top-level Related field.
- [docs/requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — wishlist #11
  row corrected.
- [docs/design/data-platform-and-archivist.md](../design/data-platform-and-archivist.md) — new
  §4.7 (Admin activity-log pagination); item 10 addendum (frontend now calls dry-run/diff).

---

## Addendum — T-097: review-queue batch clearance (DC2 part 2)

Landed in the same session tail as the sweep above (commit `a8fd059`), separate from the doc-keeper
run: the code change is frontend-only (`ReviewQueue.tsx`), the last open item from the Batch-5 list.

**Context.** The maintainer's DC2 gate model has two parts. Part 1 (T-087, commit `545c893`) wired
the two-tier gate *dependency* into the readout — a QC hold makes the downstream variant gate read
"blocked · clear QC first" rather than "all clear." Part 2 is the *clearance* half of the model:
"holds and escalate should both be clearable by the user individually or in batches, so in that
sense HOLD is just a state while ESCALATE is requesting user input." The review queue already
cleared tickets **individually** (backend-persisted); this adds the **batch** path.

**What shipped.** Reviewers+ (`isReviewer`, matching the reviewer+approver RBAC on resolve/suppress,
REQ-F-063) now get a select checkbox on every still-open (open/in-review) ticket, plus a per-run
select-all in the group subheader. Selecting ≥1 raises a sticky batch bar ("N selected — Resolve
selected / Suppress selected / Cancel"). Both batch actions loop the existing per-ticket
`act('resolve')` / `toggleSuppress()` handlers, which already **materialize the ticket + persist**
the action to the review store (`createTicket` → `ticketAction`), so a bulk clear is durable exactly
like a single click — no new backend, no new endpoint.

**Invariants held.** Off-gate: clearing a ticket never touches a verdict or finding (ADR-0001,
REQ-F-004). Selection resolves against the *live* ticket list on every render, so a key that has
since left the clearable set (already resolved, or filtered away) can never re-fire an action.
Viewers see no checkboxes (read-only).

**Verified** live as approver (`s.ops`) on `/queue`: selected two open tickets in one run → *Resolve
selected* → **Open 88→86, Resolved 1→3**, the fully-cleared run left the Open view, and the state
**persisted across a full page reload** (re-fetched counts Open 86 / Resolved 3). `tsc --noEmit` +
`oxlint` clean.

**Docs owed & done:** [functional.md](../requirements/functional.md) REQ-F-072 (part-2 note flipped
from "not yet built" to shipped) and [tasks.md](../planning/tasks.md) (new T-097 row); the
`project-qc-gate-dependency-model` session memory now marks both parts built. No backend/
data-contract/test-census docs owed (frontend-only; `git diff --stat` on `src/`/`api/`/`tests/` is
empty for `a8fd059`).
