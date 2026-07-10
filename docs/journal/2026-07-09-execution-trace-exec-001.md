# Journal — 2026-07-09 (MST) — Execution-trace ingestion (EXEC-001)

| Field | Value |
|---|---|
| **Focus** | Close the pipeline-fixer's structured-issue gap: pull structured issues from an actual pipeline executor's trace (not only PipeGuard's own gate findings) and feed them to the pipeline-repair agent (#2). |
| **Outcome** | New gate rule **EXEC-001**: a Nextflow/nf-core `trace.txt` is READ on the gate path; a failed task → a structured Finding → RERUN → flows to the repair agent via the existing recurring-signature rollup. Commit e79a319; **359 tests**, mypy + ruff clean; the pinned verdicts stayed byte-identical. |

## Discussion

**Why, and the honest split.** The user asked whether the backend pulls structured issues *from
the pipeline* for the fixer. Answer: **yes** for PipeGuard's own gate `Finding`s (already
structured/cited, incl. the log-marker `PIPE-001`), **no** for an external *executor's* structured
trace (there was no ingestion — `SourceKind.EXECUTION_TRACE` was reserved but unpopulated, and
`PIPE-001` only grepped a free-text `pipeline.log`). This built the missing (b) piece: read a real
Nextflow/nf-core execution trace.

**The key realization: this isn't new architecture.** `PIPE-001` already sits on the gate path
reading `pipeline.log` and already uses `SourceKind.EXECUTION_TRACE`. So EXEC-001 is its
**structured sibling** — the same on-gate pattern, but a real task table (`trace.txt`: `tag`,
`status`, `exit`) instead of a log grep. Low architectural risk.

**Two invariants held, deliberately.** (1) **Compose ≠ execute** (ADR-0001/0003): EXEC-001 *reads*
a trace the run produced and dropped in the run dir — exactly as the gate already reads
`qc_metrics.csv` — it never runs a process. The full external-orchestrator Run hand-off (T-057)
stays deferred. (2) **Existing verdicts byte-identical**: the pinned demo runs have no `trace.txt`,
so EXEC-001 never fires on them; the demo-pinned tests pass unchanged.

**The maintainer decision: on-gate.** A failed process becomes a first-class Finding driving the
sample to **RERUN** (consistent with the runbook's operational-failure → RERUN policy), rather than
an off-gate signal that only informs remediation. This makes a process failure show up in the
verdict *and* the recurring-signature rollup that feeds the repair agent.

**The one build subtlety.** Adding a 9th `FailureMode` (`PROCESS_FAILURE`) shifted the scale run's
deterministic mode auto-spread and broke `mock_run_scale_30`'s byte-reproducibility. Fixed by
**excluding `PROCESS_FAILURE` from the auto-spread** — a trace failure needs the extra `trace.txt`
artifact, so it's an opt-in mode, not part of the standard five-artifact QC-failure spread. The
committed scale run is byte-identical again. `trace.txt` is emitted only for runs that actually
have a process failure, so no existing fixture is perturbed.

## Decisions

| Decision | Distilled to |
|---|---|
| Ingest a structured Nextflow/nf-core execution trace on the gate path; a failed task = EXEC-001 (PIPE-001's structured sibling) → RERUN | [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [qc_metrics.md](../data/qc_metrics.md), [schemas.md](../data/schemas.md) |
| Place it ON-GATE (a failed process is first-class → RERUN), preserving compose ≠ execute (reads a trace, never runs) | [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md); this journal |
| `PROCESS_FAILURE` is excluded from the scale auto-spread (needs the opt-in `trace.txt` artifact); committed scale run stays byte-identical | `synthetic/scale.py`; [test_synthetic.py](../../tests/test_synthetic.py) |

## Open questions & TODO

1. **`.command.err` enrichment** — EXEC-001 cites the trace's process + exit code; reading the
   per-task `.command.err` stderr for a richer evidence snippet needs the Nextflow work dir (not the
   run dir), so it's a deferred enrichment.
2. **The external Run hand-off** (T-057) that would *produce* a live trace remains deferred and must
   preserve compose ≠ execute (emit + hand off, never run).
3. **A committed trace-failure demo run** was deliberately not added (avoids a 5th dashboard run
   mid-frontend-redesign); the path is proven by `tests/test_execution_trace.py` and a run is one
   generator call away (`SampleSpec(mode=PROCESS_FAILURE)`).

## Distilled into

- [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md) · [qc_metrics.md](../data/qc_metrics.md) · [schemas.md](../data/schemas.md) · [provenance.md](../data/provenance.md)
- [evaluation.md](../quality/evaluation.md) (census) · [scope-and-wishlist.md](../requirements/scope-and-wishlist.md) · [functional.md](../requirements/functional.md) · [data/README.md](../../data/README.md)
- [tasks.md](../planning/tasks.md) T-061 · [agents.md](../design/agents.md) roster #2
