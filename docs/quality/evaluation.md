# Evaluation — what "good" means

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-13 (MST) — **hardening-bookkeeping sweep** (four merged PRs #10–13: T-148/T-034/T-071a/T-041): census refresh **789/65 → 798/65** (re-derived: `uv run pytest --collect-only -q` → 798; `git ls-files 'tests/*.py' \| wc -l` → 65, unchanged file count). +9 tests, all in three already-listed files: `test_intake_scheduling` 19→**22** (T-148's agent-binding-capture-at-submit cases, ADR-0024), `test_nextflow_compile` 16→**19** (T-071a's optional-input-channel + dormant-verifybamid2-stage cases), `test_node_observations` 10→**13** (T-148's scope-by-wiring-over-a-populated-publish-dir cases). T-034's flat-metric rename (`pct_reads_identified`→`reads_passing_filter`) touched `test_gate`/`test_metrics_mapping`/`test_runbook_set`/`test_upstream_waiver` but added no tests (counts verified unchanged). **Full-suite pass/skip NOT independently re-verified this round:** this worktree is missing gitignored, machine-local `data/real-giab/` + several generated `data/RUN-2026-*-GIAB-*` run dirs (a pre-existing local-provisioning gap in this isolated worktree, not caused by these merges — confirmed by running each merge's new/touched files in isolation: `uv run pytest tests/test_intake_scheduling.py tests/test_node_observations.py tests/test_nextflow_compile.py tests/test_gate.py tests/test_metrics_mapping.py tests/test_runbook_set.py tests/test_upstream_waiver.py -q` → 132 passed, 1 skipped, 1 failed — the one failure (`test_hg002_committed_run_has_no_spurious_qc_missing`) is the SAME missing-committed-run-dir cause, unrelated to the rename; the T-148 PR's own commit message independently records an identical "9 pre-existing, data-dependent failures... fail identically on clean main in this fresh worktree" finding on this machine). Re-verify the 781-pass baseline (now expected ~790) on a fully-provisioned machine. See [journal/2026-07-13-hardening-bookkeeping.md](../journal/2026-07-13-hardening-bookkeeping.md). Prior: 2026-07-13 (MST) — **route-to-human → flag-for-review** naming refresh: EVAL-012 + the test-file census entry `test_route_to_human` → `test_flag_for_review` (file renamed, count unchanged), rule id `VAR-FFR-001`. Also: census refresh 727/55 → **789/65** (re-derived: `uv run pytest --collect-only -q` → 789; `git ls-files 'tests/*.py' \| wc -l` → 65). This refresh adds the 10 previously-uncounted test files (`test_agent_chat`, `test_chat_store`, `test_upstream_waiver`, `test_scope_by_wiring`, `test_agent_output_cache`, `test_agent_binding_store`, `test_triage_cache`, `test_node_author_scaffolds`, `test_archivist_retrieval`, `test_pipeline_repair_docs_corpus`; +51) plus incremental growth in already-listed files. `uv run pytest -q` → **781 passed / 8 skipped** (unchanged skip set). Prior: 2026-07-12 (MST) — gap-analysis-remediation census refresh (634/48 → 708/52 → 722/54; WS-01/03/05/06/07/08/09/10, then WS-02/WS-04 + a caught pre-existing drift, `test_card_readout` 17→21, from the un-recounted `61936d1` WS-06 Gap 2 API-wiring commit) |
| **Audience** | software / all |
| **Related** | [audit/gap_analysis/README.md](../../audit/gap_analysis/README.md) (the workstream tracker this census reflects), [journal/2026-07-12-gap-analysis-remediation-verification.md](../journal/2026-07-12-gap-analysis-remediation-verification.md), [risks.md](risks.md), [requirements/nonfunctional.md](../requirements/nonfunctional.md), [data/strategy.md](../data/strategy.md), [data/metric_registry.md](../data/metric_registry.md), [data/schemas.md](../data/schemas.md), [data/qc_metrics.md](../data/qc_metrics.md), [data/provenance.md](../data/provenance.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md) (Nextflow codegen, EVAL-006, EVAL-009), [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md), [ADR-0016](../adr/ADR-0016-postgres-port.md) (pluggable-store family), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md) (the W1 approval gate, EVAL-007), [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) (flag-for-review, de-id, share egress, per-variant table EVAL-013), [ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md) (custom-script processes, EVAL-015; sandboxed file browser, EVAL-016; compiler robustness, EVAL-017), [ADR-0021](../adr/ADR-0021-operator-gated-scheduled-pipeline-processing.md) (authored-pipeline intake + processing gate, EVAL-018), [HISTORY.md](../HISTORY.md) (archived census milestones), [design/nextflow-codegen.md](../design/nextflow-codegen.md), [journal/2026-07-09-frontend-batch3.md](../journal/2026-07-09-frontend-batch3.md), [journal/2026-07-10-provenance-qc-builder-auth.md](../journal/2026-07-10-provenance-qc-builder-auth.md), [journal/2026-07-10-batch5-builder-card-admin-prefs.md](../journal/2026-07-10-batch5-builder-card-admin-prefs.md), [journal/2026-07-10-wave6-route-to-human-deid.md](../journal/2026-07-10-wave6-route-to-human-deid.md), [journal/2026-07-11-d2-d3-share-egress.md](../journal/2026-07-11-d2-d3-share-egress.md), [journal/2026-07-11-share-store-persistence.md](../journal/2026-07-11-share-store-persistence.md), [journal/2026-07-11-nextflow-codegen-execution.md](../journal/2026-07-11-nextflow-codegen-execution.md), [journal/2026-07-11-audit-hardening-w1-w4-e2e.md](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md), [journal/2026-07-11-p3-backlog.md](../journal/2026-07-11-p3-backlog.md) (EVAL-008), [journal/2026-07-11-w-deferrals.md](../journal/2026-07-11-w-deferrals.md) (EVAL-009, EVAL-013), [journal/2026-07-11-fleet.md](../journal/2026-07-11-fleet.md) (EVAL-008 update, EVAL-014), [journal/2026-07-11-custom-script-io.md](../journal/2026-07-11-custom-script-io.md) (EVAL-015, EVAL-016), [design/agent-authoring-contract.md](../design/agent-authoring-contract.md) (EVAL-014), [audit/AUDIT_PLAN.md](../../audit/AUDIT_PLAN.md), [audit/SYNTHESIS.md](../../audit/SYNTHESIS.md) |

## Overview

How we know bayleaf is *correct* and *honest*: the properties we check, the tests
that check them, and the limits of what a demo-stage evaluation can claim. The unit
of evaluation is a **case** (`EVAL-NNN`) with a precise definition of good and a named
check. Cases are grouped by type: **Deterministic** (same input → same output),
**Faithfulness** (the AI — and the notify port — narrate but never decide), **Failure-mode**
(each contrived fault reaches its intended verdict; a live side effect degrades to a safe
default), and **Real-data** (against GIAB truth — Phase 2). Two subsystems on or beside the
critical path get their own cases: the **metric registry** (unit normalization) and the
**notify port** (outbound integration).

The suite is **798 tests collected across 65 files** — re-derived 2026-07-13 (MST, hardening-
bookkeeping sweep) via `uv run pytest --collect-only -q` (798 collected) + `git ls-files
'tests/*.py' | wc -l` (65, unchanged — no new test file). The 789→798 step is four merged PRs
(#10–13): +3 `test_intake_scheduling.py` (T-148's agent-binding-capture-at-submit cases, ADR-0024),
+3 `test_nextflow_compile.py` (T-071a's optional-input-channel + dormant-verifybamid2-stage cases),
+3 `test_node_observations.py` (T-148's scope-by-wiring-over-a-populated-publish-dir cases); T-034's
metric rename (`pct_reads_identified`→`reads_passing_filter`) and T-041's containerization added no
tests (verified: `test_gate`/`test_metrics_mapping`/`test_runbook_set`/`test_upstream_waiver` counts
unchanged after the rename). Was 727/55 earlier the same day, 722/54 the prior day, 708/52 after the
gap-analysis-remediation sweep, 634/48 before it. The 727→789 step (the PRIOR refresh) added the 10
test files the by-size breakdown below
had omitted (`test_agent_chat`, `test_chat_store`, `test_upstream_waiver`, `test_scope_by_wiring`,
`test_agent_output_cache`, `test_agent_binding_store`, `test_triage_cache`,
`test_node_author_scaffolds`, `test_archivist_retrieval`, `test_pipeline_repair_docs_corpus`; +51
tests) plus incremental growth in already-listed files — all pure-offline, so the skip set is
unchanged at 8. **One**
new file has landed since the 722/54 count: `tests/test_real_giab_calibrated.py` (commit `478d579`,
+3 — the WS-02/WS-04 live-genomics pass, reading the REAL committed calibrated VerifyBamID2/hap.py
tool outputs under `tests/fixtures/giab_real/` through the public `ingest_results_dir → run_gate`
path). Two existing files each gained one test the same round: `test_gate.py` 49→**50**
(`test_check_coverage_flips_contamination_when_freemix_is_examined`, commit `b03d1fa` — freezes the
`CheckCoverage` contamination-flip fix, see [qc_metrics.md](../data/qc_metrics.md#fail-closed-rules--qc-missing--qc-expected-key-ws-01-2026-07-12))
and `test_pipeline_run.py` 12→**13** (`test_run_rejects_a_non_gateable_approved_pipeline`, commit
`7cef743` — proven red-before-impl via a stashed-endpoint rerun, freezes Builder-Run's new
`check_parse_contract` parity with intake). Earlier, the prior-day recount also caught a real,
pre-existing drift the sweep before that missed: `test_card_readout.py` grew from 17 to 21 tests in
`61936d1` ("card_readout: render target_band thresholds", WS-06 Gap 2 API wiring) — a commit that
landed **after** that day's doc sweep and was never counted until the 722/54 recount. Pass/skip
depends on whether `nextflow` is on `PATH`: verified 2026-07-13 (pre-hardening-sweep) via
`uv run pytest -q` with `nextflow` absent (this repo's default sandboxed dev/CI environment) —
**781 pass / 8 skip** (789 collected minus the 8 machine-gated skips below; every addition that
round was a pure-offline stub/fixture/real-fixture-bytes test, no new skip). **By the same logic,
798 collected − 8 machine-gated skips = 790 pass / 8 skip is the expected fully-provisioned
figure post-hardening-sweep** (all 9 new tests are pure-offline, no new skip) — **not
independently re-verified end-to-end this round**: this specific worktree is missing gitignored,
machine-local `data/real-giab/` + several generated `data/RUN-2026-*-GIAB-*` run dirs (a
pre-existing local-provisioning gap in this isolated worktree, unrelated to the four PRs — see the
header cell above for the isolated-file-run evidence). `uv run pytest -q` here shows **7 failed,
782 passed, 9 skipped** (one extra skip vs. the 8 below: `test_ingest.py`'s real-path check
properly self-skips here too, since its own gitignored data is absent) — every one of the 7
failures references a missing `data/real-giab/` or `data/RUN-2026-*-GIAB-*` path, none touch
rename/binding/compiler logic. Re-verify 790/8 on a fully-provisioned machine.
The **8 skips** are machine-gated live-integration checks: **3 `nextflow`-gated** stub-run checks
(`test_nextflow_compile.py::test_generated_germline_stub_runs`, EVAL-006;
`test_e2e_pipeline.py::test_approved_germline_pipeline_stub_runs_live`, EVAL-007;
`test_io_path_wiring.py::test_driver_argv_shape_is_accepted_by_the_committed_pipeline_stub_run`,
EVAL-016) + **1 new real-path check** (`test_nextflow_promoted_ports.py`'s
`test_fastp_catalog_command_produces_every_declared_output`, WS-10, gated on
`BAYLEAF_BIOCONDA_BIN`/`PATH` + `data/real-giab/fastq/`) + **4 Postgres-live** round-trips
(`test_persistence_postgres_live.py`). **A ninth real-path test is NOT among the skips** —
`test_ingest.py::test_real_nextflow_results_ingest_and_gate` (WS-03/06) is gated on a committed-run
`.nf-runs/<run>/nf-out/results/` directory (gitignored, machine-local) rather than tool presence, and
on the machine that ran the real HG002 pipeline that directory is already on disk, so the test
**PASSES for real** (independently re-verified during this doc sweep: `uv run pytest tests/test_ingest.py
-k real_nextflow -v` → `1 passed`). Every non-live test runs unconditionally; `ruff`/`mypy` (backend)
and `tsc`/`oxlint` (frontend) are clean. Earlier census milestones (585/44 → 427/29 → 634/48) are
archived in [HISTORY.md](../HISTORY.md).

By collected size:
`test_gate` (50, was 30 → 49 (WS-01 QC-MISSING/expected-metrics/CheckCoverage + WS-06 target-band/
metric-honesty guards) → 50, `b03d1fa` — the `CheckCoverage` contamination-flip freeze), `test_api`
(44), `test_notify` (36), `test_synthetic` (33), `test_fetch_giab` (32),
`test_triage` (23, was 16 — WS-07 Q2 `ask`-endpoint cases), `test_card_readout` (21, was 14 → 17
(WS-07 Q1 `qc_reports` cases) → 21, `61936d1` — WS-06 Gap 2's API-side target_band rendering: in-band
pass, out-of-target/out-of-hard tail flags, and an anti-drift guard the readout status mirrors
`rules._evaluate_target_band`), `test_intake_scheduling` (22, was 19 — T-148's ADR-0024
agent-binding-capture-at-submit cases, 2026-07-13; before that, WS-09's submit-time parse-contract +
input-parity + scheduling-honesty guards took it 15→19), `test_review_queue` (20), `test_node_author`
(19, the advisory node-authoring agent, T-046), `test_nextflow_compile` (19, was 16 — T-071a's
optional-input-channel + dormant-verifybamid2-stage cases, 2026-07-13, incl. the mosdepth-5-output
Export-to-Nextflow regression, EVAL-019), `test_persistence` (17),
`test_nextflow_robustness` (17, the compiler robustness-hardening / hostile-input suite — one case per
verified review fix: proc-name collision, File-input source wiring, novel-kind params channel,
fan-in / dup-emit / port-drift guards, injection-escaped strings), `test_metrics` (17),
`test_archivist` (17,
the advisory archivist/librarian agent), `test_run_giab_preflight` (16, the
four pre-flight guards in `scripts/run_giab_pipeline.py`, T-131), `test_pipeline_repair` (16, the
advisory pipeline-repair agent), `test_job_store` (16), `test_runbook_set` (14, **new** — WS-05
`RunbookSet`/`RunbookKey` per-sample resolution, incl. the `expected_metrics` loop-closes-end-to-end
proof), `test_node_observations` (13, was 10 — T-148's scope-by-wiring-over-a-populated-publish-dir
cases, 2026-07-13; before that, WS-08 interim's `logs`-grant-requires-reviewer+ access-control tests
took it 8→10), `test_settings` (13, config-override authoring), `test_node_author_conformance` (13),
`test_ingest` (13, **new** — WS-03 nf-core/MultiQC `results/` → `SampleMetrics` adapter,
driver-equivalence + real-path acceptance), `test_auth`
(13), `test_safe_harbor` (12),
`test_real_giab_calibrated` (3, **new** — WS-02/WS-04 live-genomics: the real, committed
genome-wide-calibrated VerifyBamID2 FREEMIX + real hap.py SNP-F1 vs GIAB v4.2.1 truth flow through
`ingest_results_dir → run_gate`, proving the parsers on genuine tool output, not just a
format-mimicking fixture), `test_pipeline_run` (13, was 12 — `7cef743` adds the
Builder-Run non-gateable-pipeline 422 freeze test), `test_pipeline_lifecycle` (11,
submit/approve/dry-run/diff), `test_flag_for_review` (10, the
off-by-default flag-for-review gate rule VAR-FFR-001, ADR-0018 D2), `test_files_api` (10,
the sandboxed `GET /api/files` browser: allowlist, traversal/absolute/symlink-escape rejection, kind
inference, role gate, ADR-0020, EVAL-016), `test_e2e_pipeline` (10, the offline acceptance test threading
sheet→intake→the W1 approval gate→report/provenance, EVAL-007 — its own module docstring already
states it monkeypatches the Nextflow/subprocess boundary and asserts WIRING, never a live pipeline;
the gap-analysis review flagged this filename as implying more than that docstring claims and
recommended a rename to `test_pipeline_contract.py` — **not yet done, still tracked** in
[audit/gap_analysis/README.md](../../audit/gap_analysis/README.md)), `test_nextflow_custom_process` (9,
operator-authored custom-script processes: verbatim render + label, catalog-bypass-on-collision,
blank-script rejection, compose≠execute, germline-drift-green, ADR-0020, EVAL-015),
`test_io_path_wiring` (9, offline proof the `POST /api/pipelines/run` input picker wires a chosen
key through to the real driver/`nextflow run` argv), `test_gate_notify` (9), `test_artifacts_s3`
(9), `test_pipelines` (8, the Pipeline Builder save/version store), `test_node_author_importer` (8),
`test_nextflow_api` (8, incl. a posted custom-script node compiling over the wire + a blank
script 422, ADR-0020), `test_metrics_mapping` (8, was 5 — WS-06 PR1's registry-keyed `SampleMetrics`
ingestion-contract cases, incl. the `contamination.freemix` anti-scaffold proof), `test_execution_trace`
(8, the structured execution-trace feed → EXEC-001), `test_run_giab_multisample` (7, the multi-sample
driver parse: N-sample publish dir → N gated run-dir rows, byte-identical fan-out-of-1, fail-loud on
partial/empty, `S1`/`S10` anchoring, T-134, EVAL-009), `test_node_author_accept_api` (7),
`test_nextflow_promoted_ports` (7, was 5 — WS-10's fastp mandatory-output guards: every catalogued
stub materializes its declared outputs + the real-path fastp check above), `test_artifacts` (7),
`test_share_store` (6, the pluggable jsonl/sqlite/postgres share-egress-audit sink,
ADR-0016/ADR-0018 D3), `test_node_author_api` (6, the W2 read-only `GET /api/builder/node-proposal`
endpoint), `test_library_store` (6), `test_share_egress` (5, the de-identified share/report egress
endpoint, ADR-0018 D3), `test_ws02_contamination` (5, **new** — WS-02: VerifyBamID2 FREEMIX
contamination, offline stub + a real-format `.selfSM` fixture: parse, WARN/HOLD, CRITICAL/RERUN, a
clean value observed-but-not-flagged, absent-selfSM-is-not-a-hole), `test_ws04_concordance` (5,
**new** — WS-04: hap.py GIAB SNP-F1 concordance, offline stub + a real-format `summary.csv`
fixture: SNP+PASS row parse, WARN/HOLD, CRITICAL/RERUN, a high F1 observed-but-not-flagged,
absent-summary-is-not-a-hole), `test_persistence_postgres_live` (4), `test_run_giab_driver` (4, was 2 — the
Slurm/local executor-profile auto-detection unit, incl. a new WS-10-adjacent case), `test_stores_consolidated`
(3, **new** — WS-06 Gap 6: all 7 off-gate stores share the generic `JsonlStore`/`SqliteStore` base,
byte-identical output), `test_run_variants` (3, the per-variant Report endpoint
`GET /api/runs/{id}/variants`, T-133, EVAL-013), `test_stub_next_steps` (2, **new** — WS-07 Q1's
anti-boilerplate guard: the stub `next_steps` is never fabricated, across all four verdicts),
`test_upstream_waiver` (8), `test_agent_chat` (7), `test_chat_store` (6), `test_scope_by_wiring`
(5), `test_agent_output_cache` (5), `test_agent_binding_store` (5), `test_triage_cache` (4),
`test_node_author_scaffolds` (4), `test_archivist_retrieval` (4), `test_pipeline_repair_docs_corpus`
(3) (the trailing 10 files newly added to this by-size breakdown 2026-07-13 MST, previously
omitted) —
all runnable offline with no API key (`uv sync --all-extras && uv run pytest`; `test_api`/`test_triage`
need the api/claude extras to import FastAPI, the API-endpoint suites drive a `TestClient`, and the
core/agent/compiler suites run pure-offline over the core + pydantic).

## What "good" means (principles)

1. **Deterministic before impressive.** A fixed run and pinned runbook must yield
   identical verdicts, findings, and content hashes every time. Reproducibility is the
   headline property, not model quality.
2. **Honest over confident.** We evaluate whether the system *refuses to overclaim* —
   confidence omitted until grounded, no invented pathogenicity, AI degrades to a stub
   — as strictly as whether it gets verdicts right.
3. **Every number traces to a source.** A finding is "good" only if its evidence
   points at a real artifact + field; an untraceable number is a bug regardless of
   whether the verdict is right.
4. **Grounded, not calibrated.** Verdicts are checked against *intended* outcomes on
   contrived/synthetic data; confidence heuristics are **not** claimed to be
   probability-calibrated (that needs the real-data track).

## Deterministic cases

### EVAL-001 — Pinned demo scenario

| Field | Value |
|---|---|
| **Target** | End-to-end gate on `mock_run_01` |
| **Type** | Deterministic |
| **Automated?** | Yes — `test_gate.py` (`test_all_samples_parsed`, `test_s4_barcode_mismatch_is_critical_provenance`, `test_s4_missing_subject_id_flagged`, `test_s5_borderline_qc_only_warnings`, `test_verdict_aggregation_precedence`) |

**Definition of good.** S1–S3 **proceed**, S4 **escalate** (barcode/index swap +
missing `subject_id`, both preflight), S5 **hold** (borderline Q30 + coverage). Verdict
precedence: worst verdict wins.

**Method.** Parse the committed run, run the gate, assert per-sample verdicts and that
S4's barcode finding is a preflight/provenance critical, S5's are QC warnings only.

**Known failure modes.** A parser normalization change (MultiQC `pct_*` vs fastp
fraction) silently shifts a borderline sample across a threshold — caught by the pinned
values, which is the point.

### EVAL-002 — Reproducible projection from the ledger

| Field | Value |
|---|---|
| **Target** | Event ledger → relational projection (`rebuild-db`) |
| **Type** | Deterministic |
| **Automated?** | Yes — `test_persistence.py` (`test_rebuild_projects_demo_scenario`, `test_rebuild_is_idempotent`, `test_content_hashes_preserved`, `test_events_round_trip_faithfully`, `test_rebuild_from_different_ledger_drops_stale_rows`) |

**Definition of good.** Replaying a JSONL ledger yields the same runs/samples/findings/
cards/events; a second rebuild is idempotent; content hashes survive the round-trip;
rebuilding from a different ledger drops stale rows (the DB is a pure function of the
log).

**Method.** Build the demo ledger, project to SQLite, assert row-level equality and
hash preservation; rebuild twice and diff; rebuild from ledger B over DB-of-A and assert
no A-rows remain.

**Known failure modes.** A row field sourced from code rather than the event would break
purity — guarded by `schema_version` flowing from the event (a prior review finding).

### EVAL-003 — Live-repo wiring matches offline rebuild

| Field | Value |
|---|---|
| **Target** | In-band projection during a run vs. offline replay |
| **Type** | Deterministic |
| **Automated?** | Yes — `test_persistence.py` (`test_live_repo_wiring_matches_rebuild`, `test_repo_param_persists_without_changing_output`, `test_reset_clears_projection`) |

**Definition of good.** Passing a `repo` to the gate persists the same projection an
offline `rebuild-db` would produce, **without changing the gate's output** when the repo
is omitted (the seam is invisible to the default path).

**Method.** Run with and without a repo; assert identical cards; assert the persisted
rows equal the rebuilt rows.

**Known failure modes.** Persistence side effects leaking into verdicts — explicitly
asserted against.

### EVAL-004 — Metric registry normalizes by declared unit and round-trips

| Field | Value |
|---|---|
| **Target** | Metric registry (`bayleaf.metrics`) — `normalize` / `denormalize` / `observe` |
| **Type** | Deterministic |
| **Automated?** | Yes — `test_metrics.py` (`test_percent_to_fraction`, `test_percent_to_fraction_is_exact`, `test_denormalize_is_the_inverse_of_normalize`, `test_x_stays_x`, `test_multiqc_pct_trap`, `test_disallowed_raw_unit_rejected`, `test_unsupported_conversion_rejected`, `test_observe_builds_metric_value`, `test_metric_value_json_round_trip`, `test_unknown_key_rejected`, `test_alias_resolution`) |

**Definition of good.** Normalization keys on the caller-declared `raw_unit`, never the field
name: a `percent` value for a fraction metric becomes an exact decimal (`95.0%` → `0.95`, not
`0.9500…1`), `x` stays `x`, and `denormalize` is the exact inverse (rendering a canonical
threshold back into the operator-facing unit). A `raw_unit` the entry disallows, an
unsupported unit pair, or an unknown `our_key` is **rejected** — a mis-declared unit fails
loud, never a silent 100×. `observe` builds a `MetricValue` that round-trips through
`model_dump(mode="json")` without the registry present.

**Method.** Feed known raw values/units through `normalize`/`denormalize`; assert exact
decimals, identity, and inverse; assert disallowed/unsupported/unknown inputs raise; build a
`MetricValue` via `observe` and JSON round-trip it.

**Known failure modes.** An open (guessing) conversion table would mask a mis-declared unit —
the closed table + explicit raise is the guard. A float-imprecision regression (`/100` vs
`*0.01`) would churn `content_hash` — pinned by `test_percent_to_fraction_is_exact`.

### EVAL-005 — QCMetrics→MetricValue mapping holds the canonical scale on the critical path

| Field | Value |
|---|---|
| **Target** | `metrics.mapping.metric_values_for` + runbook↔registry linkage (QC gate path) |
| **Type** | Deterministic |
| **Automated?** | Yes — `test_metrics_mapping.py` (`test_maps_qcmetrics_to_normalized_metric_values`, `test_missing_field_is_skipped_not_defaulted`, `test_cluster_pf_maps_to_its_registry_key`, `test_runbook_thresholds_key_on_registered_metrics`, `test_maps_real_mock_run_01_s5`) |

**Definition of good.** Each parsed `QCMetrics` field maps to its registry `our_key` on the
declared scale (`cluster_pf` → `qc.cluster_pf`); a missing (`None`) field is **skipped, not
defaulted** (a missing metric is a signal); every runbook threshold keys on a **registered**
`our_key`; and mapping the real `mock_run_01` S5 yields the canonical `normalized_value`s the
rules gate on. The end-to-end guard that this normalization did **not** move any verdict is
the pinned S5 outcome in EVAL-001 (verdicts stayed byte-identical).

**Method.** Map a synthetic and the real S5 `QCMetrics`; assert our_keys/units, the
skipped-`None` behavior, the `cluster_pf` key, and that every runbook threshold resolves to a
registered metric.

**Known failure modes.** A new `QCMetrics` field added without a registry entry would be
silently dropped — surfaced the moment a threshold keys on it
(`test_runbook_thresholds_key_on_registered_metrics`).

### EVAL-006 — Nextflow codegen: deterministic wiring, a drift-pinned reference pipeline, and an honest placeholder for the uncatalogued

| Field | Value |
|---|---|
| **Target** | `bayleaf.nextflow.compile_graph` (card graph → DSL2 Nextflow bundle) + `POST /api/pipelines/compile` |
| **Type** | Deterministic (+ one machine-gated live check) |
| **Automated?** | Yes — `test_nextflow_compile.py` (9 offline + 1 machine-gated) and `test_nextflow_api.py` (4) |

**Definition of good.** The compiler is a pure function: the same graph always yields the same
bundle (no fabricated command, no silently-dropped edge). Concretely: every typed edge in the
graph appears as the matching `UPSTREAM.out.<kind>` channel argument; an unwired input becomes
the correct pipeline-source channel (reads, or a reference `params.*`); a reference FASTA stages
its sidecar-index glob as a tuple; a cycle or an edge to a missing node/port raises
`CompileError` rather than compiling something wrong; a tool outside the curated catalog still
wires correctly but renders as a labelled placeholder process that fails loudly on a real run
(never invents a command); and the seeded germline chain's compiled output is **byte-for-byte
identical** to the committed `pipelines/germline/` reference pipeline (the drift guard) — so
"what the Builder would export" and "the pipeline the demo actually runs" can never silently
diverge. `POST /api/pipelines/compile` mirrors the same guarantees over HTTP plus a 422 with the
compiler's own reason on a cycle/bad/empty graph.

**Method.** Unit-test each wiring rule directly against small hand-built graphs (cycle, bad edge,
uncatalogued tool, repeated tool, reference-as-source-node); assert-equal the full committed
`pipelines/germline/` tree against a fresh `compile_graph(germline_graph())` call; hit the API
endpoint via `TestClient` for the JSON/zip/422 paths. A **machine-gated, skip-safe** test (mirrors
the Postgres live-integration pattern) additionally runs the generated germline pipeline under
real `nextflow run -stub-run` when `nextflow` is on `PATH` — every process' `stub:` touches its
declared outputs, so a pass means the whole DAG's channel wiring is genuinely valid Nextflow, not
just internally self-consistent Python. Absent `nextflow` → skip, never fail.

**Known failure modes.** A hand-edit to `pipelines/germline/` without re-running
`scripts/generate_reference_pipeline.py` is caught immediately by the drift test. The catalog
itself is intentionally narrow (7 germline-chain tools) — this is a documented scope boundary
(§Limitations, [design/nextflow-codegen.md](../design/nextflow-codegen.md)), not a gap this case
claims to cover: "any Builder card compiles to something runnable" is explicitly **not** the
claim.

### EVAL-007 — End-to-end acceptance: sheet → the approval-gated run → report/provenance

| Field | Value |
|---|---|
| **Target** | The full W1+W3+W4 arc over the real API surface — `api/routers/intake.py` (registration), `api/pipeline_store.py` + `api/routers/pipelines_lifecycle.py` (Save→Submit→Approve), `api/routers/pipeline_run.py` (the approval-gated execution, ADR-0017), `GET /api/runs/{id}` (report/provenance data, W3) |
| **Type** | Deterministic (+ one machine-gated live check) |
| **Automated?** | Yes — `test_e2e_pipeline.py` (9 offline + 1 machine-gated: `test_sheet_creation_registers_run_and_skips_unfixtured_samples`, `test_intake_parse_contract_rejects_pii_and_a_no_op_sheet`, `test_approval_gate_blocks_run_until_approved_then_accepts`, `test_run_rejects_a_posted_graph_no_bypass`, `test_seed_script_produces_an_approved_baseline_runnable_by_name`, `test_report_data_verdict_mix_and_per_sample_gate_outcomes`, `test_report_flag_for_review_quotes_clinvar_verbatim`, `test_downstream_provenance_stages_read_honestly`, `test_downstream_stage_seam_mapping_is_honest`, `test_approved_germline_pipeline_stub_runs_live`) |

**Definition of good.** The whole demo arc holds together end to end, over the real API, not just
per-module unit tests: (1) a multi-sample sheet registers a run and honestly reports which
samples are processed vs. skipped (only fixtured samples run), and a smuggled `subject_id`
(PII) is rejected at the parse boundary (422) — never silently accepted. (2) The approval gate
(ADR-0017/REQ-F-086): a saved-but-unapproved pipeline's run 409s; submit→approve mints an
approved baseline; the SAME run then succeeds (202) and the compiled step order is the seeded
germline chain's real topological order (`FASTP`→`BWA_MEM2_MEM`→…→`BCFTOOLS_NORM`); a client
cannot smuggle a raw `graph` to bypass the gate (422, `extra="forbid"`). The committed
`scripts/seed_approved_germline.py` produces a baseline runnable **by name** without clicking
through the Builder, idempotently (a second call mints no duplicate revision). (3) The report/
provenance data (W3, REQ-F-087/REQ-F-088): the pinned `mock_run_01` scenario's verdict mix and
per-sample gate outcomes are exactly what EVAL-001 already pins; the committed
`RUN-2026-07-11-CLINVAR-RTH` fixture escalates via `VAR-FFR-001` with ClinVar quoted **verbatim**
(never bayleaf's own determination); the downstream `review` provenance stage reads ESCALATE
(the fired gate wins over "skipped," the W3 honesty fix), while `filter`/`share` honestly read
"not run in this build" since neither produced an artifact or event on this run.

**Method.** Drive a `TestClient` against the real routers with the intake driver
(`intake._run_pipeline`) and the operator-run background executor (`pipeline_run._execute`)
monkeypatched to no-ops — **no subprocess and no Nextflow ever run** in the offline suite; the
test asserts the WIRING (registration, the approval gate, the compiled step order, the hand-off),
never a live pipeline. The operator-run input catalog is monkeypatched to a deterministic
tmp-path fixture so the happy path is environment-independent; the pipeline store is isolated to
a per-test tmp JSONL. A tenth, env-gated case (`test_approved_germline_pipeline_stub_runs_live`)
confirms the SAME approved graph is a real `nextflow -stub-run`-valid pipeline when `nextflow` is
on `PATH`; absent it, the case **skips**, never fails (mirrors the Postgres-live pattern).

**Known failure modes.** A wiring regression that dropped or reordered a compiled process would
be invisible to per-module unit tests that only check the compiler in isolation — pinned here by
asserting the actual `steps` list `POST /api/pipelines/run` returns. A regression that let a
posted graph bypass the approval gate (the exact audit finding P1-6/P3-14 this arc closes) is
pinned by `test_run_rejects_a_posted_graph_no_bypass`, independent of the store/approval state.
The flag-for-review "skipped-while-escalated" lineage bug (W3) is pinned directly by
`test_downstream_provenance_stages_read_honestly`, not just by the underlying rule test
(EVAL-012) — a regression in the frontend-facing stage-mapping logic, not just the rule, would be
caught here.

### EVAL-008 — Execution reliability: durable job restart recovery + pre-flight fails loud, before launch

| Field | Value |
|---|---|
| **Target** | `api/job_store.py` (durable job store + shared driver launch) + `scripts/run_giab_pipeline.py`'s pre-flight guards |
| **Type** | Deterministic / Failure-mode; the `killpg` reap sub-case (below) IS a live subprocess test |
| **Automated?** | Yes — `test_job_store.py` (16, was 12) and `test_run_giab_preflight.py` (16), both pure-offline (the `killpg` cases spawn a real local child process, no network) |

**Definition of good.** Two independent reliability properties, both landed 2026-07-11 (T-131)
from the release-hardening audit's P3 findings: (1) **A job survives a backend restart.** A
`JsonlJobStore`/`SqliteJobStore` upsert round-trips a job record exactly; a job whose owning
process is gone reconciles to `complete` if its result dir is on disk, else to the new terminal
status `lost` — never left indefinitely `running`. A duplicate run-id reservation under the shared
lock is atomic: a second concurrent submit of the same id cannot also proceed. A driver-launch
timeout kills the WHOLE process group (`os.killpg`), not just the direct child, so no
Nextflow/JVM/tool subtree is left orphaned. (2) **A bad pipeline input fails loud, before
Nextflow launches**, never silently downstream: mismatched/truncated/non-FASTQ R1↔R2 pairs, a
reference↔panel-BED contig-naming mismatch (e.g. `20` vs `chr20`, which would otherwise silently
yield ~0% panel breadth), and a missing reference-index sidecar all raise a specific, actionable
`sys.exit` rather than burning a full launch or yielding a wrong result. A resolved-version probe
(`versions.txt`) never raises on a missing tool — provenance capture must not break a run.

**Method.** `test_job_store.py` exercises both store backends directly: JSONL/SQLite upsert-or-
replace round-trips, `(kind, run_id)` key namespacing, JSONL's tolerant-corrupt-line read,
`get_job_store()`'s degrade-to-JSONL-on-any-construction-failure path, and — by monkeypatching each
router's `_active`/`_DATA` module state (not a live subprocess) — the `_reconcile` restart-recovery
paths directly against `intake.intake_status`/`pipeline_run.run_status` (a `running` job with a
finished result dir → `complete`; with no result → `lost`; still in this process's `_active` set →
left alone; **the Builder-run `_reconcile → lost` branch — the mirror of the intake one — was
previously uncovered and is now tested too**, 2026-07-11 T-137). **Update (2026-07-11, T-137,
closes the gap this case used to name): the process-group `killpg` timeout-reap is now LIVE-tested,
not just asserted at the constant/identity level.** A driver command forks a real grandchild
(`sleep`) that outlives its direct child (`sh`); `test_run_driver_timeout_reaps_the_whole_process_group`
runs it through `run_driver` with a 1s timeout and asserts the grandchild is dead afterward —
proving the whole process group, not just the direct child, is reaped. A companion negative
control, `test_reap_assertion_detects_an_orphan_when_killpg_is_stubbed`, stubs the group-kill down
to a direct-child-only `proc.kill()` (the pre-fix behavior) and asserts the SAME grandchild then
**survives** — proving the positive test's liveness assertion actually detects an orphaned subtree
rather than passing vacuously. Both are skip-gated to POSIX process groups + `/bin/sh`
(`sys.platform != 'win32'`), so they run on this repo's macOS/Linux dev environment but skip
cleanly on Windows. A separate atomic-reservation test
(`test_concurrent_same_run_id_submits_reserve_atomically`) fires two real threads at the same run
id through a `threading.Barrier` and asserts exactly one wins (`queued`) and the other gets a 409 —
the concurrency claim is now genuinely exercised under contention, not just reasoned about.
`test_one_shared_driver_timeout_across_both_routers` still separately confirms both routers call
the SAME `run_driver` function object and that `DRIVER_TIMEOUT_S == 1800`. `test_run_giab_preflight.py`
unit-tests each guard as a pure function of small on-disk fixtures it builds per test (swapped-mate
FASTQs, a contig-mismatched BED, a reference missing one index suffix, a version-probe against a
deliberately-missing tool) — no Nextflow, no real GIAB data, no network.

**Known failure modes.** A store backend that silently dropped a write (rather than raising or
degrading) would be caught by the round-trip assertions; a preflight guard that returned instead
of `sys.exit`-ing on a bad input would let a corrupt run proceed to Nextflow — every guard's
negative case is asserted to raise `SystemExit`, not just to log. A `killpg` reap that only killed
the direct child (the pre-fix behavior) would leave the grandchild alive past the timeout — the
negative control above proves the test suite would catch a regression back to that behavior, not
just pass regardless. **Not covered by an automated test:** the FASTQ-pairing guard's O(reads)
cost has not been benchmarked at real panel/WGS scale, and the `killpg` live test exercises a
local `sh`/`sleep` process tree, not a real multi-process Nextflow/JVM/tool subtree (the shape it
protects in production, per the shared-function-identity check above).

### EVAL-009 — Multi-sample driver parse: N-sample publish dir → N gated run-dir rows (W4 continuation)

| Field | Value |
|---|---|
| **Target** | `scripts/run_giab_pipeline.py`'s post-run parse (`discover_samples`, `parse_publish_dir`, `write_run_dir_multi`) |
| **Type** | Deterministic (offline, fixture-driven; no live Nextflow involved) |
| **Automated?** | Yes — `test_run_giab_multisample.py` (7 tests), pure-offline |

**Definition of good.** A publish dir carrying N per-sample outputs (`${id}.fastp.json` +
mosdepth summary/thresholds + a norm VCF, per sample) parses into **one** run dir with N rows
across every frozen-five CSV, gate-able by the unchanged `run_gate_from_dir` into N cards with
zero read-API/gate change — the same "one run dir, N samples" shape `data/mock_run_01` already
uses. A fan-out of 1 (the shape every live run has taken to date) is **byte-identical** to the
pre-fan-out single-sample format — a hard regression pin. Sample-id matching is dot-prefix-
anchored + `glob.escape`d so a shared-prefix pair (`S1`/`S10`) can never cross-capture another
sample's files. A partial publish dir (a sample present but missing one of its four required
outputs) and an empty publish dir both fail loud (`SystemExit`, naming the sample/pattern) —
never a silently-dropped sample, never a fabricated metric. `demux_stats.csv`'s `% Reads` is each
sample's real share of the run's total reads.

**Method.** Build small hand-crafted publish dirs per test case (fastp JSON, mosdepth summary,
gzipped thresholds BED, a gzipped norm VCF) with `_write_sample_outputs()`, a `skip=` param
letting a test omit one output kind to construct the partial-dir case. Assert the discovered
sample-id order, the row counts in each frozen-five CSV, the exact byte-for-byte content of the
fan-out-of-1 case, and that `SystemExit` is raised (with a message matching the missing sample and
reason) for the partial/empty cases. No Nextflow, no bioconda tools, no network — runs in this
repo's default sandboxed environment.

**Known failure modes.** A regression that silently dropped a partial sample instead of failing
loud would be caught by `test_partial_publish_dir_fails_loud`; a regression in the dot-anchoring
that let `S1` match `S10`'s files would be caught by
`test_sample_id_prefix_is_anchored_no_cross_capture` (distinct `total_reads` per sample makes a
mixup observable). **Not covered by an automated test — stated as an honest, explicit deferral,
not a silent gap:** a genuinely LIVE multi-sample Nextflow run. This case proves the parse/write/
gate logic against fixture publish dirs; it does not prove Nextflow's REAL published output for
an N-row samplesheet matches the shape these fixtures assume, because no second real sample's
panel reads exist on disk in this sandbox — the live driver (`run_nextflow()`) still writes a
single-row (HG002-only) samplesheet. See [design/nextflow-codegen.md §Multi-sample driver
parse](../design/nextflow-codegen.md#multi-sample-driver-parse-2026-07-11-w4-continuation) and
the "What we do not yet verify" item below.

### EVAL-014 — Node-author accept→library: server re-derives, conformance-gates, and stores; the doc-drop importer never invents a live port (W2 backend)

| Field | Value |
| --- | --- |
| **Target** | `api/library_store.py`, `api/routers/node_author.py` (`accept_node_proposal`/`list_library_entries`), `src/bayleaf/node_author/conformance.py`, `src/bayleaf/node_author/importer.py` |
| **Type** | Deterministic (no live Claude call in any of these tests; no verdict/gate involved) |
| **Automated?** | Yes — `test_library_store.py` (6), `test_node_author_accept_api.py` (7), `test_node_author_conformance.py` (13), `test_node_author_importer.py` (8), all pure-offline |

**Definition of good.** Four properties, all landed 2026-07-11 (T-135, "W2 backend"): (1) **A
library entry can never carry a client-authored proposal.** `POST /api/builder/node-proposal/accept`
takes only a `request` string (`extra="forbid"`) and RE-DERIVES the `NodeProposal` server-side via
`propose_node()` — a caller cannot smuggle a fabricated tool/ports/version through the accept body.
(2) **`check_conformance()` mechanically enforces the agent-authoring-contract pins** — advisory
present and `True`; no `verdict`/`confidence` key anywhere in the candidate (scanned recursively,
by key not value, so a legitimate `generated_by: "stub"` value is never a false positive); no
`script`/`stub` command-body key anywhere; every port kind is a real `ARTIFACT_KINDS` member or an
explicitly-declared `reserved` one (and a `reserved_kinds` entry that is secretly a real kind is
itself flagged, `reserved_kind_actually_known`); `corpus_version`/`schema_version`/
`platform_version` pinned, plus the tool `version` when `matched`. It accepts either a validated
`NodeProposal` or a raw untrusted `Mapping` (the load-bearing path for an importer/agent that
hasn't been hardened yet). (3) **The store round-trips a `LibraryEntry` exactly** and is
degrade-to-JSONL like every other pluggable store — `BAYLEAF_LIBRARY_STORE=sqlite` failing to
construct falls back to JSONL, never raises. (4) **The doc-drop importer never fabricates a live
port.** `import_from_nextflow_schema()` maps a schema's `format: file-path` params to a real
`ARTIFACT_KINDS` kind only on a confident name/pattern match; every other param becomes a
`reserved` slot whose slug is guaranteed outside the vocabulary (a fallback slug that would
collide with a real kind is prefixed `reserved_` first) — so its output is conformant by
construction, never requiring a human to catch an invented wire after the fact.

**Method.** `test_node_author_conformance.py` asserts each of the five pins independently (one
test forces a `verdict` key into a nested port/locator/citation and asserts it's caught at depth,
not just top-level; one asserts a `known=True` port outside `ARTIFACT_KINDS` is flagged
`port_known_mismatch`; one asserts a real `ARTIFACT_KINDS` member wrongly listed in
`reserved_kinds` is flagged) plus a conformant-proposal control asserting zero violations, both on
the raw-dict path and the validated-`NodeProposal` path. `test_node_author_accept_api.py` uses a
`TestClient`: an unmatched request 422s with no entry stored; a conformant request 201s and the
returned `LibraryEntry.submitted_by` matches the RBAC actor from the `X-Bayleaf-Actor` header;
a `viewer`-role request 403s (accept is `reviewer`/`approver`-gated); the list endpoint's `tool`/
`status` filters are asserted against a multi-entry fixture. `test_library_store.py` round-trips
both the JSONL and SQLite adapters with the same fixture record and asserts they agree
byte-for-byte on `list()` ordering (`created_at` then `id`). `test_node_author_importer.py` feeds
a small hand-built nf-core-shaped schema (`definitions`/`$defs` groups, a `title`, a mix of
`file-path` and non-file-path params) and asserts: only `file-path` params become ports; a
recognized name (`input_fastq`, `reference_fasta`, …) maps to a live kind; an unrecognized name
maps to a `reserved` slug; the resulting `NodeProposal` passes `check_conformance()` with zero
violations (closing the loop back to item 2 above) — no network, no live Claude call anywhere in
this file.

**Known failure modes.** A future code path that let the accept endpoint trust a client-supplied
proposal field would be caught by the `extra="forbid"` schema rejection (asserted directly); a
conformance-check regression that stopped scanning nested structures for a forbidden key would be
caught by the depth-specific test named above; an importer regression that let an unrecognized
param name silently map to a real `ARTIFACT_KINDS` kind (rather than falling through to
`reserved`) would fail the conformance-closes-the-loop assertion. **Not covered by an automated
test:** the Builder's own "Accept to library" UI action (no frontend caller exists yet — this case
is backend-only, see [design/agent-authoring-contract.md](../design/agent-authoring-contract.md)
§Status); the `draft→approved` transition (no code path sets `status="approved"` yet, so there is
nothing to test); the free-text `--help`/README half of the doc-drop importer (not built); a
roster-wide, CI-parametrized sweep of `check_conformance()` across all six advisory agents (today
it is invoked against node-authoring candidates only).

### EVAL-015 — Operator-authored custom-script processes: verbatim rendering, catalog bypass, and never-fabricate (ADR-0020)

| Field | Value |
| --- | --- |
| **Target** | `src/bayleaf/nextflow/compiler.py` (`NfNode.script`/`.is_custom()`, `_render_custom`, `_render_module`), `api/routers/nextflow.py` (`CompileNode.script`/`.container`/`.conda`) |
| **Type** | Deterministic (pure text codegen; no live Claude call; no verdict/gate touched) |
| **Automated?** | Yes — `test_nextflow_custom_process.py` (9, pure-offline, no `TestClient`) + 2 cases in `test_nextflow_api.py` (over a `TestClient`) |

**Definition of good.** A Builder card MAY carry a human-authored verbatim Nextflow `script:` body
(plus optional `container`/`conda`) — a THIRD compile path alongside a catalogued tool and an
uncatalogued placeholder. Five properties make it trustworthy: (1) **The catalog is never
consulted for a custom node**, even when the card's tool NAME collides with a catalogued one
(`bcftools norm`) — the operator's body always wins. (2) **The body is emitted byte-for-byte**
(only re-indented into the `script:` block), never rewritten or fabricated, and wired from the
node's own typed `ins`/`outs` exactly like a catalogued per-sample process (meta-threaded). (3)
**An honest label is unconditional** — every custom module carries a header comment stating it is
operator-authored, not curated, and needs production sandboxing, plus `label 'operator_authored'`
on the process itself. (4) **Never fabricate**: a blank/whitespace `script` is a `CompileError`
(surfaced as a 422 at `POST /api/pipelines/compile`) — distinct from an uncatalogued node with NO
script at all (`script is None`), which keeps its pre-existing labelled placeholder unchanged, never
an error. (5) **A novel output kind is allowed and wired by its raw name** (`emit: <kind>`) —
the compiler never crashes just because a custom process emits something outside the built-in
`ARTIFACT_KINDS` vocabulary.

**Method.** `test_custom_process_renders_verbatim_wired_and_labelled` compiles a two-node graph
(a catalogued `bcftools call` feeding a custom `bcftools annotate` card) and asserts the operator's
exact command string appears in the emitted module, the header/label strings are present, the
operator's `container`/`conda` are threaded through, and `main.nf` wires
`BCFTOOLS_ANNOTATE(BCFTOOLS_CALL.out.vcf)` from the typed edge.
`test_custom_node_never_consults_the_catalog_even_on_a_name_collision` reuses the catalogued name
`bcftools norm` for a custom card and asserts the curated `bcftools norm -f` command does NOT leak
into the output. `test_empty_custom_script_is_a_compile_error` is parametrized over `""`, `"   "`,
and a whitespace-only multi-line string, asserting `CompileError` with `"empty script"` every time.
`test_uncatalogued_no_script_node_keeps_its_placeholder_not_an_error` asserts the pre-existing
uncatalogued path (`script is None`) is byte-for-byte unaffected — still the `PLACEHOLDER`/`exit 1`
module, never mislabelled `operator_authored`.
`test_germline_carries_no_custom_node_and_drift_stays_green` compiles the seeded germline graph and
asserts (a) no emitted file contains the custom-process header/label anywhere, and (b) the
compiler's output still matches the committed `pipelines/germline/` reference byte-for-byte (the
pre-existing drift guard) — pinning that the feature is purely additive.
`test_compile_returns_text_and_spawns_no_subprocess` monkeypatches `subprocess.run`/`Popen` to raise
if called, then compiles a custom-node graph and asserts it succeeds untouched — compose ≠ execute
holds even for operator-authored text.
`test_custom_process_may_emit_a_kind_outside_the_known_vocabulary` compiles a custom node emitting
a novel `cnv_segments` kind and asserts it is wired by name (`emit: cnv_segments`), never rejected.
`tests/test_nextflow_api.py::test_compile_accepts_an_operator_authored_custom_script_node` and
`::test_compile_rejects_a_blank_custom_script_with_a_422` re-run the wire-level shape of cases 1 and
4 above through the real FastAPI `TestClient`, confirming the additive `CompileNode` fields
(`script`/`container`/`conda`) round-trip over HTTP.

**Known failure modes.** A future change that let `_render_module` check the catalog before
`is_custom()` would be caught by the name-collision test; a regression that rendered a blank script
as an empty/placeholder command (rather than raising) would fail the parametrized blank-script
test; a regression that dropped the honest header/label would fail the labelled-render assertion.
**Not covered by an automated test:** the custom script itself running under any bayleaf-side
runtime sandbox (there is none — ADR-0020 states the approval gate + the honest label +
deployment-side sandboxing are the safety envelope, not a sandbox bayleaf builds); a LIVE
`nextflow run` of a custom process against real inputs (only the germline chain's own
`-stub-run` is live-verified, EVAL-006 — a custom process has never been executed by Nextflow in
this repo, only compiled); the Builder's `CustomScriptInspector` UI itself (frontend, not unit
tested here — see [design/builder-cards/README.md §7](../design/builder-cards/README.md#7-retired-placeholders-a-generic-file-input-source-and-the-custom-script-card-2026-07-11-branch-featcustom-script-io)).

### EVAL-016 — Sandboxed server-side file browser: allowlisted, traversal-hardened, metadata-only (ADR-0020)

| Field | Value |
| --- | --- |
| **Target** | `api/routers/files.py` (`GET /api/files`) |
| **Type** | Deterministic (pure filesystem read + boundary checks; no verdict/gate touched) |
| **Automated?** | Yes — `test_files_api.py` (10, `TestClient`-driven, pure-offline) |

**Definition of good.** Two hard boundaries make it safe to point at a real, GB-scale data host:
(1) **Allowlist, not free filesystem access** — `root` is a KEY into a small configured map
(`BAYLEAF_BROWSE_ROOTS`, default `{"data": <repo>/data}`), never a raw path; an unknown key is a
404, never a filesystem probe. (2) **Traversal-hardening that PROVABLY cannot leak** — a `..`
component or a leading `/` (absolute path) is rejected (400) BEFORE the filesystem is touched; the
resolved `root/path` is then asserted to remain inside the resolved root, catching an escaping
SYMLINK (a case the pre-checks structurally cannot see, since the path spelling is clean) at the
`resolve()`-and-assert step (403). Every rejection is checked to never leak the out-of-root content
even in its error body. The endpoint returns METADATA ONLY (name/is_dir/size/an
extension-inferred kind) — it never reads or serves file bytes.

**Method.** `_make_sandbox` builds a controlled root under `tmp_path` with a nested layout AND
plants a sentinel string (`_SECRET`) in a file just OUTSIDE the root, redirecting
`BAYLEAF_BROWSE_ROOTS` to it per-test (env read per-request, not cached). Every traversal test
(`test_dotdot_traversal_is_rejected_and_does_not_escape`,
`test_absolute_path_is_rejected_and_does_not_escape`,
`test_symlink_escaping_the_root_is_forbidden`) asserts BOTH the correct status code (400/400/403)
AND `_SECRET not in resp.text` — a positive check that the response body could never have
exfiltrated the out-of-root content, not just that the status code "looks right." The symlink case
specifically creates a symlink INSIDE the sandboxed root pointing to the root's own PARENT
directory (which holds the secret) and confirms it 403s only once resolved, proving the
resolve-and-assert step (not just the `..`/absolute pre-checks) is load-bearing.
`test_list_the_data_root_returns_entries` exercises the REAL default root (the repo's `data/`, no
env override) and asserts a known committed run dir appears and directories sort before files.
`test_kind_inference_across_extensions` asserts `.vcf.gz` → `vcf` (a double extension), `.fastq.gz`
→ `fastq`, `.fasta` → `reference_fasta`, `.bed` → `panel_bed`, and an unrecognized extension → an
honest `null`, never a guess — and separately asserts the response echoes only the allowlist KEY
(`"sandbox"`), never the root's real absolute on-disk path.
`test_nested_subdir_returns_correct_parent` walks two levels deep and asserts the `parent` link is
correct at each level, that a trailing slash normalizes without changing the listing, and that a
LEADING slash is rejected (400) rather than silently normalized (an asymmetry the test makes
explicit). `test_viewer_role_may_browse` asserts the lowest RBAC role is sufficient — allowlisted
browsing is read-only but not anonymous.

**Known failure modes.** A regression that checked `..`/absolute BEFORE resolving symlinks but
skipped the post-resolve assert would be caught by the symlink-escape test specifically (the other
two pre-checks alone cannot catch it). A regression that echoed the resolved absolute path (leaking
server filesystem layout) would fail the "echoes only the KEY" assertion in the kind-inference test.
**Not covered by an automated test:** the Builder's `FileBrowser.tsx` picker UI itself (frontend,
not exercised here); a live `BAYLEAF_BROWSE_ROOTS` override pointing at a genuinely large
(GB-scale) production data host (only a `tmp_path`-scoped sandbox and the repo's own small `data/`
are exercised); concurrent/multi-request race conditions on a mutating filesystem (the endpoint is
read-only, so this is a low-probability, low-consequence gap, not asserted either way).

### EVAL-017 — Nextflow compiler robustness: hostile/off-golden-path graphs compile correctly or fail loud (never silently wrong)

| Field | Value |
| --- | --- |
| **Target** | `src/bayleaf/nextflow/compiler.py` |
| **Type** | Deterministic (pure text codegen; compose ≠ execute — no tool runs) |
| **Automated?** | Yes — `test_nextflow_robustness.py` (17) + the byte-for-byte germline drift guard in `test_nextflow_compile.py` |

**Definition of good.** Each of the compiler robustness-review fixes is pinned by one adversarial
case: a graph that *used to* compile to a silently-wrong or unparseable bundle now either compiles
correctly or raises a `CompileError` — it never emits a plausible-but-wrong pipeline. The golden
germline chain stays byte-identical (the drift guard), proving these fixes touch only
off-golden-path/hostile inputs.

**Method.** One test per verified fix (review rank → test): (1) two distinct tools sharing a
process name are rejected rather than colliding into one module; (2) a `File input` source node of a
data kind (e.g. fastq) wires to the reads channel and a novel-kind source becomes a params channel,
rather than emitting a zero-input dangling process; (3) fan-in / duplicate-emit / port-drift guards
catch a graph whose edges no longer match a node's declared ports; (4) operator-supplied strings
(labels, script bodies) are injection-escaped so a quote/`$`/backtick cannot break out of the
generated Groovy. The last two cases in-file re-assert the golden path so the suite doubles as a
regression pin. Custom-script rendering (EVAL-015) and the drift guard (EVAL-006) stay green.

**Known failure modes.** A future compiler change that made an uncatalogued tool emit a runnable-
looking command instead of a labelled placeholder would violate the honesty framing but is NOT
directly asserted here (covered by EVAL-006/EVAL-015). The escaping is asserted against the
specific hostile strings the review found, not proven exhaustively against all injection vectors.

### EVAL-018 — Operator-gated authored-pipeline intake: approval-gated, parked, released — driver never fires on its own (ADR-0021)

| Field | Value |
| --- | --- |
| **Target** | `api/routers/intake.py`, `api/authored_pipeline.py`, `api/job_store.py` (`POST /api/runs`, `POST /api/runs/{id}/release`) |
| **Type** | Deterministic (execution-boundary control flow; off the decision gate) |
| **Automated?** | Yes — `test_intake_scheduling.py` (22, was 15; offline — the background driver is monkeypatched, so no thread runs `nextflow`). +3 as of 2026-07-13 (T-148, PR #10): `test_submit_snapshots_authored_pipeline_agent_bindings`/`test_submit_records_empty_binding_snapshot_for_default_reference`/`test_held_submit_snapshots_bindings_at_submit_not_release` — prove the ADR-0024 agent-binding snapshot this endpoint now records at submit (a related but distinct property from the scheduling gate below: WHICH agents get enforced read access to the run, not whether it runs) |

**Definition of good.** Two properties, both off the deterministic gate (ADR-0001) and preserving
compose ≠ execute (ADR-0003 — the core still never runs a tool). (1) **Authored pipeline via the
same approval gate.** A `POST /api/runs` naming a `pipeline` resolves + compiles that pipeline's
approver-blessed (`emitted`) snapshot through the SHARED `api/authored_pipeline.py` gate that
`POST /api/pipelines/run` uses — a name with no approved version is a **409**, a raw client-posted
graph is impossible (no such field), and absent → the drift-proven committed `germline-panel`
reference (byte-preserved). (2) **The processing gate parks and releases.** `mode=hold`/`schedule`
registers the run WITHOUT firing the driver (`held`/`scheduled` state); `POST /api/runs/{id}/release`
fires it later (409 if not parked, 404 if unknown). The driver-argv construction is exercised
against a seeded job record with `run_driver` captured, so the test proves the release fires the
driver identically to an immediate submit without ever launching Nextflow.

**Known failure modes.** No **time-based auto-release scheduler** exists — `scheduled` is `hold`
plus a stored `scheduled_at` and an honest note; the operator releases manually. This is a
deliberate deferred seam (ADR-0021), asserted only insofar as no background timer is expected to
fire; a genuinely live multi-sample Nextflow run through an authored pipeline stays unverified in
this sandbox (EVAL-009).

### EVAL-019 — Builder-graph compile: every shown port is a real channel, and an agent binding is off the compile path

| Field | Value |
| --- | --- |
| **Target** | `src/bayleaf/nextflow/catalog.py`, `src/bayleaf/nextflow/compiler.py`, `api/routers/nextflow.py` (`CompileRequest`) |
| **Type** | Deterministic (pure text codegen; compose ≠ execute — no tool runs) |
| **Automated?** | Partly. **Port promotion:** Yes — `test_nextflow_promoted_ports.py` (5) + the mosdepth-5-output regression in `test_nextflow_compile.py` + the byte-for-byte germline drift guard (EVAL-006). **Agent-binding compile isolation:** by construction (frontend payload is `{nodes, edges}` only; `CompileRequest` is pydantic `extra="ignore"`), pinned indirectly by the drift guard — no dedicated backend test (`69a2dab` touched no `src/`/`tests/`). |

**Definition of good.** Two properties of "what the compiler emits for a Builder graph." (1)
**No superficial ports** (REQ-F-102): every port a Builder tool card advertises maps to a REAL
emitted Nextflow channel or is removed — a promoted port (`unpaired_fastq`, `failed_fastq`,
`vcf_index`, `multiqc_html`) is a genuine byproduct of the existing `script:`/`stub:` command, and
a removed one (`read_group`, `per_base`, `panel_bed`, `fastqc_zip`, …) was never a real file. A
5-output mosdepth node compiles cleanly (closing the Export-to-Nextflow 422 the earlier 2-vs-5
arity gap caused), while the seeded `germline_graph()` stays a valid summary+thresholds subset.
(2) **An agent binding is off the deterministic compile path** (REQ-F-101): the Builder persists
`AgentBinding`s in a `graph.agent_bindings` envelope key, and compiling a graph with vs. without
bindings yields byte-identical output because the compile payload is only `{nodes, edges}` and
`CompileRequest` ignores extra keys — a binding structurally cannot touch the emitted Nextflow or a
verdict (ADR-0001 + compose ≠ execute).

**Method.** For (1), `test_nextflow_promoted_ports.py` asserts each promoted port emits its real
channel with the matching command flag, and that the removed ports are absent; the
`test_five_output_mosdepth_node_compiles_and_emits_all_channels` case builds a 5-output mosdepth
node and asserts it no longer raises `CompileError` and declares every byproduct with its real
filename. The germline drift guard (EVAL-006) re-asserts the golden chain is byte-unchanged. For
(2), the isolation rests on the payload shape + `extra="ignore"`; the drift guard pins that the
compiler output is a pure function of `{nodes, edges}`, so no `agent_bindings` key could alter it.

**Known failure modes.** The agent-binding isolation is **not** asserted by a dedicated test that
posts an `agent_bindings` key and diffs the bundle — a future change that made `CompileRequest`
consume extra keys would break the invariant without tripping a red test here (mitigated only
indirectly by the drift guard). A newly-added port that is shown but not actually emitted would
regress (1); it is caught only if a promoted-ports test names it. `adapter_fasta` stays honestly
reserved (a real optional input), so its absence from the emitted channels is expected, not a bug.

## Failure-mode cases (synthetic)

### EVAL-010 — Each contrived fault reaches its intended verdict

| Field | Value |
|---|---|
| **Target** | `bayleaf.synthetic` generator across all `FailureMode`s |
| **Type** | Failure-mode |
| **Automated?** | Yes — `test_synthetic.py` (`test_each_failure_mode_hits_intended_verdict`, `test_mixed_run_every_sample_matches_intent`, `test_committed_demo_run_verdicts`, `test_committed_demo_run_is_reproducible`, `test_generated_run_parses_with_existing_parsers`) |

**Definition of good.** clean → **proceed**; barcode_swap / absent_from_sheet →
**escalate**; missing_metadata / low_q30 / low_coverage / high_dup → **hold**;
pipeline_failure (a run-log failure marker, PIPE-001) → **rerun**; process_failure (a failed
execution-trace task, EXEC-001) → **rerun**. Generated runs parse with the *existing* parsers (no
generator-only dialect) and are byte-reproducible.

**Method.** Generate one run per mode into a temp dir, gate it, assert the verdict
equals `INTENDED_VERDICT[mode]`; regenerate and assert identical output; parse the
committed `mock_run_02/03` and assert their pinned verdict vectors.

**Known failure modes.** The generator drifting from real artifact shapes — mitigated by
reusing the production parsers in the assertion (`test_generated_run_parses_with_existing_parsers`).

### EVAL-011 — Execution-trace ingestion: a failed process → EXEC-001 → RERUN

| Field | Value |
|---|---|
| **Target** | Execution-trace rule (`rules._check_execution_trace`, **EXEC-001**) end-to-end through the gate + into the pipeline-repair feed |
| **Type** | Failure-mode |
| **Automated?** | Yes — `test_execution_trace.py` (`test_parse_execution_trace_tab_separated`, `test_parse_execution_trace_is_tolerant`, `test_exec_001_failed_task_is_a_rerun_finding`, `test_exec_001_is_a_no_op_when_clean_or_absent`, `test_exec_001_tag_exact_match_no_crossfire`, `test_exec_001_end_to_end_through_the_gate`, `test_no_trace_file_means_no_exec_finding`, `test_exec_001_feeds_the_repair_agent`) |

**Definition of good.** A Nextflow/nf-core `trace.txt` is **read** on the gate path (composes ≠
executes — it reads a trace the run already emitted, never runs a process): a failed task
(status in the runbook's failure-status set **or** a nonzero exit — so an OOM/time-kill fires
even when the status isn't literally `FAILED`) becomes a structured, cited **EXEC-001** `Finding`
(PIPELINE category, preflight gate) whose `suggested_verdict` is **RERUN**, driving the sample to
RERUN end-to-end while a clean sample stays PROCEED. The task attaches to its sample by an
**exact** nf-core `tag` match (S1 never cross-fires S10 — the substring trap PIPE-001's log grep
must avoid). A clean task, no `trace.txt`, or an unknown sample yields **no** finding (a missing
trace is a signal, not a crash; the pinned demo runs carry no `trace.txt` and are unaffected). The
EXEC-001 finding's recurring signature then **flows to the advisory pipeline-repair agent** (a
`RepairProposal`, `advisory=True`, no verdict).

**Method.** Parse a hand-built trace (tab-separated, plus a garbled/absent file for tolerance);
assert the rule fires on `FAILED` and nonzero-exit tasks and no-ops on clean/absent/unknown;
generate a synthetic `PROCESS_FAILURE` run, gate it, and assert S02 → RERUN with an EXEC-001
finding while the clean sample stays PROCEED and a no-failure run emits no `trace.txt`; roll the
signature up and assert `propose_repair` returns an advisory proposal addressing EXEC-001.

**Known failure modes.** A substring tag match would let S1's failure attach to S10 — pinned by
`test_exec_001_tag_exact_match_no_crossfire`. A trace parse that crashed on a garbled file would
break the tolerant boundary — asserted by `test_parse_execution_trace_is_tolerant`. Ingesting a
trace must not change the pinned demo verdicts (those runs have no `trace.txt`) — preserved by
EVAL-001/EVAL-010.

### EVAL-012 — Flag for review (VAR-FFR-001): off by default, verbatim ClinVar, rules decide

| Field | Value |
|---|---|
| **Target** | Flag for review gate rule (`rules._check_flag_for_review`, **VAR-FFR-001**) — `runbook.FlagForReviewPolicy` + `models.VariantCall` + `parsers.parse_variant_calls` end-to-end through the gate |
| **Type** | Failure-mode |
| **Automated?** | Yes — `test_flag_for_review.py` (`test_parse_variant_calls_reads_verbatim`, `test_parse_variant_calls_is_tolerant`, `test_flag_for_review_is_off_by_default`, `test_armed_pathogenic_routes_to_human`, `test_armed_benign_does_not_route`, `test_significance_match_is_separator_insensitive`, `test_review_status_floor_gates_routing`, `test_end_to_end_armed_run_escalates_the_card`, `test_disarmed_run_matches_stock_evaluation`, `test_clinvar_rth_fixture_escalates_via_per_run_arming` — 2026-07-11, the committed-fixture end-to-end case, see Method below) |

**Definition of good.** With the policy **disarmed** (the shipped default — empty
`significances`), a run carrying even a Pathogenic candidate produces **no** routing finding and
`evaluate_sample` is byte-identical to a run with no `variants.csv` at all. **Armed** with a
significance list, a matching candidate produces a CRITICAL `Finding` (`rule_id="VAR-FFR-001"`,
`category=variant`, lands on `Gate.VARIANT`) whose `suggested_verdict` is **ESCALATE** and drives
the card to ESCALATE end-to-end (rules decide, ADR-0001); a Benign candidate never routes; the
match is separator-/case-insensitive (`Likely_pathogenic` ≈ `"Likely pathogenic"`) while the
**quoted evidence stays verbatim** (never bayleaf's own determination, ADR-0004); an optional
review-status allow-list acts as a stricter star-rating floor. The parser preserves
`clinvar_significance` verbatim and is tolerant of an absent file or alternate column spellings
(`clnsig`/`clnrevstat`/`clnacc`).

**Method.** Parse a contrived `variants.csv` (one Pathogenic, one Benign candidate, `origin=
contrived`, never implying a real individual — the only real substrate is GIAB HG002); assert the
rule is a no-op on the disarmed `DEFAULT_RUNBOOK`; arm a copy of the runbook and assert the finding
fires only for the matching significance, cites the accession/version, and quotes CLNSIG verbatim;
assert the review-status floor gates a single-submitter call; run the gate end-to-end on an armed
vs. disarmed runbook and assert ESCALATE only when armed. **2026-07-11 addition:** exercise the
same rule against a **committed run**, not just an in-memory fixture — `api.main._active_runbook`
reads the `flag_for_review` marker in `data/RUN-2026-07-11-CLINVAR-RTH/` (a real HG002 run,
`origin=contrived`, carrying a verbatim-cited ClinVar Pathogenic BRCA1 spike HG002 does not
actually carry) and asserts the card ESCALATEs via `VAR-FFR-001` with the verbatim `CLNSIG`
evidence, while an unmarked committed run (`RUN-2026-07-04-GIAB-A`) stays disarmed — closing the
"never fires end-to-end against a committed run" gap the 2026-07-10 sweep had left open.

**Known failure modes.** A rule that fired on a disarmed default would move the pinned demo
verdicts — prevented structurally (empty tuple ⇒ `.armed is False`) and pinned by
`test_flag_for_review_is_off_by_default`/`test_disarmed_run_matches_stock_evaluation`. A rule that
normalized or reclassified `clinvar_significance` before quoting it would risk bayleaf
authoring pathogenicity — pinned by `test_armed_pathogenic_routes_to_human` asserting the quoted
value is verbatim.

### EVAL-013 — Per-variant Report endpoint: read-only, ClinVar verbatim, honest empty state (W3 continuation)

| Field | Value |
|---|---|
| **Target** | `GET /api/runs/{run_id}/variants` (`api/main.py`) — the same `bayleaf.parsers.parse_variant_calls` EVAL-012 exercises, now also served over the wire |
| **Type** | Failure-mode / read-contract |
| **Automated?** | Yes — `test_run_variants.py` (3 tests): `test_variants_served_for_clinvar_run`, `test_variants_empty_for_run_without_variants_csv`, `test_variants_unknown_run_is_404` |

**Definition of good.** The endpoint is a pure read projection — it authors no verdict, sets no
confidence, and every ClinVar field renders exactly as the parser returned it (VERBATIM, never
normalized/reclassified, ADR-0004). A run whose `variants.csv` carries a row serves it with every
field intact; a run with no `variants.csv` returns `[]` (an honest empty state — a missing
annotation is a signal, not an error, never a fabricated row); an unknown run id is a 404,
mirroring `get_run`/`get_card`'s existing read pattern (no new exposure — the same ClinVar value
this endpoint serves was already reachable through a fired flag-for-review `card.findings`
citation, EVAL-012).

**Method.** Hit the endpoint via `TestClient` against the committed `RUN-2026-07-11-CLINVAR-RTH`
fixture and assert every field of its single BRCA1 `c.68_69del` row matches `variants.csv`
verbatim (`clinvar_significance == "Pathogenic"`, the exact accession/review-status/version);
assert `mock_run_01` (no `variants.csv`) returns `200` with an empty list, not a 404; assert an
unknown run id (`NOPE`) 404s.

**Known failure modes.** A regression that normalized/reclassified `clinvar_significance` before
serving it would be caught by the exact-string assertion in
`test_variants_served_for_clinvar_run`; a regression that 404'd a variant-less run instead of
returning `[]` (conflating "no annotation" with "unknown run") would be caught by
`test_variants_empty_for_run_without_variants_csv`. **Not covered:** the fuller
`AnnotatedVariant` evidence join (gnomAD AF, inheritance-fit, call-quality) design-only per
[design/variant-interpretation.md §0 item 4](../design/variant-interpretation.md) — this case
covers only the `VariantCall`/D2 fields that shipped.

## Faithfulness cases (AI narrates, never decides)

### EVAL-020 — Triage note never touches the verdict

| Field | Value |
|---|---|
| **Target** | Triage agent (stub **and** claude path) |
| **Type** | Faithfulness |
| **Automated?** | Yes — `test_triage.py` (`test_note_never_touches_the_verdict`, `test_note_addresses_the_flagged_findings`, `test_note_cites_corpus_and_findings`, `test_note_content_hash_is_stable_and_deterministic`) |

**Definition of good.** A `TriageNote` addresses the flagged findings and cites both the
corpus and the findings, and it **cannot** carry or alter a verdict/confidence (the type
has no such field). A clean/proceed card yields no note.

**Method.** Run triage on flagged and clean cards; assert citations present, verdict
untouched, and note hash stable/deterministic.

**Known failure modes.** A future schema change adding a decision-bearing field to the
note — structurally prevented today; re-audit if the model is expanded.

### EVAL-021 — Live AI degrades to the deterministic stub

| Field | Value |
|---|---|
| **Target** | `claude` synthesizer / triage path under failure |
| **Type** | Faithfulness |
| **Automated?** | Yes — `test_triage.py` (`test_claude_path_prose_is_llm_but_citations_stay_deterministic`, `test_claude_path_falls_back_to_stub_on_refusal`, `test_claude_path_falls_back_to_stub_on_error`, `test_triage_endpoint_returns_advisory_note_for_flagged_sample`, `test_triage_endpoint_404s_for_clean_and_unknown_samples`) |

**Definition of good.** With the claude path selected, prose may be model-authored but
**citations and addressed findings stay deterministic**; any error or safety refusal
falls back to the stub (no 500, no broken demo). The API returns an advisory note for a
flagged sample and 404s for clean/unknown ones.

**Method.** Monkeypatch the client to raise / to return a refusal; assert stub fallback
and preserved citations. (This case fixed a real demo bug: a datetime-serialization
error that previously produced a 500 before the fallback could run.)

**Known failure modes.** A new field serialized outside the try-block would resurrect the
500 — the regression test pins the fallback.

## Notify-port cases (outbound integration seam)

### EVAL-040 — Notify fires only for actionable cards, and each send is one provenance event

| Field | Value |
|---|---|
| **Target** | Notify port policy + `notification.emitted` trail (engine wiring, ADR-0010 / ADR-0002) |
| **Type** | Deterministic |
| **Automated?** | Yes — `test_notify.py` (`test_notify_policy_notifies_only_actionable_cards`, `test_clean_proceed_card_is_skipped_and_not_recorded`); `test_gate_notify.py` (`test_notifier_notifies_actionable_cards_and_records_outbox`, `test_notifier_emits_one_notification_event_per_actionable_card`, `test_notification_event_payload_records_result_and_no_secret`, `test_no_notifier_emits_zero_notify_events_and_preserves_trail`, `test_notifier_does_not_change_the_cards`, `test_notify_events_survive_persistence_round_trip`, `test_each_actionable_notification_anchors_to_its_card[S4]`, `[S5]`) |

**Definition of good.** Only *actionable* (non-PROCEED) cards notify — a clean PROCEED card is
skipped and nothing is recorded. Each real notification emits exactly one `notification.emitted`
event anchored to its card (S4, S5 in the demo); the event payload records the result but **no
secret**; the notifier never mutates a card; and the events survive the persistence round-trip.
With **no** notifier wired (the default), zero notify events fire and the trail is byte-for-byte
unchanged.

**Method.** Gate `mock_run_01` with and without a notifier; assert the skip/prepare policy, one
event per actionable card, no-secret payloads, unchanged cards and trail, and event survival
through `rebuild-db`.

**Known failure modes.** A notifier that touched a card would violate the "port consumes
finished cards" contract — asserted against (`test_notifier_does_not_change_the_cards`). An
all-clear notification would spam the channel — the actionable-only policy prevents it.

### EVAL-041 — Live Slack send is opt-in and degrades to the offline stub

| Field | Value |
|---|---|
| **Target** | Slack adapter live-send seam (`BAYLEAF_SLACK_LIVE`) + `get_notifier` selection |
| **Type** | Failure-mode |
| **Automated?** | Yes — `test_notify.py` (`test_get_notifier_defaults_to_stub`, `test_get_notifier_selects_slack_from_env`, `test_get_notifier_unknown_value_falls_back_to_stub`, `test_slack_with_no_creds_falls_back_to_stub_without_sending`, `test_slack_env_path_degrades_and_does_not_send`, `test_slack_live_seam_falls_back_to_stub_on_error`, `test_slack_live_seam_missing_client_lib_falls_back_to_stub`, `test_slack_live_seam_posts_via_client_when_explicitly_enabled`, `test_slack_never_sends_when_not_armed_even_with_creds`, `test_slack_channel_is_read_from_env_never_hardcoded`) |

**Definition of good.** The notifier defaults to the offline `stub` ($0; nothing leaves the
machine). `BAYLEAF_NOTIFIER=slack` selects the adapter, but a real post fires **only** when
`BAYLEAF_SLACK_LIVE` is armed *and* a bot token + channel are present. Missing creds, a
missing Slack SDK, or any Slack error degrade to the stub (payload built + recorded, not sent).
The channel is read from env, never hardcoded. With the seam explicitly enabled and a client
present, it posts exactly once.

**Method.** Vary the environment (unset / `slack` / unknown / armed-without-creds /
armed-with-mock-client / error / missing-lib) and assert the resolved adapter and that a send
happens **only** in the armed-and-credentialed case — no send on every other path.

**Known failure modes.** A default that sent, or a send reachable without the explicit flag,
would leak data and burn budget — pinned by `test_slack_never_sends_when_not_armed_even_with_creds`.
See [risks.md](risks.md) RISK-033.

### EVAL-042 — Payload is per-verdict and copies (never sets) the verdict

| Field | Value |
|---|---|
| **Target** | Notify payload builder (`build_payload` / stub adapter) + the `python -m bayleaf.notify` CLI |
| **Type** | Faithfulness |
| **Automated?** | Yes — `test_notify.py` (`test_stub_builds_wellformed_payload_for_flagged_card`, `test_payload_is_category_specific_by_verdict`, `test_payload_reflects_the_cards_verdict_not_a_new_one`, `test_payload_is_deterministic`, `test_notify_card_entry_point_uses_env_notifier_and_injection`, `test_notify_cli_gates_and_reports_actionable`, `test_notify_cli_no_args_returns_usage`) |

**Definition of good.** Payload framing is category-specific per verdict (escalate = provenance/
identity risk; rerun = operational failure; hold = borderline QC needing operator judgment); it
cites the card's evidence (observed vs. expected); and it **mirrors** the gate's verdict rather
than deriving a new one — the type copies `verdict`/`headline` and cannot decide (ADR-0001).
Identical cards yield an identical (content-hashed) payload. The CLI gates a run dir and reports
the actionable set (and prints usage on no args).

**Method.** Build payloads for escalate / rerun / hold cards; assert per-verdict framing,
evidence citation, verdict-mirroring, and determinism; exercise the CLI happy path and no-args
usage.

**Known failure modes.** A payload builder that inferred a verdict would break the
rules-decide invariant — structurally prevented (the payload only reads already-decided
fields). Interpolating timestamps/ids into the body would break reproducibility — the builder
interpolates none.

## De-identification cases (egress transform, never touches a decision)

### EVAL-050 — Safe-Harbor-style scrub redacts identifiers and never touches a verdict

| Field | Value |
|---|---|
| **Target** | Conservative Safe-Harbor-style de-id egress transform (`api/safe_harbor.py`, ADR-0018 D3) |
| **Type** | Faithfulness |
| **Automated?** | Yes — `test_safe_harbor.py` (`test_redact_free_text_scrubs_each_class`, `test_redact_free_text_leaves_non_identifiers`, `test_generalize_date_keeps_year_only`, `test_cap_age_buckets_over_89`, `test_redact_record_drops_direct_identifiers`, `test_redact_record_caps_age`, `test_redact_record_never_touches_verdict_or_gate`, `test_policy_is_labelled_style_not_certified`) |

**Definition of good.** `redact_free_text` replaces every regex-detectable identifier (email,
phone, SSN, URL, IP, date, ZIP, long numeric id) with `[REDACTED:CLASS]` and leaves a benign
sentence unchanged. `generalize_date` reduces any date to year-only and **fails closed** to
`[REDACTED:DATE]` (never a silent passthrough) when no year is recognizable. `cap_age` buckets
ages over 89 into `"90+"`. `redact_record` drops direct-identifier fields (`submitted_by`,
`subject_id`, …) entirely, generalizes date fields, redacts free-text fields, caps age, and —
**the ADR-0001 boundary this suite pins** — passes a `verdict`/`confidence`/`gate` riding along in
an egress row through **untouched**: the scrub shapes identifiers, it never reads or alters a
decision. The honesty guardrail: `SAFE_HARBOR_POLICY_ID` contains `"style"` and never claims
`"hipaa-compliant"`; all 18 §164.514(b)(2) identifier classes are documented (some as explicit
"not present in this data model" seams).

**Method.** Feed a free-text string carrying every regex-detectable class and assert none of the
raw values survive; feed a benign sentence and assert it is byte-identical; feed several date
formats and a non-date string and assert year-only / fail-closed; feed ages under/over 89; build a
record with direct identifiers + a date + free text + a verdict/confidence and assert the
identifiers are gone/generalized/redacted while the decision fields pass through unchanged;
inspect the policy id string and the class table.

**Known failure modes.** A record scrub that also touched `verdict`/`confidence`/`gate` would
violate the egress-transform-only boundary (ADR-0001) — pinned by
`test_redact_record_never_touches_verdict_or_gate`. Free-text redaction is **mechanical** (regex,
not NLP) and will miss a name embedded in prose — documented in the module docstring and
`HIPAA_SAFE_HARBOR_CLASSES`, not silently assumed complete. **Now exercised end-to-end
(2026-07-11)**: the module is wired into a real egress endpoint,
`POST /api/runs/{run_id}/share` — see **EVAL-051** below for the endpoint-level case. `GET
/api/export` still uses the separate, less-strict `api/deid.py` pseudonymization policy
(unchanged) — the two egress paths intentionally run different policies (see
[scope-and-wishlist.md](../requirements/scope-and-wishlist.md) #14).

### EVAL-051 — De-identified share egress: approver-gated, scrubbed, and audited in the trail

| Field | Value |
|---|---|
| **Target** | `POST /api/runs/{run_id}/share` (`api/main.py`) + `api/share_store.py` — the endpoint that wires `api/safe_harbor.py` into a real egress (ADR-0018 D3), recorded through the pluggable jsonl/sqlite/postgres sink (ADR-0016) |
| **Type** | Faithfulness |
| **Automated?** | Yes — `test_share_egress.py` (`test_share_requires_approver`, `test_share_unknown_run_is_404`, `test_share_scrubs_direct_identifiers_and_labels_the_scrub`, `test_share_records_a_data_exported_event_in_the_trail`, `test_share_does_not_perturb_the_gate_decision`); the sink's own storage-backend parity is separately covered by `test_share_store.py` (jsonl default, sqlite round-trip, sqlite==jsonl parity, degrade-to-jsonl without a DSN, idempotent re-append, tolerant corrupt-line read) and a live-Postgres round-trip in `test_persistence_postgres_live.py` |

**Definition of good.** The endpoint is **approver-only** (a viewer/reviewer is 403'd) — data does
not leave on a low privilege. Every emitted row has the direct identifiers (`submitted_by`,
`subject_id`) dropped, and the returned `ShareManifest` labels the scrub as a **version**
(`policy_id="safe-harbor-style-v1"`), never a compliance claim (the disclaimer text contains
"NOT"/"compliance"). The egress is recorded as a `DATA_EXPORTED` `ProvenanceEvent` that surfaces
in the run's own trail (`GET /api/runs/{id}`), **pinned to the exact emitted bytes** by a sha256
content hash so the trail entry can never drift from what actually left, and the actor who shared
is recorded (`human:<id>`). A share is an **egress transform only**: the run's decision cards are
byte-identical before and after (ADR-0001 — a share never reads back into, or perturbs, the gate).

**Method.** Drive a `TestClient` against the committed `RUN-2026-07-11-CLINVAR-RTH` fixture (it
carries intake identity via `sample_metadata.csv`, so the scrub is demonstrably removing
something, not passing an already-clean row through) with the share store redirected to a tmp
path; assert 403 for viewer/reviewer, 404 for an unknown run, dropped identifiers + a labelled
policy id + all 18 §164.514(b)(2) classes documented, the recorded event's content hash matching
the manifest, and the cards unchanged by a `GET` before/after the share.

**Known failure modes.** An endpoint reachable without `require_role("approver")` would let a
low-privilege actor egress data — pinned by `test_share_requires_approver`. A scrub applied
in-place to the cached `_evaluate()` result (rather than to a fresh copy of the rows) would risk
mutating the gate's own state — pinned by `test_share_does_not_perturb_the_gate_decision`. **Scope
note, not a failure mode**: this endpoint is one fixed action (always `grain="decision"`, always
the Safe-Harbor-style policy) — it does not yet cover the broader Share window (scope / location /
security-level selection) [design/variant-interpretation.md §4](../design/variant-interpretation.md#4-reporting--sharing-p2)
describes.

### EVAL-052 — Scoped, de-identified node-observation read: an agent sees one node's outputs, and a log grant is scrubbed

| Field | Value |
|---|---|
| **Target** | `GET /api/runs/{run_id}/nodes/{node_id}/observations` (`api/routers/node_observations.py`) + `api/deid.py` `scrub_text()` — the Phase-4 read of a Wave-2 `AgentBinding`'s grant (REQ-F-101, REQ-NF-028) |
| **Type** | Faithfulness (egress transform, off the decision gate) |
| **Automated?** | Yes — `test_node_observations.py` (13, was 8; re-verified 2026-07-13 via `uv run pytest --collect-only tests/test_node_observations.py`): the original 8 (`test_outputs_scoped_to_node_by_germline_id`, `test_outputs_scoped_by_tool_key`, `test_logs_opt_in_and_deidentified`, `test_node_with_no_outputs_is_honest_empty`, `test_unresolved_node_is_honest_empty`, `test_unknown_grant_is_422`, `test_viewer_allowed_invalid_principal_rejected`, `test_traversal_run_id_rejected`) + WS-08 interim's `test_logs_grant_denied_to_viewer`/`test_logs_grant_allowed_to_reviewer` (2026-07-12) + T-148's scope-by-wiring-over-a-populated-publish-dir trio (2026-07-13, PR #10): `test_wired_agent_reads_scoped_outputs`, `test_unwired_agent_is_403`, `test_wired_agent_grants_capped_to_binding` — these three prove ADR-0024 enforcement (a `bound_run` fixture records a real `AgentBinding` via `agent_binding_store`), not just this section's static grant-scoping, but they live in the same file/endpoint and are counted here for that reason |

**Definition of good.** An attached advisory agent reads a **narrowing** of what agents already
observe, never a widening, and any free text is de-identified before it leaves the machine.
Concretely: (a) `grants=outputs` returns only the bound node's PUBLISHED files, scoped by the
tool's catalogued output-port globs — a sibling process's artifact (`HG002.dedup.bam` for a fastp
node) is NOT in scope. (b) `grants=logs` (opt-in) returns a scrubbed tail: a planted subject id
(`SUBJ-00042-JohnDoe`), email (`jane.patient@hospital.org`), and MRN-shaped number (`7654321`) are
all absent from the returned lines, while non-sensitive content (a coverage line) survives — the
scrub is targeted, not a blackout (REQ-NF-028). (c) Honest-empty: a run/node that produced nothing
on disk, or a node id that doesn't resolve to the seeded graph, returns an empty view with a
`note`, never fabricated outputs. (d) Read-only + least-privilege: `viewer`+ is allowed but an
invalid principal is rejected, an unknown grant is 422, a traversal `run_id` is rejected, and the
read never touches a verdict/finding/confidence (ADR-0001/0012).

**Method.** Build a per-run scratch tree (a published `results/` dir + a Nextflow `work/` task dir
with a planted-PII `.command.log`, plus a `sample_metadata.csv` giving the subject id to
pseudonymize), drive a `TestClient`, and assert node-scoping, the three planted PII literals
absent from the log tail, honest-empty on a missing/unresolved node, and each auth/validation/
traversal rejection.

**Known failure modes.** `scrub_text` is a demo heuristic, explicitly NOT HIPAA de-identification
or a validated NLP PHI scrubber — a novel PII shape it does not model (or a subject id not present
in `sample_metadata.csv`) could survive; the 6-digit floor is a deliberate readability tradeoff
that leaves 5-digit sensitive numbers alone. The agent *consuming* this scoped view is a deferred
seam (`gather_node_observations()`), so the endpoint is exercised, but no test asserts an agent
actually restricts itself to it in a narration.

## Real-data evaluation (Phase 2 — planned)

### EVAL-030 — Verdicts vs. GIAB HG002 truth

| Field | Value |
|---|---|
| **Target** | Gate + (later) variant-gate against a known-answer sample |
| **Type** | Real-data |
| **Automated?** | **Planned** — depends on the GIAB HG002 subset fetch (tasks T-013 GIAB half / T-017) |

**Definition of good.** On a real, well-characterized sample with a gold-standard truth
VCF + high-confidence BED, the gate's breadth/callability and identity checks behave
correctly, and any variant-level claim is checkable against truth.

**Method.** *(Planned)* Fetch a panel-region HG002 subset (accession + script, no raw
reads committed), run the gate, compare against truth in high-confidence regions.

**Known failure modes.** Truth is only trustworthy inside the high-confidence BED;
outside it, absence of a call is not evidence. Requires the genomics toolchain
(bioconda/containers), kept separate from the app's `uv` toolchain.

## Process cases (manual/agent review, not an automated test)

### EVAL-060 — Release-hardening audit: adversarial re-verification discipline

| Field | Value |
|---|---|
| **Target** | The whole shipped app (`src/bayleaf/`, `api/`, `frontend/`) as of commit `9878231`, judged against the demo/recording golden path |
| **Type** | Process (manual/multi-agent review) |
| **Automated?** | **No** — a Fable-5 multi-agent audit run, all read-only (no source changed by the audit itself); its findings are then verified/fixed by the automated test suite (T-126) |

**Definition of good.** Not "zero bugs" — a demo-stage codebase with 465 automated tests still
has real drift between what a screen claims and what it does. Good here means: (1) every
Blocker/High-severity finding is **adversarially re-verified** by a second pass before being
acted on — reproduced against the live app or the exact cited `file:line`, not accepted on a
single specialist's say-so; (2) findings are **deduplicated and prioritized honestly** (a demo-
blocking lie ranks above a cosmetic label, a `post-hackathon` item is named as such rather than
inflated); (3) the fix scope is **disciplined to relabeling/rewording/wiring the minimum**, not a
license to add new scope under audit cover; (4) every fix **preserves the guardrails**
(ADR-0001 — no advisory agent sets/edits a verdict; stub-default $0; no clinical/pathogenicity
language; ClinVar quoted verbatim).

**Method.** Two tracks, ten read-only specialist agents (ui-ux, data-lineage, journeys,
integration, reliability, agent-safety, science-repro, demo-readiness, contract, truthfulness) +
a wishlist-feasibility track (`w1`–`w4`, 3-approach design panels), synthesized in
`audit/SYNTHESIS.md`: 60 raw findings deduped to 26 items; **every item marked `[CONFIRMED]`**
(independently re-verified) **or `[UNVERIFIED]`** (rests on the specialist's own stated
confidence, never silently upgraded) — **0 REFUTED, 0 UNCERTAIN**. Findings sorted P0 (must-fix
before recording, 1 item) → P1 (fix before submission if possible, 6) → P2 (hide/document, 12) →
P3 (post-hackathon backlog, 14), each with an effort/risk estimate and the raising specialist(s)
named. A pre-recording go/no-go checklist closes the plan. T-126 then fixed the P0 + all 6 P1s in
one hardening commit, verified by the offline test suite (442 passed / 5 skipped at that point)
plus live manual verification of the P0 (stopped the API, reloaded `/`, confirmed the hero dot
went non-green).

**Known failure modes.** An audit that rubber-stamps its own specialists' findings without
re-verification would let a false positive burn a fix cycle, or a false negative ship a real
demo-breaking lie — mitigated by the adversarial re-verification pass and the explicit
CONFIRMED/UNVERIFIED/REFUTED taxonomy (never a silent "trust the agent"). An audit with no
prioritization discipline would either over-fix (scope creep under audit cover, explicitly
guarded against — see `SYNTHESIS.md`'s "Discipline" note) or under-fix (a real P0 buried in a
list of 84). The P2/P3 items are deliberately **not** fixed in this session — named as open,
tracked in `audit/SYNTHESIS.md`, not silently dropped.

**Update (2026-07-11, T-131/T-132).** The 14-item P3 (`post-hackathon`) backlog is now closed:
P3-14 (the approval-gate finding) was already closed earlier the same day by T-126's W1; this
session closes the remaining 13 (P3-1 through P3-13) across two waves — see the P3-backlog bullets
in [architecture.md](../design/architecture.md) and EVAL-008 above. Three of the thirteen (P3-1,
P3-9, P3-10) are **labeling-only** — no threshold, gate, or verdict logic changed, confirmed by
`runbook.py`'s `required=True` on `cluster_pf` staying literally unchanged and `git diff --stat`
on the metric-registry/runbook files showing comment-only insertions; the other ten are real code
changes (a durable job store, preflight guards, an atomic dup-id lock, a shared process-group
timeout, a11y attributes, a Pager/Tabs migration, and server-side monitoring pagination).

## What we do *not* claim

1. **No calibrated probabilities.** Confidence is a heuristic; we do not evaluate it as
   a probability and do not report ROC/Brier-style calibration.
2. **No clinical accuracy claim.** Verdicts are checked against *intended* operational
   outcomes on contrived/synthetic data, not clinical ground truth. bayleaf is a
   research/demo tool ([constraints.md](../requirements/constraints.md) REQ-C-030).
3. **No performance SLA.** No throughput/latency benchmark is measured at this stage
   (see [risks.md](risks.md), [nonfunctional.md](../requirements/nonfunctional.md)
   REQ-NF-032).
4. **The execution boundary (`POST /api/runs`, T-057, 2026-07-09) now has automated
   registration/parsing coverage, but never a live-driver run in the offline suite — CLOSED for
   the registration path, still open for a genuinely live intake run.** It was first verified
   only **manually** ("Submit → Processing… → gated HOLD," commit `e77c2e6`); `test_e2e_pipeline.py`
   (2026-07-11, EVAL-007) now asserts the registration/parsing contract automatically
   (`test_sheet_creation_registers_run_and_skips_unfixtured_samples`,
   `test_intake_parse_contract_rejects_pii_and_a_no_op_sheet`) — but with `intake._run_pipeline`
   monkeypatched to a no-op, so **no test in the offline suite ever actually runs the live
   subprocess/Nextflow driver end to end**; that remains verified only manually (T-063's
   real-GIAB run) plus the env-gated live-stub checks (EVAL-006/EVAL-007). Tracked as a narrower
   open gap than before, not silently assumed fully covered ([risks.md](risks.md) RISK-034).
5. **A genuinely LIVE multi-sample Nextflow run is unverified (2026-07-11, W4 continuation,
   EVAL-009).** The driver's post-run PARSE (publish dir → N run-dir rows) is proven against
   fixture publish dirs, offline — but no test, and no manual run, has driven a real
   multi-sample-samplesheet Nextflow invocation and confirmed the parse holds against Nextflow's
   REAL published output. The live driver still submits a single-row (HG002-only) samplesheet,
   because no second real sample's panel reads exist on disk in this sandbox. This is named as an
   open gap, not silently assumed covered by EVAL-009's offline fixture proof — see
   [design/nextflow-codegen.md §Multi-sample driver
   parse](../design/nextflow-codegen.md#multi-sample-driver-parse-2026-07-11-w4-continuation).

---

*Marker legend:* **Fact** (a named, passing test) · **Assumption** · **Decision** ·
**TODO** (Phase-2 / planned). Test ids are current as of the last-updated date; run
`pytest` for the live count.
