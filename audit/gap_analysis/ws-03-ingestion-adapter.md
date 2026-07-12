> **Workstream WS-03 fix plan** — from the [gap-analysis fan-out](README.md); grounded in source against [the 2026-07-11 design review](design-review-2026-07-11.md). Read-only design (advisory). 2026-07-11 (MST).

# WS-03 — Real Ingestion Adapter (nf-core/MultiQC `results/` → `RunArtifacts`)

## Problem
The only writer of the gate's input contract is our own driver: `parse_qc_metrics` reads a bespoke fixed-column `qc_metrics.csv` (`parsers.py:210-237`) that only `scripts/run_giab_pipeline.py::write_run_dir_multi` (`:518-589`) emits. No fastp/mosdepth/MultiQC parser exists in the core; the registry's anti-drift `aliases[]` are dead because `resolve_alias` (`registry.py:204`) is never called on any live path (grep confirms: docstrings only) — ingestion maps *named `QCMetrics` fields*, not raw tool keys (`mapping.py:23-40`, consumed at `rules.py:456`). Ingress hardcodes `_FIXTURE_SAMPLES={"HG002"}` (`intake.py:61,289`) and run discovery is import-time hardcoded to `data/` (`main.py:65`, `intake.py:56`, `pipeline_run.py:55`, `pipelines_lifecycle.py:58`, `files.py:43`), while `card_readout.py:432` already honors `PIPEGUARD_DATA_ROOT` — so the roots are inconsistent and a real NovaSeq/nf-core `results/` has no door in.

## Design
A boundary-only ingestion adapter (sibling of `artifacts/`, upstream of the deterministic gate, no verdict logic — ADR-0001) that reads the artifacts the germline pipeline **already publishes** (`nextflow/catalog.py` emits `${id}.fastp.json`, `${id}.mosdepth.summary.txt`, `multiqc_data/multiqc_data.json`) and produces a `RunArtifacts`. Three moves:

1. **Per-source extractors** each yield a uniform `ObservedMetric(our_key, raw_value, raw_unit, source_file, source_field, locator)`. For structured files (`fastp.json`, `*.mosdepth.summary.txt`, samtools flagstat) the extractor knows the native field → emits the tool-native leaf key at its **true scale** (fastp `q30_rate` is a fraction 0-1, *not* pre-scaled ×100 as the driver does at `run_giab_pipeline.py:510`). For `multiqc_general_stats`/`multiqc_data.json`, strip the MultiQC module namespace to the leaf key.
2. **Every leaf key is run through `registry.resolve_alias(leaf)` → `our_key`** — this is the first real call site of `resolve_alias`, so a MultiQC rename (`q30_rate`→`percent_q30`, `20_x_pc`, `pct_duplication`…) now folds to a stable `our_key` instead of silently vanishing. An **unrecognized** key (`UnknownMetricError`) is collected into a diagnostics list and skipped — never invented, never crash (tolerant boundary; the missing-metric signal is WS-01's to escalate).
3. **Project observed → `RunArtifacts`.** For WS-03-minimal, project the resolved `our_key`→value dict back onto the flat `QCMetrics` fields via the inverse of `_QCMETRICS_MAP`. This keeps the `RunArtifacts`/`QCMetrics` contract, `rules.py:456`, and all 465 tests unchanged, yet wires aliases to live keys immediately. Raw unit is declared per-source and normalized by the registry (`registry.normalize`), fixing the latent fastp ×100 unit smell in one place.

`load_run` auto-detects: if nf-core markers are present (`multiqc_data/` or a `*.fastp.json`), use the adapter; else fall back to the bespoke `qc_metrics.csv` (pinned demo byte-identical). A real ingress accepts an existing `results/` dir (no toolchain run), materializes a discoverable run dir under a **single configurable run-store root**.

## Exact changes
- **NEW `src/pipeguard/ingest/nfcore.py`**
  - `ObservedMetric` (frozen dataclass/NamedTuple) — the WS-06 seam.
  - `extract_fastp(path) -> list[ObservedMetric]` (q30_rate=fraction, pct passed-filter=fraction, duplication.rate=fraction; from `fastp.json` structure per `run_giab_pipeline.py:508-515`).
  - `extract_mosdepth(summary, thresholds) -> list[ObservedMetric]` (mean coverage=x, breadth_20x/30x=fraction; logic ported from `run_giab_pipeline.py:478-495`).
  - `extract_multiqc_general_stats(path, registry) -> list[ObservedMetric]` — namespace-strip then `resolve_alias`.
  - `extract_samtools_flagstat(path)` — `qc.pct_mapped` (fills a WS-01/09 gap).
  - `reconcile(raw_leaf_keys, registry) -> (dict[our_key, ObservedMetric], list[str] unknowns)` — the single `resolve_alias` call site.
  - `ingest_results_dir(results: Path, run_id, registry=default_registry()) -> RunArtifacts` — discover per-sample `${id}.fastp.json` (reuse the `${id}.` dot-anchor discipline from `run_giab_pipeline.py:424-451`), build one `QCMetrics` per sample, assemble `RunArtifacts` (samples/sample_sheet from `SampleSheet.csv` if present, else synthesized from discovered ids).
- **NEW `src/pipeguard/metrics/mapping.py::qcmetrics_from_observed(observed: dict[str,ObservedMetric], sample_id) -> QCMetrics`** — inverse projection of `_QCMETRICS_MAP` (`mapping.py:23-40`). Keeps the field-table single-sourced.
- **`src/pipeguard/parsers.py::load_run` (`:333-374`)** — add nf-core detection before the `qc_metrics.csv` branch (`:355`): if `(_maybe("multiqc_data").exists() or any *.fastp.json)`, `qc = ingest_results_dir(...).qc`; else keep `parse_qc_metrics`. No signature change.
- **API run-store root (WS-03d):** add `api/runs_root.py::runs_root()` (reads `PIPEGUARD_DATA_ROOT`, else repo `data/`) — one resolver. Replace the module-constant hardcodes: `main.py:65`, `main.py:_run_dir/_run_ids (:204-216)`, `intake.py:56`, `pipeline_run.py:55`, `pipelines_lifecycle.py:58`, `files.py:43`, aligning `card_readout.py:432` onto it. Resolve per-call (not import-time) so tests/deploys can repoint.
- **Real ingress (WS-03b):** `api/routers/intake.py` — new `POST /api/runs/ingest {results_dir}` (reviewer/approver) that runs `ingest_results_dir`, writes a discoverable run dir under `runs_root()`, returns the same `SubmitRunAck`. Replace the `_FIXTURE_SAMPLES` allowlist (`:61,289-295`) with a real check: a sample is processable if it has reads/results on disk, not because it equals `"HG002"`.

## Data-contract / model changes
- **No change to `RunArtifacts`/`QCMetrics`/`MetricValue`/`Finding` for WS-03-minimal** — the adapter projects onto today's flat `QCMetrics`, so the deterministic core and content hashes are untouched.
- **New internal type only:** `ObservedMetric(our_key, raw_value, raw_unit, source_file, source_field, locator)`. This is deliberately the shape WS-06 will promote to a first-class `RunArtifacts.observed_metrics: dict[str, ObservedMetric]` (registry-keyed) so the 7 `# NOT COMPUTED` metrics and two-sided gates land without named fields. WS-03 designs to it now; WS-06 widens the contract later.
- `ingest_results_dir` returns unknown-key diagnostics (list[str]) for WS-01 to consume as a fail-closed "unrecognized/expected-absent metric" signal — not stored on the frozen models yet.

## Cross-cutting impact & ordering
Shared-core files touched: **`parsers.py`** (`load_run` detection), **`metrics/mapping.py`** (inverse projector; keep `_QCMETRICS_MAP` the single field table). **Not touched:** `rules.py` (`:436-478`), `models.py`, `runbook.py`, `synthesis/`, `engine.py` — the verdict stays a deterministic function of findings.
- **WS-03 lands BEFORE WS-06.** WS-06's registry-driven ingestion is the promotion of `ObservedMetric` to a `RunArtifacts` field + a `dict[our_key,value]` gate loop replacing `rules.py:456`'s named-field path; it should build on this adapter, not re-parse. Design the adapter's `reconcile`/`ObservedMetric` output as WS-06's input.
- **WS-03 unblocks WS-01/WS-09 metrics.** Breadth, `pct_mapped`, duplication now arrive from real mosdepth/samtools/fastp, giving WS-01's "expected-metric present → else HOLD" real data and fixing the §9a dup-rate scale at the true source unit. WS-01's expected-metric-set logic should land **after** the adapter so it gates against real presence.
- **WS-02 (FREEMIX/identity) plugs into the extractor interface.** Add a `verifybamid2 selfSM` / NGSCheckMate extractor as one more `extract_*` yielding `ObservedMetric` — no core-dispatch change. WS-02's rule authoring depends on WS-03's extractor seam existing.
- **WS-04 (GIAB concordance)** consumes the same `results/` dir the adapter reads (VCF alongside), so the run-store-root work here is shared.

## Tests
- Adapter units on a **committed synthetic nf-core `results/` fixture** (small real-shaped `fastp.json`, `*.mosdepth.summary.txt`, `multiqc_data/multiqc_data.json`): assert the produced `QCMetrics` equals the pinned bespoke-CSV values for HG002 (equivalence proof).
- **Alias-drift test:** feed a MultiQC general-stats file with a *renamed* key (`percent_q30`, `20_x_pc`) and assert it still resolves to `qc.q30`/`qc.breadth_20x` — the anti-drift claim, now real.
- **Unit-scale test:** fastp `q30_rate=0.95` (fraction) normalizes to the same canonical value the driver's ×100 path produces — no silent 100× (registry `normalize`).
- **Unknown-key test:** an unregistered column is skipped + reported in diagnostics, never fabricated, no crash.
- `load_run` detection test: nf-core dir → adapter; legacy `qc_metrics.csv` dir → bespoke parser (both green).
- API: `POST /api/runs/ingest` from a results dir produces a discoverable run + gate cards; `runs_root()` honors `PIPEGUARD_DATA_ROOT`.
- Regression: full existing suite green (mock_run_01 + pinned GIAB unchanged).

## Back-compat / migration
- `load_run` falls back to `parse_qc_metrics` when no nf-core markers exist → `data/mock_run_01`, the pinned GIAB run dir, and every fixture stay byte-identical; `parse_qc_metrics` is retained, not deleted.
- `_FIXTURE_SAMPLES` removal is behavior-widening (more samples processable), not breaking; keep the honest "skipped (no reads/results on disk)" path for samples that genuinely lack inputs.
- Run-store root defaults to repo `data/` when `PIPEGUARD_DATA_ROOT` unset → no deploy change required.
- The driver's `write_run_dir_multi` flatten step becomes redundant once the adapter reads `results/` directly; leave it in place initially (dual-write) and retire it in a later PR to avoid coupling.

## Sequencing (PR-sized)
1. **Adapter core (no wiring):** `ingest/nfcore.py` + `ObservedMetric` + extractors + `reconcile` (the `resolve_alias` call site) + `qcmetrics_from_observed`, with the synthetic `results/` fixture and equivalence/alias/unit/unknown tests. Pure, offline, nothing else changes.
2. **`load_run` detection:** auto-route nf-core dirs to the adapter with legacy fallback; regression suite green.
3. **Configurable run-store root:** `api/runs_root.py` + replace the five hardcoded `data/` constants; align `card_readout.py`.
4. **Real ingress:** `POST /api/runs/ingest` + drop the `_FIXTURE_SAMPLES` allowlist for an on-disk check; e2e test from a results dir to gate cards.
5. **(Handoff) Retire driver flatten / open WS-06 seam:** document `ObservedMetric` → `RunArtifacts.observed_metrics` promotion; optionally stop dual-writing the bespoke CSV.

## Risks / tradeoffs / honest limits
- **MultiQC key extraction is best-effort:** MultiQC namespaces general-stats headers (`<module>_mqc-generalstats-<module>-<key>`); the namespace-strip heuristic can mis-key an unseen module. Mitigation: prefer structured `fastp.json`/`mosdepth.summary.txt` (deterministic) and treat general-stats as the alias-fed secondary; report unknowns loudly.
- **WS-03-minimal still can't gate the 7 `# NOT COMPUTED` metrics** (FREEMIX, NGSCheckMate, sex-concordance, fold_80, titv two-sided, etc.) because they have no `QCMetrics` field — that is explicitly WS-06's contract widening + WS-02's rules. WS-03 makes fold_80/titv *observable* (ingested) but they stay ungated until WS-06 adds the target-band gate type — label honestly, don't imply they gate.
- **Fail-closed caveat:** the adapter must never turn a *missing* real metric into a passing default (it emits `None`/omits) — but making "expected metric absent → HOLD" is WS-01's job; until it lands, a lean real run can still under-gate. Flag this dependency rather than paper over it.
- Two roots exist (`PIPEGUARD_ARTIFACT_LOCAL_ROOT` for the core staging store vs `PIPEGUARD_DATA_ROOT` for API discovery); consolidate discovery under `PIPEGUARD_DATA_ROOT` and document the relationship to avoid a third divergent knob.

### Critical Files for Implementation
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/parsers.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/metrics/mapping.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/metrics/registry.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/api/routers/intake.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/scripts/run_giab_pipeline.py (reference extractor logic to port into `src/pipeguard/ingest/nfcore.py`)

---

## Test-First Contract (per surfaced gap)

Four gaps carried by this plan, each with a red test that can go green **only when the real
wiring exists**, a standing anti-scaffold guard, a real-GIAB criterion where the gap is
adoption/ingestion (a synthetic fixture can pass while a real run fails — that is exactly how the
scaffolding hid), and a binary Definition of Done. Every test below **preserves the ADR-0001
invariants**: the adapter/ingress is boundary-only and emits **no** verdict; the verdict stays a
deterministic function of `Finding`s computed by `rules.py` over the produced `QCMetrics`; and
each test pushes toward **failing closed** (a missing/unknown metric is never coerced to a passing
default). New adapter units land in **`tests/test_ingest_nfcore.py`** (a sibling of
`tests/test_run_giab_multisample.py`, reusing its `_fastp_json`/`_mosdepth_summary`/
`_write_sample_outputs` fixture builders); ingress/root tests extend
**`tests/test_intake_scheduling.py`** and its `env` TestClient fixture.

### Gap A — nf-core/MultiQC `results/` → `RunArtifacts` adapter

- **Red acceptance test** — `tests/test_ingest_nfcore.py::test_adapter_qcmetrics_equal_bespoke_csv_for_one_sample`.
  Build a synthetic nf-core `results/` publish dir for one sample with the shared builders (real-shaped
  `${id}.fastp.json` via `_fastp_json(q30_rate=0.90, passed=990_000, dup_rate=0.05)`,
  `${id}.panel.mosdepth.summary.txt` via `_mosdepth_summary(50.0)`, thresholds, `multiqc_data/`).
  Run **both** paths over the *same* publish dir: (1) `write_run_dir_multi` →
  `parse_qc_metrics` (`parsers.py:210`) → `metric_values_for` (`mapping.py:43`), and (2) the new
  `ingest_results_dir(results, run_id).qc` → `metric_values_for`. Assert the two
  `dict[our_key → normalized_value]` are **equal** — `qc.q30≈0.90`, `qc.mean_target_coverage≈50.0`,
  `qc.duplication≈0.05`, `qc.breadth_20x≈0.90`, `qc.breadth_30x≈0.80` — and that feeding either
  `QCMetrics` into `run_gate`/`aggregate_verdict` yields the **same card verdict** (deterministic
  function of findings; the adapter itself returns no verdict). This exercises the full
  `structured tool file → ObservedMetric → resolve_alias → registry.normalize → QCMetrics → rule →
  verdict` path. **A stub/scaffold cannot pass it:** the assertion is byte-level equivalence of
  canonical values against the *independently derived* bespoke-CSV path (which already reads real
  fastp/mosdepth via `scripts/run_giab_pipeline.py::parse_fastp`/`parse_mosdepth`), so a
  hand-returned constant would have to reproduce every normalized value AND stay coupled to the
  driver's extraction — i.e. actually parse the files. A second case,
  `test_adapter_emits_native_source_units_not_prescaled` (unit-scale, §9a), feeds fastp
  `duplication.rate = 0.0057` (a **fraction**, the value the committed real HG002 fixture stores)
  and asserts the adapter declares `raw_unit="fraction"` so `registry.normalize` yields `0.0057`,
  **not** the driver's ×100-then-÷100 percent round-trip and **not** the `0.000057` the fixed-unit
  `mapping.py` bug produces — proving the adapter reads the true source scale.
- **Anti-scaffold guard** — `test_adapter_never_fabricates_or_defaults_an_absent_metric`: on a
  publish dir missing the mosdepth summary, assert `qc.mean_target_coverage`/breadth are **absent**
  from the produced `QCMetrics` (field `None`, mirroring `test_missing_field_is_skipped_not_defaulted`
  in `tests/test_metrics_mapping.py`) — never `0.0`, never a fabricated pass — and that the omission
  is reported in the adapter's unknown/absent diagnostics list. This freezes the fail-closed
  boundary so a future "fill in a default" regression can't turn missing real data into green.
- **Real-data acceptance (required — this is an ingestion gap):** a skip-safe, env-gated
  `test_adapter_matches_driver_on_real_giab_results` (same `pytest.mark`/`skipif` idiom as
  `tests/test_nextflow_compile.py`'s live `-stub-run` check and `tests/test_persistence_postgres_live.py`).
  Point `ingest_results_dir` at the **real** Nextflow `results/` published from
  `pipelines/germline/main.nf` on GIAB HG002 (gitignored `data/real-giab/`), and assert its
  `QCMetrics` matches the driver's `write_run_dir_multi` output for that same dir — the CLAUDE.md
  verified-live numbers (Q30 ≈ 0.882, coverage ≈ 54.2×, 553 variants) — and that the resulting gate
  card is **HOLD** (`cluster_pf` NA, the honest reads-can't-produce-a-SAV-metric outcome). Fixture
  green ≠ real run works: the synthetic-fixture equivalence test above **cannot** substitute for
  this, because a hand-shaped `multiqc_data.json` can hide the real module nesting the namespace-strip
  must survive.
- **Definition of Done:** `test_adapter_qcmetrics_equal_bespoke_csv_for_one_sample`,
  `test_adapter_emits_native_source_units_not_prescaled`, and
  `test_adapter_never_fabricates_or_defaults_an_absent_metric` all green offline **and** the
  env-gated `test_adapter_matches_driver_on_real_giab_results` green in the `hackathon` env.

### Gap B — registry aliases resolve **LIVE** keys (`resolve_alias` gets its first real call site)

- **Red acceptance test** — `tests/test_ingest_nfcore.py::test_renamed_multiqc_key_still_resolves_on_the_live_path`.
  Feed the adapter a `multiqc_data/` general-stats file whose headers use **renamed** keys —
  `percent_q30` instead of `q30_rate`, `20_x_pc` instead of a canonical breadth key,
  `pct_duplication` instead of the leaf dup key — and assert the produced `QCMetrics` still carries
  `qc.q30`, `qc.breadth_20x` (percent-scaled `99.2 → 0.992`), and `qc.duplication`. This is the
  **first** exercise of `MetricRegistry.resolve_alias` (`registry.py:204`) on a live ingestion path:
  today it is called **only** in `tests/test_metrics.py::test_alias_resolution` (verified: `grep -rn
  resolve_alias src/ api/ scripts/` returns nothing but `registry.py`'s own definition), so the
  registry's whole anti-drift `aliases[]` layer is dead weight the review flags in §3c. **A stub
  cannot pass it:** the input columns literally do not contain `qc.q30` — only the reconcile step
  routing every leaf key through `resolve_alias` can recover the stable `our_key`; a scaffold that
  key-matches on canonical names drops the renamed columns and the assertion fails.
- **Anti-scaffold guard** — `test_no_leaf_key_reaches_qcmetrics_without_alias_resolution`: assert
  that a leaf key **outside** the registry vocabulary (e.g. `totally_unknown_metric`) is **skipped
  and reported** (never raised past the boundary, never invented as a `QCMetrics` field), and — the
  standing freeze — that on the demo/real publish dir **every** extracted leaf key that lands in
  `QCMetrics` came through `resolve_alias` (no field is populated by a raw-name shortcut that
  bypasses the shield). This locks in that a future MultiQC rename cannot silently vanish, which is
  the exact §3c failure.
- **Real-data acceptance:** a **synthetic fixture genuinely suffices for the alias-drift assertion
  itself** (a rename is a header string; the resolution is pure registry logic already unit-proven
  in `test_multiqc_pct_trap`). The one real-data tie-in is folded into Gap A's
  `test_adapter_matches_driver_on_real_giab_results` — the namespace-strip that *feeds* `resolve_alias`
  must be validated once against a real `multiqc_data.json` layout; no separate real-data test is
  owed here.
- **Definition of Done:** `test_renamed_multiqc_key_still_resolves_on_the_live_path` and
  `test_no_leaf_key_reaches_qcmetrics_without_alias_resolution` green, and a repo-wide check that
  `resolve_alias` now has ≥1 non-test call site under `src/pipeguard/ingest/`.

### Gap C — real, non-fixture ingress (`POST /api/runs/ingest`, drop the `HG002` allowlist)

- **Red acceptance test** — `tests/test_intake_scheduling.py::test_ingest_endpoint_gates_a_non_fixture_results_dir`.
  Using the `env` TestClient (reviewer/approver headers per `api/auth.py`), write a synthetic
  `results/` dir for a sample that is **not** `HG002` (e.g. `NA12878`), `POST /api/runs/ingest`
  with `{results_dir}`, then assert: (1) the ack reports `NA12878` as **processed**, not skipped;
  (2) the run is discoverable via `GET /api/runs`/`GET /api/runs/{id}` and (3) yields a gate card
  for `NA12878` with a deterministic verdict from `run_gate`. This drives
  `results dir → ingest_results_dir → discoverable run dir → run_gate → card` over the real API
  surface (background Nextflow/subprocess monkeypatched to no-ops, as in `test_e2e_pipeline.py`).
  **A stub cannot pass it:** the endpoint must actually materialize a gate-able run dir from
  scattered tool outputs; today `submit_run` (`intake.py:289`) filters `processed = [s for s in
  submitted if s in _FIXTURE_SAMPLES]` with `_FIXTURE_SAMPLES = {"HG002"}` (`intake.py:61`), so a
  non-HG002 sample is unconditionally `"skipped"` — the assertion `processed == ["NA12878"]` fails
  until the allowlist is replaced by an on-disk `has_results(sample)` check.
- **Anti-scaffold guard** — `test_processability_is_on_disk_presence_not_a_sample_name_allowlist`:
  assert (1) a sample **with** results on disk is processable regardless of name, and (2) a sample
  **without** any reads/results is honestly `"skipped (no reads/results on disk)"` — and add a
  source-level assertion that no literal `{"HG002"}` / `_FIXTURE_SAMPLES` name-allowlist gates
  processing in `intake.py`. This freezes §3b so the door can't quietly re-close to one hardcoded
  sample.
- **Real-data acceptance (required — this is the adoption gap):** env-gated
  `test_ingest_real_giab_results_end_to_end` — hand the endpoint the real HG002 `results/` dir and
  assert a discoverable run whose HG002 card is **HOLD**, byte-consistent with the intake-driver
  path's own HG002 result. This is the literal "let a real run in" proof from review §3; the
  synthetic `NA12878` fixture demonstrates the allowlist is gone but cannot prove a genuine NovaSeq/
  nf-core `results/` actually flows through.
- **Definition of Done:** `test_ingest_endpoint_gates_a_non_fixture_results_dir` and
  `test_processability_is_on_disk_presence_not_a_sample_name_allowlist` green offline **and**
  `test_ingest_real_giab_results_end_to_end` green in the `hackathon` env.

### Gap D — configurable run-store root (`runs_root()` honors `PIPEGUARD_DATA_ROOT`)

- **Red acceptance test** — `tests/test_intake_scheduling.py::test_run_discovery_honors_pipeguard_data_root`.
  `monkeypatch.setenv("PIPEGUARD_DATA_ROOT", str(tmp_path))`, write a minimal gate-able run dir
  under `tmp_path/<run_id>/`, and assert the API discovers **and gates** it (`GET /api/runs` lists
  it; `GET /api/runs/{id}` returns its cards) while the repo's committed `data/` runs are **not**
  present — proving discovery repointed. **A stub cannot pass it:** run discovery is import-time
  hardcoded to the repo `data/` at `main.py:65`, `intake.py:56`, `pipeline_run.py:55`,
  `pipelines_lifecycle.py:58`, `files.py:43`; only replacing those constants with a per-call
  `runs_root()` resolver (aligned onto the pattern `card_readout.py:426`'s `_data_root()` already
  uses) lets an env override change what the running process sees. A resolver read once at import
  can't be repointed by a test's `setenv`, so the test fails until resolution is per-call.
- **Anti-scaffold guard** — `test_no_router_pins_data_root_at_import_time`: assert `runs_root()`
  returns the env value on a second call after a mid-process `setenv` (i.e. resolution is
  call-time, not cached at import), and that `card_readout._data_root()` and the intake/pipeline
  routers resolve to the **same** root under one `PIPEGUARD_DATA_ROOT` — freezing §3d and the
  plan's "avoid a third divergent knob" risk so a new router can't reintroduce a hardcoded `data/`.
- **Real-data acceptance:** **omitted — a `tmp_path` fixture genuinely suffices.** This is a
  path-resolution/infrastructure gap with no science or tool-output ingestion; the behavior is
  identical for a synthetic run dir and a real one, so there is nothing a real GIAB run would
  exercise that the tmp-dir test does not.
- **Definition of Done:** `test_run_discovery_honors_pipeguard_data_root` and
  `test_no_router_pins_data_root_at_import_time` green offline (no real-data test owed).

## Definition of Done (workstream)

- [ ] **Gap A — adapter:** `tests/test_ingest_nfcore.py::test_adapter_qcmetrics_equal_bespoke_csv_for_one_sample` + `::test_adapter_emits_native_source_units_not_prescaled` green; guard `::test_adapter_never_fabricates_or_defaults_an_absent_metric` green; real-GIAB `::test_adapter_matches_driver_on_real_giab_results` green in the `hackathon` env.
- [ ] **Gap B — live aliases:** `tests/test_ingest_nfcore.py::test_renamed_multiqc_key_still_resolves_on_the_live_path` green; guard `::test_no_leaf_key_reaches_qcmetrics_without_alias_resolution` green; `resolve_alias` now has ≥1 call site under `src/pipeguard/ingest/`.
- [ ] **Gap C — real ingress:** `tests/test_intake_scheduling.py::test_ingest_endpoint_gates_a_non_fixture_results_dir` green; guard `::test_processability_is_on_disk_presence_not_a_sample_name_allowlist` green (no `_FIXTURE_SAMPLES` name-allowlist gates processing); real-GIAB `::test_ingest_real_giab_results_end_to_end` green in the `hackathon` env.
- [ ] **Gap D — run-store root:** `tests/test_intake_scheduling.py::test_run_discovery_honors_pipeguard_data_root` green; guard `::test_no_router_pins_data_root_at_import_time` green (call-time resolution, one shared root; no real-data test owed).
- [ ] **Invariants intact:** the full offline suite stays green (`data/mock_run_01` + pinned GIAB byte-identical); every new test asserts the verdict remains a deterministic function of `Finding`s, the adapter/ingress emit no verdict, and no missing/unknown metric becomes a passing default (fail-closed).
