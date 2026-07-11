# PipeGuard — Release-Hardening Audit · SYNTHESIS

**Verdict handling.** 0 findings were REFUTED (nothing dropped) and 0 were UNCERTAIN. Every item is either **[CONFIRMED]** (verifier independently reproduced it) or **[UNVERIFIED]** (verifier did not re-check — it rests on the specialist's own confidence, noted inline; treated as Probable-at-best where confidence < Confirmed).
**Dedup.** 60 raw findings → 26 consolidated items. The big overlaps — "Gate online" (×3), MonitoringSignature drift (×2), node-author no-op CTA (×5), phase-2 badge understatement (×5), Archivist inert CTA (×4), SettingsModelTier (×2), Share-not-in-Admin-feed (×3), poll-hangs/non-durable-jobs (×3) — are merged, each resolved by a single fix.
**Discipline.** Track-A mandate: do **not** add scope; relabel/reword/wire the *minimum*. No verdict-setting agent (G1), stub-default (G2), read-only advice. Where a fix risks the working golden path more than it helps before submission, it is demoted to P2/P3.

---

## P0 — MUST-FIX BEFORE RECORDING

### P0-1 · "Gate online" is a hardcoded always-green dot on the Runs hero — lies during an outage
- **Where:** `frontend/src/screens/RunOverview.tsx:135-138` (static `bg-proceed` dot + literal `Gate online`), comment `:127-129` calls it the "live" status; real poll is `frontend/src/components/TopBar.tsx:13-36` (`useApiHealth`, 20s interval, offline→`bg-escalate`/`Offline`). Both render on `/`.
- **Why P0:** This is the plan's canonical P0 — a hero-screen status indicator that reads green while the backend is down, contradicting both TopBar's real "Offline" pill and the page's own `503` RunsError box directly beneath it. First recording screen.
- **Fix:** Drive the dot color + label from `useApiHealth()` (green only when `status==='ok'`), or relabel the span to a static, non-status caption. Isolated presentational change.
- **Effort:** `<30min` · **Risk:** very low · **Raised by:** S1 `UIUX-01`, S8 `DEMO-01`, S10 `T-TRU-01` · **Verdict: [CONFIRMED] ×3 + independently reproduced.**

*(No other finding blocks the recording: SCI-01's 100× metric bug is latent on the shipped fixtures, the MonitoringSignature drift renders correctly, and the Builder/Settings phase-2 seams are honestly badged. Everything else is P1 or lower.)*

---

## P1 — FIX BEFORE SUBMISSION IF POSSIBLE

### P1-1 · Demo script points at an "ADVISORY · STUB" badge the shipped triage UI never renders
- **Where:** `docs/demo/run-of-show.md:54` + `docs/demo/demo_plan.md:39` say "note the `ADVISORY · STUB` badge"; shipped UI renders `Advisory` + `Rule-derived triage (offline)` (`AgentSubjectCard.tsx:43-46`, `AgentTriage.tsx:96`). String `ADVISORY · STUB` exists nowhere in `frontend/src`.
- **Why P1:** Directly on the recording — the presenter's narration cue (Step 3) names an on-screen badge that isn't there. Doc-only, zero code risk; fix before you record so narration matches the screen.
- **Fix:** Update both doc lines to "the **Advisory** badge and the **Rule-derived triage (offline)** source label."
- **Effort:** `<30min` · **Raised by:** S8 `DEMO-02` · **Verdict: [UNVERIFIED] — specialist-Confirmed (grep-backed), not independently re-run.** Demo-critical.

### P1-2 · Intake "Admit (override)" note claims "recorded on the run" but is ephemeral client-only state
- **Where:** `frontend/src/screens/Intake.tsx:352` copy `Admitted below the yield target by manual override — recorded on the run.`; `override` is `useState` at `:65`, toggled only by `setOverrides` `:401-404` — no POST/localStorage/ledger. In-file ADR comment `:250-251` confirms annotation-only.
- **Why P1:** Intake gate (`/runs/:id/intake`) is on the recorded golden path; the copy asserts durable per-run provenance that does not exist and vanishes on reload — a truthfulness defect on a hero surface. Copy-only, zero risk.
- **Fix:** Reword to "…recorded locally this session (not persisted)", matching Submit's "held client-side" idiom.
- **Effort:** `<30min` · **Raised by:** S3 `J1`, S10 `T-TRU-03` · **Verdict: [CONFIRMED] (J1 reproduced) + corroborated.**

### P1-3 · Submit fabricates "Samples · 4" from SEED_SAMPLES before any file is dropped
- **Where:** `frontend/src/screens/Submit.tsx:205` `useState(SEED_SAMPLES)` (4 rows `:50-55`); `:226` `loaded = method==='upload'||imported` (true by default); `:227` `count = loaded ? samples.length : 0`; `:742` renders `Samples · {count}`. Metadata chip is labeled "seeded" (`:210`) but the samplesheet count/table is not.
- **Why P1:** Seeded scaffold is presented identically to real parsed data on the Submit hero. Live intake is off the recording default, but a judge who opens `/submit` sees a fabricated parsed count. Verifier reproduced it and upgraded confidence.
- **Fix:** Gate `count` on a real parse (`uploadName != null`), or tag the Samples header with a visible "seeded demo — replace by uploading" chip like the metadata label already carries.
- **Effort:** `<30min` (guard) / `30-90min` (labeled banner) · **Risk:** low-medium (touches Submit init state a maintainer may be editing) · **Raised by:** S10 `T-TRU-02`, S8 `DEMO-06` · **Verdict: [CONFIRMED] (verifier reproduced; specialist confidence upgraded Probable→Confirmed).**

### P1-4 · Fraction-scaled QC metrics render 100× too small in DecisionCard finding text
- **Where:** `src/pipeguard/rules.py:234` prints `mv.raw_value:g` + `threshold.unit` and `:224` denormalizes the gate to `raw_unit`; for the four fraction-raw metrics (`breadth_20x/breadth_30x/pct_mapped/on_target`, `metrics/mapping.py:~33`) this yields e.g. `0.85%` / gate `≥ 0.9%`. Correct sibling `api/card_readout.py:222-224` shows `85%` / `≥ 90%`.
- **Why P1 (not P0):** Verifier confirms the bug **but** notes it is **latent on the shipped fixtures** — no demo run emits a *failing* fraction metric, and the two hero HOLD/ESCALATE beats don't trip it, so the wrong string won't appear on camera. It becomes visibly, scientifically wrong the moment any live/sparse run fails one of these metrics. Fix before submission.
- **Fix:** Render observed value + thresholds through the same display conversion `card_readout._to_display` uses (normalized_value → threshold.unit), not `raw_value` + denormalize-to-raw_unit.
- **Effort:** `30-90min` · **Risk:** low, **but** `Finding.detail`/`Evidence` feed `content_hash`/signature — regenerate any golden fixtures asserting those strings and re-run the gate tests. · **Raised by:** S7 `SCI-01` · **Verdict: [CONFIRMED] + independently reproduced (latency caveat confirmed).**

### P1-5 · Two client pollers hang on "running" forever after a backend blip (no error path)
- **Where:** Submit intake poll `frontend/src/screens/Submit.tsx:440-452` — `await api.intakeStatus(...)` with only `setTimeout(()=>void poll(),2500)`, no `.catch`; the outer try/catch never sees the recursive rejection. Builder-run poll `frontend/src/components/BuilderModals.tsx:889` `.catch(()=>window.setTimeout(tick,3000))` retries unbounded; status endpoint `api/routers/pipeline_run.py:286-289` 404s with **no disk fallback** (unlike intake `intake.py:163-166`). Root cause: in-memory `_jobs` registries (`intake.py:54`, `pipeline_run.py:99`) are non-durable across restart.
- **Why P1:** On the Builder Run beat (on the recording), any uvicorn restart / network drop leaves the modal spinning "running" indefinitely with no honest failure — an ugly, unrecoverable on-camera stall. Under a clean demo it won't fire, hence P1 not P0.
- **Fix (visible symptom only):** Wrap both poll bodies in try/catch; treat `404`/network error as terminal "lost track of this run — check the Runs list", clear `submitting`, toast the httpError. (Durable job store + Builder-run disk fallback = P3, see P3-13.)
- **Effort:** `30-90min` · **Risk:** low, isolated to two handlers · **Raised by:** S5 `F5-R1`, `F5-R2` (+ root cause `F5-R5`) · **Verdict: [CONFIRMED] ×2 + independently reproduced.**

### P1-6 · Second execution path `POST /api/pipelines/run` runs an unapproved live graph and is undocumented
- **Where:** `api/routers/pipeline_run.py:176` gates on `require_role("reviewer","approver")` only; `:187-189` compiles a fresh client `body.graph` with **no approved-status check**; `:268` `subprocess.run(...)` executes the real Nextflow driver. Router mounted `api/main.py:98`, UI-wired `api.ts:243-244` → `PipelineBuilder.tsx:1376`. `CLAUDE.md` code map (`:225-226`) omits `pipeline_run.py`. The Save→Submit→Approve lifecycle (`pipelines_lifecycle.py:399-445`) governs only profile locators/dry-run/diff.
- **Why P1:** Not a visible break — the Run beat works — but the "two pipeline objects" reality (executable canvas graph vs approvable profile) is undocumented and the Run modal doesn't state that Run executes the current canvas independent of profile approval. Verifier: **doc reconciliation is zero-risk; wiring an approval gate could break the demo Run beat — do NOT do that pre-submission** (that gate is new scope → P3-14).
- **Fix:** Add `pipeline_run.py` to CLAUDE.md's router map with an explicit "unapproved live graphs are runnable (intentional demo affordance)" note; add one line to the Run modal stating Run executes the current canvas graph.
- **Effort:** `<30min` (doc) + `<30min` (modal label) · **Risk:** doc-only is zero · **Raised by:** S4 `F-INT-02` (Y-demo-critical), S3 `J7` · **Verdict: [CONFIRMED] (F-INT-02 reproduced) + corroborated (J7 UNVERIFIED, specialist-Confirmed).**

---

## P2 — HIDE OR DOCUMENT (fine outside the demo when clearly labelled)

### P2-1 · One relabel clears the whole node-author "add to palette" no-op cluster
- **Where:** `frontend/src/components/BuilderModals.tsx:340-342` primary CTA `Review kinds & add to palette` has `onClick={onClose}` — registers nothing; static mock `:186-345`, honestly badged `roster #5 · phase-2` (`:210-211`) and "never auto-adds" (`:333-335`). No transport: `grep node_author|propose_node api/` and `frontend/src` = empty (core-only agent `src/pipeguard/node_author/agent.py`).
- **Fix:** Relabel the primary to a non-actionable "Close (phase-2 preview)" / demote from accent styling. Modal is off the recording and already phase-2 badged → document + relabel, do not build.
- **Effort:** `<30min` · **Raised by:** S3 `J2`, S4 `F-INT-01` (Y-demo-critical), S8 `DEMO-05`, S10 `T-TRU-07`, (author-half of S1 `UIUX-07`) · **Verdict: [CONFIRMED] (J2 reproduced) + 4 corroborating (UNVERIFIED, specialist-Confirmed).**

### P2-2 · Archivist "Queue archive" is inert while footer claims the archive "is queued"
- **Where:** `frontend/src/components/BuilderModals.tsx:586-588` `Queue archive` → `onClick={onClose}`; footer `:582` asserts "the archive is queued for a human to confirm; nothing is moved automatically." No write route (only `GET /api/archive/index`, read-wired at `:529-530`).
- **Fix:** Relabel button to "Close / Preview manifest" **and** delete the "is queued" claim from `:582` (the footer over-claim is the real defect). Contrast the honest sibling "Send to review queue" toast.
- **Effort:** `<30min` · **Raised by:** S1 `UIUX-07`, S3 `J9`, S4 `F-INT-07`, S10 `T-TRU-05` · **Verdict: [UNVERIFIED] ×4 — all specialist-Confirmed, string-quoted; not independently re-run.**

### P2-3 · Stale "phase-2" badge understates the read-wired Pipeline-repair & Archivist modals
- **Where:** `BuilderModals.tsx:416` (PipelineRepairModal, fetches `api.monitoring`/`api.signatureRepair` `:364,:386`) and `:558` (ArchivistModal, fetches `api.archiveIndex` `:530`) both render `>phase-2<`; AuthorToolNodeModal `:210` phase-2 is *accurate* (true static mock).
- **Fix:** Replace the modal-level `phase-2` chip on the two read-wired modals with `advisory · read-only`; keep the inline write disclaimers. (Pipeline-repair "Send to review queue" `:502-514` already navigates + honest toast — relabel to "Open review queue" to match; **do not** build the signature→ticket write bridge.)
- **Effort:** `<30min` · **Raised by:** S1 `UIUX-06`, S3 `J6`, S4 `F-INT-06`, S8 `DEMO-04`, S10 `T-TRU-04` · **Verdict: [UNVERIFIED] ×5 — specialist-Confirmed (T-TRU-04 Probable); not independently re-run.**

### P2-4 · Submit "Save draft" is a silently inert control
- **Where:** `frontend/src/screens/Submit.tsx:1197-1202` `<button>Save draft</button>` — no `onClick`, not disabled; section comment `:1187` "inert Save draft." Accession's identically-labeled button works (`Accession.tsx:374-380`).
- **Fix:** Disable with a "phase-2 seam (not persisted)" tooltip, or fire an honest info toast. (Wiring a real localStorage draft is optional, not required.)
- **Effort:** `<30min` · **Raised by:** S3 `J4`, S8 `DEMO-07` · **Verdict: [UNVERIFIED] ×2 — specialist-Confirmed.**

### P2-5 · BaseSpace connector is a mock (fabricated "Connected as lab-ops@giab", always imports 4 GIAB seeds) with no mock label
- **Where:** `frontend/src/screens/Submit.tsx:400-402` connect on any token; `:652-655` renders green "Connected as lab-ops@giab"; `:408-415` `importRun()` unconditionally loads `SEED_SAMPLES`+`SEED_META`, ignoring the selected row's advertised count (e.g. "Cardio-panel · 28 samples" `:80-84`).
- **Fix:** Add a persistent "Demo mock · not a live BaseSpace connection (T-057)" banner to the panel whenever connected.
- **Effort:** `<30min` · **Raised by:** S3 `J5`, S8 `DEMO-08` · **Verdict: [UNVERIFIED] ×2 — specialist-Confirmed.**

### P2-6 · SettingsModelTier Save persists nothing but toasts "Updated N agents" / "Live" badge flips green
- **Where:** `frontend/src/components/SettingsModelTier.tsx:171` `setRows(next)` then `:174` `toast('Updated N agents','success')` — no api call; "Live" badge `:487-495` driven by local state; honesty note only inside the transient confirm body `:166`. No backend agent-model endpoint (`settings.py` = thresholds only; models read from env at init).
- **Fix:** Qualify the toast ("Staged locally — not persisted") and suffix the Live badge with "(local)" / add a persistent card-level "changes are local demo state — not applied" note.
- **Effort:** `<30min` · **Raised by:** S4 `F-INT-04`, S10 `T-TRU-06` · **Verdict: [UNVERIFIED] ×2 — specialist-Confirmed (T-TRU-06 Probable).**

### P2-7 · metrics-expansion roster is vaporware that can read "Live", and roster env labels are wrong
- **Where:** `SettingsModelTier.tsx:54` `metrics_expand` `wired:false, phase2:true`, `env:'PIPEGUARD_METRICS_AGENT'` — no backend module, absent from `.env.example`; the Live SegmentedControl `:279-283` is not disabled for `wired:false` rows. Separately, displayed env strings drift from real vars: `:48` `PIPEGUARD_SYNTHESIZER` (real: `PIPEGUARD_CLAUDE_MODEL`), `:53` `PIPEGUARD_NODE_AUTHOR` (real: `PIPEGUARD_NODE_AUTHOR_MODEL/_AGENT`).
- **Fix:** Mark `metrics_expand` "design-only (no backend)" and force Stub / disable Live for `wired:false` rows; correct the displayed env strings to the real `PIPEGUARD_*_MODEL/_AGENT` names.
- **Effort:** `30-90min` · **Raised by:** S4 `F-INT-03` (Probable), `F-INT-10`, S10 `T-TRU-08` · **Verdict: [UNVERIFIED] ×3 — specialist-Confirmed except F-INT-03 (Probable).**

### P2-8 · Share/DATA_EXPORTED egress is absent from the central Admin Activity feed
- **Where:** `frontend/src/screens/Admin.tsx:427` `FeedKind = 'threshold'|'pipeline'|'ticket'|'access'|'actas'` (no share/export); the share event **does** render in the per-run Provenance trail (`provenance.ts:35` `data.exported`), and `POST /api/runs/{id}/share` is approver-gated (`main.py:948-951`).
- **Why P2:** G7 ("every stakes-y write lands in an audit feed") is satisfied by the run trail; only the central Admin view omits it. Document that egress audit lives in Provenance, or add the kind.
- **Fix (min):** Document the scope; **or** (additive) add a `share` FeedKind sourced from `DATA_EXPORTED` events. Same taxonomy gap also explains ticket/notification events not merged into the run trail (`DL-06`) — scope the "single trail" claim honestly.
- **Effort:** `<30min` (document) / `30-90min` (wire) · **Raised by:** S4 `F-INT-08`, S6 `AS-06`, (trail-scope: S2 `DL-06`) · **Verdict: [UNVERIFIED] ×3 — specialist-Confirmed.**

### P2-9 · MonitoringSignature `types.ts` mirror lies ("NOT yet served") and drops served `affected_run_ids`, patched by an `as` cast
- **Where:** `api/main.py:1255-1258` serves `first_seen/last_seen/trend='flat'/affected_run_ids` (populated `:1410-1413`); `frontend/src/types.ts:346` stale comment "NOT yet served (F2)", type `:348-357` omits `affected_run_ids` + types `trend` optional; consumer casts around it at `MonitoringSignatureRow.tsx:10,60` (`SignatureWithRuns`).
- **Why P2:** Renders correctly at runtime (cast + backend defaults) — this is contract-truth, not a visible break, so it can be documented/fixed cheaply without golden-path risk.
- **Fix:** Update `types.ts:348-357` to the real shape (add `affected_run_ids: string[]`, non-optional `trend`), delete the F2 comment, drop the `SignatureWithRuns` cast.
- **Effort:** `<30min` · **Risk:** trivial, type-only · **Raised by:** S2 `DL-01`, S9 `CON-01` · **Verdict: [CONFIRMED] (DL-01 reproduced) + corroborated (CON-01 UNVERIFIED).**

### P2-10 · Real-GIAB run has no NOTE.md disclosing its chr20 / arbitrary-smoke-window scope
- **Where:** `data/RUN-2026-07-08-GIAB-HG002/` has no NOTE.md (contrast `data/RUN-2026-07-11-CLINVAR-RTH/NOTE.md`); panel is `scripts/panel_regions.example.bed:3-6` "ARBITRARY smoke-test windows on chr20 … NOT a real clinical gene panel"; the run reports `breadth_20x=0.9924` / `mean_coverage=54.2` with no run-dir caveat.
- **Why P2:** 99.2% breadth over three arbitrary ~50-100kb chr20 windows can read as whole-panel/clinical quality (G3). Doc-only mitigation; only matters if this fixture is shown.
- **Fix:** Add a NOTE.md mirroring the CLINVAR-RTH fixture (chr20-only downsample, arbitrary smoke panel, benchmark non-patient sample, no clinical claim).
- **Effort:** `<30min` · **Raised by:** S7 `SCI-06` · **Verdict: [UNVERIFIED] — specialist-Confirmed.**

### P2-11 · Share egress redaction gaps (bounded, but on a shipped egress path)
- **Where:** `AS-04` `api/safe_harbor.py:160-162` — the `value is None` short-circuit precedes the guarded-origin drop `:177-179`, so a guarded-origin run with absent `tissue` emits `"tissue": null`, leaking column presence (sibling `deid.py:129-131` orders it correctly). `AS-02` `safe_harbor.py:84-86` `_FREETEXT_FIELDS` omits `headline`/`rationale`, so card narration passes through un-redacted. `AS-01` `synthesis/claude.py:97` dumps the whole `Sample` (incl. `submitted_by`, which the export policy elsewhere DROPs) to the LLM on the live path.
- **Why P2 (not P0):** Demo runs **stub-default, offline, $0, contrived data** (G2) — AS-01/AS-02 only bite on the live synthesizer (off), and AS-04's leak is column-presence-only for a specific origin. Real but low-blast-radius; cheap defensive fixes.
- **Fix:** AS-04 — move the guarded-origin drop above the `None` branch (mirror `deid.redact`). AS-02 — add `headline`,`rationale`,`next_steps` to `_FREETEXT_FIELDS`. AS-01 — drop `submitted_by` from the synthesizer metadata dump / route through `deid.redact`.
- **Effort:** `<30min` each · **Raised by:** S6 `AS-04` (Confirmed), `AS-02` (Probable), `AS-01` (Confirmed) · **Verdict: [UNVERIFIED] — specialist confidences as noted.**

### P2-12 · Empty / no-tool-node graph is rejected at `/compile` (422) but accepted at `/pipelines/run` (202) → confusing late failure
- **Where:** `api/routers/nextflow.py:84-85` raises 422 "the graph has no tool nodes to compile"; `pipeline_run.py:187-191` calls `compile_graph` with no empty guard; `compiler.py:124-125` yields empty topo order with no error, so the run 202s then dies late in the driver ("produced no results dir", `run_giab_pipeline.py:133-134`).
- **Why P2:** A judge exploring Builder who Runs an empty canvas gets an opaque minutes-later failure instead of an immediate reason.
- **Fix:** Add `if not body.graph.nodes` guard to `run_pipeline` before compiling (or centralize the check in `compile_graph`).
- **Effort:** `<30min` · **Raised by:** S5 `F5-R3` · **Verdict: [UNVERIFIED] — specialist-Confirmed.**

---

## P3 — POST-HACKATHON BACKLOG (no golden-path bearing)

- **P3-1 · cluster_pf `required=True` structurally pins every reads-based run to HOLD** — `runbook.py:99-106,42`; the driver leaves it blank (`run_giab_pipeline.py:224,229`) so PROCEED is unreachable on the live path. **The demo intentionally relies on HG002→HOLD ("honest cluster_pf-missing")**, so changing `required` is risky (Medium) and off-mandate; document that the HOLD is structural, defer the SAV-source policy. S7 `SCI-02` · [UNVERIFIED, specialist-Confirmed].
- **P3-2 · Durable job store + Builder-run status disk fallback** (root cause behind P1-5) — `intake.py:54`, `pipeline_run.py:99,286-289`; orphaned `.nf-runs/<id>` scratch. Persistence is new scope. S5 `F5-R5`, `F5-R2` (disk-fallback half). `post-hackathon`.
- **P3-3 · No FASTQ pairing / read-count / format validation** — swapped equal-length R1/R2 → silent wrong result. `main.nf:15`, `run_giab_pipeline.py:243-244`; additive preflight finding. S7 `SCI-04`, S5 `F5-R8` (Possible). `post-hackathon`.
- **P3-4 · No reference-build / contig-naming assertion (reads↔FASTA↔panel BED)** — `20` vs `chr20` yields silent ~0% breadth. `main.nf:17`. S7 `SCI-05`. `post-hackathon`.
- **P3-5 · No pre-flight reference-index (`.fai`/`.bwt.2bit.64`) check** — burns a full Nextflow launch before failing in bwa-mem2. `run_giab_pipeline.py:264-271`. S5 `F5-R7`. `post-hackathon`.
- **P3-6 · Reproducibility pins are floating tags + version floor; no per-run digest/nextflow-version capture** — `catalog.py:71…`, `nextflow.config:5`, `provenance.py:57-59`; "deterministic reruns" = wiring + gate re-derivation, not bitwise output. Capture resolved versions (light) rather than re-pin containers (Medium risk). S7 `SCI-03`. `post-hackathon`.
- **P3-7 · Subprocess timeout kills only the direct child + timeout asymmetry (900s intake vs 1800s Builder)** — orphaned Nextflow/JVM subtree; `intake.py:107-111,110` vs `pipeline_run.py:268-281,269`. Share one timeout constant; reap the process group. S5 `F5-R9` (Probable), `F5-R6`. `post-hackathon`.
- **P3-8 · Duplicate-run-id 409 guard not atomic with run-dir creation** — concurrent same-id submits both proceed; `intake.py:134,147`, `pipeline_run.py:184,232`. Reserve under `_lock`/`run_id in _jobs`. S5 `F5-R4`. `post-hackathon`.
- **P3-9 · Live-intake driver fabricates `sample_metadata.csv` (hardcodes `tissue=blood`, `subject_id=sample_id`)** — `intake.py:108-109`, `run_giab_pipeline.py:217-221`. Mitigated: HG002-only path, real tissue *is* blood, recording uses mock_run_01 → no wrong value surfaces. Prefer a "fixture-authored" note over rewiring the live driver. S2 `DL-03`. `post-hackathon`.
- **P3-10 · Variant gate is DP-only; GQ/Ts-Tv ungated, allele-balance/AF not computed; 7 registered metrics have no parser; qc.duplication registry names Picard but driver parses fastp; stale mapping.py cluster_pf docstring** — registry/label hygiene: `runbook.py:157-165`, `metric_registry.yaml`, `mapping.py:54`. Label DP-only scope; mark unparsed metrics "not computed" in any registry-driven UI. S7 `SCI-08`, `SCI-09`, `SCI-07`, `SCI-10`. `post-hackathon`.
- **P3-11 · Agent-safety deferred items** — `AS-03` RBAC dev-shim trusts client role header + defaults `approver` (documented "never ships as production"; offline demo; note Provenance.tsx:76 "approver-gated" slightly overstates); `AS-05` redact case-sensitivity (latent); `AS-07` synthesizer prompt-injection (bounded, verdict deterministic); `AS-08` manifest advertises all 18 Safe-Harbor classes (mitigated by disclaimer). Swap to a verified IdP + default header-less to viewer at deployment. S6. `post-hackathon`.
- **P3-12 · `RunHandoffModal` is orphaned dead code still documented in CLAUDE.md:341** — `BuilderModals.tsx:79`, zero call sites (superseded by RunPipelineModal). Delete export + doc line after confirming no dynamic import. S4 `F-INT-05`. `post-hackathon`.
- **P3-13 · UI/UX & contract polish (off-recording, low risk, additive)** — lifecycle status dots reuse verdict hues (`verdict.ts:6-10`, S1 `UIUX-02`); Pager not adopted on 4 surfaces (S1 `UIUX-03`); Inbox uses SegmentedControl not Tabs + doc drift (S1 `UIUX-04`); global Toast lacks `aria-live` (`Toast.tsx:35`, S1 `UIUX-05`); ConfirmDialog lacks `role=dialog`/focus trap (S1 `UIUX-08`); `types.ts` drift — Runbook/QCThreshold omit 4 `/api/config` fields (S2 `DL-04`), `metric_values?` always emitted (S2 `DL-08`), `IntakeStatus.status` open str vs literal (S9 `CON-04`), TriageNote drops `addresses_signatures` (S9 `CON-05`); node_author `ARTIFACT_KINDS` mirror drift + `NodeProposal` no transport (S9 `CON-02`,`CON-03`); subject_id parsed but not surfaced / no server wire path (S2 `DL-07`,`DL-02`); builder-graph envelope vs NfGraph shape-by-convention (S2 `DL-05`); uncapped `/api/monitoring runs[]` (`main.py:1282-1350`, S4 `F-INT-09`); stale demo docs describe 6 screens vs ~14 routes (S8 `DEMO-03`). All `post-hackathon`.
- **P3-14 · (New scope — NOT Track A) approval gate on `/api/pipelines/run`** — wiring an `approved`-status check could break the demo Run beat; deferred to the wishlist track per P1-6. `post-hackathon`.

---

## PRE-RECORDING RELEASE CHECKLIST (go / no-go)

**Hard gate — do NOT record until green:**
- [ ] **P0-1** — `/` Runs hero no longer shows a hardcoded green "Gate online"; dot reflects `useApiHealth()` (or is relabeled non-status). Verify: stop the API, reload `/`, confirm the hero dot is **not** green and matches TopBar's "Offline".

**Strongly recommended before submission (P1 — all low/zero code risk):**
- [ ] **P1-1** — demo docs narrate the shipped `Advisory` + `Rule-derived triage (offline)` labels, not "ADVISORY · STUB".
- [ ] **P1-2** — Intake override copy reworded off "recorded on the run" → "recorded locally this session (not persisted)".
- [ ] **P1-3** — `/submit` no longer shows "Samples · 4" before an upload (guarded to 0, or seeded rows visibly labeled).
- [ ] **P1-4** — DecisionCard finding text shows fraction metrics as percent (85%, not 0.85%); **golden QC fixtures/signatures regenerated and gate tests green**.
- [ ] **P1-5** — Submit and Builder-run pollers surface an honest "lost track" toast + clear the spinner on a `404`/network error (no infinite "running").
- [ ] **P1-6** — CLAUDE.md router map includes `pipeline_run.py` with the unapproved-graph note; Run modal states it runs the current canvas graph.

**Confirm labeled/hidden (P2) if the demo strays off the scripted path:**
- [ ] Builder Author-tool CTA, Archivist "Queue archive"+footer, and the two read-wired modals' `phase-2`→`read-only` badges relabeled (**P2-1/2/3**).
- [ ] Submit "Save draft" (**P2-4**) and BaseSpace mock (**P2-5**) carry disabled/phase-2/demo-mock labels.
- [ ] SettingsModelTier Save toast + Live badge say "local, not persisted"; metrics-expansion marked design-only (**P2-6/7**).

**Guardrail sanity (must hold on camera):**
- [ ] G1 — verdicts remain rule-decided/read-only; no advisory agent sets or edits a verdict/confidence.
- [ ] G2 — recording runs **stub-default, no API key, $0**; the two live-synthesizer PII gaps (P2-11) do not fire.
- [ ] G3/G4 — no clinical/pathogenicity language; ClinVar quoted verbatim (VAR-RTH-001); no heuristic labeled "confidence".
- [ ] Beats intact — HG002 → **HOLD** (structural cluster_pf-missing, P3-1) and CLINVAR-RTH → **ESCALATE** render as scripted.
