# Master Sequencing — reconciling the 7 workstreams

The 7 `ws-*.md` plans were designed independently; several touch the **same shared core**
(`rules.py`, `runbook.py`, `models.py`, `parsers.py`, `synthesis/`). This doc reconciles their
stated dependencies into one order that avoids rework. Source: each plan's *Cross-cutting impact & ordering*.

## Dependency graph (who must land before whom)

```
WS-06·PR1 (ingestion contract: RawObservation/SampleMetrics + registry-driven metric_values_for)
   └──> WS-03 (adapter EMITS that contract)  ──> WS-06·PR2-3 (parser rewrite, gate types, metric bugs)
                                              └─> WS-01 expected-metric checks get REAL data

WS-01·PR1 (fail-closed rules; expected_metrics added FLAT on Runbook)
   └──> WS-02 (new checks plug into WS-01's expected-set + NOT-RUN catalog)
   └──> WS-05 (RunbookSet LIFTS the flat expected_metrics onto per-profile — "a move, not a rename")

WS-05 (RunbookSet + per-sample resolution — deepest evaluate_run signature change)
   └──> WS-06 keeps only §6b/§6c (its QCThreshold work composes THROUGH RunbookSet)

WS-02 (new FREEMIX / NGSCheckMate / PROV rule_ids)
   └──> WS-07 (corpus + retrieval must cover the new signatures, or it collapses on them)

WS-04 (concordance) — independent core; only its Ts/Tv target-band gate waits on WS-06·PR3
```

## The four coordination rules that matter

1. **The ingestion contract is shared by WS-03 and WS-06 — land it once, first.** WS-06's PR1
   (`RawObservation`/`SampleMetrics` + the registry-driven `metric_values_for` loop, additive/back-compat)
   is the seam WS-03's nf-core adapter emits into. Do NOT let both define parallel ingestion shapes.
2. **WS-01 adds `expected_metrics` *flat*; WS-05 lifts it onto `RunbookSet` later.** WS-01 deliberately
   uses the same field name so the migration is a move. This lets the P0 fail-closed win land *now*
   without waiting on WS-05's deep signature change.
3. **Build the NOT-RUN / expected-category catalog once (WS-01 §1d), reuse it in WS-02 and WS-06.**
   When WS-02 wires FREEMIX/identity, those keys flip from `NOT RUN` to a real check with zero extra UI.
4. **The single `runbook.py` merge is disjoint if sequenced:** WS-05 edits `Runbook`/adds `RunbookSet`;
   WS-06 edits `QCThreshold` fields. Land WS-05's structure first; WS-06's richer thresholds compose through.

## Reconciled master order

### Phase A — P0 trust + adoption (fast, mostly back-compat)
| Step | Workstream | Why here | Blocks |
|---|---|---|---|
| A1 | **WS-01 · PR1** — `QC-MISSING` + `_check_expected_metrics` + `expected_metrics` (flat) | Smallest, highest-trust; no deps; verdict fails closed | — |
| A2 | **WS-06 · PR1** — ingestion contract (`RawObservation`/`SampleMetrics`, registry-driven loop, additive) | Foundation for real ingestion; byte-identical verdicts | unblocks WS-03 |
| A3 | **WS-03** — nf-core/MultiQC `results/` → `RunArtifacts` adapter + real ingress + configurable run-root | Lets a real run *in*; emits A2's contract | feeds WS-01/WS-06 real metrics |
| A4 | **WS-01 · PR2-4** — `CheckCoverage` object + honest prose + API + UI NOT-RUN cells | Makes "examined vs not examined" visible | — |
| A5 | **WS-02** — PROV-001 → independent-source (accessioning) consistency + honest copy; demux undetermined/share gating; **FREEMIX** end-to-end | The real provenance spine; plugs into A1/A4's expected-set + catalog | corpus for WS-07 |

### Phase B — P1 correctness + science
| Step | Workstream | Why here |
|---|---|---|
| B1 | **WS-06 · PR2-3** — registry-driven parser rewrite; two-sided/target-band gate type; metric bugs (dup scale, `mean_coverage`, `% reads`) | After WS-03's adapter; unblocks WS-02 identity keys + WS-04 Ts/Tv |
| B2 | **WS-04** — hap.py/vcfeval concordance vs GIAB truth → precision/recall as cited Evidence | Independent core; Ts/Tv band after B1 |

### Phase C — P2 architecture + honesty + AI
| Step | Workstream | Why here |
|---|---|---|
| C1 | **WS-05** — `RunbookSet(assay, sample_type, platform)` + per-sample resolution; typed override schema; `_active_runbook` applies approved overrides (or the honest "authoring only" label as a safe stopping point) | Deepest signature change; lifts A1's flat `expected_metrics`; backs the assay×tissue UI |
| C2 | **WS-06 · PR4** — store consolidation (one generic `JsonlStore`; defer Postgres) | Independent cleanup |
| C3 | **WS-07** — agents get raw-artifact + cross-sample context (or honest "curated lookup"); real retrieval; wire-or-delete the Ask-agent chat; deliberate demo default | After WS-02 (corpus signatures), WS-06 (metric shape), WS-03 (real cross-sample input) |

**Fastest path to "it's a real gate, not a scaffold":** A1 → A2 → A3 → A5-FREEMIX. That is fail-closed
semantics + real ingestion + one genuine contamination check — the three the review flagged P0 — landing on
top of each other with the contract shared, not re-litigated.

## Implementation note
These are **plans** (read-only design). Implementing any workstream is opt-in and should happen on its **own
worktree/branch** (like the review-queue fix) so it never collides with the concurrent `feat/custom-script-io`
instance sharing this checkout. Suggested branch-per-workstream: `feat/gap-ws01-fail-closed`, etc.
