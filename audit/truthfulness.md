## Additional auditor 10 — Truthfulness auditor → `audit/truthfulness.md`

**Run mode:** Fable 5, code-only / headless (route + `file:line` + quoted string; no browser this pass, per the resolved 2026-07-11 evidence mode).
**Scope:** every status string / badge / toast / progress indicator / agent-output label vs. the state the system has actually reached. Guardrails G1 (rules decide) and G4 (heuristics ≠ confidence) treated as the spine.
**Method:** each finding below was re-opened and the quoted string re-confirmed at the cited line before inclusion. Grep-proven absences quote the empty result.

Ranked Blockers first.

---

### T-TRU-01 · "Gate online" is a hardcoded always-green dot with no health poll (flagship)
- **Severity:** Blocker · **Confidence:** Confirmed · **Category:** missing user-facing state
- **Area / journey:** Operate — Runs list hero screen (`/`, `RunOverview`)
- **Evidence:** `frontend/src/screens/RunOverview.tsx:136-137` — `<span className="h-[7px] w-[7px] rounded-full bg-proceed shadow-[0_0_0_3px_var(--color-proceed-bg)]" />` immediately followed by the literal `Gate online`. The dot color is the static token `bg-proceed`; there is no state, no `api.health`, no poll. `RunOverview.tsx:4` imports `api` but never calls `api.health`. Comment `:127-129` states this block "renders during loading/error too, so the shell stays stable" — i.e. it renders green even when the run index request fails.
- **Reproduction:** Load `/` with the backend stopped. `TopBar` (`TopBar.tsx:13-36`, real 20 s `api.health()` poll) correctly flips its pill to red "Offline"; the `RunOverview` header still shows a green dot + "Gate online" on the same screen.
- **Expected:** The status reflects real backend/gate reachability, or is relabeled to something it can truthfully assert.
- **Actual:** Always-green, backend-independent — a hero-screen indicator that lies during any outage, exactly while the app's other health surface says Offline.
- **Root cause:** Static markup left in place; never bound to the health seam that already exists in `TopBar`.
- **Minimum viable fix:** Reuse `TopBar`'s `useApiHealth()` hook and drive the dot color + label from it (green "Gate online" only when `status==='ok'`); otherwise amber "Gate offline". Alternative <5-min fix: relabel to a non-live string.
- **Larger fix:** A shared `HealthPill` primitive consumed by both surfaces so they can never diverge.
- **Demo-critical:** Y · **Risk of fixing now:** Very low (additive read-only hook) · **Regression test:** Component test mounting `RunsHeader` with `api.health` mocked to reject → asserts the dot is not `bg-proceed` and the label is not "Gate online".

---

### T-TRU-02 · Submit shows a fabricated "Samples · 4" (from `SEED_SAMPLES`) before any samplesheet is dropped
- **Severity:** High · **Confidence:** Probable (design-intended scaffold, but violates the demo-truthfulness requirement) · **Category:** design inconsistency
- **Area / journey:** Operate — Submit (`/submit`), golden-path hop 1
- **Evidence:** `frontend/src/screens/Submit.tsx:205` seeds state `useState<SampleRow[]>(SEED_SAMPLES)` (4 rows: HG002/HG003/HG004/NA12878, `:50-55`). `:226` `const loaded = method === 'upload' || imported` — always true in the default `upload` method. `:227` `const count = loaded ? samples.length : 0`. `:742` renders `Samples · {count}` and `:805` only shows the empty-state when `count === 0` (BaseSpace-only). `uploadName` is still `null` (`:208`) — no file parsed. The paired metadata *is* labeled seeded (`:210` `'seeded demo metadata · 4 subjects'`), but the samplesheet count and full editable table are not.
- **Reproduction:** Navigate to `/submit` fresh (upload method). Header reads "Samples · 4" with a populated barcode table, no file dropped.
- **Expected (Demo-readiness §10):** count = 0 before any drop; only the "Parsed N samples" toast (`:353`) after a real parse; `SEED_SAMPLES` must not leak a pre-filled parsed count.
- **Actual:** A fabricated count of 4 seeded samples is presented as if parsed, indistinguishable from real intake data on the hero submit screen.
- **Root cause:** Upload mode initializes `samples` to `SEED_SAMPLES` and treats "upload" as unconditionally `loaded`.
- **Minimum viable fix:** Gate `loaded`/`count` on a real parse having occurred (e.g. `uploadName != null`), or tag the seeded rows with a visible "seeded demo — replace by uploading a samplesheet" banner mirroring the metadata label at `:210`.
- **Demo-critical:** Y · **Risk of fixing now:** Low–medium (touches Submit init state a maintainer may be editing) · **Regression test:** Render `<Submit>` in upload mode with no upload → assert the sample count reads 0 (or the seeded rows carry the seeded label).

---

### T-TRU-03 · Intake "Admit (override)" note claims "recorded on the run" but is local-only React state
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** confirmed defect
- **Area / journey:** Operate — Intake gate (`/runs/:id/intake`, `Intake.tsx`)
- **Evidence:** `frontend/src/screens/Intake.tsx:352` — `'Admitted below the yield target by manual override — recorded on the run.'`. The override is `useState<Record<string, boolean>>({})` (`:65`), toggled only by `setOverrides((m) => ({ ...m, [id]: !m[id] }))` (`:403`). No POST, no localStorage, no ledger write; the file comment (`:250-251`) confirms it "never sets or overturns a gate verdict," and journeys §4 confirms it is never persisted across refetch.
- **Reproduction:** Click "Admit (override)" on a sparse sample → row reads "…recorded on the run." Refresh → the override is gone.
- **Expected:** Copy honestly scopes the annotation to the session, matching the labeled seams elsewhere.
- **Actual:** "recorded on the run" implies durable, server-side provenance that does not exist.
- **Root cause:** Copy written as if the annotation persisted; the state is ephemeral component state.
- **Minimum viable fix:** Change the string to "…recorded for this session (not persisted)" or wire it to the same client-side audit courier Submit uses.
- **Demo-critical:** N · **Risk of fixing now:** Very low (string change) · **Regression test:** Snapshot the override note copy so it can't silently re-assert persistence.

---

### T-TRU-04 · Pipeline-repair & Archivist modals render a "phase-2" badge though wired to real read endpoints (understatement)
- **Severity:** Medium · **Confidence:** Probable (badge is defensible as labeling the still-inert *write* path) · **Category:** design inconsistency
- **Area / journey:** Builder — advisory agent modals
- **Evidence:** `frontend/src/components/BuilderModals.tsx:416` (PipelineRepairModal) and `:558` (ArchivistModal) both render `>phase-2</span>`. Yet PipelineRepairModal fetches live data via `api.monitoring(...)` (`:364`) + `api.signatureRepair(selected)` (`:386`), and ArchivistModal via `api.archiveIndex()` (`:530`). These map to real backend routes: `api/main.py:1282` `GET /api/monitoring`, `:1440` `GET /api/monitoring/signatures/{signature}/repair`, `:1499` `GET /api/archive/index`.
- **Expected (Demo-readiness §2):** Drop/relabel the badge so a wired read modal isn't understated; if kept, scope it to the inert write action, not the whole modal.
- **Actual:** A modal that fetches and renders real agent output is stamped "phase-2," understating shipped capability during a demo.
- **Root cause:** Badge left over from when these modals were static mocks; not updated when read endpoints landed.
- **Minimum viable fix:** Replace the modal-level "phase-2" badge with "advisory · read-only" (or move it to sit beside the inert CTA only).
- **Demo-critical:** N · **Risk of fixing now:** Very low · **Regression test:** N/A (label).

---

### T-TRU-05 · "Queue archive" button is inert (`onClose`) while the footer claims "the archive is queued for a human to confirm"
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** incomplete integration
- **Area / journey:** Builder — ArchivistModal
- **Evidence:** `frontend/src/components/BuilderModals.tsx:586-587` — `<button onClick={onClose} …>Queue archive</button>`. The button does nothing but close: no toast, no state change, no endpoint (no write route exists; integration §6). The footer at `:582` asserts `Advisory — the archive is queued for a human to confirm; nothing is moved automatically.` Contrast the sibling "Send to review queue" (`:502-514`) which at least `navigate('/queue')`s and fires an honest toast explaining nothing was routed.
- **Reproduction:** Open Archivist modal → click "Queue archive" → modal closes silently; nothing is queued, but the footer told the user it was.
- **Expected:** Either the button performs/queues something and surfaces a real outcome, or the label + footer say it is a preview/seam.
- **Actual:** Primary-looking action + footer imply a persisted queue write that is a pure `onClose`.
- **Minimum viable fix:** Relabel to "Close" (or "Preview manifest") and change the footer to not assert "queued," or add an honest toast like the repair modal's.
- **Demo-critical:** N · **Risk of fixing now:** Very low · **Regression test:** Assert the Archivist footer copy does not assert a completed queue action while the CTA is `onClose`.

---

### T-TRU-06 · SettingsModelTier "Live" status badge flips green on a local-only Save, not wired to `PIPEGUARD_*_MODEL`
- **Severity:** Medium · **Confidence:** Probable · **Category:** incomplete integration
- **Area / journey:** Configure — Settings, Agents & model tiering
- **Evidence:** `frontend/src/components/SettingsModelTier.tsx:487-495` renders a green `border-proceed-bd bg-proceed-bg text-proceed-fg … {row.live ? 'Live' : 'Stub · $0'}` badge driven purely by local `rows` state set in `applyPanel` (`:149-175`), which ends in `toast('Updated N agents', 'success')` — no PATCH. The file comment (`:16-17`) states "nothing here is wired to the real PIPEGUARD_*_MODEL env vars yet." The only honesty disclaimer ("nothing here persists to the backend yet") lives inside the turn-live confirm dialog body (`:166`) — the persistent roster badge just reads green "Live."
- **Expected (Demo-readiness §4 / T-045):** Flipping the roster toggle must never imply an agent is armed; the "Live" state should carry a persistent "local demo, not applied" indicator.
- **Actual:** After Save, a roster row shows a green "Live" badge with no on-badge indication that it changed nothing on the backend.
- **Minimum viable fix:** Suffix the Live badge with "(local)" or add a persistent card-level "changes are local demo state — not applied to the backend" note.
- **Demo-critical:** N (Settings is off the core recording path; hide/label per synthesis P2) · **Risk of fixing now:** Very low · **Regression test:** Assert the roster surfaces a not-persisted indicator whenever a row is "Live."

---

### T-TRU-07 · AuthorToolNodeModal primary CTA "Review kinds & add to palette" is a no-op (`onClose`) — nothing is registered
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** incomplete integration
- **Area / journey:** Builder — Author a tool node (node-authoring)
- **Evidence:** `frontend/src/components/BuilderModals.tsx:340-341` — the accent PRIMARY button `<button onClick={onClose} …>Review kinds &amp; add to palette</button>` closes the modal and nothing else. The node-author capability is entirely unwired: `grep -rn "node_author\|propose_node" api/` → empty; `grep -rn "propose_node\|node_author\|NodeProposal" frontend/src` → only the Settings roster row (`SettingsModelTier.tsx:53`, `wired: false, phase2: true`). Mitigations present: the header badge "roster #5 · phase-2" (`:210-211`) and the footer "it never draws an edge, places a node on the gate, or auto-adds" (`:333-335`).
- **Expected:** A primary button reading "add to palette" either adds to the palette or is clearly non-committal.
- **Actual:** The strongest-styled CTA asserts an action ("add to palette") the static mock cannot perform; only the badge + fine-print footer disclose it.
- **Minimum viable fix:** Relabel the primary to "Close" / "Discard preview" (the modal already has a "Discard" secondary), or demote it from primary styling.
- **Demo-critical:** N (hide/label per P2) · **Risk of fixing now:** Very low · **Regression test:** N/A (label).

---

### T-TRU-08 · Metrics-expansion roster row advertises `PIPEGUARD_METRICS_AGENT`, an env var with no backend module and absent from `.env.example`
- **Severity:** Low · **Confidence:** Confirmed · **Category:** incomplete integration
- **Area / journey:** Configure — Settings, Available agents
- **Evidence:** `frontend/src/components/SettingsModelTier.tsx:54` — `{ key: 'metrics_expand', … env: 'PIPEGUARD_METRICS_AGENT', wired: false, phase2: true }`, rendered as an "Add"-able row in the Available section (`:525-547`) showing the env var in mono. But `grep -rln "PIPEGUARD_METRICS_AGENT\|metrics_expand\|metrics_agent" api/ src/` → empty (no backend module), and `.env.example` has no `PIPEGUARD_METRICS_AGENT` line (its agent selectors stop at `PIPEGUARD_NODE_AUTHOR_AGENT`).
- **Expected:** A roster row that names a real env selector, or is visibly marked "design-only (no backend)."
- **Actual:** An addable agent row advertises a config knob that does not exist anywhere in the backend or `.env.example`.
- **Minimum viable fix:** Mark the row "design-only" (distinct from the wired-but-stub node-author), or remove the env-var mono until a module exists.
- **Demo-critical:** N · **Risk of fixing now:** Very low · **Regression test:** A test asserting every roster `env` that isn't design-only appears in `.env.example`.

---

## Honest surfaces (verified truthful — clean signal)

These were inspected and found to represent their state accurately; no finding warranted.

- **TopBar health pill** — real 20 s poll of `api.health()` with honest checking/ready/offline states (`TopBar.tsx:13-36`). The correct pattern T-TRU-01 should adopt.
- **Agent-triage source label** — `Claude · {model}` only when a served note carries a model; "Live synthesis unavailable — rule-derived fallback" when the operator requested live but the agent is unarmed; "Rule-derived triage (offline)" otherwise (`AgentTriage.tsx:85-96`), with a matching amber banner (`:118-123`). Never relabels model prose as deterministic, never sets a verdict (`AgentSourceToggle.tsx:1-4`).
- **Heuristics ≠ confidence (G4)** — per-citation scores render as `N% (heuristic)` (`BuilderModals.tsx:485`); Monitoring's `auto_proceed_pct` is labeled "Throughput heuristic … Not a calibrated confidence" (`Monitoring.tsx:276`, `types.ts:329`). No confidence meter anywhere; `DecisionCard.confidence` (`types.ts:67`) is never rendered by any consumer (grep for `.confidence` in `frontend/src` → no render site).
- **Verdict read-only (G1)** — `RunDetail.tsx` only reads `card.verdict` (`:152,282-284,450`); no editable verdict control exists.
- **Error truthfulness** — `httpError()` surfaces the real status + FastAPI `detail` (`api.ts:65-82`), so toasts show real 403/409/422/503 rather than a fabricated success.
- **Login / Admin phase-2 disclaimers** — password reset toasts "would be emailed … production seam (no live mail here)" (`Admin.tsx:316`, `Login.tsx:109`); CAPTCHA "CAPTCHA · demo" (`Login.tsx:144`); role update "client-mock — dev auth shim" (`Admin.tsx:322`); Act-as writes a real audit entry (`Admin.tsx:325-332`).
- **Inbox connectors / mentions** — calendar connect toasts "isn't wired in this build (a labelled seam)" (`Inbox.tsx:1023`); mentions "stored locally, not a live ping" (`:651`); notify cadence "Notify · phase-2 seam (not yet wired to a live ping)" (`:163`).
- **Provenance reserved-fields chip** — "params hash · execution trace — phase 2" with tooltip "Reserved for phase 2 — … not captured in this build (provenance.py:50-56)" (`Provenance.tsx:216-218`).
- **BuilderConsole sarek YAML** — labeled "sarek profile is illustrative / target-state — not yet wired end-to-end" (`BuilderConsole.tsx:419`) and "Emit writes the config only — no tool runs" (`:427`).
- **Submit "Parsed N samples" toast** — fires only after a real parse with the real count (`Submit.tsx:353`); paired metadata labeled "seeded demo metadata · 4 subjects" (`:210`). (The un-labeled *samplesheet* count is T-TRU-02.)

## Summary
Nine advisory surfaces label their state honestly; **one Blocker** (T-TRU-01, the flagship hardcoded "Gate online") and **one High** (T-TRU-02, fabricated Submit sample count) are the demo-critical truthfulness defects on hero screens. The remaining Mediums are inert-CTA / understated-badge / local-only-persistence copy issues, all low-risk single-string or single-hook fixes that preserve the golden path.
