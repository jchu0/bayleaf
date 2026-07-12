# Journal — 2026-07-12 (MST) — WS-07 Q1: honest decision-card next_steps

| Field | Value |
|---|---|
| **Focus** | Replace the stub synthesizer's hardcoded per-verdict `next_steps` boilerplate with an honest deterministic fallback; surface the real QC artifacts (reports + metric readout) instead. |
| **Participants** | Claude (subagent, isolated worktree off `feat/gap-analysis-remediation`) |
| **Outcome** | Stub emits `next_steps=[]` (no fabricated advice); the API's card readout now surfaces the run's `fastp.html` / `multiqc_report.html` reports when present + honest absence otherwise; frontend renders a QC-reports block. Verdict byte-identical (ADR-0001). |

## Discussion

### The problem (review §8)
`synthesis/stub.py` carried a `_NEXT_STEPS[verdict]` table — hardcoded per-verdict
prose ("Release sample to downstream analysis.", "Requeue the sample…", etc.) emitted
on the $0 default path. That is dishonest filler: the stub cannot know a run's real
remediation, so any advice it printed *reads like* a recommendation but stands on
nothing. It is the advisory analogue of letting a heuristic set the verdict — which
ADR-0001 forbids.

### The fix (two honest halves)
1. **Core (`synthesis/stub.py`)** — dropped `_NEXT_STEPS`; the stub now returns
   `next_steps=[]`. The honest AI-off default (ADR-0006) fabricates nothing. The live
   Claude path (`synthesis/claude.py`) is unchanged — it still authors real, grounded,
   run-specific `next_steps`, so "Claude on ⇒ suggestion box populated" holds.
2. **API (`api/card_readout.py`)** — the card readout (the suggestion surface the UI
   binds to) now also carries `qc_reports: list[QcReportLink]`. `get_card_readout`
   scans the run dir for `*.html` files whose stem carries a known QC-report token
   (`fastp` / `multiqc`), scoped so a sibling sample's per-sample report can't leak
   onto this card, and links each to the existing read-only inline artifact-serve
   endpoint (`GET /api/runs/{id}/artifacts/{name}`). No HTML report on disk (e.g. the
   CSV-only `mock_run_01`) ⇒ empty list = honest absence; the metric readout is always
   the standing fallback.
3. **Frontend (`RunDetail.tsx` + `types.ts`)** — a `QcReports` block renders the report
   links (split + brief densities) or an honest "no QC report artifact" line; the
   existing `next_steps` box already rendered only when non-empty, so the boilerplate
   box simply disappears in AI-off mode.

### content_hash finding (called out per the task)
`next_steps` **is** part of `DecisionCard.content_hash` (`models.py`), so changing the
stub's `next_steps` churns every stub card's hash. BUT no test pins a *literal* card
hash — `test_gate.py` only asserts `len(content_hash) == 64` + cross-sample
distinctness, and the ledger/persistence round-trip tests re-derive both sides from the
same stub. So there were **no golden fixtures to update**. The only pinned assertion
that moved was `test_gate.py::test_stub_card_is_grounded` (`assert s4.next_steps` →
`assert s4.next_steps == []`), updated in-commit.

### Verified
- Test-first: RED confirmed (stub still emitting boilerplate; `qc_reports` KeyError),
  then GREEN after impl. `tests/test_stub_next_steps.py` (anti-boilerplate + ADR-0001
  narration-independence) and 3 new `tests/test_card_readout.py` cases
  (present / sibling-excluded / honest-absence).
- `uv run ruff check` clean · `uv run mypy` clean (91 files) · `npx tsc -b` clean ·
  `npx oxlint` clean on touched files (pre-existing fast-refresh warnings elsewhere).
- Full suite: +5 new passing tests, **zero** new failures. The 4–6 failures in
  `test_pipeline_run.py` / `test_route_to_human.py` are pre-existing, order/filesystem
  flakiness (verified flaky on pristine HEAD: 4 then 6 across runs) in another agent's
  domain — unrelated to this change.

## Decisions

| Decision | Distilled to |
|---|---|
| Stub emits no fabricated `next_steps`; AI-off points at real QC artifacts + metric readout | ADR-0001 / ADR-0006 (strengthened, not changed) — pending canonical doc sweep |
| QC-report links live on the per-card `CardReadout` (the suggestion surface), scanned from the run dir, linking the existing serve endpoint | `api/card_readout.py` docstrings; pending `design/` sweep |

## Open questions & TODO

- **Canonical doc sweep owed** (deferred to integration to avoid collisions with
  parallel agents editing shared docs): CLAUDE.md code-map §1a (stub narration),
  any `design/` doc describing the decision-card next_steps, and possibly a note in the
  card-readout design. The Doc-update map row for `synthesis/` advisory changes points
  at `design/agents.md` + ADR-0001/0006 — a reviewer should confirm whether this
  honesty change warrants a line there.
- **`frontend/src/screens/ReviewQueue.tsx:172`** has its OWN per-verdict boilerplate
  string ("Requeue the sample to clear the rerun.") — a *different* surface (queue
  action hint, not the decision-card suggestion box), left in scope-discipline. Flagged
  for a follow-up if the maintainer wants the same honesty applied there.
- **Manual browser check owed** (no JS test runner): load a run's Decision cards in
  AI-off mode and confirm (a) no "Recommended next steps" boilerplate box, (b) the
  "QC reports" block shows links when `fastp.html`/`multiqc_report.html` exist and the
  honest-absence line for `mock_run_01`.

## Distilled into

- Pending — canonical distillation deferred to integration (see TODO). This entry is the
  archive of the WS-07 Q1 change.
