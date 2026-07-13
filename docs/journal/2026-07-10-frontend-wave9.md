# Journal — 2026-07-10 (MST) — frontend Wave 9: canonical Bar + Truncate applied, page-access RBAC + Sample accessioning

| Field | Value |
|---|---|
| **Focus** | Doc-keeper SWEEP for two maintainer-directed frontend commits landed on `main` after the Wave-8 sweep (`3e592d8`→`66b14e4`), verified frontend-only via `git diff --stat 109557e 66b14e4 -- src/ api/ tests/` (empty): (1) a canonical `Bar` component consolidating every distribution/meter bar in the app + the first real application of the Wave-8 `Truncate.tsx` primitive (G3/G2); (2) a client-side page-access RBAC view-gate + a new sample-accessioning CRM screen (`/accession`, G1). Named **"Wave 9"** in the code-map narrative per the task instruction, continuing after "Wave 8" (T-110–T-115). |
| **Participants** | maintainer (UI feedback); doc-keeper subagent |
| **Outcome** | Both commits' owed docs updated in one pass: `CLAUDE.md` code map (new "Wave 9" paragraph), `docs/planning/tasks.md` (T-116, T-117), `docs/design/architecture.md` (new Wave-9 bullet + screen-count bump 11→12 + Related), `docs/design/frontend/README.md` (§4 nav/page-access note, §5.1 Submit handoff crosslink, §5.2 Runs Bar note, new §5.12 Sample accessioning, §6 Truncate note fixed, §9 Tokens Bar consolidation, §11 Admin gains the "Page access" tab as item 2), `docs/requirements/functional.md` (REQ-F-042 amended to 12 screens, new REQ-F-081/REQ-F-082, Notes/deferred #4 fixed + two new deferred notes), `docs/requirements/nonfunctional.md` (REQ-NF-023 amended, new REQ-NF-024), `docs/requirements/scope-and-wishlist.md` (item 5 Wave-9 paragraph, wishlist item 11's stale Truncate claim fixed), `docs/design/data-platform-and-archivist.md` (a G-DEID frontend-precursor note under §2.1d), `docs/quality/risks.md` (a related-but-distinct client-side-gate addendum under RISK-035). No `src/bayleaf/`, `api/`, `tests/`, or ADR file touched (verified below); no design deliverables (`briefs/`, `handoffs/`, `source/`, `bayleaf.html`) touched. |

## Discussion

### Grounding — what the two commits actually did

Read each commit's full diff (`git show <sha>` / `git show <sha> --stat`) and the actual current
source files (not just the commit body), per the "ground every claim in code" rule.

1. **`3e592d8` — canonical Bar component (G3) + Truncate applied (G2).** Read
   `frontend/src/components/Bar.tsx` in full (45 lines): `SegmentBar` (a proportional
   multi-segment distribution bar — zero-value segments filtered out so the strip never lies about
   the mix) and `MeterBar` (a single value against a track), both `h-2 · rounded-[5px]` with 2px
   segment gaps, colors passed as full Tailwind utility classes (not interpolated, so the compiler
   emits them). Confirmed by grep that all five claimed consumers actually import from it:
   `DecisionVerdictBar.tsx` and `ReviewStatusBar.tsx` both `import { SegmentBar } from './Bar'`;
   `RunOverview.tsx` imports `SegmentBar`; `Intake.tsx` and `Monitoring.tsx` both
   `import { MeterBar } from '../components/Bar'`, each with an inline comment naming the
   consolidation ("canonical MeterBar, G3"). Read `components/Truncate.tsx` in full (40 lines): a
   `ResizeObserver`-measured single-line truncation primitive that only attaches a native `title`
   when `el.scrollWidth > el.clientWidth + 1`. Confirmed its first real application: `grep -n
   Truncate frontend/src/screens/RunDetail.tsx` → one import + one JSX use at line 288 wrapping the
   decision-card headline; `grep -rln Truncate frontend/src` now returns exactly two files —
   `RunDetail.tsx` and the component's own definition — confirming the commit's own framing ("a
   broader sweep… remains the remaining G2 follow-up") is accurate: one site, not a full sweep.
2. **`66b14e4` — page-access RBAC view-gate + Sample accessioning (G1).** Read `access.ts` (155
   lines) and `context/AccessContext.tsx` (147 lines) in full. `access.ts`'s own header comment
   states the invariant directly: "a client-side VIEW-GATE, NOT a security control… it never
   authorizes a server write. The wire role… continues to govern every real write via
   `api/auth.py`'s `require_role`, entirely unchanged." Confirmed against the diff: `git show
   66b14e4 -- api/` returns nothing — `api/auth.py` is untouched. `effectivePages()` re-asserts
   `ACCESS_FLOOR` (`['runs', 'cards']`) as its literal last statement before returning, matching
   the "no deny can strand a user" claim. `AccessContext`'s `canSee` callback is
   `isAdmin || !store.enforce || canSeePage(store.map, actor.id, page)` — resolved against
   `actor.id` (the ACTING identity from `useRole()`, which Admin's "Act as" reassigns), not the
   login identity, confirming the "Act-as previews the impersonated user's nav" claim. Read
   `App.tsx`'s diff: `<RequirePage page="…">` wraps every operator route; the `/admin` route
   retains no `page` prop, so it stays governed solely by its pre-existing `isAdmin` check — the
   diff shows this explicitly (no line added to that specific route). Read `Sidebar.tsx`'s diff:
   `useNav` now does `groups.map(g => ({...g, items: g.items.filter(it => it.page == null ||
   canSee(it.page))})).filter(g => g.items.length > 0)` — untagged (Admin) items always pass, and
   an emptied group is dropped. Read `screens/Accession.tsx` (400 lines) and `lib/accession.ts`
   (168 lines) in full: `grep -c "api\." screens/Accession.tsx lib/accession.ts` confirms **zero**
   API calls in either file — every action (`exportCsv`, `saveDraft`, `sendToIntake`) touches only
   `localStorage`/`Blob`/`URL.createObjectURL`. The PII banner's claim that
   `POST /api/runs` rejects a subject field was checked against
   `api/routers/intake.py`'s actual `SubmitRunIn`/`SampleIn` models (`extra="forbid"`, no
   `subject_id`/`tissue` field present — confirmed by reading the file, not just trusting the
   banner text). `AccessionRecord` has no `dob`/`mrn` field at all (confirmed reading the type
   definition) — the "DOB/MRN deliberately not collected" claim is a type-level guarantee, not
   just a UI omission. Read `Submit.tsx`'s diff: a new `useEffect` calls `readHandoff()` on mount,
   pre-attaches `{subject_id, tissue}` via the existing `sampleMeta`/`samples` merge path (the same
   one the pre-existing `sample_metadata.csv` upload already used), then `clearHandoff()` — a
   genuine one-shot courier, not a persistent duplicate store. Read `Admin.tsx`'s diff: a new
   `access` `FeedKind` is merged into the Activity log's `rows` (backend rows + client-side
   `accessRows` from `useAccess().audit`, sorted together), each carrying a `clientSide: true`
   badge rendered distinctly — confirming the "merged in, clearly badged" claim rather than a
   silent conflation with the three backend-persisted kinds.

### Doc-update-map sweep

Walked every row of [TABLE_OF_CONTENTS.md#doc-update-map](../TABLE_OF_CONTENTS.md#doc-update-map):

- 🔴 journal — this entry.
- 🔴 task status — `tasks.md` T-116, T-117 added, both `done`.
- 🔴 doc create/move/status flip — none; no doc was created/moved/renamed (this journal is a new
  *file*, not a doc-registry change — it already has its standing map row).
- 🔴 `models.py`/`parsers.py`/`persistence/` schema change — **N/A, waived.** Confirmed zero
  `src/bayleaf/` files in either diff (`git diff --stat 109557e 66b14e4 -- src/ api/ tests/` =
  empty, reproduced at session start and again per-commit above).
- 🔴 test census (`quality/evaluation.md`) — **waived**, same reasoning as every prior
  frontend-only wave (Wave 7/8 journals): the frontend has no test runner wired into the pytest
  census (`package.json` scripts are `dev`/`build`/`tsc`/`lint`/`preview` only); `git diff --stat`
  confirms no `tests/` file changed in either commit.
- 🟠 `runbook.py`/`rules.py` → `qc_metrics.md` — N/A, no rule/threshold file touched.
- 🟠 `metrics/` registry → `metric_registry.md` — N/A, no metrics module touched.
- 🟠 `provenance.py`/`engine.py`/`EventType` → `data/provenance.md` — N/A, neither commit touches
  the ledger, event vocabulary, or any provenance-reading screen.
- 🟠 new advisory agent / model tier / corpus → `design/agents.md` — N/A, no agent touched (the
  page-access editor and Accession screen are CRM/governance surfaces, not advisory-agent ones).
- 🟠 `api/` endpoint or `frontend/` screen — new/changed capability → `architecture.md` +
  `data-platform-and-archivist.md` + `functional.md` (REQ-F). **Fired** — both commits change
  frontend capability with zero `api/` change. Updated `architecture.md` (new Wave-9 bullet +
  screen-count bump) and `functional.md` (REQ-F-042 amendment + new REQ-F-081/REQ-F-082).
  **`data-platform-and-archivist.md` also fired this time** (unlike Wave 8's waiver) — the new
  Accession screen directly instantiates that doc's G-DEID guardrail discussion (`subject_id`/
  `tissue` intake identity) and its own §2.2(C) item 3 ("persist intake by widening
  `sample.registered`") describes exactly the backend slice this screen is a client-side precursor
  to; added a short grounded note under §2.1d rather than leaving the doc silently unaware of a
  now-built, directly-related frontend capability.
- ⚪ load-bearing decision → new ADR — **N/A, no new decision.** This is a sweep of two
  already-shipped, maintainer-directed UI commits, not a design/architecture choice; the
  page-access model follows the pre-existing `isAdmin`-capability pattern rather than establishing
  a new one. See Decisions table below (empty by design).
- ⚪ scope/wishlist/"built" change → `scope-and-wishlist.md` (+ `functional.md`, `tasks.md`) —
  **fired**; updated item 5 (Built-as-of, new Wave-9 paragraph) and fixed wishlist item 11's now-
  stale "Truncate has no call sites" claim (it now has one, per the #1-priority drift the doc-
  keeper contract flags: a built feature still marked not-built).
- ⚪ files moved / module added / a map trigger rotted — new modules (`components/Bar.tsx`,
  `access.ts`, `context/AccessContext.tsx`, `screens/Accession.tsx`, `lib/accession.ts`,
  `lib/csv.ts`) were **added**, not moved across `src/`/`app/`/`data/`/`docs/`/`tests/`; no map
  trigger needed correcting. `CLAUDE.md` code map updated with a new Wave-9 paragraph.

**Also considered:**
- `quality/risks.md` — **not a hard map row, but extended anyway.** The page-access view-gate is
  thematically identical to RISK-035 (a client-side gate that could be mistaken for real access
  control) — added a short, explicitly-scoped addendum under RISK-035 rather than a new RISK-NNN,
  since it shares the same category/likelihood/impact/mitigation shape and is, if anything,
  lower-severity (narrower blast radius: it only hides nav, never grants a write, and is
  self-labelled at the point of use).
- `design/agents.md` — considered and correctly waived; neither commit touches an advisory agent
  (confirmed: no `triage/`, `pipeline_repair/`, `feedback_agent.py`, or `archivist.py` reference in
  either diff).

## Decisions

| Decision | Distilled to |
|---|---|
| No new decision made this session — this is a documentation sweep of two already-shipped, maintainer-directed frontend commits, not a design/architecture choice. (Per the operating contract, CHK-3 only fires when a decision was made; it did not fire here.) | n/a |

## Open questions & TODO

- **Broader `Truncate` sweep still open.** One call site now exists (decision-card headline); the
  Wave-8 journal's suggestion (run ids, sample names, artifact paths) is still unaddressed. Not
  re-flagged as a new item — `tasks.md T-116` and `functional.md`'s Notes/deferred both carry it
  forward from the Wave-8 open item, narrowed rather than duplicated.
- **Page-access enforcement stays client-side only** (REQ-NF-024) — a production deployment needs
  a server-side page/read-access check to close the gap the editor's own banner names. No task
  exists yet for that backend slice; flagging here in case the maintainer wants it split out.
- **`subject_id`/`tissue` persistence** (the Accession→Submit handoff) is still parsed and
  displayed client-side only — the data-platform design's §2.2(C) item 3 ("widen
  `sample.registered`") is the backend slice that would close this, gated by G-PII/G-DEID. No
  change to that item's `todo` status; the frontend now has a working precursor UI for it.

## Distilled into

- [CLAUDE.md](../../CLAUDE.md) §"Current code map" — new Wave-9 paragraph.
- [docs/planning/tasks.md](../planning/tasks.md) — T-116, T-117.
- [docs/design/architecture.md](../design/architecture.md) — new Wave-9 bullet, screen-count
  11→12, Related field.
- [docs/design/frontend/README.md](../design/frontend/README.md) — §4 (nav order + page-access
  view-gate note), §5.1 (Accession→Submit handoff crosslink), §5.2 (Bar geometry note), new §5.12
  (Sample accessioning), §6 (Truncate note corrected), §9 (canonical Bar consolidation), §11
  (Page access tab as item 2, Activity log extended).
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-042 (12 screens,
  page-access layer noted), new REQ-F-081 (Bar/Truncate), new REQ-F-082 (page-access + Accession),
  Notes/deferred #4 fixed + two new deferred notes.
- [docs/requirements/nonfunctional.md](../requirements/nonfunctional.md) — REQ-NF-023 amended
  (third client-side-PII instance), new REQ-NF-024 (page-access view-gate posture).
- [docs/requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — item 5
  (Built-as-of, Wave-9 paragraph), wishlist item 11 (stale Truncate claim fixed).
- [docs/design/data-platform-and-archivist.md](../design/data-platform-and-archivist.md) — a
  frontend-precursor note under §2.1d G-DEID.
- [docs/quality/risks.md](../quality/risks.md) — a related-but-distinct addendum under RISK-035.
