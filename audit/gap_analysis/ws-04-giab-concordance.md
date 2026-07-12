> **Workstream WS-04 fix plan** — from the [gap-analysis fan-out](README.md); grounded in source against [the 2026-07-11 design review](design-review-2026-07-11.md). Read-only design (advisory). 2026-07-11 (MST).

# WS-04 — GIAB Concordance / Scientific Validation

## Problem
`data/real-giab/` ships the HG002 v4.2.1 benchmark VCF + confident BED (`HG002_GRCh38_1_22_v4.2.1_benchmark.panel.vcf.gz`, `..._noinconsistent.bed`) but nothing ever computes concordance — the "variant gate" only counts records (`run_giab_pipeline.py:498-505 count_variants`; runbook is DP-only, `runbook.py:165-180`). The "grounded in GIAB truth" claim is unbacked, and the caller under test is `bcftools call -mv` (`pipelines/germline/modules/bcftools_call.nf`), not GATK-HC/DeepVariant.

## Design
Add an **optional benchmark-concordance stage** that runs `hap.py` (default xcmp engine, no SDF dependency; `--engine vcfeval` optional) of the pipeline's published `*.norm.vcf.gz` against the on-disk truth VCF, scored **inside `confident ∩ panel` regions**, then parses `precision / recall / F1` (SNP + INDEL, PASS rows) and Ts/Tv. Those become a new immutable per-sample `ConcordanceRecord` the gate READS (composes ≠ executes stays intact — Nextflow runs hap.py, the core only parses). A new deterministic rule **VAR-CONC-001** authors cited `Finding`/`Evidence` from those numbers and lands in the existing VARIANT gate group; the numbers also surface as registry `MetricValue`s on the card.

Concordance is only computable where a truth set is bound to the sample (HG002). For every other sample it is honestly **"not examined (no benchmark truth)"** — never a silent green. Labeling is fixed everywhere as *concordance vs the GIAB v4.2.1 benchmark within confident∩panel regions using `bcftools call -mv`* — **not clinical validation**.

Invariants preserved: rules decide (VAR-CONC-001 is a pure function of parsed numbers vs runbook), AI narrates; the new check cites its own Evidence (`concordance.csv` rows + truth-set citation); absence of an *expected* concordance fails CLOSED (→ HOLD via WS-01), never PROCEED; the seam is closed for the benchmark and labeled for everyone else.

## Exact changes
- **`src/pipeguard/models.py`**
  - New enum member on `Category` (`models.py:54-63`): reuse existing `Category.VARIANT` (no new member needed — keeps `_CATEGORY_GATE` mapping at `:97-106`, so findings route to `Gate.VARIANT` automatically).
  - New frozen model `ConcordanceRecord` (per sample): `sample_id`, and optional `snp_recall/snp_precision/snp_f1`, `indel_recall/indel_precision/indel_f1`, `snp_titv_query`, `indel_count_truth`, plus provenance `caller`, `truth_set`, `truth_regions`, `engine`. All optional (a partial/garbled hap.py summary is a signal, not a crash — same posture as `VariantCall`, `models.py:446-464`).
  - `RunArtifacts` (`models.py:466-500`): add `concordance: list[ConcordanceRecord] = Field(default_factory=list)`; include its ids in `sample_ids()` (`:487-500`).
- **`src/pipeguard/parsers.py`**
  - New `parse_concordance(path)` modeled on `parse_variant_calls` (`parsers.py:282-325`) — tolerant `pd.read_csv`, `_first_present` column spellings, verbatim numbers.
  - `load_run` (`:333-374`): parse `concordance.csv` (absent → `[]`) and pass into `RunArtifacts`.
- **`src/pipeguard/metrics/metric_registry.yaml`**
  - Add six `gate: variant`, `canonical_unit: fraction`, `direction: higher_is_better` keys: `concordance.snp_recall/…_precision/…_f1`, `concordance.indel_recall/…_precision/…_f1` (source module `happy`, `source_file: happy.summary.csv`). These are *new computed* keys (not the 7 NOT-COMPUTED ones).
  - Flip `variant.titv` from ungated observation to a target-band gate (see data-contract below); keep `contamination.freemix`/identity keys for WS-02.
- **`src/pipeguard/rules.py`**
  - New `_check_concordance(sid, concordance, runbook)` → **VAR-CONC-001**, `category=Category.VARIANT`. Gate SNP **F1 and Recall** (recall = clinical sensitivity) against runbook thresholds; below `hard_fail` → `CRITICAL`/`RERUN`, borderline → `WARN`/`HOLD`. Evidence cites `concordance.csv` (`locator=sample_id`, `value=f1=…`, `expected=≥ gate`) **and** the truth set (`source=f"GIAB {truth_set}"`, `source_field="F1/Recall"`, `source_kind=SourceKind.METRIC`) plus the caller string. Detail text hard-codes the honest label ("concordance vs benchmark, `bcftools call -mv`, confident∩panel — not clinical validation").
  - Wire into `evaluate_sample` (`rules.py:436-478`) next to the QC loop, resolving `next((c for c in artifacts.concordance if c.sample_id==sid), None)`.
- **`src/pipeguard/runbook.py`**
  - Add concordance `QCThreshold`s (`required=False` — a non-benchmark run has no truth, so absence is *not* a spurious HOLD; WS-01's expected-metric-set upgrades absence to a finding for the benchmark profile). Thresholds calibrated to `bcftools call -mv` on a panel (e.g. SNP F1 gate `0.90`, hard-fail `0.80`; SNP recall gate `0.90`, hard-fail `0.80`).
  - `variant.titv` becomes a `target_band` threshold (needs WS-06 gate-type; see ordering).
- **`src/pipeguard/engine.py`** (`:140-146`)
  - After `metric_values_for(qc)`, also append registry `MetricValue`s for the sample's `ConcordanceRecord` (via `registry.observe(metric_key="concordance.snp_f1", …)`) so the card's `metric_values` carry them and the VARIANT gate group in `card_readout.py` renders them. Additive, off the hash (same treatment as existing metric_values).
- **`scripts/run_giab_pipeline.py`** (driver, outside core)
  - New `parse_happy_summary(results, sample)` → reads `${sample}.happy.summary.csv` via `_one_for` (`:424-439`), extracts SNP/INDEL PASS precision/recall/F1 + Ts/Tv.
  - `write_run_dir_multi` (`:518-591`) writes a new `concordance.csv` (one row per sample that had a truth set), carrying `caller="bcftools call -mv"`, `truth_set`, `truth_regions="confident∩panel"`, `engine`. Samples with no truth → no row (honest absence).
  - Pass `--truth_vcf/--truth_bed/--truth_regions` into `run_nextflow` (`:366-421`) params only when the benchmark sample is being run; add CLI args in `main` (`:612-639`).
- **`pipelines/germline/modules/happy.nf` (new)** + **`pipelines/germline/main.nf`** (`:14-28`)
  - `HAP_PY` process, `conda 'bioconda::hap.py=0.3.15'`, input `(meta, norm_vcf)`, `truth_vcf`, `confident_bed`, `panel_bed`, `reference`; runs `hap.py <truth> <norm> -f <confident> -R <panel> -r <reference> -o ${meta.id}.happy` publishing `${meta.id}.happy.summary.csv`. Wire conditionally: `if (params.truth_vcf) HAP_PY(BCFTOOLS_NORM.out.filtered_vcf, …)`. Non-benchmark runs omit `--truth_vcf` → process never runs → concordance absent (fail-honest, not fail-fabricate).

## Data-contract / model changes
- New `ConcordanceRecord` (frozen, all-optional-except-sample_id) + `RunArtifacts.concordance: list[ConcordanceRecord]`.
- New run-dir artifact `concordance.csv`: `sample_id,snp_recall,snp_precision,snp_f1,indel_recall,indel_precision,indel_f1,snp_titv_query,caller,truth_set,truth_regions,engine`.
- Registry: +6 `concordance.*` keys (`fraction`, `variant` gate); `variant.titv` → gated. **No new `CanonicalUnit`** (precision/recall/F1 = `fraction`, Ts/Tv = `ratio` already exist).
- **Shared QCThreshold contract change (owned by WS-06, consumed here):** extend `QCThreshold` (`runbook.py:13-42`) with `gate_type: Literal["one_sided","target_band"] = "one_sided"` + `target_low/target_high: float|None`; `_evaluate_metric` (`rules.py:194-279`) branches on it. WS-04's concordance metrics are one-sided and need none of this; only the Ts/Tv sanity gate does.

## Cross-cutting impact & ordering
- **Shared core touched:** `models.py`, `parsers.py`, `rules.py`, `runbook.py`, `engine.py`, `metrics/metric_registry.yaml`. All additive; existing findings/verdicts byte-identical when `concordance.csv` is absent (every run today).
- **WS-06 must land before** the Ts/Tv target-band gate (it owns the `QCThreshold.gate_type`/target-band change and the registry-driven ingestion). Concordance F1/recall/precision are one-sided and ship **independent of WS-06**. If WS-06's registry-driven `dict[our_key,value]` ingestion lands, `ConcordanceRecord` + `parse_concordance` should fold into that generic path (retire the dedicated parser) — flag as a follow-up so we don't re-create the 4-file coupling.
- **WS-01 must define the expected-metric-set** so that when a benchmark/GIAB profile is bound to a sample, a *missing* concordance becomes a HOLD (fail-closed) rather than a `required=False` skip; and the "not examined" catalog cell (WS-01 §1d) covers non-benchmark samples. WS-04 provides the metric; WS-01 provides the closed-catalog fail-closed semantics — land WS-01's expected-set hook first or concurrently.
- **WS-03 (ingest adapter):** a real `results/` adapter should also discover a `happy.summary.csv` if present, so concordance rides the same ingress. Coordinate the adapter's artifact map.
- No dependency on WS-02/05/07.

## Tests
- `parse_concordance`: well-formed, missing-column, empty-file → `[]`/`None` fields (mirror `test_*` parser style).
- `_check_concordance`/VAR-CONC-001: fixture `concordance.csv` with (a) good F1/recall → no finding, (b) borderline → WARN/HOLD, (c) collapsed F1 → CRITICAL/RERUN; assert Evidence cites `concordance.csv` **and** the truth set, and the honest caller label is in the detail.
- Verdict-invariance: a run dir **without** `concordance.csv` produces byte-identical cards to today (guards the additive claim) — extend `test_run_giab_multisample`/`test_card_readout`.
- Registry: every new `concordance.*` `our_key` is registered and normalizes (extend the existing our_key-registration test).
- Driver: `parse_happy_summary` unit test against a committed tiny `happy.summary.csv` fixture (no hap.py on PATH needed — pure parse, same pattern as `test_run_giab_driver.py`).
- Ts/Tv target-band test lands with WS-06.

## Back-compat / migration
- Every change is additive; absent `concordance.csv` (all existing fixtures) → zero behavior change, verdicts and content-hashes unchanged.
- `metric_registry_version` **must bump** (1→2) since new keys are added — it is snapshotted on every `AnalysisRun` and `MetricValue` (`registry.py`, `engine.py:87`); update the version-pinned tests/fixtures.
- `bcftools call -mv` stays the default caller; a later `--caller deepvariant` swap re-derives concordance automatically (record `caller` in the artifact so the comparison is never mis-attributed). No data migration — new artifact, new optional fields.

## Sequencing (PR-sized)
1. **Core contract (no behavior change):** `ConcordanceRecord` + `parse_concordance` + `load_run` wiring + 6 registry keys + version bump + parser/registry tests. Verdicts unchanged (no rule yet).
2. **Rule + surfacing:** VAR-CONC-001 + runbook concordance thresholds (`required=False`) + engine card `MetricValue`s + card_readout label. Verdict changes only when `concordance.csv` present; add rule/invariance tests.
3. **Execution wiring:** `happy.nf` + conditional `main.nf` + driver `--truth_*` passthrough + `parse_happy_summary` → writes `concordance.csv`; end-to-end HG002 (env-gated like the rest of the driver).
4. **Ts/Tv target-band (after WS-06):** wire `variant.titv` as a target-band sanity gate + concordance Ts/Tv observation.
5. **Fail-closed integration (with WS-01):** benchmark profile requires concordance → absent = HOLD; non-benchmark = "not examined" catalog cell.

## Risks / tradeoffs / honest limits
- **Caller ceiling:** `bcftools call -mv` on a panel yields lower F1 than DeepVariant/GATK-HC; thresholds are calibrated to *this* caller and the finding says so. Do **not** advertise the numbers as caller-agnostic quality — they gate *this pipeline's* regression, not "clinical-grade variant quality." Keep concordance thresholds conservative so a real regression trips CRITICAL without false-alarming on the caller's baseline.
- **Truth only for HG002:** concordance is structurally unavailable for real subjects (no truth). It is a **benchmark/validation** signal, not a per-run gate — the design makes that explicit via `required=False` + the "not examined" state, and leans on WS-01 to fail-closed only where a truth set is actually bound.
- **hap.py dependency/runtime:** adds a bioconda dep and minutes of runtime; gated behind `params.truth_vcf` so it never burdens a real run. xcmp engine avoids the rtg SDF; `--engine vcfeval` is an opt-in that needs an SDF (note in module docs).
- **Region semantics:** scoring inside `confident ∩ panel` (confident BED is genome-wide `_noinconsistent.bed`, panel is the arbitrary chr20 smoke windows) — the F1 is only as meaningful as that intersection; label it as such and never generalize beyond the panel.
- **Honest limit:** this backs the *"concordance vs a public benchmark"* claim only. It is **not** clinical validation, not accreditation, and says so in the finding text, the registry `display_name`, and the card label.

### Critical Files for Implementation
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/scripts/run_giab_pipeline.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/rules.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/models.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/metrics/metric_registry.yaml
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/pipelines/germline/main.nf

## Test-First Contract (per surfaced gap)

Each gap below gets (1) a **red acceptance test** that cannot pass until the real wiring exists,
(2) an **anti-scaffold guard** that freezes the finding so it can't silently reopen, (3) a
**real-data acceptance** criterion where the gap is a science/ingestion claim (omitted, with a
reason, where a fixture genuinely suffices), and (4) a binary **Definition of Done**. Every test
preserves the WS-invariants (§11 of the review): the verdict stays a **deterministic function of
`Finding`s** (`aggregate_verdict`, `synthesis/base.py:28-32`), the gap pushes the gate toward
failing **CLOSED**, and the concordance numbers + `VAR-CONC-001` verdict come only from the parser
+ the deterministic rule — **never a synthesizer** (the AI-narrates boundary, ADR-0001).

New home for the parser+rule specs: **`tests/test_concordance.py`** (new file, styled on the
existing **`tests/test_route_to_human.py`** — the closest analog: a variant-gate rule with its own
tolerant parser, an off-by-default posture, and an end-to-end "rules decide the card verdict" test).
Driver specs extend **`tests/test_run_giab_driver.py`** / **`tests/test_run_giab_multisample.py`**;
card-surfacing specs extend **`tests/test_card_readout.py`**; registry specs extend
**`tests/test_metrics.py`**.

### Gap 1 — concordance actually computed vs the truth VCF

**Red acceptance test** — `tests/test_concordance.py::test_end_to_end_concordance_run_reruns_the_card`
(mirrors `tests/test_route_to_human.py::test_end_to_end_armed_run_escalates_the_card`, lines
120-131). It builds `RunArtifacts(run_id="RUN-CONC", concordance=[ConcordanceRecord(sample_id="HG002",
snp_f1=0.40, snp_recall=0.42, snp_precision=0.55, caller="bcftools call -mv",
truth_set="HG002 v4.2.1", truth_regions="confident∩panel")])`, then `cards = run_gate(artifacts,
runbook=<concordance thresholds armed>)` and asserts `card.verdict is Verdict.RERUN` and
`any(f.rule_id == "VAR-CONC-001" for f in card.findings)`. It exercises the **whole
parse→rule→verdict path**: `parse_concordance` populating `RunArtifacts.concordance` →
`_check_concordance` resolving the record in `evaluate_sample` (rules.py:436-478, beside the existing
`_check_route_to_human` call at :474) → the finding's `suggested_verdict=RERUN` flowing through
`aggregate_verdict`. A **companion** `test_check_concordance_collapsed_f1_reruns` calls
`_check_concordance("HG002", records, runbook)` directly and asserts a `Finding` with
`rule_id=="VAR-CONC-001"`, `category is Category.VARIANT`, `gate.value == "variant"`,
`severity is Severity.CRITICAL`, `suggested_verdict is Verdict.RERUN`.
- **Why a stub/scaffold can't pass:** with no `ConcordanceRecord` model, no `parse_concordance`, and
  no `_check_concordance` wired into `evaluate_sample`, the sample trips no rule → `aggregate_verdict([])
  → PROCEED` (base.py:30-31). The assertion `card.verdict is Verdict.RERUN` fails. A prose-only
  scaffold that writes "concordance looks good" into a narration string sets **no** `Finding` and
  cannot move the verdict — the rule must exist and be a pure function of the parsed numbers.
- **Determinism/fail-closed asserts baked in:** `test_concordance_verdict_is_synthesizer_independent`
  runs the same armed `RunArtifacts` under `PIPEGUARD_SYNTHESIZER=stub` and a mocked `claude` and
  asserts an **identical** `card.verdict` (rules decide, AI narrates); the collapsed-F1 case fails
  **closed** to RERUN, never PROCEED.

**Anti-scaffold guard** — `tests/test_concordance.py::test_below_hard_fail_f1_never_proceeds`: a
`ConcordanceRecord` whose `snp_f1`/`snp_recall` is below the runbook `hard_fail` **never** yields an
empty findings list for that sample and **never** aggregates to `Verdict.PROCEED`, for any armed
concordance runbook. Freezes the exact §4 finding (a benchmark VCF on disk that never moves the
gate). Paired additivity guard — `tests/test_run_giab_multisample.py` extension
`test_concordance_absent_cards_byte_identical`: a run dir **without** `concordance.csv` produces
cards whose `content_hash`es are byte-identical to today's (guards the "purely additive" claim so
wiring the feature can't perturb the pinned demo; today `concordance.csv` is absent for every
committed run, so this must hold for `data/mock_run_01` and every GIAB fixture). The fail-closed
**absence** case (a benchmark profile bound but concordance missing → HOLD) is owned by WS-01's
expected-metric-set hook and is asserted there; WS-04's guard here covers present-but-collapsed.

**Real-data acceptance** — REQUIRED (this is the core science/ingestion claim). Env-gated like the
existing live-driver checks (the `nextflow -stub-run` / Postgres-live skip pattern, e.g.
`tests/test_run_giab_driver.py` gating on `shutil.which`): with `nextflow` + `hap.py` on PATH and
`data/real-giab/` present, the driver runs `hap.py` of the published `HG002.norm.vcf.gz` against
`HG002_GRCh38_1_22_v4.2.1_benchmark.panel.vcf.gz` **within `confident ∩ panel`**, and the emitted
`concordance.csv` row for HG002 has real `snp_recall/snp_precision/snp_f1 ∈ (0,1]` (not the fixture's
contrived `0.40`, and never a fabricated constant). Criterion: `parse_concordance` on the live run
dir yields a record with **non-None** `snp_f1`, and that value equals hap.py's summary digit-for-digit.
A committed tiny `happy.summary.csv` fixture (`tests/test_run_giab_driver.py::test_parse_happy_summary_extracts_precision_recall_f1`,
no hap.py on PATH needed, same pure-parse pattern as the existing driver parse tests) proves the
**parser** but explicitly does **not** satisfy this criterion — "fixture green ≠ hap.py actually ran
against the truth VCF" is exactly how the scaffold hid.

**Definition of Done:** `test_end_to_end_concordance_run_reruns_the_card`,
`test_check_concordance_collapsed_f1_reruns`, `test_concordance_verdict_is_synthesizer_independent`,
`test_below_hard_fail_f1_never_proceeds`, and `test_concordance_absent_cards_byte_identical` all green
offline; **and** the env-gated real-HG002 driver check produces a non-None parsed `snp_f1` from a real
hap.py run.

### Gap 2 — precision/recall/F1 surfaced as cited evidence

**Red acceptance test** — `tests/test_concordance.py::test_concordance_finding_cites_csv_and_truth_set`
(mirrors `tests/test_route_to_human.py::test_armed_pathogenic_routes_to_human`, lines 72-84, which
asserts `next(e for e in f.evidence if e.source_field == "CLNSIG")` and a verbatim value). For a
`ConcordanceRecord(snp_f1=0.40, snp_recall=0.42, …)` the `VAR-CONC-001` finding must carry **two**
kinds of `Evidence`: one citing the artifact (`source=="concordance.csv"`, `locator` containing the
`sample_id`, `value` containing the parsed `f1` string) **and** one citing the benchmark
(`source` starting `"GIAB "` and naming the truth set, `source_field in {"F1","Recall"}`,
`source_kind is SourceKind.METRIC`, `expected` naming the gate). The **card-surfacing** companion
`tests/test_card_readout.py::test_concordance_metric_values_surface_on_card`: a card built (via
`run_gate`) from a run carrying a `ConcordanceRecord` has `metric_values` including
`metric_key=="concordance.snp_f1"` (and recall/precision), and `build_qc_readout(card)` renders them
inside the **VARIANT** gate group (`[g for g in readout.gates if g.gate is Gate.VARIANT]`), with the
observed value preserved losslessly — the same projection contract `test_card_readout.py` already
pins for QC metrics.
- **Why a stub/scaffold can't pass:** the asserted `Evidence.value` must equal the number parsed from
  `concordance.csv` (e.g. `"f1=0.40"`), and the `MetricValue` must be `registry.observe`d from the
  parsed record (engine.py:140-146). A scaffold that emits narration prose has **no** `Evidence`
  object with `source=="concordance.csv"` and no `concordance.snp_f1` `MetricValue` — the `next(e for
  e in f.evidence if e.source_field=="F1")` lookup raises `StopIteration` and the `metric_values`
  membership assert fails. The truth-set citation cannot be faked into existence by prose.
- **Determinism/fail-closed asserts baked in:** the surfaced number is the parsed value, so the same
  `concordance.csv` yields the same `Evidence.value` and the same card `content_hash` across runs;
  the number is presented **with** its truth-set citation or not at all (never an unbacked bare number).

**Anti-scaffold guard** — `tests/test_concordance.py::test_conc_finding_always_carries_dual_citation`:
**every** `VAR-CONC-001` finding carries `≥2` `Evidence` entries, at least one with
`source=="concordance.csv"` and at least one with `source.startswith("GIAB")` and
`source_kind is SourceKind.METRIC`. Freezes §11.2 (every new check authors its own cited `Evidence`
the same way FREEMIX/RTH do) so a later refactor can't drop the truth-set citation and present a
precision/recall number the operator can't trace. Registry-registration guard —
`tests/test_metrics.py` extension: the six new `concordance.snp_recall/precision/f1` +
`concordance.indel_recall/precision/f1` `our_key`s are in `SEED_KEYS`, each resolves to a typed entry
with `gate == Gate.VARIANT` and `canonical_unit == CanonicalUnit.FRACTION`, and `registry.version`
bumps 1→2 (the existing `test_registry_loads_all_seed_keys` pins the version and the exact key set,
so a missing/renamed key fails loudly).

**Real-data acceptance** — the **evidence-shape** guard is satisfied by a fixture (the citation
structure is deterministic and a synthetic `concordance.csv` exercises it fully — say so explicitly).
The **numbers** are covered by Gap 1's real-data criterion: on the live HG002 run the F1/recall/precision
surfaced on the card and in the `Evidence.value` must equal hap.py's actual summary, not a placeholder.
No separate real-data run is needed for Gap 2 beyond Gap 1's.

**Definition of Done:** `test_concordance_finding_cites_csv_and_truth_set`,
`test_concordance_metric_values_surface_on_card`, `test_conc_finding_always_carries_dual_citation`,
and the extended `test_registry_loads_all_seed_keys` (six keys, version 2) all green.

### Gap 3 — Ts/Tv target-band

**Red acceptance test** — `tests/test_concordance.py::test_titv_out_of_band_holds` and
`::test_titv_in_band_passes`. Today `_evaluate_metric` (rules.py:194-279) is **one-sided only**
(`value >= gate` or `value <= gate`) and `variant.titv` is a registered-but-**ungated** observation
(runbook.py:165-179 comment: "a … target-band metric the one-sided gate can't score"). These tests
build a `QCMetrics(variant_titv=1.2)` (well outside the ~2.0–2.1 WGS band) and assert
`_evaluate_metric("S", <variant.titv target-band threshold>, mv)` returns a `Finding` with
`severity is Severity.WARN` and `suggested_verdict is Verdict.HOLD`; an in-band `variant_titv=2.05`
returns `None`. It exercises the real `_evaluate_metric` two-sided branch against a
`QCThreshold(gate_type="target_band", target_low=2.0, target_high=2.1)`.
- **Why a stub/scaffold can't pass:** the `QCThreshold.gate_type`/`target_low`/`target_high` fields
  and the `_evaluate_metric` target-band branch **do not exist yet** (owned by WS-06). Until they do,
  `variant.titv` produces **no** finding for any value, so `test_titv_out_of_band_holds`'s
  "returns a Finding" assertion fails, and a scaffold that hardcodes a HOLD would wrongly fail
  `test_titv_in_band_passes` (an in-band 2.05 must return `None`). Only the real two-sided gate
  satisfies **both** directions.
- **Determinism/fail-closed asserts baked in:** an out-of-band Ts/Tv fails toward HOLD (attention),
  in-band is silent; the decision is a pure function of `(target_low, target_high, value)`.

**Anti-scaffold guard** — `tests/test_concordance.py::test_titv_is_actually_gated_not_dropped`:
`DEFAULT_RUNBOOK.threshold_for("variant_titv")` (once WS-06 lands) is not `None` and its `gate_type`
is `"target_band"`; a value inside `[target_low, target_high]` **never** yields a finding and a value
outside **always** does. Freezes §6c/§9d (Ts/Tv "parsed but can't be scored") so it can't regress to
a silent ungated observation.

**Real-data acceptance** — OMITTED; a fixture genuinely suffices. The target-band decision is pure
threshold arithmetic over a single scalar; a synthetic `variant_titv` value exercises every branch
with no dependence on a real run. (The *observed* Ts/Tv on HG002 is a nice-to-have but not required to
prove the gate works.)

**Definition of Done:** `test_titv_out_of_band_holds`, `test_titv_in_band_passes`, and
`test_titv_is_actually_gated_not_dropped` green — **gated on WS-06** landing the
`QCThreshold.gate_type`/`target_low`/`target_high` contract and the `_evaluate_metric` two-sided
branch (this workstream's DoD records the dependency, does not duplicate WS-06's own tests).

### Gap 4 — caller-choice honesty

**Red acceptance test** — `tests/test_concordance.py::test_concordance_records_caller_and_honest_label`
(mirrors `tests/test_route_to_human.py::test_armed_pathogenic_routes_to_human`'s
`assert "makes no pathogenicity determination" in f.detail`). For a `ConcordanceRecord(caller="bcftools
call -mv", truth_regions="confident∩panel", …)` the `VAR-CONC-001` finding's `detail` must contain the
caller string, the region string (`"confident"` and `"panel"`), and the disclaimer `"not clinical
validation"`; and a **caller swap** is honored — a record with `caller="deepvariant"` puts
`"deepvariant"` (not a hardcoded `"bcftools"`) in the detail. A driver companion
`tests/test_run_giab_driver.py::test_concordance_csv_stamps_the_caller_run` asserts the emitted
`concordance.csv` carries the `caller` column equal to the caller the driver actually ran.
- **Why a stub/scaffold can't pass:** the caller must be threaded from the parsed `ConcordanceRecord`
  into the finding text and the artifact column. A scaffold that hardcodes a generic "concordance:
  PASS" string contains no caller/region/disclaimer substrings, and a hardcoded `"bcftools"` fails the
  `caller="deepvariant"` swap assertion — the value must round-trip from the record.
- **Determinism/fail-closed asserts baked in:** the honesty label is deterministic text derived from
  the record's provenance fields (not a synthesizer), so it never drifts per invocation; a number is
  never presented as caller-agnostic "clinical-grade" quality (§4/§9b overclaim frozen out).

**Anti-scaffold guard** — `tests/test_concordance.py::test_conc_never_overclaims_without_caller_context`:
**no** `VAR-CONC-001` finding text asserts variant quality without naming the caller (`record.caller`
substring present), the `confident∩panel` region, and the `"not clinical validation"` disclaimer; and
`ConcordanceRecord.caller` in the emitted artifact equals the caller the driver ran (never a hardcoded
default). Freezes the review's "grounded in GIAB truth" → *this pipeline's `bcftools call -mv`
regression signal, labeled as such* reframing.

**Real-data acceptance** — PARTIAL (fixture suffices for the label/threading; one real-data tie-in).
The finding-text and swap behavior are fully exercised by a synthetic `ConcordanceRecord`. The single
real-data criterion, folded into Gap 1's live check: the live HG002 driver stamps the **actual** caller
it ran (`bcftools call -mv` today, from `pipelines/germline/modules/bcftools_call.nf`) into
`concordance.csv` — so the label can never mis-attribute the numbers to a caller the run didn't use.

**Definition of Done:** `test_concordance_records_caller_and_honest_label`,
`test_concordance_csv_stamps_the_caller_run`, and `test_conc_never_overclaims_without_caller_context`
green; the caller stamped in the live-HG002 `concordance.csv` equals the pipeline's actual caller.

## Definition of Done (workstream)

- [ ] **Gap 1 — concordance computed vs truth VCF:** `tests/test_concordance.py::test_end_to_end_concordance_run_reruns_the_card` + `::test_check_concordance_collapsed_f1_reruns` + `::test_concordance_verdict_is_synthesizer_independent` green; **guard** `::test_below_hard_fail_f1_never_proceeds` + `tests/test_run_giab_multisample.py::test_concordance_absent_cards_byte_identical`; **real-data** env-gated HG002 hap.py run yields a non-None parsed `snp_f1`.
- [ ] **Gap 2 — precision/recall/F1 as cited evidence:** `tests/test_concordance.py::test_concordance_finding_cites_csv_and_truth_set` + `tests/test_card_readout.py::test_concordance_metric_values_surface_on_card` green; **guard** `tests/test_concordance.py::test_conc_finding_always_carries_dual_citation` + `tests/test_metrics.py::test_registry_loads_all_seed_keys` (six `concordance.*` keys, version 2). Numbers proven real via Gap 1's HG002 run.
- [ ] **Gap 3 — Ts/Tv target-band:** `tests/test_concordance.py::test_titv_out_of_band_holds` + `::test_titv_in_band_passes` green; **guard** `::test_titv_is_actually_gated_not_dropped`. **Blocked on WS-06** (`QCThreshold.gate_type`/`target_low`/`target_high` + `_evaluate_metric` two-sided branch). Fixture suffices — no real-data run.
- [ ] **Gap 4 — caller-choice honesty:** `tests/test_concordance.py::test_concordance_records_caller_and_honest_label` + `tests/test_run_giab_driver.py::test_concordance_csv_stamps_the_caller_run` green; **guard** `tests/test_concordance.py::test_conc_never_overclaims_without_caller_context`; **real-data** live HG002 `concordance.csv` stamps the pipeline's actual caller.
- [ ] **Cross-cutting invariants (asserted inside the above):** verdict is `aggregate_verdict(findings)` (deterministic, synthesizer-independent); every new check fails **closed**; every VAR-CONC-001 number carries a truth-set citation; no card renders concordance "passed" for a caller/region it did not actually run.
