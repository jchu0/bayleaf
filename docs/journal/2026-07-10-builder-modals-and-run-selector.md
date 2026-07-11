# Journal — 2026-07-10 (MST) — Batch 7: Builder advisory-modal wiring, RunSelector, Monitoring per-run pagination

| Field | Value |
|---|---|
| **Focus** | Doc-keeper SWEEP for 3 commits (`34bca5d`→`adfd7aa`, T-069/T-070/T-072) landed after the Batch-6 sweep ([journal](2026-07-10-admin-settings-builder-wiring.md)). Ground every claim in the real diffs (`git show <sha>`), then walk the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) and update every doc it obligates, in the same sweep. |
| **Participants** | doc-keeper subagent (SWEEP mode) |
| **Outcome** | 3 commits swept, all frontend-only, all wiring-only (no verdict/gate/ADR-0001 boundary changed): Monitoring's per-run throughput columns gain client-side pagination — **frontend half only**, the backend `runs[]` payload stays uncapped (T-072 narrowed, not closed); a new reusable `RunSelector` component closes T-070; and the three remaining static Builder-modal previews (Run hand-off, pipeline-repair, archivist) plus saved-profiles "Open" close T-069 — the last of the Pipeline Builder's known, labelled deferrals from the T-062 rebuild onward. Docs updated: `docs/planning/tasks.md` (T-069/T-070 flipped to `done`, T-072 narrowed), `CLAUDE.md` code map (new Batch 7 paragraph + deferrals line), `docs/design/architecture.md` (new batch-7 bullet + deferrals paragraph rewritten), `docs/design/frontend/README.md` (§5.8 Monitoring, §6 Builder console/Run/Advisory-agents/Profile-control), `docs/design/data-platform-and-archivist.md` (new §4.8 + §4.6 cross-reference fix + §5 Archivist frontend-wiring note), `docs/requirements/functional.md` (REQ-F-045, REQ-F-047), `docs/requirements/scope-and-wishlist.md` (wishlist #11 row + item 4's stale `RunHandoffModal` claim). Backend/data-contract/test-census docs (`quality/evaluation.md`, `quality/risks.md`, `data/*.md`, `design/agents.md`, the ADR set): waived — see Decisions/map-sweep below. |

## Discussion

### Grounding pass (`git show`, before writing any doc)

Confirmed the three commits touch only `frontend/src/` — `git diff --stat a728cb7..adfd7aa -- src/ api/ tests/` (`a728cb7` = the commit immediately before this batch, per `git log --oneline`) returns empty, so no backend/test-census trigger fires this sweep.

1. **`34bca5d` (T-072 frontend half) — Monitoring: paginate the per-run rows.**
   `frontend/src/screens/Monitoring.tsx`: the shared `SigPerPage`/`SIG_PER_PAGE` type/const are
   generalized to `PerPage`/`PER_PAGE_OPTIONS` (used by both pagers now); new `runsPerPage`/
   `runsPage` state, a reset-to-page-1 `useEffect` on `[window, dateStart, dateEnd, runsPerPage]`,
   and `pagedRuns = chartRuns.slice(...)` feeding both the bar-chart `.map()` and the date-label
   `.map()` (previously `chartRuns.map(...)` directly, uncapped). `maxSamples` still computed over
   the full `chartRuns`, not `pagedRuns`, so the y-axis doesn't rescale between pages — read the
   diff to confirm this (line `const maxSamples = Math.max(...chartRuns.map(...))` is unchanged,
   above the new pagination block). A new "Showing X–Y of N runs" footer block is a near-exact
   copy of the existing signatures-pager footer (confirms the commit message's "ports the same
   scale-kit pattern verbatim" claim). **Confirmed still open:** `api/main.py`'s `get_monitoring`
   was not touched by this commit (not in the diff at all — only `Monitoring.tsx` changed) — the
   `runs: list[MonitoringRunRow]` field on the wire response is still returned in full; this commit
   bounds only what the frontend *renders*, matching the commit message's own "the backend `rows[]`
   cap remains an honest open item" framing. This closes only the frontend half of
   [tasks T-072](../planning/tasks.md); the row stays `todo`.
2. **`3c6455e` (T-070) — Builder: reusable searchable RunSelector for dry-run.**
   New `frontend/src/components/RunSelector.tsx` (174 lines): a controlled `value: string | null` /
   `onChange` combobox, self-fetching `api.runs(status ? { status } : undefined)` lazily on first
   `open` (only when no `runs` prop is injected), capped to `maxRows` (default 8) via
   `matches = filtered.slice(0, maxRows)`, filtering on `run_id`/`platform` substring
   (case-insensitive). Each row uses `RUN_STATUS_META[r.status].dot` — confirmed this is the same
   `verdict.ts` export the top-bar switcher (`TopBar.tsx`, T-074) already uses, so the dot reads the
   run's real lifecycle `status`, never `n_attention` (the F17 bug this repo has fixed twice now).
   On fetch failure: `error` state renders "Couldn't load runs." with zero rows — read the effect's
   guard (`if (injected || !open || fetched || loading || error) return`) and confirmed `error` is
   in both the guard *and* the dependency array, which is what prevents the classic "loading
   true→false re-triggers the effect → re-fires the failing request forever" bug the commit message
   calls out; `close()` resets `error` so reopening retries. `BuilderConsole.tsx`'s `runId` state
   changes from `useState('mock_run_01')` (a string) to `useState<string | null>(null)`; the
   Resolve button's `disabled` gains `|| !runId`. This closes [tasks T-070](../planning/tasks.md) —
   grepped `frontend/src/` post-commit for any other `RunPicker`/`RunSelector` definition; this is
   the only one, and it has exactly one consumer so far (`BuilderConsole`'s Dry-run tab). The
   `onViewAll`/`runs`/`status` props are unused by that one consumer — read as forward-looking, not
   yet exercised (no second consumer exists in this diff).
3. **`adfd7aa` (T-069) — Builder: wire the advisory agent modals + saved-profiles to real data.**
   The largest of the three (`+559/-40` across 6 files). Read `BuilderModals.tsx` in full:
   - `PipelineRepairModal`: two sequential `useEffect`s — (1) `api.monitoring('all', 25)` on mount,
     auto-selecting `d.signatures[0]?.signature` (backend sorts by count desc, confirmed by reading
     the existing `get_monitoring` signature-ranking logic is unchanged, not touched by this diff);
     (2) `api.signatureRepair(selected)` whenever `selected` changes, rendering the real
     `AgentProposal` fields (`summary`, `rationale`, `attach_to`, `scope`, `citations[]` — each with
     `score != null ? ... '% (heuristic)' : ...`, confirmed the label string is literally
     `(heuristic)`, never "confidence"). "Send to review queue" now calls `navigate('/queue')` +
     `toast(...)` instead of the old `onClose` no-op — confirmed no `POST /api/review/tickets` call
     was added (grepped the diff for `createTicket`/`ticketAction` — absent), so the commit
     message's "no fabricated ticket" claim holds structurally, not just in the copy.
   - `ArchivistModal`: one `useEffect` calling `api.archiveIndex()`, rendering a new
     `ArchiveIndexBody` component off the real `ArchiveDigest` fields (`n_runs`, `n_archive_ready`,
     `by_origin`, `by_status`, `proposed_action`, `recurring_signatures`, `disclaimer` — read
     verbatim into JSX, no re-authored language). "Queue archive" button — checked the diff for its
     `onClick`; it still just calls `onClose` (inert), confirmed no write endpoint was added.
   - `RunHandoffModal`: gains `profile`/`yaml`/`curLoc`/`savedName`/`onEmit` props (threaded from
     `PipelineBuilder.tsx`'s existing `yamlFor(profile, locEdits)` computation — not a new backend
     call, the same string the Emit console already renders); `onCopy` calls
     `navigator.clipboard.writeText(yaml)` then `onEmit()` (the pre-existing compose-only handler).
     The old button (`<ArrowRight/> Hand off to Nextflow`, `onClick={onClose}`) is gone — confirmed
     by the diff removing the `ArrowRight` import and that JSX block entirely.
   - Saved-profiles: `PipelineBuilder.tsx` gains `loadOpen` state + a toolbar "Open" button + a new
     `LoadSavedModal` (reads `api.listPipelines()`, an already-existing client method — grepped
     `api.ts`, unchanged by this diff) + `loadSavedPipeline(pg)` which sets
     `docKind='blank'`/`userNodes`/`userEdges`/`locEdits`/`refLoc`/`profile`/`version`/`saveStatus`/
     `savedName` from the chosen `PipelineGraph`, and `setMode(pg.status === 'approved' ? 'view' :
     'edit')` — confirmed this reuses the exact same `isLinked`/`showSeeded` machinery T-075 built
     (`docKind='blank'` ⟹ not the linked doc ⟹ `showSeeded=false` ⟹ the loaded nodes render, not the
     hardcoded seeded DAG). The "never fabricates nodes" claim: `if (!nodes.length) toast(...no
     builder topology to restore...)` — read this branch, confirmed it does NOT fall through to
     rendering anything.
   - `types.ts`: `AgentProposal` gains ~10 optional enrichment fields + `RepairCitation`; a new
     `ArchiveArtifactRef`/`ArchiveSignature`/`ArchiveCitation`/`ArchiveDigest` family mirrors the
     backend `api/archivist.py` pydantic models field-for-field (spot-checked `by_origin`,
     `by_status`, `n_archive_ready`, `archive_ready`, `disclaimer`, `content_hash` against
     `ArchiveDigest` in `api/archivist.py` — unchanged this diff, confirmed the frontend type is
     catching up to an already-existing backend shape, not the other way around).
   This closes [tasks T-069](../planning/tasks.md) — the row's own text named exactly these three
   modals + saved-profiles as the remainder after T-096 narrowed it; all four are now wired.

### Doc-update-map sweep

Walked every row of the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) against the 3
commits above:

- 🔴 unconditional journal row → this entry.
- 🔴 task-status row → `planning/tasks.md`: T-069 `in-progress`→`done`, T-070 `todo`→`done`, T-072
  description narrowed to "frontend half closed, backend half open" (status stays `todo` — the row
  describes the backend gap, which is still real).
- 🔴 doc create/move/rename/status-flip → N/A for `TABLE_OF_CONTENTS.md` specifically (this journal
  is a new file, but journals are tracked generically via the existing `journal/` directory row, not
  individually — matching how the Batch-5/Batch-6 journals were handled, confirmed by reading those
  journals' own "Distilled into" lists, neither of which touched `TABLE_OF_CONTENTS.md`).
- 🔴 `models.py`/`parsers.py`/`persistence/` field change → **N/A, confirmed**: `git diff --stat
  a728cb7..adfd7aa -- src/ api/` is empty.
- 🔴 test census (`tests/`) → **N/A, confirmed**: `git diff --stat a728cb7..adfd7aa -- tests/` is
  empty. `quality/evaluation.md`'s hardcoded count is untouched by this batch; not re-derived since
  nothing could have falsified it.
- 🟠 `runbook.py`/`rules.py` → N/A, untouched.
- 🟠 `src/pipeguard/metrics/` → N/A, untouched.
- 🟠 `provenance.py`/`engine.py`/`EventType` → N/A, untouched.
- 🟠 new advisory agent/model tier/corpus → **N/A, waived**: no new agent, model tier, or corpus was
  added — `PipelineRepairModal`/`ArchivistModal` now *consume* the already-built pipeline-repair
  (T-058) and archivist (T-059) agents' existing endpoints; grepped `docs/design/agents.md` for
  `T-069`/`T-070`/`T-072`/`RunSelector`/`BuilderModals`/`ArchivistModal`/`PipelineRepairModal` —
  zero hits, confirming that doc makes no claim this batch contradicts (it describes the agents
  themselves, not their frontend consumption). Not touched.
- 🟠 **`api/` endpoint or `frontend/` screen — new/changed capability** → **fires** (all 3 commits
  are frontend capability changes: a new pagination affordance, a new reusable component, and three
  modals gaining real data). Updated `design/architecture.md`, `design/frontend/README.md`,
  `requirements/functional.md` (REQ-F-045, REQ-F-047), and `design/data-platform-and-archivist.md`
  (new §4.8, the fourth instance of the scale-kit pagination pattern — a genuine "windowed
  aggregate" concern per that doc's §4.4/§4.5/§4.6/§4.7 family; also a one-line frontend-wiring note
  in §5, the Archivist section, since `ArchivistModal` now calls the endpoint that section
  documents).
- ⚪ load-bearing decision → **checked, none made**: all three commits wire already-decided backend
  seams (T-054/T-058/T-059/T-049, governed by ADR-0001/0003/0008/0009/0012/0016/0017) or are pure
  UI re-presentation (Monitoring pagination). No new/updated ADR.
- ⚪ scope/wishlist/"built" change → **fires**: `requirements/scope-and-wishlist.md` wishlist #11
  row explicitly named `RunHandoffModal`/`PipelineRepairModal`/`ArchivistModal` as "remain static
  previews" and T-070 as "stays open" — both corrected. Also found and fixed a second, older stale
  claim in that same doc (wishlist item 4, the pipeline-repair-agent row): "The Pipeline Builder's
  'Hand off to Nextflow' run modal stays a static preview (`RunHandoffModal`, T-069)" — that
  specific button no longer exists post-`adfd7aa` (confirmed above); reworded to describe the real
  copy-YAML button instead of leaving a dangling reference to a removed UI affordance.
- ⚪ files moved across top-level dirs / map trigger rot → N/A, no file moved across
  `src/`/`app/`/`data/`/`docs/`/`tests/`; `CLAUDE.md` code map needed the routine content refresh
  (the map row above fired) — done.
- **`quality/risks.md`** → **checked, waived**: no new write endpoint, no new auth surface, no new
  externally-reachable input path. `RunSelector` is a read-only `GET /api/runs` consumer (an
  already-risk-assessed endpoint); `PipelineRepairModal`/`ArchivistModal` are read-only `GET`
  consumers of already-built, already-advisory (off-gate, ADR-0001) endpoints. Grepped
  `docs/quality/` for the three task ids and every new component/modal name — zero hits, confirming
  no existing risk row references stale behavior either.

## Decisions

| Decision | Distilled to |
|---|---|
| All three commits are pure frontend consumption of already-decided, already-built backend seams (T-049/T-054/T-058/T-059, ADR-0001/0003/0008/0009/0012/0016/0017) or client-side re-presentation (Monitoring pagination) — no new ADR. Compose ≠ execute is unchanged: `RunHandoffModal`'s new Copy button fires `navigator.clipboard.writeText` + the pre-existing compose-only `onEmit`, no network call, confirmed by reading the diff | [architecture.md](../design/architecture.md) new batch-7 bullet, [functional.md](../requirements/functional.md) REQ-F-045 |
| T-072 is explicitly a two-part gap (frontend render cap vs backend payload cap); this batch closes only the frontend half — recorded as a narrowing, not a closure, in `tasks.md`, matching the pattern already established for T-069 by the Batch-6 sweep | [tasks.md](../planning/tasks.md) T-072 row |
| `quality/risks.md`: no new row — every new call site this batch is a read-only `GET` against an already-shipped, already-advisory (off-gate) endpoint; no new exploitable surface introduced | none — explicit waiver, see the map-sweep list above |
| `quality/evaluation.md` test census: **not** re-derived — confirmed via `git diff --stat a728cb7..adfd7aa -- tests/` (empty) that no test file changed this batch | none — explicit waiver |

## Open questions & TODO

1. **`RunSelector`'s `onViewAll`/`runs`/`status` props are unused so far** — the commit message
   frames the archivist/run-handoff surfaces as future consumers, but this batch didn't wire them
   (`RunHandoffModal` still has no run-selection UI — it renders the *current* builder graph's YAML,
   not a picked run's). Not a doc drift (nothing claims otherwise), just a forward-looking note.
2. `docs/design/frontend/README.md` still has no template metadata table (Status/Last-updated/
   Audience/Related) — flagged again in the Batch-5 and Batch-6 journals, still not fixed (would
   touch the whole file's structure, not just its content); flagging a third time rather than
   scope-creeping this sweep.
3. The "Author a tool node" Builder modal (T-046) remains the only static `phase-2` preview left in
   the Builder — correctly still a *design note, not built* per its own tasks.md row; no drift, just
   noting it as the natural next candidate if the maintainer wants full modal parity.

## Distilled into

- [docs/planning/tasks.md](../planning/tasks.md) — T-069/T-070 flipped to `done`; T-072 narrowed
  (frontend closed, backend open).
- [CLAUDE.md](../../CLAUDE.md) — Current code map item 4 (frontend paragraph): new Batch 7
  paragraph + deferrals line rewritten.
- [docs/design/architecture.md](../design/architecture.md) — new "Frontend fixes batch 7" bullet;
  deferrals paragraph rewritten; Related field gains this journal + the missing batch-6 journal
  link (a pre-existing gap, fixed opportunistically).
- [docs/design/frontend/README.md](../design/frontend/README.md) — §5.8 (Monitoring per-run
  pagination), §6 (Console RunSelector note, Run hand-off real-YAML note, Advisory-agents real-data
  note, Profile-control "Open" note).
- [docs/design/data-platform-and-archivist.md](../design/data-platform-and-archivist.md) — new
  §4.8 (Monitoring per-run pagination, frontend half); §4.6 cross-reference fixed; §5 gains a
  frontend-wiring note; Related field gains this journal.
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-045 (Dry-run
  run-selector + advisory-modal wiring + saved-profiles), REQ-F-047 (per-run pagination, frontend
  half); Related field gains this journal.
- [docs/requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — wishlist #11
  row (T-069/T-070 closed) and item 4's stale `RunHandoffModal` reference corrected; Related field
  gains this journal.
