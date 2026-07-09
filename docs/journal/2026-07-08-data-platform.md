# Journal — 2026-07-08 (MST) — Data platform, real-GIAB gate, design captures, export slice

| Field | Value |
|---|---|
| **Focus** | Second session of the day: put the metric registry on the critical path, run **real** GIAB through the full gate, merge the frontend/API seams, capture the data-platform + variant + output-layout designs, and build the `/api/export` slice. |
| **Participants** | James Hu, Claude Code |
| **Outcome** | Real GIAB HG002 clears every measurable gate; metric registry on the critical path; notify/Slack live; three design docs + Appendix D captured via adversarial workflows; `GET /api/export` (CSV/JSONL/Parquet) shipped. |

## Discussion

**Discipline held:** build → verify green (ruff/mypy/pytest) → adversarial read-only
review (Explore agents, never write-enabled) → fold fixes → merge → push. Parallel
worktree agents for disjoint clusters; central coordination for cross-cutting files.

**Metric registry on the critical path (T-024/T-025).** Metrics now normalize to canonical
decimals **before** the QC gate thresholds them: runbook gates in canonical units keyed on
`our_key`; rules gate on `normalized_value`; display renders back via `registry.denormalize`.
Verdicts byte-identical at every step. The units contract (metrics cross boundaries as
`normalized_value`, registry is the single unit authority) is the load-bearing invariant here.
Documented in `schemas.md` §6 + **ADR-0015** (layered data contract).

**Notify port + Slack (T-015b).** `NotifyPort` + StubNotifier + SlackNotifier wired into
`run_gate` as an off-by-default `notifier=` hook emitting `notification.emitted` events;
per-verdict, evidence-cited messages; live send behind `PIPEGUARD_SLACK_LIVE`, verified
end-to-end against a real workspace.

**Real GIAB through the FULL gate (T-017 → T-002b).** `scripts/gate_giab.py`: `mosdepth --by`
for coverage, then `samtools fastq | fastp` for real Q30/dup/reads-PF. HG002 = Q30 88.2%,
dup 0.006%, reads-PF 99.3%, coverage 55.8× → **PROCEED**, registry-normalized exactly like a
mock run — the units contract proven on real data. cluster-PF is a run-level SAV metric, not
gated (would be a spurious "missing").

**Frontend + API seams merged (T-027).** Two parallel worktree agents (frontend metrics panel
+ polish; API `/api/runbook` + Prometheus `/metrics`), both adversarially reviewed. Folded
Medium/Low fixes: Settings borderline-band was rendering a relative fraction as an absolute
unit (±0.03x vs the real ±0.9×); canonical→display gate formatting (0.85 → 85%); `units_note`
on `/api/runbook`; robustified the Prometheus test.

**Design captures (adversarial workflows — the big fan-outs).** Ran four multi-agent workflows
(design perspectives → adversarial critiques → synthesis), fact-checked each before landing:
- **Data platform + archivist** → `design/data-platform-and-archivist.md`. Key reframe: the
  queryable platform is ~80% already built (event ledger → projector → SqliteRepository +
  `MetricValue`); BUILD-NOW is just `/api/export` + a RunsBrowser. A critique caught a real
  trap: durable writes into the `@lru_cache`'d `_evaluate` would corrupt the append-only ledger.
- **Agent-layer hub** → `design/agents.md` (roster + shared invariants + intake checklist).
- **NGS output-layout** → §3 expansion + Appendix C (tool-output catalog, `(VERIFY)`-tagged;
  BAM→CRAM saves only ~20–40% lossless; `pct_reads_identified` is a fastp pass-filter rate,
  not a barcode-ID metric).
- **Variant-gate substrate** → Appendix D. Framing contract (HG002 is a benchmark genome, not
  a patient; ClinVar is fixture-selection/annotation only, never a runtime gate input); layered
  CMRG-spine panel; two-truths/two-BEDs routing; `isec`-restrict-to-gradeable-BED-first fix.

**Export slice (T-030 backend).** `GET /api/export` over the in-memory cards: `grain=decision`
(narration + findings) / `grain=feature` (the ML corpus, one `MetricValue`/row). `format=csv|
jsonl|parquet` (pyarrow optional extra, lazy import, 501 fallback). Every row carries `origin`
(tagged the mock runs contrived/synthetic); `submitted_by` never emitted; `X-PipeGuard-Export-
Source: live-recompute` honesty label.

## Decisions

| Decision | Distilled to |
|---|---|
| Layered immutable data contract (units, content-hash, event-authoritative) | [ADR-0015](../adr/ADR-0015-layered-data-contract.md), `schemas.md` |
| Metric registry on the critical path; verdicts byte-identical | T-025, `metric_registry.md` |
| Real GIAB through the full gate; cluster-PF not gated | T-002b, `gate_giab.py` |
| Data-platform build-now = `/api/export` + RunsBrowser; agents spec-only | design doc "Decisions taken" (D1–D14) |
| Postgres/pgvector as the single end-goal store; Parquet export now; DuckDB optional | D3, wishlist #19 |
| BAM→CRAM archiving + full archive contents incl. decision cards | D8, design §3 |
| Variant-gate substrate design (panel + pluggable caller); gate rules stay Phase 2 | T-031, Appendix D |

## Open questions & TODO

- **T-030 frontend half** still owed: `started_at` on `RunSummary` + the `/runs` RunsBrowser
  (month bucketing, filter bar, per-run + batch Export download).
- **Build-now-if-time:** `gate_giab.py --call` (bcftools) + EVAL-030 (approved if time remains).
- **Deferred:** config-for-paths loader (T-032), pipeline run-state/mission-control (T-033),
  `pct_reads_identified` rename (T-034). Agent-layer buildout tomorrow.
- **Meta:** journal was dropped for ~72 commits — fixed via an always-loaded **Doc-update map**
  (ToC), a read-lean/write-complete clause + session-end checklist (CLAUDE.md), and a soft
  pre-push journal nudge. This entry is the backfill.

## Distilled into

- ADRs/docs: [ADR-0015](../adr/ADR-0015-layered-data-contract.md),
  [`design/data-platform-and-archivist.md`](../design/data-platform-and-archivist.md),
  [`design/agents.md`](../design/agents.md); refreshed
  [`planning/tasks.md`](../planning/tasks.md) (T-024→T-034),
  [`requirements/scope-and-wishlist.md`](../requirements/scope-and-wishlist.md),
  [`TABLE_OF_CONTENTS.md`](../TABLE_OF_CONTENTS.md), [`demo/one-pager.md`](../demo/one-pager.md).
- Code: `src/pipeguard/{metrics,notify,models,engine,rules,runbook}`, `api/main.py`
  (runbook/metrics/export), `frontend/` (MetricsPanel + polish), `scripts/gate_giab.py`.
