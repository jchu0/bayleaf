# Journal — 2026-07-10 (MST) — Settings: model-tiering → a scale-aware agent table with explicit edit

| Field | Value |
|---|---|
| **Focus** | Doc-keeper SWEEP for 1 commit (`7b579bb`, "Wave 5," ST1/ST2) landed after the Wave-3 doc sweep ([journal](2026-07-10-confirm-dialog-audit-gate.md), commit `d65c9c1` → sweep commit `c79f62c`). Ground every claim in the real diff (`git show 7b579bb`), confirm frontend-only, then walk the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) and update every doc it obligates, in the same sweep. |
| **Participants** | doc-keeper subagent (SWEEP mode) |
| **Outcome** | 1 commit swept, frontend-only (`git diff --stat c79f62c 7b579bb -- src/ api/ tests/` empty), no verdict/gate/ADR-0001 boundary changed. Rebuilds `frontend/src/components/SettingsModelTier.tsx`: the old 3-item model-tiering card (dropdowns applied on change) is now a TABLE of the full 7-row advisory-agent roster (Agent · Purpose · Model · Status · Edit), capped 10 rows/page + a pager, with an explicit pencil→staged-draft→Save/Cancel edit flow. The 7th row (metrics-expansion agent, ST2) is a **labelled phase-2 UI placeholder with no backend module or env var** — confirmed by grep, not added anywhere as a shipped agent. Docs updated: `docs/planning/tasks.md` (new T-103 row), `CLAUDE.md` (new paragraph in code-map item 4), `docs/design/frontend/README.md` (§5.10 Settings bullet rewritten), `docs/requirements/functional.md` (new REQ-F-076 + Related crosslink), `docs/design/architecture.md` (new short bullet in the frontend-fixes sequence + Related crosslink), `docs/design/data-platform-and-archivist.md` (new §4.10, the scale-kit pattern's newest surface + Related crosslink). Waived with reasons below: `docs/design/agents.md`, `docs/adr/ADR-0012-agent-scoping-model-tiering.md`, `docs/requirements/scope-and-wishlist.md`, `docs/quality/risks.md`, `docs/quality/evaluation.md`, `data/schemas.md`/`provenance.md`/`metric_registry.md`, `data/licensing.md`/`requirements/constraints.md`, `ops/telemetry-connectors.md`, `demo/*.md`. |

## Discussion

### Grounding pass (`git show`, before writing any doc)

Confirmed the date first: `git log -1 --format=%ci 7b579bb` → `2026-07-10 19:08:46 -0700` — the
`-0700` offset matches this repo's MST (UTC-7, Arizona-style, no DST) convention, same calendar
date as the Wave-3/Wave-4/batch-8 sweeps that preceded it. Confirmed frontend-only:
`git diff --stat c79f62c 7b579bb -- src/ api/ tests/` returns **empty** — no backend/
data-contract/test trigger fires this sweep (waives the whole 🔴 `models.py`/`parsers.py`/
`persistence/` row, the 🔴 test-census row, and the 🟠 `runbook.py`/`rules.py`/`metrics/`/
`provenance.py` rows outright — all subsets of this empty diff). Read the full diff
(`git show --stat`/`git show`): 1 file, `frontend/src/components/SettingsModelTier.tsx`,
`+189/-40`.

1. **The roster (`AGENTS` array).** Now 7 entries, each `{ key, label, desc, def, env, where?,
   phase2? }`: `synthesizer` (`BAYLEAF_SYNTHESIZER`), `qc_triage` (`BAYLEAF_TRIAGE_AGENT`),
   `pipeline_repair` (`BAYLEAF_PIPELINE_REPAIR_AGENT`), `archivist`
   (`BAYLEAF_ARCHIVIST_AGENT`), `feedback` (`BAYLEAF_FEEDBACK_AGENT`), `node_author`
   (`BAYLEAF_NODE_AUTHOR`, `where: 'builder'`), `metrics_expand`
   (`BAYLEAF_METRICS_AGENT`, `phase2: true`). Cross-checked the first five env-var strings
   against the real backend: `grep -rn "BAYLEAF_SYNTHESIZER\|BAYLEAF_TRIAGE_AGENT\|
   BAYLEAF_PIPELINE_REPAIR_AGENT\|BAYLEAF_ARCHIVIST_AGENT\|BAYLEAF_FEEDBACK_AGENT" src/
   api/` — all five are real, live env switches (`src/bayleaf/engine.py`,
   `src/bayleaf/triage/agent.py`, `src/bayleaf/pipeline_repair/agent.py`,
   `api/feedback_agent.py`, `api/archivist.py`). Then checked the other two:
   `grep -rn "BAYLEAF_NODE_AUTHOR\|BAYLEAF_METRICS_AGENT" src/ api/` — **zero hits**. Neither
   env var exists server-side. This is expected for `node_author` (roster #5 in
   [agents.md](../design/agents.md) is explicitly "proposed — design note for review," T-046, not
   built) but is a real honesty point to carry into the docs for `metrics_expand`, which has
   **no roster entry, no design note, and no code anywhere** — it is purely this commit's UI
   label for a new idea (ST2). The commit message itself already calls this out ("labelled
   phase-2, no backend metric-authoring endpoint yet"), so the docs only need to preserve that
   framing, not invent anything further.
2. **Explicit edit.** `editing`/`draft` state + `beginEdit`/`cancelEdit`/`saveEdit`: `saveEdit()`
   does `setRows((prev) => ({ ...prev, [editing]: draft }))` then clears `editing`/`draft` — this
   is **the only state mutation in the whole file**; there is no `api.ts` import, no `fetch`, no
   `useEffect` syncing to a backend. Confirmed: `grep -n "api\.\|fetch(" frontend/src/components/
   SettingsModelTier.tsx` (post-commit) finds nothing. So "Save" here means "commit the draft to
   local React state," full stop — a page refresh loses it, same as before this commit. This
   matters for the doc claim: T-045 already flagged "per-agent model tiering (Settings screen,
   UI-only, not wired to `BAYLEAF_*_MODEL`)" as an open, honestly-labelled gap; this commit
   does **not** close that gap, it only makes the UI that sits on top of it scale better and
   apply more deliberately. Every doc edit below says this explicitly rather than let "Save"
   read as if it now persists.
3. **Pagination.** `PER_PAGE = 10`, `pages = Math.ceil(AGENTS.length / PER_PAGE)` — with 7 rows
   `pages === 1`, so the pager itself doesn't render yet (`{pages > 1 && (...)}`), but the cap is
   real and will engage the moment an 8th agent is added. Confirmed this matches the
   already-established "scale-kit" pagination pattern used four other places
   ([data-platform-and-archivist.md §4.5–§4.8](../design/data-platform-and-archivist.md)) and a
   fifth not yet given its own subsection (Agent-triage's 10-row pager, T-099) — same
   `SegmentedControl`-free numbered-pager idiom, same "Showing X–Y of N" caption shape.
4. **"New agent" crosslink.** A `<Link to="/builder">` — confirmed `/builder` is a real route
   (`PipelineBuilder.tsx`, already documented in [README.md §6](../design/frontend/README.md) as
   the node-author agent's home) — not a dead link or a placeholder.
5. **No frontend test file changed** (confirmed: this repo's frontend has no test framework
   configured, established precedent from the Wave-3/confirm-dialog sweep — `tsc`/`oxlint` + live
   manual verification is the established pattern here, not a new gap this commit introduces).

### Doc-update map sweep

Walked [the map](../TABLE_OF_CONTENTS.md#doc-update-map) row by row against the confirmed
frontend-only diff:

1. **🔴 ANY working session** → owed this journal. Done.
2. **🔴 A task changes status / is created** → owed `planning/tasks.md`. Fired — new T-103 row,
   depends on T-045 (the task that first landed the now-superseded 3-item card).
3. **🟠 `api/` endpoint or `frontend/` screen — new/changed capability** → owed
   `design/architecture.md` + `design/data-platform-and-archivist.md` +
   `requirements/functional.md` (REQ-F). **All three fired** — this is a real, if narrow,
   frontend-screen capability change (a card → a scalable table + an explicit-edit flow).
   `functional.md`: new REQ-F-076, placed in the "Authoring lifecycle, RBAC & operator surfaces"
   section (continuing REQ-F-075's local numbering) since it shares that section's explicit-edit
   theme, and crosslinked back to REQ-F-042 (which first described the Settings screen) and
   REQ-F-075 (the ConfirmDialog precedent this table's Save/Cancel staging echoes, even though it
   doesn't reuse that exact component). `architecture.md`: a short bullet appended to the
   "Frontend fixes batch N" sequence (after batch 8), matching the brevity T-095's analogous
   Settings-only change got in batch 6 — no new Invariant, since nothing about *what* the app can
   do to a verdict/gate changed. `data-platform-and-archivist.md`: a new **§4.10**, because this
   is concretely another instance of the doc's own tracked "scale-kit pagination pattern"
   (§4.5–§4.9) — the doc already has a standing convention of giving each new instance its own
   dated subsection, so skipping one here would be an inconsistent omission, not a legitimate
   waiver.
4. **⚪ Files moved / a module added / a map trigger rotted** → owed `CLAUDE.md` code map. Fired
   — no module was added or moved, but the code map's item 4 (`frontend/`) already narrates the
   Settings screen's history in detail (Batch 5's Sample-type dropdown, T-095), so a change to
   what that screen does belongs in the same running paragraph for discoverability. New
   paragraph added just before the closing `src/bayleaf/synthetic/` sentence.
5. **🟠 A new advisory agent anywhere (`synthesis/`, `triage/`, or an off-gate one) / a model
   tier / a corpus** → owed `design/agents.md` + the relevant ADR. **Deliberately NOT fired** —
   checked carefully per the task's explicit instruction. The trigger's own wording is "a new
   advisory agent **anywhere**" — read narrowly as *anywhere in the codebase* (i.e., an
   implementation), not "anywhere it's mentioned in a UI label." Grounded this reading against
   the grounding-pass finding above: `BAYLEAF_METRICS_AGENT` has zero hits in `src/`/`api/` —
   there is no module, no agent class, no corpus, no ADR-0009 retrieval seam, nothing that could
   be "added to the roster" in the sense [agents.md](../design/agents.md)'s roster table means it
   (each existing row links to a real module: `triage/`, `pipeline_repair/`, `api/archivist.py`,
   `api/feedback_agent.py`, or — for the one still-proposed row, node-authoring — a real design
   doc, [node-authoring-agent.md](../design/node-authoring-agent.md)). Adding a metrics-expansion
   row to that table with no design doc behind it would be worse than not mentioning it: it would
   put an unbuilt, undesigned idea on the same table as a genuinely-proposed one (node-authoring,
   which at least has a design note), collapsing a real distinction the table exists to preserve.
   **Decision: waived**, per the task's own instruction ("do NOT add it to design/agents.md as a
   shipped agent") — and mentioned instead only in the docs that describe the Settings *screen*
   (README.md, functional.md, architecture.md, tasks.md, CLAUDE.md), every time explicitly
   labelled "phase-2," "no backend module or env var," and "not a shipped roster addition," with
   a pointer back to `agents.md` so a reader who goes looking finds the real roster, not a
   dangling reference. `ADR-0012` (agent scoping/model tiering): read in full — its Decision and
   "Realized" sections are about which agents get built and their model-tier defaults; this
   commit changes neither (no new agent shipped, no `BAYLEAF_*_MODEL` default changed) — waived.
6. **⚪ A load-bearing decision made/realized/superseded** → a new ADR or an existing ADR's
   Decision/Status + a journal Decisions row. Considered: is "the metrics-expansion agent is a
   phase-2 idea, not built" itself a decision worth an ADR? No — it is the **absence** of a
   decision (an idea logged, not committed to), and ADR-0012 already establishes the pattern
   ("roster ideas land as a row first, then graduate to a design doc/ADR + implementation" —
   [agents.md](../design/agents.md) §Intake) for exactly this situation; this commit doesn't even
   clear the first bar of that pattern (no roster row, by design — see item 5 above). No new ADR.
7. **⚪ Scope / wishlist / "built" changes** → `requirements/scope-and-wishlist.md`. **Not
   fired** — grepped for "model tier"/"agent designer"/"New agent"/"metrics-expansion"/"ST1"/"ST2"/
   "scale-aware": zero hits in this doc. Nothing there claims "one-click apply" or omits an
   agent-designer as a wishlist item today, so nothing goes stale. Waived.
8. **Catch-all / risk.** Considered `quality/risks.md` — is "this table's Save doesn't persist
   anything" a new risk? No: it is the **same, already-tracked** gap T-045 logged (a
   presentation-only rebuild of a pre-existing UI-only card), not a new one this commit
   introduces, and it carries no security/RBAC/data-handling dimension the way the login gate
   (RISK-035) does. Waived — no new risk row.

**Waived, with reasons:** `design/agents.md` (map row 5 above — no backend agent module/env var
exists for the new roster row; adding it would misrepresent an unbuilt idea as a designed
proposal); `adr/ADR-0012-agent-scoping-model-tiering.md` (read in full — no agent shipped, no
model-tier default changed); `requirements/scope-and-wishlist.md` (grepped, zero hits, nothing
stale); `quality/risks.md` (no new risk — the UI-only gap this table sits on is already tracked
via T-045, not newly introduced); `quality/evaluation.md` (no test change — `git diff --stat
c79f62c 7b579bb -- tests/` empty, and this repo's frontend has no test-file census tracked there
at all); `data/schemas.md`/`data/provenance.md`/`data/metric_registry.md` (no wire-contract,
event-vocabulary, or metric change — confirmed by the empty `src/`/`api/` diff, a superset check);
`data/licensing.md`/`requirements/constraints.md` (no new dependency — the diff touches exactly
one `.tsx` file, `frontend/package.json` untouched); `ops/telemetry-connectors.md` (no `/metrics`
series change); `demo/*.md` (no demo-flow or command change — this is Settings-screen presentation
work, not a run-of-show step).

## Decisions

| Decision | Distilled to |
|---|---|
| The metrics-expansion agent (ST2) stays a UI-only label, not a roster addition — no row in [design/agents.md](../design/agents.md), no ADR, because no backend module/env var/design doc exists for it; every doc that mentions it (README.md, functional.md, architecture.md, tasks.md, CLAUDE.md) labels it phase-2/proposed and points back to the real roster | [design/frontend/README.md](../design/frontend/README.md) §5.10, [functional.md REQ-F-076](../requirements/functional.md), [tasks.md T-103](../planning/tasks.md) |
| The Settings agent table's explicit Save/Cancel does not close the T-045 "UI-only, not wired to `BAYLEAF_*_MODEL`" gap — it is a presentation rebuild only (verified: `saveEdit()` only calls `setRows`, no `api.ts` write exists) — every doc touched says this explicitly rather than implying persistence | [CLAUDE.md](../../CLAUDE.md) code map §4, [architecture.md](../design/architecture.md), [data-platform-and-archivist.md §4.10](../design/data-platform-and-archivist.md) |

## Open questions & TODO

- If/when the metrics-expansion agent idea graduates past a UI label (a design doc, then a
  `src/bayleaf/`/`api/` module + `BAYLEAF_METRICS_AGENT` env var), it needs a real roster row
  in [design/agents.md](../design/agents.md) (roster #6) following the intake checklist there —
  this session deliberately did not pre-create that row.
- The Settings model-tiering table (this commit and its T-045 predecessor) has never been wired
  to the backend `BAYLEAF_*_MODEL` env vars — an open item for whenever Settings authoring
  (REQ-F-062) grows a real "apply model tier" write path; not scoped to this sweep.
- `docs/design/frontend/README.md` still has no metadata table (Status/Last updated/Audience/
  Related) — a pre-existing gap already flagged in the Wave-3/Wave-4/Batch-8 journals, still out
  of this sweep's narrow scope.

## Distilled into

- [docs/planning/tasks.md](../planning/tasks.md) — new T-103 row.
- [CLAUDE.md](../../CLAUDE.md) — new paragraph in the frontend code-map entry (item 4).
- [docs/design/frontend/README.md](../design/frontend/README.md) — §5.10 Settings bullet rewritten (table + explicit edit + New-agent crosslink).
- [docs/requirements/functional.md](../requirements/functional.md) — new REQ-F-076 + Related crosslink.
- [docs/design/architecture.md](../design/architecture.md) — new short bullet in the frontend-fixes sequence + Related crosslink.
- [docs/design/data-platform-and-archivist.md](../design/data-platform-and-archivist.md) — new §4.10 + Related crosslink.
