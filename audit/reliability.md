## Specialist 5 — Reliability & failure-mode audit → `audit/reliability.md`

**Run mode:** Fable 5, code-only / headless (route + `file:line` + quoted string; no browser this pass). Every finding re-opened and the quoted string re-confirmed in source. Guardrails G1–G7 honored (nothing here proposes an agent/AI touching a verdict).

**Scope reminder / golden-path calibration.** The *recording* golden path uses pre-gated `mock_run_01` already on disk, so the live-intake and Builder-run break paths below are ranked by real-world reliability, not demo-blocking. None are demo Blockers; the two Highs are "the UI lies/stalls about a live run's fate," which is the class of failure this audit most wants surfaced.

---

### F5-R1 · Submit intake-status polling has no error handler → live run stalls forever with no honest failure state
- **Severity:** High · **Confidence:** Confirmed · **Category:** missing-user-facing-state
- **Area / journey:** Operate A — Submit (`/submit`) → `POST /api/runs` → intake-status poll → decision cards.
- **Evidence:** `frontend/src/screens/Submit.tsx:440-452`. The whole poll loop is un-guarded: `const st = await api.intakeStatus(ack.run_id)` (L441) with the only continuation `setTimeout(() => void poll(), 2500)` (L449) and the kickoff `void poll()` (L452). There is **no `.catch`** anywhere in the chain, and the outer `try/catch` (L430-456) does not await `poll`, so a rejected poll promise is discarded by `void`. `api.intakeStatus` throws on any non-2xx (`frontend/src/api.ts:87` `if (!res.ok) throw await httpError(res)`).
- **Reproduction:** Submit HG002 live; while the background Nextflow job is `running` (the run dir isn't created until the driver's final `write_run_dir`), restart uvicorn (or drop the network). Next poll hits `GET /api/runs/{id}/intake-status` → `_jobs` is empty → `intake.py:164` `SampleSheet.csv` not yet on disk → **404**. `intakeStatus` throws; the rejection is swallowed.
- **Expected:** A poll failure surfaces an honest error toast and clears the spinner (or retries with a visible "reconnecting" state), letting the operator recover.
- **Actual:** Unhandled promise rejection; `submitting` stays `true`; the button spins indefinitely with no toast — the UI silently hangs on a run whose fate is unknown.
- **Root cause:** Fire-and-forget recursive `async` poll with no rejection path; combined with the non-durable `_jobs` registry (F5-R5) a mid-run 404 is a normal, reachable event, not an edge case.
- **Min fix:** Wrap the poll body in `try/catch` (or add `.catch`) that toasts `httpError` detail and calls `setSubmitting(false)`; treat a 404 as a soft "lost track of this run — check the Runs list" state rather than an infinite stall.
- **Demo-critical:** N (recording uses pre-gated `mock_run_01`) · **Risk of fixing:** Low, isolated to one handler.
- **Regression test:** Component test: mock `api.intakeStatus` to reject after one `running` poll; assert an error toast fires and `submitting` returns to `false`.

---

### F5-R2 · Builder-run status endpoint has no disk fallback and the modal polls forever on error → a completed/lost run shows "running" indefinitely
- **Severity:** High · **Confidence:** Confirmed · **Category:** confirmed-defect
- **Area / journey:** Builder B — compose → `POST /api/pipelines/run` → poll `GET /api/pipelines/run/{run_id}` in `RunPipelineModal`.
- **Evidence:** `api/routers/pipeline_run.py:287-289` — `job = _jobs.get(run_id)` then `if job is None: raise HTTPException(status_code=404, ...)`, with **no disk fallback** (unlike intake's `api/routers/intake.py:164` `if (_DATA / run_id / "SampleSheet.csv").exists(): return ... status="complete"`). Frontend `frontend/src/components/BuilderModals.tsx:889` swallows every fetch error into an unbounded retry: `.catch(() => window.setTimeout(tick, 3000))`.
- **Reproduction:** Start a Builder run; restart uvicorn mid-run (or after it finishes on disk). `run_status` returns 404 for the now-unknown `run_id`; the modal's `.catch` re-schedules `tick` every 3 s forever. Even after the run has actually *completed on disk*, `run_status` still 404s (no disk recovery), so the modal never reaches `complete`.
- **Expected:** After a restart the modal should either recover terminal state from disk (as intake does) or surface an honest "lost connection to this run" state — not spin forever.
- **Actual:** Perpetual "running" phase; the operator never learns the run finished or died.
- **Root cause:** Asymmetry between the two status endpoints (intake has a `SampleSheet.csv` disk fallback; Builder-run has none) plus an infinite, un-surfaced client retry.
- **Min fix:** Give `run_status` the same disk fallback (`data/<run_id>/SampleSheet.csv` → `complete`, else 404); bound the client retry and surface an error state after N failures.
- **Demo-critical:** N · **Risk of fixing:** Low.
- **Regression test:** API test: register a job, clear `_jobs`, create `data/<id>/SampleSheet.csv`, assert `GET /api/pipelines/run/{id}` returns `complete` not 404.

---

### F5-R3 · Empty / no-tool-node graph is rejected at `/compile` (422) but accepted at `/pipelines/run` (202) → confusing late "no results dir" failure
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** design-inconsistency
- **Area / journey:** Builder B — Export (`POST /api/pipelines/compile`) vs Run (`POST /api/pipelines/run`).
- **Evidence:** The compile router guards empties itself: `api/routers/nextflow.py:84-85` `if not req.nodes: raise HTTPException(status_code=422, detail="the graph has no tool nodes to compile")`. The run router has **no such guard** — `api/routers/pipeline_run.py:187-191` goes straight to `compile_graph(graph)`, and `compile_graph` does **not** raise on an empty/all-source graph (`src/bayleaf/nextflow/compiler.py:124-125`: `tool_nodes=[]` → `_topo_order([]...)` returns `[]`, no `CompileError`). Grep confirms the string `"no tool nodes"` exists only in `nextflow.py:85`.
- **Reproduction:** `POST /api/pipelines/run` with `graph.nodes: []` (valid per `RunPipelineIn`/`CompileRequest`). Response is **202 queued**; the background driver runs an empty `main.nf`, produces no results, and the driver `sys.exit`s at `scripts/run_giab_pipeline.py:133-134` "nextflow run produced no results dir", flipping the job to `failed`.
- **Expected:** Both compile and run reject an empty/no-tool-node graph up front with the same 422 + reason (checklist item 1).
- **Actual:** Run accepts it, spends a Nextflow launch, then fails late with an opaque "no results dir" instead of a clean compile-time 422.
- **Root cause:** The "no tool nodes" guard lives in the compile *router*, not in `compile_graph`, so the run router (which reuses `compile_graph` but not the router) misses it.
- **Min fix:** Move the empty/no-tool-node check into `compile_graph` (raise `CompileError`), or add `if not body.graph.nodes` to `run_pipeline` before compiling.
- **Demo-critical:** N · **Risk of fixing:** Low; centralizing in `compile_graph` also hardens the export path.
- **Regression test:** `POST /api/pipelines/run` with `nodes: []` asserts 422 with a "no tool nodes" reason.

---

### F5-R4 · Duplicate-run-id 409 guard is not atomic with run-dir creation → concurrent same-id submits both proceed
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** confirmed-defect
- **Area / journey:** Operate A intake + Builder B run — the `(data/<run_id>).exists()` de-dup.
- **Evidence:** `api/routers/intake.py:134` `if (_DATA / run_id).exists(): raise HTTPException(status_code=409, ...)` then `api/routers/intake.py:146-147` registers the job under lock and spawns a thread; the run dir is created only much later by the driver's `write_run_dir` (`scripts/run_giab_pipeline.py:204`). Same shape in `api/routers/pipeline_run.py:184`. Neither router checks `run_id in _jobs` before overwriting (`intake.py:147`, `pipeline_run.py:232` both do a bare `_jobs[run_id] = _Job(...)`).
- **Reproduction:** Fire two `POST /api/runs` with the same `run_name` within the window before either driver writes `data/<run_id>/`. Both pass the `.exists()` check (dir absent), both register (the second overwrites `_jobs[run_id]`), both driver threads run against the same `.nf-runs/<run_id>` scratch and the same `data/<run_id>` output.
- **Expected:** Exactly one job per run_id; the second submit 409s (checklist item 7).
- **Actual:** A race window admits two concurrent executions writing the same scratch/output dirs, with only the last `_jobs` entry observable via status.
- **Root cause:** De-dup keyed on a filesystem side effect produced at the *end* of the job, not reserved atomically at submit; `_jobs` (guarded by `_lock`) is not consulted as the authority.
- **Min fix:** Under `_lock`, reject if `run_id in _jobs` with a non-terminal status (and/or create a reservation marker dir synchronously) before spawning the thread.
- **Demo-critical:** N (single-operator demo) · **Risk of fixing:** Low.
- **Regression test:** Concurrency test submitting the same run_id twice; assert exactly one job registered / one 202 + one 409.

---

### F5-R5 · In-memory `_jobs` registries are non-durable → backend restart loses running-job state and orphans scratch
- **Severity:** Medium · **Confidence:** Confirmed · **Category:** missing-user-facing-state
- **Area / journey:** Operate A + Builder B — job observability across a restart (root cause behind F5-R1/F5-R2).
- **Evidence:** `api/routers/intake.py:54` `_jobs: dict[str, _Job] = {}` (module-level dict + `threading.Lock` + daemon threads); recovery on lookup miss is disk-only and only reaches `complete` (`intake.py:162-166`). `api/routers/pipeline_run.py:99` same registry; `pipeline_run.py:287-289` recovers nothing (always 404 on miss). `.nf-runs/<run_id>` scratch is created by the driver (`scripts/run_giab_pipeline.py:113-114`) and never cleaned on crash.
- **Reproduction:** Submit; restart uvicorn while `running`. `_jobs` is empty post-restart; a `running` intake job becomes 404 until/unless it finished on disk; a Builder-run job is unrecoverable; `.nf-runs/<run_id>/work` is left behind.
- **Expected:** Polling UIs degrade honestly after a restart (surface "unknown/lost" rather than hang), and orphaned scratch is bounded (checklist item 8).
- **Actual:** A `running` job silently disappears (404), driving the client stalls in F5-R1/F5-R2; scratch accumulates.
- **Root cause:** Ephemeral in-process registry with no durable job store (acknowledged as a "demo-scale analogue" in `intake.py:53`).
- **Min fix (demo-scoped):** Ensure the two client pollers treat 404 as a terminal "lost track" state (fixes the visible symptom); optionally persist a tiny job-status marker file per run so status survives a restart.
- **Larger fix:** Back `_jobs` with a durable store keyed by run_id; reap orphaned `.nf-runs` on startup.
- **Demo-critical:** N · **Risk of fixing:** Low for the client-side degradation; Medium if adding persistence.
- **Regression test:** Restart-simulation: clear `_jobs`, assert intake returns 404 for a never-finished run and the client shows an honest lost state.

---

### F5-R6 · Timeout asymmetry: the identical germline pipeline gets 900 s via intake but 1800 s via Builder-run
- **Severity:** Low · **Confidence:** Confirmed · **Category:** design-inconsistency
- **Area / journey:** Operate A intake vs Builder B run — both shell out to the same `scripts/run_giab_pipeline.py`.
- **Evidence:** `api/routers/intake.py:110` `... capture_output=True, text=True, timeout=900` vs `api/routers/pipeline_run.py:269` `... text=True, timeout=1800`.
- **Reproduction:** A germline run that takes 15–30 min (cold conda env / larger inputs) times out (→ `failed`) through Submit but not through the Builder.
- **Expected:** The same pipeline has a consistent, documented time budget regardless of entry point.
- **Actual:** Two different budgets for the same work; an intake submit can fail on a run the Builder path would complete.
- **Root cause:** Independently chosen literals in two routers.
- **Min fix:** Share a single timeout constant across both routers (justify the value in a comment).
- **Demo-critical:** N · **Risk of fixing:** Low.
- **Regression test:** N/A (constant); optionally assert both routers reference the same symbol.

---

### F5-R7 · No pre-flight reference-index check → a missing `.fai`/`.bwt.2bit.64` burns a full Nextflow launch before failing at bwa-mem2
- **Severity:** Low · **Confidence:** Confirmed · **Category:** post-hackathon-improvement
- **Area / journey:** Execution driver — index staging for alignment/variant calling.
- **Evidence:** The driver pre-flight only checks primary file existence: `scripts/run_giab_pipeline.py:264-271` loops over `(cfg.reference, cfg.read1, cfg.read2, cfg.panel_bed)` calling `path.exists()` — **no** sidecar-index check. The pipeline stages the index via a glob only: `pipelines/germline/main.nf:17` `ch_reference = Channel.value([file(params.reference), file("${params.reference}.*")])` (and `INDEXED_REFERENCE_PARAMS={"reference"}`, `src/bayleaf/nextflow/catalog.py:234`). An empty glob stages nothing and bwa-mem2/bcftools fail at *runtime*.
- **Reproduction:** Point `--reference` at a FASTA with no `.fai`/`.bwt.2bit.64` sidecars; the run launches Nextflow, aligns, and fails inside `BWA_MEM2_MEM` minutes later.
- **Expected:** A loud, *early* failure (pre-flight) that names the missing index.
- **Actual:** Loud but very late — the failure is honest (returncode ≠ 0 → job `failed` with stderr tail) but wastes a full launch and gives an opaque tool error. (This is an accepted seam per the checklist; flagged as a UX/reliability improvement, not a correctness bug.)
- **Root cause:** No index preflight; the glob silently tolerates zero sidecars.
- **Min fix:** In the driver preflight, assert at least the samtools `.fai` and a bwa-mem2 index sibling exist for an `INDEXED_REFERENCE_PARAMS` reference; `sys.exit` with a clear message if absent.
- **Demo-critical:** N (committed reference is pre-indexed) · **Risk of fixing:** Low.
- **Regression test:** Driver unit test: reference with no sidecars → preflight `SystemExit` mentioning the missing index.

---

### F5-R8 · No FASTQ pairing/format/length validation → a swapped or mismatched read pair may produce a silent wrong result instead of a loud crash
- **Severity:** Low · **Confidence:** Possible (absent-validation defect is Confirmed; the "silent wrong result" consequence is Probable) · **Category:** scientific-correctness-risk
- **Area / journey:** Execution — reads enter the pipeline as two independent params.
- **Evidence:** Reads are passed straight through as independent CLI params (`scripts/run_giab_pipeline.py:243-244` `--read1`/`--read2`) and wired as an unvalidated tuple channel (`pipelines/germline/main.nf:15` `ch_reads = Channel.value([file(params.read1), file(params.read2)])`). No pairing, equal-count, or format check exists in the driver, compiler, or any gate rule (grep of the read path shows no read-sync validation).
- **Reproduction:** Swap R1/R2 (two valid, equal-length fastqs). fastp/bwa-mem2 run without error and emit a plausible-but-wrong alignment; the gate scores it as a normal run. (A *truncated/unequal* pair would instead crash bwa-mem2 loudly — so the outcome is input-dependent.)
- **Expected:** Either a validation gate on read sync, or an explicit acknowledgement that read identity/order is assumed correct upstream.
- **Actual:** A swapped equal-length pair is **not guaranteed** to fail loudly, contradicting the "never a silent wrong result" reliability goal for this seam. (Depth on the scientific implications is owned by Specialist 7; flagged here only as the reliability failure mode.)
- **Root cause:** Reads treated as opaque independent inputs with no sync validation.
- **Min fix:** Document the assumption prominently and/or add a lightweight read-count/format sanity check (fastp already emits before/after counts — assert R1/R2 counts match) that fails the job on mismatch.
- **Demo-critical:** N · **Risk of fixing:** Low.
- **Regression test:** Feed a mismatched-count pair; assert the job flips to `failed` rather than producing a card.

---

### F5-R9 · Subprocess timeout kills only the direct child → orphaned Nextflow/JVM subtree and `.nf-runs` scratch
- **Severity:** Low · **Confidence:** Probable · **Category:** post-hackathon-improvement
- **Area / journey:** Execution — timeout/crash handling in both routers.
- **Evidence:** `api/routers/intake.py:107-111` `subprocess.run(..., timeout=900)` with the timeout handled at `intake.py:120-123` (`except Exception → status="failed"`); same at `pipeline_run.py:268-281`. `subprocess.run` on `TimeoutExpired` kills only the launched python driver; the driver's own `nextflow`/`java`/tool grandchildren (spawned in `run_nextflow`, `scripts/run_giab_pipeline.py:128-131`) are not in a process group that gets reaped, and `.nf-runs/<run_id>` scratch is left on disk.
- **Reproduction:** Trigger a >900 s intake run; the job flips to `failed` (good) but a `nextflow`/JVM process and its `work/` scratch can linger.
- **Expected:** A timeout tears down the whole process tree and (optionally) cleans scratch.
- **Actual:** Job status is honest, but resources orphan.
- **Root cause:** No process-group / `start_new_session` reaping around the driver subprocess.
- **Min fix:** Launch the driver in a new session/process group and kill the group on timeout; reap `.nf-runs/<run_id>` on failure.
- **Demo-critical:** N · **Risk of fixing:** Low–Medium (process-group handling needs care on macOS/Linux).
- **Regression test:** Hard to unit-test portably; cover with a manual runbook note.

---

## Honest surfaces (verified solid — do NOT "fix")

These were probed and hold up; calling them out so the signal above stays clean:

- **Cyclic / bad-edge / out-of-range graphs → 422 with the compiler's reason on BOTH paths.** `compile_graph` raises `CompileError` for cycles (`compiler.py:195` "graph has a cycle — a Nextflow DAG must be acyclic"), unknown nodes (`compiler.py:116`), and out-of-range ports (`compiler.py:118-121`); both `nextflow.py:88-89` and `pipeline_run.py:190-191` catch it → 422 (never 500). (The *empty*-graph case is the one gap — F5-R3.)
- **Partial publish is a hard failure, not a degraded gate.** `_one()` `sys.exit`s on any missing published output (`scripts/run_giab_pipeline.py:139-144`), and both routers require `returncode == 0 AND data/<run_id>/SampleSheet.csv exists` (`intake.py:112`, `pipeline_run.py:271`) — a partial run flips to `failed`.
- **Uncatalogued tool → labelled placeholder that fails loudly on a real run but `-stub-run`-validates.** `_render_placeholder` emits `exit 1` in `script:` and a `touch` `stub:` (`compiler.py:227-249`); no fabricated command.
- **`nextflow` not on PATH → clean loud failure.** `run_nextflow` `sys.exit`s with a PATH hint (`scripts/run_giab_pipeline.py:105-110`) → returncode ≠ 0 → job `failed` with the stderr tail surfaced (`intake.py:117-119`). A uvicorn started without `BAYLEAF_BIOCONDA_BIN` fails every submit at the driver rather than stalling.
- **Timeouts flip to `failed`, don't hang.** The `except Exception` branch catches `TimeoutExpired` in both routers (`intake.py:120-123`, `pipeline_run.py:278-281`).
- **Toast/httpError surface the real backend outcome.** `httpError` unpacks FastAPI's `detail` string/array (`api.ts:68-83`) and every read/write throws on non-2xx (`api.ts:87,97`); `ErrorBox` offers `onRetry` (`States.tsx:18-32`).
- **Traversal-safe inputs by key, not path.** Builder-run resolves inputs from a server-side `_catalog()` keyed lookup that only surfaces present files (`pipeline_run.py:59-88, 203-211`); `run_id` is slug-validated (`_RUN_ID_RE`, `pipeline_run.py:42,182-183`).
- **Drift guard genuinely gates.** `test_committed_reference_pipeline_matches_the_compiler` asserts byte-for-byte equality AND no extra committed files (`tests/test_nextflow_compile.py:69-78`).

**Known coverage gap (informational, matches checklist item 12):** the real execution path is unverified in the default offline suite — `tests/test_pipeline_run.py:82-86` monkeypatches `_execute` to a no-op, and the only end-to-end DAG check (`test_generated_germline_stub_runs`, `tests/test_nextflow_compile.py:156-181`) `pytest.skip`s when `nextflow` isn't on PATH. So CI without Nextflow proves 422/RBAC/compile behavior but **not** DAG-validity or a real run.
