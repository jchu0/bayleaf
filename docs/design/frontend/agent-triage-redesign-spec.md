# Agent Triage / System-Agents Redesign — Design Spec

| Field | Value |
|---|---|
| **Status** | Spec — **Slice 1 (§12, "IA move") fully landed 2026-07-13**, including `WS-1b`'s dedicated `systemAgents` `PageId` + `/system-agents` page (see the note below); Slices 2–6 (the `AgentDockProvider` floating window and everything after it) remain spec-only, to be built later |
| **Date** | 2026-07-12 (MST) |
| **Type** | Product-design spec sheet (fable) — IA split + a new floating-window interaction |
| **Problem** | (1) The global **system agents** (pipeline-repair, archivist) are pinned inside a *per-run* screen even though they act cross-run. (2) "Ask the agent" is a static, scrim-backed pop-out that dies on navigation — it cannot follow the operator around the app. |
| **Scope** | Frontend IA + interaction only. **No verdict/gate semantics change.** Agents stay advisory (ADR-0001); nothing here lets an agent set or override a verdict/confidence. |
| **Audience** | software / design / reviewers |
| **Related** | [ui-conventions.md](../ui-conventions.md) (UIC-1..19), [agents.md](../agents.md) (roster + taxonomy), [ADR-0001](../../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0022](../../adr/ADR-0022-agent-observation-binding.md), [frontend/README.md](README.md), [audit/ux-duplicate-data-review.md](../../../audit/ux-duplicate-data-review.md) (the `useRun(runId)` cache this reuses), [journal 2026-07-13-audit-fixes-ia.md](../../journal/2026-07-13-audit-fixes-ia.md) (the partial-landing sweep) |

> **What actually shipped vs. this spec (2026-07-13).** The maintainer's literal complaint — "system
> agents and agent triage look like duplicate pages" — is fixed. It landed in two steps: first a
> cheaper interim (one `AgentTriage.tsx` component with a route-derived `isSystemView = !runId`
> conditional, both routes sharing `PageId: 'agent'`, the crumb disambiguated by a `TopBar.tsx`
> sentinel), then **`WS-1b` in full (page-naming landing, verified in code):** a dedicated
> `SystemAgents.tsx` component on its own **`/system-agents`** route with its own **`systemAgents`
> `PageId`** + "System Agents" nav item in `access.ts`/`PAGE_CATALOG`, while `AgentTriage.tsx` is now
> the per-run **Triage** page (`/runs/:id/agent`, `PageId: 'agent'`) with the launchers removed. Net
> effect: the visual duplication is gone, the nav/crumb read correctly, **and** an Admin page-access
> grant **can now** separate "Triage" from "System Agents" (each has its own `PageId`) — closing the
> gap the interim left open. **Still unbuilt** below: §4 (the promoted workspace panels), §5 (the
> `AgentDockProvider` floating window), and §§6–12. See
> [design/agents.md](../agents.md) § "Pipeline-vs-system agents" for the grounded, dated detail and
> [journal 2026-07-13-audit-fixes-ia.md](../../journal/2026-07-13-audit-fixes-ia.md).

This is the design of record for splitting node-attached from system agents and for turning "Ask the agent" into a persistent floating workspace. Every item carries a stable id (`TX-N` taxonomy, `WS-N` workspace, `AW-N` ask-window, `PV-N` provenance) so it can be referenced without quoting.

---

## 1. Context & problem

Two agent surfaces exist today, and both are mis-scoped:

1. **`screens/AgentTriage.tsx` hosts three things at once** — the per-run QC-triage note (`AgentSubjectCard` + `AgentComposer`, correctly run-scoped) **and** two launcher cards for **pipeline-repair** and **archivist** (`AgentTriage.tsx:122-135`, opening `PipelineRepairModal`/`ArchivistModal`). The comment even admits the awkwardness: *"they act on runs / recurring signatures / the organization — NOT on a single pipeline node — so they launch from here, not the Builder palette"* (`AgentTriage.tsx:30-31`). They were moved off the Builder palette (correct — they never had a node attachment) but landed on the **wrong** page: a per-run route (`/runs/:runId/agent`). Pipeline-repair reasons over recurring signatures **across every run**; the archivist indexes **every released run**. Scoping them to whichever run happens to be in context is a category error — and each modal silently re-fetches the whole cross-run payload (`api.monitoring('all', 25)`, `api.archiveIndex()`) to escape that scope.

2. **`AgentComposer` is a dead-end pop-out.** It toggles between an inline card and a scrim-backed centered modal (`AgentComposer.tsx:51-67`). The scrim makes it modal-ish; the fixed position and per-subject remount (`AgentTriage.tsx:232`, `key={composer-${sample}}`) mean it **cannot survive navigation** and **cannot follow a question across screens**. The maintainer wants a movable, resizable, persistent window an operator keeps open while they work.

**The redesign, in one line:** give system agents their own **global workspace** (a nav destination), leave node-attached agents exactly where they are (per-run / per-node), and replace the pop-out with **one persistent, draggable, resizable floating window** that any agent surface can launch.

---

## 2. The agent taxonomy — where each agent lives (`TX`)

Grounded in [agents.md § "Pipeline-vs-system agents"](../agents.md) and the roster. The split is **by what an agent scopes over**, and it dictates *where the UI puts it*:

| id | Agent (roster #) | Scopes over | Lives in (after this redesign) | Why |
|---|---|---|---|---|
| **TX-1** | **QC-triage** (#1) | one flagged **card** in one run | **Per-run** — `screens/AgentTriage.tsx` (unchanged placement); node-attachable in Builder | Its subject is a single card's findings; meaningless without a run context |
| **TX-2** | **Node-authoring** (#6) | one **Builder node** (card author) | **Builder palette** — `AuthorToolNodeModal` (unchanged) | Authors a card in the graph being edited; a compose-time tool, not a run advisor |
| **TX-3** | **Pipeline-repair** (#2) | **recurring signatures across all runs** | **NEW System-agents workspace** (global) | Cross-run failure reasoning; a run context only narrows it artificially |
| **TX-4** | **Archivist** (#3) | **all released runs / the org** | **NEW System-agents workspace** (global) | Indexes the whole platform; inherently run-independent |
| **TX-5** | **Feedback-triage** (#4) | the **off-gate feedback corpus** | **Admin** (governance) — *not* the agent workspace (see Open Q1) | No canvas/run presence; it's a product-ops tool, Admin-scoped |

**Rule (`TX-6`):** a page may host an agent **only if the agent's scope matches the page's scope.** A run-scoped page hosts run-scoped agents; a global page hosts global agents. This is the invariant the current code violates and the whole IA change enforces.

**What moves:** `TX-3` + `TX-4` leave `AgentTriage.tsx` (delete the `AgentLauncher` block at `AgentTriage.tsx:119-135` and the `repairOpen`/`archivistOpen` state). `PipelineRepairModal`/`ArchivistModal` bodies are **promoted into the new workspace** (see §4) — the modal shells go away, the rich bodies (`BuilderModals.tsx:369-638`) are reused as panels.

**What stays put:** `TX-1` (the `AgentSubjectCard` + the launch point for the ask-window), `TX-2` (Builder), `TX-5` (Admin).

---

## 3. IA / nav placement (`WS-1`)

Add **one** global destination. It belongs in the **Analyze** group (cross-run advisory, alongside Provenance/Monitoring), *not* Operate (no per-run step) and *not* Configure (nothing is being authored).

```
OPERATE      Inbox · Review queue · Accessioning · Submit · Intake · Decision cards · Runs
ANALYZE      Provenance · Agent triage · ✦ System agents (NEW) · Monitoring
CONFIGURE    Pipeline builder · Settings
ADMIN        Admin panel        (isAdmin only; feedback-triage surfaces here)
```

Concrete wiring (mirrors every existing page — do not invent a new pattern):

1. **`WS-1a`** — Route: add `<Route path="/agents" …>` in `App.tsx`, page-gated `<RequirePage page="system-agents">` like its siblings (`App.tsx:71-80`).
2. **`WS-1b`** — Access catalog: add `'system-agents'` to `PageId` and `PAGE_CATALOG` (`access.ts:19-31, 38-51`) in group `'Analyze'`, label **"System agents"**. This satisfies **UIC-6** (every page admin-assignable) automatically.
3. **`WS-1c`** — Nav: add one `Item` to the Analyze group in `Sidebar.tsx:87-106` — label "System agents", a non-run-scoped `to: '/agents'` (a **fixed** path, unlike the per-run `/runs/:run/agent`), icon suggestion `Bot`/`Sparkles`, `page: 'system-agents'`.
4. **`WS-1d`** — Keep the existing **"Agent triage"** item exactly as-is (per-run, `page: 'agent'`). Two nav items now read clearly: *Agent triage* = "triage this run's flagged samples"; *System agents* = "the cross-run advisory agents". Naming disambiguation is deliberate (see Open Q1 if the maintainer prefers a single "Agents" hub).

**Do NOT** deep-link the workspace from `DecisionContextRail`'s "Ask agent to triage" button (`DecisionContextRail.tsx:80-87`) — that button is correctly QC-triage/run-scoped and stays pointed at `/runs/:run/agent`.

---

## 4. System-agents workspace layout (`WS`)

A **two-pane** screen: a fixed short **agent roster** (left) + the selected agent's **panel** (right). The roster is a *fixed small set* (2 agents, maybe 3) so a vertical list is correct and scale-safe; the **data each agent surfaces is unbounded**, so those controls are dropdown + `Pager` (never pills, never infinite rows — scale-aware rule).

```
┌─ System agents ──────────────────────────────── [ global · cross-run ] ──┐
│ Advisory · these agents never set a verdict — rules decide (ADR-0001).    │  ← keep this safety banner (UIC-1 exempts limitation warnings)
├───────────────────┬──────────────────────────────────────────────────────┤
│ AGENTS            │  ✦ Pipeline-repair          claude · <model> · armed  │  ← PV pill (§6)
│                   │  Watches recurring failure signatures across runs.    │
│ ▸ Pipeline-repair │  ──────────────────────────────────────────────────  │
│    #2 · armed     │  Signature ▼ [ QC-DEPTH-LOW · 14× ▾ ]  (dropdown+pager)│  ← unbounded → select, not pills
│                   │  ┌─ Proposed fix (advisory) ─────────────────────────┐│
│   Archivist       │  │ summary … · rationale … · attach_to · scope       ││  ← reuse BuilderModals repair body
│    #3 · stub      │  │ citations:  KB-217 · INC-0042   (heuristic score)  ││
│                   │  └───────────────────────────────────────────────────┘│
│  (feedback-triage │  [ Ask the agent ▸ ]   [ Route to review queue ⚠ ]    │  ← Ask opens the window (§5); Route is a confirmed write
│   → Admin, Q1)    │  provenance: claude · <model> · advisory · off-gate    │
└───────────────────┴──────────────────────────────────────────────────────┘
```

1. **`WS-2` — Left roster.** One selectable row per system agent: name, roster #, and a **source/status chip** (`armed` = `claude`, `stub` = offline) read from Settings' agent-tiering state. Selection is URL-owned (`/agents?agent=pipeline-repair`) so it deep-links and survives reload (the `useUrlFacet` idiom from the duplicate-data review, `RunDetail.tsx:113-140`). Default = the first agent. This is a list of ≤3 fixed rows — **not** a pill row and **not** paginated.
2. **`WS-3` — Right panel = the promoted modal body.** Render the existing `PipelineRepairModal` / `ArchivistModal` **content** (`BuilderModals.tsx:386-462` / `528-547`) inline as a panel — same signature picker, same proposal/digest rendering, same honest error/empty states. Drop the `ModalShell`/overlay wrapper; keep every advisory label and the citation rows verbatim.
3. **`WS-4` — Cross-run pickers are dropdown + pager.** Pipeline-repair's signature `<select>` (`BuilderModals.tsx:406-418`) already exists; formalize it as a searchable dropdown that **server-windows** when signatures grow (today it pulls `monitoring('all', 25)` — cap and paginate; see the duplicate-data review's `#7`/`#2` fixes). The archivist's index is a summary (no per-item list) — leave as-is.
4. **`WS-5` — Every panel ends with a provenance footer** (§6) and, where an action exists, a **confirmed + audited** hand-off (§7) — never a silent write.
5. **`WS-6` — One canonical fetch.** The workspace and the ask-window must share **one** cross-run store, not re-fetch per panel (today the two modals fetch independently). Reuse/introduce a `useMonitoring()` / `useArchiveIndex()` module cache, consistent with the `useRun(runId)` direction in [ux-duplicate-data-review.md](../../../audit/ux-duplicate-data-review.md).

---

## 5. The draggable "Ask the agent" window (`AW`)

Replaces `AgentComposer`'s pop-out. It is a **non-modal, persistent, draggable, resizable floating window** — a movable workspace panel, *not* a modal and *not* a scrim-backed overlay.

### 5.1 Architecture (the load-bearing decision)

1. **`AW-1` — Hoist it above the router.** The window is owned by a new `AgentDockProvider` mounted in `App.tsx` **outside** `<BrowserRouter>` — a sibling of `ToastProvider`/`ConfirmProvider` (`App.tsx:50-54`). Route changes re-render the page under it; the window and its threads **persist untouched**. This is the single reason the current pop-out can't do what's asked, so it is non-negotiable.
2. **`AW-2` — Launch = open a session, not mount a component.** Any surface (a System-agents panel `WS-5`, the per-run `AgentSubjectCard`, a Decision card) calls `openAsk({ agent, context })`. `context` is a **captured reference** — `{ runId?, sampleId?, signature?, label }` — snapshotted at launch, so the window keeps its subject even after the operator navigates away.
3. **`AW-3` — Position/size persist** in `PrefsContext` (localStorage), like `navCollapsed` (`Sidebar.tsx:236`). Reopening restores where the operator left it.

### 5.2 Window states (`AW-4`)

| State | Description | Chrome |
|---|---|---|
| **Closed** | nothing rendered; launch affordances live on agent surfaces | — |
| **Floating** (default open) | free-positioned card, draggable + resizable, top z-index when focused, **no scrim** (page stays fully interactive) | full title bar + body + resize handles |
| **Docked** | snapped to the **right edge**, full-height column; page content is unblocked (overlay, does not reflow — see Open Q3) | dock/undock toggle active |
| **Minimized** | collapses to a **dock chip** in a bottom-right rail (avatar + context label + unread-reply dot); click restores | chip only |
| **Maximized** (optional) | near-fullscreen centered workspace, still non-modal | restore replaces maximize |

```
FLOATING ─────────────────────────────────────────────────────────────
 ╔═ ⣿ drag handle (entire title bar) ═══════════════════════════════════╗
 ║ ✦ Pipeline-repair  ⟨RUN-2026-…-A · QC-DEPTH-LOW⟩   stub·$0   ⇥ – ▢ ✕ ║  ← avatar · name · context chip · source pill · [dock][min][max][close]
 ╠══════════════════════════════════════════════════════════════════════╣
 ║ Advisory · won't change the verdict                                  ║  ← persistent, never scrolls away
 ║ ┌── transcript · aria-live=polite ────────────────────────────────┐ ║
 ║ │  you ▸ how sure is this depth, not a swap?                       │ ║
 ║ │  ✦  ▸ streaming reply…▌                              [ Stop ]    │ ║
 ║ │       ⌞ cite: finding F-1042 · KB-217 (heuristic) ⌝             │ ║
 ║ └──────────────────────────────────────────────────────────────────┘ ║
 ║ [ quick-ask chip ] [ chip ] [ chip ]           (horizontal scroll)   ║
 ║ ┌ Message the agent…  (Enter send · Shift+Enter newline) ─┐ [ Send ] ║
 ║ └───────────────────────────────────────────────────────────┘        ║
 ║ Advisory · the agent can't change the verdict                    ◢   ║  ← corner resize handle
 ╚══════════════════════════════════════════════════════════════════════╝

MINIMIZED → bottom-right dock rail:
    [ ✦ Pipeline-repair · RUN-…-A ●1 ]  [ ✦ QC-triage · HG002 ]      ← one chip per open session
```

### 5.3 Chrome & behavior

1. **`AW-5` — Title bar** (drag handle spans the whole bar): agent avatar + name · **context chip** (the captured subject) · **source pill** (`stub·$0` / `claude·<model>`) · spacer · **dock/undock** · **minimize** · **maximize/restore** · **close (✕)**.
2. **`AW-6` — Drag:** pointer-drag the title bar to move. **Clamp to viewport** (title bar can never leave the screen). On window/viewport resize, re-clamp. Respect `prefers-reduced-motion` (no inertia; instant).
3. **`AW-7` — Resize:** bottom-right corner handle (min ~360×320, max = viewport). Body is a flex column: title bar + advisory strip fixed, transcript `flex-1` scroll, composer footer fixed — identical structure to the current popped layout (`AgentComposer.tsx:52-57`), just detached from the scrim.
4. **`AW-8` — Focus / z-index:** clicking anywhere in a window brings it to front and shows a focus ring; only the focused window sits on top. No scrim ever — coexistence with the page is the whole point.
5. **`AW-9` — Close vs minimize:** **✕ ends the session** (drops the thread; advisory + non-persistent, so no confirm needed — see §7). **Minimize preserves it** as a dock chip. `Esc` while focused = **minimize** (reversible), never close (avoid losing a thread to a stray key).
6. **`AW-10` — Multi-session model (recommended, minimal):** at most **one visible floating window**; additional launches (or minimizing the current one) become **dock chips** in the bottom-right rail. Selecting a chip restores that session and minimizes the previous. Cap concurrent sessions (e.g. **6**) and show "6 max — close one to start another" — scale-aware, no unbounded window pile. *(Simultaneous multiple floating windows is an explicit non-goal for v1; see Open Q2.)*
7. **`AW-11` — Context re-targeting:** the window's context chip is a read-only label of the captured subject. Launching a **new** ask from a different subject opens a **new session** (new chip) — it never silently repoints an existing thread.

### 5.4 The ask/reply contract (design against the parallel backend)

1. **`AW-12` — Send path:** the textarea + quick-ask chips share one `ask(agent, context, text)` call (mirrors `AgentComposer.submit`, `AgentComposer.tsx:27-41`). Enter sends; Shift+Enter newlines.
2. **`AW-13` — Streaming:** the reply streams into the transcript token-by-token under `aria-live="polite"`; a blinking caret marks in-flight; a **Stop** control cancels. The source pill shows the **armed** source optimistically and finalizes on completion (`stub·$0` if the seam falls back).
3. **`AW-14` — Advisory-only, always:** no message ever renders or implies a verdict/confidence (ADR-0001; `agents.md` invariants 1–2). The persistent advisory strip (`AW` header) and the footer line restate it. The **honest offline** reply is verbatim the existing copy (`AgentComposer.tsx:36`: *"Offline (rule-derived): I can't change the verdict — that's the rule engine's call…"*).
4. **`AW-15` — Grounding:** an agent reply that cites evidence renders **citation chips** reusing `AgentSubjectCard`'s `FindingCite`/`KnowledgeCite` split (`AgentSubjectCard.tsx:122-158`) — `finding` chips deep-link to `/runs/:run`, `knowledge` chips show the corpus ref. Evidence stays visually separate from generated prose (ADR-0001 separation, UIC-8).

---

## 6. Advisory & provenance treatment (`PV`)

Provenance must be legible on **every** agent surface — workspace panels *and* the ask-window — so "advisory, not a decision" is never in doubt. All fields already exist on the wire (`types.ts`: `mode: 'stub'|'claude'`, `generated_by`, `model`, `citations[].source_kind`).

1. **`PV-1` — Source pill** (reused everywhere): `stub · $0` (offline, deterministic) vs `claude · <model>` (armed). Same rendering the modals use (`BuilderModals.tsx:284, 444`). Never present stub prose as a live answer, never present live prose as deterministic (the exact bug `AgentTriage.tsx:95-102` guards against).
2. **`PV-2` — Advisory tag** on every agent message/panel: the amber-neutral "advisory" chip already standard (`AgentSubjectCard.tsx:43-45`).
3. **`PV-3` — Verdict-firewall copy** in each footer, verbatim from `AgentSubjectCard.tsx:106-107`: *"The verdict is set by the rule engine, not this note. Reviewer judgment required before any action."*
4. **`PV-4` — Citations are grounded, never invented:** render only `source_kind`-keyed labels the contract carries; score labelled `(heuristic)` (`BuilderModals.tsx:277, 452`), never a calibrated probability (life-science guardrail 2).
5. **`PV-5` — Honest unavailability:** on any agent/seam error, degrade to the deterministic stub and show the existing "agent unavailable — the gate is unaffected" banner (`BuilderModals.tsx:202-205, 396-399, 540-543`) — as a message in the window, not a crash.
6. **`PV-6` — No verdict UI, anywhere in these surfaces.** No verdict dot, no confidence number, no "the agent decided" phrasing. The only verdict an operator sees is on the Decision card, set by rules.

---

## 7. Writes, confirmation & audit (`AW-16`)

An **ask is a read** — advisory, no state change — so it needs **no** confirm (the explicit-edit+audit rule governs *writes*). But an **action spun off from an agent** is a write and must obey the app-wide gate:

1. The window/workspace **never performs a write itself.** "Route to review queue" (`WS-5`) and any "accept proposal" hand off to the **existing** confirmed + audited flows — `useConfirm` + a real-outcome `toast` + the audit log, exactly as `PipelineRepairModal`'s queue hand-off already does (`BuilderModals.tsx:469-481`).
2. Node-authoring "accept to library" (if ever surfaced) stays reviewer/approver-gated server-side (`require_role`) — the UI gate is a view convenience, not authorization (UIC-6 banner).
3. Closing an ask session (`AW-9`) drops an advisory thread only — no persisted state, so no confirm. *(If threads become server-persisted per Open Q4, revisit.)*

---

## 8. Empty / loading / error / streaming states (`AW-17`)

| Surface | State | Treatment |
|---|---|---|
| Workspace panel | loading | "Asking the <agent>…" spinner (`BuilderModals.tsx:392-394`) |
| Workspace panel | empty | agent-specific honest empty (e.g. "No recurring signatures across served runs", `BuilderModals.tsx:400-403`) |
| Workspace panel | error | degrade-to-stub banner (`PV-5`) |
| Ask-window | no messages | the current empty state (`AgentComposer.tsx:103-111`) |
| Ask-window | awaiting first token | "Asking the <agent>…" row in transcript |
| Ask-window | streaming | tokens + caret + **Stop** (`AW-13`) |
| Ask-window | seam offline | honest stub reply as an agent message (`AW-14`) |
| Ask-window | context gone (run released/deleted) | keep the thread readable; a muted "this context is no longer available" note under the chip — never fabricate |

---

## 9. Accessibility (`A11Y`)

Extends the UIC-19 baseline to the two new surfaces:

1. **`A11Y-1`** — Window is `role="dialog"` **`aria-modal="false"`** (non-modal — it must NOT trap global focus; the page stays operable). Labelled by the title bar (`aria-labelledby`).
2. **`A11Y-2`** — Full keyboard operation: launch focuses the composer; Tab cycles within the focused window; a documented shortcut (e.g. `Esc` to minimize, a focus-window hotkey) moves between window and page. Title-bar buttons (dock/min/max/close) are real `<button>`s in tab order.
3. **`A11Y-3`** — Keyboard move/resize: when the title bar is focused, arrow keys nudge position; modifier+arrows resize — so drag/resize isn't mouse-only.
4. **`A11Y-4`** — Streaming replies announced via `aria-live="polite"`; an error reply may use `role="alert"` (matching Toast's assertive path, UIC-19).
5. **`A11Y-5`** — Dock chips are buttons with `aria-label` (agent + context + unread count). `prefers-reduced-motion` disables drag inertia and stream animation.
6. **`A11Y-6`** — Roster (`WS-2`) is a `listbox`/roving-tabindex selector (reuse the `Tabs`/`SegmentedControl` a11y patterns already shipped, UIC-19).

---

## 10. Cross-cutting convention conformance

1. **UIC-1** — no flavor text; **keep** the "advisory · never sets a verdict" limitation banner (UIC-1 explicitly exempts safety/limitation warnings).
2. **Scale-aware** — fixed agent roster is a short list (fine); all *unbounded* sets (signatures, sessions) use dropdown/`Pager`/capped-dock — never pills, never infinite rows.
3. **Explicit-edit + audit** — §7: asks are reads (no confirm); spun-off writes route through `useConfirm`+toast+audit.
4. **Theme** — warm Japandi light + subtle dark: use the existing tokens only (`bg-card`/`bg-card-2`/`border-line`/`border-line-strong`/`text-text{,-2,-3}`/`bg-accent`/`bg-accent-weak`/`shadow-card`/`shadow-pop`) so both themes and all 6 palettes (UIC-7) inherit correctly. **No new hardcoded colors.** The window's float shadow = existing `shadow-pop`.
5. **Advisory framing everywhere** — §6; no element implies an agent set a verdict.

---

## 11. Open questions (for the maintainer)

1. **Feedback-triage & the "Agents" naming.** Does feedback-triage (`TX-5`) join the System-agents workspace as a third agent, or stay in Admin (it's off-gate/governance)? And do you prefer two nav items (*Agent triage* + *System agents*) or a single **"Agents"** hub with a "this run" section + a "system" section? (Spec assumes: feedback-triage stays in Admin; two nav items.)
2. **Session model depth.** Is the parallel backend a **multi-turn thread** or **single-shot Q&A**? And is one-window-plus-dock (`AW-10`) enough, or do you want multiple simultaneous floating windows? (Spec recommends one visible + a capped dock; multi-window is a labelled non-goal for v1.)
3. **Dock = overlay or reflow?** Right-docked (`AW-4`) as an overlay (cheap, no layout change) vs. pushing page content (cleaner, but touches every screen's max-width). (Spec assumes overlay.)
4. **Thread persistence.** Advisory asks in localStorage only, or server-persisted to the experience ledger (ADR-0007 ML-ready outputs)? Persistence would add an audit/retention surface and change `AW-9`'s close semantics.
5. **Does per-run QC-triage's inline composer also become the floating window?** (Spec recommends unifying on one window component, launched with a `{runId, sampleId}` QC-triage context — deleting the bespoke `AgentComposer` pop-out — so there's one ask surface, not two.)

---

## 12. Implementation-effort note

Independently shippable slices, win/risk-ordered:

| # | Slice | Effort | Notes |
|---|---|---|---|
| 1 | **IA move** — new `/agents` route + `system-agents` PageId + nav item; delete the two launchers from `AgentTriage.tsx`; promote the two modal bodies into workspace panels | **M** | Pure relocation; mostly reuses `BuilderModals` bodies. No new backend. |
| 2 | **`AgentDockProvider`** (hoisted, persistent) + one **floating window** with drag/resize/min/close + position persistence | **L** | The core new interaction; no scrim; clamp-to-viewport is the fiddly part. |
| 3 | **Ask contract wiring** — `openAsk`, context capture, quick-asks, streaming + Stop, source pill, citations reuse | **M** | Against the parallel backend; falls back to the honest stub if unarmed. |
| 4 | **Dock chips + multi-session** (`AW-10`) + maximize/dock states | **M** | Ship after the single window works; capped, scale-aware. |
| 5 | **A11Y pass** (`A11Y-1..6`) — keyboard move/resize, live regions, roving roster | **S–M** | Extends the UIC-19 baseline; do alongside #2. |
| 6 | **Shared cross-run store** (`WS-6`) so panels + window don't re-fetch | **S** | Reuses the `useRun`/`useMonitoring` cache direction from the duplicate-data review. |

**Cheapest real win first:** slice 1 alone fixes the mis-scoping (the maintainer's #1 ask) with almost no new UI — it's a move, not a build. The window (slices 2–4) is the larger investment and is where the compute budget goes.

---

### Critical files for implementation

- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/screens/AgentTriage.tsx  (strip system-agent launchers; keep QC-triage; launch the window)
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/components/AgentComposer.tsx  (replaced by the floating window)
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/components/BuilderModals.tsx  (PipelineRepair/Archivist bodies → workspace panels)
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/components/AgentSubjectCard.tsx  (citation + advisory-copy idioms to reuse)
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/App.tsx  (add route; mount AgentDockProvider above the router)
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/access.ts  (add `system-agents` PageId + catalog row)
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/components/Sidebar.tsx  (add the Analyze nav item)
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/context/PrefsContext.tsx  (persist window position/size)
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/docs/design/agents.md  (taxonomy source of truth — keep in sync)
