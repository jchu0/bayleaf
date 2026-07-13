# Journal — 2026-07-12 (MST) — Gap-analysis remediation: workstream landings + the real-HG002 verification milestone

| Field | Value |
|---|---|
| **Focus** | Doc-keeper SWEEP over the full `feat/gap-analysis-remediation` branch (`main..HEAD`, 20 commits): distil the session's workstream landings (WS-01/03/05/06/07/08/09/10) into the canonical docs per the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map), and record the headline verification milestone — the toolchain now runs on this machine and the full ingestion spine was proven end-to-end on real GIAB HG002 output. |
| **Participants** | Claude (doc-keeper subagent) on top of a prior autonomous overnight build session (Claude Opus 4.8 + `adversarial-reviewer`/`test-writer` subagents); maintainer (James Hu) reviewing. |
| **Outcome** | 10 canonical docs swept and corrected against code (2 real staleness bugs found and fixed: `metric_registry.md`/`qc_metrics.md`'s "10 gated/10 ungated" count and `nf-core-conventions.md`'s "pending real MultiQC parsing" claim); `docs/planning/tasks.md` gained 9 new task rows (T-144–T-152); `audit/gap_analysis/README.md`'s living tracker brought current; this journal captures the reasoning + decisions. **Addendum (same day):** WS-02/WS-04 landed (`b8494f5`, `072d8db`) — metric catalog 11/9 of 20 → 13/8 of 21, labelled "gated + parser-wired, not pipeline-produced"; caught and corrected a real `CheckCoverage` over-claim (the contamination category does not actually auto-flip to "ran") and a second pre-existing test-census drift (`test_card_readout` +4, `61936d1`); tracker corrected to 🟡 interim, not ✅ done, against this folder's own Definition of Done (real-data acceptance leg not landed). |

## Discussion

### Why this session exists

The branch landed 20 commits of gap-analysis remediation (closing gaps the 2026-07-11 adversarial
design review found: [design-review-2026-07-11.md](../../audit/gap_analysis/design-review-2026-07-11.md),
[delta-review-2026-07-12.md](../../audit/gap_analysis/delta-review-2026-07-12.md)) without a
canonical-doc sweep — two prior journals
([2026-07-12-gap-analysis-implementation.md](2026-07-12-gap-analysis-implementation.md),
[2026-07-12-ws07-honest-next-steps.md](2026-07-12-ws07-honest-next-steps.md)) explicitly flagged
"canonical doc sweep owed... deferred to integration to avoid collisions with parallel agents
editing shared docs." This entry IS that integration: SWEEP mode over the whole branch, grounding
every claim against the actual code (`grep`/`read`, not the commit messages verbatim — one over-claim
was caught and corrected mid-sweep, see below), then AUTHOR this journal, then run the CHK checklist.

### Method — verify before writing

Per CLAUDE.md's "ground every claim in code" rule, every factual claim below was checked directly,
not trusted from a commit message:

1. **`git log --oneline main..HEAD` + full commit bodies** (20 commits) — the ground truth for what
   landed, in what order, with what caveats already self-documented.
2. **Direct greps of the actual code** — `models.py` (`CheckCoverage`, `RawObservation`,
   `SampleMetrics`, `RunArtifacts.qc`), `runbook.py` (`RunbookKey`, `RunbookSet`, `QCThreshold.kind`,
   `GERMLINE_PANEL_RUNBOOK`), `rules.py` (`QC-MISSING`, `_check_expected_metrics`,
   `compute_check_coverage`, `_evaluate_target_band`), `ingest/nfcore.py`, `metric_registry.yaml`,
   `settings.py`.
3. **A re-derived test census**: `uv run pytest --collect-only -q` → 708 collected (was 634);
   `git ls-files 'tests/*.py' | wc -l` → 52 files (was 48); `uv run pytest -q` → 700 passed / 8
   skipped in this sandboxed shell.
4. **A live re-verification, not just re-reading a commit claim**: this doc-sweep session is running
   on the SAME machine the maintainer used for the real HG002 run — `.nf-runs/RUN-2026-07-08-GIAB-HG002/nf-out/results/`
   is genuinely on disk (gitignored, machine-local). Ran
   `uv run pytest tests/test_ingest.py -k real_nextflow -v` directly → **`1 passed`** — independently
   confirming WS-03/06's real-path ingestion-spine claim, not just quoting it.
5. **A caught over-claim, corrected before it shipped**: my first draft of the `evaluation.md` census
   said `test_e2e_pipeline.py` had been "relabelled in its own module docstring as a contract test...
   per the gap-analysis review's recommendation." `git log --oneline main..HEAD -- tests/test_e2e_pipeline.py`
   returned **nothing** — the file was never touched on this branch. The docstring's honest framing
   predates this branch; the review's rename recommendation (`test_pipeline_contract.py`) is **still
   open**, not done. Fixed before landing — see `quality/evaluation.md`'s entry for the corrected text.
   This is exactly the "confident surface vs. thin wiring" failure mode this whole branch exists to
   fix, caught in the act of documenting it.

### What actually landed (grounded against code, not just commit prose)

1. **WS-10 (`efef163`) — fastp promoted-output regression, REFUTED.** Ran the catalog's real fastp
   command on real HG002; the mandatory `unpaired_fastq`/`failed_fastq` outputs are always created
   (fastp opens the writers eagerly). No code fix; two guards froze the evidence. **RESOLVED.**
2. **WS-01 (`4d6acbf`, `118d8a5`, `98aca3d`, `14ea6fa`) — fail-closed gate, all 4 PRs.** `QC-MISSING`
   is live; `expected_metrics`/`_check_expected_metrics` shipped as a validated mechanism (dormant
   until WS-05); `models.CheckCoverage` replaced "all checks passed" with an honest "N ran / M not
   examined" count on the card AND the RunDetail clean-card panel. Grounded: read `rules.py` lines
   ~380–420 (`_check_expected_metrics`, `compute_check_coverage`) and `models.py:215`
   (`class CheckCoverage`) directly.
3. **WS-06 (`7b3f5ad`, `f4444be`, `cb56eb6`, `2033849`, `ce483ca`) — all six gaps.** Registry-keyed
   `SampleMetrics`/`RawObservation` ingestion contract (PR1); `RunArtifacts.qc: list[QCMetrics |
   SampleMetrics]` — a **transition Union, not a hard flip** (PR2); `QCThreshold.kind:
   Literal["one_sided", "target_band"]`, `variant.titv` the first `target_band` gate (Gap 2); dup-rate
   **REFUTED** (Gap 3 — the fixture's `0.0057` was already the correct percent, confirmed by running
   fastp for real in WS-10; the plan's proposed fix would have been a NEW bug); mosdepth/label source
   honesty (Gaps 4–5); one generic `JsonlStore`/`SqliteStore` base collapsing 7 store trios (Gap 6).
   Grounded: read `metric_registry.yaml` directly (confirmed 13/20 keys wired, the `# NOT COMPUTED`
   comments), `runbook.py`'s 11 `QCThreshold(...)` constructions (counted them), and
   `tests/test_api.py`'s `n_gated == 11` assertion.
4. **WS-03 (`b231068`, `6c38ab3`) + the verification milestone.** `ingest/nfcore.py::ingest_results_dir()`
   parses a real nf-core `results/` dir into `SampleMetrics`. The milestone: `openjdk` 17 installed
   into the machine-local `hackathon` conda env → `nextflow` 26.04 on `PATH` → the REAL germline
   pipeline ran on real GIAB HG002 (`completed=7 failed=0`, Q30 88.2%, coverage 54.2×, 553 variants)
   → the adapter parsed the SAME genuine `results/` (zero unmapped keys, Q30 0.8822, coverage
   54.23×, breadth 0.9924/0.9707) → the WS-06·PR2 Union → `run_gate` → **HOLD** on the structural
   `cluster_pf`-missing signal, matching the production driver's own parse exactly. **Grepped for
   production callers of `ingest_results_dir`** — found none outside `tests/`; `scripts/run_giab_pipeline.py`
   has its own, unrelated-by-name `SampleMetrics` dataclass (a local flat dataclass, NOT
   `models.SampleMetrics`) and still writes the frozen-five `qc_metrics.csv` → `QCMetrics`. **This is
   the load-bearing honesty finding of this sweep:** the two ingestion paths are proven equivalent on
   genuine data, but NOT unified — the adapter is gate-wired and gate-proven, not gate-called.
5. **WS-05 (`064bd0d`) — `RunbookSet`.** `RunbookKey(assay, sample_type, platform)` +
   binary-weight precedence + `GERMLINE_PANEL_RUNBOOK` as WS-01's first production consumer,
   verified end-to-end (the same sample PROCEEDs under `DEFAULT_RUNBOOK`, HOLDs under
   `DEFAULT_RUNBOOK_SET`). `evaluate_sample`/`aggregate_verdict` confirmed unchanged by direct read
   (ADR-0001 preserved).
6. **WS-07 Q1+Q2 (`9ace6ea`, `27289bd`) — partial.** Honest stub `next_steps=[]` + real `qc_reports`
   links; a wired `ask` endpoint (advisory, `AgentReply`, no verdict field — confirmed by reading
   `models.py`'s `AgentReply` and the test assertion `"verdict" not in payload`). Design items 1
   (richer agent context), 2 (semantic retrieval), 4 (demo default) from
   [ws-07-ai-earning-its-place.md](../../audit/gap_analysis/ws-07-ai-earning-its-place.md) are
   **design-only** — not landed this session; do not conflate Q1/Q2 with the plan's full scope.
7. **WS-09 (`1c57523`) — interim, not the original ask.** Submit-time 422 validation
   (`check_parse_contract` + `check_inputs_suppliable`) makes intake honestly REJECT a pipeline it
   can't gate, instead of running it to completion in Nextflow then dying at parse. **This is a
   different resolution than the workstream's own title** ("actually gate a non-germline pipeline")
   — it makes the failure mode honest and fast, it does not make intake capable of gating an
   arbitrary non-germline pipeline. Recorded as a Decision below.
8. **WS-08 interim (`8c8e2a1`) — access-control honesty, not full enforcement.** `AgentBinding` is
   confirmed (by reading `frontend/src/` + grepping `src/`/`api/` for a server-side binding model —
   none found) to be a **client-side-only advisory hint**; the real, server-enforced access control is
   node-scope + wire-role, and `logs` now correctly requires reviewer+ (was any viewer — a real
   access hole, now closed). Full per-agent binding enforcement stays a documented deferral.

### The Fable design spec (`271400c`) — a sibling artifact, not implementation

[docs/design/frontend/agent-triage-redesign-spec.md](../design/frontend/agent-triage-redesign-spec.md)
landed the same day from a parallel Fable design track — splits node-attached agents (QC-triage,
node-authoring) from global system agents (pipeline-repair, archivist, which move to a new
Analyze-group "System agents" destination) and replaces the static "Ask the agent" pop-out with one
persistent, draggable `AgentDockProvider` floating window. **Design spec only — no code landed for
it.** Registered here for completeness; no doc obligation beyond what its own commit already
satisfied (it is itself a `docs/design/` artifact).

### Docs swept, and why each was obligated (the Doc-update map trail)

1. **`CLAUDE.md` code map** (🔴/⚪, "files moved / a module added / a trigger rotted" +
   the cumulative effect of every 🟠 row below) — items 1a (CheckCoverage), 1b (ingestion contract
   Union), 1c (RunbookSet, target-band gate, corrected gated/ungated counts), a new item 1g
   (`ingest/nfcore.py`, with the honest gate-proven-not-gate-called framing), 3a/3b (stub honesty +
   `ask` endpoint), 4b.i (the verification milestone + WS-09 honesty), 4c (WS-08 access-control
   honesty note inside the existing Builder-agent-hardening paragraph).
2. **`docs/data/metric_registry.md`** (🟠, `runbook.py`/`metrics/` changes) — **a real drift fixed**:
   "10 gated / 10 ungated" was stale (now 11/9 after WS-06 Gap 2); the Wiring-status paragraph's
   "3 wired-but-ungated" list corrected to 2 (`variant.titv` moved to gated).
3. **`docs/data/qc_metrics.md`** (🟠, same trigger) — Gate 3 table's Ti/Tv row annotated as now
   genuinely gated; a new item 5 in Implementation status; the Ungated-observations list corrected;
   Labeling-honesty point 2 corrected ("DP-only" was no longer true); two new sections —
   **Runbook resolution — `RunbookSet`** and **Fail-closed rules — `QC-MISSING`/`QC-EXPECTED-<key>`**
   — giving WS-05/WS-01 their natural canonical home (this doc IS "the decided runbook").
4. **`docs/data/nf-core-conventions.md`** (catch-all — the doc that owns nf-core/MultiQC mapping
   conventions) — **a real drift fixed**: §4 claimed ingestion "today it still maps the flat
   `QCMetrics` fields... pending real MultiQC parsing"; that sentence was written before WS-03/06 and
   is now false. Corrected with the honest gate-proven/not-gate-called framing.
5. **`docs/data/schemas.md`** (🔴, `models.py` new/renamed fields) — a new blockquote for
   `SampleMetrics`/`RawObservation`/the `RunArtifacts.qc` Union; `DecisionCard`'s item 10 extended
   with `check_coverage?`.
6. **`docs/requirements/functional.md`** (🟠, new/changed `api/` capability) — REQ-F-104 (ask-agent
   endpoint), REQ-F-105 (fail-closed gate + `CheckCoverage`), REQ-F-106 (WS-09 submit-time
   validation); a new Notes/deferred item 10 naming the ingestion-adapter's proven-but-unwired
   status plus the WS-07/08/09 open items, so a reader of "what's built" doesn't have to cross-check
   the audit folder to find the honest caveats.
7. **`docs/quality/evaluation.md`** (🔴, unconditional — tests changed) — re-derived census (708/52,
   was 634/48), the per-file "By collected size" breakdown updated for every file whose count
   changed, the 8-skip breakdown updated (a new WS-10 real-path skip; the WS-03/06 real-path test
   explicitly called out as NOT among the skips and independently re-verified passing).
8. **`docs/planning/tasks.md`** (🔴, unconditional — tasks changed status/were created) — 9 new rows
   (T-144–T-152), one per workstream landing plus one for this sweep itself, each with Depends-on +
   the honest deferred-scope caveats; the "Last updated" header line summarized.
9. **`audit/gap_analysis/README.md`** — not a formal Doc-update-map row (the ToC's audit-folder note
   says the audit deliverable itself doesn't get "routine upkeep"), but this specific file
   **self-declares** as "the living tracker... update statuses as fixes land," and the branch's own
   prior commits already treated it that way (`fefa95a` updated it mid-session). Updated the
   "Current status" block, the per-workstream status table (WS-01/03/05/06 → done; WS-07/09 → 🟡
   with precise scope of what landed vs. what's still open), the P0–P3 roadmap checkmarks, and marked
   the "Parallel execution — wave board" section historical (the fan-out plan it describes did not
   happen — the work landed serially in one session instead).
10. **This journal.**

### Docs deliberately NOT touched (waivers)

1. **ADRs** — no new ADR authored, per the explicit instruction for this sweep. See Decisions below
   for two candidates flagged for the maintainer rather than unilaterally ADR'd.
2. **`docs/design/architecture.md`, `docs/design/data-platform-and-archivist.md`** — greped both for
   stale ingestion/runbook framing; found none (`RunbookSet`/`CheckCoverage`/the ingestion adapter
   simply aren't mentioned there yet, and the data-platform doc's relevant wishlist item, #10 in
   Appendix B, is about a DIFFERENT, broader `ArtifactRef`/persistence-level ingestion that WS-03
   didn't build — not contradicted). Waived: the 🟠 "api/ endpoint... new/changed capability" row
   didn't fire for these two docs specifically because none of this session's landings are a NEW
   `api/` endpoint surfaced in architecture.md's inventory except the `ask` endpoint, which is a
   one-line addition alongside five other advisory-agent endpoints already described generically
   there — not worth a bespoke architecture.md edit for one more agent verb.
3. **`docs/requirements/scope-and-wishlist.md`** — greped for stale claims (hardcoded next_steps,
   ingestion adapter, "all checks passed"); found none. Waived: no in-scope/wishlist boundary moved —
   this was gate-honesty remediation of already-in-scope capabilities, not a new capability crossing
   from wishlist to built.
4. **`docs/TABLE_OF_CONTENTS.md`** — waived: no canonical doc was created, moved, renamed, or had its
   status flag flipped (📝→🚧→✅); the journal directory's existing single row already covers a new
   dated journal file. The Doc-update map itself was re-read, not edited (no trigger rotted).

## Decisions

| Decision | Distilled to |
|---|---|
| `RunArtifacts.qc` becomes a transition **Union** (`QCMetrics \| SampleMetrics`), not a hard type flip — measured the blast radius first (every `.qc` reader already used only `.sample_id`/`metric_values_for`/`.model_dump`) so both shapes gate identically with zero existing-code breakage | [schemas.md](../data/schemas.md) (new `SampleMetrics`/`RawObservation` blockquote); no new ADR — an implementation-strategy choice under the existing [ADR-0015](../adr/ADR-0015-layered-data-contract.md) layered-contract umbrella, not a new architectural decision. **Flagged for the maintainer**: if a THIRD ingestion shape is ever added, this Union pattern (vs. a discriminated wrapper type) should get its own ADR. |
| WS-09 resolves "an authored pipeline intake can't gate" by **rejecting it at submit (422, before compute)**, not by generalizing the parser to dynamically support any pipeline shape — a deliberate, conservative scope choice (fail closed/fast over fail open/general) | [qc_metrics.md](../data/qc_metrics.md), `CLAUDE.md` code map item 4b.i, `audit/gap_analysis/README.md` WS-09 row (now explicitly labelled "interim, not the original ask"). **Flagged for the maintainer**: if "gate an arbitrary authored pipeline" becomes an actual product requirement (not just an audit-finding fix), the reject-vs-generalize tradeoff is ADR-worthy — right now it's under-the-radar as an implementation choice inside an already-existing WS-09 plan doc. |
| WS-08's per-agent binding enforcement gap gets an **honest interim** (real wire-role gating on `logs`, honest docstring correction) rather than either (a) building full server-side enforcement now or (b) leaving the over-claiming docstring in place | `CLAUDE.md` code map item 4c; already the established "close the seam or label it" invariant from the gap-analysis review §11 — not a new decision, an application of an existing one. No new ADR. |
| Gap 3 (WS-06 dup-rate) and the WS-10 fastp-regression concern are **REFUTED, not fixed** — the plan's proposed changes would have introduced NEW bugs (a 100× dup-rate inflation; a falsely-optional fastp port); verified by running the real tool, not by re-reading the plan | `audit/gap_analysis/README.md` (both call out "REFUTED" explicitly, sourced from the original commits); `docs/data/qc_metrics.md`/`metric_registry.md` carry no dup-rate change (silence is the correct outcome here). |
| This doc-sweep corrects a caught over-claim (test_e2e_pipeline.py rename) rather than let a plausible-sounding but ungrounded claim ship | This journal (§Method above); `quality/evaluation.md`'s `test_e2e_pipeline` entry. |

## Open questions & TODO

1. **Unify the two ingestion paths** (WS-03/06's proven adapter vs. the production driver's own
   parser) — currently proven-equivalent, not unified. A `POST /api/runs/ingest` endpoint or wiring
   the driver to call `ingest_results_dir` directly is the natural next step.
2. ~~**WS-02 (FREEMIX/NGSCheckMate) and WS-04 (GIAB concordance)** remain entirely unstarted~~ —
   **superseded same day, see the Addendum below**: both landed (offline/fixture-proven), but
   neither reached the real-data leg their own plans required.

## Addendum (same day, later session) — WS-02/WS-04 landed + a caught over-claim

**Focus.** A focused SWEEP for two commits landed after this entry's original close-out: `b8494f5`
(WS-02, `contamination.freemix`) and `072d8db` (WS-04, `concordance.snp_f1`). Docs-only, no code.

**What landed, grounded against code (not commit prose alone):**

1. Both metrics reuse the EXISTING generic `runbook.QCThreshold` / `rules._evaluate_metric` loop —
   no bespoke rule, no dispatch change (confirmed: `contamination.freemix`/`concordance.snp_f1` are
   ordinary entries in `runbook.py`'s `qc_thresholds` list, scored by the same code path as
   `variant.dp`). Registered/gated/ungated counts: 20/11/9 → **21/13/8**, re-verified against
   `tests/test_api.py::test_metric_catalog_lists_registered_metrics_and_gated_flag`
   (`n_registered==21`, `n_gated==13`) and a direct count of `metric_registry.yaml` entries +
   `runbook.py`'s `QCThreshold(...)` constructions.
2. **The honesty bar for this sweep: "gated + parser-wired, NOT pipeline-produced."** Real parsers
   (`ingest.nfcore._extract_verifybamid`/`_extract_happy`) exist and are tested (5 cases each,
   `test_ws02_contamination.py`/`test_ws04_concordance.py`), but the tools that PRODUCE the inputs
   (verifybamid2, hap.py) ship only as standalone Nextflow modules
   (`pipelines/optional_modules/{verifybamid2,happy}.nf`, real `script:`+`stub:`) — **not wired
   into any runnable pipeline.** `pipelines/germline/` is drift-locked byte-for-byte to the
   card-graph compiler's own output (`tests/test_nextflow_compile.py::test_committed_reference_pipeline_matches_the_compiler`),
   and the compiler has no input-gated-conditional concept for an optional add-on tool yet. This is
   the same honesty pattern already recorded for the WS-03 ingest adapter itself ("gate-wired but
   not gate-called") — one layer earlier in the pipeline.
3. **A real, un-planned drift caught mid-sweep, not just re-reading commit prose.** `rules.py`'s own
   `_EXPECTED_CATEGORIES` comment (and `docs/data/qc_metrics.md`/`schemas.md`, written during the
   original WS-01 PR2 work) claimed "contamination/identity flip to 'ran' automatically once WS-02
   wires FREEMIX (their first finding does it)." Verified directly with a constructed sample and a
   WARN-triggering FREEMIX value (`uv run python` against `rules.evaluate_sample` +
   `rules.compute_check_coverage`): the `contamination` category **still reports `not_examined`**.
   Root cause, read directly in `rules.py`: `_evaluate_metric`/`_evaluate_target_band` (the generic
   threshold loop ALL `QCThreshold`s share, including `contamination.freemix`) hardcode
   `category=Category.QC` on every finding they emit — never `Category.CONTAMINATION` — and
   `compute_check_coverage`'s `artifact_present[Category.CONTAMINATION]` stays hardcoded `False`
   regardless of what's present. So a `QC-FREEMIX` finding never lands in `found_categories` for
   that category. WS-02, as actually implemented (the existing generic loop, not the plan's
   proposed bespoke `CONTAM-001` rule), never could have flipped this — the original design comment
   was accurate about the PLAN, not about what shipped. Corrected in `qc_metrics.md` and
   `schemas.md`; the code itself is untouched (docs-only sweep) and this is now a named, tracked gap.
4. **Definition-of-Done cross-check against the workstreams' own plan docs.** Both
   `ws-02-identity-provenance.md` and `ws-04-giab-concordance.md` mark a **real-data acceptance
   test REQUIRED** for exactly this gap ("the ingestion/science gap where 'fixture green ≠ real run
   works' hid" / "the core science/ingestion claim"). Neither commit's own message claims one —
   both say "OFFLINE only — [tool] is never installed/run" outright. Per `audit/gap_analysis/README.md`'s
   own Definition of Done ("a workstream flips to done only with... its real-path test green on
   real GIAB — not a fixture"), WS-02/WS-04 do **not** qualify as ✅ done; corrected the tracker to
   🟡 interim rather than let a flat "not started" → "done" transition over-claim past what
   actually landed.
5. **A test census re-derivation caught a second, unrelated pre-existing drift**: `uv run pytest
   --collect-only -q` → 722 (was 708) + `git ls-files 'tests/*.py' | wc -l` → 54 (was 52). The delta
   is +5 (`test_ws02_contamination.py`) +5 (`test_ws04_concordance.py`) +4 — that last +4 traced to
   `test_card_readout.py` (17→21), from `61936d1` ("card_readout: render target_band thresholds,"
   WS-06 Gap 2 API wiring) — a commit that landed **after** this entry's original doc sweep and was
   never counted. Fixed in `quality/evaluation.md` alongside the WS-02/WS-04 delta. `uv run pytest
   -q` confirms **714 passed / 8 skipped** (722 − 8 = 714, no new skip — both new test files are
   pure offline stub+fixture).

## Decisions (addendum)

| Decision | Distilled to |
|---|---|
| WS-02/WS-04 land as **offline-only, generic-loop-scored** metrics rather than waiting for the real-data leg (verifybamid2/hap.py execution + pipeline wiring) — a deliberate incremental step, matching the plans' own phasing (parse/gate first, real-data acceptance as a separate, harder leg) | `audit/gap_analysis/README.md` (🟡 interim status, explicit Definition-of-Done gap named), [metric_registry.md](../data/metric_registry.md) (`‡` marker), `docs/planning/tasks.md` T-153/T-154. **Flagged for the maintainer**: wiring `pipelines/optional_modules/{verifybamid2,happy}.nf` into a runnable pipeline needs the compiler to gain an input-gated-conditional concept it doesn't have today — a real design decision, not a doc-only fix, if/when the real-data leg is prioritized. |
| The `CheckCoverage` contamination/identity category-flip is a genuine, real gap (not a doc typo) — corrected the docs to state what the code does, rather than what the original design comment intended, and left the code as a named follow-up rather than silently patching it inside a docs-only sweep | `qc_metrics.md`, `schemas.md`, `audit/gap_analysis/README.md` next-action item 2. No new ADR — an implementation gap inside an already-decided design (WS-01's `CheckCoverage`), not a new architectural decision. |

## Distilled into (addendum)

- [CLAUDE.md](../../CLAUDE.md) — code map items 1c (counts) + 1g (WS-02/WS-04 honesty note).
- [docs/data/metric_registry.md](../data/metric_registry.md) — 21/13/8 counts, `‡` marker, Wiring-status honesty paragraph.
- [docs/data/qc_metrics.md](../data/qc_metrics.md) — new item 6, corrected `CheckCoverage` claim, widened variant-gate-scope item 2.
- [docs/data/schemas.md](../data/schemas.md) — corrected `CheckCoverage` claim.
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-071 counts, new Notes item 11.
- [docs/quality/evaluation.md](../quality/evaluation.md) — census 708/52 → 722/54, `test_card_readout` drift fix.
- [docs/planning/tasks.md](../planning/tasks.md) — T-153, T-154.
- [audit/gap_analysis/README.md](../../audit/gap_analysis/README.md) — WS-02/WS-04 🟡 interim status, Definition-of-Done gap named, next-action items.
- This addendum.
3. **WS-07's Design items 1/2/4** (richer agent context, semantic retrieval, a deliberate live-Claude
   demo default) stay design-only.
4. **WS-08 full enforcement** (server-side `AgentBinding` persistence, run→executed-graph linkage,
   per-agent grant intersection, one real triage consumer) stays deferred.
5. **WS-09's dynamic non-germline gating** (parse off the compiled graph's `emit`s, rather than
   reject-at-submit) and the inert time-based scheduler both stay open.
6. Two implementation-strategy decisions flagged above (the `RunArtifacts.qc` Union pattern; the
   WS-09 reject-vs-generalize tradeoff) are candidates for a future ADR if either pattern recurs or
   becomes a genuine product requirement — not authored here per this sweep's explicit scope
   (docs-only, no unprompted ADRs).
7. A manual browser check of the RunDetail `CheckCoverage`/`QcReports` panels (flagged as owed in
   [2026-07-12-ws07-honest-next-steps.md](2026-07-12-ws07-honest-next-steps.md)) is still outstanding
   — no JS test runner exists in this repo to automate it.

## Distilled into

- [CLAUDE.md](../../CLAUDE.md) — code map items 1a/1b/1c/1g/3a/3b/4b.i/4c.
- [docs/data/metric_registry.md](../data/metric_registry.md) — gated/ungated counts + Wiring status.
- [docs/data/qc_metrics.md](../data/qc_metrics.md) — Ti/Tv target-band, new RunbookSet + fail-closed-rules sections.
- [docs/data/nf-core-conventions.md](../data/nf-core-conventions.md) — §4 ingestion-status correction.
- [docs/data/schemas.md](../data/schemas.md) — `SampleMetrics`/`RawObservation`/`CheckCoverage`.
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-104/105/106 + Notes item 10.
- [docs/quality/evaluation.md](../quality/evaluation.md) — re-derived test census.
- [docs/planning/tasks.md](../planning/tasks.md) — T-144–T-152.
- [audit/gap_analysis/README.md](../../audit/gap_analysis/README.md) — status table, roadmap, next-actions.
- [2026-07-12-gap-analysis-implementation.md](2026-07-12-gap-analysis-implementation.md) and
  [2026-07-12-ws07-honest-next-steps.md](2026-07-12-ws07-honest-next-steps.md) — both marked
  "Distilled into: this entry" (their own pending-integration TODO closed here).
