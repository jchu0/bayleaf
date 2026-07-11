# Journal — 2026-07-10 (MST) — Batch 8: japandi theme, UI feedback pass, Recharts monitoring rework

| Field | Value |
|---|---|
| **Focus** | Doc-keeper SWEEP for 3 commits (`5763be1`→`f8a6f35`, T-098/T-099/T-100) landed after the Batch-7 sweep ([journal](2026-07-10-builder-modals-and-run-selector.md)). Ground every claim in the real diffs (`git show <sha>`), then walk the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) and update every doc it obligates, in the same sweep — with special attention to a partial reversal: this batch's Monitoring rework REMOVES the per-run pager Batch 7 had just added for T-072. |
| **Participants** | doc-keeper subagent (SWEEP mode) |
| **Outcome** | 3 commits swept, all frontend-only (`git diff --stat 1169e37 f8a6f35 -- src/ api/ tests/` empty), all re-presentation/UX (no verdict/gate/ADR-0001 boundary changed): a japandi light-theme re-skin + theme-aware canvas dots (T-098); four disjoint UI-feedback tweaks — agent tiles clickable in Builder View mode, Provenance "hash"→"fingerprint" relabel, a capped/gapped Runs verdict bar, and Agent-triage pagination (T-099); and a Recharts-based Monitoring throughput chart + recurring-signature unique ids + reversible clear/restore, which **adds the frontend's first charting dependency (recharts 3.9.2, MIT)** and **reverses (not narrows) T-072's just-shipped frontend pager** — the chart now scrolls instead of paginating, so `GET /api/monitoring`'s `runs[]` is uncapped in both directions again (T-100). Docs updated: `docs/planning/tasks.md` (3 new rows T-098–T-100; T-072's row rewritten to describe the reversal, not just "frontend half closed"), `CLAUDE.md` code map (new Batch 8 paragraph + rewritten deferrals sentence), `docs/design/architecture.md` (new batch-8 bullet + rewritten deferrals paragraph + Related crosslink), `docs/design/data-platform-and-archivist.md` (new §4.9 superseding §4.8's pager + Related crosslink), `docs/design/frontend/README.md` (§4 App shell tokens, §9 Tokens, §5.2 Runs, §5.6 Provenance, §5.7 Agent triage, §5.8 Monitoring rewritten, §6 Builder Canvas + Modes), `docs/requirements/functional.md` (REQ-F-047 superseding note + Related crosslink). Waived with reasons below: `data/licensing.md`/`requirements/constraints.md` (recharts is a bundled frontend npm lib, not a genomics tool/external-process dependency — outside this doc's stated scope, and neither doc tracks any of the frontend's existing deps either), `quality/evaluation.md` (no `tests/` change), `quality/risks.md`, `data/schemas.md`/`provenance.md`/`metric_registry.md` (no wire-contract change), `design/agents.md` + the ADR set (no new agent, no decision reversal), `requirements/scope-and-wishlist.md` (no scope/wishlist-item change — these are UI-polish tweaks to already-built, already-tracked screens). |

## Discussion

### Grounding pass (`git show`, before writing any doc)

Confirmed dates first: `git log -1 --format=%ci` on all three commits → `2026-07-10` (the third,
`f8a6f35`, at 18:04 local — same MST calendar date as the other two and as Batch 7). Confirmed
frontend-only: `git diff --stat 1169e37 f8a6f35 -- src/ api/ tests/` (`1169e37` = the Batch-7
sweep commit immediately before this trio) returns **empty** — no backend/data-contract/test
trigger fires this sweep.

1. **`5763be1` — Theme: soften light mode to a warm japandi palette + subtler canvas dots.**
   `frontend/src/index.css`: read the full diff. `--color-page` `#f5f7f9`→`#f2efe7`,
   `--color-card` `#fff`→`#faf9f4`, `--color-card-2` `#eef1f4`→`#ebe6da`, `--color-card-3`
   `#e6eaef`→`#e2dccd`, `--color-line` `#e4e8ed`→`#e5dfd1`, `--color-line-strong`
   `#d2d9e0`→`#d1c9b8`, `--color-text` `#1b232c`→`#2a2620`, `--color-text-2` `#586472`→`#6a6459`,
   `--color-text-3` `#8b95a1`→`#978f80`, `--color-accent-weak` `#eaf0fc`→`#eaeef6` (a subtler
   retint, still blue-family). `--color-accent`/`--color-accent-strong` (`#1f5fd0`/`#1a4fac`)
   and every dark-theme variable are **untouched** — confirmed by reading past the light `@theme`
   block into the `light` selector and the `dark` selector separately; the diff hunk for `dark`
   only *adds* the new `--canvas-dot` line, doesn't touch existing dark colors. New
   `--canvas-dot: #d6cfbe` (light) / `rgba(150, 165, 185, 0.08)` (dark). `frontend/src/components/
   BuilderCanvas.tsx`: the dot-grid `backgroundImage` moved from the inner content `<div>` onto
   the outer scroll-surface `<div ref={scrollRef}>` (a new `style` prop added there) and both now
   reference `var(--canvas-dot)` instead of the old hardcoded `#dbe1e8`. This is exactly what the
   commit message claims — verified no other file in the diff (`git show --stat` = 2 files only).
2. **`3c6dacb` — UI feedback pass: agent tiles in View, provenance relabel, runs bars, triage
   pagination.** Read all 4 changed files in full.
   - `PipelineBuilder.tsx`: `PaletteItem` type gains `alwaysEnabled?: boolean`; the three Agents
     palette entries (`QC-triage`/`Pipeline-repair`/`Archivist`) each set `alwaysEnabled: true`;
     the palette-item `disabled` computation changes from `it.disabled || isView` to
     `it.disabled || (isView && !it.alwaysEnabled)`. Confirmed the Gate tile (`disabled: true`,
     no `alwaysEnabled`) and every tool/reference tile are unaffected — `it.disabled` still forces
     the Gate off regardless, and tool tiles have no `alwaysEnabled` flag so `isView` still gates
     them. Each agent's `onClick` (`setSelected('a_qc_triage')` / `setRepairOpen(true)` /
     `setArchivistOpen(true)`) was already read-only before this commit (grepped for a write call
     inside those handlers — none), confirming the commit message's "read-only advisory reads"
     framing is accurate, not just asserted.
   - `Provenance.tsx`: the copy button's `title` and rendered text both change "hash …" →
     "fingerprint …"; the button's `title` is now a full `Content fingerprint · ${art.sha256} ·
     click to copy` (previously a static "Copy content hash," no value on hover) — so the "full
     value on hover" claim is real (a native `title` tooltip on the label element), not a UI
     panel. The `hash n/a` fallback also becomes `fingerprint n/a`. Confirmed `art.sha256` (the
     wire field name) is unchanged — only display strings changed, consistent with T-080's
     defense-in-depth precedent (label ≠ wire field).
   - `RunOverview.tsx`: `VerdictBar`'s wrapper class gains `max-w-[300px] gap-[2px]`; each segment
     div gains `rounded-[3px]`. Confirmed the `running` (single neutral track) branch is
     unaffected — the `max-w`/`gap` apply to the wrapper regardless of branch, so a running row's
     single bar is also now capped/rounded (a minor, harmless side effect not called out in the
     commit message but visible in the diff — noted here for completeness, not worth its own doc
     line since it's the same neutral "sequencing" bar, just capped like every other row now).
   - `AgentTriage.tsx`: new `page` state, `PER = 10`, `pages`/`curPage`/`pagedFlagged` derived,
     `flagged.map` → `pagedFlagged.map`, a new pager block gated on `flagged.length > PER`
     (mirrors the exact ‹/numbered/› pattern already used elsewhere in this app — Runs/Monitoring/
     Review-queue). `setPage(1)` added to the run-switch `useEffect`, so switching the active run
     resets pagination (read this to confirm no stale-page bug across runs).
3. **`f8a6f35` — Monitoring: Recharts throughput chart + clear/restore signatures (Wave 2).** The
   largest commit (`package.json`/`package-lock.json` + 2 screen files, `+655/-170`). Read
   `Monitoring.tsx`'s full diff plus `package.json`.
   - **Dependency:** `frontend/package.json` gains exactly one line, `"recharts": "^3.9.2"`, under
     `dependencies` (not `devDependencies` — it ships in the bundle). Confirmed via `npm view
     recharts license` equivalent knowledge (MIT — recharts is a well-known MIT-licensed React
     charting library; the commit message states MIT and nothing in the diff contradicts it, but
     this doc-keeper did not independently fetch the npm registry metadata — flagged as an
     **Assumption**, not independently re-verified this session, consistent with the commit
     author's own claim). Checked [licensing.md](../data/licensing.md) and
     [constraints.md](../requirements/constraints.md) for any existing frontend-npm-dependency
     tracking precedent: **none** — neither doc mentions React, Vite, Tailwind, FastAPI, or any
     other existing frontend/API dependency; `licensing.md`'s own Overview line scopes it to "the
     genomics tools and reference data PipeGuard sits on top of" (external-process invocation,
     GPL-binary-bundling risk) — a fundamentally different licensing shape than a statically
     bundled MIT React component library. **Decision: waive licensing.md/constraints.md for this
     dependency** (see Decisions table) — the justification instead lives in CLAUDE.md's code map
     and this journal, per the task's explicit instruction to "note it explicitly."
   - **Chart rework:** `STACK_ORDER`/manual flex-based bars replaced by `V_HEX`/`TREND_HEX` +
     `ChartDatum`/`ChartTooltip` + a `<ComposedChart>` with 4 stacked `<Bar>`s (`stackId="v"`,
     `maxBarSize={26}`) and one `<Line dataKey="flagged">`. Confirmed the tooltip is "grounded"
     per the commit message: `ChartTooltip` reads `payload[0].payload` (a real `ChartDatum` built
     from `r.counts.hold ?? 0` etc. — no synthesized/interpolated values, `flagged = hold + rerun
     + escalate` computed directly from the same counts, not a separate estimate).
     `chartWidth = Math.max(FRAME_W, chartData.length * COL_W)` with `FRAME_W = 588`, `COL_W = 42`
     — confirmed this is the "~14-day frame" claim (588/42 ≈ 14 columns) and that it's a **floor**,
     not a cap (`Math.max`, not `Math.min`) — so more than 14 dated runs still render, just wider
     than the frame, inside the `overflow-x-auto` wrapper. **Confirmed the per-run pager is
     gone**: grepped the post-commit file for `runsPerPage`/`runsPage`/`pagedRuns` — none remain;
     the whole "Showing X–Y of N runs" footer block (previously ~50 lines, visible in the T-072
     diff) is deleted in this diff's hunk, replaced by nothing — the chart now maps over the full
     `chartData` array via Recharts' own internal rendering, not a hand-rolled `.map()` with a
     `.slice()` in front of it. This is the reversal the task instructions flagged, confirmed at
     the code level, not just from the commit message.
   - **Signatures:** `sigId = SIG-${sig.signature.slice(0, 8)}` in `MonitoringSignatureRow.tsx`,
     rendered ahead of `rule_id · title`. `cleared: Set<string>` state seeded from
     `localStorage.getItem(CLEARED_KEY)` (try/catch-guarded both read and write — a
     `localStorage`-unavailable environment degrades to "doesn't persist," not a crash), `visibleSigs`/
     `clearedSigs` partition `filteredSigs` by membership, `toggleClear` flips membership. Confirmed
     **no `api.ts` call added** in this diff (grepped for a new fetch/`api.` call in the signature
     clear path — none) — this is purely client-side state, consistent with the "never a DB purge"
     claim. `MonitoringSignatureRow` gains `cleared`/`onToggleClear` props (both optional, so any
     other consumer of this shared row component — there is currently only Monitoring itself —
     is unaffected by omission).

### Doc-update map sweep

Walked [the map](../TABLE_OF_CONTENTS.md#doc-update-map) row by row against the confirmed
frontend-only diff:

1. **🟠 `api/` endpoint or `frontend/` screen — new/changed capability** → owed
   `design/architecture.md` + `design/data-platform-and-archivist.md` +
   `requirements/functional.md` (REQ-F). **Fired** — three screens changed (Monitoring,
   Provenance, Runs, Agent triage, Pipeline Builder — five, technically). Handled: new
   architecture.md batch-8 bullet + rewritten deferrals paragraph; new data-platform §4.9;
   REQ-F-047 superseding note. The `/metrics`/`_render_prometheus` sub-clause does not fire — no
   series changed (this batch touched zero backend code).
2. **🔴 ANY working session** → owed this journal. Done.
3. **🔴 A task changes status / is created** → owed `planning/tasks.md`. Fired three times (three
   new `done` rows) plus once more for T-072 (its row's *content* changes to describe the
   reversal — its `status` stays `todo`, unchanged, but the map's trigger is "a task changes
   status... **or is created**," and T-072 wasn't newly created; I updated it anyway because
   leaving it describing "frontend half CLOSED" when the very next commit undid that closure
   would be exactly the "doc contradicted by code" drift this contract exists to catch — see
   Decisions below).
4. **⚪ Files moved / a module added / a map trigger rotted** → owed `CLAUDE.md` code map. Fired
   (new dependency + three screens changed). Handled: new Batch 8 paragraph + rewritten
   deferrals sentence.
5. **⚪ Scope / wishlist / "built" changes** → `requirements/scope-and-wishlist.md`. **Not
   fired** — no new capability crossed from wishlist to built, no scope line changed; this is
   UI polish on already-`done` (T-062-era) screens. Waived.
6. **🔴 `models.py`/`parsers.py`/`persistence/`** → `data/schemas.md`. **Not fired** — confirmed
   zero `src/pipeguard/` changes in all three diffs.
7. **🔴 tests/ added/removed/renamed, or an EVAL case** → `quality/evaluation.md`. **Not fired**
   — confirmed zero `tests/` changes (`git diff --stat 1169e37 f8a6f35 -- tests/` empty, a
   subset of the broader check above). Waived — no census to recount.
8. **🟠 `runbook.py`/`rules.py`** → `data/qc_metrics.md` (+ `ADR-0013` if policy changed). **Not
   fired.**
9. **🟠 `metrics/` registry** → `data/metric_registry.md`. **Not fired.**
10. **🟠 `provenance.py`/`engine.py`/`EventType`/JSONL ledger** → `data/provenance.md`. **Not
    fired** — the ledger/event vocabulary is untouched; Provenance's UI relabel ("hash"→
    "fingerprint") is a display string only, not a schema or event-type change (confirmed the
    wire field `sha256` is unchanged in the diff).
11. **🟠 A new advisory agent / model tier / corpus** → `design/agents.md` + ADR. **Not fired** —
    no new agent; the Builder's existing three agent tiles just became clickable one mode
    earlier, not a new capability, model, or corpus.
12. **⚪ A load-bearing decision made/superseded** → a new ADR or an existing ADR's Decision/
    Status + a journal Decisions row. Considered whether "add recharts" or "reverse T-072's
    pager" rise to ADR-worthy: **no** — neither changes an architectural invariant (ADR-0001's
    rules-decide/AI-advises boundary, ADR-0002's ledger, ADR-0003's ports, ADR-0006's AI-off-
    default, ADR-0014's FastAPI+React split are all untouched). Both are UI-implementation
    choices the maintainer made directly, captured as Decisions rows below and in the doc-map
    sweep — not ADR-worthy per the contract's "load-bearing" bar.

**Waived, with reasons:** `quality/risks.md` (no new risk class — the `runs[]`-uncapped risk
T-072 already tracks isn't new, just re-described more accurately); `data/strategy.md`/
`data/nf-core-conventions.md`/`data/qc_metrics-sources.md`/`data/qc_metrics-rare-disease.md`
(no data/QC-metric change); the ADR set (no decision reversal, see #12 above);
`ops/telemetry-connectors.md` (no `/metrics` series change); `demo/*.md` (no demo-flow or
command change — this is in-app UI polish, not a run-of-show step); `data/licensing.md` +
`requirements/constraints.md` (see the recharts discussion above — outside the doc's stated
scope, and no existing frontend dep is tracked there either, so adding just this one would be
inconsistent, not more honest).

## Decisions

| Decision | Distilled to |
|---|---|
| Add `recharts@3.9.2` (MIT) as the frontend's first real charting dependency, justified by hover-tooltip + trend-line + frozen-frame requirements a hand-rolled SVG chart can't meet without reinventing a chart library; not tracked in `data/licensing.md`/`requirements/constraints.md` (those docs are scoped to the genomics-tool/external-process stack, not bundled frontend npm libs — no existing frontend dep is tracked there either) | [CLAUDE.md](../../CLAUDE.md) code map (Batch 8 paragraph), [tasks.md T-100](../planning/tasks.md), this journal |
| T-072's frontend mitigation (Batch 7's per-run pager, `34bca5d`) is REVERSED by this batch's Recharts chart, not merely narrowed — re-describe the task row, `architecture.md`, `data-platform-and-archivist.md`, and `functional.md` REQ-F-047 to say so explicitly rather than leaving stale "frontend half CLOSED" language standing next to code that no longer paginates | [tasks.md T-072](../planning/tasks.md), [architecture.md](../design/architecture.md), [data-platform-and-archivist.md §4.9](../design/data-platform-and-archivist.md), [functional.md REQ-F-047](../requirements/functional.md) |
| Neither the japandi theme re-skin nor the Recharts monitoring rework is ADR-worthy — both are UI-implementation choices within existing architectural invariants (ADR-0001/0002/0003/0006/0014 all untouched), not load-bearing decisions | this journal (§Doc-update map sweep, item 12) |

## Open questions & TODO

- `GET /api/monitoring`'s `runs[]` payload remains uncapped server-side with **no** frontend
  mitigation as of this batch (T-072, `todo`) — becomes a real concern once `synthetic/scale.py`
  (T-050) seeds a much larger window; the eventual fix is server-side `page`/`limit`, not another
  frontend re-presentation (a pager would just get removed again the next time the UI pattern
  changes).
- The recharts MIT-license claim (commit message + this journal) was not independently
  re-verified against the npm registry/upstream LICENSE this session — flagged as an Assumption
  in the Discussion above, consistent with `licensing.md`'s own "reported ≠ verified" posture for
  everything not in its verified-verbatim table (which recharts isn't part of, being out of that
  doc's scope).
- `docs/design/frontend/README.md` still has no metadata table (Status/Last updated/Audience/
  Related) that the doc-keeper contract's templates otherwise require of every doc — pre-existing
  drift, out of this sweep's scope (not touched by these 3 commits' obligations); worth a
  dedicated pass if a future session owns that file more broadly.

## Distilled into

- [docs/planning/tasks.md](../planning/tasks.md) — T-098/T-099/T-100 rows added; T-072 rewritten.
- [CLAUDE.md](../../CLAUDE.md) — Batch 8 paragraph in the frontend code-map entry + rewritten deferrals sentence.
- [docs/design/architecture.md](../design/architecture.md) — new batch-8 bullet + rewritten deferrals paragraph + Related crosslink.
- [docs/design/data-platform-and-archivist.md](../design/data-platform-and-archivist.md) — new §4.9 + Related crosslink.
- [docs/design/frontend/README.md](../design/frontend/README.md) — §4 App shell, §9 Tokens, §5.2 Runs, §5.6 Provenance, §5.7 Agent triage, §5.8 Monitoring, §6 Builder Canvas + Modes.
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-047 superseding note + Related crosslink.
