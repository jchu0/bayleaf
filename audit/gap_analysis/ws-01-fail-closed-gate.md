> **Workstream WS-01 fix plan** — from the [gap-analysis fan-out](README.md); grounded in source against [the 2026-07-11 design review](design-review-2026-07-11.md). Read-only design (advisory). 2026-07-11 (MST).

# WS-01 — Fail-Closed Gate Semantics

## Problem
`PROCEED` today means "no *modeled* rule objected," not "examined and clean." Three seams leak green on missing data: the whole QC block is skipped when a sample has no QC row (`rules.py:453` `if qc is not None:`), `required=False` metrics silently vanish when absent (`rules.py:198-199`), and empty findings render as "all checks passed" (`stub.py:50-56`) — while the UI drops any check category with no rows (`MetricsPanel.tsx:157`, `RunDetail.tsx:476` `gateRan`). A sheet-declared sample with no QC emits zero findings → `aggregate_verdict([]) → PROCEED` (`base.py:28-32`).

## Design
Make "missing data" a **deterministic finding** so the verdict fails closed by the *existing* aggregation math — never by changing `aggregate_verdict`. Two new rules turn absence into HOLD (symmetric presence rule; expected-metric-set rule). Then make honesty visible: a deterministic `CheckCoverage` object (computed in the trust anchor, carried on the card as un-hashed contextual metadata like `metric_values`) drives (b) coverage prose + a card count and (d) a fixed expected-category catalog rendered as explicit `NOT RUN`. The verdict stays `f(findings)`; coverage is narration/telemetry only.

## Exact changes

**`src/pipeguard/rules.py`**
- `_check_presence` (`rules.py:85-130`) — add the symmetric **sheet-without-QC** rule. New param `qc_present: bool` (or pass `qc`+`demux`). Emit `QC-MISSING` (category `QC`, severity `WARN`, `suggested_verdict=HOLD`) when `qc is None and sheet is not None` (declared-for-sequencing but no QC artifact). Cites `Evidence(source="qc_metrics.csv", locator=f"sample_id={sid}", value="missing", expected="present")` — the new rule authors its own evidence (invariant 2). Guard on `sheet is not None` so an intake-only/accessioned-but-not-run sample is not false-HOLDed.
- New `_check_expected_metrics(sid, by_key, runbook)` — for each `our_key` in `runbook.expected_metrics` not in `by_key`, emit `QC-EXPECTED-<key>` (category from registry gate, `WARN`, `HOLD`) "expected metric not examined." This restores signal for `required=False` safety metrics *bound to a profile* without NA-flagging genuinely lean runs.
- `evaluate_sample` (`rules.py:436-478`) — keep the `if qc is not None:` guard (avoids N duplicate NA findings), but after the threshold loop call `_check_expected_metrics` (only when `qc is not None`; the `qc is None` case is covered by `QC-MISSING`). Add new `compute_check_coverage(...)` (below).
- New `compute_check_coverage(sid, artifacts, runbook, findings) -> CheckCoverage` — deterministic: enumerates the expected check set (provenance/metadata/qc-threshold/expected-metric/pipeline categories the runbook defines) vs. what actually ran given the artifacts present, returns counts + not-examined labels + `categories_ran`/`categories_not_run`. Lives in `rules.py` because it is a pure function of artifacts+runbook (trust anchor), not narration.

**`src/pipeguard/runbook.py`**
- Add to `Runbook` (`runbook.py:71-95`): `pipeline_profile: str = "default"` and `expected_metrics: tuple[str, ...] = ()`. `DEFAULT_RUNBOOK` leaves `expected_metrics=()` → zero behavior change. A `germline-panel` runbook variant sets e.g. `("qc.breadth_20x",)`. This is the seam WS-06 (§6a `RunbookSet`) will lift onto the per-`(assay, sample_type, platform)` profile — same field name so the migration is a move, not a rename.

**`src/pipeguard/synthesis/base.py` + `stub.py` + `claude.py`**
- `Synthesizer.synthesize` protocol (`base.py:46-53`) — add optional `coverage: CheckCoverage | None = None`. `aggregate_verdict` untouched (invariant 1).
- `StubSynthesizer.synthesize` (`stub.py:44-81`) — replace the empty-findings prose (`stub.py:50-56`): headline `"{verdict} — {ran}/{expected} checks passed"` (not "all checks passed"); rationale states coverage: `"{sample} passed the {ran} checks that ran; {not_examined_labels} not examined."` The non-empty branch appends the same coverage tail.
- `ClaudeSynthesizer` — thread `coverage` through; the live prompt may narrate coverage but the count is deterministic (never model-authored).

**`src/pipeguard/models.py`**
- New `CheckCoverage(BaseModel)`: `checks_expected: int`, `checks_ran: int`, `not_examined: list[str]`, `categories_ran: list[Category]`, `categories_not_run: list[Category]`.
- `DecisionCard` (`models.py:215-306`) — add `check_coverage: CheckCoverage | None = None`, documented (like `metric_values`, `models.py:249-253`) as contextual metadata **excluded from `content_hash`** (`models.py:287-306`).

**`src/pipeguard/engine.py`**
- `run_gate` loop (`engine.py:104-146`) — compute `coverage = compute_check_coverage(sample_id, artifacts, runbook, findings)`, pass into `synthesizer.synthesize(sample_id, findings, artifacts, coverage)` (`engine.py:137`), and attach `card.check_coverage = coverage` alongside the `metric_values` attach (`engine.py:144-146`).

**`api/main.py` + `api/card_readout.py`**
- Surface the expected-category catalog + ran/not-run on the qc-readout side-channel (`card_readout.py:316-373`, `QcReadout` at `:163-169`) or on the card endpoint, so the frontend can render `NOT RUN`. Optionally add `required`/expected flags to `RunbookThreshold` (`main.py:168-201`, `get_runbook` `:1052-1082`).

**`frontend/src/components/MetricsPanel.tsx` + `screens/RunDetail.tsx`**
- Fix `gateRan` (`RunDetail.tsx:476`) — a gate that ran clean has *no* `gate_result` (only findings produce one, `models.py:270-272`); drive expected-gate/category presence from the backend `CheckCoverage`, not `card.gate_results`. Add a `not_run` status alongside `not_measured` (`MetricsPanel.tsx:45-55`) and render a fixed expected-category catalog (contamination, identity) with an explicit `NOT RUN` cell instead of hiding empty groups (`MetricsPanel.tsx:157`). Add a one-line "Coverage: N ran · M not examined" summary from `check_coverage`.

## Data-contract / model changes
- `Runbook`: `+pipeline_profile: str = "default"`, `+expected_metrics: tuple[str, ...] = ()`.
- New `CheckCoverage` model; `DecisionCard.check_coverage: CheckCoverage | None` (un-hashed).
- `Synthesizer.synthesize(..., coverage: CheckCoverage | None = None)` — signature widened (optional, back-compatible).
- New findings `QC-MISSING`, `QC-EXPECTED-<key>` (both HOLD).
- API: optional `CheckCoverage`/expected-category catalog on the readout response.

## Cross-cutting impact & ordering
Shared-core files touched: `rules.py`, `runbook.py`, `models.py`, `synthesis/base.py`, `synthesis/stub.py`, `synthesis/claude.py`, `engine.py`.
- **WS-06 (§6a/§6b) must land after WS-01 here**: `expected_metrics`/`pipeline_profile` are added flat now and WS-06 lifts them onto `RunbookSet(assay, sample_type, platform)` — coordinate the field name so it is a move. WS-06's registry-driven ingestion also makes the expected-metric check meaningfully richer.
- **WS-02 must land after**: WS-01 defines the expected-category catalog + `NOT RUN` UI and the expected-metric HOLD machinery; when WS-02 wires `contamination.freemix`/`identity.*`, add those keys to a profile's `expected_metrics` and they auto-flip from `NOT RUN` to a real ran-check (or a HOLD if expected-but-absent) — no further UI work.
- **WS-07 (AI) shares the `synthesize` signature change**: rebase WS-07 on the widened `coverage` param; the live path narrates coverage but never authors the count (invariant 1/3).
- **WS-05 (config loop)**: when `_active_runbook` (`main.py:233-248`) starts applying real overrides, `expected_metrics` must be part of the typed override schema — flag as a dependency, not a blocker.

## Tests
- `tests/test_gate.py` (patterns at `:54-59`): declared sample, no QC row → `QC-MISSING` → run verdict HOLD, not PROCEED. Assert `S1-S3` still clean/PROCEED (pinned demo unchanged) and HG002 still HOLDs on `cluster_pf` (unchanged).
- Expected-metric: runbook with `expected_metrics=("qc.breadth_20x",)` + a sample missing breadth → `QC-EXPECTED-*` HOLD; default runbook (`expected_metrics=()`) → no new finding.
- `compute_check_coverage`: counts + `not_examined` labels for clean vs. missing-data samples.
- Stub prose: empty-findings card shows "N/M checks" not "all checks passed"; `check_coverage` populated; `content_hash` excludes it (attach/detach → identical hash).
- Frontend: `not_run` catalog renders for contamination/identity; clean QC gate no longer disappears.

## Back-compat / migration
- `DEFAULT_RUNBOOK.expected_metrics=()` and `QC-MISSING` guarded on `sheet is not None` → mock_run_01 (all 5 have QC rows) and HG002 (QC row present) are **byte-for-byte unchanged** in verdict.
- `CheckCoverage` excluded from `content_hash` → card identity stable.
- **One deliberate churn**: the empty-findings prose change alters `headline`/`rationale`, which *are* in `DecisionCard.content_hash` (`models.py:300-301`), so every clean-PROCEED card's hash changes. This is an intended narration update (not a verdict change) — update golden fixtures/persisted-card tests in the same PR and call it out in the PR description.
- `synthesize` coverage param is optional → external callers unaffected.

## Sequencing
1. **PR1 — fail-closed rules (smallest, highest trust):** `rules.py` `QC-MISSING` + `_check_expected_metrics`; `runbook.py` `expected_metrics`/`pipeline_profile`. Verdict now fails closed. No prose/hash change.
2. **PR2 — coverage object + prose:** `models.CheckCoverage` + card field; `compute_check_coverage`; `synthesize` signature + stub/claude prose; `engine` wiring. Update golden tests (hash churn).
3. **PR3 — API surface:** expose `CheckCoverage`/expected-category catalog on the qc-readout side-channel (`card_readout.py`) and optionally `RunbookThreshold` (`main.py`).
4. **PR4 — frontend NOT RUN:** fix `gateRan`, add `not_run` status + fixed expected-category catalog + coverage summary (`MetricsPanel.tsx`, `RunDetail.tsx`).

## Risks / tradeoffs / honest limits
- **content_hash churn** on clean cards is unavoidable if coverage lives in `rationale`; the alternative (count only in the un-hashed field, generic rationale) reduces churn but weakens the prose the review asked for. Recommend accepting the one-time churn + golden update.
- **Over-flagging**: an `expected_metrics` entry a legitimately lean run can't produce would wrongly HOLD — mitigated by scoping expected sets to *named* profiles (default empty); this is the intended trade (signal over silent-pass).
- **"Declared but no QC" semantics**: `QC-MISSING` treats a sheet-declared, QC-less sample as missing-data HOLD; a mid-run/partial-ingest sample will HOLD rather than PROCEED — correct for a safety gate, but note it depends on WS-03's ingestion honestly marking in-progress runs so this isn't mistaken for a QC failure.
- **`gateRan` fix depends on `CheckCoverage` reaching the frontend** (PR3 before PR4); until then the UI keeps today's hide-empty behavior.
- Coverage denominator must be defined precisely (thresholds evaluated + presence/provenance/pipeline rules that executed) so "M not examined" isn't a misleading count — pin it in `compute_check_coverage`'s docstring and a test.

### Critical Files for Implementation
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/rules.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/runbook.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/synthesis/stub.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/models.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/frontend/src/screens/RunDetail.tsx

---

## Test-First Contract (per surfaced gap)

Each gap below gets a **red** acceptance test (fails today, green only when the *real* wiring exists),
an **anti-scaffold guard** (a standing assertion that freezes the finding so it can't silently reopen),
a **real-data acceptance** criterion (only where adoption/ingestion/science is at stake — otherwise the
gap is a deterministic rule/prose/projection change a fixture genuinely settles, and that is stated), and
a binary **Definition of Done**.

**Invariants every test in this contract must preserve** (asserted inline, not assumed):
- **I1 — verdict is a deterministic function of findings.** The run verdict is `aggregate_verdict(findings)`
  (`synthesis/base.py:28-32`) and nothing else. Every red test asserts the verdict equals
  `aggregate_verdict(findings)` for the exact finding list it produced — never a value the synthesizer,
  prose, or `CheckCoverage` chose. `aggregate_verdict` itself is **not modified** by any WS-01 change.
- **I2 — the gate fails closed.** Missing/absent data pushes toward the *more severe* verdict (HOLD),
  never PROCEED. Each red test drives a missing-data path and asserts the run does **not** land on PROCEED.
- **I3 — the AI/narration layer never sets a verdict.** `CheckCoverage` is deterministic, computed in the
  trust anchor (`rules.compute_check_coverage`), carried as **un-hashed** contextual metadata, and read by
  the stub/Claude prose only. Tests assert it is excluded from `content_hash` and that attaching/detaching
  it (or swapping stub↔claude) leaves the verdict identical.

The reference cited real test files: `tests/test_gate.py` (rule engine + stub + aggregation, existing
patterns at `:56-90`, `:141-158`, `:365-373`) and `tests/test_card_readout.py` (the QC-readout side-channel
the frontend consumes, existing patterns at `:104-113`, `:177-198`, `:259+`). **There is no JavaScript test
runner in `frontend/`** (only `oxlint` + `tsc build` — verified: `frontend/package.json` has no `test`
script, no vitest/jest, zero `*.test.tsx`), so the NOT-RUN UI catalog is pinned at its *data contract*
(`tests/test_card_readout.py`, real + runnable) plus a labelled manual browser verification for the DOM
itself — no fabricated JS test is claimed.

---

### Gap A — no-QC → HOLD (the `if qc is not None:` skip + no symmetric sheet-without-QC rule)

Today a sheet-declared sample with **no QC row** skips the entire QC block (`rules.py:453`) and
`_check_presence` (`rules.py:85-130`) has PROV-002 for *QC-without-sheet* but **no rule for sheet-without-QC**,
so it emits zero findings → `aggregate_verdict([]) → PROCEED` (`base.py:31`). That is the exact case a safety
gate must fail closed on.

- **Red acceptance test** — `tests/test_gate.py::test_sheet_without_qc_holds`.
  Build a `RunArtifacts` with a sample declared on `sample_sheet` (and present in intake metadata, so
  META-002 does *not* fire and the HOLD is attributable purely to missing QC) but **absent from `artifacts.qc`**;
  run the real `evaluate_sample(sid, artifacts, DEFAULT_RUNBOOK)` (or `run_gate` end-to-end). Assert exactly
  one `QC-MISSING` finding, `category is Category.QC`, `severity is Severity.WARN`, `suggested_verdict is
  Verdict.HOLD`; assert its Evidence is self-authored and cites the real source
  (`source == "qc_metrics.csv"`, `value == "missing"`, `expected == "present"`, `SourceKind.METRIC`) —
  invariant 2 of the review's "what to preserve." Assert the run verdict `aggregate_verdict(findings) is
  Verdict.HOLD` and **is not** `Verdict.PROCEED` (I1 + I2). This exercises the real parse→rule→verdict path:
  `evaluate_sample` → the new symmetric branch of `_check_presence` → `aggregate_verdict`.
  **Why a stub/scaffold cannot pass it:** the test constructs real artifacts and reads the finding list the
  rule engine actually emits, then re-derives the verdict from *those* findings. A scaffold that hardcodes a
  HOLD card, or returns HOLD without an emitted, cited `QC-MISSING` finding, fails the Evidence-source and
  `aggregate_verdict(findings)`-equality assertions; the only way to green it is to author the finding in the
  deterministic engine so it flows through the existing aggregation math unchanged.
- **Anti-scaffold guard** — `tests/test_gate.py::test_declared_sample_never_proceeds_without_examined_qc`.
  Standing assertion over any run: **for every sample where `sheet is not None` and no QC row exists, the
  finding set contains `QC-MISSING` and `aggregate_verdict(findings) is not Verdict.PROCEED`.** Phrased as an
  implication that freezes the finding: *"no sheet-declared, QC-less sample can map to PROCEED."* Also pin the
  guard boundary — an intake-only/accessioned sample (`sheet is None and qc is None`) does **not** emit
  `QC-MISSING` (no false HOLD on a not-yet-sequenced sample), matching the plan's `sheet is not None` guard.
- **Real-data acceptance** — **required** (this is where "fixture green ≠ real run works" bites). On real
  GIAB HG002 via `scripts/run_giab_pipeline.py` (the `hackathon` env; `data/real-giab/` is present in this
  checkout), the driver *does* write a QC row for HG002, so the criterion is that `QC-MISSING` **does not
  fire** for HG002 and the sample still **HOLDs on `cluster_pf`** (the existing honest structural HOLD,
  `runbook.py:99-114`) — the new rule must neither mask nor duplicate that HOLD. A synthetic no-QC fixture
  proves the rule *fires*; the real HG002 run proves it does **not** spuriously fire when QC is genuinely
  present. Evidence: `tests/test_gate.py::test_sheet_without_qc_holds` (fires on fixture) green **and** the
  live HG002 run card carries no `QC-MISSING` finding while retaining the `cluster_pf` HOLD (env-gated check,
  joins the skip-safe live pattern already used by `test_nextflow_compile.py` / `test_persistence_postgres_live.py`).
- **Definition of Done:** `test_sheet_without_qc_holds` **and**
  `test_declared_sample_never_proceeds_without_examined_qc` green, and the env-gated HG002 live check confirms
  no spurious `QC-MISSING`. Pinned demo unchanged: `test_clean_samples_have_no_findings` (`:56`) and
  `test_verdict_aggregation_precedence` (`:87`) stay green (mock_run_01's five samples all carry QC rows).

---

### Gap B — empty-findings "all checks passed" prose

`StubSynthesizer.synthesize` with an empty finding list writes *"cleared every provenance, metadata, and QC
check… No inconsistencies were found"* (`stub.py:50-56`) — conflating "no modeled rule objected" with
"verified good," including categories (contamination/identity) nothing ever examined.

- **Red acceptance test** — `tests/test_gate.py::test_empty_findings_prose_states_coverage_not_all_passed`.
  Take a genuinely clean sample (e.g. S1 from mock_run_01 via `run_gate(load_run(DATA),
  synthesizer=StubSynthesizer())`, following the pattern at `:141-143`). Assert the card's `headline` +
  `rationale` **do not** contain the banned phrases (`"all checks passed"`, `"cleared every"`, `"No
  inconsistencies were found"`), and **do** contain a coverage count sourced from the card's real
  `check_coverage` — `f"{check_coverage.checks_ran}/{check_coverage.checks_expected}"` — and an explicit
  "not examined" clause naming at least one un-examined category (`check_coverage.not_examined` non-empty,
  e.g. contamination/identity). Assert `card.verdict is Verdict.PROCEED` still (I1 — the prose change moves
  narration, never the verdict) and `card.generated_by == "stub"`, `card.confidence is None` (`:146-147`).
  Exercises the real `engine.run_gate` → `compute_check_coverage` → `StubSynthesizer.synthesize(...,
  coverage=...)` path.
  **Why a stub/scaffold cannot pass it:** the count must equal the *real* `CheckCoverage` computed from this
  run's artifacts+runbook. A hardcoded replacement string (swap "all checks passed" for a fixed "5/5") passes
  the banned-phrase check but fails the guard test below, which compares the denominator against a different
  run's coverage and against the runbook's actual expected-category count — a constant can't satisfy both.
- **Anti-scaffold guard** — `tests/test_gate.py::test_no_card_claims_all_checks_passed_when_a_category_not_run`.
  Over every card in the demo run, assert **no `rationale`/`headline` asserts blanket clearance while
  `check_coverage.not_examined` is non-empty** (the banned phrases never co-occur with an uncovered category),
  and assert the denominator is honest: `check_coverage.checks_expected` equals the count the runbook defines
  (thresholds evaluated + presence/provenance/metadata/pipeline rules that ran + expected-metric set) and is
  strictly `> checks_ran` whenever a category (contamination/identity) has no rule — so "M not examined" can
  never be faked to zero. Freezes the finding: *"no card renders 'all checks passed' when a check category is
  NOT RUN."*
- **Real-data acceptance** — **not required; a fixture suffices, and here is why:** this is a deterministic
  prose-templating change over `CheckCoverage`, which is itself a pure function of `(artifacts, runbook)`.
  mock_run_01's clean samples (S1-S3) and the missing-data fixture from Gap A exercise both the covered and
  uncovered branches with no dependence on live tool output. (The HG002 live run will naturally show the new
  coverage prose, but nothing about the prose is unverifiable offline.)
- **Definition of Done:** `test_empty_findings_prose_states_coverage_not_all_passed` **and**
  `test_no_card_claims_all_checks_passed_when_a_category_not_run` green. Note the deliberate one-time
  `content_hash` churn on clean-PROCEED cards (prose is hashed, `models.py:300-301`): the golden/persisted-card
  fixtures updated in the same PR is part of DoD, called out in the PR description (per the plan's Back-compat §).

---

### Gap C — `required=False` silent skip (safety-adjacent metrics vanish when absent)

A `required=False` threshold with a *missing* value returns `None` → no finding (`rules.py:194-199`), so a
pipeline that simply omits breadth/mapping/on-target reads "all clear." The richer the check, the easier it
evades the gate.

- **Red acceptance test** — `tests/test_gate.py::test_expected_metric_absent_holds`.
  Construct a named-profile runbook via `DEFAULT_RUNBOOK.model_copy(update={"expected_metrics":
  ("qc.breadth_20x",)})` and a sample whose QC row omits `breadth_20x`; run `evaluate_sample`. Assert exactly
  one `QC-EXPECTED-QC.BREADTH_20X` (or the plan's `QC-EXPECTED-<key>` id) finding, `severity WARN`,
  `suggested_verdict Verdict.HOLD`, with self-authored Evidence citing the expected key (`value == "not
  examined"`, `expected == "present"`). Assert `aggregate_verdict(findings) is Verdict.HOLD` and not PROCEED
  (I1 + I2). **Paired negative in the same test (or a sibling):**
  `tests/test_gate.py::test_expected_metric_default_runbook_no_finding` — the identical sample under
  `DEFAULT_RUNBOOK` (`expected_metrics == ()`) emits **no** `QC-EXPECTED-*` finding and stays byte-for-byte
  unchanged (the lean-run guarantee). Exercises the real `evaluate_sample` → new `_check_expected_metrics`
  driven off the runbook field + the sample's actual `by_key` map (`rules.py:456`).
  **Why a stub/scaffold cannot pass it:** a scaffold must satisfy *both* the positive (fires on the
  expected-set runbook) and the negative (silent on the default runbook) branches simultaneously — that is
  only achievable by wiring the check to the real `runbook.expected_metrics` field and the sample's real
  metric map. A hardcoded "always emit" or "never emit" stub fails one branch.
- **Anti-scaffold guard** — `tests/test_gate.py::test_expected_metric_set_leaves_no_silent_skip`.
  Standing assertion: for a named profile, `{key for key in runbook.expected_metrics if key not in
  sample_by_key}` equals `{f.our_key-derived-key for f in findings if f.rule_id.startswith("QC-EXPECTED")}` —
  every expected-but-absent metric produces exactly one finding, none silently vanishes — **and**
  `DEFAULT_RUNBOOK.expected_metrics == ()` (a `runbook.py` assertion) so the default path is provably a no-op.
  Freezes the finding: *"a `required=False` metric bound to a profile's expected set can no longer skip
  silently."*
- **Real-data acceptance** — **not required for the core assertion; a fixture suffices** (the expected-metric
  rule is pure runbook-field-vs-sample-map logic). One optional real-data corroboration worth noting, not
  gating DoD: HG002's live mosdepth output *does* emit `breadth_20x`, so a future `germline-panel` profile
  listing it as expected should show it **RAN**, not HOLD-on-absent — a check that the rule doesn't spuriously
  HOLD a real run that legitimately emits the metric. This lands with WS-06's `RunbookSet` profile binding,
  flagged there as a dependency, not blocking this gap's fixture-level DoD.
- **Definition of Done:** `test_expected_metric_absent_holds`, `test_expected_metric_default_runbook_no_finding`,
  and `test_expected_metric_set_leaves_no_silent_skip` green; `test_missing_metric_flagged` (`:106`, the
  `required=True` NA→WARN path) and `test_metric_pass_returns_none` (`:101`) unchanged.

---

### Gap D — NOT-RUN UI catalog (absent check categories are invisible)

`MetricsPanel`/`QCReadout` render only gate groups with rows (`g.rows.length > 0`), and `gateRan`
(`RunDetail.tsx:476`) derives "did this gate run?" from `card.gate_results` — but a gate that ran *clean* has
no `gate_result` (only findings produce one, `models.py:270-272`), so a clean gate is indistinguishable from a
gate that never ran, and "contamination: not examined" is inferred from a missing pill, never shown.

- **Red acceptance test (rule layer)** — `tests/test_gate.py::test_compute_check_coverage_marks_uncovered_categories`.
  For a clean mock_run_01 sample, assert `compute_check_coverage(sid, artifacts, DEFAULT_RUNBOOK, findings)`
  returns `categories_not_run` containing the categories with no rule/parser (contamination, identity),
  `checks_ran < checks_expected`, and `not_examined` labels naming them; for the Gap-A missing-QC sample,
  assert the QC category is reported not-fully-covered. Asserts `compute_check_coverage` is a pure function of
  `(artifacts, runbook, findings)` (deterministic, trust-anchor — I3).
- **Red acceptance test (API data contract the UI consumes)** —
  `tests/test_card_readout.py::test_readout_exposes_not_run_catalog` (extends the existing readout patterns at
  `:177-198`). Assert the qc-readout side-channel surfaces the *fixed expected-category catalog* with an
  explicit per-category `ran | not_run` status — a category with no rows **and** no rule renders `not_run`,
  never omitted — and carries the `checks_ran / checks_expected` summary. Exercises the real
  `card_readout`/API projection, not the DOM.
  **Why a stub/scaffold cannot pass it:** the catalog status must be derived from the real `CheckCoverage`
  computed off artifacts+runbook. A scaffold that returns `categories_ran == categories_expected` (the current
  hide-empty behavior) fails, because contamination/identity genuinely have no rule/parser and must surface as
  `not_run`; a stub that hardcodes a NOT-RUN list fails the count assertions when the covered set changes
  between a clean run and the missing-QC run.
- **Anti-scaffold guard** — `tests/test_card_readout.py::test_expected_category_never_silently_omitted`.
  Standing assertion: **every category in the fixed expected catalog appears in the readout with an explicit
  `ran`/`not_run` status — none is dropped for having zero rows.** Concretely, the set of category ids in the
  projected catalog equals the fixed expected set for *every* run (clean, borderline S5, missing-QC), so a
  clean gate can never disappear (`gateRan` fix) and an unexamined category can never be inferred from absence.
  Freezes the finding: *"no readout omits an expected category; NOT RUN is rendered, not implied."*
- **Frontend DOM (labelled, not a fabricated test):** since `frontend/` has **no JS test runner**, the
  `MetricsPanel`/`RunDetail` render is verified by (i) the two Python contract tests above (the data the UI
  binds to), and (ii) a manual browser check — the decision card shows a fixed contamination/identity row with
  an explicit `NOT RUN` cell and a "Coverage: N ran · M not examined" line — recorded as a screenshot in the
  PR. No `*.test.tsx` is invented; `tsc build` + `oxlint` clean is the automated frontend gate.
- **Real-data acceptance** — **not required; a fixture suffices.** This gap is a projection/presentation
  contract over `CheckCoverage` (a deterministic function of already-parsed artifacts). contamination/identity
  are NOT-RUN on *every* run today (no parser exists — that wiring is WS-02's job), so the fixed catalog
  renders identically for fixture and real runs; nothing here depends on live tool output.
- **Definition of Done:** `test_compute_check_coverage_marks_uncovered_categories`,
  `test_readout_exposes_not_run_catalog`, and `test_expected_category_never_silently_omitted` green;
  `tsc build` + `oxlint` clean; PR screenshot showing the NOT-RUN catalog + coverage summary rendered.
  `test_card_carries_registry_normalized_metric_values` (`:349`) and the existing readout tests unchanged.

---

### Cross-gap invariant test — `CheckCoverage` is un-hashed and verdict-neutral

- **Test** — `tests/test_gate.py::test_check_coverage_excluded_from_content_hash` (mirrors the existing
  `test_metric_values_are_not_in_content_hash`, `:365-373`). Assert a card's `content_hash ==
  card.model_copy(update={"check_coverage": None}).content_hash` (I3 — coverage is contextual metadata like
  `metric_values`, `models.py:249-253`), and that attaching coverage does not change `card.verdict`. Assert
  `check_coverage` survives `model_dump(mode="json")` (API/ML serialization, like `:376`). This guarantees the
  narration/telemetry object can never leak into card identity or the verdict.

---

## Definition of Done (workstream)

- [ ] **Gap A (no-QC → HOLD):** `tests/test_gate.py::test_sheet_without_qc_holds` green + guard
  `tests/test_gate.py::test_declared_sample_never_proceeds_without_examined_qc` green + env-gated HG002 live
  check shows no spurious `QC-MISSING` (retains `cluster_pf` HOLD).
- [ ] **Gap B (empty-findings prose):** `tests/test_gate.py::test_empty_findings_prose_states_coverage_not_all_passed`
  green + guard `tests/test_gate.py::test_no_card_claims_all_checks_passed_when_a_category_not_run` green +
  golden/persisted-card hash fixtures updated in-PR.
- [ ] **Gap C (`required=False` silent skip):** `tests/test_gate.py::test_expected_metric_absent_holds` +
  `tests/test_gate.py::test_expected_metric_default_runbook_no_finding` green + guard
  `tests/test_gate.py::test_expected_metric_set_leaves_no_silent_skip` green.
- [ ] **Gap D (NOT-RUN UI catalog):** `tests/test_gate.py::test_compute_check_coverage_marks_uncovered_categories`
  + `tests/test_card_readout.py::test_readout_exposes_not_run_catalog` green + guard
  `tests/test_card_readout.py::test_expected_category_never_silently_omitted` green + `tsc build`/`oxlint`
  clean + PR screenshot of the rendered NOT-RUN catalog.
- [ ] **Cross-gap invariant:** `tests/test_gate.py::test_check_coverage_excluded_from_content_hash` green
  (`CheckCoverage` un-hashed + verdict-neutral).
- [ ] **Regression floor (unchanged):** `test_clean_samples_have_no_findings` (`:56`),
  `test_verdict_aggregation_precedence` (`:87`), `test_missing_metric_flagged` (`:106`),
  `test_metric_values_are_not_in_content_hash` (`:365`) all green — mock_run_01 + HG002 verdicts
  byte-for-byte unchanged.
