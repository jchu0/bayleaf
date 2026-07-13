## Specialist 4 — Integration-seam audit → bayleaf release-hardening (Track A, Fable 5)

**Scope run:** code-only / headless. Every claim re-opened and the quoted string confirmed in the file. Owns: `api/routers/*`, `api/main.py` routes, `api/*_store.py`, six agent modules, `frontend/src/api.ts` call sites, `BuilderModals.tsx`, `SettingsModelTier.tsx`, `app/streamlit_app.py`.

**Headline:** The wiring surface is, on the whole, *honestly labelled* — nearly every unfinished seam wears a visible `phase-2` / `advisory` / "not wired" tag, RBAC writes are all server-enforced, and `compose ≠ execute` holds at the core. The integration defects that remain are (a) a **second, undocumented execution path** that runs an unapproved live graph, (b) a cluster of **read-wired / write-inert CTAs** whose primary buttons do nothing, (c) one **audit-feed blind spot** (share egress never reaches the Admin Activity feed), and (d) **UI-only Settings persistence** with a success toast that overstates it. None are G1–G7 Blockers (no agent can set a verdict; no un-gated cascading write on the golden path).

### Capability matrix (verified against repo, not docs)

| Capability | UI | API | Persistence | Execution | Agent | Tested | Notes / `file:line` |
|---|---|---|---|---|---|---|---|
| Submit → run (primary) | ✔ Submit → `api.submitRun` | ✔ `POST /api/runs` `intake.py:126` | ✔ `data/<run_id>/` | ✔ driver subprocess `intake.py:107` | n/a | partial (real `_execute` monkeypatched offline) | RBAC `require_role("reviewer","approver")` `intake.py:128`; 409 dup guard `:134` |
| Builder Run → run (2nd path) | ✔ `RunPipelineModal` `PipelineBuilder.tsx:1376` | ✔ `POST /api/pipelines/run` `pipeline_run.py:173` | ✔ | ✔ `pipeline_run.py:268` | n/a | partial | **Not in CLAUDE.md code map**; **no approved-status gate** — RBAC role only `pipeline_run.py:176,187-189` (F-INT-02) |
| Compile / export | ✔ `NextflowExportModal` | ✔ `POST /api/pipelines/compile` `nextflow.py:74` | none (stateless) | none | n/a | ✔ | off-gate transform, honest |
| Node-authoring agent | ✗ `AuthorToolNodeModal` static mock | ✗ (`grep node_author api/` empty) | ✗ | ✗ | ✔ core `propose_node` `node_author/agent.py:333` | core only | F-INT-01 |
| metrics-expansion agent | roster row only `SettingsModelTier.tsx:54` | ✗ | ✗ | ✗ | ✗ (no module; env var absent from `.env.example`) | ✗ | vaporware, F-INT-03 |
| SettingsModelTier Save | ✔ local React state `SettingsModelTier.tsx:171` | ✗ (`settings.py` only `/thresholds`) | ✗ | not bound to `BAYLEAF_*_MODEL` | n/a | n/a | F-INT-04 |
| `RunHandoffModal` | exported, 0 call sites `BuilderModals.tsx:79` | — | — | — | — | — | orphaned; CLAUDE.md:341 still describes it — F-INT-05 |
| Pipeline-repair modal | ✔ read `api.monitoring`/`api.signatureRepair` | read endpoints exist | ✗ write | — | ✔ (advisory) | — | "Send to review queue" navigate-only `BuilderModals.tsx:504-513`; no repair→ticket bridge — F-INT-06 |
| Archivist modal | ✔ read `api.archiveIndex` | read exists | ✗ write | — | ✔ (advisory) | — | "Queue archive" `onClose` only `BuilderModals.tsx:586-587` — F-INT-07 |
| D3 Share audit | ✔ ConfirmDialog | ✔ `POST /api/runs/{id}/share` `main.py:948` | ✔ `DATA_EXPORTED` event | — | n/a | — | lands in Provenance only; **Admin `FeedKind` has no `share`** `Admin.tsx:427` — F-INT-08 |
| `GET /api/monitoring` `runs[]` | Monitoring screen | ✔ `main.py:1282` | — | — | — | — | **uncapped** — only `signatures_limit`, no `page`/`limit` for runs — F-INT-09 |
| Page-access RBAC | ✔ `access.ts` (view-gate) | server `require_role` unchanged | localStorage only (labelled seam) | — | — | — | **honest** (see Honest surfaces) |
| `/metrics` + Grafana/Prometheus | Admin external links `:9090`/`:3000` | ✔ real exporter `_render_prometheus` `main.py:1505` | — | — | — | — | **honest** (off-demo-path, labelled) |
| Streamlit app | parallel UI | imports core directly `app/streamlit_app.py:19-21` | — | ✔ via core | ✔ synthesizer | untracked by React seams | parallel delivery layer, honest |

---

### Findings (Blockers first — none rose to Blocker; ranked by signal)

**F-INT-02 · Second execution path `POST /api/pipelines/run` runs an unapproved live graph and is undocumented · High · Confirmed · incomplete-integration**
Builder "Run pipeline" compiles and executes the operator's **live canvas graph** as a real background subprocess gated on RBAC role alone — it never checks the `Save→Submit→Approve` lifecycle (`api/routers/pipeline_run.py:176` `require_role("reviewer","approver")`, `:187-189` `graph = _to_graph(...)` → `compile_graph(graph)` compiled fresh, `:268` `subprocess.run(cmd, ...)`). This is a full second execution boundary beside `POST /api/runs`, yet **CLAUDE.md's router code map omits it entirely** (`grep -n "pipeline_run\|pipelines/run" CLAUDE.md` = no hits; the map at CLAUDE.md:225-226 lists `settings.py`/`review_queue.py`/`pipelines_lifecycle.py` but not `pipeline_run.py`; `nextflow.py` is described as compile-only at CLAUDE.md:216).
- Actual: an unsaved/unapproved draft graph runs directly; the approval lifecycle (`pipelines_lifecycle.py`) governs only locators/dry-run/diff, not this run.
- Expected: either gate `/api/pipelines/run` on approved `PipelineGraphStore` status, or document that live-graph execution is an intentional demo affordance.
- Min fix: add the second execution path to CLAUDE.md's code map; decide gate-vs-affordance (maintainer W1 already resolves toward adding the approved-status gate — that is *new scope*, so for Track A the minimum is the doc reconciliation + an explicit "unapproved graphs are runnable" note).
- Demo-critical: Y (Builder golden path). Fix risk: doc-only = none; adding the gate risks breaking the demo Run beat → defer to W1.

**F-INT-01 · Node-authoring agent is core-only; the Builder "add to palette" button registers nothing · Medium · Confirmed · incomplete-integration**
`AuthorToolNodeModal`'s primary CTA "Review kinds & add to palette" is `onClick={onClose}` (`BuilderModals.tsx:340-342`) — identical to the "Discard" handler; it surfaces/registers nothing. The real agent is core-only: `propose_node` exists (`src/bayleaf/node_author/agent.py:333`) but `grep -rn node_author api/` = empty and `grep -rn propose_node frontend/src` = empty (no endpoint, no transport). The modal is honestly tagged "roster #5 · phase-2" (`BuilderModals.tsx:210-212`), which keeps this from being a truthfulness Blocker, but the button verb "add to palette" implies a side effect that never happens.
- Min fix: relabel the CTA to a phase-2-honest verb (e.g. "Preview proposal (phase-2)") so it doesn't imply palette registration. Demo-critical: Y (on the Builder path). Fix risk: trivial.

**F-INT-08 · D3 Share egress is invisible in the Admin Activity feed · Medium · Confirmed · missing-user-facing-state**
`POST /api/runs/{run_id}/share` (`api/main.py:948`, `require_role("approver")` `:951`) records a tamper-evident `DATA_EXPORTED` provenance event — but the Admin Activity feed's `FeedKind` union has no `share` case: `type FeedKind = 'threshold' | 'pipeline' | 'ticket' | 'access' | 'actas'` (`frontend/src/screens/Admin.tsx:427`). A de-identified data export — the single most stakes-y egress action — therefore never appears in the central audit feed; it is auditable only if someone opens that run's Provenance trail.
- Min fix: add a `share` `FeedKind` + source it from `DATA_EXPORTED` events into the Admin feed. Demo-critical: N (off recording default). Fix risk: low (additive feed case).

**F-INT-06 · Pipeline-repair "Send to review queue" is write-inert; no repair-proposal→ticket bridge · Medium · Confirmed · incomplete-integration**
The modal is read-wired (fetches `api.monitoring('all',25)` `BuilderModals.tsx:364` + `api.signatureRepair` `:386`) but its primary CTA only `onClose()` + `navigate('/queue')` + a toast (`BuilderModals.tsx:504-513`); `grep -rn "RepairProposal\|createTicket\|repair" api/routers/review_queue.py` = empty — there is no write endpoint turning a signature-level `RepairProposal` into a sample-scoped ticket. The toast is honest ("Routing a signature-level fix to a specific ticket needs a sample-scoped ticket and approver sign-off" `:507`), so no orphaned linkage is *claimed*. Secondary: the modal still renders a "phase-2" badge (`:416`) though it is now wired to real read endpoints — the badge *understates* its read status.
- Min fix: keep the honest toast; drop/relabel the stale "phase-2" badge to "read-only" so the label matches the wiring. Demo-critical: N. Fix risk: trivial.

**F-INT-04 · SettingsModelTier Save persists nothing but toasts "Updated N agents" · Medium · Confirmed · missing-user-facing-state**
`applyPanel()` only mutates local React state — `setRows(next)` (`SettingsModelTier.tsx:171`) — with no `api.ts` call; `settings.py` exposes only `/thresholds` endpoints (`api/routers/settings.py:185,228,266`), and agent models are read solely from `BAYLEAF_*_MODEL` env vars at agent init (`api/feedback_agent.py:196`, `api/archivist.py:495`). The confirm dialog is honest ("Demo seam — nothing here persists to the backend yet" `:166`), but the terminal success toast `Updated ${panelKeys.length} agent…` (`:174`) reads as an applied change.
- Min fix: qualify the toast (e.g. "Staged locally — not persisted"). Demo-critical: N (off recording). Fix risk: trivial.

**F-INT-03 · metrics-expansion agent is pure vaporware surfaced as a roster row; nothing structurally blocks a "Live" toggle · Medium · Probable · incomplete-integration**
Roster row `{ key: 'metrics_expand', … env: 'BAYLEAF_METRICS_AGENT', wired: false, phase2: true }` (`SettingsModelTier.tsx:54`) — there is **no backend module** and the env var is **absent from `.env.example`** (`grep -n AGENT= .env.example` shows only TRIAGE/PIPELINE_REPAIR/ARCHIVIST/NODE_AUTHOR; `grep -rn BAYLEAF_METRICS_AGENT .` hits only frontend + docs). It starts in "Available" (`INITIAL_ACTIVE` filters `a.wired` `:57`), but the Execution live/stub `SegmentedControl` (`:279-283`) has no guard preventing a phase-2/unwired row from being edited to "Live" — a user who adds it to the roster and toggles Live would see a vaporware agent render "Live" (client-only). The `phase-2` label persists in the editor header (`:228`), which mitigates it.
- Min fix: disable the Live segment for `wired:false` rows (force Stub), or hide `metrics_expand` from the roster entirely for the demo. Demo-critical: N (Settings, off path). Fix risk: low. Confidence Probable because the Live-read requires a multi-step user interaction and stays client-only.

**F-INT-07 · Archivist "Queue archive" is write-inert; stale phase-2 badge · Low · Confirmed · incomplete-integration**
Read-wired (`api.archiveIndex()` `BuilderModals.tsx:530`); the "Queue archive" CTA is `onClick={onClose}` (`:586-587`) with no write endpoint. Footer copy is honest ("nothing is moved automatically" `:582`). Like F-INT-06 it carries a "phase-2" badge (`:558`) though read-wired.
- Min fix: relabel badge to "read-only"; leave the inert write honestly disabled. Demo-critical: N. Fix risk: trivial.

**F-INT-05 · `RunHandoffModal` is orphaned dead code still documented as the hand-off surface · Low · Confirmed · incomplete-integration**
`export function RunHandoffModal` (`BuilderModals.tsx:79`) has **zero call sites** (`grep -rn RunHandoffModal frontend/src` returns only the definition); it is superseded by `RunPipelineModal` (used at `PipelineBuilder.tsx:1376`). Yet CLAUDE.md:341 still describes it: "`RunHandoffModal` now shows the real composed `run_layout.yaml`" — doc drift pointing at dead code.
- Min fix: delete the export (and CLAUDE.md line) or re-wire; do not ship both a live and a phantom hand-off surface. Demo-critical: N. Fix risk: low (verify no lazy re-export first).

**F-INT-09 · `GET /api/monitoring` returns an uncapped `runs[]` · Low · Confirmed · post-hackathon-improvement**
`get_monitoring(window, signatures_limit)` (`api/main.py:1282-1286`) caps only the signature list (`sig_limit`, `:1401`); every in-window run is appended to `rows` and returned in `runs: list[MonitoringRunRow]` (`:1329,1343-1350,1277`) with no `page`/`limit`. At the house-rule 100+ sample scale (G6) the payload grows unbounded server-side. Not a golden-path break (recording uses the fixed served set), so backlog.
- Min fix: add optional `page`/`limit` to `runs[]` mirroring the run-list pager (`main.py:438-439,490-494`). Demo-critical: N. Fix risk: low.

**F-INT-10 · SettingsModelTier roster `env` labels don't match the real env vars · Low · Confirmed · design-inconsistency**
The roster displays each agent's env var (`single.env`, `SettingsModelTier.tsx:225`; tooltip "Each model is a BAYLEAF_*_MODEL env var" `:335`), but several labels are wrong: synthesizer `env: 'BAYLEAF_SYNTHESIZER'` (`:48`) while the real model var is `BAYLEAF_CLAUDE_MODEL` (`.env.example:12`); node-author `env: 'BAYLEAF_NODE_AUTHOR'` (`:53`) while the real vars are `BAYLEAF_NODE_AUTHOR_AGENT` / `BAYLEAF_NODE_AUTHOR_MODEL` (`.env.example:49,54`). An operator copying these strings into a `.env` would set a no-op var.
- Min fix: correct the `env` strings to the real `BAYLEAF_*_MODEL` names. Demo-critical: N. Fix risk: trivial.

---

### Honest surfaces (verified clean — do not flag)
- **Page-access RBAC is honestly scoped.** `frontend/src/access.ts:2` self-documents "a client-side VIEW-GATE, NOT a security control" and `:7-9` "it never authorizes a server write. The wire role … continues to govern every real write via api/auth.py's require_role, entirely unchanged." No write relies on client gating — checklist item 10 confirmed clean.
- **`/metrics` exporter is real and links are honestly off-path.** `_render_prometheus()` (`api/main.py:1505`) is a real exporter; Admin surfaces `Prometheus /metrics` as the read-API seam and Prometheus `:9090` / Grafana `:3000` as external links explicitly noted "not part of the offline demo path" (`Admin.tsx:759-761`). Checklist item 11 confirmed honest.
- **Streamlit is a genuine parallel layer.** `app/streamlit_app.py:19-21` imports `load_run`, `run_gate`, `get_synthesizer` from the core directly — an independent presentation over the same core, not a mock. Untracked by React seams (as the plan notes) but honest.
- **Both run endpoints and the compile endpoint keep `compose ≠ execute` at the core and are RBAC-gated** (`intake.py:128`, `pipeline_run.py:176`, `nextflow.py` stateless). The core (`src/bayleaf/`) shells out nowhere.
- **Repair/Archivist modals do not fabricate linkage** — their inert CTAs are paired with honest copy; the defect is stale badges + missing write bridges, not a false success claim.
