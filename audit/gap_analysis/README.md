# Gap Analysis — Remediation Home

This folder tracks the fixes surfaced by the **2026-07-11 adversarial design review**
([`design-review-2026-07-11.md`](design-review-2026-07-11.md)) — closing the gap between
what the product *claims* and what the code *wires*.

> **The through-line:** confident surfaces, thinner wiring. The bones are right
> (deterministic verdict, cited evidence, rules-decide/AI-narrates — ADR-0001);
> the work is wiring those surfaces down to reality without breaking the invariants.

## ▶ Current status & next action (resume here)

**As of 2026-07-12:** planning is COMPLETE and test-gated — nothing left to plan. Git on `main` @ `d530dfc`,
clean tree (the other session finished + merged). The delta sweep is done ([`delta-review-2026-07-12.md`](delta-review-2026-07-12.md)):
the original core findings are **unchanged**, `tsc -b` is **closed**, §7 is **partially closed**, and three new
workstreams (WS-08/09/10) were added.

**Next action — implement, test-first, on a branch off `main`:**
1. **🔴 WS-10 (fastp required-output regression) FIRST** — smallest + urgent; may break the live demo at step 1.
   `test-writer` writes the `optional`-port guard + a real-GIAB fastp check, then the one-line `Port.optional` fix.
2. **WS-01 (fail-closed)** — now higher priority (authored pipelines route *real* verdicts through the still-open gate).
3. Then the fastest path: **WS-06·PR1** (ingestion contract) → **WS-03** (nf-core adapter) → **WS-02** (FREEMIX).

**Toolchain** (reusable agents, checked into `.claude/agents/`): `adversarial-reviewer` (find the gap) →
`test-writer` (freeze it red) → implement → re-run the guard. A workstream is ✅ **done** only when its Test-First
Contract is green **incl. the real-GIAB leg** (see Definition of Done below). Model: fable available until EOD
2026-07-12 for design/UI only; everything else Opus.

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

## Workstreams

Each `ws-*.md` maps a coherent, mostly-independent slice of the review. Several touch the **shared core**
(`rules.py`, `runbook.py`, `models.py`, `parsers.py`, `synthesis/`) — the plans flag those dependencies so the
cross-cutting refactors sequence correctly (see the master ordering, filled in once the plans land).

| # | Workstream | Review § | Plan | Status |
|---|---|---|---|---|
| WS-01 | Fail-closed gate semantics (missing-QC→HOLD, "no findings"≠"all passed", expected-metric sets, "not examined" states) | §1 | `ws-01-fail-closed-gate.md` | ✅ planned |
| WS-02 | Real identity/provenance checks (FREEMIX/NGSCheckMate; PROV-001 → independent-source consistency + honest copy; undetermined-reads) | §2 | `ws-02-identity-provenance.md` | ✅ planned |
| WS-03 | Real ingestion adapter (MultiQC/fastp/mosdepth `results/` → `RunArtifacts`; live registry keys; real ingress; run-store root) | §3 | `ws-03-ingestion-adapter.md` | ✅ planned |
| WS-04 | Scientific validation (hap.py/vcfeval concordance vs the on-disk GIAB truth VCF; precision/recall as evidence) | §4 | `ws-04-giab-concordance.md` | ✅ planned |
| WS-05 | Config loop + multi-dimensional runbook (`RunbookSet(assay×sample_type×platform)`; typed override schema applied in `_active_runbook`; back the assay×tissue UI) | §5a/5c, §6a | `ws-05-config-and-runbook-dimensions.md` | ✅ planned |
| WS-06 | Registry-driven extensibility + metric correctness (registry-driven ingestion; two-sided/target-band gate type for Ts/Tv & uniformity; store consolidation; dup-rate / mean_coverage / % reads bugs) | §6b/c/d, §9 | `ws-06-registry-extensibility-and-metric-bugs.md` | ✅ planned |
| WS-07 | AI earning its place (agents get raw-artifact context or relabel as lookup; semantic retrieval; wire-or-delete the "Ask agent" chat; deliberate demo default) | §8, §5b | `ws-07-ai-earning-its-place.md` | ✅ planned |
| **WS-08** | **Phase-4 observation binding — wire it real** (server-enforce grants [closes an access hole], one real consumer + UI, run→graph linkage, live-path de-id, real test) | delta §2 | [`delta-review-2026-07-12.md`](delta-review-2026-07-12.md) | ✅ planned (delta) |
| **WS-09** | **Authored-pipeline execution — gate a *non-germline* pipeline** (parse off the compiled `emit`s or validate-at-submit; intake input-wiring parity with Builder-Run; scheduling) | delta §2, closes §7-tail | [`delta-review-2026-07-12.md`](delta-review-2026-07-12.md) | ✅ planned (delta) |
| **WS-10** | **fastp required-output regression — 🔴 URGENT** (`unpaired/failed_fastq` are mandatory outputs → may break the live golden path at step 1; add `Port.optional` or re-verify live) | delta §2 | [`delta-review-2026-07-12.md`](delta-review-2026-07-12.md) | ✅ planned (delta) |

Scope/over-build (§7) is **acknowledged and sanctioned** — tracked here as posture, not a fix workstream:
label the governance layers "not enforcement," defer Postgres×6 / HIPAA until a deployment needs them, and
rebalance effort toward the core (the review's effort-inversion finding). It informs sequencing, not a `ws-` plan.
**The Pipeline Builder specifically is a deliberate feature, not creep** — it addresses the Builder track's
own suggested "pipeline translator for bench scientists" idea (deviation was sanctioned); "it doesn't feed the
gate" is true but by design, its own value prop. See review §7 context note.

## Roadmap (from review §10)

| Priority | What | Workstream | Status |
|---|---|---|---|
| **P0** | Fail-closed: `missing-QC → HOLD` + honest "N checks ran / M not examined" prose | WS-01 | ☐ |
| **P0** | One real identity/contamination check (VerifyBamID2 FREEMIX) end-to-end + "not examined" UI | WS-02 | ☐ |
| **P0/P1** | MultiQC/fastp/mosdepth ingest adapter — let a real run in | WS-03 | ☐ |
| **P1** | GIAB concordance (hap.py/vcfeval) → precision/recall on the card | WS-04 | ☐ |
| **P1** | Metric correctness (dup-rate scale, `mean_coverage`/`% reads` relabel) | WS-06 | ☐ |
| **P1/P2** | Close (or honestly label) the Settings→runbook loop | WS-05 | ☐ |
| **P2** | Multi-dimensional `RunbookSet`; registry-driven metric adds; two-sided gate type | WS-05, WS-06 | ☐ |
| **P2** | AI honesty (more agent input or relabel; demo default) | WS-07 | ☐ |
| **P3** | Right-size scope; honest governance labels; rebalance toward core | §7 (posture) | ☐ |

## Parallel execution — wave board

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

_Created 2026-07-11 (MST). Tracker — keep statuses current; a workstream is done only when its Test-First
Contract (incl. the real-GIAB leg where required) is green, per the Definition of Done above._
