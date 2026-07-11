# Journal — 2026-07-10 (MST) — Audit retrofit: explicit-confirm gate on one-click writes

| Field | Value |
|---|---|
| **Focus** | Doc-keeper SWEEP for 1 commit (`d65c9c1`, "Wave 3") landed after the Wave-4 sweep ([journal](2026-07-10-wave4-submit-parsing-and-api-errors.md), commit `1bb79b8`). Ground every claim in the real diff (`git show d65c9c1`), confirm frontend-only, then walk the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) and update every doc it obligates, in the same sweep. |
| **Participants** | doc-keeper subagent (SWEEP mode) |
| **Outcome** | 1 commit swept, frontend-only (`git diff --stat 9733842 d65c9c1 -- src/ api/ tests/` empty), no verdict/gate/ADR-0001 boundary changed. Adds a reusable `ConfirmProvider`/`useConfirm()` primitive (`frontend/src/components/ConfirmDialog.tsx`) that realizes the maintainer's standing design rule — no single accidental click may fire a cascading/state-changing write — and routes the review queue's stakes-y ticket actions (Resolve/Escalate/Reopen/Suppress, incl. batch) plus Admin's Act-as through it. Docs updated: `docs/planning/tasks.md` (new T-102 row), `docs/requirements/functional.md` (new REQ-F-075 + Related crosslink), `CLAUDE.md` (new Wave-5 code-map paragraph), `docs/design/frontend/README.md` (§5.5 Review queue + §11 Admin), `docs/design/architecture.md` (new Invariant 8 + Related crosslink), `docs/adr/ADR-0017-identity-rbac-authoring-lifecycle.md` (a second "Realized addendum," no decision change), `docs/quality/risks.md` (RISK-035 "Further hardening" note + Related crosslink). Waived with reasons below: `docs/design/data-platform-and-archivist.md`, `docs/requirements/scope-and-wishlist.md`, `docs/quality/evaluation.md`, `docs/adr/ADR-0008-issue-taxonomy-suppression-escalation.md`, `data/schemas.md`/`provenance.md`/`metric_registry.md`, `data/licensing.md`/`requirements/constraints.md`, `design/agents.md`, `ops/telemetry-connectors.md`, `demo/*.md`. |

## Discussion

### Grounding pass (`git show`, before writing any doc)

Confirmed the date first: `git log -1 --format=%ci d65c9c1` → `2026-07-10 18:51:53 -0700` — the
`-0700` offset matches this repo's MST (UTC-7, Arizona-style, no DST) convention, same calendar
date as the Wave-4 sweep, immediately after it (`git log --oneline -5 d65c9c1` shows
`d65c9c1 → 9733842[Wave-4 doc sweep] → 1bb79b8[Wave-4 Submit] → f8d9ea0[Wave-4 API errors] →
e39bb4e[Batch-8 doc sweep]`). Confirmed frontend-only: `git diff --stat 9733842 d65c9c1 --
src/ api/ tests/` returns **empty** — no backend/data-contract/test trigger fires this sweep.
Read the full diff (`git show --stat`/`git show`): 4 files, `+183/-12` —
`frontend/src/App.tsx` (+3), `frontend/src/components/ConfirmDialog.tsx` (new, 106 lines),
`frontend/src/screens/Admin.tsx` (+10/-4), `frontend/src/screens/ReviewQueue.tsx` (+59/-12).

1. **`ConfirmDialog.tsx` (new).** A `ConfirmContext` + `ConfirmProvider` holding one pending
   `ConfirmOpts | null` and a `resolver` ref; `confirm(opts)` sets the opts and returns a
   `Promise<boolean>` whose resolver is stashed in the ref, so a call site can
   `if (!(await confirm({...}))) return` before firing a write. `close(v)` resolves the promise
   and clears state. An `useEffect` attaches a `keydown` listener only while `opts` is set,
   cancelling (`close(false)`) on `Escape` — confirmed this is scoped per-open (the listener is
   added/removed with `opts`, not a permanent global one). The rendered dialog: an
   `AlertTriangle` icon tinted `escalate` colors when `tone === 'danger'` else `accent` colors,
   title + optional body, Cancel/Confirm buttons (labels default to "Cancel"/"Confirm", override
   via opts), a `fixed inset-0` backdrop whose `onClick` cancels while the card itself
   `stopPropagation()`s — confirmed both Escape and click-outside cancel, never confirm, matching
   the commit message's claim. `useConfirm()` throws if called outside the provider (a real
   programmer-error guard, not a runtime user-facing failure).
2. **`App.tsx`.** `ConfirmProvider` now wraps the tree, mounted **outermost after
   `ToastProvider`** (confirmed by the diff: `<ToastProvider><ConfirmProvider><PrefsProvider>…`)
   — so a confirm dialog can render above/alongside toasts app-wide, matching the commit
   message's "mounted at the app root" claim.
3. **`ReviewQueue.tsx`.** Read the full diff.
   - `ACTION_CONFIRM` is a lookup for `resolve`/`escalate`/`reopen`, each with a title + a body
     naming the effect + "recorded in the audit log." `confirmAct(t, action)` awaits `confirm()`
     then calls the pre-existing `act(t, action)` — **the same backend-persisting function this
     screen already had**, confirmed by diffing: `act`/`toggleSuppress` themselves are
     **untouched** by this commit; only their call sites in the `on={{...}}` prop object changed
     from direct calls to `void confirmAct(t, 'resolve')` etc.
   - `confirmSuppress(t)` checks `uiRef.current[keyOf(t)]?.suppressed` first — if already
     suppressed, it un-suppresses **directly, no confirm** (`toggleSuppress(t)`); only the
     suppress direction gets the DANGER-toned confirm naming the cross-run cascade. Confirmed
     `ack: () => act(t, 'acknowledge')` in the `on={{...}}` prop keeps its **inline comment**
     "soft, non-destructive — no confirm" — the commit's own code documents the low-stakes
     exemption, not just the message.
   - `batchAct(action)` now computes `n = selectedTickets.length`, returns early if `n === 0`
     (no confirm on an empty selection — can't fire a no-op write anyway), else confirms
     `"${Resolve|Suppress} N selected ticket(s)?"` with a `tone: 'danger'` only for suppress,
     then runs the **exact same** `for` loop over `selectedTickets` calling `act`/
     `toggleSuppress` per ticket — unchanged from before, confirmed by diff (only the function
     signature gained `async` + the confirm gate at the top).
   - The two toolbar buttons (`onClick={() => batchAct(...)}`) become
     `onClick={() => void batchAct(...)}` — a `void` cast on the now-async handler, not a
     behavior change.
4. **`Admin.tsx`.** `actAs(u)` was `const actAs = (u) => { ... if (!window.confirm(...)) return;
   setActor(...) }`; now `async (u) => { ... const ok = await confirm({title, body,
   confirmLabel: 'Act as'}); if (ok) setActor(...) }` — same guard (early return if
   `u.id === actor.id`), same eventual `setActor` call, only the confirmation mechanism changed.
   The button's `onClick={() => actAs(u)}` becomes `onClick={() => void actAs(u)}`.
5. **No backend/persistence change anywhere.** Confirmed by the empty `src/ api/ tests/` diff
   stat above — every confirmed action still calls a function that existed before this commit
   (`act`, `toggleSuppress`, `setActor`), so nothing about *what* gets written or *where* it's
   persisted (`api/routers/review_queue.py`'s `ticketAction`, the client-mock
   `RoleContext.setActor`) changed. The Admin Activity audit feed (reads
   `listThresholds`+`listPipelines`+`listTickets`) is therefore unaffected — a resolved/
   suppressed ticket still lands there exactly as before.
6. **No frontend test file changed** (confirmed: `frontend` has no test framework configured —
   `grep -i test frontend/package.json` finds nothing, and no `*.test.*`/`*.spec.*` file exists
   in the repo; every prior frontend-only commit in this history verifies via `tsc`/`oxlint` +
   live manual checks, not an automated suite — this commit's "tsc + oxlint clean" claim is
   consistent with that established pattern, not a new gap).

### Doc-update map sweep

Walked [the map](../TABLE_OF_CONTENTS.md#doc-update-map) row by row against the confirmed
frontend-only diff:

1. **🔴 ANY working session** → owed this journal. Done.
2. **🟠 `api/` endpoint or `frontend/` screen — new/changed capability** → owed
   `design/architecture.md` + `design/data-platform-and-archivist.md` +
   `requirements/functional.md` (REQ-F). **Partially fired.** `functional.md`: fired — new
   REQ-F-075. `architecture.md`: fired — a new Invariant 8 ("off-gate writes are explicit and
   audited"), since this is a durable interaction guarantee future sessions (Settings/variant
   authoring, per the commit message) should check against, not just a one-off screen note.
   `data-platform-and-archivist.md`: **not fired** — grepped for `suppress`/`review queue`/
   `confirm`; its only "confirm" hits are unrelated ("confirm against a real sarek run," data
   sourcing confirmations) — the doc's scope (export/archivist/data-platform design) is
   untouched by a client-side confirmation gate over already-existing ticket actions. Waived.
3. **🔴 A task changes status / is created** → owed `planning/tasks.md`. Fired — new T-102 row.
4. **⚪ Files moved / a module added / a map trigger rotted** → owed `CLAUDE.md` code map. Fired
   — new Wave-5 paragraph (a module was added: `components/ConfirmDialog.tsx`).
5. **⚪ Scope / wishlist / "built" changes** → `requirements/scope-and-wishlist.md`. **Not
   fired** — grepped for `review queue`/`suppress`/`escalat`; the doc's review-queue mentions are
   about the pipeline-repair agent roster item (built status, cross-run signature flow), not the
   ticket-action UX this commit changes. No scope/wishlist item names or claims "one-click, no
   confirm" today, so nothing here goes stale. Waived.
6. **🔴 `models.py`/`parsers.py`/`persistence/`** → `data/schemas.md`. **Not fired** — confirmed
   zero `src/pipeguard/` changes (the grounding-pass empty-diff check above is a superset).
7. **🔴 `tests/` added/removed/renamed, or an EVAL case** → `quality/evaluation.md`. **Not
   fired** — `git diff --stat 9733842 d65c9c1 -- tests/` is empty (subset of the check above);
   no Python test census to recount, and this frontend repo has no test-file census tracked in
   `evaluation.md` at all (grounded: `evaluation.md`'s census is Python-`pytest`-only). Waived.
8. **🟠 `runbook.py`/`rules.py`** → `data/qc_metrics.md`. **Not fired.**
9. **🟠 `metrics/` registry** → `data/metric_registry.md`. **Not fired.**
10. **🟠 `provenance.py`/`engine.py`/`EventType`/JSONL ledger** → `data/provenance.md`. **Not
    fired** — no event vocabulary or ledger format touched; the actions this commit gates were
    already off-gate, unpersisted-to-the-ledger writes before this commit, and stay so.
11. **🟠 A new advisory agent / model tier / corpus** → `design/agents.md` + ADR. **Not fired**
    — `ConfirmDialog` is a UI primitive, not an agent (roster or otherwise); no ADR-0001/0006/
    0009/0012 boundary touched.
12. **⚪ A load-bearing decision made/superseded** → a new ADR or an existing ADR's Decision/
    Status + a journal Decisions row. Considered carefully, since the commit message frames this
    as realizing "the maintainer's standing design rule" and the task explicitly asked to check
    for a design doc recording the explicit-edit/audit principle. **Found:**
    [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md) already decided the
    server-side half of "audited" (Decision 4: "identity is server-captured into audit/`*_by`
    fields, never client-set") and already carries a precedent "Realized addendum" section
    (2026-07-10, the demo-login layer) for exactly this shape of frontend-only, no-decision-
    change follow-up. **Decision: no new ADR** — added a **second Realized addendum** to
    ADR-0017 instead, framing the confirm gate as the frontend-UX completion of that existing
    audit decision (deliberate, not just recorded), plus a new non-ADR Invariant 8 in
    `architecture.md` for discoverability. This mirrors the Wave-4 sweep's reasoning (no new ADR
    for a UX implementation fix within existing, unchanged invariants) while still giving the
    principle a durable, citable home per the map's "never bury a decision in an appendix" rule
    — the difference here is the home is an *addendum to an existing ADR that already owns the
    audit guarantee*, not a design-doc appendix.

**Waived, with reasons:** `quality/evaluation.md` (map row 7, no test change, no census to
recount); `adr/ADR-0008-issue-taxonomy-suppression-escalation.md` (grepped for "confirm"/
"UI" — this ADR defines the suppression **taxonomy and semantics** — what a suppression *means*
— which is unchanged; the confirm gate only changes *how deliberately* an operator triggers the
already-defined action, not what it does); `data/schemas.md`/`data/provenance.md`/
`data/metric_registry.md` (no wire-contract, event-vocabulary, or metric change — map rows
6/9/10 above); `data/licensing.md`/`requirements/constraints.md` (no new dependency — the diff
adds zero lines to `frontend/package.json`, confirmed in the `git show --stat` file list above:
only `.tsx` files changed); `design/agents.md` (no new/changed agent — map row 11 above);
`ops/telemetry-connectors.md` (no `/metrics` series change); `demo/*.md` (no demo-flow or
command change — this is in-app interaction-safety work, not a run-of-show step).

## Decisions

| Decision | Distilled to |
|---|---|
| No new ADR for the confirm-gate primitive — it is the frontend-UX realization of [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md)'s existing audit decision (Decision 4: identity captured into `*_by` fields), not a new architectural boundary; captured as a second "Realized addendum" on that ADR + a new non-ADR Invariant 8 in [architecture.md](../design/architecture.md), giving the principle a durable, citable, non-buried home | [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), [architecture.md](../design/architecture.md) §Invariants |
| Acknowledge and un-suppress stay direct one-clicks, by design — low-stakes/non-destructive, so gating them behind a confirm would add friction without mitigating a real accidental-click risk | [functional.md REQ-F-075](../requirements/functional.md), [tasks.md T-102](../planning/tasks.md), [design/frontend/README.md](../design/frontend/README.md) §5.5 |

## Open questions & TODO

- The commit message flags `ConfirmDialog` as "reusable for the settings/variant work ahead" —
  when Settings' threshold-edit save/approve or a future variant-authoring surface lands, check
  whether its writes are stakes-y enough to route through the same primitive (Settings'
  threshold save/approve is already RBAC + audited per REQ-F-062/ADR-0017, but is not yet
  confirm-gated — an open question for that surface's own sweep, not this one).
- No automated frontend test exists for `ConfirmDialog`'s cancel/confirm/Escape/click-outside
  behavior (verified live only, per this repo's established frontend-verification pattern — see
  grounding-pass item 6). Not a new gap introduced by this commit, just an existing one this
  primitive now also depends on.
- `docs/design/frontend/README.md` still has no metadata table (Status/Last updated/Audience/
  Related) — a pre-existing gap already flagged in the Batch-8 and Wave-4 journals, still out of
  this sweep's narrow scope.

## Distilled into

- [docs/planning/tasks.md](../planning/tasks.md) — new T-102 row.
- [docs/requirements/functional.md](../requirements/functional.md) — new REQ-F-075 + Related crosslink.
- [CLAUDE.md](../../CLAUDE.md) — new Wave-5 paragraph in the frontend code-map entry.
- [docs/design/frontend/README.md](../design/frontend/README.md) — §5.5 Review queue (new confirm-gate note) + §11 Admin (Act-as dialog upgrade note).
- [docs/design/architecture.md](../design/architecture.md) — new Invariant 8 + Related crosslink.
- [docs/adr/ADR-0017-identity-rbac-authoring-lifecycle.md](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md) — second Realized addendum.
- [docs/quality/risks.md](../quality/risks.md) — RISK-035 "Further hardening" note + Related crosslink.
