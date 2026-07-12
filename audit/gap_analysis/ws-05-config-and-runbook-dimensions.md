> **Workstream WS-05 fix plan** — from the [gap-analysis fan-out](README.md); grounded in source against [the 2026-07-11 design review](design-review-2026-07-11.md). Read-only design (advisory). 2026-07-11 (MST).

# WS-05 — Config Loop + Multi-Dimensional Runbook

## Problem
The runbook is a single flat `list[QCThreshold]` (`runbook.py:76-181`) with no assay/sample-type/platform axis, yet `SettingsAssayTable.tsx` renders a 3-assay × 2-tissue matrix it cannot persist to the core. The whole draft→approve override stack reaches no verdict: `_active_runbook` (`api/main.py:233-248`) only ever returns `DEFAULT_RUNBOOK`, the override `payload` is schemaless `dict[str, Any]` (`settings.py:114-134`) carrying display labels ("Q30", "Mean genome depth") no rule can map, and `settings.py:1-15` admits the loop is never closed.

## Design
Three coupled pieces, all fail-closed, all keeping the verdict a pure function of findings (ADR-0001):

1. **`RunbookSet` keyed `(assay, sample_type, platform)`** in `runbook.py`, with a total, documented resolution order. Each axis gets a distinct binary weight (`assay=4, sample_type=2, platform=1`); a sample's candidate keys are the 7 non-empty masked combinations, tried in descending weight, first registered match wins, else the `default` Runbook. Binary weights guarantee a **total order with no ties** and encode "assay dominates." Resolution is a pure function of sample metadata + the set — no LLM, fully deterministic.

2. **Per-sample resolution in `evaluate_run`/`run_gate`** (the signature cross-cut). `evaluate_run` and `run_gate` widen their `runbook` param to `Runbook | RunbookSet`; a bare `Runbook` is coerced to a `RunbookSet(default=...)` (back-compat). `evaluate_run` resolves the concrete `Runbook` **per sample** from `(artifacts.assay, sample.tissue, artifacts.platform)` and passes it to the existing `evaluate_sample(sid, artifacts, runbook)` — whose signature is **deliberately unchanged**, so all rule-level tests and WS-01/WS-06 rule edits keep composing against a concrete resolved runbook. This is the sharp decision: widen the two orchestration entry points, freeze the rule signature.

3. **Typed override schema + real apply in `_active_runbook`.** Add a typed `ThresholdOverridePayload` parsed at *apply* time (the store envelope stays tolerant per its charter). `_active_runbook` reads the latest **approved** override per name, parses each, and patches `gate`/`hard_fail`/`borderline_band` of **existing** thresholds (matched by registry `our_key`) on a per-run **copy** of the default, registering the result in a `RunbookSet` under the override's key. Fail-closed guards: an unparseable/legacy override is **ignored + logged**, never crashes and never silently moves a gate; overrides may **not** set `required`, add, or remove a threshold, so they can never convert a fail-closed backstop (e.g. `cluster_pf` `required=True`) into fail-open.

The frontend `SettingsAssayTable` must send `our_key`-keyed edits, not display labels — otherwise the typed parser rejects them (the current honest failure mode). Until that lands, `get_config`/the table carry an in-product **"authoring only — not applied to runs"** banner (the §5a honest-label fallback), which is also the safe interim if step 3 slips.

## Exact changes
- **`src/pipeguard/runbook.py`**
  - Add `RunbookKey` (frozen: `assay/sample_type/platform: str|None`, normalized lower/trim) and `RunbookSet(BaseModel)` with `default: Runbook`, `entries: dict[RunbookKey, Runbook]` (or `list[RunbookEntry]`), and `resolve(assay, sample_type, platform) -> Runbook` implementing the weight-ordered fallback. Document the order in the docstring.
  - Add classmethod `RunbookSet.of(Runbook)` for coercion.
  - Leave `QCThreshold` (`:13-42`) and `Runbook` (`:71-195`) structurally intact — `RunbookSet` composes whatever `QCThreshold` shape WS-06 later produces.
- **`src/pipeguard/rules.py`**
  - `evaluate_run` (`:481-486`): accept `Runbook | RunbookSet | None`; coerce; resolve per sample via `set.resolve(artifacts.assay, sample.tissue, artifacts.platform)`; call unchanged `evaluate_sample`. `evaluate_sample` (`:436-478`) signature **unchanged**.
- **`src/pipeguard/engine.py`**
  - `run_gate` (`:49-78`): widen `runbook` to `Runbook | RunbookSet`; coerce (`:78`). `gate_provenance["runbook_metrics"]` (`:87`) currently reads one runbook — change to record the **resolved runbook per sample** (or the set's key list) so provenance stays honest under per-sample resolution. `run_gate_from_dir` (`:226`) type widened.
- **`src/pipeguard/models.py`**
  - `RunArtifacts` (`:466-486`): add `assay: str | None = None` (run-level; `Sample.tissue` at `:312` already supplies sample_type, `platform` at `:483` already exists).
- **`src/pipeguard/parsers.py`**
  - `load_run` (`:333-374`): read an optional `assay` marker file in the run dir (mirrors the `origin`/`route_to_human` marker pattern) and set `RunArtifacts.assay`.
- **`api/routers/settings.py`**
  - Add `ThresholdEdit` (`our_key: str`, optional `gate/hard_fail/borderline_band: float`) and `ThresholdOverridePayload` (`schema_version`, `assay/sample_type/platform: str|None`, `thresholds: list[ThresholdEdit]`) + a tolerant `parse_override_payload(dict) -> ThresholdOverridePayload | None`. Keep `ThresholdOverrideIn.payload` (`:134`) a `dict` at ingest (store charter), but run `parse_override_payload` in the `_sanity` validator (`:136-142`) so a well-formed typed payload is accepted and a malformed one 422s early (rather than silently unapplied).
- **`api/main.py`**
  - `_active_runbook` (`:233-248`): return `RunbookSet`. Build `default = DEFAULT_RUNBOOK` (+ existing `route_to_human` marker layering at `:241-248`), then fold in the latest **approved** overrides from `get_settings_store()`, parsing + patching per above.
  - `_evaluate` (`:251-272`): passes the `RunbookSet` through to `run_gate` unchanged at `:256`. **Add cache invalidation**: `_evaluate` is `@lru_cache` (`:251`), so approving an override won't re-gate — call `_evaluate.cache_clear()` from the approve endpoint (or key a version stamp into `_evaluate`).
  - `get_config` (`:691-694`): either return the resolved default plus the applied-override summary, or add the honest "authoring only" flag consumed by the frontend banner.
- **`api/routers/intake.py`**
  - Persist `assay` (`SubmitRunIn.assay`, `:99`) into the run record (`:317-335`) and write the `assay` marker into the run dir so `load_run` sees it.
- **`frontend/src/components/SettingsAssayTable.tsx`**
  - Map display rows (`:31-57`) to registry `our_key`s and send a typed `ThresholdOverridePayload` (`:160`), dropping/greying metrics with no computed `our_key` (FREEMIX, fold-80 — pending WS-02/WS-06). Add the "authoring only → applied" state tied to `get_config`.

## Data-contract / model changes
- New: `RunbookKey`, `RunbookSet`, `RunbookSet.resolve(...)`, `RunbookSet.of(...)` (`runbook.py`).
- New: `ThresholdEdit`, `ThresholdOverridePayload`, `parse_override_payload` (`settings.py`).
- `RunArtifacts.assay: str | None = None` (additive, optional — no fixture migration).
- Signature widen: `evaluate_run(artifacts, runbook: Runbook | RunbookSet | None)`, `run_gate(..., runbook: Runbook | RunbookSet | None)`, `run_gate_from_dir(...)`, `_active_runbook -> RunbookSet`. `evaluate_sample` **unchanged**.
- Override payload gains a typed contract; the store envelope stays `dict` (tolerant persistence).

## Cross-cutting impact & ordering
- **Shared core touched:** `runbook.py`, `rules.py` (`evaluate_run`), `engine.py`, `models.py`, `parsers.py`. This is the deepest signature change of the 7 workstreams — I own the sequencing of the `evaluate_run`/`run_gate` widening.
- **WS-06 (must rebase on me):** §6a's `RunbookSet` *is* this workstream — WS-06 keeps only §6b (registry-driven ingestion) and §6c (two-sided `QCThreshold` gate type). Land my `RunbookSet`/resolution **first**; WS-06's richer `QCThreshold` composes through `RunbookSet` unchanged (it holds Runbooks holds thresholds). Coordinate the single `runbook.py` merge: I edit `Runbook`/add `RunbookSet`, WS-06 edits `QCThreshold` fields — disjoint hunks if sequenced.
- **WS-01 (builds on my resolved runbook):** §1c's expected-metric-per-profile binding naturally hangs off the **resolved** `Runbook`, so land my per-sample resolution **before** WS-01's expected-set. WS-01's independent fixes (missing-QC-row → HOLD, empty-findings prose) are orthogonal and may land first. My fail-closed override guard (no `required` edits) depends on WS-01's `required=True` backstops staying authoritative — align on that invariant.
- **WS-02/WS-06 downstream:** FREEMIX/fold-80 override rows stay greyed until those workstreams compute the `our_key`s.

## Tests
- `RunbookSet.resolve`: exact match; each single-axis fallback; the full 7-key precedence order (assert assay beats sample_type beats platform); empty set → `default`; unknown axis values → `default`.
- `evaluate_run` with a `RunbookSet`: two samples, different `tissue`, get different gates; a bare `Runbook` still works (back-compat); byte-identical findings vs. today for the pinned `mock_run_01`/HG002 fixtures (verdict-stability regression).
- `parse_override_payload`: valid typed payload; legacy display-label payload → `None` (ignored, not applied); out-of-range numbers 422 (reuses `settings.py` bounds).
- `_active_runbook`: no overrides → default only; one approved override → its `our_key` gate patched, others untouched; a `draft` (unapproved) override → **not** applied; unparseable approved override → default gate stands (fail-closed) + logged; override cannot set `required`/remove a threshold; approve → `_evaluate` cache cleared → next gate reflects it.
- Existing `test_settings.py`, `test_gate.py`, `test_run_giab_*` stay green.

## Back-compat / migration
- `RunArtifacts.assay` and the override typed schema are additive; older stored override records (display-label payloads) parse to `None` and are **ignored, not applied** — no data migration, and the pre-change verdict is preserved.
- Coercing bare `Runbook` → `RunbookSet` keeps every existing `run_gate`/`evaluate_run` caller (Streamlit app, scripts, tests) working unchanged.
- The pinned demo (`HG002 → HOLD` on missing `cluster_pf`) is unchanged: no approved overrides exist by default, and overrides cannot touch `required`.

## Sequencing (PR-sized)
1. **Core `RunbookSet` + resolution** — add types to `runbook.py`, widen `evaluate_run`/`run_gate`/`run_gate_from_dir`, add `RunArtifacts.assay` + `load_run` marker read. Pure back-compat (no override apply yet); verdicts byte-identical. *(Foundation WS-06/WS-01 rebase on.)*
2. **Typed override schema** — `ThresholdEdit`/`ThresholdOverridePayload`/`parse_override_payload` in `settings.py`; validator accepts typed, rejects garbage. Still not applied.
3. **Honest label** — `get_config` flag + `SettingsAssayTable` "authoring only — not applied" banner. Immediate honesty; safe stopping point if step 4 slips.
4. **Close the loop** — `_active_runbook` folds approved overrides into a `RunbookSet`; `_evaluate` cache invalidation on approve; intake persists `assay`. Flip the banner to "applied."
5. **Frontend our_key mapping** — `SettingsAssayTable` emits typed `our_key` payloads; grey uncomputed metrics.

## Risks / tradeoffs / honest limits
- **`assay` provenance:** if `assay` is written by the intake driver, it partly "grades its own homework" (§3d). Honest limit: mark driver-fabricated assay vs. operator/LIMS-supplied until WS-03 lands a real intake source. Absent assay → falls back to the default runbook (safe).
- **Cache staleness:** `_evaluate`'s `lru_cache` means approvals need explicit invalidation; miss it and overrides look inert. Called out as a required step, with a test.
- **Fail-closed vs. flexibility:** restricting overrides to `gate/hard_fail/borderline_band` on existing thresholds blocks operators from adding a brand-new gate via config in v1 — a deliberate trade to keep the fail-closed backstops (`required`, threshold membership) out of config reach. Adding thresholds via config is deferred until a metric has a computed `our_key` (WS-06).
- **Combinatorial keys:** `(assay, sample_type, platform)` is 3 axes; more axes (kit, reference build) would need re-weighting. The binary-weight scheme extends cleanly but isn't infinite — documented as a known ceiling.
- **Frontend/core coupling:** step 5 must land or the matrix keeps writing payloads the core ignores; steps 3–4 keep that state *honest* in the meantime rather than silently lying.

### Critical Files for Implementation
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/runbook.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/rules.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/src/pipeguard/engine.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/api/main.py
- /Users/jchu/IdeaProjects/claude_life_science_hackathon/api/routers/settings.py

## Test-First Contract (per surfaced gap)

Each surfaced gap below is frozen by a **red** acceptance test (fails today, green only when the *real* wiring exists), a standing **anti-scaffold guard** (so the finding can't silently reopen), and — for the gaps that must survive contact with a real run — a **real-data acceptance** on GIAB HG002. Every test preserves the WS invariants: the verdict stays a **deterministic function of findings** (`aggregate_verdict` over rule `Finding`s, ADR-0001), resolution/override machinery only moves threshold *numbers* or *selects* a threshold set — it never sets or overrides a verdict/confidence — and every fallback pushes toward failing **closed** (an unmatched axis → the full `default` runbook; a malformed override → the default gate stands; no config edit can touch `required`/threshold membership).

Grounding anchor for the API-level tests: `tests/test_route_to_human.py::test_clinvar_rth_fixture_escalates_via_per_run_arming` already imports `from api.main import _active_runbook` and drives `run_gate_from_dir("data/RUN-...", runbook=rb)` asserting a verdict — the exact seam the override/config tests reuse. Env-gated real-run checks follow the skip-safe pattern in `tests/test_nextflow_compile.py:264-292` (`shutil.which("nextflow")` → `pytest.skip`).

### Gap A — `RunbookSet(assay × sample_type × platform)` per-sample resolution

1. **Red acceptance test — `tests/test_runbook_set.py::test_evaluate_run_resolves_threshold_set_per_sample`** (new file; unit-resolution helpers in the same file, e2e in `tests/test_gate.py`).
   - **Asserts:** build a `RunbookSet` with a `default` (stock `DEFAULT_RUNBOOK`) plus one `entries` key `(assay=None, sample_type="saliva", platform=None)` whose `qc.q30` gate is tightened above HG002's/S-sample's observed Q30. Two samples on one run differ only in `Sample.tissue` (`models.py:314`) — one `blood`, one `saliva`. `evaluate_run(artifacts, the_set)` (`rules.py:481`) must yield a `QC-Q30` finding for the **saliva** sample and **none** for the **blood** sample. Exercises the real path parse → `RunArtifacts`(`assay`/`platform`) + `Sample.tissue` → `RunbookSet.resolve(...)` per sample → unchanged `evaluate_sample(sid, artifacts, resolved)` → `aggregate_verdict`.
   - **Companion resolution units (same file):** exact-match wins; each single-axis fallback resolves; the full 7-key precedence asserts **assay (weight 4) beats sample_type (2) beats platform (1)** with no ties (register three overlapping entries, assert the assay-keyed one wins); empty set → `default`; unknown axis values → `default`.
   - **Why a stub can't pass:** today `evaluate_run`/`evaluate_sample` take a single flat `Runbook` and apply one threshold list to every sample; `RunbookSet` does not exist (the import fails). A scaffold that ignores the axes and applies `default` to all samples yields **identical** findings for both samples — the test demands they *differ*, which is only possible once resolution genuinely selects the saliva entry from `(artifacts.assay, sample.tissue, artifacts.platform)`.
   - **Invariant hook:** the saliva flip is a *new deterministic `QC-Q30` finding*, not a verdict the set "set" — assert the verdict still comes from `aggregate_verdict(findings)`; and a bare `Runbook` passed to `evaluate_run`/`run_gate` yields **byte-identical** findings to today on `data/mock_run_01` (reuse the `test_gate.py` fixtures + the pinned 16-event/verdict/hash assertions) — back-compat coercion cannot drift the pinned demo.

2. **Anti-scaffold guard — `tests/test_runbook_set.py::test_resolution_is_per_sample_and_never_ungates`.** Freezes the finding two ways: (a) `RunbookSet.resolve(...)` **never returns None and never returns a runbook with an empty `qc_thresholds`** — an unmatched sample resolves to `default` (whose `qc_thresholds` is non-empty), so a new axis can never silently drop gating (fail-closed); (b) `RunbookSet.of(rb).resolve(any, any, any) is rb` (or `== rb`) — the bare-`Runbook` coercion path is provably a no-op, so the deepest signature widen can't diverge from today. A standing assert that two samples with distinct `(assay, tissue, platform)` **and** a matching distinct entry never receive the same resolved runbook object.

3. **Real-data acceptance.** **A synthetic two-tissue fixture genuinely suffices for the resolution logic** — resolution is a pure function of sample metadata + the set, independent of real reads, so no HG002 run is required to prove *correct selection*. The one real-run dependency (that `RunArtifacts.assay` is actually populated on a live run so per-assay resolution is non-vacuous) is an ingestion concern and is covered by Gap D's real-data acceptance, not duplicated here.

4. **Definition of Done.** `test_evaluate_run_resolves_threshold_set_per_sample` + the resolution-unit cases + `test_resolution_is_per_sample_and_never_ungates` all green, **and** the existing `tests/test_gate.py` pinned suite (incl. `test_ledger_captures_gate_event_trail`'s 16-event byte-identity) stays green under the widened `Runbook | RunbookSet` signature.

### Gap B — Typed override schema (`parse_override_payload`)

1. **Red acceptance test — `tests/test_settings.py::test_parse_override_payload_typed_vs_legacy`** (extends the existing settings suite; `parse_override_payload`/`ThresholdOverridePayload`/`ThresholdEdit` land in `api/routers/settings.py`).
   - **Asserts:** a well-formed **typed** payload (`schema_version` present + `thresholds: [{our_key: "qc.q30", gate, hard_fail, borderline_band}]`) parses to a `ThresholdOverridePayload` with typed, validated fields; a **legacy/display-label** payload — the current shape (a bare `dict` like the `_body()` helper's `{"qc.q30": {...}}`, or a display label `{"Q30": {...}}`, with no `schema_version`/`thresholds` array) — parses to **`None`** (ignored, never applied). Out-of-range numbers still 422 via the validator, reusing the bounds the existing `test_payload_rejects_obviously_out_of_range_thresholds` pins (a negative `gate`, an absurd `hard_fail`, a `borderline_band` outside `[0,1]`).
   - **Why a stub can't pass:** `parse_override_payload` does not exist today (import fails), and the store is deliberately schemaless (`ThresholdOverrideIn.payload: dict`, `settings.py`). A pass-through scaffold (`return payload`) cannot (a) return a *typed* object, (b) distinguish typed from legacy (the `None` branch), or (c) reject out-of-range fields — all three are asserted.
   - **Invariant hook — fail-closed membership guard:** a typed payload that tries to set `required`, or names an `our_key` **not** registered in `default_registry()` / not present in `DEFAULT_RUNBOOK.qc_thresholds`, or attempts to *add/remove* a threshold, is rejected (422 at ingest) or dropped at parse — config can only patch `gate`/`hard_fail`/`borderline_band` of an **existing** threshold. This is what keeps the `qc.cluster_pf` `required=True` NA→HOLD backstop (`runbook.py:107-114`) out of config's reach.

2. **Anti-scaffold guard — `tests/test_settings.py::test_override_schema_cannot_touch_required_or_membership`.** Standing asserts: (a) `parse_override_payload` returns `None` for **any** payload lacking `schema_version` + a `thresholds` array — the currently-stored display-label payloads never become an applied override; (b) the `ThresholdEdit` model has **no** field named `required`, `metric`, `add`, or `remove` (introspect `ThresholdEdit.model_fields`), so the typed contract *structurally* cannot flip a fail-closed backstop or change threshold membership; (c) an edit whose `our_key` is unregistered is rejected.

3. **Real-data acceptance.** **Not an adoption/ingestion/science gap** — the parser is pure over an in-memory payload; a fixture payload fully exercises it. Omit real-data acceptance (stated explicitly so its absence is intentional, not overlooked).

4. **Definition of Done.** `test_parse_override_payload_typed_vs_legacy` + `test_override_schema_cannot_touch_required_or_membership` green, and the existing `tests/test_settings.py` suite (tolerant store round-trips, 422 bounds, sqlite/postgres selection) stays green.

### Gap C — `_active_runbook` applies the approved override (or honest "not applied" label) + cache invalidation

1. **Red acceptance test — `tests/test_active_runbook.py::test_approved_override_moves_active_runbook_and_verdict`** (new file; models on `tests/test_route_to_human.py`'s `_active_runbook` + `run_gate_from_dir` pattern, backed by a tmp settings store via `PIPEGUARD_SETTINGS_PATH` like `tests/test_settings.py`).
   - **Asserts (loop-closed build):** save a **typed** override (a tightened `qc.mean_target_coverage` gate) for a committed stock run (e.g. `data/RUN-2026-07-04-GIAB-A`), **approve** it via the settings router, then `api.main._active_runbook(run_id)` returns a `RunbookSet`/`Runbook` whose patched `our_key` gate **differs from `DEFAULT_RUNBOOK`**, with every other threshold untouched. Re-gating the run (`run_gate_from_dir` / `_evaluate`) then flips the affected sample's verdict (PROCEED → HOLD) — and the flip is carried by a **new `QC-*` finding** the tightened gate emitted, asserted via `aggregate_verdict`, never by the override "setting" a verdict.
   - **Asserts (honest-label build — the §5a fallback):** if a build ships the label instead of the applied loop, `GET /api/config` (`get_config`, `api/main.py:691`) MUST carry `applied=false` / "authoring only — not applied to runs" **and** `_active_runbook(run_id)` MUST equal `DEFAULT_RUNBOOK` for a run with an approved override. The surface can never claim applied while returning the default (and can never return a moved gate while claiming not-applied). One of the two branches must hold — a build cannot pass with a silent middle state.
   - **Why a stub can't pass:** today `_active_runbook` literally `return DEFAULT_RUNBOOK` (+ only the `route_to_human` marker layering), ignoring the settings store entirely — its output **cannot differ** after an approval, and `get_config` returns a flat `DEFAULT_RUNBOOK.model_dump()` with no `applied` flag. Neither branch can be satisfied by the current wiring.

2. **Anti-scaffold guard — `tests/test_active_runbook.py::test_only_approved_typed_overrides_apply_and_cache_clears`.** Standing asserts freezing every fail-closed edge: (a) a **draft** (unapproved) override does **not** change `_active_runbook` — only the latest `approved` revision applies; (b) an **unparseable/legacy** approved override is **ignored + logged**, the default gate stands (fail-closed — a garbage override never moves a gate); (c) an approved override can **never** remove a threshold or flip `required` — the `qc.cluster_pf` NA→HOLD backstop and the pinned HG002 HOLD survive every override; (d) approving an override calls `_evaluate.cache_clear()` (`_evaluate` is `@lru_cache`, `api/main.py:251`) so the *next* `_evaluate(run_id)` reflects the new gate — a test that approves then re-reads and sees the moved verdict, proving the stale cache can't mask the change.

3. **Real-data acceptance.** **A committed fixture run dir suffices for the loop *mechanics*** (pure API + core, no reads), so the primary tests use `data/RUN-2026-07-04-GIAB-A`. But because "fixture green ≠ real run works" is exactly how config scaffolding hides, add an **env-gated** backstop `tests/test_active_runbook.py::test_override_moves_real_hg002_gate` (skip when the driver-produced HG002 run dir / `nextflow` is absent, per the `test_nextflow_compile.py:264` pattern): approve a tightened `qc.mean_target_coverage` override and re-gate the **real HG002 run dir** `scripts/run_giab_pipeline.py` produced, asserting HG002's coverage gate actually moves — the config loop controls a real run, not only a hand-authored fixture.

4. **Definition of Done.** `test_approved_override_moves_active_runbook_and_verdict` + `test_only_approved_typed_overrides_apply_and_cache_clears` green (the honest-label branch acceptable as an interim DoD only if `get_config.applied=false` is asserted and `_active_runbook==DEFAULT`), and the env-gated `test_override_moves_real_hg002_gate` green where the real run dir is present.

### Gap D — assay × tissue Settings table backed by a real core data source

1. **Red acceptance test — two parts** (the *testable* backend contract that backs the UI; the React render itself is validated by manual/e2e, out of scope for `tests/`).
   - **`tests/test_settings.py::test_assay_keyed_typed_override_is_accepted_and_applied`:** a payload in the exact shape a fixed `SettingsAssayTable` must emit — a typed `ThresholdOverridePayload` carrying `assay`/`sample_type` axis fields + `our_key`-keyed `ThresholdEdit`s — is accepted by `POST /api/settings/thresholds` (not 422) and, once approved, is folded by `_active_runbook` into the **matching `RunbookSet` key** (assert via the Gap-C seam that a sample resolving to that assay/tissue gets the patched gate). The current display-label emission (`"Q30"`, "Mean genome depth") is **rejected/ignored** — proving the frontend must migrate to `our_key`.
   - **`tests/test_api.py::test_config_exposes_runbook_axes_or_honest_flag`:** `GET /api/config` returns **either** an axis-aware runbook (resolvable `(assay, sample_type, platform)` keys the table can render truthfully) **or** an explicit `applied=false` / "authoring only" flag. A scaffold returning today's flat `DEFAULT_RUNBOOK.model_dump()` with neither axis metadata nor an honest flag fails.
   - **Why a stub can't pass:** `get_config` is flat today and `SettingsAssayTable.tsx` admits "the assay×tissue matrix has no core data source." A scaffold that keeps the flat dump fails the axis-or-flag assertion; a display-label payload that is silently stored-and-ignored fails the accept-and-apply assertion.
   - **Invariant hook:** assert `GET /api/config` and the settings-apply path carry **no** verdict/confidence field — only thresholds; the table can influence a verdict *only* by moving a deterministic threshold a rule then gates on (ADR-0001), never by authoring a verdict.

2. **Anti-scaffold guard — `tests/test_api.py::test_config_never_flat_while_claiming_authored_axes`.** Standing asserts: (a) `/api/config` never returns a flat runbook while also advertising assay×tissue authoring — either the axes are real (resolvable keys present) or `applied=false` is set; (b) a display-label override payload is never *silently accepted-and-ignored* — it 422s at ingest **or** parses to `None` at apply **and** `get_config.applied` reflects that it did not take effect (the surface can't lie about whether an edit is live).

3. **Real-data acceptance.** **This is an adoption gap** (does operator-facing config actually control a real run) — include an **env-gated** `tests/test_settings.py::test_assay_override_reaches_real_hg002_run` (skip-safe per `test_nextflow_compile.py:264`): the intake path persists `assay` (a run-dir marker read by `load_run`, `parsers.py:333`, mirroring the `origin`/`route_to_human` marker pattern) on the **real HG002 driver run**, an approved assay-keyed override resolves through `RunbookSet` to that assay's `Runbook`, and HG002's gate moves — proving the assay×tissue authoring reaches a real run, not only a synthetic fixture. A companion offline unit `tests/test_gate.py::test_load_run_reads_assay_marker` pins the marker read itself (`RunArtifacts.assay` populated from the marker; absent marker → `None` → default runbook, fail-safe).

4. **Definition of Done.** `test_assay_keyed_typed_override_is_accepted_and_applied` + `test_config_exposes_runbook_axes_or_honest_flag` + `test_config_never_flat_while_claiming_authored_axes` + `test_load_run_reads_assay_marker` green, and the env-gated `test_assay_override_reaches_real_hg002_run` green where the real HG002 run dir is present.

## Definition of Done (workstream)

- [ ] **Gap A — `RunbookSet` per-sample resolution:** `tests/test_runbook_set.py::test_evaluate_run_resolves_threshold_set_per_sample` (+ resolution-unit cases) green; guard `tests/test_runbook_set.py::test_resolution_is_per_sample_and_never_ungates` green; `tests/test_gate.py` pinned 16-event/verdict/hash suite still byte-identical under the widened signature.
- [ ] **Gap B — Typed override schema:** `tests/test_settings.py::test_parse_override_payload_typed_vs_legacy` green; guard `tests/test_settings.py::test_override_schema_cannot_touch_required_or_membership` green. (Fixture suffices — no real-data check.)
- [ ] **Gap C — `_active_runbook` applies approved override + cache invalidation:** `tests/test_active_runbook.py::test_approved_override_moves_active_runbook_and_verdict` green; guard `tests/test_active_runbook.py::test_only_approved_typed_overrides_apply_and_cache_clears` green; env-gated real-run `tests/test_active_runbook.py::test_override_moves_real_hg002_gate` green where the HG002 run dir is present.
- [ ] **Gap D — assay × tissue UI backed by core:** `tests/test_settings.py::test_assay_keyed_typed_override_is_accepted_and_applied` + `tests/test_api.py::test_config_exposes_runbook_axes_or_honest_flag` green; guards `tests/test_api.py::test_config_never_flat_while_claiming_authored_axes` + offline `tests/test_gate.py::test_load_run_reads_assay_marker` green; env-gated real-run `tests/test_settings.py::test_assay_override_reaches_real_hg002_run` green where the HG002 run dir is present.
