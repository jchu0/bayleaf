## Specialist 8 — Demo-readiness & status-truthfulness auditor → `audit/demo-readiness.md`

**Run mode:** Fable 5, code-only/headless (route + `file:line` + quoted string; no browser this pass). Every finding was re-opened and the quoted string confirmed. Guardrails G1–G7 honored; nothing was turned "live." Ranked Blockers → High → Medium → Low.

**Recording golden path under test (from `run-of-show.md`):** Run Overview `/` → Decision card `mock_run_01`/S4 → Ask triage → live AI flip (terminal) → reproduce-from-log (terminal) → Slack (terminal) → Provenance + Review queue. Stub is the recording default; live intake/Nextflow is OFF-recording; `data/mock_run_01` is pre-gated.

---

### DEMO-01 · "Gate online" is a hardcoded always-green dot on the hero Runs screen — no health poll · **High** · Confirmed · missing-user-facing-state (Operate / Run Overview hero)

- **Evidence:** `frontend/src/screens/RunOverview.tsx:136-137` renders `<span className="h-[7px] w-[7px] rounded-full bg-proceed shadow-[0_0_0_3px_var(--color-proceed-bg)]" />` + literal `Gate online`. The header comment `RunOverview.tsx:128-129` even calls it "the **live** 'Gate online' status (an operational health indicator, not flavor prose)" — a false "live" claim. The component fetches only `api.runsPage()` (`RunOverview.tsx:214`) and never calls `api.health()`. The real poll exists and is used elsewhere: `frontend/src/components/TopBar.tsx:13-36` (`useApiHealth()` → `api.health()`, on mount + every 20s; `api.health` at `frontend/src/api.ts:204`).
- **Reproduction:** Load `/`. The header shows a green "Gate online" dot. Now stop the backend and reload: `RunOverview.tsx:296` renders `RunsHeader` unconditionally, so the green "Gate online" dot stays green **while** `RunsError` (`RunOverview.tsx:146-168`, "The artifact store returned `503` reading `/runs`") renders directly below it — a self-contradicting hero screen.
- **Expected:** The dot reflects real reachability (green only when `api.health` says ok), or the label is demoted to a non-health caption.
- **Actual:** Always green regardless of backend state; contradicts the page's own 503 error box.
- **Root cause:** Static markup left in `RunsHeader` when the real health pill was implemented only in `TopBar`.
- **Min fix:** Reuse the `TopBar` `useApiHealth()` hook (or lift it) and drive the dot/label from it; or relabel to a static non-status caption. `<30 min`.
- **Demo-critical:** Y (Run Overview is Step 1 of the recording). **Synthesis P0 candidate.**
- **Risk of fixing now:** Low (isolated, read-only health call already exists).
- **Regression test:** RTL render of `RunOverview` with `api.health` mocked to `{status:'down'}` asserts the header dot is not `bg-proceed` and label ≠ "Gate online".

---

### DEMO-02 · Demo script instructs pointing at an "ADVISORY · STUB" badge that the shipped triage UI does not render · **Medium** · Confirmed · design-inconsistency (Operate / Agent triage — recording Step 3)

- **Evidence:** `docs/demo/run-of-show.md:54` — "…note the `ADVISORY · STUB` badge. It never sets the verdict." and `docs/demo/demo_plan.md:39` — "`ADVISORY · STUB` badge." Shipped UI: `frontend/src/components/AgentSubjectCard.tsx:43-46` renders a plain `Advisory` badge + `{sourceLabel}` text; `frontend/src/screens/AgentTriage.tsx:96` sets `sourceLabel = 'Rule-derived triage (offline)'` in stub mode (and `Claude · ${model}` when armed). `grep -rniE "advisory.{0,4}stub|>stub<" frontend/src` → **no matches** (the literal "STUB" badge does not exist). Design note `docs/quality/risks.md:160` shows the intended-but-drifted label "the UI badges output `ADVISORY · STUB/CLAUDE`".
- **Reproduction:** Follow Step 3 on `/runs/mock_run_01/agent`; presenter looks for an "ADVISORY · STUB" chip and finds "Advisory" + "Rule-derived triage (offline)".
- **Expected:** Narration matches the on-screen chip.
- **Actual:** Narration names a badge string that isn't shipped.
- **Min fix:** Update both doc lines to "note the **Advisory** badge and the **Rule-derived triage (offline)** source label"; no code change needed. `<30 min`.
- **Demo-critical:** Y (hero beat). **Risk:** none (docs only). **Regression test:** doc-lint asserting demo narration strings exist as literals in `frontend/src`.

---

### DEMO-03 · Demo docs are stale (dated 2026-07-08): describe ~6 screens; app ships ~14 routes · **Medium** · Confirmed · design-inconsistency (whole recording)

- **Evidence:** `docs/demo/run-of-show.md:6` and `docs/demo/demo_plan.md:6` both "**Last updated** 2026-07-08 (MST)". `demo_plan.md:28-45` walkthrough enumerates 6 screens (Run overview, Decision cards, Ask triage, Provenance, Review queue, Monitoring+Settings). Shipped routes `frontend/src/App.tsx:57-80`: `/login`, `/`, `/accession`, `/submit`, `/inbox`, `/runs/:id`, `/runs/:id/provenance`, `/runs/:id/intake`, `/runs/:id/agent`, `/settings`, `/admin`, `/monitoring`, `/queue`, `/builder`. Accession, Submit, Inbox, Admin, Intake gate, Builder, and Nextflow export are undocumented. (`run-of-show.md:12` also still says "~5-minute" while its own slot is 5:00.)
- **Expected:** Docs scope matches the shipped surface, or explicitly declare the 6-screen recording subset and mark the rest "not on the recording path."
- **Actual:** A viewer/presenter reading the docs cannot reconcile them with the 14-route app.
- **Min fix:** Add a "screens intentionally off the 3–5 min recording" list to both docs and bump the date; do not re-script. `30–90 min`.
- **Demo-critical:** N (off-screen) but presenter-accuracy risk. **Risk:** none.

---

### DEMO-04 · `PipelineRepairModal` & `ArchivistModal` keep a "phase-2" badge though both call real read endpoints (understating) · **Medium** · Confirmed · design-inconsistency (Builder agent modals)

- **Evidence:** `frontend/src/components/BuilderModals.tsx:416` renders `…>phase-2</span>` on `PipelineRepairModal`, which fetches live data via `api.signatureRepair(selected)` (`BuilderModals.tsx:386`) and `api.repairSignatures`. `BuilderModals.tsx:558` renders the same `phase-2` chip on `ArchivistModal`, which fetches `api.archiveIndex()` (`BuilderModals.tsx:530`). Both **write** CTAs are genuinely inert — "Send to review queue" only `navigate('/queue')` + toast (`BuilderModals.tsx:505-509`); "Queue archive" is `onClose` (`BuilderModals.tsx:586-588`) — so the badge conflates a wired read path with an unwired write path.
- **Expected:** Either drop the badge (read path is live) or relabel it to scope only the inert write action (e.g. "routing = phase-2").
- **Actual:** A blanket "phase-2" chip understates that the modal loads real signatures/archive data.
- **Min fix:** Replace the top-level `phase-2` chip with an "advisory · read-only" chip and keep the honest inline footer disclaimers already present (`:498`, `:582`). `<30 min`.
- **Demo-critical:** N (Builder, off the Operate recording). **Risk:** Low.

---

### DEMO-05 · `AuthorToolNodeModal` primary CTA "Review kinds & add to palette" is a no-op button that reads as actionable · **Low** · Confirmed · incomplete-integration (Builder / node-author)

- **Evidence:** `frontend/src/components/BuilderModals.tsx:340-342` — the accent primary button `Review kinds &amp; add to palette` has `onClick={onClose}` only; it registers/surfaces nothing (node-author is core-only, T-046). The modal **is** honestly labelled otherwise: `BuilderModals.tsx:210-211` "roster #5 · phase-2" and footer `:334-335` "it never draws an edge… or auto-adds." Reached from `SettingsModelTier.tsx:366-373` "New agent" → `/builder`, implying agent creation.
- **Expected:** A primary CTA either performs the labelled action or reads as disabled/secondary given the surrounding "phase-2/never auto-adds" copy.
- **Actual:** An accent "add to palette" button that silently closes the modal.
- **Min fix:** Demote to a secondary "Close preview" style or disable it with a "phase-2 — proposals are not yet registerable" tooltip. `<30 min`.
- **Demo-critical:** N. **Risk:** Low.

---

### DEMO-06 · Submit seeds 4 samples + run details in upload mode by default, unlabelled as seeded · **Low** · Confirmed · missing-user-facing-state (Operate / Submit — off recording)

- **Evidence:** `frontend/src/screens/Submit.tsx:205` `useState<SampleRow[]>(SEED_SAMPLES)` (4 GIAB rows, `Submit.tsx:50-55`); `Submit.tsx:226-227` `loaded = method==='upload' || imported` and `count = loaded ? samples.length : 0` → in the default upload mode, `count = 4` on first paint; `Submit.tsx:204` `meta = SEED_META` prefills Run details `RUN-2026-07-09-A`. The samples header `Submit.tsx:742` renders "Samples · {count}" (= 4) and Run details `Submit.tsx:716-736` render prefilled, with **no** "seeded/demo" label. **Honest counterpart (passes):** the green "Parsed N samples" chip `Submit.tsx:549-572` is gated on `uploadName`, so it does **not** fabricate a parse before a real drop; the metadata chip `Submit.tsx:210` is labelled "seeded demo metadata · 4 subjects".
- **Expected:** Pre-populated demo rows carry a visible "seeded demo — replace by uploading" marker (as the metadata chip already does), so "Samples · 4" can't read as parsed/imported data.
- **Actual:** Table + run details look populated with real data before any upload.
- **Min fix:** Add a "seeded demo data" chip to the Samples header when `!uploadName && !imported`. `<30 min`.
- **Demo-critical:** N (Submit is off the recording). **Risk:** Low.

---

### DEMO-07 · Submit "Save draft" button is silently inert (no handler) · **Low** · Confirmed · incomplete-integration (Operate / Submit — off recording)

- **Evidence:** `frontend/src/screens/Submit.tsx:1197-1202` — `<button type="button" className="…">Save draft</button>` has no `onClick`; clicking produces no toast, no persist, no state change. It sits beside the real `Submit to pipeline` button, so it reads as live.
- **Expected:** Either wire a draft persist, or label/disable it as a phase-2 seam (the app's own idiom — cf. the honest phase-2 toasts in Inbox/Admin).
- **Actual:** Dead primary-adjacent control.
- **Min fix:** Add an info toast "Draft save is a phase-2 seam (not persisted)" or `disabled` + tooltip. `<30 min`.
- **Demo-critical:** N. **Risk:** Low.

---

### DEMO-08 · Submit BaseSpace panel shows a fabricated "Connected as lab-ops@giab" and imports seeded samples with no mock label · **Low** · Confirmed · missing-user-facing-state (Operate / Submit — off recording)

- **Evidence:** `frontend/src/screens/Submit.tsx:400-402` `connectBase()` sets `baseConnected` on any non-empty token; `Submit.tsx:652-655` then renders a green dot + "Connected as `lab-ops@giab`"; `Submit.tsx:408-415` `importRun()` reveals `SEED_SAMPLES` (comment: "demo stand-in. No execution"). The panel itself carries no visible "demo/mock" label (unlike the metadata chip). Corroborates journeys/T-057.
- **Expected:** A visible "demo mock — no real BaseSpace call" label on the panel so the fake connection/import can't read as a live integration.
- **Actual:** Reads like a real OAuth connection + run import.
- **Min fix:** Add a "Demo mock · not a live BaseSpace connection" banner to the BaseSpace panel. `<30 min`.
- **Demo-critical:** N. **Risk:** Low.

---

## Honest surfaces (verified true — do not touch)

- **TopBar health pill** (`TopBar.tsx:13-36`, `HEALTH_META` `:32-36`): real `api.health` poll every 20s, Ready/Offline reflect actual reachability. This is the correct pattern DEMO-01 should adopt.
- **Streamlit fallback synthesizer status** (`app/streamlit_app.py:119-125`): honestly shows "🤖 Live Claude synthesis is ON" vs "📋 Offline rule-based narration (stub)" with a caption on how to enable — the always-green rung-3 fallback is truthful.
- **Monitoring determinism** (`Monitoring.tsx:343-357`): every `Bar`/`Line` sets `isAnimationActive={false}` → no reflow/jitter on a recording; the Median-review KPI is honest — value `'—'` with hint "Review-latency telemetry not yet captured by the backend" (`Monitoring.tsx:279`). (T-072 `runs[]` scope is uncapped and commented `:199,:239`; fine for the fixed served fixtures, a P3 payload-size backlog item.)
- **Phase-2 seams keep honest, present-tense-safe labels:** Login password-reset toast "Password reset is a production seam…" (`Login.tsx:109`), CAPTCHA labelled "demo" (`Login.tsx:144`); Admin reset "A password-reset link **would be** emailed… (no live mail here)" (`Admin.tsx:316`), role update "client-mock — dev auth shim" (`Admin.tsx:322`); Inbox calendar connector "isn't wired in this build (a labelled seam)" (`Inbox.tsx:1023`), Notify "phase-2 seam (not yet wired…)" (`Inbox.tsx:163`), Mentions "demo seam — stored locally, not a live ping" (`Inbox.tsx:651`). No false past-tense success toasts.
- **No "confidence" for heuristics (G4):** per-citation scores render `${…}% (heuristic)` (`BuilderModals.tsx:485`); Monitoring auto-proceed labelled "Throughput heuristic — … Not a calibrated confidence" (`Monitoring.tsx:276`); `types.ts:585,329` reinforce. No confidence meter found on any surface.
- **Verdict/advice separation (G1):** triage source toggle "only reflects/requests a *narration* source — never … the verdict/confidence" (`AgentSourceToggle.tsx:1-4`); AgentSubjectCard footer "The verdict is set by the rule engine, not this note" (`AgentSubjectCard.tsx:107`); SettingsModelTier confirm body "Demo seam — nothing here persists to the backend yet" (`SettingsModelTier.tsx:166`) and toast "Updated N agents" (not "applied/armed").
- **AuthorToolNodeModal label** is prominent and honest ("roster #5 · phase-2", `BuilderModals.tsx:210-211`) — only its primary button (DEMO-05) reads too strong.

---

## Required deliverables

**(a) Deterministic demo setup checklist (pre-clock):**
1. `uv sync --all-extras --extra slack`.
2. Backend **stub default**: `uv run uvicorn api.main:app --port 8010` (no `PIPEGUARD_*_AGENT` flags).
3. Frontend: `npm --prefix frontend run dev`; open the Vite URL.
4. `rm -f run.events.jsonl pg.sqlite` (append-only ledger — a stale file doubles Step-5 counts, `run-of-show.md:36-38`).
5. Sanity gate (green-room check): `uv run python -c "from pipeguard import run_gate_from_dir; _, c = run_gate_from_dir('data/mock_run_01'); print([(x.sample_id, x.verdict.value) for x in c])"` → `[('S4','escalate'), ('S5','hold'), ('S1','proceed'), ('S2','proceed'), ('S3','proceed')]`.
6. Pre-type (don't run) the armed AI + Slack one-liners so each ★ beat is one Enter.
7. Arm Streamlit fallback: `uv run streamlit run app/streamlit_app.py`.
8. **Do NOT** navigate to Submit/Builder/BaseSpace on camera (unlabelled-seed surfaces DEMO-06/07/08); **do NOT** run live Nextflow intake on the clock.

**(b) Prompts + fixtures + expected outputs:**
- Fixture: `data/mock_run_01` (5 samples). Run Overview `/` → point at `mock_run_01` "N need attention".
- `mock_run_01`/S4 Decision card → verdict **escalate**; cited i5 `AGGCGAAG` ≠ declared `GGCTCTGA` + missing `subject_id`.
- Ask triage on S4 → Advisory note; **say "Advisory / Rule-derived triage (offline)"**, not "ADVISORY·STUB" (DEMO-02).
- Live flip: `PIPEGUARD_TRIAGE_AGENT=claude PIPEGUARD_SYNTHESIZER=claude uv run uvicorn api.main:app --port 8010` → same panel, Claude prose, citations/verdict unchanged; degrades to stub on refusal.
- Reproduce: `make emit-ledger && make rebuild-db` → `… 16 event(s) -> 1 run(s), 5 decision card(s).`
- Slack: `PIPEGUARD_NOTIFIER=slack PIPEGUARD_SLACK_LIVE=1 uv run python -m pipeguard.notify data/mock_run_01` (or the $0 no-`_LIVE` variant that sends nothing).

**(c) Fallback footage plan:** rung 1 = each step's row Fallback; rung 2 = **stay on stub** (default, $0); rung 3 = **Streamlit** (`streamlit run app/streamlit_app.py`, `streamlit_app.py:119-125` shows an honest synthesizer status, always green); rung 4 = recorded walkthrough.

**(d) Features to HIDE / keep off-camera:** Submit BaseSpace panel (DEMO-08) + seeded Submit table (DEMO-06) + inert "Save draft" (DEMO-07); Builder `AuthorToolNodeModal` no-op CTA (DEMO-05); Builder Repair/Archivist "phase-2" chips (DEMO-04); live Nextflow intake (timing/conda-dependent); any surface that could expose a green "Gate online" while the backend is flaky (DEMO-01 — keep the backend healthy for the whole take).

**(e) Golden-path regression test spec (one):** extend `tests/test_gate.py` (EVAL-001, `data/mock_run_01`) with `test_mock_run_01_pinned_verdicts`: `run_gate_from_dir('data/mock_run_01')` returns per-sample verdicts exactly `{S1:proceed, S2:proceed, S3:proceed, S4:escalate, S5:hold}`, S4 carries a barcode-mismatch finding citing observed `AGGCGAAG` vs declared `GGCTCTGA`, and `DecisionCard.confidence is None` for every card (G4). This is the deterministic green-room gate for the recording.
