# Journal — 2026-07-13 (MST) — Audit-surfaced frontend honesty fixes (G1–G7) + the System-agents/Agent-triage IA split

| Field | Value |
|---|---|
| **Focus** | Close a fresh round of audit-surfaced "confident-surface-vs-thin-wiring" gaps in the **frontend** (the deterministic spine was already wired; these are places the *surface* over-claimed relative to it) — G1–G7 across Provenance, Decision cards, RunDetail, the Pipeline Builder, the Ask-agent composer, the TopBar, and Review-queue/Settings — then resolve a maintainer-reported IA duplication ("system agents and agent triage look like duplicate pages") and close the one advisory POST endpoint with no `require_role` seam coverage. |
| **Participants** | Claude (doc-keeper, SWEEP + AUTHOR) grounding commits already landed by James Hu + Claude Opus 4.8 on `feat/gap-analysis-remediation`; maintainer review pending. |
| **Outcome** | 13 commits (`c15a4d2`…`a1aef73`) journaled and swept. Two genuine pre-existing doc drifts caught and fixed (a stale `docs/design/frontend/README.md` claim that the decision-card gate strip's grey/green split matched code it no longer matches, and a stale claim that the Builder inspector still has a Close-X button). One fabricated-capability UI-copy claim ("suppress mutes future occurrences across runs") is now retracted in code; the doc that had quoted the old copy verbatim is corrected too. `docs/planning/tasks.md` gains 11 new rows (T-155–T-165), one of them (T-165) a **newly identified, not-yet-fixed** gap (Builder-Run has no parse-contract check, unlike intake post-WS-09) surfaced by grounding this sweep in code rather than only in commit prose. Verified independently (not just quoted from commit messages): `uv run pytest -q -k ask` → 8 passed; `uv run mypy` → clean (95 files); `npx tsc -b` → clean; full `uv run pytest -q` → 714 passed / 8 skipped (test census **unchanged** — these 13 commits touch zero Python test files). |

## Discussion

### Why this session exists

The branch's last journal ([2026-07-12-gap-analysis-remediation-verification.md](2026-07-12-gap-analysis-remediation-verification.md),
plus its same-day addendum) closed out the WS-01…WS-10 backend/ingestion gap-analysis work. Thirteen
more commits landed after that entry closed, all frontend-side (plus one one-file backend authz
fix), un-journaled:

1. **`c15a4d2`** — brings a new `<Missing/>` honesty primitive (`frontend/src/components/Missing.tsx`)
   onto the trunk: one reusable component + a `formatScalar()` helper so an absent scalar renders a
   semantic, de-emphasized token (`not-captured`/`not-measured`/`not-run`/`not-applicable`/`unknown`)
   instead of a bare `—`, an empty cell, or — the actual bug class this exists to prevent — a
   fabricated `0`. It generalizes a pre-existing local `NotCaptured()` idiom in
   `DecisionContextRail.tsx` into a reusable family. Self-contained (React-only import), `tsc` clean,
   no consumers wired yet in this commit — it is the substrate the next three land on.
2. **`34f5380`** (**G1**) — `RunReport.tsx` + `provenance/Lineage.tsx`: the terminal "De-identified
   share" node no longer reads "Completed" green while an upstream stage is gray (a downstream node
   must never look more-complete than its lineage); intake/demux/qc nodes now require **positive**
   evidence they ran (an artifact, a gate checkpoint, or the run's own cards/`started` event) rather
   than "no bad verdict showed up" (absence ≠ passed — a fail-closed rule, mirroring the WS-01
   `CheckCoverage` posture at the UI layer); the decision gate is pulled OUT of the numbered 9-step
   process chain and rendered as its own terminal aggregate verdict banner (a `GATE_STAGE` with
   `n: 0`, unioned back in for drill-in lookups via `ALL_STAGES`) — it is an aggregate over every
   stage, not "step 8 of 9"; `RunReport.tsx`'s provenance pins (`Rule pack`, `Runbook metrics`,
   `Events`, `Started`, `Completed`) route absent values through the new `<Missing/>` primitive
   instead of a fabricated `0`/`—`.
3. **`de14fa3`** (**G2**) — `GateResultStrip.tsx`: **the headline bug this whole round exists to
   fix.** `blocked` used to be `cardVerdict === 'escalate' || cardVerdict === 'rerun'` — a **HOLD**
   card fell through that check, so a not-run downstream gate on a held card rendered **green
   "Cleared with margin,"** painting a held sample as if every gate had passed. `blocked` is now
   `cardVerdict !== 'proceed'` **plus** a per-gate `unclearGates`/`blockingGate` lookup that mirrors
   `card_readout.py`'s own `_blocking_gate` derivation, so the top-strip chip and the QC-readout hero
   can no longer disagree about the same card. `DecisionContextRail`'s Subject field and
   `MetricsPanel`'s `not_measured` observed-cells now route through `<Missing/>` too (a new `Observed`
   wrapper component).
4. **`8734cd8`** (**G3**) — `RunDetail.tsx`: a **released** run used to hard dead-end at
   `<DecisionReleased>` with no way to inspect what actually happened. A "View cards anyway" latch now
   reveals the per-sample cards on demand (fanning out the QC-readout fetch only once the operator
   opts in — a released run's main effect never fetches them eagerly) plus a `canSee('provenance')`
   -gated "Open provenance" link. Every inline cross-link on this screen (the review-queue banner
   link, the "Open provenance"/"Ask agent to triage" rail buttons on `CardBody`) is now gated on the
   same `useAccess().canSee(page)` the nav itself uses — a restricted actor is never invited into a
   `RequirePage`-gated access-denied dead-end from an inline link the nav had otherwise hidden.
5. **`13ad1a4`** (**G4**) — `BuilderInspector.tsx` + `PipelineBuilder.tsx`: in **Connect mode**, a user
   node's body used to be inert to a click (only its ports responded — `nodeDrag` returned early
   before selection), while seeded tool/agent cards still selected via the canvas path — an
   inconsistency, now fixed by selecting the node before the early return. The inspector header's
   redundant **X (Close)** button is **removed**, keeping only the **›** collapse — the two used to do
   different things (Close cleared the selection, Hide collapsed to a rail) in a way the audit + the
   maintainer's own notes flagged as confusable; clearing the selection is now a canvas
   background-click or Escape. A new read-only `CatalogRef` panel maps a user node whose name matches
   a seeded catalog Tool to that tool's Params + declared I/O — previously stranded on the
   seeded-card-only `ToolView` and unreachable from the default (editable) flow; absent sha/size
   render `—`, never fabricated, since artifact bytes only exist for a bound run.
6. **`b4a06c0`** (**G5**) — `AgentComposer.tsx` now **POSTs the real `/ask` endpoint**
   (`api.askAgent`, `POST /api/runs/{run}/cards/{sample}/ask`, WS-07 Q2's backend from the prior
   session) and renders the returned `AgentReply` verbatim — per the commit's own framing,
   "SCAFFOLD→WIRED": no hardcoded reply string, the offline stub is the real
   retrieval-grounded answer. The dead `AgentSourceToggle.tsx` is deleted; the composer now shows a
   passive "Live agent: not armed" status instead (arming is env-side, `BAYLEAF_TRIAGE_AGENT=claude`
   — the UI can only report it, never toggle it). `App.tsx` gains a run-independent `<Route
   path="/agents">` (same `AgentTriage` component, same `page="agent"` access gate) and
   `Sidebar.tsx` gains a "System agents" nav entry (`Sparkles` icon, `to: '/agents'`) — reachable even
   when no run is in context or a run 404s.
7. **`084c730`** (**G6**) — `TopBar.tsx`: the crumb title used to fall through to a hardcoded default
   for any route it didn't special-case, so `/accession`, `/inbox`, and `/admin` all read "Runs." A
   new `routePage()` resolves the pathname to a `PageId` and the crumb now reads
   `pageLabel(page)` off the **same** `PAGE_CATALOG` the nav itself uses — one owner for a page's
   name. The bespoke top-bar run switcher (hand-rolled combobox) is deleted in favor of reusing the
   shared, keyboard/loading/error-aware `<RunSelector>` (already used elsewhere, e.g. the Builder's
   "Open a saved pipeline" picker) — same idiom (capped rows, search-by-id/platform, a real
   status dot), one fewer bespoke implementation. `RunOverview.tsx`'s empty state now branches on
   *why* the list is empty: a search miss ("No runs match your search… Clear search") vs. a
   filter/date miss ("No runs match this filter… Show all runs") — previously every empty case said
   "Clear the filter," which was actively wrong advice for a search miss.
8. **`c583581`** (**G7**) — `ReviewQueue.tsx`: a rejected write (403/409) used to leave a ticket
   stranded showing the **optimistic** post-action state (e.g. "Resolved") with no way back short of a
   manual refetch. `syncAction` now snapshots the ticket's UI slice before the optimistic patch and
   **restores** it on a rejected write (mirrors the Pipeline Builder's own reconcile-on-catch
   pattern), then still surfaces the real backend error via toast. The Suppress confirm dialog's copy
   used to claim *"Future occurrences of `<rule>` across runs are hidden from the queue until
   un-suppressed"* — **a capability the backend does not implement** (`api/routers/review_queue.py`
   has no cross-run suppression-muting lifecycle; [ADR-0008](../adr/ADR-0008-issue-taxonomy-suppression-escalation.md)
   itself already labels that lifecycle **deferred**, so this was UI copy promising a design target
   as if it already shipped). The copy is retracted to *"Resolves this ticket and marks the issue
   class handled here. It does not mute future occurrences on other runs (cross-run suppression is
   not built)."* `SettingsNotifications.tsx`: the Slack/Teams status dot used to read green
   **"Connected"** — a health check this seam never performs — now reads a neutral **"Configured ·
   not verified."** "Save" used to toast **"Notification settings saved"** — nothing here persists to
   a backend (component state only, lost on reload) — now toasts **"Applied locally — demo seam, not
   persisted to a backend."** The Discord "Connect" button, previously a dead click, now toasts
   **"Discord connect is not wired in this demo."** A dashed-border demo-seam banner states all three
   honesty points plainly on the panel itself.

### The IA-duplication fix (this turn) — three follow-up commits

G5 (`b4a06c0`) added the `/agents` route, but it rendered through the **same** `AgentTriage.tsx`
component the per-run `/runs/:id/agent` route uses — and that component's per-run triage table only
renders when a `runId` is present, while the two system-agent launcher tiles (Pipeline-repair,
Archivist) render unconditionally. Net effect: `/agents` showed the launchers with no table (correct
for that route), but the **per-run** route ALSO still showed the launchers alongside its own table —
the maintainer's own words, "system agents and agent triage look like duplicate pages."

9. **`a499691`** — splits `AgentTriage.tsx`'s content by `isSystemView = !runId`: the two org-agent
   launcher tiles now render **only** when there is no `runId` (the `/agents` route); the per-run
   route shows only its flagged-samples table + advisory composer, with a *"No run in context"* empty
   state under it. This is a **lighter-weight implementation** than the design spec drafted the same
   week ([design/frontend/agent-triage-redesign-spec.md](../design/frontend/agent-triage-redesign-spec.md),
   `271400c`) proposed — the spec's Slice 1 (`WS-1`) called for a **new** `system-agents` `PageId`
   in `access.ts`/`PAGE_CATALOG`, a dedicated nav item, and deleting the launchers out of
   `AgentTriage.tsx` into a promoted panel. What shipped instead is one component with a route-derived
   conditional and **the same shared `PageId: 'agent'`** for both routes — cheaper, and it achieves
   the maintainer's actual complaint (no more visual duplication), but an Admin page-access grant
   still cannot distinguish "can see Agent triage" from "can see System agents" (both gate on the one
   `'agent'` page). Verified (commit's own claim, and independently re-verified below): `tsc -b`
   clean; browser-checked both routes render distinctly.
10. **`f230f7e`** — `/agents` and `/runs/:id/agent` sharing `PageId: 'agent'` meant the crumb (fixed in
    G6 to read off `PAGE_CATALOG`) resolved **both** routes to the same label, "Agent triage" — so the
    IA split's own page title/crumb disagreed on the System-agents page. `routePage()` gains a
    route-aware `'system-agents'` sentinel matched **before** the generic `/agent` branch (the same
    pattern already used for `'admin'`, which also has no dedicated `PageId`), and `useCrumb()` names
    it literally "System agents." Excluded from the per-run pill logic (`PER_RUN_PAGES` — it carries
    no `runId`).
11. **`a1aef73`** — `POST /api/runs/{run_id}/cards/{sample_id}/ask` was, per the commit's own audit,
    **the only advisory endpoint with no `require_role` dependency at all** — it bypassed
    `api/auth.py`'s shim entirely, unlike its siblings (`node_observations`, `files`, every other
    advisory-read endpoint). Grepped to confirm before trusting the commit's own claim: `grep -n
    "require_role" api/main.py` shows every other endpoint in that file gated; `ask_card_agent` was
    the one bare `def`. Now gated `Depends(require_role("viewer", "reviewer", "approver"))` — the
    **read-family floor**, not the write/exec reviewer+ floor, because this is advisory (ADR-0001), not
    a mutation. Demo behavior is unchanged (the permissive dev-default clears viewer+ under both
    normal and `BAYLEAF_AUTH_STRICT` modes) — the value is closing the seam so a real-IdP swap
    doesn't leave this one endpoint wide open while every sibling is covered. The docstring notes
    reviewer+ as a one-word cost-control tightening if a deployment wants one.

### Method — verify before writing (per CLAUDE.md's "ground every claim in code")

1. **Read every commit's own diff**, not just its message — `git show <sha>` for all 13, in full for
   the ones with load-bearing logic changes (`de14fa3`'s `GateResultStrip`, `34f5380`'s `Lineage.tsx`,
   `13ad1a4`'s `BuilderInspector.tsx`, `c583581`'s `ReviewQueue.tsx`/`SettingsNotifications.tsx`,
   `a1aef73`'s `api/main.py`).
2. **Independently re-ran the verification the commits claim**, rather than trusting the commit
   messages verbatim:
   - `uv run pytest -q -k ask` → **8 passed** (matches `a1aef73`'s "8 ask tests green").
   - `uv run mypy` → **Success: no issues found in 95 source files** (matches "project-wide mypy
     clean").
   - `cd frontend && npx tsc -b` → clean, no output (matches `a499691`'s "tsc -b clean").
   - `uv run pytest --collect-only -q` → **722 tests collected**; `git ls-files 'tests/*.py' | wc -l`
     → **54** — identical to the prior journal's addendum count. `git diff --stat c15a4d2^..a1aef73 --
     tests/ src/ api/` confirms only `api/main.py` changed among those three trees (16 lines, the
     `a1aef73` authz dependency) — **zero Python test files were touched by this round**, so
     [quality/evaluation.md](../quality/evaluation.md)'s census is genuinely unaffected and the
     🔴 "add/remove/rename a test" doc-update-map row does **not** fire. `uv run pytest -q` → **714
     passed / 8 skipped** — green.
   - Did **not** independently re-run the browser check `a499691` claims ("browser-checked both
     routes render distinctly") — accepted it on the strength of the commit's own explicit claim plus
     the code read (the `isSystemView` conditional is unambiguous from source), consistent with this
     being a doc-sweep pass, not a fresh QA pass.
3. **Cross-checked every touched screen's existing canonical-doc description against the new code**,
   not just against the commit message — this is what surfaced the two real doc drifts below (§Docs
   swept, items 2 and 5) and the one still-open code gap (§Distilled into / Decisions, the Provenance
   pin and the Builder-Run parity gap).

### Docs swept, and why each was obligated (the Doc-update map trail)

1. **`docs/planning/tasks.md`** (🔴, unconditional) — 11 new rows, T-155–T-165 (one per commit-group
   G1–G7 + the Missing substrate + the IA-split + the authz fix + the newly-identified Builder-Run
   parity gap), the `Last updated` header line updated.
2. **`docs/design/frontend/README.md`** — a **real, caught drift**, not a routine update: §5.4
   Decision cards' "Pill polish" bullet (grounding **T-089**, `d5fdcb2`) describes the *pre-de14fa3*
   semantics ("a 'Not run' (hard-blocked-upstream) chip stays grey") as the shipped, correct behavior
   — it does not mention the HOLD-card green-chip bug `de14fa3` fixed, so as written it would mislead
   a reader into thinking the strip was already correct. Appended a dated correction, plus a note on
   the released-run-inspectable fix (G3) in the same section (RunDetail hosts the decision-card view).
   §5.6 Provenance's "Wider cards…" bullet says **"The 9-stage lineage chain"** — now false; `34f5380`
   restructured it to 8 numbered process stages + a terminal aggregate gate banner. §5.5 Review
   queue's "Actions now confirm first" bullet **quotes the exact fabricated Suppress copy verbatim**
   ("future occurrences of `<rule>` across runs are hidden … until un-suppressed") as the shipped
   confirm-dialog text — corrected to the retracted wording, crediting `c583581`. §6 Pipeline
   builder's Inspector section claims the panel "carries **two** distinct affordances" (Hide **and**
   Close) — false since `13ad1a4`; corrected, plus a note on the new `CatalogRef` Params/I/O panel.
   §5.7 Agent triage + the "Advisory agents (relocated…)" paragraph in §6 are extended with the
   further IA split (system agents now render ONLY on `/agents`) and the crumb-naming fix; §4 App
   shell's Analyze-group list gains "System agents," and its "Top bar — run switcher" note gets a
   one-line pointer to the `RunSelector` reuse.
3. **`docs/design/ui-conventions.md`** — a new **UIC-20** row for the `<Missing/>` primitive: a
   durable, cross-cutting convention (not a one-off screen tweak — reused by three separate consumers
   in this round: `RunReport.tsx`, `DecisionContextRail.tsx`, `MetricsPanel.tsx`, per the doc-update
   map's "maintainer states a new durable UI rule → append a UIC-N row" trigger, generalized here from
   an audit-surfaced pattern rather than a direct maintainer quote, matching how UIC-2/UIC-5's
   audit-driven corrections were recorded in this same file on 2026-07-11).
4. **`docs/design/agents.md`** (🟠, "a new agent-attachment/taxonomy change") — the existing
   "Pipeline-vs-system agents" section (written 2026-07-12 for ADR-0022) said system agents "moved
   OUT of the Builder palette to Agent-triage launchers" — true but now incomplete: as of `a499691`
   they render **only** on the run-independent `/agents` view, not on the per-run
   `/runs/:id/agent` route that same component also serves. Extended with the `isSystemView` split
   and the shared-`PageId` caveat (an Admin page-access grant cannot yet separate the two views).
   Also notes the `ask` endpoint's new `require_role` floor next to QC-triage's roster row (the
   endpoint wasn't mentioned there at all before — a gap, not a contradiction).
5. **`docs/design/frontend/agent-triage-redesign-spec.md`** — a **real drift**: its own metadata
   table's Status field reads *"Spec — not implemented; to be built later by someone else."* That is
   now false for Slice 1 (`WS-1`, the IA move) — `a499691`/`f230f7e` landed a narrower version of it
   (see item 9 above). Corrected the Status field and added an implementation-note distinguishing what
   landed (Slice 1, in a cheaper shared-component/shared-`PageId` form) from what didn't (Slices 2–6,
   the `AgentDockProvider` floating window and everything after it — genuinely still spec-only).
6. **`docs/design/architecture.md`** (🟠, "api/ endpoint — new/changed capability") — the "Advisory
   agent reads (off the gate)" bullet lists `GET /api/monitoring/signatures/{signature}/repair`,
   `GET /api/runs/{id}/archive-digest`, `GET /api/archive/index`, `GET /api/builder/node-proposal` —
   but never mentions `POST .../ask` at all, despite it being the same class of advisory endpoint and
   now the one with a documented authz floor worth naming. Added.
7. **`docs/requirements/functional.md`** (🟠, same trigger) — REQ-F-104 (the ask-agent endpoint) gets
   a one-line addendum for the `a1aef73` authz floor, so a reader of "what's built" sees the seam is
   now closed without cross-referencing `api/main.py`.
8. **This journal.**

### Docs deliberately NOT touched (waivers)

1. **`docs/quality/evaluation.md`** — waived: the 🔴 "add/remove/rename a test" trigger requires an
   actual test-file change; verified via `git diff --stat` (§Method item 2) that none of these 13
   commits touch `tests/`. The census (722 collected / 54 files / 714 passed / 8 skipped) is
   unchanged from the prior journal's addendum and independently re-confirmed above, not merely
   copy-forwarded.
2. **`docs/data/*.md`, `docs/adr/*.md`** — waived: no schema, event-vocabulary, metric-registry, or
   load-bearing architectural decision changed. The IA-split and the authz floor are implementation
   choices under existing decisions (ADR-0022's taxonomy, ADR-0017's RBAC primitive), not new ones —
   see Decisions below for the explicit non-ADR reasoning.
3. **`CLAUDE.md` "Current code map"** — waived, per the task's own scoping ("ONLY if a listed fact is
   now stale"). Checked directly: item 3b (the `ask` endpoint paragraph) makes no claim about frontend
   wiring status, so `b4a06c0` wiring the composer to it doesn't contradict anything written there.
   Item 4c's "System agents (pipeline-repair, archivist) moved off the Builder palette → Agent-triage"
   remains true after the further `/agents`-vs-per-run split (Agent-triage is still the umbrella
   screen); the more precise, dated detail belongs in `design/agents.md` (item 4 above), which is
   where it landed — CLAUDE.md's code map is deliberately coarse-grained per its own stated scope.
4. **`docs/requirements/scope-and-wishlist.md`** — waived: no in-scope/wishlist boundary moved; every
   commit in this round is a bug/honesty fix to already-in-scope, already-built screens.
5. **`docs/design/builder-cards/README.md`** — checked for a stale connect-mode/inspector claim
   (line 113 mentions Connect-mode port behavior, unrelated to the node-body-click fix); found none
   contradicted by `13ad1a4`.

## Decisions

| Decision | Distilled to |
|---|---|
| The System-agents/Agent-triage IA split ships as **one component with a route-derived conditional and a shared `PageId`**, not the design spec's dedicated route/PageId/promoted-panel shape — a deliberate cheaper fix for the maintainer's literal complaint (visual duplication), leaving the spec's richer slices (dedicated page-access grant, the `AgentDockProvider` floating window) open | [design/agents.md](../design/agents.md) (taxonomy section), [design/frontend/agent-triage-redesign-spec.md](../design/frontend/agent-triage-redesign-spec.md) (Status corrected to partial), `docs/planning/tasks.md` T-163. No new ADR — implementation strategy under the existing [ADR-0022](../adr/ADR-0022-agent-observation-binding.md) taxonomy decision, not a new architectural choice. |
| The `POST .../ask` authz floor is **viewer+ (the read-family floor), not reviewer+** — advisory endpoints get the authenticated-actor floor, mutations get the higher one; this is an application of the existing [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md) RBAC primitive to a seam that had been missed, not a new authorization tier | [design/architecture.md](../design/architecture.md) (Advisory agent reads bullet), [requirements/functional.md](../requirements/functional.md) REQ-F-104. No new ADR. |
| The fabricated cross-run "suppress" UI copy is **retracted, not implemented** — `ADR-0008` already labels the suppression-muting lifecycle deferred, so the fix is honesty-in-copy, not a scope decision; building the real lifecycle stays future work under that same ADR | `ADR-0008`'s existing Status line (unchanged — already accurate); `docs/design/frontend/README.md` §5.5 (corrected quote). |

## Open questions & TODO

1. ~~**A genuinely-open code gap surfaced by this sweep**: Builder-Run (`POST /api/pipelines/run`) never calls `check_parse_contract`…~~ **RESOLVED same session — see the Addendum below (commit `7cef743`).** The gap was real and is now closed with parity to intake; **T-165 → done**.
2. **The Provenance-screen "Runbook metrics" pin is a near-miss the `34f5380` fix did not reach.** `RunReport.tsx`'s own "Runbook metrics" pin is now correctly wrapped in `<Missing/>`/`formatScalar` when no `started` event exists. But `screens/Provenance.tsx`'s `ProvenanceHeader` component has a **separate, near-identical** "Runbook metrics" pin (`gp.runbook_metrics.length`, unwrapped) that early-returns "No run header captured" when `!started` — so the exposed edge case is narrower (a `started` event that exists but whose payload's `runbook_metrics` field is malformed/absent still renders raw `0`), but the same class of gap. Not fixed this round (frontend code is out of scope for a doc-keeper pass); named here and in T-165's sibling note so it isn't lost. *(This is the more precise version of the "RunReport runbook-metrics pin" tail named in this session's brief — grounded against the actual two call sites rather than assumed identical.)*
3. **`Lineage.tsx`'s "gate ran" evidence is `detail.cards.length > 0` only** — a run that completed with genuinely zero decision cards (an edge case; not verified reachable through the current demo/fixture set, since WS-01's `QC-MISSING` produces a HOLD card rather than zero cards) would show the terminal decision-gate banner as "not run" even though `run_gate` executed. Not fixed this round; named as a labelled limitation, not silently dropped. *(The "Lineage 0-samples handling" tail named in this session's brief.)*
4. **The Admin page-access editor cannot distinguish "System agents" from "Agent triage."** Both routes share `PageId: 'agent'` (a deliberate, cheaper implementation choice — Decision above), so an admin granting/denying "Agent triage" access grants/denies both views together. If per-view access control becomes a real requirement, this needs the spec's originally-proposed dedicated `system-agents` `PageId` (spec §`WS-1b`).
5. `design/frontend/agent-triage-redesign-spec.md`'s remaining slices (2–6: the `AgentDockProvider`
   floating window, dock chips/multi-session, the shared cross-run store) stay entirely spec-only —
   unaffected by this round.

## Distilled into

- [docs/planning/tasks.md](../planning/tasks.md) — T-155–T-165.
- [docs/design/frontend/README.md](../design/frontend/README.md) — §4 App shell, §5.4 Decision cards, §5.5 Review queue, §5.6 Provenance, §5.7 Agent triage, §6 Pipeline builder / Advisory agents.
- [docs/design/ui-conventions.md](../design/ui-conventions.md) — new UIC-20.
- [docs/design/agents.md](../design/agents.md) — Pipeline-vs-system agents section, QC-triage roster row.
- [docs/design/frontend/agent-triage-redesign-spec.md](../design/frontend/agent-triage-redesign-spec.md) — Status field + implementation-note.
- [docs/design/architecture.md](../design/architecture.md) — Advisory agent reads bullet.
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-104 addendum.
- This entry.

## Addendum (same day) — G8 landed: Builder-Run parse-contract parity (commit `7cef743`)

The doc-sweep above surfaced (Open questions §1 / **T-165**) that Builder-Run had no
`check_parse_contract` call, unlike intake post-WS-09. That gap was **closed the same session**,
test-first, so this journal's own §1 is now resolved:

1. **The fix** — `api/routers/pipeline_run.py` calls `check_parse_contract(graph, body.name)` right
   after `compile_record`, before the driver is launched. This is the same structural, tool-free
   check `api/routers/intake.py` already ran (WS-09 #1) — so the two execution paths now reach parity:
   an approved authored pipeline whose catalogued nodes can't collectively produce the frozen-five
   is rejected at submit (422) instead of running to completion in Nextflow and dying at parse.
2. **Why it was reverted once, and how the fixtures were the real bug** — a first attempt broke 5
   tests; the contract was correct, the *fixtures* were unrealistic. `test_pipeline_run.py` (a
   minimal `fastp → bwa-mem2` graph) and `test_io_path_wiring.py` (`_GRAPH_3KIND`, a partial
   fastp→bwa→bcftools-call chain) both produce only a BAM/VCF, not the frozen-five, so the contract
   *should* reject them. Both were swapped to the shared `germline_graph_dict()` — the real gate-able
   chain — reused (not transcribed) so the fixture can never drift from the seeded pipeline. The two
   input-validation tests were made deterministic against the 3-kind graph (supply two kinds, omit
   one, so which category the endpoint names is order-independent).
3. **The anti-scaffold guard** — a new red test `test_run_rejects_a_non_gateable_approved_pipeline`
   freezes the gap: an approved non-gate-able graph must 422. Proven **red-before-impl** by stashing
   the endpoint hunk and re-running (202 without the check → 422 with it), so the test can only pass
   on the real wiring, not a scaffold.
4. **Verification** — full offline suite **715 passed / 8 skipped**; `mypy` + `ruff` clean.
   Distilled into `docs/planning/tasks.md` **T-165 → done**.

On **Open questions §2** (the `Provenance.tsx` `ProvenanceHeader` runbook-metrics pin): re-examined
against the code rather than assumed. `ProvenanceHeader` early-returns "No run header captured" when
`!started`, and past that renders `gp.runbook_metrics.length` — which is "0" only when a *present*
started event carries an empty/malformed list. `RunReport.tsx`'s `formatScalar(length)` renders the
identical "0" in that same state (0 is a real count, not an absence). So the two pins are
**behaviorally equivalent in every reachable state**, and "0 runbook metrics" is truthful when the
gate ran with an empty runbook — there is no real honesty gap to fix, so the pin was left unchanged
(no churn to correct code). §3 (`Lineage.tsx` 0-cards) and §4 (shared `PageId`) remain labelled
limitations as written.
