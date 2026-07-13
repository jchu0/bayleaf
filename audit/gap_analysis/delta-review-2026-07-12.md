# Delta Review — commits since the 2026-07-11 design review (`6f1c758..HEAD`)

| Field | Value |
|---|---|
| **Date** | 2026-07-12 (MST) |
| **Range** | `6f1c758` → `d530dfc` (20 commits, the other session's Builder/execution/Nextflow arc) |
| **Method** | 4 `adversarial-reviewer` lenses (Opus), grounded in the diffs; read-only |
| **Companion to** | [`design-review-2026-07-11.md`](design-review-2026-07-11.md) (the original ~35 findings) |

## TL;DR

The delta **did not touch the core gate** — every P0/P1 finding's code (`rules.py`, `runbook.py`,
`synthesis/`, `parsers.py`, `metrics/`, `models.py`, the driver's parse logic) is `diff`-empty in range. So
**WS-01–WS-06 and WS-09-metric-bugs stand unchanged.** The delta's real work is a **Builder→execution path**
(authored pipelines can now feed the gate — §7 partially closed) and Nextflow/port hardening — and it introduced
**one urgent regression and three new "confident surface / thin wiring" gaps.** One original finding (`tsc -b`
in CI) was **closed** by `e40784c`.

---

## 1. Reconciliation with the original review

| Cluster | Status | Evidence |
|---|---|---|
| §1 fail-closed | **UNCHANGED** — but *more load-bearing now*: the new authored-pipeline path routes verdicts through this still-open gate | `rules.py`/`synthesis`/`runbook.py` diff-empty |
| §2 identity/provenance | **UNCHANGED, slightly worse** — `dff2cef` removed NGSCheckMate from the node-author corpus (honest, but the identity surface is thinner) | `rules.py` untouched; `tool_cards.jsonl` 11→10 |
| §3 ingestion | **UNCHANGED** — frozen-five CSV contract untouched; `_FIXTURE_SAMPLES={"HG002"}` still; `files.py` is a *browse picker*, not the run-store root | `intake.py:61`, `parse_qc_metrics` untouched |
| §4 GIAB concordance | **UNCHANGED** — `count_variants` still counts records; truth VCF unused | `run_giab_pipeline.py:509` |
| §5 config loop | **UNCHANGED** — `_active_runbook` still returns `DEFAULT_RUNBOOK` only | `api/main.py:235-253` |
| §6a–c registry/gate-type | **UNCHANGED** | `runbook.py`/`mapping.py`/`models.py` diff-empty |
| §6d store proliferation | **SLIGHTLY WORSE** — 3 new API surfaces (`authored_pipeline.py`, `routers/files.py`, `routers/node_observations.py`), no consolidation | — |
| §7 scope / "builder doesn't feed the gate" | **PARTIALLY ADDRESSED** — `469d0fa` (ADR-0021): `POST /api/runs` resolves an *approved* authored graph, compiles it, runs *that* `main.nf` → parse → gate. The drawn graph can now feed the verdict. **Bounded — see New #2.** | `authored_pipeline.py`, `intake.py:99-104` |
| §8 AI earning its place | **UNCHANGED** — the new `gather_node_observations` is exactly the *input* §8a's fix needs, but **no agent consumes it** (see New #1) | `node_observations.py:380`; `triage/` doesn't import it |
| §9 metric correctness | **UNCHANGED** — `parse_fastp` still `dup = rate*100`, the fixture-fraction mismatch is live | `run_giab_pipeline.py:503` |
| **DoD "fix the verifier" (`tsc -b` in CI)** | **✅ CLOSED** | `e40784c` runs frontend `tsc -b` on pre-push |

---

## 2. New findings (from the delta) + new workstreams

### WS-10 · fastp required-output regression — **URGENT (potential golden-path break)**

- **[HIGH]** `1621e3f` promoted fastp's `unpaired_fastq`/`failed_fastq` to **required** Nextflow outputs and
  mutated the real fastp command (`--unpaired1/2`, `--failed_out`) — but `Port` has no `optional` field
  (`catalog.py:23-37`) and `_render_catalogued` emits every output as mandatory (`compiler.py:463`). On clean
  HG002 PE reads fastp may write **no** unpaired/failed files → `FASTP` fails "Missing output file(s)" → the
  **whole intake pipeline fails at step 1.** The last confirmed live run (`completed=7 failed=0`) was *before*
  this change; the stub `touch`es the files, so `-stub-run` + drift tests pass regardless. *(Depends on fastp
  runtime behavior the agent couldn't execute — likely-but-unconfirmed.)*
- **Fix:** add an `optional` flag to `Port`, render `optional: true` (the nf-core convention for these
  byproducts) — **or** re-run `nextflow run pipelines/germline/main.nf` on real reads and confirm the files
  exist before shipping.
- **Test-first / DoD:**
  - *Real-path acceptance (REQUIRED):* `test_fastp_optional_outputs_on_real_hg002` — env-gated, runs the real
    germline `main.nf` on GIAB reads; **red today if fastp omits the files** (the thing to verify). Only green
    proves the golden path survived the promotion.
  - *Guard:* `test_promoted_byproduct_ports_render_optional` — asserts any catalog `Port` for a contingent
    byproduct emits `optional: true` in the compiled module (freezes the fix).
  - *DoD:* both green, and one real `nextflow run` logged `completed=N failed=0`.

### WS-08 · Phase-4 observation binding — wire it real (the maintainer-flagged gap, plus a deeper one)

- **[HIGH] The binding is never server-enforced.** `node_observations()` (`node_observations.py:365-380`) takes
  `grants` from the *query string* — it never loads the persisted `AgentBinding` or takes an `agent` identity.
  So `grants=logs` is gated only by wire role → **any viewer can `GET .../observations?grants=logs` on any
  node, bound or not.** "Node-scoped least-privilege" is true of the *data* (globs scope to one node) but false
  of the *access*. Security-relevant.
- **[HIGH] Present-but-inert** — `api.nodeObservations` has **zero call sites**; `triage/` never imports
  `gather_node_observations`; no UI displays observations. The Builder grant popover toggles a binding that
  changes **no behavior anywhere.**
- **[MED] No run→graph linkage** — `_resolve_spec` (`:144-155`) resolves node ids against the *seeded germline
  graph*, never the authored graph a run actually executed (nothing records which). Works only by id-equality
  coincidence; a non-germline run reusing a germline id resolves silently wrong.
- **[MED] De-id scrubs placeholders, not real PII, on the live path** — the "known subject id" scrub reads
  `sample_metadata.csv`, but the live driver writes **placeholder** subject ids (`run_giab_pipeline.py:549`),
  so on a real run the known-literal defense has nothing to catch; protection collapses to the regex fallback
  (which wouldn't redact a *name*). The test plants a fixture subject that can't arise live.
- **[MED]** `test_node_observations.py` is a plumbing/scaffold test — passes without any consumer.
- **Fix / test-first:** load the run's authored `agent_bindings`, take `agent`, intersect requested grants with
  the *persisted* grant (403/empty otherwise) → guard `test_logs_denied_without_persisted_grant`; wire one real
  consumer (QC-triage calling `gather_node_observations` for its bound nodes, **and** an observations panel) →
  real-path `test_triage_reads_bound_node_outputs`; record executed pipeline on the run + resolve against it.
  Until then, drop "bound"/"least-privilege" from the docstrings — call it a node-scoped read gated by wire role.

### WS-09 · Authored-pipeline execution — actually gate a *non-germline* pipeline

- **[HIGH] Post-run parse is hardcoded to germline's four outputs.** `run_giab_pipeline.py` requires every
  sample to publish `*.fastp.json` + `*mosdepth.summary.txt` + `*thresholds.bed.gz` + `norm.vcf.gz`, `sys.exit`
  on any absence (`:442-462`). So an approved authored pipeline that isn't germline-output-shaped **runs to
  completion in Nextflow then dies at parse → `failed` run after a full compute burn.** ADR-0021 frames the
  limit as "only HG002 has reads" (data); the real blocker is **parse coupling** (structural) — even *with*
  reads, a non-germline graph can't yield a card.
- **[HIGH] Intake never wires the authored pipeline's inputs.** `_run_pipeline` passes only run-metadata flags
  (`intake.py:222-229`), never `--read1/2/--reference/--panel-bed`, so the driver falls back to HG002 defaults
  **regardless of what the authored graph needs.** The sibling Builder-Run path validates `required_inputs` and
  rejects unsupported kinds (`pipeline_run.py:246-256,335`) — intake has **none** of that. An authored pipeline
  needing a different input runs against HG002 silently (wrong-but-runs). Two routers "share one gate" but
  emphatically not input handling; only one is safe.
- **[MED] "Schedule" is inert** — `scheduled_at` is stored/validated/displayed but no code path fires a
  scheduled run at its time.
- **Fix / test-first:** drive the parse off the compiled graph's declared `emit`s (or validate terminal outputs
  vs the frozen-five at submit and **422 up front**) → real-path `test_nongermline_authored_pipeline_gates`;
  route intake through the same `required_inputs`/catalog binding as Builder-Run → guard
  `test_intake_rejects_authored_graph_with_unfilled_inputs`; either fire scheduled runs or label the control
  "not auto-scheduled."

---

## 3. Honesty note — `adapter_fasta`

The maintainer described this delta as *"fastp adapter_fasta promotion (a positional-input catalog change)."*
**The code says otherwise:** `adapter_fasta` was left **reserved** — no catalog entry, no positional input, no
channel (`catalog.py:82`, `BuilderShared.tsx:473-477`, honestly commented as deferred). It's also the *one*
exception to commit `1621e3f`'s own principle ("reserved ports become real channels **or are removed** — no
superficial ports"): every other reserved port was removed; `adapter_fasta` was kept as a dashed inert slot.
Not a code bug — but the *verbal* claim is one the code contradicts, exactly the surface/wiring gap the review
warns about. **Action:** either remove the port (honor "no superficial ports") or actually promote it; and
correct the description before it lands in a demo/README.

---

## 4. Net change to the course of action

1. **Core remediation unchanged** — WS-01–WS-06, WS-09-metric-bugs proceed as planned; the delta didn't move them.
2. **WS-01 (fail-closed) is now higher priority** — the authored-pipeline path routes verdicts through the
   still-open gate, so "missing output → HOLD not PROCEED" now guards real execution, not just fixtures.
3. **Three new workstreams:** WS-08 (Phase-4 wiring), WS-09 (authored-execution parse+inputs), **WS-10 (fastp
   regression — URGENT).**
4. **WS-10 first** if a live demo run is planned — it may already break the golden path; it's small (a `Port`
   `optional` flag) and it's the one finding that could fail step 1 of the demo.
5. **`e40784c` closed** the CI/`tsc -b` verifier gap — check that item off.
