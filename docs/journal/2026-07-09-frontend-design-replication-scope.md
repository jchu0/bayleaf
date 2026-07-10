# Journal — 2026-07-09 (MST) — Frontend design-replication scoping

| Field | Value |
|---|---|
| **Focus** | The maintainer dropped updated design files from the design track (`docs/design/frontend/` refreshed; a stale older copy also landed at repo root). Fan out agents to map the updated prototype against the current React app, flag every overlap/contradiction, and produce an ordered implementation scope before touching code. |
| **Outcome** | 14-way read-only gap analysis (one agent per screen/concern) + synthesis. App is structurally sound but **9 of 11 UI surfaces are `major-gap`/`new-build`**; data contract (`types.ts`/`api.ts`) missing ~80% of the types/methods the backend already serves. **28 flags** (contradictions/overlaps/ambiguities/backend-gaps) + 5 invariant guardrails, deduped cross-screen. Pipeline Builder is the heavyweight (~30–40% of total). Full scope embedded below; awaiting maintainer decisions on depth + serif before implementing. |
| **Related** | [docs/design/frontend/README.md](../design/frontend/README.md) (design source of truth) · [ADR-0014](../adr/) (productionization) · [tasks.md](../planning/tasks.md) T-022/T-022b (prior 1:1 migration) |

## Discussion

**Method.** A `Workflow` fan-out spawned 14 read-only analysis agents (shell+nav, tokens, Submit,
Runs, Intake, Decision cards, Review queue, Provenance, Agent triage, Monitoring, Settings, Pipeline
builder, data contract, repo hygiene), each comparing the **canonical** design
(`docs/design/frontend/README.md` + `source/PipeGuard.dc.html`, 3360 lines) to its React target,
then a synthesis stage deduped findings and ordered the plan. Baseline before any change: frontend
`tsc -b` clean + `oxlint` clean.

**One agent errored (recovered).** The `analyze:review-queue` agent hit the `StructuredOutput` retry
cap (5) — it wrote an over-verbose `designIntent` that truncated the payload before the other
required fields, failing schema validation repeatedly. Re-ran it standalone as a read-only agent with
free-form markdown output (no forced schema → no truncation-into-invalid failure); it returned
complete. Lesson for future workflows: cap per-field verbosity or split detail into array items so a
single field can't blow the output budget.

**Canonical vs stale (the headline overlap, F25).** `docs/design/frontend/` is the newest package
(dc.html 3360 lines / 1.19 MB). The repo-root `/PipeGuard.html`, `/source/`, `/briefs/`, `/handoffs/`
are an **older untracked extraction** (dc.html 2956 lines / 800 KB, superseded 00–03 handoff naming) —
a tab-complete/grep hazard that patches the wrong file. Recommendation: `rm -rf` the four root paths,
`git add` the README-cited `docs/design/frontend/briefs/…`, commit the WIP design files, add
root-anchored `.gitignore` guards.

**Review-queue recovered findings (merged into the flag set).** matchLevel `major-gap`: serif header +
eyebrow missing; tickets always fully expanded (no collapse/first-open); no status summary bar; no
Escalate-to-approver action; recurring banner uses `--hold-*` not `--rerun-*` and omits the window;
Suppress/repair buttons are inert placeholders. **RBAC contradiction:** the design lets a *Reviewer*
resolve holds/reruns, but backend §5e marks `action=resolve` approver-only — design is the stated
authority. Backend `/api/review/tickets` (+ actor/role headers) exists but is unwired in `api.ts`;
status token `in_review` vs code `'in-review'`.

---

## Consolidated implementation scope (synthesis)

_Verbatim synthesis output; the flag IDs (F1…F28, INV-a…e) are the stable reference for maintainer
decisions._

## Executive summary

The React app is a **structurally sound but visually and behaviorally partial** realization of the refreshed design: tokens and `verdict.ts` are near-verbatim (only theme is `minor-gap`), but **9 of the 11 UI surfaces are `major-gap` or `new-build`**, and the shared data contract (`types.ts`/`api.ts`) is missing roughly 80% of the types and client methods the shipped backend already serves. The single biggest piece of work is the **Pipeline Builder** — it needs ~16 net-new components (free composition, Connect-mode wiring, minimap, four modals, editable locators, a three-tab console) and dwarfs every other screen; the **Decision-cards QC-readout hero** and the **Settings dialog + assay-RBAC lifecycle** are the next two heaviest. Nothing in the plan requires inventing a backend endpoint — the two genuinely blocked features (Monitoring `first_seen/last_seen/trend`, Median-review KPI) are called out as backend decisions, and all compose surfaces (Submit, Builder) stay local-state per the "compose ≠ execute" invariant. The critical unlock is **Wave 1 foundation** (data contract + header-aware/RBAC api client + tokens + nav/route rewrite + shared RoleContext), which every screen depends on and which must land single-author before the per-screen work fans out.

---

## 1. Flags — deduped, cross-screen (priority deliverable)

Action key: **DECIDE** = genuine maintainer call · **AUTO** = safe to auto-resolve during build · **BACKEND** = needs a backend/spec change (don't invent on the client) · **GUARDRAIL** = invariant to preserve, no decision.

| ID | Kind | Where (screens) | Finding | Recommended resolution | Action |
|----|------|-----------------|---------|------------------------|--------|
| **F1** | contradiction | submit, runs, intake, decision, provenance, agent, monitoring, settings | dc.html renders every H1 in **Newsreader serif 27px/500**; the app uses **IBM Plex Sans 22px/600** app-wide and Newsreader is not wired. This is **one global decision**, not eight. | Adopt the serif as the design's deliberate refresh: add `@fontsource/newsreader` + a `--font-serif` token and route all page titles through a single shared `PageHeader` (eyebrow + serif title). One change, all screens. If the maintainer prefers consistency-with-current, keep sans — but decide once. | **DECIDE** |
| **F2** | backend-gap / contradiction | monitoring, data-contract | `MonitoringSignature` ships only `{signature,rule_id,title,gate,count}`. Design needs **first→last-seen (col 3)** and **trend ▲▼ (col 5)**; README §7 *claims* the aggregate carries `first_seen/last_seen` but the code omits them. | Add `first_seen`, `last_seen`, and a `trend` (first-half vs second-half of window) to `MonitoringSignature` in `api/main.py`; until then, render cols 3/5 as empty/omitted — **do not fabricate dates**. | **DECIDE / BACKEND** |
| **F3** | backend-gap | monitoring | "Median review" KPI (design value `6m`) has no source; `MonitoringOverall` has no review-latency field. | Either add a `median_review_*` field to the backend or ship the tile as an honest labeled placeholder. Recommend placeholder for the demo. | **DECIDE / BACKEND** |
| **F4** | contradiction | provenance | Design mock shows **align (BWA-MEM2) + variant (DeepVariant) executed** with BAM/VCF artifacts; the app honestly marks them "not run in this build" (pipeline starts from FASTQ). | Keep the honest empty-state (matches the "don't fabricate an aligner run" guardrail); confirm the maintainer accepts the visual divergence from the prototype. | **DECIDE** |
| **F5** | contradiction | intake | Design hard-codes the run-status chip as **"Run admitted"** (all-pass mock); code derives a dynamic **"Run needs review"** from real tiles. | Keep the dynamic state (more honest, "rules decide"); confirm intended. | **DECIDE** |
| **F6** | ambiguity | shell-nav | TopBar demo-state: dc.html has an interactive **Ready/Loading/Empty/Error** preview menu; app renders a passive data-driven "State: Ready". | Keep the passive indicator (aligns with data-driven-state invariant). Confirm the design accepts it. | **DECIDE** |
| **F7** | contradiction | agent-triage | README §5.7 prose says **"circular send"**; dc.html (source of truth for markup) renders a rounded-rect **"Send"** button. | Follow dc.html (rounded-rect labeled "Send", paper-plane icon). | **DECIDE** |
| **F8** | overlap | decision | `DecisionFeedback` (thumbs) + inline `TriagePanel` exist in the app's Split body but **not** in the prototype cards, which instead put an "Ask agent to triage" button in the context rail. | Decide keep-both (off-gate telemetry, ADR-0001-compliant) vs. replace with the rail button. Recommend keep the feedback footer, add the rail button, drop the inline triage panel from the card (it duplicates the Agent screen). | **DECIDE** |
| **F9** | ambiguity | settings | Granular-only "Metric catalog" section is an app extra not in §5.10. | Keep as an app-extra behind the Granular profile, or drop to match spec. Recommend keep (harmless, informative). | **DECIDE** |
| **F10** | ambiguity | settings | Guardrail copy promises "gate can't cross hard-fail / percentages clamp 0–100," but the prototype handler only does `Math.max(0,n)`. | Implement the promised clamps in React (the copy asserts them). | **DECIDE** |
| **F11** | ambiguity / invariant | pipeline-builder | README says ports are **half-circles → full circles in Connect mode**; neither prototype nor app implements half-circles (both use full dots). | Defer half-circle styling; ship full-dot ports that grow to full connect-circles. Confirm it's cosmetic. | **DECIDE** |
| **F12** | overlap | settings, data-contract | Two runbook surfaces: `/api/config` (raw `Runbook`) vs `/api/runbook` (operator-facing `RunbookPolicy` with disclaimer + `our_key` + direction). | Settings screen should consume `/api/runbook` (disclaimer-bearing); pick one shape per screen to avoid two competing threshold models. | **DECIDE** |
| **F13** | backend-gap | pipeline-builder, settings, data-contract | Save/version/approval and threshold-override are **client stubs** in the prototype; durable stores exist (`api/pipelines_lifecycle.py`, `api/settings_store.py`, `require_role`) but aren't wired. | Wire the RBAC lifecycle to the real stores **or** ship non-durable client stubs for the demo — flag that Approve/Save don't persist until connected. Time-box call. | **DECIDE / BACKEND** |
| **F14** | contradiction | shell-nav, submit, all | Nav grouping: README §4 = **2 groups (Operate/Configure)**; dc.html + current code = **3 groups (Operate/Analyze/Configure)**. | **Resolved to 2 groups** (task instruction + README are authority). Fold Analyze (Provenance, Agent triage, Monitoring) to the end of Operate; keep Configure = Pipeline builder · Settings. See §2b. | **AUTO** |
| **F15** | contradiction | runs, monitoring, data-contract | Status vocab: prototype uses `review`/`pending`; backend wire values are **`needs_review`/`pending_review`/`approved`**. | Use backend wire values in types; map to display labels ("Needs review") at the render layer only. Same for Pipeline/Settings status. | **AUTO** |
| **F16** | backend-gap | runs, data-contract | README §7 lists `dateFrom/dateTo` on `/api/runs`; the endpoint does **not** accept them (only Monitoring `window` does). | Filter the date-range **client-side on `run_date`** (fine for ~28 runs). Do not add the params to the client. | **AUTO / BACKEND** |
| **F17** | invariant-risk | runs, data-contract | Code infers "Released" from `n_attention===0`, so a running run mislabels. | Drive status/platform/date from the **real `RunSummary.status`** field (now typed); never infer. | **AUTO / GUARDRAIL** |
| **F18** | backend-gap | settings, data-contract | assay × sample-type thresholds are **not typed server-side**; `/api/settings/thresholds` stores an opaque `payload`. | Seed the assay-keyed rows client-side (matching the prototype `rowsByAssay`) and pack/unpack into the opaque `payload`. No backend type change. | **AUTO / BACKEND** |
| **F19** | contradiction | provenance | Origin chips still rendered in **header** and **per-artifact** despite README §5.6 explicitly removing them. | Delete both (the headline provenance contradiction). | **AUTO** |
| **F20** | overlap | decision | `MetricsPanel.tsx` is dead (imported nowhere) with wrong columns; `EvidenceTable` does double-duty as "QC readout by gate" but is findings-driven. | Repurpose `MetricsPanel` into the new **QCReadout** (metric_values → Metric·Observed·Threshold·Status); split findings into a separate **CitedEvidence** (Source·Field·Observed·Expected). | **AUTO** |
| **F21** | overlap | monitoring | `Monitoring.tsx` does an N+1 `api.runs()` + N× `api.run()` reassembly duplicating the server roll-up. | Consolidate onto a single `api.monitoring(window)` call. | **AUTO** |
| **F22** | contradiction | pipeline-builder | Default mode is **Edit** in code but README says **View**; Params were made editable and Locators read-only, **inverting** the design (Locators are the load-bearing edit surface); Tidy sits disabled in the toolbar instead of functional in the canvas cluster. | Default to **View**; make **Locators editable / Params read-only**; move Tidy to the canvas action cluster and make it work. | **AUTO** |
| **F23** | overlap | shell-nav, settings | Two "Settings" surfaces share the word: Configure→Settings (the `/settings` thresholds screen, exists) and the user-panel **profile/preferences dialog** (missing). | Build the dialog as a **separate modal**; do not route the popover's Settings to `/settings`. | **AUTO** |
| **F24** | overlap | tokens-theme | `--color-page` and `--color-card-2` are byte-identical (`#eef1f4`), collapsing the design's two-step neutral backdrop; `--color-nav-hover` is `#1b232c` vs design `#1b222b`; `App.css` is dead Vite scaffold. | Restore `--color-page: #f5f7f9`, keep `--color-card-2: #eef1f4`; add `--color-nav-active #22303f`; align nav-hover to `#1b222b`; delete `App.css`. | **AUTO** |
| **F25** | overlap / hygiene | repo-hygiene | **Two parallel copies** of the design package: canonical `docs/design/frontend/` (newest, some WIP `M`) and an **older untracked root extraction** (`/PipeGuard.html`, `/source/`, `/briefs/`, `/handoffs/`) with the superseded 00–03 handoff naming. A tab-complete/grep can patch the wrong (older) file. | `rm -rf` the four root paths (untracked, zero history); `git add` the untracked README-cited `docs/design/frontend/briefs/review-to-design-brief.md`; commit the 4 WIP files; add **root-anchored** `.gitignore` guards (`/PipeGuard.html`, `/source/`, `/briefs/`, `/handoffs/`). Keep the large prototypes committed (cited source of truth; use git-lfs later if size bites, never gitignore). | **AUTO** |
| **F26** | ambiguity | data-contract | README §7 TS sketch uses `{id,samples,attention,date}`; shipped API + `types.ts` use `{run_id,n_samples,n_attention,run_date}`. | Use the **API/pydantic names**; treat README §7 TS as illustrative. | **AUTO** |
| **F27** | backend-gap | submit, data-contract | No `POST /api/submissions`, no samplesheet-upload, **no BaseSpace endpoint**. | Build Submit **local-state only** (registration/navigation); keep `source:'basespace'` selectable but wire no client method. Preserve compose ≠ execute. | **AUTO / BACKEND** |
| **F28** | backend-gap | provenance | `RunArtifact` has no `url/href`; per-stage **note string** isn't served. | "Open in store"/"download" need an artifact URL field (or a defined client no-op/store route); "Copy digest" is client-side clipboard. Per-stage note: add a stage note field or, interim, present gate `rationale` in the band and synthesize non-gate notes. | **BACKEND** |
| **INV-a** | invariant-risk | decision, monitoring, data-contract, agent | No **confidence meter** anywhere. | Keep `DecisionCard.confidence` unrendered; label `auto_proceed_pct` a throughput heuristic. | **GUARDRAIL** |
| **INV-b** | invariant-risk | provenance, decision, data-contract | **Origin never relabels up**; `not_captured` reported honestly. | Origin fields read-only in the client; show "not captured", never fabricate `sample_type`/`library_prep`/`origin`. | **GUARDRAIL** |
| **INV-c** | invariant-risk | decision, intake, agent, settings, shell-nav | **Rules decide / AI advises.** | Synthesis-error state must still render rule-derived cards (current "error → no cards" path violates this); intake override + role toggle + agent chat must never set/override a verdict or confidence. | **GUARDRAIL** |
| **INV-d** | invariant-risk | submit, pipeline-builder | **Compose ≠ execute.** | Submit and Builder register/emit config only; no call may start processing. Keep the barcode-collision guardrail note verbatim. | **GUARDRAIL** |
| **INV-e** | invariant-risk | pipeline-builder | Prototype `bPortTap` wires **any** output→input. | Enforce **typed-port kind-matching** in Connect mode so V1 "all edges kind-matched" stays honest. | **GUARDRAIL** |

### 2b. Nav-grouping recommendation

**Adopt the two-group nav (Operate / Configure).** README §4 is the declared source of truth and the task confirms it; the three-group code follows the stale dc.html prototype. Concretely: **Operate** = Submit samplesheet · Runs · Intake gate · Decision cards · Review queue · Provenance · Agent triage · Monitoring (this exact 8-item order, Submit first); **Configure** = Pipeline builder · Settings. This lands in Wave 1 (`Sidebar.tsx`).

---

## 2. Cross-cutting foundation (must land first — Wave 1)

These are the shared contracts every screen imports; parallel writers on them collide, so **Wave 1 is single-author and serialized internally** in this order:

**W1-A · Tokens & theme** (`index.css`, delete `App.css`) — restore `--color-page: #f5f7f9`; add `--color-nav-active #22303f`, fix `--color-nav-hover #1b222b`; add `pgspin` + `pgfade` keyframes and **all shared keyframes now** so screen waves never touch `index.css` and collide; (if F1 = serif) add `--font-serif` + Newsreader font. *Effort M.*

**W1-B · Data contract** (`types.ts`) — the gating dependency for every screen. Add `RunStatus`; `status/platform/run_date` on `RunSummary`; the `Monitoring*` family; `CardReadout/QcReadout/GateReadout/MetricReadout/CardHeader`; the `Pipeline*` family; `Ticket*` family; `ThresholdOverride*` family; `RunbookPolicy/RunbookThreshold`; unions `OriginTag/ArtifactKind/ReferenceKind`; frontend-local compose types `Submission/SampleRow/LayoutLocator/RunLayoutConfig/ProposedFlag/AgentProposal`. Use **backend wire names/values** (F15, F26). *Effort L.*

**W1-C · API client** (`api.ts`, depends on W1-B) — a **header-aware fetch** returning `{data,total,statusCounts,page,limit}` (current `get<T>` discards headers, so pagination + status facets are structurally unreadable); **RBAC header injection** (`X-PipeGuard-Actor`/`-Role`) on writes; new methods: `runs(opts)`, `monitoring(window)`, `qcReadout(run,sid)`, pipeline CRUD+lifecycle, review tickets, settings thresholds, `runbook()`, `export()`, archive/repair reads. Only for endpoints that exist (respect F16/F27). *Effort L.*

**W1-D · Shared RoleContext** (new `context/RoleContext.tsx`) — one `reviewer|approver` source consumed by the user panel, Settings save/approve, Pipeline-builder approve, Review queue, and feeding W1-C's actor/role. Resolves the F-cluster where a popover toggle would otherwise be cosmetic. *Effort S.*

**W1-E · Nav + routing** (`Sidebar.tsx`, `App.tsx`, `TopBar.tsx`) — fold to 2 groups (§2b); add **Submit as first Operate item** + `/submit` route (pointing at a minimal Submit stub created here) + TopBar crumb + `/` separator; fix selected-item styling (`#22303f`/600), unselected `#aab4bf`, attention-badge rebind to the current run's flagged-sample count in mono, green avatar gradient, distinct icons. *Effort M.*

**W1-F · Shared primitives** (new files) — `PageHeader` (eyebrow + title), `useRefresh` hook ("Updated {time}" + spin), `CollapsibleRow` (chevron header + drawer), `SegmentedControl`, `FacetChip` (mono count badge). These are extracted once (intake/monitoring/decision/runs all reuse them, per the F "shared primitive" overlaps) so screen waves don't hand-roll four divergent copies. Also fold the `RunDetail ?filter=attention` seed here so Monitoring's affected-run chips land correctly without a second author on `RunDetail.tsx`. *Effort M.*

---

## 3. Ordered implementation plan (waves)

### Wave 1 — Foundation (single-author, serialized): W1-A → W1-F above. Nothing else starts until B/C/E land.

### Wave 2 — Per-screen builds (parallel-safe; each owns its `screens/*.tsx` + its own new components)

All Wave-2 screens are mutually parallel **except** the two coupling notes flagged inline. Backend edits (`api/main.py` for F2/F3, optional date params) run as a **separate parallel backend track**, not blocking the frontend if the decided-deferred columns are omitted.

**① Submit samplesheet — `new-build` — NOT parallel-blocking (net-new file).**
Gaps: scaffold route/nav/crumb *(M, done in W1-E stub → flesh out here)*; header eyebrow+title+intro *(S)*; segmented Upload/BaseSpace toggle *(S)*; upload drop-zone + parsed chip *(M)*; BaseSpace connect card (gated token) *(M)*; connected run-list + Import *(M)*; run-details 4-field card *(S)*; editable samples table w/ type-cycle chip + add/remove + empty state *(L)*; footer guardrail + Save-draft (inert) + Submit→intake nav *(S)*. Files: `screens/Submit.tsx` (new). Local-state only (F27). **Parallel: yes.**

**② Runs overview — `major-gap`.**
Gaps: full toolbar — search · Recent/Urgent sort · **date-range calendar** · per-page · pager *(L)*; 4 real-status **facet chips w/ mono count badges** *(M)*; run card + platform·date + status pill + inline count legend *(M)*; header eyebrow/gate-ring *(S)*; card hover-lift/radius polish *(S)*; empty/error states *(S)*. Files: `screens/RunOverview.tsx` (+ `api/main.py` only if date params chosen — else client-side per F16). **Parallel: yes.**

**③ Intake gate — `major-gap`.**
Gaps: **collapsible admission rows** (chevron + drawer, uses W1-F `CollapsibleRow`) *(L)*; scaled yield bars in drawer *(M)*; **Refresh control** (uses W1-F `useRefresh`) *(M)*; status-chip/override copy+colors *(M)*; header eyebrow/serif *(S)*; step indicator placement/hue (#1f6feb) *(M)*; card header/body split *(M)*; QC-tile chip semantics *(S)*; "No intake data" empty state *(S)*. Keep honest FASTQ tiles (F4/InterOp gap). Files: `screens/Intake.tsx`. **Parallel: yes.**

**④ Decision cards — `major-gap` (second-heaviest).**
Gaps: **QCReadout hero** from `metric_values`/`qc-readout` — the flagship, currently absent on clean cards *(L)*; **ContextRail 288px** *(L)*; fix Dense/Brief layouts (both diverge) *(L)*; released + synthesis-error + skeleton loading states *(M)*; first-card-open (not all-non-proceed) *(S)*; **CitedEvidence** split from `EvidenceTable` *(M)*; header eyebrow/serif/platform·date + proportional bar replacing stat tiles *(M)*; sample-type + origin chips *(M)*; next-steps arrows/numbered pills *(S)*; metric-Fail→rerun color *(S)*. Files: `screens/RunDetail.tsx`, `MetricsPanel.tsx`→QCReadout, `EvidenceTable.tsx`, `GateResultStrip.tsx`, `States.tsx`, `DecisionFeedback.tsx`, `verdict.ts`. **Wire `card_readout.py` via `api.qcReadout` (F20).** ⚠ **Coupling: also owns `RunDetail.tsx`** — take the `?filter=attention` seed from W1-F; Monitoring must not co-author this file. **Parallel: yes, but sole author of `RunDetail.tsx`.**

**⑤ Provenance — `major-gap`.**
Gaps: **remove header + per-artifact origin chips** (F19) *(S+S)*; **artifacts as links** (open-in-store/copy-digest/download) *(M, F28 for URL)*; **color node number badges by status** *(M)*; per-stage note bar *(M, F28)*; gate badge → pill w/ dot *(S)*; status-pill label "Awaiting review" *(S)*; eyebrow/serif *(S)*; grid stretch + node chrome *(M)*; artifact divider rows *(S)*. Keep align/variant honest empty-state (F4). Files: `screens/Provenance.tsx`. **Parallel: yes.**

**⑥ Agent triage — `major-gap`.**
Gaps: **multi-line `<textarea>` composer** (Enter send / Shift+Enter newline) *(M)*; **pop-out/minimize modal** *(L)*; Ask-the-agent header *(S)*; composer footer helper *(S)*; suggestion-chip copy/style *(S)*; empty state *(S)*; bubble radii/bg *(S)*; Send label/style *(S)*; eyebrow/serif *(M)*; live/offline source toggle *(M)*; subject-card footer *(S)*; error-fallback banner *(S)*. Keep the multi-sample picker (reasonable real-data enhancement). Files: `screens/AgentTriage.tsx`. **Parallel: yes.**

**⑦ Monitoring — `major-gap`.**
Gaps: **collapsible searchable 5-col signature grid** (chevron·signature·first→last·freq·trend + drawer) *(L)*; search + empty state *(M)*; **affected-run chips → `/runs/:id?filter=attention`** *(M, uses W1-F seed)*; per-row **Escalate-to-repair** (advisory read) *(M)*; **7/14/30d window + single `api.monitoring`** (drop N+1, F21) *(L)*; KPI set/labels + median tile *(M, F3)*; gate bars per-gate color *(S)*; date-labelled throughput bars *(S)*; band ratio/eyebrow/serif *(S)*. Files: `screens/Monitoring.tsx`, `api/main.py` (F2 first_seen/last_seen/trend). ⚠ Cols 3/5 render only once F2 backend lands — omit honestly otherwise. **Parallel: yes** (RunDetail seed already in W1-F).

**⑧ Settings — `major-gap` (third-heaviest).**
Gaps: **SettingsDialog** (user-panel → Profile + Preferences modal) *(L)*; **assay-keyed Whole-blood/Saliva table** w/ read-only→Edit→Save→**approver-gated** lifecycle + audit + guardrail note *(L+L)*; **per-agent model tiering** (3 dropdowns, roster **incl. Fable 5**) *(M)*; **notifications** Slack+Teams+Discord *(M)*; pricing fix (Opus 5/25) *(S)*; eyebrow/copy *(S)*; operator-profile layout + required-metadata chips *(S)*. Uses RoleContext (W1-D). assay rows client-seeded into opaque payload (F18); consume `/api/runbook` (F12). Files: `screens/Settings.tsx`, `components/Sidebar.tsx` (user panel — **coordinate with the shell user-panel task**), `SettingsDialog.tsx` (new). **Parallel: yes, but the Sidebar user-panel/popover is shared with the shell task — assign both to one author.**

**⑨ Shell user panel + popover** (the interactive `UserPanel` + `UserSettingsDialog`) — pairs with ⑧ and W1-D. Replace the static footer div with the avatar button + popover (Settings row → dialog, Role row → RoleContext toggle, Sign out). *Effort M.* Files: `components/Sidebar.tsx`. **Assign together with ⑧** (same file/state).

### Wave 3 — Pipeline Builder (its own track — **the heavyweight**)

`major-gap`, **~16 net-new components, effort XXL** — treat as a standalone multi-day track that can run in parallel with Wave 2 but is the largest single body of work in the project:
Console tab switcher + **Diff + Dry-run tabs** *(L)*; Save·version·approval cluster + RBAC toggle *(M)*; **profile combobox** *(M)*; **free composition** (palette add + user nodes + drag/delete) *(L)*; **Connect mode + port wiring + minimap** *(L)*; Run hand-off modal *(M)*; **Author-a-tool-node modal** *(L)*; **editable Locators + live YAML regen** *(L)*; pipeline-repair + archivist modals *(L)*; reference inspector *(M)*; gate runbook table *(M)*; linked-run strip *(M)*; default→View, Params/Locators invert, canvas centering, sarek banner, agent-inspector values *(S each)*. Enforce **typed-port kind-matching** (INV-e). Files: `screens/PipelineBuilder.tsx`, `verdict.ts` (+ new modal/component files). Save/approve non-durable until F13 stores wired.

### Wave 0 (do anytime, independent) — Repo hygiene (F25)

`git rm -rf` the four root strays; `git add` the README-cited brief; commit the 4 WIP design files; add root-anchored `.gitignore` guards. *Effort S.* No code dependency — can run first or last.

---

## 4. New files / components to create

1. `screens/Submit.tsx` — full new screen (+ segmented toggle, drop-zone, BaseSpace card, editable samples table).
2. `context/RoleContext.tsx` — shared `reviewer|approver`.
3. Shared primitives: `PageHeader`, `useRefresh`, `CollapsibleRow`, `SegmentedControl`, `FacetChip`, `DateRangePicker`.
4. Decision: `QCReadout` (repurposed `MetricsPanel`), `CitedEvidence`, `ContextRail`, `VerdictBar`, released/synthesis-error/skeleton states.
5. Shell: `UserPanel` popover, `UserSettingsDialog`.
6. Settings: `SettingsDialog`, `AssayThresholdTable`, `ModelTierRow`, `NotificationChannelRow`.
7. Monitoring: collapsible `SignatureRow`, signature search + empty state, window selector.
8. Pipeline Builder (~16): `RunHandoffModal`, `AuthorToolNodeModal`, `PipelineRepairModal`, `ArchivistModal`, `ProfileCombobox`, `SaveVersionApprovalCluster`, `LinkedRunStrip`, Connect-mode + user-node canvas, `Minimap`, canvas action cluster, `ReferenceInspector`, gate runbook table, editable `LocatorRow`, console `DiffTab`/`DryRunTab` + switcher.
9. api.ts: header-aware fetch helper; RBAC header injection.

---

## 5. Effort read & time-box guidance

**Rough totals** (T-shirt): Wave 1 foundation ≈ **L–XL** (2–3 focused days); Submit **L**; Runs **L**; Intake **L**; Decision **XL**; Provenance **M–L**; Agent **M–L**; Monitoring **L**; Settings + user panel **XL**; Pipeline Builder **XXL** (≈ a week on its own); repo-hygiene **S**. **Whole program ≈ 3–4 engineer-weeks**, with the Builder as ~30–40% of it. Because Wave 2 is parallel-safe, wall-clock compresses hard with 3–4 authors after Wave 1.

**If time-boxed (demo-critical first):**
- **Build:** Wave 0 hygiene · Wave 1 foundation in full · Nav+Submit (front door) · Runs toolbar/facets · **Decision QC-readout hero + released/synthesis-error states** (the app's centerpiece) · Intake collapsible rows + Refresh · Provenance origin-chip removal + artifact links · Agent composer (textarea + pop-out) · Monitoring wired to `/api/monitoring` with collapsible signatures + search + window.
- **Defer:** Pipeline Builder **free-composition / Connect-mode / four modals** (ship the read-only skeleton + three-tab console only) · Settings **full preferences dialog + full assay-RBAC lifecycle** (ship per-agent tiering + notifications + a read-only assay table) · Monitoring **first_seen/last_seen/trend cols + Median-review KPI** (blocked on F2/F3 backend) · BaseSpace import · half-circle ports · InterOp tiles. All deferrals are either backend-blocked or the least demo-visible, and none touch an invariant.

**Guardrails that hold across every wave (INV-a…e):** no confidence meter; origin never relabels up; rules decide / AI advises (synthesis-error still shows rule-derived cards; overrides/role-toggle/agent never set a verdict); compose ≠ execute; typed-port kind-matching enforced.

---

## Maintainer decisions (2026-07-09 MST)

1. **Scope: "Everything, faithfully"** — full replication of all 11 surfaces incl. the Pipeline
   Builder XXL track and the complete Settings RBAC lifecycle. Pause for review between waves.
2. **F1 → adopt Newsreader serif** for all page titles via a shared `PageHeader` + `--font-serif`.

Defaulted DECIDE flags (unless overridden): keep honest empty-states (F4/F5); "Send" per dc.html
(F7); keep feedback footer + rail "Ask agent", drop inline triage panel (F8); keep Metric catalog
(F9); implement threshold clamps (F10); defer half-circle ports (F11); Settings consumes `/api/runbook`
(F12); Review-queue Reviewer resolves holds/reruns, escalation-resolution needs Approver.

Execution starts at **Wave 1 (foundation, single-author)**: W1-A tokens/serif · W1-B types · W1-C
api client · W1-D RoleContext · W1-E nav+routing+Submit stub · W1-F shared primitives. Wave 0 repo
hygiene folded in.

---

## Wave 1 — foundation (DONE, verified)

Single-author foundation landed; `tsc -b` + `oxlint` clean; browser-verified (no console errors,
API data loads).

- **Wave 0 hygiene** — removed the stale root `/PipeGuard.html /source /briefs /handoffs`
  duplicate; added root-anchored `.gitignore` guards (F25).
- **W1-A tokens/serif** — `--color-page` restored to `#f5f7f9` (un-collapsed from `--color-card-2`
  `#eef1f4`, F24); added `--color-nav-active #22303f`, `--font-serif` (Newsreader), `pgspin`
  keyframe; nav-hover → `#1b222b`; deleted dead `App.css`; `main.tsx` imports Newsreader 400/500 +
  sans 500 + mono 500/600. Added `@fontsource/newsreader` dep.
- **W1-B types.ts** — added RunStatus + status/platform/run_date on RunSummary; RunsPage; Role/Actor;
  OriginTag/ArtifactKind/ReferenceKind; the Monitoring*, CardReadout/QcReadout, RunbookPolicy,
  Pipeline*, Ticket*, ThresholdOverride*, AgentProposal, and frontend-local compose families — all
  on backend wire names/values (needs_review, pending_review).
- **W1-C api.ts** — header-aware `runsPage()` (reads X-PipeGuard-Total-Count/-Status-Counts/-Page/
  -Limit), RBAC header injection via `setApiActor`, and typed methods for every shipped endpoint
  (runs query, qcReadout, monitoring, tickets, pipeline CRUD+lifecycle, threshold overrides, runbook,
  archive/repair reads). No invented endpoints (respects F16/F27).
- **W1-D RoleContext** — shared reviewer|approver, toggled from the user panel, feeds the API actor.
- **W1-E shell** — Sidebar rebuilt to 2 groups (Operate/Configure) in design order with Submit first,
  distinct icons, mono attention badge (current run's flagged count), and the interactive user-panel
  popover (Settings dialog / Role toggle / Sign out); UserSettingsDialog (profile+prefs modal); TopBar
  `/` separator + Submit crumb + always-on search + card-2 insets; App.tsx wraps RoleProvider + adds
  `/submit`; Submit screen stub (Wave-2 flesh-out).
- **W1-F primitives** — PageHeader (serif title), SegmentedControl, FacetChip, CollapsibleRow,
  useRefresh.

**Verified in browser:** serif H1 = Newsreader 27px/500/-0.3px; 2-group nav; user-panel popover;
role toggle propagates popover→footer→API actor; page bg `#f5f7f9`.

**Next:** Wave 2 (per-screen builds, parallel-safe) — pausing here for review per the agreed cadence.
