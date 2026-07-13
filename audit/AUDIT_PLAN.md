# bayleaf — Release-Hardening Audit Plan (Fable)

> **This plan has two fenced tracks, both run on Fable 5 over the same repo grounding.**
> **Track A — Release-hardening audit** (§ below through "Critical framing"): what exists → P0–P3 fixes; mandate = *do not expand scope*.
> **Track B — Wishlist feasibility** (final § "TRACK B"): grounded implementation design for *new* maintainer wishlist features → design proposals; mandate = *design new scope, grounded in real seams*.
> The two never share an agent — each agent's prompt scopes it to exactly one track — so Track B's "propose new work" mandate can't erode Track A's "don't add scope" discipline.

## Purpose

Release-harden **bayleaf**'s working golden path before the hackathon demo. The objective is to **reduce uncertainty** around the existing Operate flow and Builder flow — make the shipped system coherent, integrated, reliable, scientifically credible, and demo-truthful. This is **not** a scoping exercise: do **not** propose new features, redesigns, or speculative agents. A finding is valuable only if it de-risks the golden path or corrects a claim the UI makes about itself. bayleaf is an AI-assisted **provenance & QC decision gate** for genomics runs; its hero output is a per-sample `DecisionCard` (proceed / hold / rerun / escalate). Every conclusion must respect that **rules decide and AI only advises**.

---

## Fable-compatibility assumptions (ADJUSTABLE — correct these if Fable's mechanics differ)

The plan below assumes Fable is a multi-agent orchestration surface where:

1. One **MASTER instruction** is prepended to every agent (specialists + synthesis).
2. **N specialist agents run in parallel**, each on the Fable model, each self-contained (no cross-agent chat).
3. Each specialist **writes its report to `audit/<specialty>.md`** (a filesystem write). *If Fable instead uses fixed output slots or has no file-write, treat "save to `audit/<specialty>.md`" as "emit your full report into your output slot verbatim" and let the synthesis agent read the slots.*
4. A single **synthesis agent runs last**, with read access to all specialist reports.
5. Agents can **read the repo and drive the running app** (FastAPI read-API + Vite/React frontend) but **must not edit code** (see guardrails). *If Fable agents are read-only-repo with no browser, downgrade every "screenshot + route" evidence requirement to "route + accessibility-tree/DOM excerpt + `file:line`" and say so in the report header.*

This block exists so the maintainer can reconcile the plan with Fable's real capabilities before running it. Everything downstream assumes 11 agents: 8 specialists + 2 additional auditors (contract, truthfulness) + 1 synthesis.

**Resolved (2026-07-11) — run mode & evidence.** This audit runs on **Fable 5 across every agent** (specialists, the adversarial-verify skeptics, and synthesis). A single-specialist **dry-run (Truthfulness) validated the approach**: 9 findings, all grounded in real `file:line` with quoted strings, **zero mismatched citations on re-check** — Fable-5's grounding on this repo is reliable. Evidence mode is **code-only / headless** (route + `file:line` + quoted string, exactly as the dry-run auto-downgraded to); the two screenshot-wanting specialists (UI/UX, demo-readiness) run headless too, and a **separate browser pass follows the run** to attach visual proof only to the findings that need it. Orchestration: specialists **return structured findings (read-only, no file writes)**; the harness writes `audit/<specialty>.md` + `audit/SYNTHESIS.md` so no write-capable audit agent touches the tree.

---

## bayleaf guardrails every agent MUST honor

These are non-negotiable and take precedence over any "improvement" instinct:

**G1 — ADR-0001 (rules decide / AI advises).** The verdict and confidence are computed by the deterministic rule engine (`src/bayleaf/rules.py` → `synthesis/base.py::aggregate_verdict`), never by an LLM. Every advisory agent's JSON schema exposes **prose only**. **An auditor recommendation to let any agent set, edit, or override a verdict/confidence is itself a Blocker finding**, not a fix.

**G2 — Offline-first, conserve API credits.** All six advisory LLM seams are **OFF/stub by default** (`BAYLEAF_*_AGENT=stub`, ADR-0006). The demo baseline runs with **no API key** at **$0**. Auditors must **record stub-vs-live status**, never assume a live agent, and never turn one on to "test" it without saying so. The demo recording default is the stub.

**G3 — Not a clinical system.** No diagnostic, therapeutic, or safety claim. ClinVar significance is quoted **verbatim** as cited evidence (VAR-RTH-001); bayleaf authors no pathogenicity. Flag any UI text that reads as a clinical call.

**G4 — "Confidence" values are heuristics.** Any per-citation score is a heuristic keyword-overlap number, surfaced as `N% (heuristic)`, **never** "confidence." `DecisionCard.confidence` is intentionally `null` until grounded (T-019). Flag any surface that renders a confidence meter or calls a heuristic "confidence."

**G5 — Read-only during audit.** Do **not** edit production code. A maintainer may be concurrently editing Builder files (`frontend/src/components/Builder*.tsx`, `screens/PipelineBuilder.tsx`, `api.ts`, `types.ts`, `index.css`), so **quote the offending string** in every citation — line numbers can shift under concurrent edits, but a reviewer can re-anchor by string. Report defects; do not reconcile them yourself. (Run this audit only when that session has landed, so it isn't a moving target.)

**G6 — House rule: scale-aware UI.** 100+ sample flowcells are normal. No pill/bubble selection, no infinite rows — dropdowns + pagination. Flag any surface that would break at volume.

**G7 — House rule: explicit edit + audit.** Every mutation must be explicitly selected + saved (no accidental single-click cascade), and every stakes-y write must route through `useConfirm` and land in an audit feed. Flag any un-gated cascading write.

---

## Fan-out structure — 11 agents

| # | Agent | Report file |
|---|-------|-------------|
| 1 | UI/UX consistency auditor | `audit/ui-ux.md` |
| 2 | Data-movement / lineage auditor | `audit/data-lineage.md` |
| 3 | Feature-completeness (journeys) auditor | `audit/journeys.md` |
| 4 | Integration-seam auditor | `audit/integration.md` |
| 5 | Reliability & failure-mode auditor | `audit/reliability.md` |
| 6 | Agent safety & security auditor | `audit/agent-safety.md` |
| 7 | Scientific correctness & reproducibility auditor | `audit/science-repro.md` |
| 8 | Demo-readiness & truthfulness-of-status auditor | `audit/demo-readiness.md` |
| 9 | Contract auditor (FE↔API↔core↔agent↔manifest) | `audit/contract.md` |
| 10 | Truthfulness auditor (labels vs reality) | `audit/truthfulness.md` |
| 11 | Synthesis agent | `audit/SYNTHESIS.md` |

---

## Specialist 1 — UI/UX consistency auditor → `audit/ui-ux.md`

**Role.** Audit every screen / modal / drawer / card / form / chart / toast / loading / empty / error / nav state for terminology, visual, and interaction consistency, and for controls that *look* actionable but aren't.

**Owns (routes + files).** All 12 operator routes + `/admin` + `/login` in `frontend/src/App.tsx`; `components/Sidebar.tsx` (Operate / Analyze / Configure / Admin nav); `verdict.ts` (token maps); `index.css` (6 themes: clinical/sand/slate light + midnight/carbon/indigo dark via `data-theme × data-palette`, `PrefsContext`); shared primitives in `components/` (`Tabs.tsx`, `Bar.tsx` [`SegmentBar`/`MeterBar`], `Toast.tsx`, `ConfirmDialog.tsx`, `Pager.tsx`, `RunSelector.tsx`, `States.tsx`, `PageHeader.tsx`, `VerdictBadge.tsx`, `SegmentedControl.tsx`, `Check.tsx`+`hooks/useRangeSelect.ts`, `Truncate.tsx`); screens `RunOverview.tsx`, `RunDetail.tsx`, `Provenance.tsx`, `ReviewQueue.tsx`, `Monitoring.tsx`, `Submit.tsx`, `Accession.tsx`, `Intake.tsx`, `AgentTriage.tsx`, `Settings.tsx`(+`SettingsAssayTable`/`SettingsModelTier`), `Admin.tsx`, `Inbox.tsx`.

**Inspection checklist (verify reality; do not assume):**
1. **"Card" overload.** Builder "tool node / card" (`UserNode`/`ToolCard`/`PaletteItem`) vs "Decision card" (`DecisionCard` in `RunDetail`). Confirm nav labels, page headers, and modal titles never conflate the two.
2. **Five coexisting status vocabularies.** `RunStatus`(running/needs_review/released) · `IntakeStatus`(queued/running/complete/failed) · `PipelineRunStatus` · `PipelineStatus`(draft/pending_review/approved) · `TicketStatus`(open/in_review/resolved). Confirm each renders with a distinct, labelled token set and no surface shows a raw enum.
3. **Run-status dots reuse verdict hues** (`RUN_STATUS_META`: needs_review=hold-amber, running=info-blue, released=proceed-green). On the Runs list, `TopBar` switcher, and `RunSelector`, confirm a hold-amber *lifecycle* dot cannot be misread as verdict **Hold**.
4. **Verdict/confidence is strictly read-only** (G1/G4) on `RunDetail`, `ReviewQueue`, `AgentTriage`, `Monitoring`. No editable verdict control anywhere; advisory surfaces say "advisory"/"heuristic", never "confidence."
5. **Every INERT primary action is visibly labelled phase-2/seam:** `AuthorToolNodeModal`, `PipelineRepairModal` "Send to review queue," `ArchivistModal` "Queue archive," Inbox calendar connectors + mentions, `SettingsModelTier` Save + metrics-expansion row, `Submit` "Save draft," `Login` CAPTCHA/OAuth, `Admin` password/email reset, Accession "Save draft."
6. **Shared-primitive adoption is complete:** `Tabs` replaced `FacetChip` (deleted) in Runs/ReviewQueue/Admin/RunDetail; `Bar.tsx` backs every bar (no stray `h-[11px]`/`rounded-6` leftovers); `Pager.tsx` on every paginated surface; `SegmentedControl` reserved for compact toggle *settings* (7d/14d/30d, theme, density) only.
7. **Loading/error/empty states.** `States.tsx` (`Loading`/`Skeleton`/`ErrorBox` with `onRetry`/`Empty`) vs screen-local variants (`RunSelector` inline, `DecisionStates`, `BuilderModals` inline, `Monitoring`). Every error state must offer retry; every empty state must be honest, never a fabricated row.
8. **Theme completeness across all 6 palettes.** Verdict + gate colors stay **inherited** from `@theme` (never palette-overridden) at AA; nav (`--color-nav*`) + canvas dot grid (`--canvas-dot`) theme end-to-end in light and dark; `PrefsContext` density (split/brief/dense) applies where declared.
9. **Scale-aware (G6).** Submit sample table (25/page + bulk add/remove), ReviewQueue select-all is page-scoped, Monitoring runs, AgentTriage flagged table (10/page), Admin Activity (25/50/100). Confirm no infinite row list and no pill-per-item selection.
10. **`Truncate` coverage.** Applied only to the `RunDetail` decision headline today — check other overflow-prone strings (run ids, sample names, artifact paths) don't break layout inconsistently; report the gap if unaddressed.
11. **a11y basics.** Keyboard focus + labels on the Builder canvas controls, ConfirmDialog (Esc/click-outside cancel), form inputs on Submit/Accession/Settings; contrast of verdict tokens.

**Evidence format.** Per finding: a **screenshot** + the **exact route** + the component `file:line`. UI-only claims without a route+screenshot are downgraded to "Possible."

**Golden-path intersection.** Owns the visual truth of every Operate hop and the Builder toolbar; a mislabeled status/verdict on `RunOverview`/`RunDetail` is High.

---

## Specialist 2 — Data-movement / lineage auditor → `audit/data-lineage.md`

**Role.** Trace each object end-to-end: UI input → frontend state → API request → validation → filesystem/store → Nextflow execution → agent/tool read → persisted output → UI render. Surface duplicated sources of truth, schema drift, stale state after mutations, and data that never crosses a boundary.

**Owns.** `frontend/src/types.ts` (hand-kept TS mirror — top of the contract chain), `frontend/src/api.ts` (typed client, RBAC actor headers, `httpError()`, header-borne totals); `src/bayleaf/models.py` (authoritative pydantic contract), `src/bayleaf/provenance.py` (11 `EventType`s, `EventLedger`), `src/bayleaf/parsers.py::load_run`; `api/main.py` (`RunSummary`/`RunDetail`/`RunArtifact`, `@lru_cache`'d `_evaluate`, `get_run` share-merge L508-512, `_ARTIFACT_STAGE`), `api/card_readout.py` (metric_values ⋈ QCThreshold), `api/routers/intake.py` (`SubmitRunIn`/`SampleIn` `extra='forbid'`), `api/pipeline.py` (`PipelineGraph` envelope), `api/routers/nextflow.py` (`CompileEdge` `from`→`src`), `api/routers/review_queue.py` (`Ticket` snapshot), the five stores (`review_store.py`/`share_store.py`/`pipeline_store.py`/`settings_store.py`/`feedback` store).

**Inspection checklist:**
1. **`types.ts` drift, field by field.** It is hand-kept (`types.ts` L1). Confirm `RunStatus`/`PipelineStage`/`ArtifactKind`(18 kinds)/`Verdict`/`Gate`/`Severity` unions still match backend bare-str values.
2. **Known stale drift: `MonitoringSignature`.** Backend serves `first_seen`/`last_seen`/`trend`(non-optional, default `'flat'`)/`affected_run_ids` (`api/main.py` ~L1250); frontend `types.ts` (~L346) still says "NOT yet served (F2)," omits `affected_run_ids`, and types `trend` as optional|null. **Confirm and quantify the render impact.**
3. **`subject_id`/`tissue` split.** Present on core `Sample` (parsed from `sample_metadata.csv`) + Accession client courier, but `SampleIn` is `extra='forbid'` — a smuggled subject field must **422**, not silently drop. Confirm no operator subject data is lost without a message.
4. **Share-merge purity.** `get_run` merges `DATA_EXPORTED` events from the **separate** `share_store` into the `lru_cache`'d ledger by `created_at`. Confirm the cache stays pure and the merge is idempotent across refetches.
5. **`content_hash` stability.** `DecisionCard.content_hash` excludes `run_id` + `metric_values` (models.py ~L287-306); `MetricValue`/`Finding` hashes exclude `id`/`created_at`. Confirm no serializer accidentally includes them.
6. **Join keys.** Card `MetricValue.metric_key` must equal runbook `QCThreshold.our_key` or the readout silently marks `not_gated` (`card_readout.py` ~L326). Confirm the germline metrics all join.
7. **Two runbook shapes.** `QCThreshold.gate` (numeric, `GET /api/config`) vs `RunbookThreshold.gate`(numeric)+`pipeline_gate`(enum, `GET /api/runbook`). Confirm they don't conflate gate meaning.
8. **Envelope round-trip.** `PipelineGraph.graph: dict[str,Any]` is stored as-is, never node-validated (`schema_version 'builder/0.1'`). Confirm byte-for-byte round-trip and that the compile-time `NfGraph` shape doesn't silently diverge; check `CompileEdge` `from`→`src` alias (`nextflow.py` ~L41) matches `NextflowGraphBody` `{from:{node,idx}}`.
9. **Origin tags.** Every artifact/lineage row must carry the run's `real-giab|synthetic|contrived|unknown` origin so a consumer never mistakes contrived for real; `RunArtifact.sha256` is null above the 8 MB cap.
10. **EventType coverage.** `ProvenanceEvent.event_type` is a bare string; the Provenance "Event trail" honors the 5 types `run_gate` emits — confirm `DATA_EXPORTED`/`ticket.actioned`/`notification.emitted` render generically, not dropped.

**Required deliverable.** A **data-lineage diagram** (text/mermaid) for: pipeline, run, ticket, agent action, tool, artifact, QC result. Plus a drift table (contract point → FE type → BE type → match Y/N → `file:line`).

**Evidence format.** `file:line` on both sides of every boundary claim; a curl/HTTP trace for any live drift.

**Golden-path intersection.** Owns the Submit→POST /api/runs→intake-status→cards→provenance→share chain end-to-end.

---

## Specialist 3 — Feature-completeness (journeys) auditor → `audit/journeys.md`

**Role.** Audit **complete user journeys**, not pages. Per journey: missing steps, dead ends, nonfunctional controls, silent failures, non-persisted state, missing confirmation/approval gates, features present in one layer but absent in another.

**Owns the journeys:**
- **A. Operate:** Accession (`/accession`) → Submit (`/submit`, identity-join-gated) → `POST /api/runs` → intake-status poll → Decision cards (`/runs/:id`) → Review queue (`/queue`) → Agent triage (`/runs/:id/agent`) → Provenance (`/runs/:id/provenance`) → Share.
- **B. Builder:** compose card graph (`/builder`) → Export to Nextflow (`POST /api/pipelines/compile`) → Run pipeline (`POST /api/pipelines/run`) → Save→Submit→Approve (`api/routers/pipelines_lifecycle.py`) → Dry-run/Diff → Open saved profile (`LoadSavedModal`, `GET /api/pipelines`).
- **C. Create-a-tool (node-authoring):** the source spec's "Domain Expansion Agent" journey.

**Inspection checklist:**
1. **Operate hop-by-hop reachability**, and RBAC: a viewer (no reviewer role) must be **403'd at `POST /api/runs`** yet still read cards/queue.
2. **Submit identity-join gate cannot be bypassed.** `canSubmit` requires `join.metadataPresent && joinApproved`; `approvedSig` is bound to the join signature so any edit re-opens approval; a "conflict" row (`join.blocking>0`) truly blocks. `sample_metadata.csv` is **required** (UIC-11).
3. **`subject_id`/`tissue` never sent** — parsed + shown, but `SampleIn` `extra='forbid'` (T-117 seam). Confirm no 422 surprises an operator and the localStorage courier (`lib/accession.ts`) is labelled.
4. **Intake "Admit (override)"** in `Intake.tsx` is local-only annotation — never a POST, never a verdict/gate mutation (G1), never persisted across refetch.
5. **CREATE-A-TOOL IS A DEAD END — CONFIRM, DON'T ASSUME.** `AuthorToolNodeModal` (`BuilderModals.tsx` ~L186) is a **static STAR `--help` mock**; its "Review kinds & add to palette" button is a **no-op** (`onClose` only) — it registers/surfaces **nothing**. The real `src/bayleaf/node_author` agent (`propose_node`, T-046) is **core-only**. **Run `grep -rn node_author api/` and `grep -rn propose_node frontend/src` and confirm BOTH are empty.** Report the missing endpoint + missing wiring as a key finding; confirm nothing in the Builder claims a proposed node was registered.
6. **"rerun" is a dead journey step.** No in-place requeue/re-execution is wired from a ticket or decision card; `resolutionNote('rerun')` is copy only; both Submit and Builder-Run **409 on a duplicate `run_id`**, so a "rerun" means a fresh `run_id`. Flag the missing loop.
7. **Repair "Send to review queue" fabricates no ticket** — it only `navigate('/queue')`. Confirm no orphaned/implied linkage between a signature-level `RepairProposal` and a sample-scoped ticket.
8. **Builder Run vs approval mismatch.** `POST /api/pipelines/run` executes the **live** graph **without checking approved status** — an unsaved/unapproved draft runs directly (only RBAC + input-kind validation gate it), sitting *beside* the Save→Submit→Approve lifecycle that governs only locators/dry-run/diff. Assess whether this is an intended demo affordance or a missing gate.
9. **Two "pipeline" objects in one Builder.** node/edge graph (Export/Run) vs profile locators (Emit/Dry-run/Diff). Confirm consistent labelling and that **Emit** (console.log only) is not mistaken for a hand-off.
10. **Review-queue tickets are DERIVED + lazily materialized.** Verify the per-key promise chain + `serverIdRef` guarantees **exactly one** `createTicket` under rapid double-actions and that resolved tickets fall out of the selectable set.
11. **BaseSpace "Pull from BaseSpace"** is a visual mock (`importRun()` reveals `SEED_SAMPLES`; no OAuth/fetch, T-057). Confirm it cannot silently claim a real import.

**Evidence format.** Per journey: a step table (Step → Control → Route/Endpoint → Works Y/N/Partial → `file:line`), screenshots at each dead end.

**Golden-path intersection.** This *is* the golden path; a broken Operate or Builder hop is Blocker/High.

---

## Specialist 4 — Integration-seam auditor → `audit/integration.md`

**Role.** Find everything that *appears* implemented but isn't fully connected. Search `TODO/FIXME/placeholder/stub/mock/sample/temporary/hardcoded`, endpoints with no callers, UI actions with no endpoint, backend capability with no UI, stores/models unused by services, agents not wired.

**Owns.** The full wiring surface: `api/routers/` (`intake.py`, `pipeline_run.py`, `nextflow.py`, `pipelines_lifecycle.py`, `review_queue.py`, `settings.py`), `api/main.py` routes, `api/*_store.py`, all six agent modules (`src/bayleaf/{triage,pipeline_repair,node_author,synthesis}`, `api/{feedback_agent,archivist}.py`), `frontend/src/api.ts` call sites, `BuilderModals.tsx`, `SettingsModelTier.tsx`, `Streamlit app/streamlit_app.py`.

**Required deliverable — the capability matrix** (one row per capability):

`Capability | UI | API | Persistence | Execution | Agent | Tested`

Populate at minimum these rows and **verify each cell against the repo, not the doc:**
1. Submit → run execution (**second execution path also exists** — `POST /api/pipelines/run`, Builder Run, `pipeline_run.py:173`; **not in CLAUDE.md's code map** — reconcile the doc drift).
2. Node-authoring agent — **core Agent ✔, API ✗, UI ✗** (T-046; grep-confirm empty).
3. `metrics-expansion` agent — **vaporware**: only a `SettingsModelTier.tsx:54` roster row (`phase2:true`, env `BAYLEAF_METRICS_AGENT`), **no backend module, env var absent from `.env.example`**. Confirm it can never read as "Live."
4. `SettingsModelTier` Save (T-045) — **UI-only local React state, no PATCH, not bound to `BAYLEAF_*_MODEL`**. Confirm no false "applied" impression.
5. `RunHandoffModal` (`BuilderModals.tsx:79`) — **orphaned dead code**: exported, **zero call sites** (superseded by `RunPipelineModal`). CLAUDE.md still describes it as the hand-off surface. Decide remove vs re-wire.
6. `PipelineRepairModal` / `ArchivistModal` — **read-wired, write-inert** ("Send to review queue" navigates only; "Queue archive" is `onClose`). No write endpoint exists.
7. Repair proposal → ticket — **no write bridge** (broken triage→queue handoff).
8. D3 Share audit — lands in the run's **Provenance trail**, **not** the Admin Activity feed (`Admin.tsx` `FeedKind` has no `share` case).
9. `GET /api/monitoring` `runs[]` — **uncapped server-side** (T-072, no `page`/`limit`), frontend render cap also removed. Payload-size risk unmitigated both directions.
10. Page-access RBAC (`access.ts`) — **VIEW-gate only in localStorage**; `api/auth.py::require_role` unchanged. Confirm no write relies on client gating.
11. `/metrics` Prometheus exporter + Grafana/Prometheus links — real exporter, but Admin links are **off-demo-path external** (`:9090`/`:3000`), not fetched in-app.
12. Streamlit app — a **parallel delivery layer** over the core; its own coverage is untracked by React-side seams.

**Evidence format.** Every matrix cell needs a `file:line` (a code location or the grep that proves absence). "Absent" claims require the grep command + empty result quoted.

**Golden-path intersection.** Owns whether each golden-path control actually reaches a backend; a UI action with no endpoint on the path is High.

---

## Specialist 5 — Reliability & failure-mode auditor → `audit/reliability.md`

**Role.** Actively try to break the system and confirm every failure yields an understandable state, a recoverable action, and an auditable record. Focus on the Nextflow execution seams and the in-process job registries.

**Owns.** `scripts/run_giab_pipeline.py` (`run_nextflow`, `_one`, parse_*), `api/routers/intake.py` (`_jobs` registry, `_bioconda_env`, timeout 900 s), `api/routers/pipeline_run.py` (`_jobs`, timeout 1800 s, `_catalog`), `src/bayleaf/nextflow/{compiler.py,catalog.py}` (`CompileError`, `_render_placeholder`), `pipelines/germline/`, `api/routers/nextflow.py` (compile 422s), `Toast.tsx`/`httpError()`, `States.tsx`.

**Inspection checklist (each failure → observed state + recoverability + audit trail):**
1. **Invalid/cyclic graph** through `POST /api/pipelines/compile` **and** `POST /api/pipelines/run` → both must return **422 with the compiler's reason** (not 500): `_topo_order` "cycle," bad-edge "unknown node"/"out of range," empty "no tool nodes."
2. **Uncatalogued tool node** → renders as a **placeholder** (`exit 1`, fails loudly on a real run) yet has a working `stub:` so `-stub-run` validates. No fabricated command.
3. **Missing reference index.** `INDEXED_REFERENCE_PARAMS={'reference'}` glob-stages `file('${params.reference}.*')`; if `.fai`/`.bwt.2bit.64` absent, the glob is empty and bwa-mem2/bcftools fail **at runtime, not compile** (no pre-flight index check). Confirm the failure is loud.
4. **Mismatched/swapped R1/R2.** Compiler/driver take reads as independent params with **no pairing/length/format validation** — force a swap and confirm a loud process crash (`check=True` → `CalledProcessError` → job `failed`), never a silent wrong result.
5. **nextflow not on PATH.** `run_nextflow()` `sys.exit`s with a PATH hint; confirm the background job flips to `failed` with the stderr tail surfaced via intake-status, and that a `uvicorn` started **without `BAYLEAF_BIOCONDA_BIN`** fails every submit at the driver — surfaced as a real toast, not a silent stall.
6. **Failed Nextflow process / partial publish.** `_one()` `sys.exit`s if any of `*.fastp.json`/`*.mosdepth.summary.txt`/`*.thresholds.bed.gz`/`*.norm.vcf.gz` is missing — a partial run is a **hard failure**, not a degraded gate. Confirm the ok-check requires returncode==0 **and** `data/<run_id>/SampleSheet.csv` exists.
7. **Duplicate run id.** 409 in both routers, guarded by `(_DATA/run_id).exists()` — flag the **race window** for two concurrent submits of the same id before either writes its dir.
8. **Backend restart mid-run.** `_jobs` is an in-memory dict + `threading.Lock` + daemon threads (non-durable). Confirm a restart loses job state, orphans `.nf-runs/<run_id>` scratch, and intake-status can only recover `complete` from disk — a `running` job becomes 404/unobservable. Verify the polling UIs degrade honestly.
9. **Subprocess timeouts** (900 s / 1800 s) flip the job to `failed` via the except-branch rather than hanging.
10. **Browser refresh / lost network during Operate** — confirm intake-status polling and the run switcher recover.
11. **Drift guard actually gates.** After a `catalog.py`/`germline.py` edit, `scripts/generate_reference_pipeline.py` must be run or `test_committed_reference_pipeline_matches_the_compiler` fails on any divergence or stray/missing file.
12. **The real execution path is UNTESTED offline.** `test_pipeline_run.py` monkeypatches `_execute` to a no-op; end-to-end `-stub-run` validity is checked only when nextflow is on PATH (skip-safe). Note that CI without nextflow yields 422 pass / 5 skip — **DAG validity unverified in the default offline suite**.

**Evidence format.** For each break: the exact trigger (input/command), the observed HTTP status / job status / toast, and the handling `file:line`. A "loud failure" claim needs the stderr tail or 4xx body quoted.

**Golden-path intersection.** Owns the live-intake reliability that sits behind Submit; but note the **recording** golden path uses pre-gated `mock_run_01`, so rank live-intake breaks by whether the demo actually exercises them.

---

## Specialist 6 — Agent safety & security auditor → `audit/agent-safety.md`

**Role.** The six advisory agents read logs/metadata/findings and can *propose* pipelines/tools/shares. Audit prompt-injection surfaces, verdict-boundary integrity, least privilege, egress de-identification, and the one tool-executing surface. **G1 is the spine: an agent that could set a verdict/confidence is a Blocker.**

**Owns.** `src/bayleaf/triage/agent.py`, `src/bayleaf/pipeline_repair/agent.py`, `src/bayleaf/node_author/agent.py`, `api/feedback_agent.py`, `api/archivist.py`, `src/bayleaf/synthesis/claude.py` + `synthesis/base.py::aggregate_verdict`; `src/bayleaf/rules.py` (`_check_route_to_human`/VAR-RTH-001), `src/bayleaf/runbook.py` (`RouteToHumanPolicy`), `api/main.py::_active_runbook`, `data/RUN-2026-07-11-CLINVAR-RTH/`; `api/safe_harbor.py` + `api/deid.py`, `POST /api/runs/{id}/share`, `api/share_store.py`; `api/routers/pipelines_lifecycle.py` (dry-run resolver), `api/routers/intake.py`, `api/auth.py`, `.env.example`.

**Inspection checklist:**
1. **Prose-only schemas.** Confirm `_ADVICE_SCHEMA`, `_PROSE_SCHEMA`×2, `_NARRATION_SCHEMA`, `_THEMES_SCHEMA` expose **no** verdict/confidence/finding/citation property the model could set (G1).
2. **Refusal + exception guards.** Each Claude agent must check `response.stop_reason == 'refusal'` **before** reading content and wrap the body in try/except → deterministic stub fallback (ADR-0006). Verify all five: triage, pipeline_repair, node_author, feedback_agent, synthesis/claude.
3. **Deterministic provenance.** citations / addressed `rule_ids` / `attach_to` / `scope` / ports / version / locators are assembled from the retriever+rules in `_assemble_*`, **not** from LLM output — provenance survives even if model text is discarded.
4. **Least privilege.** Archivist input (`RunArchiveInput`) carries **no** `subject_id`/`tissue`/`submitted_by`; its Claude payload is de-identified aggregate counts only; `_classify_kind` never opens a file. Feedback agent's Claude path receives **only** the aggregate rollup (never raw messages/ids) and has **no HTTP surface** (CLI only).
5. **Prompt-injection surfaces reaching an LLM.** Synthesizer `log_excerpts` (up to 8, `artifacts.log_lines`) + full `finding.detail`; triage `finding.detail` + `source_field`. Confirm none can escape the prose-only schema or alter the pre-computed verdict.
6. **VAR-RTH-001 integrity.** Quotes ClinVar `CLNSIG` **verbatim** (`value=hit.clinvar_significance`, `source_field=CLNSIG`); **disarmed by default** (`RouteToHumanPolicy.significances == ()`); armed **per-run** only via `_active_runbook` marker file; never mutates `DEFAULT_RUNBOOK`. It is rule-consumed evidence, **not** sent to any LLM on the gate path. Confirm the disarmed path is byte-identical to a run with no `variants.csv`.
7. **Egress scrub is egress-only.** `safe_harbor.redact_record` reads decided cards, never a gate/rule input (G1). Confirm the docstring honesty guardrail ("NOT attested HIPAA de-id; regex misses prose names") is surfaced and no HIPAA-compliant claim is made. `deid.py` is fail-closed (unrecognized column → policy default).
8. **Share endpoint hardening.** `require_role('approver')` + frontend `ConfirmDialog`; records a tamper-evident `DATA_EXPORTED` event (sha256 of exact bytes). Note the **absence** of a diff-preview, the append-only (no-rollback) posture, and the missing Admin Activity audit case.
9. **Node-author is core-only.** grep-confirm no api endpoint, no `propose_node` in frontend; `AuthorToolNodeModal` is a static phase-2 mock; Settings row is `wired:false/phase2:true`.
10. **Dry-run resolver is READ-ONLY** and flags `invalid` (not merely `missing`) for absolute/`..`-escaping locator patterns — a path-traversal guard on a client-authored graph.
11. **Only tool-executing surface.** `POST /api/runs` (intake) is RBAC-gated, regex-sanitizes `run_id`, `extra='forbid'` rejects unexpected PII fields; confirm `src/bayleaf/` core still executes nothing (grep for `subprocess`/`os.system`/`shutil.which` in `src/bayleaf/` — only `scripts/` + `api/routers/{intake,pipeline_run}.py` may shell out).
12. **Env selectors fail safe.** `get_*_agent()` must default to stub on any value other than exactly `'claude'` (stripped/lowered) — a typo can't silently enable a live agent.

**Evidence format.** `file:line` for every schema field, guard, and privilege claim; the grep + empty result for every "absent" claim.

**Golden-path intersection.** Owns the Agent-triage panel, the Share action, and the D2 fixture run — all live golden-path beats where an autonomy or egress slip would be Blocker.

---

## Specialist 7 — Scientific correctness & reproducibility auditor → `audit/science-repro.md`

**Role.** Review as an NGS platform. Audit metric units/thresholds, reference/chrom compatibility, tool-version/container pinning, provenance/reproducibility, and every UI scientific claim. Require each conclusion to distinguish **observed evidence / inference / uncertainty / recommended verification**. Respect G3/G4.

**Owns.** `src/bayleaf/metrics/{metric_registry.yaml,registry.py,mapping.py}`, `src/bayleaf/runbook.py` (`DEFAULT_RUNBOOK`, 5 required + 5 optional), `src/bayleaf/rules.py`, `src/bayleaf/models.py` (`Gate`/`_CATEGORY_GATE`, `MetricValue`, `RULE_PACK_VERSION`), `src/bayleaf/parsers.py`; `pipelines/germline/main.nf` + `nextflow.config`, `src/bayleaf/nextflow/catalog.py` (conda + container pins); data: `data/RUN-2026-07-08-GIAB-HG002/` (the **one** real run), `data/RUN-2026-07-11-CLINVAR-RTH/`, `scripts/{fetch_giab_hg002.py,giab_hg002_manifest.json,gate_giab.py,panel_regions.example.bed}`; docs `docs/data/{qc_metrics.md,metric_registry.md}`, `docs/adr/ADR-0004`, `ADR-0018`, `docs/quality/evaluation.md`.

**Inspection checklist:**
1. **Paired-end identity/ordering.** `main.nf` passes reads as `Channel.value([file(read1), file(read2)])` with **no check** that R1/R2 are matched or have equal read counts; no gate rule validates FASTQ sync. Confirm this is an accepted seam, not silently assumed correct.
2. **Reference build / chrom naming.** Reference is chr20-only (UCSC hg38, chr-prefixed) reconciled **manually** (journal 2026-07-09). Verify **no** code path asserts contig-naming/build match between reads, FASTA, and panel BED — a mismatch fails at runtime, uncaught by the gate.
3. **Tool-version / container-digest capture.** `catalog.py` pins conda version + biocontainer build **tag**, **not** `@sha256`; `nextflow.config` `nextflowVersion` is a floor (`>=23.04.0`). Confirm resolved image digests + Nextflow version are **not** captured per-run into the ledger, and label reproducibility claims accordingly.
4. **Units/thresholds.** Each `_QCMETRICS_MAP` `raw_unit` must match what the source emits (q30/reads/cluster_pf/dup=percent, coverage/variant_dp=x, breadth/pct_mapped/on_target=fraction); every `QCThreshold.our_key` must be registered (test asserts) and its `gate`/`hard_fail` in canonical units. Registry `_CONVERSIONS` is percent↔fraction only and raises on a mis-declared unit.
5. **Observed vs inference vs uncertainty.** `Finding.evidence` always carries observed value + expected/threshold + source; `DecisionCard.confidence` stays `None`; `CLNSIG` quoted verbatim (never normalized before quoting); AI narration structurally separable from rule fields.
6. **Frozen-five contract.** `q30, pct_reads_identified, mean_coverage, dup_rate, cluster_pf` stay the 5 `required=True` thresholds; adding a `QCMetrics` field without a registry entry must **surface** (`test_runbook_thresholds_key_on_registered_metrics`), not silently drop.
7. **Contrived-vs-real labelling.** **25 committed `GIAB-*` runs are `origin=contrived`** (invented values); only `RUN-2026-07-08-GIAB-HG002` is `real-giab`. Verify the UI/demo never presents contrived runs as real GIAB data, and that the chr20-downsample framing is surfaced — currently only in script docstrings/journal, **not** a `NOTE.md` in the real run dir.
8. **Variant gate completeness.** Only `variant.dp` is wired; no `INFO/AF` (gnomAD is design-only), no caller-specific filters, Ts/Tv + GQ stay ungated observations. Confirm the variant gate is honestly a call-quality stub beyond DP + route-to-human.
9. **Registered-only metrics (T-071a).** `qc.zero_cov_targets`, `qc.fold_enrichment`, `qc.fold_80`, `identity.ngscheckmate_match`, `identity.sex_concordance`, `contamination.freemix`, `variant.allele_balance` have **no parser** — verify surfaced as gaps, not implied computed. Contamination (verifybamid2 FREEMIX) is not computed for the real-GIAB path.
10. **Deterministic-rerun claim.** Confirm the compiler drift guard (`compile_graph(germline_graph()) == committed` byte-for-byte) and that "deterministic reruns" means pinned wiring + pinned versions, **not** bitwise-identical variant output (which depends on the external toolchain). No automated truth-set comparison yet (EVAL-030 planned).

**Evidence format.** `file:line` for every unit/threshold/pin claim; the observed value + source for any scientific statement; distinguish observed/inferred/uncertain explicitly.

**Golden-path intersection.** Owns the "rules-decide moment" — HG002 → HOLD on the honest `cluster_pf`-missing signal, and the CLINVAR-RTH ESCALATE beat.

---

## Specialist 8 — Demo-readiness & status-truthfulness auditor → `audit/demo-readiness.md`

**Role.** Run the recording golden path repeatedly; find clicks, pauses, nondeterminism, animation jitter, manual-cleanup points, anything that reads as mocked, and any **status indicator that lies**. Produce a deterministic demo setup checklist, exact prompts + fixtures, expected outputs, a fallback plan, features to hide, and one golden-path regression test.

**Owns.** `docs/demo/run-of-show.md` + `docs/demo/demo_plan.md` (both **last updated 2026-07-08 — stale**, describe a 6-screen app; shipped app has 12 routes), `tests/test_gate.py` (EVAL-001, `data/mock_run_01`), `app/streamlit_app.py`, `frontend/src/components/TopBar.tsx` (real health pill), `frontend/src/screens/RunOverview.tsx` (the **hardcoded "Gate online" dot**), `AgentTriage.tsx`/`AgentSourceToggle.tsx`/`AgentSubjectCard.tsx` (source labels), `Login.tsx`, `Toast.tsx`.

**Inspection checklist:**
1. **`RunOverview.tsx:130-141` "Gate online"** is a **hardcoded always-green dot with no health poll** (unlike `TopBar`'s real `api.health` pill) — it reads green during a recording even if the backend is down. **Highest-confidence status discrepancy.** Either wire it to `api.health` or relabel it.
2. **Stale phase-2 badges understate reality.** `PipelineRepairModal` (~L416) and `ArchivistModal` (~L558) still render a "phase-2" badge though both are now wired to real read endpoints. Decide drop/relabel.
3. **`AuthorToolNodeModal` static mock** must carry a prominent "roster #5 · phase-2" label so a viewer can't mistake it for a live node-author proposal (no api/frontend wiring, T-046).
4. **`SettingsModelTier` Stub·$0/Live toggle Save is UI-only** (T-045) — the narration must never imply flipping a roster "Live" toggle arms an agent.
5. **No "confidence" for a heuristic** — grep user-facing strings; per-citation score must read `N% (heuristic)`; no confidence meter anywhere (G4, T-019).
6. **Docs vs shipped surface.** Refresh or scope: the script covers 6 screens; the app has 12 routes (Accession/Inbox/Admin/page-access/Nextflow export undocumented). Nothing on screen should contradict the narration.
7. **Live-LLM beats are non-deterministic prose** — confirm the **stub is the recording default** and the AI flip degrades to stub on any error/refusal (EVAL-021) so a take can't break.
8. **Live Nextflow intake is timing/conda-env-dependent** (HG002-only, honest-skips others) — keep it **OFF** the 3-minute recording; pinned `mock_run_01` must be on screen. `app/streamlit_app.py` is the always-green fallback (its Synthesizer status is honest).
9. **Live Slack beat** ($0 no-secret variant sends nothing; presenter never reads `.env` on screen).
10. **`Submit.tsx` count = 0** before any drop (no fabricated "4 samples"); only toast "Parsed N samples" after real parsing; `SEED_SAMPLES` must not leak a pre-filled parsed count.
11. **Monitoring recharts** transitions must be deterministic given the fixed served runs and not reflow/jitter on a recording (T-072 uncapped `runs[]` is the payload-size risk).
12. **Phase-2 seams keep honest labels** — Inbox/Admin/Login (calendar OAuth, password reset, mail, mentions) must not toast a past-tense success implying a real side effect.

**Required deliverables.** (a) A deterministic demo setup checklist; (b) exact prompts + fixtures + expected outputs per step; (c) a fallback footage plan (Streamlit rung 2); (d) a "features to hide" list; (e) one complete golden-path regression test spec.

**Evidence format.** Screenshot + route for every status/label claim; the exact narration line at risk.

**Golden-path intersection.** Owns the whole recording; a lying status indicator on the hero screens is P0.

---

## Additional auditor 9 — Contract auditor → `audit/contract.md`

**Role.** A cross-boundary agreement audit across **frontend types / API schemas / core pydantic / agent structured outputs / tool manifests / execution artifacts**. Mismatched agreements across subsystem boundaries are a bigger release risk than individual bugs.

**Owns the seams:** `types.ts` ↔ `api/main.py` + `api/routers/*` + `src/bayleaf/models.py`; agent output models (`{triage,pipeline_repair,node_author}/models.py`, `NodeProposal`/`RepairProposal`/`TriageNote`/`ArchiveDigest`) ↔ their frontend renderers; `catalog.py` `PortSpec.kind` ↔ frontend `ArtifactKind`; `PipelineGraph` envelope ↔ `NfGraph`/`CompileEdge`; store record shapes ↔ readers.

**Inspection checklist:**
1. **`MonitoringSignature` stale drift** (backend serves `first_seen/last_seen/trend/affected_run_ids`; frontend says "NOT yet served," omits `affected_run_ids`, mistypes `trend`) — the single highest-value known contract break.
2. **Status enum values match:** `PipelineStatus`='pending_review' (not README's 'pending'); `TicketStatus`='in_review'; `IntakeStatus`. README §7 uses stale aliases.
3. **`ArtifactKind` (18 kinds) ↔ `catalog.py PortSpec.kind`** — reserved/unwired kinds must not fabricate a wired port; `node_author` `reserved_kinds` are structurally `PortSpec.known=false`.
4. **`CompileEdge from→src` alias** matches `NextflowGraphBody {from:{node,idx}}` exactly.
5. **`subject_id` split** — core `Sample` has it, `SampleIn extra='forbid'` rejects it — confirm no schema implies a wire path exists.
6. **`DecisionCard.confidence`** uniformly `null` across the wire; no frontend consumer renders a bar.
7. **`content_hash` exclusions** (`run_id`, `metric_values`) preserved by every serializer.
8. **Two runbook shapes** (`QCThreshold` vs `RunbookThreshold`+`pipeline_gate`) don't conflate gate meaning.
9. **`node_author NodeProposal`** structured-output contract exists but is **on no wire** (grep-confirm) — flag as a contract with no transport.

**Evidence format.** A boundary drift table: Contract point | Producer `file:line` | Consumer `file:line` | Match Y/N | Impact.

**Golden-path intersection.** Owns the invisible agreements behind every rendered card, artifact, and status.

---

## Additional auditor 10 — Truthfulness auditor → `audit/truthfulness.md`

**Role.** For an AI-heavy scientific platform, **misleading certainty is more damaging than an obvious error.** Audit whether every label / status / progress indicator / agent conclusion / success message / generated artifact accurately represents what the system has actually completed.

**Owns.** Every status string, badge, toast, and agent-output label across the app; especially `RunOverview` "Gate online," `SettingsModelTier` Stub/Live, `AuthorToolNodeModal`, `PipelineRepair`/`Archivist` phase-2 badges, `AgentTriage`/`AgentSourceToggle`/`AgentSubjectCard` labels, `Submit` "Parsed N samples," `Login`/`Admin`/`Inbox` phase-2 disclaimers, `Provenance` "params hash · execution trace — phase 2," `BuilderConsole` sarek YAML.

**Inspection checklist:**
1. Does any indicator claim liveness it doesn't have? (**"Gate online" hardcoded green** is the flagship case.)
2. Does any button imply a persisted/side-effecting action that is inert? (Queue archive, Send to review queue, Settings Save, Save draft, password reset.)
3. Does any agent surface present advisory prose as a confirmed verdict, or a heuristic score as "confidence"?
4. Does any success toast fire before/without the real backend outcome? (Confirm `Toast` + `httpError()` surface real 403/409/422/503.)
5. Does any "N samples parsed / N events → M cards" number reflect real state, or a hardcoded value?
6. Does any phase-2 label **overstate** (understating badge on a now-wired modal) or **understate** (static mock that looks live)?
7. Are contrived runs ever presented as real GIAB data (cross-check Specialist 7)?

**Evidence format.** Per finding: the exact on-screen string + route + screenshot, the code that produces it (`file:line`), and the true state it misrepresents.

**Golden-path intersection.** A truthfulness defect on a hero screen is P0 regardless of functional correctness.

---

## MASTER instruction (prepended to all 11 agents)

You are one agent in a **release-hardening audit of bayleaf** under a hackathon deadline. The objective is **NOT** to expand scope, redesign, or propose speculative features — it is to make the **existing** golden path coherent, integrated, reliable, scientifically credible, and demo-truthful. **Do not modify production code** (a maintainer may be concurrently editing Builder files). Inspect the complete repo — frontend, API routers, core (`src/bayleaf/`), pydantic models, stores, Nextflow codegen + committed pipeline, agent prompts + schemas, fixtures (`data/`), tests, docs, `.env.example`, config. **Do not infer a feature works because files exist — trace it and, where possible, drive it.** Where a ground-truth map marks something stub / phase-2 / absent, **verify reality; do not assume it works.** Honor guardrails **G1–G7** above (rules decide / AI advises; offline-first stub-default; not clinical; heuristics ≠ confidence; read-only; scale-aware; explicit-edit+audit).

**Every finding uses this exact schema:**
> Finding ID · Title · Severity (Blocker/High/Medium/Low) · Confidence (Confirmed/Probable/Possible) · Area + affected journey · exact evidence (file paths + line numbers) · reproduction steps · expected behavior · actual behavior · likely root cause · minimum viable fix · larger architectural fix (only when materially useful) · Demo-critical (Y/N) · risk of fixing immediately · suggested regression test.

**Classify each finding into exactly one of 7 categories:**
1. confirmed defect
2. incomplete integration
3. design inconsistency
4. missing user-facing state
5. scientific-correctness risk
6. security-or-agent-autonomy risk
7. post-hackathon improvement

**No vague findings.** Never write "improve error handling" or "make the UI consistent." Name the exact component, the exact inconsistency or failure condition, and the smallest concrete remediation. **Prioritize preserving the working golden path over refactoring.**

**The bayleaf golden path (anything that breaks it is Blocker/High):**

*Operate flow (recording default uses pre-gated `data/mock_run_01`; live intake is off-recording):*
1. **Accession** (`/accession`, client-side CRM, `lib/accession.ts` courier) → **Submit** (`/submit`, real Illumina-v2/plain-CSV parse, **required** `sample_metadata.csv` human-approved identity join) → **`POST /api/runs`** (`api/routers/intake.py`, RBAC reviewer/approver, `SampleIn extra='forbid'`).
2. **Intake-status poll** (`GET /api/runs/{id}/intake-status`) while the **Nextflow-first driver** (`scripts/run_giab_pipeline.py` runs `pipelines/germline/main.nf`, HG002 fixture only) publishes QC → `data/<run_id>/` frozen-five CSVs → `run_gate`.
3. **Runs list** (`/`, `RunOverview`, `GET /api/runs`, real status dots) → **Intake gate** (`/runs/:id/intake`) → **Decision cards** (`/runs/:id`, `RunDetail`, `GET /api/runs/{id}/cards/{sid}/qc-readout`; **verdict rule-decided, READ-ONLY per G1**).
4. **Review queue** (`/queue`, ticket lifecycle, confirm-gated) → **Agent triage** (`/runs/:id/agent`, `GET .../triage`, advisory stub default, "heuristic" not "confidence") → **Provenance** (`/runs/:id/provenance`, event trail + artifact download + **approver-only** `POST /api/runs/{id}/share` de-id egress) → **Monitoring** (`/monitoring`, `GET /api/monitoring`).

*Builder flow:*
5. **Pipeline builder** (`/builder`) compose card graph → **Export to Nextflow** (`POST /api/pipelines/compile`, `NextflowExportModal`, compose ≠ execute) → **Run pipeline** (`POST /api/pipelines/run`, `RunPipelineModal`, real execution via the same driver) → **Save→Submit→Approve** lifecycle (`api/routers/pipelines_lifecycle.py`, RBAC) → **Dry-run/Diff** (real endpoints once Saved).

*Rules-decide demo beats:* HG002 → **HOLD** (honest `cluster_pf`-missing) on real intake; `data/RUN-2026-07-11-CLINVAR-RTH/` → **ESCALATE** via VAR-RTH-001 quoting ClinVar verbatim.

**Save your report to `audit/<specialty>.md`** (or, per the Fable-compatibility block, emit it verbatim into your output slot). Rank Blockers first.

---

## Synthesis agent instruction → `audit/SYNTHESIS.md`

You receive all 10 specialist reports. **Do not concatenate.** Produce a decision-grade release plan:

1. **Deduplicate** overlapping findings (many will name `RunOverview` "Gate online," the `MonitoringSignature` drift, `node_author` being unwired, `SettingsModelTier` T-045, the inert repair/archive CTAs, uncapped `/api/monitoring runs[]`).
2. **Resolve contradictions** between specialists; where two disagree, state which you verified and how.
3. **Independently verify every Blocker** — re-read the cited `file:line` or re-drive the route before promoting it. A Blocker you could not reproduce is demoted to Probable with a note.
4. **Group symptoms under common root causes** (e.g. hand-kept `types.ts` drift; stale demo docs; inert phase-2 CTAs; in-memory job registry non-durability).
5. **Identify fixes that resolve multiple findings** (one relabel/rewire that clears several truthfulness items).
6. **Estimate effort per fix:** `<30 min` / `30–90 min` / `2–4 hr` / `post-hackathon`.
7. **Avoid risky refactors before submission** — never recommend a broad refactor that endangers the working golden path; prefer the minimum viable fix.
8. **Produce a release checklist** (pre-recording go/no-go items, each tied to a P0/P1).

**Final output is ONLY these four prioritized sections (bayleaf-specific):**
- **P0 — must-fix before recording:** breaks the Operate or Builder golden path, corrupts/mislabels data, is scientifically misleading, an obvious security/agent-autonomy failure, or a hero-screen status that lies (e.g. hardcoded "Gate online" reading green while offline).
- **P1 — fix before submission if possible:** visible inconsistency, incomplete integration on a path a viewer might touch, confusing failure, or a high-probability demo issue (e.g. stale phase-2 badge that understates a wired modal; a live-agent beat that could 500 without the stub fallback).
- **P2 — hide or document:** incomplete features that are fine **outside** the demo when clearly disabled/labelled (BaseSpace mock, `AuthorToolNodeModal`, Inbox connectors, Median-review KPI, Settings model-tier Save, node-author agent).
- **P3 — post-hackathon backlog:** genuine improvements with no golden-path bearing (subject_id server persistence, `/api/monitoring` pagination, container `@sha256` pinning, durable job store, interpretation/metrics-expansion agents, truth-set eval EVAL-030).

---

## Critical framing (read last, applies to every **Track-A audit** agent)

**Do not reward finding more work.** Reward **reducing uncertainty around the existing golden path.** A confirmed, reproduced defect on the Operate or Builder flow — with a `file:line`, a repro, and a minimum viable fix — is worth more than ten speculative "could be better" observations. When a map says something is a stub/phase-2/absent seam, your job is to **confirm the label is honest and prominent**, not to build the missing feature. **Preserve the working golden path over any refactor.** If a fix's risk exceeds its golden-path benefit before submission, it belongs in P2 or P3, not P0.

> Track A above is the release-hardening audit (mandate: **do not expand scope**). **Track B below is the opposite mandate** — grounded feasibility design for *new* wishlist features — and is fenced off so the two never bleed together. A Track-A agent never reads Track B, and vice-versa; each agent's prompt scopes it to exactly one track.

---

# TRACK B — Wishlist feasibility (grounded implementation design)

## Purpose (Track B)

For each maintainer wishlist item, uncover **the best way to implement it in *this* codebase** — not whether it's a good idea, but *how* it should be built given the real architecture. Each item gets a grounded **design proposal**: candidate approaches tied to the actual files/seams they'd touch, a recommended path, the smallest first slice, effort, risks, and guardrail/golden-path impact. Output is design intelligence that can seed an ADR + `tasks.md` entries — **not** code. This track **does** propose new scope (that's its job); it stays honest by grounding every approach in real seams and by respecting the guardrails as **hard design constraints**.

## Track-B master instruction (prepended to every Track-B agent)

You are a **grounded implementation-design** agent for a bayleaf wishlist feature. Your job is **not** to audit and **not** to code — it is to find the **best way to build this feature in the existing codebase**, grounded in real files, patterns, and seams. Read the repo the way an architect would before writing an ADR. Honor guardrails **G1–G7** as **non-negotiable design constraints**, not suggestions:
- **G1/ADR-0001:** rules decide the verdict/confidence; any new feature keeps AI advisory and off the deterministic critical path. A design that lets a feature set/override a verdict is disqualified — say so.
- **G2:** offline-first, stub-by-default, $0 baseline — a new LLM seam must ship stub-first with a deterministic fallback and a `BAYLEAF_*` selector.
- **Ports & adapters / ADR-0016:** reuse the existing pluggable-store shape (jsonl|sqlite|postgres, degrade-to-jsonl), the RBAC dev-shim (`api/auth.py::require_role`), the event ledger, the shared frontend primitives (`Tabs`/`Bar`/`Toast`/`ConfirmDialog`/`Pager`), and the six-agent seam pattern **before** inventing a new abstraction. Name the existing thing you'd reuse.
- **G3/G4:** no clinical claims; heuristics ≠ confidence.
- **G6/G7:** scale-aware (dropdowns + pagination, never infinite rows / pill-per-item); every mutation explicitly selected + saved + audited + confirm-gated.
- **compose ≠ execute** stays: the core (`src/bayleaf/`) never shells out; only `scripts/` + `api/routers/{intake,pipeline_run}` may.

**Method — a design panel per item.** Produce (or, in the fan-out, three agents each produce) **2–3 genuinely distinct approaches**, then recommend one. Each approach must name the **real files/seams** it touches and the **existing pattern** it extends. Prefer the **smallest MVP slice with production-ready seams** over a big-bang build.

**Output schema per wishlist item → `audit/wishlist/<Wn-slug>.md`:**
> Item ID · Feature (one line) · User value + which persona/journey · **Approaches** (2–3; each: sketch · real files/seams touched `file:line` · reuses-existing-pattern · pros · cons · guardrail fit) · **Recommended approach + why** · **Smallest first slice (MVP seam)** · Effort (`spike-needed` / `<½ day` / `½–1 day` / `multi-day`) · Risks & tradeoffs · **Guardrail/ADR-0001 impact** · Golden-path impact (does it touch the demo path? should it?) · New ADR + `tasks.md` entries it would spawn · Open questions for the maintainer. Distinguish **grounded-in-code** from **assumption** explicitly.

## Wishlist items (maintainer-supplied, grounded 2026-07-11)

Four items, each a **"clean implementation" of already-roadmapped work** — grounded below against real `file:line` so the design panel starts from truth. **Interlock:** W1 (run-path generality + catalog coverage) and W2 (authoring → catalog entries) share the **`ProcessSpec` seam** and the **compose≠execute trust boundary**; W3 adds new cards + provenance stages that W1's compiler and the Provenance surfacing must handle; W4 (execution model — per-sample-parallel via SLURM, local-serial fallback) extends W1's compiler + driver and is exercised by the multi-sample E2E. **Naming caution for agents:** these `W1/W2/W3` are the *maintainer's* numbering — they do **not** match the unrelated `W1/W2/W3` rows in `scope-and-wishlist.md` (webhook/container/etc.), and there is no literal `W1/W2/W3` id in `tasks.md`; use the roadmap anchors named per item.

---

### W1 — The Pipeline Builder actually builds *working* Nextflow workflows via the compiler

**Intent (maintainer):** whatever an operator composes on the canvas compiles to a *runnable* Nextflow workflow and executes cleanly — not just the seeded germline graph.

**Grounded interpretation:** **Compile is already fully general** — `POST /api/pipelines/compile` (`api/routers/nextflow.py:74-110`) compiles an *arbitrary* posted graph to a **stub-runnable** bundle for any topology of any cards, and `POST /api/pipelines/run` (`api/routers/pipeline_run.py:173-239`) executes the operator's **live canvas graph** (compiled fresh at `:187-189`). So "builds working Nextflow" is largely there for **compile + `-stub-run`**; the real gap is **real execution beyond the germline chain**, coupled in four specific places.

**The gap (what "clean" adds):**
1. **Catalog = 7 tools** (`catalog.py:66-217`); an uncatalogued card → an **honest placeholder that `exit 1`s** (`compiler.py:227-249`, never a fabricated command). But the palette *offers* uncatalogued cards (e.g. NGSCheckMate, `BuilderShared.tsx:217`) → run hits the placeholder.
2. **Run path hardcoded to germline:** the driver always passes `--read1/--read2/--reference/--panel_bed` (`scripts/run_giab_pipeline.py:121-127`); only 3 input categories are runnable (`_KIND_TO_CATEGORY`, `pipeline_run.py:46`); and the **post-run parse hard-fails unless the four germline outputs exist** (`run_giab_pipeline.py:275-279`) — so a non-germline graph reports "failed" even when Nextflow *succeeded*.
3. **Inputs = server fixtures only**, no upload / bring-your-own-data (`_catalog()`, `pipeline_run.py:59-88`).
4. **Run executes the live graph on RBAC role alone** — no approved-status check (`pipeline_run.py:187-189` vs the T-049/T-052 draft→approve lifecycle).

**Seams to reuse:** the `ProcessSpec`+`Port` extension point (`catalog.py:22-59,66`; add a tool = one frozen spec, no compiler change); `required_inputs(graph)` already generalizes external-input discovery (`compiler.py:74-89`); the `_execute`+`_jobs` execution seam (`pipeline_run.py:242-281`); the `RunPipelineModal` category→dropdown picker (`BuilderModals.tsx:848-1026`); the drift guard + generator + **live `-stub-run` gate** (the honesty check for any new pipeline, `tests/test_nextflow_compile.py:156-181`).

**Guardrail tensions to resolve:** compose≠execute (all execution stays in `scripts/`+`api/`, never core); **generalize output parsing** rather than loosen the honest fail; hand-curated (trusted `script:`) vs agent/schema-generated specs (the W2 link); approval-vs-execution (should an unapproved live graph be runnable?).

**Roadmap anchors:** **T-123** (built the compiler + Nextflow-first intake; its open remainder *is* W1 — it explicitly disclaims "any card runs"), **wishlist #9** (nf-core `nextflow_schema.json`→form importer — the natural mechanism to onboard arbitrary tools, **unbuilt/XL**), **#11** (visual builder).

**Design-panel should weigh:** (A) generalize the run path (graph-driven params + output parsing + wider input categories) so any *all-catalogued* graph runs — smallest, keeps curation; (B) the nf-core schema-form importer (#9) to onboard arbitrary tools/params — scalable, bigger, ties to W2; (C) a "runnable tier" — the Builder honestly marks execution-ready (catalogued+parsed) vs compose-only (placeholder) cards, generalizing incrementally.

**Resolved (2026-07-11):** (1) **No BYO-data upload for now — but PIN the seam:** `_catalog()` stays fixtures-only; reserve an upload path as a labelled future extension, don't build it. (2) **A real run MUST require an approved pipeline version** — gate `POST /api/pipelines/run` on the `PipelineGraphStore` approved status (today it executes the live graph on RBAC role alone, `pipeline_run.py:187-189`), tying execution to the draft→approve lifecycle. (3) The E2E covers **all inputs (samplesheet + metadata) → report generation** (shared with W3's acceptance test). **New cross-cutting thread to uncover:** requiring an approved version + the RBAC role model drives **substantial UI updates** — run controls gated on approval, submit/approve/run flows surfaced, role-appropriate affordances — *uncover these during the design* (this is also a Track-A UI/UX + journeys concern; the panel should produce the UI-change inventory, not just the backend gate).

**Still open:** which non-germline pipeline is the first real target (WES / the panel / a second reference pipeline)?

---

### W2 — Scoped, versioned authoring agents in an accessible library (+ a boundaries MD)

**Intent (maintainer):** authoring agents whose output can be incorporated into a pipeline in a **scoped** way, **versioned to the platform version**, **added to an accessible agent library** — governed by an **MD** defining how such an agent is built and what it may do.

**Refinement (2026-07-11) — the PRIMARY thing to uncover is the scaffold + constraint contract.** Less "wire the existing modal," more: *what exact scaffolds and constraints must exist for such an authoring agent to operate safely and repeatably.* This resolves the earlier tools-vs-agents fork: it is a **card/tool-authoring agent**, plus the **general convention for how any agent is made and incorporated**. The design panel's headline output is that contract (a real MD), enumerated next.

**Resolved (2026-07-11):** the scaffold governs **both** — authoring pipeline **cards/tools** *and* authoring **new advisory agents** — and the **"accessible agent library" IS the existing six-agent roster** (synthesizer / QC-triage / pipeline-repair / feedback / archivist / node-author, surfaced in Settings), which we want to make **cleanly expandable** to a 7th/8th agent. So the "library/registry" work targets the roster + its `BAYLEAF_*_AGENT` seams + the Settings roster UI, governed by the scaffold MD — not a greenfield store.

**Grounded interpretation:** productionize the existing node-authoring agent (`src/bayleaf/node_author/`, T-046) — today **core-only**, **corpus-bound to a fixed 11-card table** (`knowledge/tool_cards.jsonl`), **advisory/prose-only**, with **no doc-drop parser** (narrower than its own design note) — into a wired capability whose proposals become **scoped, versioned, human-approved library entries**. The Builder's `AuthorToolNodeModal` (`BuilderModals.tsx:186`) is a **static STAR mock** with no accept handler and no endpoint (`grep node_author api/` + `grep propose_node frontend/src` both empty).

**The gap (four sub-goals):** (a) **scoped incorporation** — nothing consumes `NodeProposal`; no `NodeProposal → Builder card → ProcessSpec` path; "which pipeline/stage a node may join" is unmodeled. (b) **versioned to platform version** — proposals pin tool + corpus (`NODE_AUTHOR_CORPUS_VERSION`) + schema versions, but **nothing binds to a platform version** (only unreferenced `pyproject.toml:7` `0.1.0`). (c) **accessible library/registry (= the six-agent roster, to be made expandable)** — today adding an agent means editing code + `.env.example` + the client-only Settings roster (T-045); there is **no governed "add an agent/tool to the library" path**, and the tool-card corpus is a hand-curated flat JSONL. (d) **boundaries MD** — no per-agent capability contract exists.

**The crux tension (resolve this first):** an authored node is "advisory" **only as a proposal**. The moment it becomes a real card reaching **compiler → `nextflow run`**, it crosses into **execution**. Today's safety rests on a hard seam: the agent proposes **ports/version/locators only, never a `script:`/`stub:` body** — those live solely in the hand-curated `ProcessSpec` catalog; an uncatalogued tool → placeholder, never a command. **A human must author the `ProcessSpec`.** W2's "scoped incorporation" must keep this seam explicit — otherwise agent-authored metadata becomes a route to arbitrary command execution.

**Seams to reuse:** the six-agent `stub|claude` seam (`get_node_author_agent`; mirror the read-only `GET /api/monitoring/signatures/{sig}/repair` shape); the **versioned `PipelineGraph` envelope + draft→approve lifecycle** (`api/pipeline.py`: `PipelineStatus draft|pending_review|approved`, monotonic `version`, `submitted/reviewed/approved_by`, `extra="forbid"`, pluggable store) — the ready-made template for *both* versioning **and** scoped approval; RBAC (`api/auth.py`, `require_role`); the retrieval `Protocol` (swappable; the corpus JSONL is the registry's natural home).

**PRIMARY DELIVERABLE — the authoring-agent scaffold + constraints contract (a real MD the panel must design).** Enumerate, each grounded in the real seam, exactly what such an agent receives and must obey:
1. **The templates it authors *into* (never around).** The `ToolCardEntry` corpus schema (`knowledge/tool_cards.jsonl`), the `NodeProposal`/`PortSpec` output model (`node_author/models.py`), and the *target* `ProcessSpec`/`Port` card template (`catalog.py:22-59`). The agent fills these shapes — it **never** authors a `script:`/`stub:` body.
2. **Rules for interacting with the Nextflow integration.** How a proposal maps `NodeProposal → ProcessSpec → compile_graph → nextflow run`; the hard rule that it emits **ports/version/locators only** (a human authors the runnable `script:`/`stub:`); uncatalogued → **placeholder `exit 1`, never a fabricated command** (`compiler.py:237-245`); the typed-port/`ArtifactKind` vocabulary (unknown → `reserved`/unwired via the structural `PortSpec.known`); and the **drift-guard + live `-stub-run` gate** any new tool must pass before it is "runnable."
3. **UI do's and don'ts.** Proposals surface as **advisory**, **never auto-added** (a human accepts); no false "Live"/overstated phase-2 labels (cf. the Track-A truthfulness findings); reserved-kind chips are **shown, not wired**; the accept action is **confirm-gated + audited** (explicit-edit house rule); scale-aware.
4. **Conventions for how any agent is made + incorporated.** The six-agent `stub|claude` seam: env selector `BAYLEAF_*_AGENT`/`_MODEL`, lazy `anthropic` import, **degrade-to-stub on any error incl. refusal**, **prose-only schema**, `advisory: Literal[True]`, **off the deterministic critical path** (ADR-0009/0012, G1); required tests + a `.env.example` entry; and where it registers in the library/roster. Seed doc to extend: `docs/design/agents.md`.

Plus the pins the MD must fix: capability limits (**metadata not commands**; only `ARTIFACT_KINDS`; **no verdict/confidence** — G1); review/approval (draft→pending_review→approved; inert until a human accepts *and* authors the ProcessSpec); versioning (tool version **and** platform version **and** corpus/schema); reserved-vs-known kinds = a **governed registry change, never a fabrication**.

**Roadmap anchors:** **T-046** + **scope #5** (node-authoring — both list the honest gaps), **#9** (nf-core schema→form importer — the doc-drop mechanism, unbuilt), **#11** (builder save/version/approve backend). Design source: `docs/design/node-authoring-agent.md` ("Next slices"), `docs/design/agents.md`.

**Design-panel should weigh:** (A) wire the *existing* corpus-bound agent end-to-end (read-only endpoint + modal → proposal → human-approved catalog entry), versioned + scoped — minimal, no new authoring power; (B) add the **doc-drop importer** (the design note's original vision + #9): `nextflow_schema.json`/`--help`/README → propose a genuinely new tool → human authors the ProcessSpec — the real "bring your own tools"; (C) the **library/registry as a first-class system** (a versioned tool-card store reusing the pluggable-store shape + a platform-version stamp + a library UI), with the boundaries MD as the governing contract.

**Open questions for maintainer (resolved: library = the six-agent roster, expandable; scaffold governs both card- and agent-authoring):** "Versioned to the platform version" — pin to `pyproject.toml` version or a dedicated platform/pipeline-version constant (panel to propose)? Who approves a roster/library addition — the approver role, or a stricter governance role (given a new agent adds capability)?

---

### W3 — Surface the downstream-of-variant-calling steps in Builder cards + Provenance

**Intent (maintainer):** the downstream processes after variant calling that we've built but not surfaced through Builder pipeline cards and Provenance.

**Grounded interpretation + premise corrections:** the reference pipeline **stops at `bcftools norm`** (filter/normalize; `main.nf:19-25`) — nothing after. **Built-but-unsurfaced downstream capabilities:** route-to-human (**VAR-RTH-001**, `rules.py:332-404`, off by default), ClinVar-annotation reading (`parsers.parse_variant_calls`), the variant gate (`variant.dp`, `runbook.py:157-165`), and **de-id/share** (D3, surfaced today only as a `DATA_EXPORTED` *event*). **NOT built — design-only, so these need *building* first, not merely surfacing:** contamination/verifybamid2, the interpretation agent/`RunReport`/gnomAD; **NGSCheckMate has a card but no `ProcessSpec`** → placeholder. Also: there is **no `PipelineStage` enum in `models.py`** — provenance stages live in `frontend/src/types.ts:127` (`intake/demux/qc/align/variant/gate`).

**The gap per page:** **Builder cards** — no annotation, route-to-human/interpretation/report, contamination, or share card; NGSCheckMate is the half-built pattern (card, no backend spec). **Provenance** — `STAGES` (`Lineage.tsx:13-20`) has no filter/annotate/route-to-human/interpret/share stage; `norm`'s `.norm.vcf.gz` **collapses into the "variant" stage** (`_ARTIFACT_STAGE`, `main.py:558-582`). **Concrete honesty bug:** in the RTH fixture the *variant stage node reads "skipped / not run"* even though **VAR-RTH-001 fired an ESCALATE** — the route-to-human escalation is **invisible on the Lineage DAG** (it shows on the terminal gate node, the Event trail, and the card, but not the variant stage node). Share is an event, never a stage.

**Seams to reuse:** add a `ProcessSpec`+card (NGSCheckMate = the worked half-example); extend `PipelineStage` (`types.ts:127`) + `STAGES` (`Lineage.tsx:13-20`) + `_ARTIFACT_STAGE` (`main.py:558-582`) with **honest "not run in this build"** status (`Lineage.tsx:94-116`); `DATA_EXPORTED` is the template for surfacing a downstream event without it being a gate; the runbook gate readout; the `RepairProposal` advisory pattern for an interpretation surface.

**Guardrail tensions:** G1 (a surfaced card/stage is a **location, never a verdict** — the *rule* emits the ESCALATE); G3/G4 (quote ClinVar **verbatim**, never author pathogenicity; ACMG surfaced-as-input, never emitted); honesty (a stage not actually run reads "not run in this build" — **fixing the RTH "skipped-while-escalated" inconsistency is the anchor case**, and is arguably also a Track-A truthfulness finding); compose≠execute (an uncatalogued downstream card → placeholder, never a fabricated command).

**Roadmap anchors:** **ADR-0018 P4 "Honest provenance stages"** (lines 75-77) — the exact follow-up; `docs/design/variant-interpretation.md §2` (lines 107-109) names the gap **verbatim** ("the `PipelineStage` enum + the provenance DAG `STAGES` gaining filter/annotate/interpret/report entries … is also still unbuilt"); §1.8 (Report tab on RunDetail); **T-017** (contamination); scope #6/#14/#20.

**Design-panel should weigh:** (A) **pure surfacing of what's built** — add filter + route-to-human + share as honest Provenance stages/events (fix the "variant node skipped while ESCALATE fired" bug) + Builder cards for the built downstream steps; label design-only steps "not run in this build"; (B) add the **annotation card + stage** (the missing step between call and route-to-human), incl. an annotate `ProcessSpec` (or honest placeholder); (C) the **interpretation Report surface** (ADR-0018 §1.8) — a RunDetail Report tab + per-variant advisory panel reusing the `RepairProposal` pattern; bigger, ties to the (design-only) interpretation agent.

**Maintainer refinement (2026-07-11) — expands W3 from "surface" to "build + wire + prove":**
1. **Wire the full port graph end-to-end — all imports + every reserved/optional port → a relevant output location.** Concretely: **(a)** every **import/source node** (FASTQ input, Reference FASTA, Panel BED, Truth VCF, samplesheet, metadata) wired to the card input ports that consume it; **(b)** every **reserved** output port registered + wired (today `fastp_html`, `samtools_stats`, … sit in the `ARTIFACT_KINDS` mirror as *reserved — surfaced, never wired*, `node_author/models.py:47,214`; `docs/design/builder-cards/README.md §5`); **(c)** every **optional** output port routed to its relevant destination — a downstream **consumer** (MultiQC, the gate/QC readout, the Report tab) or a **file-output node** (the published-output nodes added in `e5cb6d7`). **Grounded gap (verified in `catalog.py`):** MultiQC's `inputs` cover only `fastp_json` + `markdup_metrics` + `mosdepth_summary` — so `mosdepth_thresholds`, `bai`, and the reserved `fastp_html`/`samtools_stats` are **dangling**, and terminal `filtered_vcf`/`multiqc_json` need explicit published/file-output locations on the canvas. Also fold in the card-only-no-spec tools (NGSCheckMate) so the palette is fully runnable, not partly placeholder. **Coupling:** this is a shared W1 (the compiler wires channels *from edges* — an unwired port simply isn't emitted downstream) + W3 (downstream/Report surfacing) concern, and the E2E exercises the *complete* graph. *(Re-ground the exact reserved-kind list + file-output-node wiring when the Builder session lands — `e5cb6d7` just added file-output nodes and `BuilderShared` is mid-edit.)*
2. **A full end-to-end test** — from **sample + metadata sheet creation** (Accession → Submit identity-join) **through report**, **ideally driven through the Pipeline Builder** (compose → compile → run), not just the hardcoded intake. This E2E is effectively the **acceptance criterion for W1 + W3 together** (W1 makes the Builder-composed graph runnable; W3 adds the downstream cards + stages + report it must reach). **Sequenced: after the current planning wraps *and* after the concurrent Builder session lands** (see Queued deliverables below).

**Scope-honesty (active pushback, per the maintainer's own "flag over-broadening" rule):** "wire *all* cards" and "through *report*" span from trivial to not-demo-feasible, so the design must tier them honestly:
- **Buildable now** (tool in the `hackathon` conda env, just needs a `ProcessSpec` script/stub): straightforward — e.g. an annotation tool, an identity check with an installed binary.
- **Needs real setup / not installed:** some reserved tools have no binary/container available in the demo env — those stay honest placeholders (`exit 1`), not fake-green.
- **Design-only (needs *building*, not wiring):** contamination/verifybamid2 (T-017), the interpretation agent + gnomAD, and **the "report" itself** (ADR-0018 §1.8 is design-only — there is *no* report surface today). "Through report" therefore requires **building at least a minimal report** (or defining "report" = the decision-card + provenance summary that already exists). The panel must say which.
The clean end-state is: the E2E runs green for the real germline + built downstream, and every not-yet-runnable card reads an **honest "not run in this build"/placeholder** — never a fabricated pass.

**Resolved (2026-07-11):** W3's immediate Track-B output is **documentation** (the build brief) — but the goal is to **build and harden**. **"Report" = option (a): BUILD a real RunDetail Report tab** (ADR-0018 §1.8 — a per-variant advisory panel + honest downstream provenance stages); the E2E **terminates in that built Report surface**, not the stopgap decision-card/provenance summary. **MVP it over EXISTING downstream data** — `VariantCall` (ClinVar quoted **verbatim**, never authored pathogenicity — G3/G4), route-to-human findings, gate outcomes, provenance — so **no interpretation agent is required for v1**; the fuller interpretation layer (gnomAD / `AnnotatedVariant` / `PriorityTier`, design-only) stays a later slice. The RTH Lineage "skipped-while-escalated" bug is **in scope to fix** (also a Track-A truthfulness finding). This upgrades W3's design-panel option **C (the interpretation Report surface)** from "one option" to the **committed target**, with A (surface built downstream) + B (annotation card/stage) as supporting slices beneath it.

**Still open:** which reserved/optional cards are in scope given tool availability (I'll enumerate installed-vs-not during the build)? Must the E2E run through the **Builder** (compose→run) for every step, or is the intake path acceptable where the Builder can't yet drive one?

---

### W4 — Nextflow execution model: per-sample-parallel via SLURM by default, local single-thread-serial fallback

**Intent (maintainer):** default behavior = **embarrassingly parallel sample processing via SLURM job submissions** when SLURM is available; if not, **standard single-thread processing, one sample at a time**.

**Grounded current state (verified):** the pipeline is **single-sample and local-only**. `main.nf:15` = `ch_reads = Channel.value([file(params.read1), file(params.read2)])` — a **single-sample value channel**, no per-sample fan-out from a samplesheet. `nextflow.config` profiles = `conda|docker|singularity|stub` (**no `slurm`, no executor config**, just `process.cpus = 2`); the compiler's `_render_config` (`compiler.py:326`) emits that same set. The driver (`scripts/run_giab_pipeline.py`) passes **no `-profile`** and does **no scheduler detection** → today everything runs on Nextflow's local executor, one sample.

**The gap (three pieces):**
1. **Per-sample fan-out (the "embarrassingly parallel" part).** Restructure the *emitted* `main.nf` input from a single-sample `Channel.value` to a **per-sample queue channel** (samplesheet → `splitCsv` → one item per sample → each sample's chain runs independently). Parallelism is **across samples**; within a sample the chain stays ordered. A **compiler change** (`compiler.py` emits `main.nf`) + samplesheet-driven input — **required by the E2E's multi-sample samplesheet regardless of scheduler**.
2. **SLURM executor profile + auto-detect default.** Add a `slurm` profile (`process.executor = 'slurm'` + queue/resource directives, nf-core `conf/`-style) to the emitted `nextflow.config`, and have the driver **auto-detect** (`shutil.which("sbatch")`) → pass `-profile slurm` when present. On SLURM each per-sample process invocation is submitted as a job → embarrassingly parallel to cluster capacity.
3. **Local single-thread serial fallback.** No `sbatch` → a `standard` local profile with `executor.queueSize = 1` / `process.maxForks = 1` + `cpus = 1` → **one sample at a time, single-threaded** (overrides today's `cpus = 2`).

**Seams to reuse:** `_render_config` (`compiler.py:326`) is the single emission point for profiles (extend it, never hand-edit the committed config); the driver's existing `shutil.which` pattern for scheduler detection; ADR-0003's portability story (same graph, executor by profile); nf-core executor-profile conventions (`docs/data/nf-core-conventions.md`); the drift guard (`generate_reference_pipeline.py` + the byte-for-byte test) so a new profile flows through cleanly.

**Guardrail / scope tensions (active pushback):** the demo `hackathon` conda env almost certainly has **no SLURM** — so the demo default is the **local-serial fallback**, and the SLURM path is **buildable + unit-testable** (detection branch + config emission + `-stub-run` DAG validity) but **not live-verifiable without a cluster**. Be honest: test the *branch* (`sbatch` present → slurm profile chosen) and the fallback; label the SLURM path **config-verified, not cluster-verified** — don't claim a run we can't produce. compose≠execute holds (core emits text; driver/`api` own execution). Per-sample fan-out also changes the intake job model (many samples in flight) — the in-memory `_jobs` registry + intake-status polling must report **per-sample/per-run state honestly**.

**Roadmap anchors:** **ADR-0003** (Nextflow carries compute portability — this realizes the executor-profile half); **T-123** (the compiler + driver this extends); `docs/data/nf-core-conventions.md`. Couples to **W1** (compiler + run path) and the **E2E** (multi-sample samplesheet → per-sample parallel).

**Open questions for maintainer:** SLURM queue/partition/account + per-process resource labels — hardcode sensible defaults or config/`.env`-drive them? A container profile (singularity, common on HPC) alongside `slurm`, or conda-on-PATH only? A max-parallel cap (`executor.queueSize` for slurm) or unbounded?

---

## Queued deliverables (post-planning — after the concurrent Builder session lands)

1. **Acceptance E2E test** (maintainer-requested): a full end-to-end test from **sample + metadata sheet creation → run → downstream → report** (report = the **built RunDetail Report tab**, option a), driven **through the Pipeline Builder** where possible, over a **multi-sample samplesheet** so the W4 per-sample fan-out is exercised (SLURM path if a cluster is present, else the local-serial fallback). Doubles as the acceptance criterion for **W1 + W3 + W4**. Depends on: (a) the Builder session landing (it cites Builder `file:line`), (b) W1's run-path generality + W3's downstream cards/stages/report being at least minimally built, (c) enumerating installed-vs-not tools for the "wire all reserved/optional cards" ask. **Not started — queued behind the current planning.**

## How Track B runs (Fable 5, same grounding as Track A)

Per item: a **3-approach design panel** (3 Explore-grounded agents propose independently) → a **Fable-5 judge/synthesis** picks + merges the best into the recommended proposal → I write `audit/wishlist/<Wn>.md`. Runs in the **same fan-out** as Track A (shared repo grounding, all Fable 5) or standalone. Read-only: agents design, they don't build. A follow-up step can turn an accepted proposal into an ADR + `tasks.md` slice.

## Critical framing (Track B)

Reward the **most implementable, lowest-risk path that fits the existing architecture** — not the most ambitious feature. A proposal that reuses an existing seam and ships a small honest MVP beats a greenfield redesign. If an item can't be built without violating a guardrail (G1 especially), **say that plainly** — that's the highest-value finding this track can produce.
