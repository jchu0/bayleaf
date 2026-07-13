# Gap Analysis — Remediation Home

This folder tracks the fixes surfaced by the **2026-07-11 adversarial design review**
([`design-review-2026-07-11.md`](design-review-2026-07-11.md)) — closing the gap between
what the product *claims* and what the code *wires*.

> **The through-line:** confident surfaces, thinner wiring. The bones are right
> (deterministic verdict, cited evidence, rules-decide/AI-narrates — ADR-0001);
> the work is wiring those surfaces down to reality without breaking the invariants.

## ▶ Current status & next action (resume here)

**Full remediation session, 2026-07-12** on branch `feat/gap-analysis-remediation` (off `main` @ `8e9658e`;
NOT merged/pushed — review then merge). Offline suite **722 tests / 54 files, 714 passed / 8 skipped**
(was 708/52, 700/8 passed/skipped; before that 634/48, 627/7); ruff + mypy clean at every commit; the pinned demo + HG002 verdicts are byte-identical
throughout. **Headline: the Nextflow verification pass this tracker used to flag as blocked now happened.**
`openjdk` 17 was installed into the machine-local `hackathon` conda env (`nextflow` 26.04 + the bioconda
toolchain now run on this machine); the REAL germline pipeline ran end-to-end on real GIAB HG002
(`completed=7 failed=0`, Q30 88.2%, coverage 54.2×, 553 variants), and the FULL alternate ingestion spine
(WS-03 adapter → WS-06 Union → gate) was proven against that SAME genuine output — see WS-03/WS-06 below and
[journal 2026-07-12-gap-analysis-remediation-verification.md](../../docs/journal/2026-07-12-gap-analysis-remediation-verification.md).

**Landed this session (each its own commit, test-first):**
1. ✅ **WS-10** (`efef163`) — fastp promoted-output regression **empirically REFUTED**. **RESOLVED.**
2. ✅ **WS-01** (`4d6acbf`, `118d8a5`, `98aca3d`, `14ea6fa`) — fail-closed gate, all four PRs landed:
   `QC-MISSING` (LIVE), `expected_metrics` mechanism (validated at construction), `CheckCoverage` (honest
   "N ran / M not examined" on the card + the RunDetail clean-card panel, replacing "all checks passed"),
   an HG002 real-data no-spurious-fire guard. **DONE** — the mechanism now has a live consumer (WS-05, below).
3. ✅ **WS-06** (`7b3f5ad`, `f4444be`, `cb56eb6`, `2033849`, `ce483ca`) — all six gaps closed: PR1 registry-keyed
   `SampleMetrics` ingestion contract, PR2 `RunArtifacts.qc` Union type flip (the gate consumes ingested
   metrics), Gap 2 `target_band` gate kind (`variant.titv` now genuinely gated — metric catalog 11/9, was
   10/10), Gap 3 (dup-rate) **REFUTED** — `0.0057` was already the correct percent, no change, Gaps 4-5 metric
   source/label honesty (mosdepth, not Picard; "Reads passing filter," not a demux concept), Gap 6 store
   consolidation (7 off-gate stores → one generic `JsonlStore`/`SqliteStore` base). **DONE.**
4. ✅ **WS-03** (`b231068`, `6c38ab3`) — `src/bayleaf/ingest/nfcore.py::ingest_results_dir()`, a real
   nf-core/MultiQC `results/` → `SampleMetrics` adapter, proven end-to-end on genuine HG002 output (zero
   unmapped keys, matching the driver's own parse, same HOLD verdict). **DONE, but with an honest unresolved
   gap:** the adapter is gate-wired and gate-proven, but **not gate-called** by any production path — intake
   still runs the driver's own separate, unrelated-by-name bespoke parser. Unifying them (a
   `POST /api/runs/ingest` endpoint) is explicitly deferred, not silently dropped.
5. ✅ **WS-05** (`064bd0d`) — `RunbookSet`/`RunbookKey` per-sample `(assay, sample_type, platform)` resolution;
   `GERMLINE_PANEL_RUNBOOK` is the first production consumer of WS-01's `expected_metrics`, verified
   end-to-end (PROCEED under `DEFAULT_RUNBOOK`, HOLD under `DEFAULT_RUNBOOK_SET`, same sample). **DONE.**
   Deferred, labelled: the Settings→runbook config-apply loop; the assay×tissue frontend UI.
6. 🟡 **WS-07** (`9ace6ea` Q1, `27289bd` Q2) — honest stub `next_steps` (`[]`, not boilerplate) + real
   `qc_reports` links; a wired `POST .../ask` endpoint (advisory, stub-grounded/Claude-answers-only-prose).
   **PARTIAL** — Design items 1 (richer per-agent artifact/cross-sample context), 2 (real semantic retrieval),
   and 4 (a deliberate live-Claude demo default) from [ws-07-ai-earning-its-place.md](ws-07-ai-earning-its-place.md)
   remain design-only, not landed this session.
7. 🟡 **WS-09** (`1c57523`) — submit-time 422 validation (parse-contract + input-parity) so an authored
   pipeline that can't be gated fails FAST instead of running to completion then dying. **INTERIM BY DESIGN,
   not the workstream's original ask** — it makes intake honestly REJECT a non-germline pipeline, not GATE
   one; "actually gate a non-germline pipeline" (dynamic parse off the compiled graph's `emit`s) stays open.
8. 🟡 **WS-08 (interim)** (`8c8e2a1`) — closed the log-read access hole (`grants=logs` now reviewer+, was any
   viewer) + corrected the "server-enforced binding least-privilege" over-claim to honest labeling. Full
   per-agent binding enforcement (needs server-side binding persistence + run→graph linkage) stays deferred —
   **unchanged status from before this session's later commits; still interim.**
9. 🟡 **WS-02 (interim)** (`b8494f5`) — `contamination.freemix` gated: a real `ingest.nfcore._extract_verifybamid`
   parser + an optional `runbook.QCThreshold` (gate 0.02 → WARN/HOLD, hard_fail 0.05 → CRITICAL/RERUN), scored
   through the EXISTING generic QC loop (no bespoke `CONTAM-001` rule as the plan proposed). **Does NOT meet this
   folder's own Definition of Done**: the plan's Test-First Contract marks a **real-data acceptance test REQUIRED**
   for this exact gap ("the ingestion/science gap where 'fixture green ≠ real run works' hid") —
   `test_verifybamid2_freemix_on_real_hg002` was never written; the landed test file
   (`tests/test_ws02_contamination.py`) is offline stub + fixture only, by the commit's own admission
   ("OFFLINE only — verifybamid2 is never installed/run"). Additionally `pipelines/optional_modules/verifybamid2.nf`
   is **not wired into any runnable pipeline** (the germline reference is drift-locked to the compiler's own
   output), so a live FREEMIX value isn't reachable without more work — see
   [metric_registry.md](../../docs/data/metric_registry.md) Wiring status. PROV-001 reframe, demux-share/
   undetermined gating, and the identity/contamination "NOT RUN" card readout from the plan are **not** landed.
10. 🟡 **WS-04 (interim)** (`072d8db`) — `concordance.snp_f1` gated the same way (generic loop, optional
    `QCThreshold`, gate 0.99 → WARN/HOLD, hard_fail 0.95 → CRITICAL/RERUN). **Same Definition-of-Done gap as
    WS-02**: the plan marks real-data acceptance REQUIRED ("the core science/ingestion claim"); the landed
    `tests/test_ws04_concordance.py` is offline stub + fixture only ("OFFLINE only — hap.py is never
    installed/run"). `pipelines/optional_modules/happy.nf` is likewise not wired into a runnable pipeline.
    SNP-recall/precision and INDEL metrics from the plan are not registered (F1 only).

**Real, un-planned finding from the doc sweep that landed WS-02/WS-04 (2026-07-12):** the
`CheckCoverage` "contamination category auto-flips to ran on the first finding" claim
(`rules.py`'s own `_EXPECTED_CATEGORIES` comment, and `docs/data/{qc_metrics,schemas}.md`) does
**not** actually hold now that WS-02 has landed — every `QCThreshold` finding (incl. `QC-FREEMIX`)
is tagged `Category.QC`, never `Category.CONTAMINATION`, and `compute_check_coverage`'s
`artifact_present[Category.CONTAMINATION]` stays hardcoded `False`. Verified directly (`uv run
python` against `rules.evaluate_sample`/`compute_check_coverage` with a WARN-triggering FREEMIX
value: `contamination` still reports `not_examined`). Corrected in `qc_metrics.md`/`schemas.md`;
not yet fixed in code.

**Next action (next session, same branch or a fresh one off it):**
1. **WS-02/WS-04 real-data acceptance leg** — the REQUIRED real-GIAB test neither workstream landed:
   run `verifybamid2` against the real HG002 panel BAM and `hap.py` against the real HG002 truth VCF,
   env-gated skip-safe like the other real-path checks. Blocked on wiring
   `pipelines/optional_modules/{verifybamid2,happy}.nf` into a runnable pipeline first (needs the
   compiler to gain an input-gated-conditional concept for an optional add-on tool — currently absent).
2. **`CheckCoverage` contamination/identity category-flip** — build what WS-01's original design
   comment promised: either tag the contamination/identity `QCThreshold` findings with their real
   `Category`, or add a bespoke `CONTAM-001`/`IDENT-001` rule (the WS-02 plan's original proposal),
   so `compute_check_coverage` actually flips to "ran" when FREEMIX/NGSCheckMate fires.
3. **WS-02 remainder** — PROV-001 independent-source reframe, demux-share/undetermined-reads gating,
   NGSCheckMate identity, and the identity/contamination "NOT RUN" card readout (plan §rules/§readout)
   are all still unbuilt.
4. **WS-07 remainder** — richer agent context, real semantic retrieval, a deliberate demo default (Design
   items 1/2/4 above).
5. **WS-08 completion** — server-side `AgentBinding` persistence + run→executed-graph linkage + per-agent
   grant intersection + one real triage consumer of `gather_node_observations`.
6. **WS-09 completion** — actually gate a non-germline authored pipeline (dynamic parse off compiled `emit`s),
   not just reject one at submit; fire a scheduled run at its time (currently inert-by-design).
7. **Unify the two ingestion paths** (WS-03/06) — wire `POST /api/runs` to `ingest_results_dir` (or a
   `POST /api/runs/ingest` endpoint) so the proven-equivalent adapter becomes the ONE parser, not a proven
   parallel one.

**Toolchain** (reusable agents, checked into `.claude/agents/`): `adversarial-reviewer` (find the gap) →
`test-writer` (freeze it red) → implement → re-run the guard. A workstream is ✅ **done** only when its Test-First
Contract is green **incl. the real-GIAB leg** (see Definition of Done below).

## How this folder works

- [`design-review-2026-07-11.md`](design-review-2026-07-11.md) — the source review (~35 findings, §1–§11).
- [`delta-review-2026-07-12.md`](delta-review-2026-07-12.md) — **adversarial sweep of the commits landed since**
  (the other session's Builder/execution/Nextflow arc). Reconciles the original findings (core **unchanged**;
  §7 partially closed; `tsc -b` closed) and adds **WS-08/09/10** — including the **URGENT** fastp regression.
- [`00-master-sequencing.md`](00-master-sequencing.md) — **the reconciled build order** across all 7 workstreams
  (dependency graph + phased A/B/C plan). Read this before implementing anything — several plans touch the
  same shared core and must land in order.
- **`ws-*.md`** — one **system-wide fix plan** per workstream (problem → exact edits → data-contract
  changes → cross-cutting impacts → tests → sequencing → risks). Each ends with a **Test-First Contract**:
  per surfaced gap, a red acceptance test that a scaffold can't pass + an anti-scaffold guard + (for
  adoption/ingestion/science gaps) a real-GIAB criterion + a binary Definition of Done.
- This README is the **living tracker**: status per workstream + the P0→P3 roadmap. Update statuses as fixes land.

**Fastest path to "real gate, not scaffold":** WS-01·PR1 → WS-06·PR1 → WS-03 → WS-02 (FREEMIX) — fail-closed
semantics + real ingestion + one genuine contamination check, landing on a shared contract. See the master doc.
**Status (2026-07-12): the first three legs are DONE** (WS-01 full, WS-06 full, WS-03 core+proven); **WS-02
(FREEMIX) landed offline/fixture-proven the same day, but NOT the REQUIRED real-data leg** (see below) — the
path to "real gate, not scaffold" is still one leg short of genuinely real.

## Workstreams

Each `ws-*.md` maps a coherent, mostly-independent slice of the review. Several touch the **shared core**
(`rules.py`, `runbook.py`, `models.py`, `parsers.py`, `synthesis/`) — the plans flag those dependencies so the
cross-cutting refactors sequence correctly (see the master ordering, filled in once the plans land).

| # | Workstream | Review § | Plan | Status |
|---|---|---|---|---|
| WS-01 | Fail-closed gate semantics (missing-QC→HOLD, "no findings"≠"all passed", expected-metric sets, "not examined" states) | §1 | `ws-01-fail-closed-gate.md` | ✅ **DONE** (`4d6acbf`, `118d8a5`, `98aca3d`, `14ea6fa`) — all four PRs landed |
| WS-02 | Real identity/provenance checks (FREEMIX/NGSCheckMate; PROV-001 → independent-source consistency + honest copy; undetermined-reads) | §2 | `ws-02-identity-provenance.md` | 🟡 **INTERIM** (`b8494f5`) — `contamination.freemix` gated + parser-wired (offline stub+fixture only); the plan's **REQUIRED real-data acceptance test is NOT landed** (Definition-of-Done gap, self-admitted in the commit); PROV-001/demux-gating/NGSCheckMate/NOT-RUN-readout are unbuilt |
| WS-03 | Real ingestion adapter (MultiQC/fastp/mosdepth `results/` → `RunArtifacts`; live registry keys; real ingress; run-store root) | §3 | `ws-03-ingestion-adapter.md` | ✅ **DONE, core + proven** (`b231068`, `6c38ab3`) — real-path acceptance test green on genuine HG002 output; **not yet gate-called by any production path** (deferred: unify with the driver's own parser) |
| WS-04 | Scientific validation (hap.py/vcfeval concordance vs the on-disk GIAB truth VCF; precision/recall as evidence) | §4 | `ws-04-giab-concordance.md` | 🟡 **INTERIM** (`072d8db`) — `concordance.snp_f1` gated + parser-wired (offline stub+fixture only); the plan's **REQUIRED real-data acceptance test is NOT landed** (same Definition-of-Done gap); recall/precision/INDEL metrics not registered |
| WS-05 | Config loop + multi-dimensional runbook (`RunbookSet(assay×sample_type×platform)`; typed override schema applied in `_active_runbook`; back the assay×tissue UI) | §5a/5c, §6a | `ws-05-config-and-runbook-dimensions.md` | ✅ **DONE (resolver half)** (`064bd0d`) — `RunbookSet` + `expected_metrics` production consumer verified end-to-end; the Settings config-apply loop + assay×tissue UI stay deferred |
| WS-06 | Registry-driven extensibility + metric correctness (registry-driven ingestion; two-sided/target-band gate type for Ts/Tv & uniformity; store consolidation; dup-rate / mean_coverage / % reads bugs) | §6b/c/d, §9 | `ws-06-registry-extensibility-and-metric-bugs.md` | ✅ **DONE, all 6 gaps** (`7b3f5ad`, `f4444be`, `cb56eb6`, `2033849`, `ce483ca`) — Gap 3 (dup-rate) REFUTED, not fixed |
| WS-07 | AI earning its place (agents get raw-artifact context or relabel as lookup; semantic retrieval; wire-or-delete the "Ask agent" chat; deliberate demo default) | §8, §5b | `ws-07-ai-earning-its-place.md` | 🟡 **Q1/Q2 landed** (`9ace6ea`, `27289bd`) — honest stub `next_steps` + a wired `ask` endpoint; Design items 1 (agent context), 2 (semantic retrieval), 4 (demo default) still design-only |
| **WS-08** | **Phase-4 observation binding — wire it real** (server-enforce grants [closes an access hole], one real consumer + UI, run→graph linkage, live-path de-id, real test) | delta §2 | [`delta-review-2026-07-12.md`](delta-review-2026-07-12.md) | 🟡 interim (`8c8e2a1`): logs→reviewer+ & honest labels; full enforcement deferred |
| **WS-09** | **Authored-pipeline execution — gate a *non-germline* pipeline** (parse off the compiled `emit`s or validate-at-submit; intake input-wiring parity with Builder-Run; scheduling) | delta §2, closes §7-tail | [`delta-review-2026-07-12.md`](delta-review-2026-07-12.md) | 🟡 **interim** (`1c57523`) — submit-time 422 validation (reject-not-run) landed; dynamic non-germline gating + scheduled auto-release stay open |
| **WS-10** | **fastp required-output regression — 🔴 URGENT** (`unpaired/failed_fastq` are mandatory outputs → may break the live golden path at step 1; add `Port.optional` or re-verify live) | delta §2 | [`delta-review-2026-07-12.md`](delta-review-2026-07-12.md) | ✅ RESOLVED (`efef163`) — regression refuted + guards |

Scope/over-build (§7) is **acknowledged and sanctioned** — tracked here as posture, not a fix workstream:
label the governance layers "not enforcement," defer Postgres×6 / HIPAA until a deployment needs them, and
rebalance effort toward the core (the review's effort-inversion finding). It informs sequencing, not a `ws-` plan.
**The Pipeline Builder specifically is a deliberate feature, not creep** — it addresses the Builder track's
own suggested "pipeline translator for bench scientists" idea (deviation was sanctioned); "it doesn't feed the
gate" is true but by design, its own value prop. See review §7 context note.

## Roadmap (from review §10)

| Priority | What | Workstream | Status |
|---|---|---|---|
| **P0** | Fail-closed: `missing-QC → HOLD` + honest "N checks ran / M not examined" prose | WS-01 | ✅ done |
| **P0** | One real identity/contamination check (VerifyBamID2 FREEMIX) end-to-end + "not examined" UI | WS-02 | 🟡 interim — gated + parser-wired, offline only; real-data leg (REQUIRED) not done; "not examined" UI not built (and, per this sweep, the `CheckCoverage` category flip does not actually fire even when a finding does) |
| **P0/P1** | MultiQC/fastp/mosdepth ingest adapter — let a real run in | WS-03 | ✅ done (core; not yet production-called — see WS-03 status above) |
| **P1** | GIAB concordance (hap.py/vcfeval) → precision/recall on the card | WS-04 | 🟡 interim — F1 gated + parser-wired, offline only; real-data leg (REQUIRED) not done; recall/precision not registered |
| **P1** | Metric correctness (dup-rate scale, `mean_coverage`/`% reads` relabel) | WS-06 | ✅ done (dup-rate REFUTED as a non-bug; mean_coverage/% reads fixed) |
| **P1/P2** | Close (or honestly label) the Settings→runbook loop | WS-05 | 🟡 labelled, not closed — `_active_runbook` still one run-level `Runbook`; `RunbookSet` resolution itself is done |
| **P2** | Multi-dimensional `RunbookSet`; registry-driven metric adds; two-sided gate type | WS-05, WS-06 | ✅ done |
| **P2** | AI honesty (more agent input or relabel; demo default) | WS-07 | 🟡 partial — Q1/Q2 done; richer context/retrieval/demo-default open |
| **P3** | Right-size scope; honest governance labels; rebalance toward core | §7 (posture) | ☐ posture only, not a fix workstream (unchanged) |

## Parallel execution — wave board

**Status (2026-07-12): this plan is now HISTORICAL, not forward-looking** — Wave 0 (WS-06·PR1,
WS-05·step1, WS-01·PR1) and most of Wave 1/2 (WS-03, WS-06 remainder, WS-07 Q1/Q2, WS-09 interim)
landed serially in one session rather than across the fanned-out branches this board describes; the
actual sequencing is recorded commit-by-commit above and in
[journal 2026-07-12-gap-analysis-remediation-verification.md](../../docs/journal/2026-07-12-gap-analysis-remediation-verification.md).
Kept below for the dependency reasoning (still accurate) — WS-02/WS-04 landed interim (offline
only, real-data leg still open) and that remaining leg could still use this parallel structure.

Parallelism is bounded by **file-level contention**: nearly every workstream edits
`rules.py`/`runbook.py`/`models.py`/`parsers.py`, so this runs in **waves**, not a flat 7-way fan-out.
Dependency detail in [`00-master-sequencing.md`](00-master-sequencing.md).

**Wave 0 — Foundation (serial, ~3 PRs — the critical-path bottleneck).** The shared-core *contracts* everything
rebases onto; these edit the same core files so they can't parallelize with each other:
- **WS-06·PR1** ingestion contract · **WS-05·step1** `RunbookSet`/per-sample resolution · **WS-01·PR1** fail-closed rules.

**Wave 1 — Parallel fan-out (~5–6 concurrent branches, once Wave 0 is on `main`).** Disjoint files → run together:

| Lane | Branch | Touches (disjoint) |
|---|---|---|
| A | WS-07 (AI) | `synthesis/context.py` (new), `triage/`, ask-endpoint, `AgentComposer` |
| B | WS-06·PR4 (store consolidation) | `*_store.py` |
| C | WS-03 (nf-core adapter + ingress) | `ingest/` (new), `intake.py`, run-root |
| D | WS-04 (concordance) | additive: record/parser/rule + driver |
| E | WS-05·tail (override schema, config loop, UI) | `settings.py`, `api/main.py`, frontend |
| F | WS-01·tail (CheckCoverage, prose, NOT-RUN UI) | synthesis, `card_readout`, frontend |

**Wave 2 — Serial core-thread (the long pole; runs *beside* Wave 1).** Heavy `rules.py`/`parsers.py` contention —
same owner, sequenced: **WS-02** (PROV-001 / FREEMIX / demux) → **WS-06·PR2-3** (parser rewrite, gate types, metric bugs).

**Critical path:** Foundation → WS-02 → WS-06·core. ~60–70% of the effort parallelizes beside it.

**Merge discipline** (continuous-integration-to-`main`): base every branch off `origin/main`; **own git worktree
per branch** (no collision with each other or a concurrent instance sharing the checkout); small PRs;
**merge on green DoD incl. the real-GIAB leg**; Wave-1 branches rebase on `main` after Wave 0. CI runs `tsc -b` +
the acceptance tests.

## Invariants the fixes must preserve (review §11)

1. **Rules decide, AI narrates** (ADR-0001) — the verdict stays a deterministic function of rule findings.
2. **Cited evidence** — every new rule/check (FREEMIX, concordance, presence) authors its own `Evidence`.
3. **Fail-safe** — every change pushes *further* toward failing closed, never toward the LLM deciding.
4. **Honest labeling** — close the seams or label them in-product; never paper over.

## Definition of Done — how a fix counts as *real* (not scaffold)

The whole point of this folder: a workstream is ✅ **done** only when the wiring is *proven*, never when a PR
merges. Each `ws-*.md` Test-First Contract makes that binary.

**Two kinds of "end-to-end" — you need both, named for what they actually prove:**

- **Contract E2E** — mocks the compute boundary; proves the API/routing/report *plumbing connects*. Fast,
  deterministic, worth keeping. ⚠️ **`tests/test_e2e_pipeline.py` is this — relabel it.** It monkeypatches the
  Nextflow/subprocess boundary to no-ops and runs the bespoke fixture format, so it validates the
  approval-gate/report **contract**, NOT that a real pipeline runs or real tool outputs get checked. Calling it
  "end-to-end" let "it passes E2E" quietly become "the system works" — the same confident-surface trap the
  review found, turned on our own verification. Rename to `test_pipeline_contract.py` (or add a module docstring)
  so it stops implying more than it proves.
- **Real-path acceptance** — un-stubs the driver, runs **real GIAB HG002**, asserts the *intended* outcome
  (a contaminated sample escalates via real FREEMIX; a real `results/` dir produces a card; concordance
  actually appears). Slow, env-gated (skip-safe, like the live-Nextflow tests). **This is the only thing that
  proves the wiring is real** — and it's structurally what the old E2E could never satisfy.

**A workstream flips to ✅ done only with:**

1. a linked commit, and
2. its Test-First Contract acceptance + guard tests green, and
3. for any adoption / ingestion / science gap: its **real-path test green on real GIAB — not a fixture**, and
4. for anything deliberately deferred (e.g. WS-05's config loop): the honest in-product **"not applied" label**
   present instead of a silent claim.

Never "done on vibes," never "done because it merged."

**Fix the verifier itself, or none of the above runs:** ✅ **`tsc -b` is now wired into pre-push** (commit
`e40784c`, 2026-07-12) — the frontend type-check no-op is closed. Still open: the **acceptance + guard tests**
must also run in pre-push/CI (esp. the env-gated real-GIAB legs), or the anti-scaffold guards are themselves scaffold.

---

_Created 2026-07-11 (MST); statuses last updated 2026-07-12 (MST) — see [journal
2026-07-12-gap-analysis-remediation-verification.md](../../docs/journal/2026-07-12-gap-analysis-remediation-verification.md).
Tracker — keep statuses current; a workstream is done only when its Test-First
Contract (incl. the real-GIAB leg where required) is green, per the Definition of Done above._
