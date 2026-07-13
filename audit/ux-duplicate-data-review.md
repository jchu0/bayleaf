# UX Review — Duplicate Data Across Tabs/Views (system-wide)

| Field | Value |
|---|---|
| **Date** | 2026-07-12 (MST) |
| **Type** | Read-only design pass (fable) — information-architecture audit + unified fix |
| **Problem** | The same datum renders/derives across multiple tabs/views/facets (catch-all "All" ⊇ its subsets), a rendering + cognitive tax that scales badly even with lazy loading |
| **Scope** | Presentation/IA only — verdict/gate semantics untouched |

This is the design of record for collapsing duplicate-data patterns. The **unified pattern** is the actionable part; the **per-cluster audits** (appendix) are the grounded catalog it's built from.

---

## Unified fix — the design

# Unified IA Pattern — "One canonical list, faceted views"

All paths below are under `/Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/` (absolute paths in the Critical Files list). Verdict palette (`verdict.ts:32,50,58`) and gate semantics are untouched throughout — everything here is presentation and state plumbing.

---

## 1. The principle

**Every domain gets exactly one canonical, memoized list, fetched once. Everything else — tabs, chips, counts, KPI tiles, bars, badges, dropdowns — is a selector over it, never a second fetch, a second derivation pass, or a second rendered copy.**

Three corollaries:

1. **"All" is not a category; it is the absence of a filter.** A tab named "All" that coexists with subset tabs makes every row a member of ≥2 tabs and forces a second count derivation. Either remove it (default to the *actionable* facet, let search escape the facet — the Review queue already has exactly this machinery for resolved, `ReviewQueue.tsx:329`) or define it as filter-cleared state whose count is the one total the `Pager` already prints ("Showing X–Y of Z", `Pager.tsx:50-52`).
2. **Facets must partition.** A facet set over one list is only valid if the facets are mutually disjoint. Overlapping facets (RunDetail's `attention` ⊇ `escalate ∪ rerun ∪ hold`, alongside `all`, `RunDetail.tsx:194-204` — three memberships per flagged card) are forbidden; an overlapping "roll-up" becomes a **group divider** inside the sorted list (the attention-first sort at `RunDetail.tsx:191-193` already encodes it) or a clickable segment on a summary bar.
3. **Tabs are for views, not filters.** A tab is warranted only when it changes the *rendering or the actions* (Inbox Board vs Calendar — different layout, `Inbox.tsx:1571-1574`; Provenance Lineage vs Events vs Artifacts). When two tabs render the same row component with the same actions and differ only in the predicate, that's a filter wearing a tab costume — collapse it. Both kinds must consume the same memoized index; a "view" that re-fetches (`AgentTriage.tsx:39`, `Provenance.tsx:46`) or re-derives (`RunReport.tsx:67-70` duplicating `RunDetail.tsx:40`) is a parallel copy, not a view.

When to use what:
- **Tabs (`Tabs.tsx`)** — disjoint views with different layout/actions, or a disjoint facet partition *without* a catch-all peer.
- **Single grouped list** — when the roll-up ordering already tells the story (verdict-sorted cards; run-grouped tickets, `ReviewQueue.tsx:350-357`): group headers with counts instead of extra facets.
- **Progressive disclosure** — history/archive (`resolved`, `cleared`, `done`): out of the default view, reachable via one explicit facet or toggle backed by a *server-windowed* query, never downloaded up front and hidden client-side (the current Resolved anti-pattern: full history fetched at `ReviewQueue.tsx:236` then windowed client-side at `329-335`).

---

## 2. The pattern kit

Six primitives. Four are extractions of code that already exists; two are small new shared pieces.

### 2a. Domain store — one fetch per entity (NEW: 3 contexts/hooks, modeled on `InboxContext.tsx`)

| Store | Canonical source | Consumers that stop fetching |
|---|---|---|
| `TicketsContext` | one `api.listTicketsPage()` (open + in_review full; resolved windowed via `since`, already supported — `api.ts:158-183`) | `ReviewQueue.tsx:231-243` (deletes the runs N+1 at 232), `InboxContext.tsx:201-207`, `NotificationBell.tsx` via InboxContext, Admin ActivityTab's `api.listTickets()` at `Admin.tsx:471` |
| `RunsContext` | one `api.runsPage()` (`api.ts:132-155`, header-borne `statusCounts` + total) | `Layout.tsx:13-16`, `RunOverview.tsx:229-239`, `RunSelector.tsx:53-62` self-fetch (keep as fallback), TopBar switcher |
| `useRun(runId)` | module-level cache over `api.run` | `RunDetail.tsx:77-78`, `Provenance.tsx:46`, `AgentTriage.tsx:39` — three fetches of the heaviest payload become one per run per session |

Same shape for singletons: hoist the `useApiHealth` interval (`hooks/useApiHealth.ts:13-26`) into one module poller with subscribers.

### 2b. `useFacetedList` hook (NEW — extracted, not invented)

The Review queue's `view` memo is already the correct single-pass pipeline: **tally → facet filter → search → window → paginate → group → `orderedIds`** (`ReviewQueue.tsx:303-359`). Extract it as `hooks/useFacetedList.ts`:

```
useFacetedList<T>({ items, facetOf, searchText, matches, page, perPage, groupBy? })
  → { counts, shown, total, paged, groups, orderedIds }
```

- `counts` is **one reduce** keyed by facet — replacing the 4 filter passes at `ReviewQueue.tsx:311-316`, the 3 more at `568-572`, Inbox's ≥7 scans (`Inbox.tsx:344-366, 1508-1510`), and Admin's `Admin.tsx:548-552`.
- `orderedIds` preserves the `useRangeSelect` contract exactly (flat render order, `useRangeSelect.ts:10-12`), so shift-select/parent-checkbox semantics survive unchanged.
- Page-clamp and reset-on-filter behavior already duplicated in five screens (`ReviewQueue.tsx:337-344`, `RunOverview.tsx:268-272`, `Monitoring.tsx:217-227`, `Inbox.tsx:353-361`, `Admin.tsx:554-559`) lands here once, feeding the shared `Pager`.

### 2c. `FacetBar` — the clickable summary bar (NEW component, built on `Bar.tsx`)

`ReviewStatusBar` (`ReviewStatusBar.tsx:12-30`) and `DecisionVerdictBar` (`DecisionVerdictBar.tsx:19-35`) are near-identical `SegmentBar`-plus-legend renderings that sit *next to* a separate count control showing the same numbers (`ReviewQueue.tsx:610-619`; `RunDetail.tsx:228+247-254`). Merge into one `components/FacetBar.tsx`: `SegmentBar` on top, the legend items rendered as **filter buttons** (count + dot, `aria-pressed`), colors passed through from `VERDICT_BAR`/`VERDICT_DOT` untouched. One grouped tally powers bar widths, legend counts, and the active filter. This deletes the "two adjacent summaries of one list" pattern instead of decorating it.

### 2d. `Tabs` stays — with two conventions

Keep `Tabs.tsx` as the canonical view selector (its own header says so, `Tabs.tsx:3-10`). New conventions: (1) a `Tabs` facet set must be a partition — no catch-all peer, no overlapping roll-up; (2) every `count` prop must come from the store's single tally, never a local `.filter().length`.

### 2e. Group headers + archive-as-facet

- **Group-within**: the run-group headers in ReviewQueue (`ReviewQueue.tsx:350-357, 773-775`) are the model — extract a tiny `GroupHeader` (label + count from the tally) and reuse it for RunDetail's "Needs attention" divider.
- **Archive-as-facet**: "cleared"/"done" sections are facet *values* on the one list (`Active n | Cleared n` via `SegmentedControl`, which `Tabs.tsx:8-9` reserves for exactly this kind of compact toggle), sharing the same row component and the same `Pager` — never a second simultaneously-mounted section (`Monitoring.tsx:573-599`, whose cleared side is unpaginated at `579`).

### 2f. Views are saved filters — URL-owned facet state

`RunDetail.tsx:113-140` already owns `?view=` and `?filter=` in searchParams with unknown-value fallback. Standardize this as a `useUrlFacet(key, values, fallback)` hook so Review queue status, Runs status, and Admin kind facets deep-link the same way. A "view" in this app *is* a URL: `/queue?status=open`, `/runs/:id?filter=escalate`. (This also fixes the "two spellings of the flagged set" — AgentTriage's flagged table becomes a deep-link to the same facet.)

Plus one shared-component repair: replace Monitoring's hand-rolled pager (`Monitoring.tsx:524-570`) with `<Pager noun="signatures">`, and give `Pager` ellipsis windowing (today it renders every page button, `Pager.tsx:74-89` — 80 buttons at 2,000 rows/25).

---

## 3. Decision rules — when is a separate tab legitimate?

Run every tab set through four tests:

1. **Disjointness test** — *Can one row appear under two tabs?* Yes → it's a filter, not a view. Collapse: drop the catch-all (default = actionable facet) or turn the superset into a group divider. Fails: ReviewQueue `all` (`ReviewQueue.tsx:71-76`), RunDetail `all`+`attention` (`RunDetail.tsx:197-204`), Admin `all` (`Admin.tsx:574-585`), Inbox `All` chip (`Inbox.tsx:363-367`).
2. **Action/layout test** — *Does switching tabs change the row component, the available actions, or the layout?* Yes → genuine view tab (Board/Calendar/Notes `Inbox.tsx:1571-1574`; Cards vs Report — different reading mode; Provenance's three tabs). No → filter (Monitoring Active vs Cleared: same `MonitoringSignatureRow`, same actions, `Monitoring.tsx:489-508` vs `579-597`).
3. **Default test** — the default facet is the *actionable* subset when the domain accumulates history (tickets → Open; runs → arguable, see table), and "everything" stays reachable via search (which escapes facets, per `ReviewQueue.tsx:329`) or an explicit windowed toggle. A catch-all default is only acceptable when browsing-everything genuinely is the page's job **and** the facets are disjoint (RunOverview) — and even then its count comes from the header total, not a client tally.
4. **One-tally rule** — any count rendered in two places (tab badge + tile + bar legend + bell) must be read from one memoized stats selector. Two predicates for one label is a bug factory (Inbox "Flagged": tile counts done items, chip doesn't — `Inbox.tsx:1508` vs `366`).

---

## 4. Per-page application table (worst-first)

| Page | Duplication today | Fix | Effort |
|---|---|---|---|
| **Review queue** (`ReviewQueue.tsx`) | O(runs) N+1 fetch (231-232) + separate full ticket fetch (236) + double resolved fetch (240-243); `All/Open/In review/Resolved` tabs (71-76, 613-619) with 7 full-array scans/render (311-316, 568-572); `ReviewStatusBar` as a second non-interactive summary (610) | Rows from `TicketsContext`; card detail lazy per expanded ticket. Drop `All` tab (default `open`; `filter` state already defaults to `'open'`, 202). Verdict summary becomes the clickable `FacetBar` (verdict axis) over the same tally that feeds the three status tabs. Resolved = server-windowed facet only (`since` param exists, `api.ts:164`); delete `recentResolvedKeys` (213, 252, 330-331). Keep `view` pipeline shape → `useFacetedList`, preserving `orderedIds`/selection (303-363) | **L** |
| **Admin › Activity** (`Admin.tsx:454-586`) | `All` + 5 kind tabs over a feed fabricated from 3 full collection fetches (468-472) re-run on every tab remount (808); counts scan (548-552) | Tickets from `TicketsContext`; hoist the fetch to Admin mount (or better: one backend `?kind=&page=` feed endpoint). Kind tabs stay (disjoint) minus `All`: default = unfiltered state whose count is the Pager total. One tally | **M** (client) / **L** (with backend) |
| **Inbox** (`Inbox.tsx`) | `All/Unread/Flagged` chips + KPI tiles + tab badge + bell = 4 derivations, 2 predicates for "flagged" (344-366, 1508-1510, 1557; `NotificationBell.tsx:32-35,117`); Board/Calendar/Notes each re-partition `items` (853-856, 977-987, 1180) with divergent done-visibility (347 vs board/calendar) | One `inboxStats` + one index `{byColumn, byDueDay, notes, recent}` computed in a single memo in `InboxContext.tsx` (next to `unreadCount`, 281); tiles become buttons that set the matching filter; Unread/Flagged stay as attribute filter chips (they're toggles, not a partition — fine) with counts from stats; one "show archived" rule decided once. Board/Calendar/Notes remain tabs (pass the action/layout test) but consume the shared index | **M** |
| **Monitoring** (`Monitoring.tsx`) | Cleared section = second simultaneously-mounted copy of the same rows, unpaginated (573-599 vs 489-508); hand-rolled pager (524-570); two overlapping time scopes (231-232 window vs 254-263 client date filter) | `Active n | Cleared n` facet (SegmentedControl) over one list + one shared `Pager`; `cleared` stays a localStorage Set, row-level Restore unchanged (`MonitoringSignatureRow` already takes `cleared`/`onToggleClear`). Merge time controls: window presets *inside* `DateRangePicker`, or drop the client date filter until the endpoint takes dates | **S** (cleared+pager) / **M** (time scope) |
| **RunDetail** (`RunDetail.tsx`) | Counts rendered 3× (chips 247-254, `DecisionVerdictBar` 228, banner 230-245); overlapping facets `all`+`attention`+verdicts (194-204); Report re-derives sort/bar/banner (`RunReport.tsx:25,67-70,140-155`); N+1 `qcReadout` for all cards (87-92) | One `FacetBar` (verdict axis, `attention` count as its header CTA replacing the banner) replaces chips + bar; "Needs attention" becomes a `GroupHeader` divider in the attention-first sort. One shared sorted/filtered model + shared page state consumed by both Cards and Report (Report stays a view tab — different reading mode); `ORDER`/`governingGate` exported once from `verdict.ts`. `qcReadout` fetched per *visible* card | **M** |
| **Runs overview** (`RunOverview.tsx`) | `All/Needs review/Sequencing/Released` tabs (344-349) with dual-sourced counts (275-279); list fetched 3× app-wide (`Layout.tsx:13-16`, 229-239, `RunSelector.tsx:53-62`); 3 hand-rolled search predicates | Facets pass the disjointness test and browsing-all is this page's job: keep the tab set, but counts **exclusively** header-borne (delete the client-tally fallback at 278) and `All`'s count = header total. Source from `RunsContext`; make facets server queries (`status`/`q`/`page` already exist, `api.ts:110-117`) when run count grows | **S** now / **M** server-side |
| **AgentTriage / Provenance** | Full run re-fetch per screen (`AgentTriage.tsx:39`, `Provenance.tsx:39-46`); flagged predicate + governing-gate copy-pasted (AgentTriage 42-48,173 = RunDetail 195,329,500) | `useRun(runId)` cache; `governingGate` helper; triage table deep-links `?filter=attention` instead of minting a second "flagged set" spelling. Provenance's double `groupArtifacts` (Prov 67 / `Artifacts.tsx:35`) → group once in container | **S** |
| **Admin › rosters** (`Admin.tsx:37,308` vs `AccessEditor.tsx:31`) | Two mutable copies of the user roster, already drifting on save (318-323 vs `AccessEditor.tsx:176`) | One roster context (the `AccessContext` pattern); merge Page access into the per-user detail view | **S–M** |
| **NotificationBell / health** | Unmemoized full sort per render on every page (`NotificationBell.tsx:32-35`); 2 health pollers (`useApiHealth.ts:13-26` ×2 mounts) | `recent` + non-done count exported memoized from `InboxContext`; health poll singleton | **XS** |

---

## 5. Migration order + risks

**Order (win/risk ratio, each step independently shippable):**

1. **Zero-risk selectors** — bell `recent` memo, health singleton, export `ORDER`/`governingGate`/`GATE_TAG` from `verdict.ts`, Monitoring pager → shared `Pager` + ellipsis. Pure relocation, no behavior change.
2. **Monitoring cleared-as-facet** — the only place two copies mount simultaneously and the unpaginated one; isolated screen, localStorage semantics preserved verbatim.
3. **`inboxStats` + shared index in InboxContext** — fixes the count-disagreement bug class; no visual redesign.
4. **`useRun(runId)` cache + AgentTriage/Provenance re-source** — biggest network win per line changed.
5. **RunDetail FacetBar + attention divider + lazy qcReadout** — first real IA change; validates `FacetBar` on the simplest case (one run, counts already in `detail.summary.counts`).
6. **`useFacetedList` extraction + Review queue re-source onto `TicketsContext`** — the big one; do it after `FacetBar` and the hook exist.
7. **`RunsContext` + header-only counts**, then **Admin activity** (schedule around backend availability for the feed endpoint).

**Preserve (non-negotiable semantics):**
- **Selection**: `orderedIds` = flat visible render order into `useRangeSelect` (`useRangeSelect.ts:10-12`); resolved tickets stay non-selectable (`ReviewQueue.tsx:306-309`); page-scoped selection stays (`375-378`).
- **RBAC**: actor headers are module-level (`api.ts:59-66`) so store centralization is safe, but role-gated action *availability* stays in screen handlers — the store owns data, never permissions.
- **Optimistic overlay + sync**: ReviewQueue's `ui` patch / `syncAction` promise-chain de-dup (`ReviewQueue.tsx:383-399`) moves into `TicketsContext` intact — this is what finally makes queue-resolve and board-resolve mutate one state instead of drifting (`InboxContext.tsx:365-371` today never touches the queue).
- **Clear-from-view reversibility** (Monitoring M4): localStorage-persisted, per-row Restore, cleared rows searchable — the facet must keep search spanning both sides.
- **Verdict palette / gate semantics**: `FacetBar` consumes `VERDICT_BAR`/`VERDICT_DOT` as-is; no derivation of verdicts changes anywhere.

**Honest limits:**
- Both `Tabs` consumers already render one panel at a time, so DOM savings are real only for Monitoring-cleared and the bell; the primary wins are **fetch elimination, count consistency, and cognitive load**, plus O(1) tallies replacing O(n·k) re-scans.
- Client-side faceting still ships the whole collection; the pattern makes the later flip to server faceting mechanical (headers already carry totals/counts for runs and tickets) but doesn't remove the payload today.
- The ticket's three status vocabularies (open/in_review/resolved vs kanban column vs read/unread) are *different axes on one entity* by design; one store makes them overlay fields on one row, but unifying the vocabulary is a product decision this pattern deliberately does not force.
- Admin's activity feed can't be truly canonical without a backend audit endpoint; the client-side interim only stops the per-tab-switch refetch and the catch-all counts.

### Critical Files for Implementation
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/screens/ReviewQueue.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/context/InboxContext.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/components/Bar.tsx (base for the new `FacetBar`, alongside `ReviewStatusBar.tsx`/`DecisionVerdictBar.tsx` which it replaces)
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/screens/RunDetail.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/api.ts

---

# Appendix — per-cluster audit (grounded catalog)


## Appendix A — Review queue + Inbox

# Duplication Catalog — Review Queue + Inbox cluster

Scope read: `frontend/src/screens/ReviewQueue.tsx`, `frontend/src/screens/Inbox.tsx`, `frontend/src/context/InboxContext.tsx`, `frontend/src/components/NotificationBell.tsx`, plus `frontend/src/inbox.ts`, `frontend/src/components/Tabs.tsx`, `frontend/src/components/ReviewStatusBar.tsx`, `frontend/src/api.ts`, `frontend/src/components/TopBar.tsx`. All paths below are under `/Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/`.

One structural note that frames everything: `Tabs` is a controlled selector and both screens mount only the active tab's content (`Inbox.tsx:1571-1574`; ReviewQueue has one list body). So the tax here is mostly **not** four DOM copies at once — it's (a) the same entity **fetched and stored by two independent subsystems**, (b) catch-all facets whose counts re-scan the full array N× per render, and (c) the same rows re-rendered in an always-mounted global surface (the bell) plus whichever page view is open.

---

## 1. The Ticket — two competing canonical sources, five render surfaces, three client stores (WORST)

- **Entity:** a review ticket (one flagged sample in one run).
- **Where it duplicates:**
  - **Review queue** derives its rows from *run decision cards*, not the ticket store: it fetches **every run detail** (`api.runs().then(runs => Promise.all(runs.map(r => api.run(r.run_id))))`, `ReviewQueue.tsx:231-232` — an N+1 over all runs) and builds `QueueTicket`s from flagged cards (`ReviewQueue.tsx:261-297`, push at 282). Server tickets are fetched *separately and in full* only to hydrate status (`api.listTickets()`, `ReviewQueue.tsx:236`, applied at 248-250).
  - **InboxContext** independently fetches the *same tickets* through a second pipeline: `api.listTickets({status:'open'})` + `api.listTickets({status:'in_review'})` (`InboxContext.tsx:201-207`), merges them with a localStorage overlay into `InboxItem`s (`InboxContext.tsx:223-278`).
  - Those InboxItems then render in **four page views** — stream `InboxRow` (`Inbox.tsx:410`), Board `BoardCard` (`Inbox.tsx:917-925`), Calendar day-cells + agenda (`Inbox.tsx:977-987, 1100-1113`), Notes (any annotated ticket, `Inbox.tsx:1180`) — **plus the always-mounted bell dropdown** (`NotificationBell.tsx:74-107`, mounted globally at `TopBar.tsx:157`).
- **Redundancy:** a re-fetch (two subsystems hit `/api/review/tickets` on the same session), a re-derivation (queue rebuilds "tickets" from full run payloads even though the ticket store exists), and **three divergent client states** for one entity: `ReviewQueue`'s `ui` overlay (`ReviewQueue.tsx:199`), `InboxContext.tickets` (`InboxContext.tsx:149`), and the per-operator localStorage overlay (`InboxContext.tsx:151`). Resolving in the queue (`ReviewQueue.tsx:416`) does not touch the Inbox copy until its manual `refresh` (`Inbox.tsx:1525`); resolving from the board (`InboxContext.tsx:365-371`) refreshes only Inbox's copy, never the queue's `ui`. Same datum, drift by design.
- **Scale cost:** page-load cost of the queue is O(runs) HTTP requests + O(all cards) parse *before a single ticket renders*; the ticket list is transferred twice (once unfiltered at 236, once as open+in_review at InboxContext 201-204) on every app load because the provider wraps the router (`App.tsx:61-63`). Cognitive cost: the same escalation exists as a queue card, a stream row, a board card, a calendar dot, and a bell row, each with different status vocabulary (open/in_review/resolved vs inbox/todo/doing/done vs read/unread).
- **Quick fix idea:** one `TicketStore` context fetched once (tickets as canonical rows; run-card detail lazy-loaded per ticket), with ReviewQueue, InboxContext, and the bell all consuming *selectors* over it — kanban column/read/flag stay as overlay fields on the same store, never a second fetch.

## 2. Review queue status tabs — "All" ⊇ Open/In review/Resolved, with 7 full-array scans per render

- **Entity:** the derived `QueueTicket` list.
- **Where it duplicates:** `STATUS_FILTERS` declares `all` alongside the three statuses (`ReviewQueue.tsx:71-76`), rendered as `Tabs` with per-facet counts (`ReviewQueue.tsx:613-619`). The catch-all coexists with the subsets: every ticket is countable in "All" *and* exactly one status tab, and the "All" tab renders the union of rows the other tabs render.
- **Redundancy:** count derivation — `view.counts` runs **three full `tickets.filter` passes plus length** (`ReviewQueue.tsx:311-316`) inside a memo whose deps include `ui`, `page`, and `search` (`ReviewQueue.tsx:359`), so *every checkbox tick, keystroke, or page flip* re-scans the whole array 4×; then `shown` filters again (332-335). `ReviewStatusBar` segments add **three more** full passes over the same array per render (`ReviewQueue.tsx:568-572`), and `expandAll` maps it all again (574). "All" is also a rendered duplicate: switch tabs and the identical rows re-mount under a different facet.
- **Scale cost:** at 10k tickets that's ~70k predicate evaluations per keystroke (search resets page → memo recompute), all to label tabs whose numbers are derivable from one `groupBy(status)` pass. Cognitive: "All" makes the default read "everything, including resolved history," which the code itself fights with the resolved-window machinery (below).
- **Quick fix idea:** drop "All"; default to Open, compute all counts in a single reduce keyed by status, and let `ReviewStatusBar` consume the same tally instead of re-filtering.

## 3. Resolved tickets fetched twice and windowed client-side over an already-full list

- **Entity:** resolved tickets.
- **Where it duplicates:** the load effect issues **both** the unfiltered `api.listTickets()` (which includes every resolved ticket, `ReviewQueue.tsx:236`) **and** `api.listTicketsPage({status:'resolved', since:…})` (`ReviewQueue.tsx:240-243`). The window page's rows are used only to build a key-set (`recentResolvedKeys`, `ReviewQueue.tsx:252`) that then *filters the client-side list that already contains all of them* (`ReviewQueue.tsx:329-335`).
- **Redundancy:** a duplicate fetch of the same rows (resolved tickets ride both responses), plus a "windowed subset vs full history" pair of views over one list — `showAllResolved` (`ReviewQueue.tsx:211, 685-693`) toggles between two renderings of the same data, and the true total is displayed from a third source (`resolvedTotal` header vs `view.counts.resolved`, `ReviewQueue.tsx:681-683`).
- **Scale cost:** the window exists to keep a long resolved history from flooding the view — but the full history is *already downloaded and hydrated into `ui`* by line 236, so the payload/memory cost is paid regardless; only the rendering is windowed. As resolved history grows this becomes the dominant transfer on every queue load.
- **Quick fix idea:** make the resolved window server-side only — fetch open+in_review fully, resolved via the paged endpoint on tab entry, and delete `recentResolvedKeys`.

## 4. Inbox stream facets + KPI tiles — the same counts derived three separate ways

- **Entity:** `InboxItem`s (non-done).
- **Where it duplicates:** filter chips `All / Unread / Flagged` (`Inbox.tsx:215, 363-367`) — "All" is again the catch-all over the subsets and renders the union rows. But the counts are computed **independently three times**: the `shown` memo builds `base` (`Inbox.tsx:344-350`); `unread` re-filters outside it (351); `FILTERS` re-runs `items.filter(i => i.column !== 'done')` *again* for the "All" n (364) and `flagged` (366); the mark-all-unread guard scans again (396). Then the page header's KPI tiles re-derive `flagged`, `overdue`, `done` with three more full passes (`Inbox.tsx:1508-1510, 1533-1545`) — `flagged` is now counted in two places with **different predicates** (tiles count flagged including done items; the chip excludes done), so the two numbers can silently disagree.
- **Redundancy:** re-derivation (≥7 full-array scans per render of the page) and a duplicated *displayed* datum (Flagged count appears in the KPI tile and the chip; Unread appears in tile, chip, tab badge at 1557, and bell badge).
- **Scale cost:** with hundreds of tickets + notes the scans are cheap-ish, but the disagreement risk grows with data: one flagged done-column item makes tile ≠ chip forever. Cognitive: four numbers for "unread" trains users to distrust counts.
- **Quick fix idea:** compute one `inboxStats` memo in `InboxContext` (unread/flagged/overdue/done, done-exclusion decided once) and have tiles, chips, tab badge, and bell all read it.

## 5. Board / Calendar / Notes — three organizational views re-partitioning the same items with per-view visibility rules

- **Entity:** the same `items` array from `useInbox()`.
- **Where it duplicates:** Board partitions it per column with `byColumn` — a filter+sort executed **once per column per render** (4 passes, `Inbox.tsx:853-856`); Calendar re-partitions the same array by due date (`scheduled` at 977, `byDay` at 978-987) and renders each dated item **twice within the tab** (day-cell dot+count at 1082-1087, agenda card at 1100-1113); Notes filters it a third way (`isSelf || note.trim()`, `Inbox.tsx:1180`) and re-counts per folder in `folderNav` (one pass per folder, 1223-1227). The stream additionally back-references board state as a chip on each row (`item.column !== 'inbox'`, `Inbox.tsx:237-241`).
- **Redundancy:** rendered copies across tabs (one ticket with a due date and a note appears in the stream, a board column, a calendar cell, the agenda, *and* Notes) and re-derivation (each tab rebuilds its partition from the flat array on every render; none share a grouped index).
- **Scale cost:** the per-view caps diverge — stream pages at 25 (`Inbox.tsx:342`), board reveals 20/column (`COLUMN_PAGE`, 429), calendar renders **all** dated items' dots with no cap, folder counts scan all notes per folder. As items grow, the calendar month grid is the unbounded one. Cognitively: "where is this item?" has four answers, and only the stream hides `done` (347) while board/calendar still show it — the cleared-section rule is inconsistent across views of the same list.
- **Quick fix idea:** one memoized index in context (`{byColumn, byDueDay, notes, stats}` computed in a single pass) consumed by all tabs, with a single shared "archived items visible?" rule.

## 6. NotificationBell — an always-mounted, unmemoized copy of the Inbox stream

- **Entity:** the most recent non-done `InboxItem`s.
- **Where it duplicates:** the bell (mounted globally, `TopBar.tsx:157`) rebuilds `recent` with a full copy + filter + sort **on every render, no `useMemo`** (`NotificationBell.tsx:32-35`), and its footer re-filters the whole array again just for the "N items →" count (`NotificationBell.tsx:117`). These are the same rows `InboxTab` renders (`Inbox.tsx:344-350`) and the same non-done predicate, hand-copied.
- **Redundancy:** rendered rows (the 6-row dropdown is a subset view of the stream) plus a re-derivation on a component that re-renders whenever *any* context change happens anywhere in the app — because `InboxContext` wraps the router (`App.tsx:61-63`), every `markRead`/keystroke-adjacent overlay patch re-sorts the full list in the top bar even when the dropdown is closed.
- **Scale cost:** O(n log n) sort in the top bar on every inbox mutation, on every page. At large n this taxes *every* screen, not just /inbox. Cognitive cost is low (this is a legitimate summary view) — the problem is purely that it's a parallel computation instead of a selector.
- **Quick fix idea:** expose `recent` (and the non-done count) as memoized values from `InboxContext`, computed once alongside `unreadCount` (`InboxContext.tsx:281`).

## 7. Verdict-severity summary vs status tabs — two parallel "state of the queue" summaries

- **Entity:** the queue's aggregate composition.
- **Where it duplicates:** `ReviewStatusBar` shows a verdict-mix bar over the *whole* queue "independent of the status filter" (`ReviewStatusBar.tsx:8-11`, fed at `ReviewQueue.tsx:568-572, 610`), directly above the status tabs' counts over the same tickets (`ReviewQueue.tsx:613-619`), above the run-group headers that count the same tickets a third time per group (`ReviewQueue.tsx:773-775`).
- **Redundancy:** re-derivation (three filter passes at 569-571) and a second rendered aggregate of one list along a second axis (verdict vs status), with no interaction between them — clicking a bar segment does nothing; the tabs don't reflect verdict.
- **Scale cost:** minor compute, real cognitive load: two adjacent summaries invite "which number is the backlog?" and neither filters the other.
- **Quick fix idea:** make the severity bar's segments clickable verdict *facets* over the same canonical list (one grouped tally powering bar, tabs, and group headers).

---

### Cross-cutting principle violation

The cluster has **two catch-alls** (queue "All" tab, inbox "All" chip) sitting over filtered subsets, **two fetch pipelines** for one entity (`ReviewQueue.tsx:231-243` vs `InboxContext.tsx:201-204`), and **zero shared derived indexes** — every facet/count/tab re-filters a flat array locally. The one-canonical-source shape would be: a single ticket store + a single `InboxItem` merge, one grouped-stats pass, and every tab/chip/tile/bell rendered as a selector over that pass.

### Critical Files for Implementation

- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/context/InboxContext.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/screens/ReviewQueue.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/screens/Inbox.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/components/NotificationBell.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/api.ts


## Appendix B — Runs + Monitoring + Agent triage

# Duplication Catalog — Runs · Monitoring · Agent Triage cluster

All paths relative to `/Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src`. Ranked worst-first.

---

## 1. Monitoring signatures: main list + "Cleared" section render the same rows in parallel (cleared side unpaginated)

- **Entity**: `MonitoringSignature` rows (`data.signatures` from one `api.monitoringPage` call, `screens/Monitoring.tsx:183`).
- **Where it duplicates**: One fetched array is split into two *simultaneously rendered* sections of the same component: `visibleSigs`/`clearedSigs` at `screens/Monitoring.tsx:213-214`, main list at `Monitoring.tsx:489-508`, cleared section at `Monitoring.tsx:573-599`. The code's own comment admits it: *"Cleared signatures (M4) — reversibly hidden; still fully rendered + searchable + escalatable"* (`Monitoring.tsx:572`). This is the "cleared section" variant of catch-all + subset: `filteredSigs` is the catch-all; the two sections are its partition, both materialized as `<MonitoringSignatureRow>` DOM (identical row component, `components/MonitoringSignatureRow.tsx:26`).
- **Redundancy**: Rendered rows (two live copies of the row component with duplicated `openSigs` toggle wiring — the identical Set-toggle closure appears twice, `Monitoring.tsx:495-501` and `583-590`); plus a third copy of the same entity's identity in `localStorage` (`pipeguard.monitoring.cleared`, `Monitoring.tsx:54,143-167`).
- **Scale cost**: The main list is client-paginated (`Monitoring.tsx:217-223`) but `clearedSigs.map(...)` at `Monitoring.tsx:579` has **no pager** — clear 500 signatures over a 30d window and toggling "Cleared" mounts 500 full rows at once. Cleared state also silently diverges from the server: signatures cleared in one browser reappear in another, and stale hashes accumulate in localStorage forever.
- **Quick fix**: Make "Cleared" a facet value on the *one* signatures list (`view: active | cleared`), reusing the same pager, instead of a second rendered section.

## 2. AgentTriage flagged-samples table: a second fetch + second rendering of RunDetail's "attention" view

- **Entity**: The flagged `DecisionCard`s of one run (verdict ≠ proceed).
- **Where it duplicates**: `AgentTriage` independently re-fetches the whole run (`api.run(runId)`, `screens/AgentTriage.tsx:39`) and re-derives flagged cards (`AgentTriage.tsx:42-48`: `cards.filter((c) => c.verdict !== 'proceed')`) — the exact predicate RunDetail's `attention` facet already applies (`screens/RunDetail.tsx:195`: `filter === 'attention' ? c.verdict !== 'proceed'`). The triage table rows (`AgentTriage.tsx:168-210`) echo per-card data (sample_id, verdict, gate, headline, findings count) that the RunDetail card headers already render (`RunDetail.tsx:334-352`), and the selected row is rendered *again* on the same screen inside `AgentSubjectCard` (`AgentTriage.tsx:230`).
- **Redundancy**: A full re-fetch of `RunDetail` (the payload includes every card's findings, gate_results, events) per navigation between two sibling routes; a re-derivation — the "governing gate" expression `card.gate_results.find((g) => g.verdict === card.verdict)?.gate ?? card.findings[0]?.gate ?? null` is copy-pasted **three times**: `AgentTriage.tsx:173`, `RunDetail.tsx:329` (`originInfo`), `RunDetail.tsx:500` (`fbGate`); and rendered rows (row + subject card show the same datum twice).
- **Scale cost**: A 100+-sample flowcell means a multi-hundred-KB `RunDetail` payload fetched twice for what is one user journey (cards → triage). The triple-derivation means a fix to gate attribution must land in three places or the same sample shows different gates on different screens. Cognitive: the operator sees "flagged samples" as a table here, as filtered cards on RunDetail, and as `n_attention` chips on RunOverview — three presentations, no shared source.
- **Quick fix**: One `useRun(runId)` cache/context (fetch once, share across `/runs/:id`, `/runs/:id/agent`, `/runs/:id/provenance` — Provenance also refetches, `screens/Provenance.tsx:39,46`), and one exported `governingGate(card)` helper.

## 3. RunOverview status facets: catch-all "All" tab + status subsets over one runs list, with counts derived two ways

- **Entity**: `RunSummary` rows (one `api.runsPage()` fetch, `screens/RunOverview.tsx:229-239`).
- **Where it duplicates**: The exact pattern named in the brief — `FACETS` at `RunOverview.tsx:32-37` is `All / Needs review / Sequencing / Released`, rendered as `Tabs` with counts (`RunOverview.tsx:344-349`) over one client-side filter (`RunOverview.tsx:248-249`). "All" is by construction the union of the other three, so every run is reachable in ≥2 tabs. Counts are additionally *dual-sourced*: header-borne `statusCounts` with a client-tally fallback (`RunOverview.tsx:275-279`) — two derivations of the same numbers.
- **Redundancy**: Not parallel DOM (tabs swap one list — this screen is already closest to the target principle), but duplicated *membership* (every run in 2 facets), duplicated count derivation (server header vs. `runs.filter(...).length`), and a duplicated per-run verdict summary: each `RunCard` renders `VerdictBar` + `VerdictLegend` (`RunOverview.tsx:114-117`) restating the same `run.counts` the run's own detail page restates again (see #4).
- **Scale cost**: The whole "scale kit" is client-side over one unpaginated fetch (`RunOverview.tsx:229-233` comment: "a single in-memory pass … (28 runs)") — at 5,000 runs the catch-all fetch ships everything so the facet counts stay consistent; the facets stop being a payload optimization and become pure re-filtering of a giant in-memory copy. The "All" count (`runs.length`) also drifts from header `total` if the server ever paginates.
- **Quick fix**: Drop the client tally fallback and make facets server queries over one paged endpoint (the API already supports `status`, `q`, `sort`, `page` — `api.ts:110-117`), keeping counts exclusively header-borne.

## 4. RunDetail verdict counts rendered three times on one screen (chips + verdict bar + attention banner), with "All"/"attention" catch-alls

- **Entity**: One run's verdict counts (`detail.summary.counts`, `detail.summary.n_attention`).
- **Where it duplicates**: On a single render of `screens/RunDetail.tsx`: (a) the facet chips `All / Needs attention / Escalate / Rerun / Hold / Proceed` with counts (`RunDetail.tsx:197-204`, rendered via `Tabs` at `247-254`); (b) `DecisionVerdictBar` — the same counts as a proportional bar *plus a legend spelling out every verdict count again* (`RunDetail.tsx:228`; `components/DecisionVerdictBar.tsx:19-33`); (c) the attention banner repeating `n_attention` a third time (`RunDetail.tsx:230-236`). The facet set itself has *two* overlapping catch-alls: a non-proceed card is a member of `all`, `attention`, **and** its own verdict facet (`RunDetail.tsx:194-196`) — three tabs per card.
- **Redundancy**: Re-rendered derivations of one counts object, three visual grammars for the same four numbers; `n_attention` appears in the chip row and the banner within ~30px of each other.
- **Scale cost**: Mostly cognitive/scan load — the operator reconciles three count displays before reading a single card; any future counts bug shows differently in each. The facet membership duplication also means URL deep-links (`?filter=`) have two spellings for "the flagged set" (`attention` here vs. the flagged table on AgentTriage).
- **Quick fix**: Make `DecisionVerdictBar`'s legend *be* the facet control (clickable segments/legend = filter), deleting the separate chips row and folding the banner count into the `attention` facet.

## 5. RunDetail "Decision cards" vs "Report": two view tabs re-deriving the same cards, plus an N+1 readout fan-out

- **Entity**: `detail.cards` (and `detail.summary.counts`) of one run.
- **Where it duplicates**: Top-level view tabs at `screens/RunDetail.tsx:160-173` switch between the cards view and `RunReport` (`RunDetail.tsx:181-188`). `RunReport` re-sorts the same cards with a duplicated `ORDER` map (`components/RunReport.tsx:67-70` vs `RunDetail.tsx:40,191-193`), re-renders the same `DecisionVerdictBar` (`RunReport.tsx:140`) and the same attention banner (`RunReport.tsx:142-146`), and re-walks `detail.cards` for findings (`RunReport.tsx:75-86`). Separately, the cards view fires one `api.qcReadout` per card (`RunDetail.tsx:87-92`) — an N+1 fan-out for data that echoes what each card's `gate_results` already summarize.
- **Redundancy**: Re-derivation (sort, counts bar, banner duplicated across sibling views of one entity) and a per-card re-fetch (N+1) whose results are thrown away on every run/filter change (`setReadouts({})` at `RunDetail.tsx:73`).
- **Scale cost**: 100+ samples → 100+ parallel `qcReadout` requests on every mount *even for cards on pages the user never opens* (the fan-out loops `d.cards`, not `pageCards`). Switching Cards ↔ Report re-executes the sorts/derivations; a divergence in the two `ORDER` copies would silently order the two views differently.
- **Quick fix**: Lift sort/derivations into one shared selector over `detail`, and lazy-fetch `qcReadout` per *visible* card (on expand or on page), not per run.

## 6. The runs list is fetched into three-plus independent client stores

- **Entity**: `RunSummary[]` (the `/api/runs` collection).
- **Where it duplicates**: (a) `components/Layout.tsx:13-16` fetches `api.runs()` at the app shell to feed `Sidebar` (flagged count, `components/Sidebar.tsx:50`) and the `TopBar` run switcher (`components/TopBar.tsx:39,65-68`); (b) `RunOverview` fetches it again via `api.runsPage()` (`screens/RunOverview.tsx:232-239`); (c) `RunSelector` lazily self-fetches `api.runs({status})` when no list is injected (`components/RunSelector.tsx:53-62`); (d) outside this cluster but same entity: `screens/ReviewQueue.tsx:232` does `api.runs().then((runs) => Promise.all(runs.map((r) => api.run(r.run_id))))` — the full N+1 the Monitoring screen already retired (comment at `screens/Monitoring.tsx:177`).
- **Redundancy**: Three independent `useState` copies of the same collection, three fetches per session (plus the ReviewQueue N+1), and duplicated search/filter logic — TopBar's id/platform match (`TopBar.tsx:65-68`), RunSelector's (`RunSelector.tsx:67-74`), and RunOverview's (`RunOverview.tsx:248-250`) are three hand-rolled copies of the same predicate.
- **Scale cost**: Payload × 3 on load; state can disagree (Sidebar's `n_attention` badge vs RunOverview's facet counts refresh on different lifecycles, so the badge can show stale counts while the list shows fresh ones); every new consumer adds another fetch+store rather than another view.
- **Quick fix**: One `RunsContext`/query-cache owning `RunSummary[]` + `statusCounts`; TopBar, Sidebar, RunSelector, RunOverview all become views over it.

## 7. Recurring signatures re-fetched (whole monitoring payload) by the PipelineRepairModal; repair endpoint has two clients

- **Entity**: `MonitoringSignature[]` and the signature-repair proposal.
- **Where it duplicates**: `PipelineRepairModal` — launched from AgentTriage (`screens/AgentTriage.tsx:123-128,238`) — fetches `api.monitoring('all', 25)` (`components/BuilderModals.tsx:328-341`), pulling KPIs + runs + gates it discards, just to populate a signature `<select>` (`BuilderModals.tsx:406-418`) with the same signatures the Monitoring screen already holds in state (`screens/Monitoring.tsx:183`). The repair call itself has two client implementations: the typed `api.signatureRepair` (`api.ts:283-284`, used by `BuilderModals.tsx:352-353`) and a raw `fetch('/api/monitoring/signatures/…/repair?window=…')` hand-rolled inside `components/MonitoringSignatureRow.tsx:68-70` because "the typed api.signatureRepair() client is frozen at signature-only arity" (`MonitoringSignatureRow.tsx:66`).
- **Redundancy**: A full re-fetch of the heaviest read endpoint for a dropdown; a duplicated HTTP client for one endpoint (with different error surfacing — `httpError` parsing vs bare `res.status`); and a third rendering of signature identity (modal `<option>` rows vs `MonitoringSignatureRow` vs its Cleared copy in #1).
- **Scale cost**: `window='all'` grows unboundedly with history — the modal's cost scales with total signatures ever, not with what it shows (25). The two repair clients drift: the row threads `?window=`, the modal cannot, so "the same proposal" is computed over different spans depending on where you clicked.
- **Quick fix**: Add `window` to `api.signatureRepair`, delete the raw fetch, and pass signatures into the modal (or expose a signatures-only endpoint) instead of re-fetching the whole monitoring aggregate.

## 8. Monitoring's two overlapping time filters split one payload into two different scopes on one screen

- **Entity**: The windowed monitoring payload (`data.runs`, `data.overall`, `data.gates`, `data.signatures` — all from the single call at `screens/Monitoring.tsx:183`).
- **Where it duplicates**: Two independent time controls sit side-by-side in one header (`Monitoring.tsx:229-243`): the window segmented control (`7d/14d/30d`, `Monitoring.tsx:19-23`) scopes everything server-side, while the `DateRangePicker` (`Monitoring.tsx:128-129`) re-filters *only* `data.runs` client-side (`Monitoring.tsx:254-263`). The UI must then carry an apology label: "Date range refines this chart only · KPIs & gate-pass stay 7d-scoped" (`Monitoring.tsx:321-323`).
- **Redundancy**: A re-derivation (a second, client-side time filter over already-window-filtered rows) producing *two coexisting scopes of the same entity on one screen* — the chart's rows and the KPI tiles/gate meters/signatures no longer describe the same set.
- **Scale cost**: Cognitive first (numbers on the same screen silently disagree once a date range is set), and it interacts badly with the server-side throughput pager (`Monitoring.tsx:404-415`): the date filter applies only to the *current page* of `runs[]`, so at high run counts the chart shows "runs in range ∩ current page" — an unlabelled third scope.
- **Quick fix**: One time scope — either make the window control a preset of the date-range picker and send dates server-side, or drop the client date filter until the endpoint accepts date params.

## 9. `/api/health` polled by two independent 20s intervals on the Runs page

- **Entity**: API health status.
- **Where it duplicates**: `useApiHealth` creates a *per-instance* `setInterval` + fetch (`hooks/useApiHealth.ts:13-26`); it is mounted by both the TopBar pill and `RunsHeader`'s "Gate online" indicator (`screens/RunOverview.tsx:146`, comment at `RunOverview.tsx:123-125` says they "read the same real health poll" — they read the same *endpoint*, but run two separate pollers).
- **Redundancy**: A duplicate re-fetch (2× `/api/health` every 20s while on Runs) and two state copies that can transiently disagree (one poller flips to `offline` up to 20s before the other).
- **Scale cost**: Small per page, but the pattern invites a poller per indicator; N health dots = N intervals.
- **Quick fix**: Hoist the poll into a context/module singleton; `useApiHealth` subscribes instead of polling.

## 10. Hand-rolled signatures pager duplicates the shared `Pager`

- **Entity**: Pagination UI/state over the signatures list.
- **Where it duplicates**: `screens/Monitoring.tsx:524-570` hand-builds a per-page control + numbered page buttons, while the same file already uses the canonical shared `Pager` for throughput (`Monitoring.tsx:407-415`) and RunOverview uses it for runs (`screens/RunOverview.tsx:362`) — the codebase even tags it "canonical shared <Pager> (UIUX-03)".
- **Redundancy**: Re-implemented component + duplicated clamp/reset logic (`Monitoring.tsx:217-227` mirrors `RunOverview.tsx:268-272`); the hand-rolled version renders *every* page number as a button (`Monitoring.tsx:544-557`).
- **Scale cost**: 2,000 signatures at 25/page = 80 page buttons rendered in the footer; behavior drift from the shared Pager (ellipsis handling, a11y) accrues silently.
- **Quick fix**: Replace `Monitoring.tsx:524-570` with the shared `<Pager noun="signatures">`.

---

## Cross-cutting observation

This cluster's screens are already *mostly* single-fetch-plus-client-views internally (RunOverview and RunDetail switch one list under tabs rather than mounting parallel lists). The duplication tax concentrates in three shapes: (1) **the Cleared partition on Monitoring** — the only place two copies of the same rows are mounted simultaneously, and the unpaginated one at that; (2) **cross-screen re-fetch of the same entity** (run detail: RunDetail/AgentTriage/Provenance; runs list: Layout/RunOverview/RunSelector/ReviewQueue; signatures: Monitoring/RepairModal) with no shared store; (3) **re-stated aggregates** — verdict counts rendered 2–3 ways per screen with the derivation logic copy-pasted (governing gate ×3, sort ORDER ×2, id/platform search ×3). Moving to one query-cache per domain entity (runs, run detail, monitoring) plus exported derivation helpers would collapse nearly all ten instances without visual redesign; only #1, #4 and #8 need an IA decision.

### Critical Files for Implementation
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/screens/Monitoring.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/screens/RunDetail.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/screens/AgentTriage.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/api.ts
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/components/Layout.tsx


## Appendix C — RunDetail + Provenance + Admin

# Duplication Catalog — RunDetail + Provenance + Admin cluster

Scope read: `screens/RunDetail.tsx`, `screens/Provenance.tsx`, `screens/Admin.tsx`, plus the shared renderers they delegate to (`components/RunReport.tsx`, `components/provenance/{Lineage,EventTrail,Artifacts}.tsx`, `components/AccessEditor.tsx`). Ranked worst-first.

---

## 1. Admin › Activity log — a catch-all "All" facet over a feed that is itself a re-projection of three other domains' canonical lists

- **Entity**: audit/governance rows — but the underlying canonical data is **tickets** (Review queue's entity), **threshold overrides** (Settings' entity), and **pipeline versions** (Builder's entity), plus two localStorage stores (page-access audit, act-as audit).
- **Where it duplicates**:
  - Tab row `All / Thresholds / Pipelines / Tickets / Access / Act-as` — `frontend/src/screens/Admin.tsx:574-585`. `All` (count = `rows.length`) is exactly the union of the five kind facets; every row appears in "All" **and** its kind tab. Classic catch-all + filtered subsets.
  - The feed is built by **full-fetching three whole collections** — `api.listThresholds() / api.listPipelines() / api.listTickets()` with no query params at `Admin.tsx:468-472` — and flattening them into `FeedRow`s (`Admin.tsx:474-511`). Each ticket explodes into `1 + actions.length` rows (`Admin.tsx:493-509`).
  - Those same tickets are independently fetched and rendered by the Review queue (`frontend/src/screens/ReviewQueue.tsx:236` calls `api.listTickets()` too) and by the Inbox stream (`context/InboxContext.tsx:202-203`), so one ticket action renders in ≥3 surfaces app-wide.
  - The tab is conditionally mounted (`Admin.tsx:808`: `{tab === 'activity' && <ActivityTab />}`), so **every tab switch remounts and re-runs all three fetches** (`useEffect` with `[]`, `Admin.tsx:467-515`), and the act-as log is read only in a `useState` initializer (`Admin.tsx:459`) — refresh depends on that remount.
- **Redundancy**: a full re-fetch of three unbounded collections per visit; a client-side re-derivation (flatten + sort at `Admin.tsx:511`, counts scan at `Admin.tsx:548-552`); and a catch-all facet re-listing every kind's rows.
- **Scale cost**: `listTickets()` here is unwindowed (ReviewQueue at least windows resolved tickets via `listTicketsPage({since})`, `ReviewQueue.tsx:241`); every governance action anywhere in the app adds a row here forever; feed length = thresholds + pipelines + tickets×(1+actions) + audits, all sorted and counted client-side on each remount. Pagination hides DOM weight, not the fetch/derive weight — and the counts scan touches every row regardless of page.
- **Quick fix idea**: one paginated backend audit-feed endpoint (`?kind=&page=`) so the kind tabs become query filters over a single canonical stream instead of a client-side union of three re-fetched domains; drop "All" counts to server-provided facet counts.

## 2. RunDetail — "Decision cards" vs "Report" view-tabs are two parallel renderers of the same `detail.cards`

- **Entity**: the run's `DecisionCard[]` (one card per sample) plus the run's summary/verdict counts.
- **Where it duplicates**: view switch at `frontend/src/screens/RunDetail.tsx:160-172` (`cards` | `report`, URL-owned at `RunDetail.tsx:115`). Both branches render the same cards with independent implementations:
  - Sort: `RunDetail.tsx:191-193` vs `RunReport.tsx:67-70` — same comparator, with the `ORDER` constant literally duplicated (`RunDetail.tsx:40` and `components/RunReport.tsx:25`).
  - Per-card block: `CardHead`/`CardBody` (`RunDetail.tsx:334-352, 450-616`) vs `SampleReport` (`RunReport.tsx:389-428`) — both render VerdictBadge + sample id + headline + `GateResultStrip` + `CitedEvidence` + next-steps for the same card.
  - Run-level chrome duplicated verbatim: `DecisionVerdictBar` at `RunDetail.tsx:228` and `RunReport.tsx:140`; the `n_attention` "Open review queue" banner at `RunDetail.tsx:230-245` and `RunReport.tsx:142-155` (near-identical JSX).
  - Independent pagination state on the same rows (`RunDetail.tsx:67-68` vs `RunReport.tsx:38-46`), so flipping views loses your position and shows a differently-paged copy of the same list.
- **Redundancy**: re-rendered rows (full card list rebuilt per view), re-derived sort, duplicated banner/summary components — plus an **N+1 fetch that ignores the view entirely**: `RunDetail.tsx:87-92` fires `api.qcReadout(runId, sample)` for **every** card on load, even when the user is on the Report view or on page 1 of 25.
- **Scale cost**: the comment at `RunDetail.tsx:65` says 100+ cards per flowcell — that's 100+ readout requests up front, and every readout arrival triggers a re-render that re-runs the unmemoized sort+filter (`RunDetail.tsx:191-196` executes inside `renderBody()` on every state change). The Report additionally lacks the verdict filter, so behavior diverges between the two copies.
- **Quick fix idea**: one canonical sorted/filtered card model (memoized, shared page state) with the Report as a print-styled *layout* of the same row component; fetch `qcReadout` only for the currently-paged cards.

## 3. Run detail payload re-fetched wholesale by every run-scoped screen

- **Entity**: the `RunDetail` payload (summary + all cards + the full append-only event ledger).
- **Where it duplicates**: `RunDetail.tsx:77-78` (`api.run(runId)`), `Provenance.tsx:46` (same call again on navigation), `AgentTriage.tsx:39` (again). Provenance's `refetchDetail` (`Provenance.tsx:38-40`) re-downloads the entire payload just to pick up **one** appended `DATA_EXPORTED` event after a share. Out-of-cluster but symptomatic: `ReviewQueue.tsx:232` fetches `api.run()` for *every* run in a `Promise.all`.
- **Redundancy**: pure re-fetch — no cache, no shared context; the same cards+events cross the wire once per screen visit and once per share.
- **Scale cost**: per `components/provenance/EventTrail.tsx:33`, a 100-sample run emits ~500 events (`2 + 2N + F`); with 100 cards + findings the detail payload is the heaviest object in the app, re-downloaded on each Cards↔Provenance↔Agent hop. Lazy tab rendering does nothing for this — it's network + parse cost, repeated.
- **Quick fix idea**: a runId-keyed detail cache (context or query cache) that RunDetail/Provenance/AgentTriage share, with an events-only append refresh after a share.

## 4. Admin › Users & roles vs Page access — two independent copies of the same roster, already drifting

- **Entity**: the user roster (`DEMO_ACCOUNTS`).
- **Where it duplicates**: `SEED_USERS` copied into per-tab mutable state at `Admin.tsx:37-38` + `Admin.tsx:308` (`useState(SEED_USERS)`), and a second module-level copy `ROSTER` at `components/AccessEditor.tsx:31`. Both tabs render a parallel user table (name/id/role + per-user Edit detail view: `UserDetail` at `Admin.tsx:193-302` vs the editor view at `AccessEditor.tsx:213-403`).
- **Redundancy**: rendered rows (two user tables), state duplication (two copies of role data), and duplicated per-user drill-in UX.
- **Scale cost**: correctness, not volume — a role saved in Users & roles mutates only UsersTab's local copy (`Admin.tsx:318-323`); Page access's "Wire role" column (`AccessEditor.tsx:176`) still shows the seeded role, so the two tabs contradict each other in the same session. Tab switching also remounts UsersTab (`Admin.tsx:806`), silently discarding its edited roster. Any real user store multiplies both tables and both detail views.
- **Quick fix idea**: lift the roster into one context (the pattern `AccessContext` already uses) that both tabs read; merge Page access into the per-user detail view so "user" has one canonical list and one drill-in.

## 5. RunDetail verdict chips — "All" + overlapping "Needs attention" facet over one card list

- **Entity**: the same `DecisionCard[]` as #2.
- **Where it duplicates**: chip row at `RunDetail.tsx:197-204` (`All / Needs attention / Escalate / Rerun / Hold / Proceed`), filter applied at `RunDetail.tsx:194-196`. `All` is the union of the four verdicts, and `attention` is the union of escalate+rerun+hold — so a flagged card is reachable under **three** facets, and the chip counts sum to well over the card count.
- **Redundancy**: not parallel DOM (facets render exclusively), but overlapping *derived subsets* + counts of one list, re-filtered and re-sorted un-memoized on every render (see #2's re-sort note); the "attention" union also duplicates information the sort already encodes (attention verdicts are ordered first by `ORDER`, `RunDetail.tsx:40, 191-193`).
- **Scale cost**: cognitive — the operator sees `All 100 · Needs attention 12 · Escalate 4 · Rerun 5 · Hold 3 · Proceed 88` and must mentally reconcile which chips overlap; each chip click re-derives the list from scratch at 100+ cards.
- **Quick fix idea**: keep the four disjoint verdict facets, and turn "Needs attention" into a group header/divider in the already-attention-first sorted list instead of a fifth overlapping subset.

## 6. Provenance › Lineage drill-in vs Artifacts tab — the same artifact rows rendered by two different renderers, grouped twice

- **Entity**: `RunArtifact[]` (one per `(stage, role)` edge; `Artifacts.tsx:20-23`).
- **Where it duplicates**: Lineage's per-stage I/O columns filter and render them (`components/provenance/Lineage.tsx:263-265` + `ProvArtifactRow` at `Lineage.tsx:419-448`); the Artifacts tab renders the same files as a flat grouped index (`components/provenance/Artifacts.tsx:35, 120-167`). Both rows carry the same link/fingerprint/size/download affordances via two unrelated implementations. The grouping itself is computed twice per page load: once in the container just for the tab badge (`Provenance.tsx:67`) and again inside the Artifacts view (`Artifacts.tsx:35`).
- **Redundancy**: re-derivation (double `groupArtifacts`) + two divergent row renderers over one entity (Lineage shows raw per-edge rows keyed by `a.name`; Artifacts collapses edges into chips — same file, different shape per tab).
- **Scale cost**: modest today, but the renderer split means every artifact-affordance change is done twice (they've already diverged: grouped vs ungrouped, chips vs plain rows), and each tab switch remounts and recomputes grouping/filter state from zero.
- **Quick fix idea**: group once in the Provenance container, pass `groups` down (badge = `groups.length`), and share a single `ArtifactRow` component between the drill-in and the index.

## 7. Run-execution provenance pins derived and rendered twice (Provenance header vs Report sign-off)

- **Entity**: the run-execution pins (rule pack, runbook metric count, narration provenance, samples/status, events count, started/completed) derived from the `analysis_run.started/completed` events.
- **Where it duplicates**: `ProvenanceHeader` derives via `events.find(...)` + `readGateProvenance` at `Provenance.tsx:161-176` and renders pins at `Provenance.tsx:183-220`; `RunReport` re-derives identically at `RunReport.tsx:89-94` and renders the same pin set at `RunReport.tsx:275-286` — with two separate locally-defined `Pin` components (`Provenance.tsx:225-232` vs `RunReport.tsx:448-455`) whose labels have already drifted ("Narration provenance" vs "Narration"; Report adds a `?? detail.summary.n_samples` fallback the header lacks, `RunReport.tsx:280`).
- **Redundancy**: re-derivation of the same event scan + a second rendered copy of the same eight facts on a sibling view of the same run.
- **Scale cost**: small per-run, but it's the drift engine — two hand-maintained derivations of "what happened in this execution" shown to the same user two clicks apart; every new pin (e.g., the phase-2 params hash, `Provenance.tsx:214-219`) must be added twice or the surfaces disagree.
- **Quick fix idea**: extract one `deriveRunProvenance(events)` + shared `<ProvenancePins>` used by both the header band and the report's sign-off section.

---

## Appendix — pure code duplication noticed in passing (same-datum renderers, not extra data copies)

- `FilterSelect` defined twice, byte-similar: `EventTrail.tsx:179-206` and `Artifacts.tsx:189-216`.
- `ORDER` verdict-rank constant: `RunDetail.tsx:40` and `RunReport.tsx:25`; `GATE_TAG`: `RunDetail.tsx:43` and `Lineage.tsx:86`.
- The `n_attention` banner JSX: `RunDetail.tsx:230-245` vs `RunReport.tsx:142-155` (counted under #2).

**Cluster-level principle applied**: the run has one canonical payload (`api.run`) — fetch it once and let Cards/Report/Lineage/Event-trail/Artifacts be projections of it; the audit domain has no canonical source at all today — Admin's Activity log fabricates one client-side from three other domains' full collections, which is the single worst instance here.

### Critical Files for Implementation
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/screens/Admin.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/screens/RunDetail.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/components/RunReport.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/screens/Provenance.tsx
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/api.ts
