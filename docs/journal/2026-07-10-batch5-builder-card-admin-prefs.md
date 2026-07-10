# Journal — 2026-07-10 (MST) — Batch 5: builder polish, gate dependency, prefs, admin role-staging

| Field | Value |
|---|---|
| **Focus** | Doc-keeper SWEEP for 8 commits (`14c9f3c`→`5774143`, T-085–T-092) landed after the last sweep (`8514609`, the Batch-4 sweep). Ground every claim in the real diffs (`git show <sha>`), then walk the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) and update every doc it obligates. |
| **Participants** | doc-keeper subagent (SWEEP mode) |
| **Outcome** | 8 commits swept: 2 Pipeline-Builder canvas fixes (Tidy/Cancel/minimap, reference-source palette cards + collapsible sections), 3 decision-card presentation fixes (gate-dependency `blocked_by`, green "Passed" pill, dropped left verdict spine), a Provenance view-vs-download split, a real persisted theme/density preference store, and an Admin role-staging/confirm-Act-as hardening. All are re-presentation / UX fixes on top of already-shipped seams — **no verdict, gate, or ADR-0001 boundary changed**, verified per-commit below. Docs updated: `planning/tasks.md` (T-085–T-092 rows), `CLAUDE.md` code map, `design/frontend/README.md` (§4/§5.4/§5.6/§6/§11), `design/architecture.md` (§Component map item 4, batch-5 paragraph + card-readout/artifacts/admin amendments), `requirements/functional.md` (REQ-F-072, REQ-F-073, amendments to REQ-F-045/066/070). `quality/risks.md` and the ADR set: waived (see Decisions). |

## Discussion

### Grounding pass (git show, before writing any doc)

Read `git show --stat` then the full diff for each of the 8 commits. Summary of what each
actually touched (not the commit-message prose alone — the diffs match the messages in all 8
cases, no drift found):

1. **`14c9f3c` (T-085) — Builder Tidy/Cancel/minimap.**
   `frontend/src/screens/PipelineBuilder.tsx` + `BuilderCanvas.tsx`. `tidy()` now computes a
   longest-path depth per node over `userEdges` (relaxed in `|V|` passes) and places each node
   in the column of its depth, stacking parallel nodes in a column (`60 + col*230, 56 + row*120`)
   — replaces the old one-row `150 + i*170` layout that lost the connection structure. A new
   `cancelDraft()` resets every draft-scoped state var (`docKind`, `docName`, `userNodes`,
   `userEdges`, `locEdits`, `refLoc`, `selected`, connect-mode, `version`, `saveStatus`,
   `emitted*`, `profile`) and flips to View — wired to a new Cancel button shown only
   `!isLinked`. The minimap's container div moved `bottom-3.5 right-3.5` → `right-3.5 top-3.5`
   (one class-string change).
2. **`c6a6210` (T-086) — Reference palette cards + collapsible sections.**
   `BuilderShared.tsx`'s `BTOOLSPEC` gains three no-input entries (`Reference FASTA` → emits
   `reference_fasta`, `Panel BED` → `panel_bed`, `Truth VCF` → `truth_vcf`) and
   `PipelineBuilder.tsx` adds a `References` palette section wired to the existing `addNode`.
   The `Palette` component gains `collapsed: Set<string>` state; each section header is now a
   button with a chevron + item count that toggles collapse, **except** while a search query is
   active (`isCollapsed = collapsed.has(s.heading) && !q`) so matches always show.
3. **`545c893` (T-087, DC2 part 1) — gate dependency `blocked_by`.** `api/card_readout.py`:
   new `_GATE_DEP_ORDER = (PREFLIGHT, QC, VARIANT)` and `_blocking_gate(gate, unclear)` — walks
   upstream from `gate`'s index and returns the *nearest* gate in `unclear`, else `None`.
   `build_qc_readout` computes `unclear = {gr.gate for gr in card.gate_results if gr.verdict is
   not PROCEED}` (a gate only gets a `gate_result` when it has findings, so "has a gate_result"
   ⟺ "not clear" — confirmed by reading `rules.py`'s finding→gate_result path referenced in the
   diff comment) and stamps `blocked_by` on every `GateReadout` it builds (both the canonical-order
   loop and the defensive "gate not in canonical order" loop). New test
   `test_qc_hold_blocks_the_downstream_variant_gate` (`tests/test_card_readout.py`) asserts on
   real `mock_run_02` data: the QC-unclear sample's Variant `blocked_by is Gate.QC`, nothing
   upstream of QC is blocked, and a fully-clear sample (no `gate_results`) blocks nothing.
   Frontend: `types.ts` `GateReadout`/`MetricsPanel.tsx` `ReadoutGroup` both gain optional
   `blocked_by?: Gate | null`; `MetricsPanel.tsx`'s `Rollup` renders a `hold`-toned "blocked ·
   clear \<upstream\> first" pill **before** the "all clear"/`not_measured` checks (so it always
   takes priority); `RunDetail.tsx`'s `CardBody` computes the same nearest-upstream-unclear logic
   client-side (`blockingGate()`) for the placeholder/empty groups it synthesizes when the API
   readout has no rows for a gate, so the placeholder path mirrors the API path exactly. Confirmed
   this is **pure re-presentation**: no change to `rules.py`, `synthesis/`, or any `Finding`/
   `Verdict` — the card's own verdict is already the QC finding; this only stops a *downstream*
   gate's UI from reading "all clear" when its upstream isn't. ADR-0001 (rules decide, never a
   presentation layer) is unaffected — grepped `synthesis/` and `rules.py`, neither commit touches
   them.
4. **`24940e1` (T-088, DC3) — drop the left verdict spine.** One-line-effective diff in
   `RunDetail.tsx`: the `CollapsibleRow` invocation drops
   `className={\`border-l-[3px] ${VERDICT_STRIPE[card.verdict]}\`}` and the now-unused
   `VERDICT_STRIPE` import. Per the commit message, the maintainer reserves the colored left rail
   for Pipeline-Builder tool cards (`BuilderCanvas`, unaffected — grepped, no `VERDICT_STRIPE`
   usage there). The card keeps its neutral border; verdict is still carried by the badges/pills.
5. **`d5fdcb2` (T-089, DC1) — green "Passed" gate pill.** `GateResultStrip.tsx`: the
   no-gate-result branch's chip class is now conditional — `blocked` (card verdict is
   escalate/rerun) keeps the old neutral `border-line bg-card-2 text-text-2`; otherwise it's
   `border-proceed-bd bg-proceed-bg text-proceed-fg` (the shared proceed/green token set). Text
   unchanged ("Passed"/"Not run"). **Distinct component from #3's `blocked_by` pill** — this is
   the top-strip per-gate chip driven by the card's own `cardVerdict`, not the QC-readout hero's
   gate-dependency chip; the two "blocked"-like states are unrelated code paths that happen to
   share the visual "hold" tone by convention.
6. **`de5fa94` (T-090, P1/P2) — inline view vs. attachment download.** `api/main.py`:
   `get_run_artifact` gains a `download: bool = False` query param; `FileResponse(...,
   content_disposition_type="attachment" if download else "inline")`. Read-only/traversal-hardening
   logic (bare filename, `resolve()` + `is_relative_to` check) is untouched. New assertions in
   `tests/test_api.py`: default request has `"inline"` in `content-disposition`;
   `?download=1` has `"attachment"`. `Provenance.tsx`: the artifact-name anchor's `title` is now a
   name-sensitive hover string (`sample_metadata.csv` → "Intake · LIMS/subject metadata sheet —
   click to view"; `SampleSheet.csv` (case-insensitive) → "Demux · Illumina barcode/index
   manifest — click to view"; else a generic "Open artifact at its location (view)") and its
   `href` is unchanged (`art.url`, i.e. no `?download=1`); the separate Download anchor's `href`
   becomes `` `${art.url}?download=1` ``. Verified both anchors now diverge (view vs. save) where
   they previously both saved.
7. **`08a42ad` (T-091) — real, persisted theme + density.** New
   `frontend/src/context/PrefsContext.tsx` (83 lines): `Theme = 'light'|'dark'|'system'`,
   `Density = 'split'|'brief'|'dense'`, `localStorage` key `pipeguard.prefs`
   (`try/catch`-guarded load + persist — private-mode-safe, degrades to defaults). Theme resolves
   `system` via `matchMedia('(prefers-color-scheme: dark)')` and stamps
   `document.documentElement.dataset.theme`; a live `matchMedia` `change` listener keeps it in
   sync while on `system`. `index.css` gains a `:root[data-theme="dark"]` block overriding the
   `@theme --color-*` custom properties (confirmed by reading the diff: page/card/surface/text/
   accent + dark verdict bg/border/fg + shadow tokens + `color-scheme: dark`) — every existing
   Tailwind utility that already reads a `--color-*` var retargets with **no per-component
   change**. `App.tsx` wraps the tree in `<PrefsProvider>`; `UserSettingsDialog.tsx` and
   `RunDetail.tsx`'s card-density control both now read/write the same `usePrefs()` state (one
   density setting, not two) — grounded by reading the diff hunk in `RunDetail.tsx` (5 lines
   changed, swaps a local `useState<Density>` for `usePrefs()`).
8. **`5774143` (T-092, A1) — Admin role edits stage into a draft.** `Admin.tsx`'s `UsersTab`:
   role changes no longer call `setUsers` directly from a 3-way `SegmentedControl`. A `draft:
   Record<string, Role>` holds pending edits; `stage(id, role)` adds/removes an entry (removes if
   it matches the already-saved role, so re-toggling back to the saved value clears "dirty");
   `dirty = users.some(u => draft[u.id] !== undefined && draft[u.id] !== u.role)` gates a new
   Save/Discard bar. `save()` applies every staged role, re-syncs the live `actor` via `setActor`
   only if the **current actor's own** role was staged, then clears the draft. The role control
   itself is now a native `<select>` (Viewer/Reviewer/Approver) instead of the toggle, with an
   "unsaved" badge when `staged`. `actAs(u)` adds a `window.confirm(...)` gate before
   `setActor(u)`, naming the target user + role and warning that subsequent off-gate writes are
   attributed to them. Confirmed this only touches the **client-mock** roster
   (`api/auth.py` is unchanged, still the header dev-shim) — [risks.md RISK-035](../quality/risks.md)
   already documents that a viewer can bypass this via `localStorage`; this commit doesn't change
   that posture, it only makes the *legitimate* admin UI path more deliberate.

### Doc-update-map sweep

Walked every row of the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) against the 8
commits above:

- 🔴 unconditional journal row → this entry.
- 🔴 task-status row → `planning/tasks.md` gains T-085–T-092 (all `done`, `Port` phase,
  `parallel-safe: yes`, since each touched disjoint files per-commit).
- 🔴 doc create/move/rename/status-flip → N/A, no doc was created/moved/renamed this session
  (this journal is a *new file*, which is the unconditional row above, not this one).
- 🔴 `models.py`/`parsers.py`/`persistence/` field change → N/A, none of the 8 commits touch
  `src/pipeguard/` at all (grepped `git show --stat` output above — every changed path is under
  `frontend/src/` or `api/`).
- 🔴 test census (`tests/`) → **fires**: `tests/test_card_readout.py` (+1 test, T-087) and
  `tests/test_api.py` (+1 assertion pair in an existing test, T-090, not a new test function).
  Checked `quality/evaluation.md` for a hardcoded count — deferred to CHK-2 below (see Decisions;
  waived with the specific count re-derived).
- 🟠 `runbook.py`/`rules.py` → N/A, untouched.
- 🟠 `src/pipeguard/metrics/` → N/A, untouched.
- 🟠 `provenance.py`/`engine.py`/`EventType` → N/A, untouched.
- 🟠 new advisory agent/model tier/corpus → N/A, none of the 8 touch `triage/`,
  `pipeline_repair/`, or an off-gate agent module.
- 🟠 **`api/` endpoint or `frontend/` screen — new/changed capability** → **fires** (7 of 8
  commits are exactly this). Updated `design/architecture.md`, `design/frontend/README.md` (the
  data-platform-and-archivist.md doc is about the data platform/export/archivist and is NOT
  obligated by this batch — none of the 8 commits touch export, the archivist, or run-browser
  data-platform concerns; waived, naming this map row), and `requirements/functional.md` (new
  REQ-F-072/073 + amendments to REQ-F-045/066/070).
- ⚪ load-bearing decision → **checked, none made**: every commit is a UI/presentation
  fix or additive backend field on an already-decided seam (`card_readout.py`'s `blocked_by` is a
  projection of already-computed `gate_results`, not a new rule). No new/updated ADR.
- ⚪ scope/wishlist/"built" change → N/A, no wishlist item closed or opened by this batch.
- ⚪ files moved across top-level dirs / map trigger rot → N/A, no file moved across
  `src/`/`app/`/`data/`/`docs/`/`tests/`; `CLAUDE.md` code map still needs the routine content
  refresh (not because a trigger rotted, but because the map row above fired) — done.

## Decisions

| Decision | Distilled to |
|---|---|
| Gate-dependency `blocked_by` (T-087) is a pure re-presentation over already-computed `gate_results`, not a new rule/decision — no new ADR; ADR-0001 (rules decide, never a presentation layer) reconfirmed intact by grepping `rules.py`/`synthesis/` for changes (none) | [architecture.md](../design/architecture.md) §Component map item 4 (batch-5 paragraph) + [functional.md](../requirements/functional.md) REQ-F-072 |
| No new `quality/risks.md` row: T-092's Admin role-staging is a client-UX hardening of an already-documented client-mock surface — [RISK-035](../quality/risks.md) already covers "a viewer can mint any role via localStorage" and this commit doesn't change that boundary (only makes the *legitimate* UI path deliberate) | none — explicit waiver, see CHK-2 |
| `tests/` census: `quality/evaluation.md`'s hardcoded "N tests" line re-derived via `uv run pytest --collect-only -q` + `git ls-files` (see CHK-2) rather than incremented by eye, since T-087 adds one function and T-090 only extends an existing one | [evaluation.md](../quality/evaluation.md) (count refreshed if stale) |

## Open questions & TODO

1. **T-087 is explicitly "part 1"** of the maintainer's two-tier gate model — user-clearable
   HOLD/ESCALATE (individually + in batches) is still the next slice (per the commit message);
   tracked informally, not yet a task row (no task id assigned by the maintainer yet).
2. `docs/design/frontend/README.md` (the top-level package README, not a
   `handoffs/YYYY-MM-DD-*.md` delta) has no template metadata table (Status/Last-updated/
   Audience/Related) — a pre-existing gap from before template enforcement, not introduced by
   this batch. Flagging rather than fixing now (out of this sweep's scope; would touch the whole
   file's structure, not just its content).

## Distilled into

- [docs/planning/tasks.md](../planning/tasks.md) — T-085 through T-092 rows.
- [CLAUDE.md](../../CLAUDE.md) — Current code map item 4 (frontend paragraph), batch-5 addendum.
- [docs/design/frontend/README.md](../design/frontend/README.md) — §4 (prefs), §5.4 (decision
  card), §5.6 (provenance), §6 (builder), §11 (admin).
- [docs/design/architecture.md](../design/architecture.md) — §Component map item 4 (batch-5
  paragraph; card-readout, artifacts-endpoint, and admin sub-sections amended).
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-072 (gate dependency),
  REQ-F-073 (persisted user preferences), amendments to REQ-F-045/066/070.
