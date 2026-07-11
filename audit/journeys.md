## PipeGuard Release-Hardening Audit — Specialist 3: Feature-completeness (journeys)

**Run mode:** Fable 5, code-only / headless (route + `file:line` + quoted string; no browser this pass, per AUDIT_PLAN §Resolved 2026-07-11).
**Scope:** Journey A (Operate: Accession → Submit → POST /api/runs → intake-status → Decision cards → Review queue → Agent triage → Provenance → Share), Journey B (Builder: compose → Export → Run → Save/Submit/Approve → Dry-run/Diff → Open saved), Journey C (Create-a-tool / node-authoring).
**Guardrails honored:** G1 (rules decide) — no finding recommends letting any surface set a verdict/confidence. Every claim re-opened and the quoted string confirmed. No production code edited.

**Verdict up front:** the two demo-critical hero paths (pre-gated `mock_run_01` → cards → queue → provenance → share) are coherent and honest; the identity-join submit gate and the review-queue exactly-once ticket materialization are genuinely robust (see Honest surfaces). No Blocker. The findings below are dead controls, durability claims the UI can't keep, and journey steps that exist in one layer but dead-end in another.

---

### J1 · Intake "Admit (override)" claims it is "recorded on the run" but is ephemeral client-only state
- **Severity:** High · **Confidence:** Confirmed · **Category:** missing user-facing state · **Journey:** A (Operate — Intake gate)
- **Evidence:** `frontend/src/screens/Intake.tsx:65` `const [overrides, setOverrides] = useState<Record<string, boolean>>({})`; toggled only at `:401-404` `onClick={(e) => { e.stopPropagation(); setOverrides((m) => ({ ...m, [id]: !m[id] })) }}`; the on-screen copy at `:352` reads `'Admitted below the yield target by manual override — recorded on the run.'` and the chip label `:266` `override: 'Admitted · manual override'`. There is no `api.*` call, no `localStorage`, and no POST anywhere in the override path.
- **Reproduction:** Open `/runs/:id/intake` (Intake gate) on a run with a genuinely-sparse sample → expand the row → click **Admit (override)**. The chip flips to "Admitted · manual override" and the note says "recorded on the run." Reload the page (or switch runs and back).
- **Expected:** Either the override is actually persisted (server or at least labelled client-side), or the copy does not claim it was "recorded on the run."
- **Actual:** The override lives only in component React state — lost on reload/navigation and never transmitted; the "recorded on the run" copy asserts a durable audit record that does not exist.
- **Likely root cause:** IG1 shipped the annotation UI ahead of any persistence seam (correct under G1 — an override must never mutate a gate verdict — but the copy was written as if it persisted).
- **Minimum viable fix:** Reword `:352`/label to "recorded locally in this session (not persisted)" — matching the honest "held client-side" idiom Submit already uses.
- **Larger fix:** Persist the override as an off-gate annotation event (never a verdict mutation) so the audit claim becomes true.
- **Demo-critical:** N (recording uses pre-gated `mock_run_01`; would become Y if the narration exercises the override). · **Fix risk:** none (copy-only). · **Regression test:** snapshot assert the override note does not contain "recorded on the run" unless a persistence call fired.

### J2 · Create-a-tool (Journey C) is a non-functional dead end — the "add to palette" button is a no-op and the node-author agent has no transport
- **Severity:** High · **Confidence:** Confirmed · **Category:** incomplete integration · **Journey:** C (Create-a-tool / node-authoring)
- **Evidence:** `frontend/src/components/BuilderModals.tsx:340-342` — the primary action `<button onClick={onClose} ...>Review kinds &amp; add to palette</button>` (and Discard `:337-339`, also `onClose`); the whole `AuthorToolNodeModal` is a static mock over `STAR_HELP` (`:186-345`, hardcoded input ports fastq/reference_fasta at `:270-276`). Mounted at `frontend/src/screens/PipelineBuilder.tsx:1402`. Grep confirms no transport: `grep -rn "node_author" api/` → empty; `grep -rn "propose_node" frontend/src/` → empty; the only frontend reference is the Settings roster row `SettingsModelTier.tsx:53` (`wired: false, phase2: true`). The real agent (`src/pipeguard/node_author`) is core-only.
- **Reproduction:** Builder → open "Author a tool node" → edit the proposed node → click **Review kinds & add to palette**. The modal closes; nothing is registered, no node appears in the palette, no request is made.
- **Expected:** Either the button performs its labelled action (register/propose a node), or its label does not imply a persisted "add to palette."
- **Actual:** The action-implying primary button only closes the modal; journey C produces nothing. The modal is honestly badged "roster #5 · phase-2" (`:210-212`), so the header is truthful, but the button label overstates.
- **Likely root cause:** T-046 built the agent core-only and never wired an `api/` endpoint or a `propose_node` client call; the pre-existing modal was left as a phase-2 visual.
- **Minimum viable fix:** Relabel the button to a non-actionable "Close (phase-2 preview)" so it can't read as a live registration.
- **Larger fix:** Add `POST /api/nodes/propose` → `propose_node()` and an `api.proposeNode` client call that appends the returned `NodeProposal` to the palette.
- **Demo-critical:** N (labelled phase-2; off the Operate/Builder demo hops). · **Fix risk:** none (relabel). · **Regression test:** assert the button has an `onClick` that is not merely `onClose`, or that clicking it issues a request.

### J3 · Builder "Emit" console claims it "Wrote src/pipeguard/layout/run_layout.yaml" but only console.logs
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** confirmed defect · **Journey:** B (Builder — Emit)
- **Evidence:** `frontend/src/screens/PipelineBuilder.tsx:492-499` `onEmit` sets `emitted=true` and `console.log(...)` — no network/file write; the success panel it triggers is `frontend/src/components/BuilderConsole.tsx:423-431`: `Wrote <span className="font-mono">src/pipeguard/layout/run_layout.yaml</span>. Emit writes the config only — no tool runs.`
- **Reproduction:** Builder → **Emit**. The console tab shows a green check + "Wrote src/pipeguard/layout/run_layout.yaml."
- **Expected:** Emit either writes that file (it does not — the core is framework-agnostic and no endpoint exists) or the message does not assert a filesystem write.
- **Actual:** A concrete false claim that a specific repo path was written; the follow-up sentence ("Emit writes the config only") softens but the leading verb+path is untrue.
- **Likely root cause:** Copy carried over from an intended wired-ingest design; the demo path is `console.log` only (comment at `:497`).
- **Minimum viable fix:** Change "Wrote src/pipeguard/layout/run_layout.yaml" → "Composed run_layout.yaml (preview — not written to disk)."
- **Demo-critical:** N (Builder Emit is not on the stale 6-screen run-of-show). · **Fix risk:** none (copy-only). · **Regression test:** assert the emitted panel text does not contain "Wrote " unless a write call fired.

### J4 · Submit "Save draft" is a fully inert control on the Operate golden path (no handler), inconsistent with Accession's working Save draft
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** missing user-facing state · **Journey:** A (Operate — Submit)
- **Evidence:** `frontend/src/screens/Submit.tsx:1198-1202` — `<button type="button" className="...">Save draft</button>` with no `onClick` and not `disabled`; the section comment at `:1187` literally reads "guardrail note + **inert Save draft** + Submit." By contrast `frontend/src/screens/Accession.tsx:374-380` wires the same label to `onClick={saveDraft}` (persists to `localStorage`, toasts).
- **Reproduction:** `/submit` → click **Save draft**. Nothing happens (no toast, no persistence, no error).
- **Expected:** A visible primary-styled button either acts or is labelled/disabled as a phase-2 seam.
- **Actual:** A live-looking button silently does nothing on the hero submission screen, while the identically-labelled Accession button works — an inconsistency an operator will hit.
- **Likely root cause:** Submit's draft-persistence was never wired; the button was left in place without a phase-2 label.
- **Minimum viable fix:** Either wire it to the same `saveAccessionDraft`-style localStorage draft, or disable it with a "phase-2" tag (matching the app's labelled-seam convention).
- **Demo-critical:** N. · **Fix risk:** low. · **Regression test:** assert the Submit "Save draft" button has an `onClick` or is `disabled`.

### J5 · BaseSpace "Import" always loads the 4 GIAB seed samples regardless of the selected run's stated sample count, with no mock disclaimer
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** design inconsistency · **Journey:** A (Operate — Submit / BaseSpace)
- **Evidence:** `frontend/src/screens/Submit.tsx:408-415` `importRun` sets `setSamples(SEED_SAMPLES)` + `setMeta(SEED_META)` unconditionally (ignores `id`); the run rows advertise other counts at `:80-84` (`{ id: '20260708_NB551_0041', proj: 'Cardio-panel', samples: 28 }`, `{ ... samples: 12 }`). The connect UI reads as real ("Connect to BaseSpace Sequence Hub" `:586`, "Connected as lab-ops@giab" `:654`) with no "demo/mock" label on the import.
- **Reproduction:** `/submit` → "Pull from BaseSpace" → paste any token → Connect → click **Import** on "Cardio-panel · 28 samples." The samples table populates with 4 GIAB rows (HG002/HG003/HG004/NA12878) and the run details become "RUN-2026-07-09-A / GIAB-QC."
- **Expected:** Import reflects the selected run, or the BaseSpace panel is labelled a demo stand-in so it cannot read as a real import (checklist item 11, T-057).
- **Actual:** Every import yields the same 4 seed samples and rewrites run metadata, contradicting the selected row's own count; nothing on screen tells the viewer it's a mock.
- **Likely root cause:** BaseSpace connector is a visual mock; `importRun` reveals `SEED_SAMPLES` as the stand-in payload (comment at `:78-79`).
- **Minimum viable fix:** Add a persistent "Demo connector — sample data is illustrative (T-057)" banner in the BaseSpace panel; optionally set the sample count to match the row.
- **Demo-critical:** N (default method is Upload; recording avoids BaseSpace). · **Fix risk:** low. · **Regression test:** assert the BaseSpace panel renders a demo/seam label whenever connected.

### J6 · Pipeline-repair "Send to review queue" fabricates no ticket — only navigate + toast (triage→queue handoff absent)
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** incomplete integration · **Journey:** A/B (Analyze — repair → Review queue)
- **Evidence:** `frontend/src/components/BuilderModals.tsx:502-514` — the button's `onClick` calls `onClose(); navigate('/queue'); toast('Opened the review queue. Routing a signature-level fix to a specific ticket needs a sample-scoped ticket and approver sign-off.', 'info')`. No `api.createTicket` / write. A signature-level `RepairProposal` has no bridge to a sample-scoped `Ticket` (confirmed: only `createTicket` in `ReviewQueue.tsx` mints tickets, keyed on run|sample, `:405`).
- **Reproduction:** Builder → Pipeline-repair agent → **Send to review queue**. Lands on `/queue`; no new ticket is created or linked.
- **Expected:** Either a ticket is created/linked, or the label doesn't imply routing.
- **Actual:** The button navigates only; the honest toast discloses the missing bridge, but the label "Send to review queue" overstates the action.
- **Likely root cause:** T-069 wired the modal to real read endpoints but the signature→ticket write bridge was deliberately deferred.
- **Minimum viable fix:** Relabel to "Open review queue" (matching the toast).
- **Larger fix:** Add a signature→ticket materialization path (a repair proposal opens/links a sample-scoped ticket with approver sign-off).
- **Demo-critical:** N (honest toast; modal badged phase-2). · **Fix risk:** none (relabel). · **Regression test:** assert clicking either issues a create or the label is navigation-only.

### J7 · Builder "Run pipeline" executes an unsaved/unapproved graph — the Save→Submit→Approve lifecycle is disjoint from the executable graph
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** design inconsistency · **Journey:** B (Builder — Run vs approval)
- **Evidence:** `api/routers/pipeline_run.py:173-239` `run_pipeline` gates on `require_role("reviewer","approver")` + input-kind validation only — it compiles and runs `body.graph` directly with no `status=='approved'` check. The lifecycle (`api/routers/pipelines_lifecycle.py:399-445`, draft→pending_review→approved) governs only the stored profile's locators / dry-run / diff, never this live graph. `RunPipelineModal` (which posts the live canvas graph) is mounted at `frontend/src/screens/PipelineBuilder.tsx:1376`.
- **Reproduction:** Builder → compose a graph (never Save/Submit/Approve) → **Run pipeline** → pick inputs → Run. It executes against the chosen inputs and produces a gate-able run.
- **Expected:** A single coherent story: either an approval gate applies to execution, or the docs/UI make explicit that operator Run is intentionally independent of the profile-approval lifecycle.
- **Actual:** Two "pipeline" objects coexist (executable node/edge graph vs approvable profile locators) with no shared gate; an unapproved draft runs while the approval flow only blesses a separate artifact. This is defensible under compose≠execute ("operators run pipelines") but is undocumented drift and confusing.
- **Likely root cause:** T-123 added the execute path (Nextflow-first) beside the pre-existing profile lifecycle without reconciling the two "pipeline" concepts.
- **Minimum viable fix:** In the Run modal, label the relationship ("Run executes the current canvas graph; it is independent of profile approval"); reconcile CLAUDE.md's code map (the second execution path is not in it — cross-ref Specialist 4).
- **Demo-critical:** N. · **Fix risk:** low (labelling); adding a real execution gate is higher-risk, post-hackathon. · **Regression test:** a doc/UX assertion naming the two pipeline objects distinctly.

### J8 · "rerun" is a dead journey step — no in-place requeue/re-execution is wired; dup run_id 409s in both routers
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** incomplete integration · **Journey:** A (Operate — Review queue / Decision card → rerun)
- **Evidence:** `frontend/src/screens/ReviewQueue.tsx:179-183` `resolutionNote`: `if (verdict === 'rerun') return 'Requeue the sample to clear the rerun.'` — copy only; no requeue control or endpoint exists. A fresh run is required: `api/routers/intake.py:134-135` and `api/routers/pipeline_run.py:184-185` both `raise HTTPException(status_code=409, ...` on `(_DATA / run_id).exists()`. Grep for requeue/rerun wiring returns only these strings and the `Verdict` enum.
- **Reproduction:** Open a `rerun`-verdict ticket → the copy says "Requeue the sample to clear the rerun," but there is no button that requeues; resolving merely marks it cleared (compose≠execute), and re-submitting the same `run_id` 409s.
- **Expected:** Either a "rerun" affordance that spawns a fresh run, or copy that doesn't imply an in-place requeue exists.
- **Actual:** The rerun loop is unimplemented; the only path is a brand-new `run_id`, which the queue never offers.
- **Likely root cause:** rerun was scoped as a verdict/label without the execution loop behind it.
- **Minimum viable fix:** Reword the rerun note to "Submit a fresh run to re-measure — resolving here only records the review."
- **Larger fix:** A "requeue as new run" action that pre-fills Submit/Run with a derived `run_id`.
- **Demo-critical:** N. · **Fix risk:** none (copy-only). · **Regression test:** assert no UI control claims to requeue without hitting a submit endpoint.

### J9 · Archivist "Queue archive" is inert (onClose only) with no write endpoint
- **Severity:** Low · **Confidence:** Confirmed · **Category:** incomplete integration · **Journey:** B (Builder — Archivist advisory)
- **Evidence:** `frontend/src/components/BuilderModals.tsx:586-588` — `<button onClick={onClose} ...>Queue archive</button>`; footer copy at `:582` is honest ("nothing is moved automatically"), header badged "phase-2" (`:558`). No archive-write endpoint exists (read-only `GET /api/archive/index` only).
- **Reproduction:** Builder → Archivist → **Queue archive** → modal closes; nothing is queued.
- **Expected:** Label a non-actionable button as such, or wire a queue-archive write.
- **Actual:** Action-implying label on an inert control; mitigated by an honest footer + phase-2 badge, so low risk.
- **Minimum viable fix:** Relabel "Queue archive" → "Close (phase-2 preview)."
- **Demo-critical:** N. · **Fix risk:** none. · **Regression test:** assert inert phase-2 modal buttons don't carry action verbs, or are disabled.

### J10 · Submit is not role-gated in the UI for viewers — the enabled "Submit" 403s only after click (server-side)
- **Severity:** Low · **Confidence:** Confirmed · **Category:** missing user-facing state · **Journey:** A (Operate — Submit / RBAC)
- **Evidence:** `frontend/src/screens/Submit.tsx:271` `canSubmit = count > 0 && join.metadataPresent && joinApproved` — no role check; the button `:1203-1211` disables only on `submitting || !canSubmit`. Server enforces correctly: `api/routers/intake.py:126-128` `require_role("reviewer","approver")` → a viewer is 403'd (and the toast surfaces the real detail via `httpError`, `api.ts:68-80`). So reads (cards/queue) still work; only the write is blocked — honestly, but late.
- **Reproduction:** Act as a viewer (Admin → Act as viewer) with an approved join → click **Submit to pipeline** → 403 toast after the round-trip.
- **Expected:** For a viewer, the Submit action reads as unavailable up front (disabled + reason), rather than appearing enabled and failing on click.
- **Actual:** The button looks actionable to a viewer and only reveals the RBAC boundary after a failed POST. Server authz is intact (not a security hole), but the affordance is misleading.
- **Likely root cause:** Page-access RBAC (`access.ts`) is a VIEW-gate; the Submit button was never additionally role-gated.
- **Minimum viable fix:** Disable Submit for non-reviewer/approver with a "needs Reviewer" hint (mirrors ReviewQueue's `resolveLocked`/`escalateLocked` idiom).
- **Demo-critical:** N. · **Fix risk:** low. · **Regression test:** assert the Submit button is disabled/labelled for a viewer actor.

---

### Honest surfaces (verified working / correctly labelled — reported so the signal above stays clean)
1. **Submit identity-join gate cannot be bypassed.** `canSubmit` requires `metadataPresent && joinApproved` (`Submit.tsx:271`); approval is bound to the join **signature** (`:256-260`) so any edit (sample type / re-attach / add-remove) re-opens approval; a blocking row (`join.blocking > 0`) hard-blocks approval (`:387-398`, `:1131`). `sample_metadata.csv` is genuinely required (`:945-961`). Robust.
2. **Review-queue tickets are derived + materialized exactly once.** The per-key promise chain + synchronous `serverIdRef` (`ReviewQueue.tsx:400-419`, `:228-229`) guarantees a rapid double-action mints one `createTicket`; resolved tickets fall out of the selectable set (`:315-318`, `:543`). Assign uses the same guard (`:446-468`). Correct.
3. **`subject_id`/`tissue` is a clean, labelled client-side seam.** Accession → Submit handoff via a one-shot localStorage courier (`Submit.tsx:283-294`, `lib/accession.ts`), and `SampleIn`/`SubmitRunIn` are `extra="forbid"` (`intake.py:59,70`) so a smuggled subject field 422s rather than silently dropping. The PII banner is prominent and honest (`Accession.tsx:148-159`).
4. **Share journey is approver + confirm gated and audited.** `Provenance.tsx:108-133` — non-approver never sees the control (`:113`), `useConfirm` gate (`:116`), `api.shareRun` records a `DATA_EXPORTED` event, refetch surfaces it in the trail. (Note for Specialist 4/8: the share audit lands in the Provenance trail, not the Admin Activity feed — cross-layer gap owned there.)
5. **Dry-run resolver is read-only + traversal-hardened.** `pipelines_lifecycle.py:298-332` refuses absolute/`..`-escaping locator patterns as `invalid`, globs only inside the run dir, `DryRunResult.executed` is a hard-coded `False` (`:120`). Compose≠execute holds.
6. **Accession Export CSV / Save draft / Send to wetlab intake** all work and are honestly labelled client-side (`Accession.tsx:112-140`).
7. **Emit/Export/Run are three clearly-separated Builder actions** — Emit (compose profile), Export to Nextflow (real `POST /api/pipelines/compile`), Run (real `POST /api/pipelines/run`); the confusion is only the "Wrote…" copy (J3) and the disjoint approval lifecycle (J7), not the wiring.

**Coverage note:** Journey A hops (Accession→Submit→intake-status→cards→queue→triage→provenance→share) and Journey B hops (compose→export→run→save/submit/approve→dry-run/diff→open-saved) were each traced to code; Journey C confirmed absent by grep. Live-intake reliability (nextflow-on-PATH, job durability) is owned by Specialist 5 and excluded here.
