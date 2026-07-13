## bayleaf Release-Hardening Audit — Specialist 1: UI/UX consistency auditor

**Run mode:** Fable 5, code-only / headless (route + `file:line` + quoted string; no browser this pass, per the resolved evidence mode). Every citation below was re-opened and the quoted string confirmed. Line numbers may shift under concurrent Builder edits (G5) — re-anchor by the quoted string.

**Scope covered:** all 13 routed screens in `App.tsx` + `/login`; nav (`Sidebar.tsx`); token maps (`verdict.ts`); themes (`index.css`, 6 palettes); shared primitives (`Tabs`/`Bar`/`Toast`/`ConfirmDialog`/`Pager`/`RunSelector`/`States`/`PageHeader`/`VerdictBadge`/`SegmentedControl`/`Truncate`); and the Builder modals. G1 (verdict read-only) and G4 (no "confidence" meter) held on every surface I inspected — see "Honest surfaces."

---

### UIUX-01 · "Gate online" health dot on the Runs hero is hardcoded green — never polls, and can contradict the real health pill 6px away
- **Severity:** High · **Confidence:** Confirmed · **Category:** missing-user-facing-state · **Demo-critical:** Y
- **Area / journey:** Operate hero — `/` (Run overview), the first screen of the recording.
- **Evidence:**
  - `frontend/src/screens/RunOverview.tsx:135-138` — `<span className="h-[7px] w-[7px] rounded-full bg-proceed shadow-[0_0_0_3px_var(--color-proceed-bg)]" />` followed by literal text `Gate online`. No hook, no state, no fetch.
  - Its own comment lies about this: `RunOverview.tsx:129` — "only the **live** 'Gate online' status (an operational health indicator, not flavor prose) stays in the actions slot."
  - Contrast the real thing: `frontend/src/components/TopBar.tsx:13-30` `useApiHealth()` polls `api.health()` on mount + every 20 s and maps `offline → { label: 'Offline', dot: 'bg-escalate' }` (`TopBar.tsx:35`).
- **Reproduction:** Stop the API (or break `/runs`). RunOverview body renders `RunsError` — "The artifact store returned `503` reading `/runs`" (`RunOverview.tsx:155-156`) — while the header still shows a green `Gate online`, and the TopBar simultaneously shows red `Offline`. Three-way contradiction on one screen.
- **Expected:** A status labelled as live either reflects real reachability (wire it to `api.health` like TopBar) or is relabelled to something honestly static.
- **Actual:** Always-green dot that reads "online" during an outage; directly conflicts with the adjacent real pill.
- **Root cause:** Static markup left in the page header when the real health poll was centralized into TopBar; the comment was never updated.
- **Minimum viable fix:** Replace the static span in `RunsHeader` with the same `useApiHealth()` pill used by TopBar (or drop the dot and keep a neutral, unlabelled title).
- **Larger fix:** Extract a single `<HealthPill/>` primitive so there is exactly one health indicator vocabulary app-wide.
- **Risk of fixing now:** Very low — isolated, presentational.
- **Regression test:** Render `RunOverview` with `api.health` mocked to `{status:'down'}`; assert the header dot is not `bg-proceed` and no "online" copy renders.

---

### UIUX-02 · Lifecycle status dots reuse the exact verdict/gate hues — amber "Needs review" dot sits beside amber "Hold" verdict on the same card
- **Severity:** Medium · **Confidence:** Confirmed (hue reuse) / Possible (misread) · **Category:** design-inconsistency · **Demo-critical:** N
- **Area / journey:** Runs list, TopBar switcher, `RunSelector` — every surface that renders a run-status dot.
- **Evidence:**
  - `frontend/src/verdict.ts:6-10` — `RUN_STATUS_META`: `needs_review: { dot: 'bg-hold' }`, `running: { dot: 'bg-info' }`, `released: { dot: 'bg-proceed' }`.
  - `verdict.ts:27-32` — `VERDICT_DOT.hold: 'bg-hold'`, `.proceed: 'bg-proceed'` (identical classes).
  - Co-occurrence on one card: `RunOverview.tsx:106` renders `<StatusPill>` (amber `bg-hold` dot for `needs_review`), and `RunOverview.tsx:119-120` renders the verdict `SegmentBar`/`VerdictLegend` whose Hold segment is also `bg-hold` (`verdict.ts:47` `VERDICT_BAR.hold: 'bg-hold'`). The attention badge at `RunOverview.tsx:109` is amber again (`border-hold-bd bg-hold-bg text-hold-fg`).
  - `running` blue (`--color-info #1f6feb`, `index.css:66`) is byte-identical to the preflight gate hue (`--color-preflight #1f6feb`, `index.css:61`).
- **Expected:** A lifecycle dot should be visually separable from a verdict token (distinct shape/hue), so amber can't mean both "run needs review" and "sample verdict Hold" on the same card.
- **Actual:** One amber = run-lifecycle "Needs review" + verdict "Hold" + "need attention" badge, all on the Runs card.
- **Root cause:** Lifecycle status tokens were mapped onto the verdict palette rather than a neutral lifecycle palette.
- **Minimum viable fix:** Give `RUN_STATUS_META` a distinct lifecycle palette (e.g. neutral/outline dots), or always pair the dot with its text label in a bordered chip so hue is never the sole signal (StatusPill already labels; the bare dots in TopBar/RunSelector rows also label — the collision is strongest on the Runs card where verdict amber and status amber stack).
- **Larger fix:** Reserve `proceed/hold/rerun/escalate` hues exclusively for verdicts; introduce lifecycle-specific tokens.
- **Risk of fixing now:** Low — token-map change, but touches every status dot; verify all six themes.
- **Regression test:** Snapshot the `needs_review` RunCard; assert the lifecycle dot class differs from `VERDICT_DOT.hold`.

---

### UIUX-03 · Shared `Pager` primitive is not adopted on four paginated surfaces — the exact idiom it replaced is still hand-rolled
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** design-inconsistency · **Demo-critical:** N
- **Area / journey:** Runs, Agent triage, Monitoring, Review queue.
- **Evidence — hand-rolled inline pagers (Showing X–Y + numbered prev/next):**
  - `frontend/src/screens/RunOverview.tsx:345-388` (`Showing {from}–{to} of {total} runs` + inline buttons).
  - `frontend/src/screens/AgentTriage.tsx:188-224` (`Showing … of {flagged.length} flagged`).
  - `frontend/src/screens/Monitoring.tsx:494-519` (`Showing {sigFrom}–{sigTo} of {sigTotal} signatures`) — byte-for-byte the markup `Pager.tsx` encapsulates.
  - `frontend/src/screens/ReviewQueue.tsx:833-846` (`Showing … of {view.total} tickets`).
- **Evidence — the primitive exists and is adopted elsewhere:** `frontend/src/components/Pager.tsx` (canonical footer), used by Intake, Accession, Inbox, RunDetail, Submit, Artifacts, EventTrail, SettingsModelTier, AccessEditor.
- **Expected:** Every paginated surface uses `<Pager>` (checklist item 6: "Pager.tsx on every paginated surface").
- **Actual:** Four surfaces duplicate the idiom; AgentTriage's copy even omits a per-page control, so pagination controls differ screen-to-screen.
- **Root cause:** `Pager` was extracted after these four screens were built; they were never migrated.
- **Minimum viable fix:** Replace each inline footer with `<Pager total=… page=… perPage=… onPage=… onPerPage=… noun=…/>` (AgentTriage can pass `hidePerPage`).
- **Risk of fixing now:** Low-medium — behavior-preserving; verify page-clamp parity.
- **Regression test:** Assert each of the four screens renders the shared `Pager` (e.g. by test id) rather than local buttons.

---

### UIUX-04 · Inbox's top-level view switcher uses `SegmentedControl` (the "compact settings" control) instead of the canonical `Tabs`
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** design-inconsistency · **Demo-critical:** N
- **Area / journey:** `/inbox` — Inbox / Board / Calendar / Notes primary navigation.
- **Evidence:**
  - `frontend/src/screens/Inbox.tsx:1548` — `<SegmentedControl<Tab>` drives the four full-screen views (`Inbox.tsx:1577-1580` `tab === 'inbox' | 'board' | 'calendar' | 'notes'`).
  - The design rule it violates: `frontend/src/components/Tabs.tsx:5-10` — "FRAMED tabs — the canonical VIEW-SELECTOR across the app … distinct on purpose from SegmentedControl, which stays for compact toggle SETTINGS (7d/14d/30d window, theme, density). Consumers (Runs / Review queue / Admin / RunDetail / Provenance / **Inbox**) inherit automatically." Inbox is named as a Tabs consumer but does not use `<Tabs>` (grep: `<Tabs` appears only in ReviewQueue/RunOverview/RunDetail/Admin/Provenance).
- **Expected:** A four-way, page-level view selector uses `Tabs`; `SegmentedControl` is reserved for compact toggle settings.
- **Actual:** Inbox's main navigation renders as a pill-segmented control, and the `Tabs` doc comment mis-states that Inbox already inherits it (doc drift).
- **Root cause:** Inbox predates/skipped the Tabs migration; the Tabs comment was written aspirationally.
- **Minimum viable fix:** Swap `SegmentedControl<Tab>` for `Tabs<Tab>` (both are generic over the value union with a `count` badge API, so the unread badge maps directly), or correct the Tabs comment to stop claiming Inbox.
- **Risk of fixing now:** Low — same props shape; visual change only.
- **Regression test:** Assert `/inbox` renders `role="tablist"` (Tabs sets it) for its view switcher.

---

### UIUX-05 · Toasts — the app's only surface for real backend outcomes (403/409/422/503) — are not announced to assistive tech
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** missing-user-facing-state · **Demo-critical:** N
- **Area / journey:** Global — every write handler (Submit/Builder-run/Settings/Repair) relies on `useToast`.
- **Evidence:** `frontend/src/components/Toast.tsx:35-47` — the toast container is `pointer-events-none fixed bottom-5 right-5 z-[100] …` with **no** `role="status"`, `role="alert"`, or `aria-live`. The file's own header (`Toast.tsx:4-5`) states its purpose is to "surface their real backend outcome (403/409/422/503) instead of silently diverging." (Grep confirms only `DecisionFeedback.tsx:80` and `FeedbackWidget.tsx:105` use `role="status"`; the global Toast does not.)
- **Expected:** Transient status/error notifications live in an `aria-live` region so screen-reader users hear "Pipeline failed — …" etc.
- **Actual:** A sighted user sees the toast; an AT user gets no announcement of the very outcomes the component exists to surface.
- **Root cause:** ARIA live-region attribute omitted from the toast list container.
- **Minimum viable fix:** Add `role="status" aria-live="polite"` (and `aria-live="assertive"` for `kind === 'error'`) to the container at `Toast.tsx:35`.
- **Risk of fixing now:** Very low — additive attributes.
- **Regression test:** Fire an error toast; assert the container exposes an `aria-live` region containing the message.

---

### UIUX-06 · The single "phase-2" badge conflates a fully-static mock with two read-live modals — understating what actually works
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** design-inconsistency · **Demo-critical:** N
- **Area / journey:** Builder modals (Author tool node / Pipeline-repair / Archivist).
- **Evidence:**
  - Fully-static mock, correctly badged: `frontend/src/components/BuilderModals.tsx:210-211` — `AuthorToolNodeModal` header `roster #5 · phase-2` (its body is a hardcoded `STAR --help` mock).
  - Read-LIVE modals wearing the identical badge: `BuilderModals.tsx:416` — `PipelineRepairModal` `phase-2`, though it fetches real data (`api.monitoring(...)` `BuilderModals.tsx:364`, `api.signatureRepair(...)` `:386`); and `BuilderModals.tsx:558` — `ArchivistModal` `phase-2`, though it fetches `api.archiveIndex()` (`:530`).
- **Expected:** A badge vocabulary should distinguish "static mock (no wiring)" from "read-live, write-inert." One `phase-2` chip for both is ambiguous and, on the two live-read modals, understates reality (they pull real signatures/archive digests).
- **Actual:** Same chip on a static mock and on two modals with a working read path — a viewer can't tell which is which.
- **Root cause:** A single badge string reused across three modals at different integration maturity.
- **Minimum viable fix:** Split the label (e.g. `mock` vs `read-only preview`), or drop the chip from the two read-live modals and keep it only on the static `AuthorToolNodeModal`.
- **Risk of fixing now:** Low — label-only. (Overlaps demo-readiness Spec 8 item 2; coordinate one wording.)
- **Regression test:** Assert `AuthorToolNodeModal` carries a "mock" indicator distinct from the read-live modals' badge.

---

### UIUX-07 · Primary buttons that look actionable but are pure no-ops — "Queue archive" and "Review kinds & add to palette" only close the modal
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** design-inconsistency · **Demo-critical:** N
- **Area / journey:** Builder → Archivist modal; Builder → Author-tool-node modal.
- **Evidence:**
  - `frontend/src/components/BuilderModals.tsx:586-588` — Archivist primary button `Queue archive` has `onClick={onClose}` (does nothing). Yet the footer copy one line up, `BuilderModals.tsx:582`, says "the archive **is queued** for a human to confirm; nothing is moved automatically" — implying a queue action occurred.
  - `frontend/src/components/BuilderModals.tsx:340-341` — Author-tool-node primary button `Review kinds &amp; add to palette` also `onClick={onClose}` — it registers/adds nothing.
  - (For contrast, the sibling `PipelineRepairModal` "Send to review queue" at `BuilderModals.tsx:502-514` at least `navigate('/queue')` and fires an honest toast — the better pattern.)
- **Expected:** A primary CTA either performs its stated action or is visibly disabled/relabelled; footer copy must not claim a side effect ("is queued") that never happens.
- **Actual:** Both CTAs are styled as live primary/secondary buttons; Archivist's copy asserts a queue that doesn't exist.
- **Root cause:** Phase-2 seams with no write endpoint; the button label + footer copy over-promise.
- **Minimum viable fix:** Relabel to a non-committal verb (e.g. "Close preview") or disable with a tooltip; change `BuilderModals.tsx:582` copy to not claim "is queued." (The modal-level `phase-2` badge is present, which partially mitigates, but the button/footer wording still over-states.)
- **Risk of fixing now:** Low — copy/label only. (Write-wiring itself is Spec 3/4's call.)
- **Regression test:** Assert clicking "Queue archive" produces no state change beyond dismissing the modal, and the footer omits "is queued."

---

### UIUX-08 · Shared `ConfirmDialog` (the G7 write gate) lacks dialog semantics and focus management
- **Severity:** Low · **Confidence:** Confirmed · **Category:** post-hackathon-improvement · **Demo-critical:** N
- **Area / journey:** Global — every stakes-y write routes through `useConfirm` (share, roster live-toggle, roster removal, …).
- **Evidence:** `frontend/src/components/ConfirmDialog.tsx:52-60` — the overlay/panel has **no** `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, no focus trap, and the confirm button is never auto-focused (`ConfirmDialog.tsx:84-92`). Esc-cancel and click-outside-cancel are correctly implemented (`ConfirmDialog.tsx:38-45,55`). (Grep: only `FeedbackWidget.tsx:89` uses `role="dialog"`.)
- **Expected:** A modal confirmation exposes `role="dialog" aria-modal` with focus moved into it and trapped, so keyboard/AT users can operate the gate that guards every audited write (G7).
- **Actual:** Keyboard focus stays behind the overlay; AT users aren't told a dialog opened.
- **Root cause:** Minimal dialog implementation focused on visuals + Esc.
- **Minimum viable fix:** Add `role="dialog" aria-modal="true"`, label it from `opts.title`, and focus the confirm button on open.
- **Risk of fixing now:** Low — additive; keep Esc/click-outside behavior.
- **Regression test:** Open a confirm; assert `role="dialog"` present and focus lands inside.

---

### Honest surfaces (verified good — clean signal)
- **G1 verdict read-only holds everywhere I inspected.** `RunDetail` shows verdict only via `VerdictBadge` (`RunDetail.tsx:293`); the AI block is explicitly `AI narration (advisory)` (`RunDetail.tsx:368-370`, `:560-563`). `AgentTriage` renders `VERDICT_DOT/VERDICT_LABEL` read-only (`AgentTriage.tsx:167-168`) and the source toggle only swaps narration (`AgentSourceToggle.tsx:3-4`). No editable verdict control found on any surface.
- **G4 heuristics ≠ confidence holds.** No "confidence" meter renders anywhere; per-citation scores read `N% (heuristic)` (`BuilderModals.tsx:485`); Monitoring's auto-proceed ratio is labelled "Throughput heuristic … Not a calibrated confidence" (`Monitoring.tsx:276`). `DecisionCard.confidence` is `number | null` and never bound to a bar (grep clean).
- **Canonical `Bar` (G3) fully adopted.** `SegmentBar`/`MeterBar` back every distribution/meter (RunOverview, Intake, Monitoring, DecisionVerdictBar, ReviewStatusBar); no stray `h-[11px]`/`rounded-6` bar geometry remains (`BuilderLegend`'s `h-[11px]` is a round legend dot, not a bar). `FacetChip` is fully deleted (grep empty).
- **Theme completeness (checklist 8).** `index.css` defines all 6 palettes (clinical/sand/slate light + midnight/carbon/indigo dark); verdict + gate hues are inherited from `@theme` and **not** overridden by the `data-palette` variants (only surface/nav/accent vars are retargeted) — a palette can't make a verdict illegible. Nav (`--color-nav*`) and canvas dots (`--canvas-dot`) theme end-to-end.
- **Scale-aware (G6).** No pill-per-item selection or infinite lists found; AgentTriage caps 10/page (`AgentTriage.tsx:49`), RunDetail/Submit/Accession/Intake/Admin paginate via `Pager`, and switchers cap rows + search (`TopBar.tsx:40`, `RunSelector.tsx:22`). (The pager *duplication* is UIUX-03; the scale behavior itself is sound.)
- **Empty/error honesty.** `RunSelector` and `PipelineRepairModal` say "Couldn't load …" on failure rather than fabricating rows; `States.ErrorBox` offers `onRetry`; RunOverview's bespoke 503 error offers Retry (`RunOverview.tsx:159-165`).

### Low-confidence / not filed (couldn't confirm the defect)
- **Provenance run-summary pin renders a payload `status` verbatim.** `Provenance.tsx:176,202` shows `{nSamples} · {status}` where `status = readStr(completed.payload,'status')` sourced from `src/bayleaf/engine.py:169` (`payload={"status": arun.status, …}`). If `arun.status` is a snake_case enum it would leak a raw value; I could not confirm the exact string headless, so I am **not** filing it — flagged here as a 60-second thing to eyeball on the real Provenance page. Marked Possible only.
