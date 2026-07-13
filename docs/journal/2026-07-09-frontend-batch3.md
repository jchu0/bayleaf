# Journal — 2026-07-09 (MST) — frontend maintainer-feedback batch 3 (doc sweep)

| Field | Value |
|---|---|
| **Focus** | SWEEP the Doc-update map for five commits landed on `main` (Submit execution boundary, decision-card three-gate readout, top-bar run switcher + F17, editable germline template, Monitoring signatures pagination); ground every claim against the actual diffs before touching docs. |
| **Participants** | doc-keeper subagent (Claude Code), maintainer (James Hu, prior session) |
| **Outcome** | 12 docs updated; 3 task-ID collisions in commit messages found and fixed with new, non-colliding rows; one commit's cited task id (T-072) does not actually match its scope, documented as a doc note rather than silently marked done. |

## Discussion

### Commits swept (newest → oldest)

1. `01ba673` — Pipeline builder: germline template → editable draft.
2. `17a3e56` — Top bar: searchable, capped run switcher + F17 real-status-dot fix.
3. `12ffa30` — Decision card: honest full three-gate readout.
4. `e77c2e6` — Samplesheet → run: `POST /api/runs` triggers the real GIAB pipeline (T-057).
5. `e5d5043` — Monitoring: paginate the recurring-signatures list.

For each, read the full `git show <sha>` diff (not just the message) before writing anything —
per the doc-keeper contract's "ground every claim in code" invariant. All five diffs matched
their commit-message descriptions; no behavioral drift between the message and the code. The
drift found was in the **task-ID bookkeeping**, not the implementation.

### Drift found: three commit messages cite already-used task IDs

`docs/planning/tasks.md` already has T-057 through T-072 fully allocated (`git log` confirms:
T-057 = "Tier-2 north-star backend," proposed/blocked, matching the ingest work; T-058 =
Pipeline-repair agent, done; T-059 = Archivist agent, done; T-060 = doc-keeper subagent, done;
T-072 = Monitoring per-run-rows pagination gap, open). Three of the five new commits cite IDs
that collide with unrelated, already-*done* rows:

- `12ffa30` cites "(T-058)" for the decision-card three-gate fix — T-058 is the Pipeline-repair
  agent. **New row: T-073.**
- `17a3e56` cites "(T-059)" for the top-bar run switcher — T-059 is the Archivist agent.
  **New row: T-074.**
- `01ba673` cites "(T-060)" for the editable germline template — T-060 is the doc-keeper
  subagent. **New row: T-075.**

I did not rewrite the commit messages (git history is not a doc-keeper concern, and rewriting
local history the user didn't ask to rewrite is out of scope). Instead each new task row's
description includes a "**Doc note:**" line naming the collision and the correct id, so a
future reader who finds "(T-058)" in `git log` and looks it up in `tasks.md` sees the redirect.

`e77c2e6` cites "(T-057)" correctly — T-057 was already the bundled "run submissions/ingest +
BaseSpace + triage chat + hand-off" row, and this commit ships the ingest/hand-off slice of it.
Updated T-057's status from `proposed` to `in-progress` and rewrote its description to separate
what shipped (ingest + hand-off, via `api/routers/intake.py`) from what's still wishlist
(BaseSpace connector, conversational multi-turn triage chat).

### Drift found: `e5d5043`'s cited task id describes a *different* gap than what it fixed

`e5d5043`'s message cites "(T-072)." Reading T-072's actual text: it is about `GET
/api/monitoring`'s **per-run** `rows: list[MonitoringRunRow]` having no page/limit. Reading the
diff (`git show e5d5043 -- frontend/src/screens/Monitoring.tsx`): it paginates
`filteredSigs`/`pagedSigs` — the recurring-**signatures** grid — never touching `data.runs`.
Confirmed via `grep -n "sig_limit\|signatures_limit" api/main.py` that the frontend never sends
`signaturesLimit` (`api.monitoring(window)`, no second arg), so the signatures payload actually
was fully uncapped and worth pagination — but it is not the row T-072 describes. I did **not**
mark T-072 done. Instead: **new row T-076** captures what `e5d5043` actually shipped, and T-072
now carries a note pointing at T-076 and stating it is "still open after T-076."

This is exactly the kind of thing CLAUDE.md's guardrail 3 ("never fabricate... a count" / "the
#1 drift you fix is a built feature still marked deferred") flags in reverse — here the risk
was **marking an unrelated gap "fixed"** by trusting a commit-message task-id at face value.
Grounding against the actual diff caught it.

### Verification method (per file/claim)

- Every frontend behavior claim (BuilderShared `germlineTemplate()`, TopBar combobox, verdict.ts
  `RUN_STATUS_META`, MetricsPanel `emptyGateGroup`, RunDetail's three-gate skeleton, Monitoring
  pagination) verified by reading the actual `git show <sha> -- <file>` diff, not the commit
  prose.
- The `RunbookThreshold.pipeline_gate` claim verified by reading `api/main.py`'s `get_runbook()`
  — confirmed it reads `registry.entry(t.our_key).gate`, an **existing** metric-registry field,
  not a new registry entry — so `data/metric_registry.md` is NOT owed (no new metric/alias/unit).
- The intake router's shape (`POST /api/runs`, `GET /api/runs/{id}/intake-status`,
  `_FIXTURE_SAMPLES = {"HG002"}`, 409/422 semantics, `require_role`) verified by reading the
  full new file `api/routers/intake.py` (170 lines).
- Test-census claim: `uv run pytest --collect-only -q` → 362 tests collected, matching
  `quality/evaluation.md`'s existing "362 tests / 22 files, 359 pass / 3 skip" — and
  `git diff --stat a111703..01ba673 -- tests/` is empty, confirming none of these five commits
  touched `tests/`, so the census doc was already accurate and not owed by this batch. Also
  confirmed (via `grep`) that the new `POST /api/runs` endpoint has **zero** automated test
  coverage — flagged honestly in `quality/evaluation.md` §"What we do not claim" (item 4) and
  `quality/risks.md` RISK-034, rather than left silently unmentioned.
- `data/schemas.md` checked for `RunbookThreshold`/`pipeline_gate`: no hits — it's an API-layer
  (`api/main.py`) model, not a `src/bayleaf/models.py` core model, so the 🔴 schemas.md map
  row does not fire for this change (confirmed by grep, not assumed).

## Decisions

| Decision | Distilled to |
|---|---|
| Three commit-message task-ID collisions get new, non-colliding rows (T-073/074/075) rather than overwriting the existing T-058/059/060 rows those ids already own | [tasks.md](../planning/tasks.md) T-073–T-075 |
| `e5d5043`'s cited "(T-072)" is not marked done — it fixed a different, adjacent gap (signatures list, not per-run rows); a new row T-076 captures what shipped, T-072 stays open | [tasks.md](../planning/tasks.md) T-072/T-076 |
| T-057 downgraded from a single "proposed" bundle to "in-progress," split narratively into shipped (ingest/hand-off) vs. still-wishlist (BaseSpace, chat) rather than closing the whole bundled row on a partial ship | [tasks.md](../planning/tasks.md) T-057 |
| The new `POST /api/runs` job-runner instance is a narrow, demo-scoped realization worth a factual addendum to ADR-0003's Realized section — not a new decision, no alteration of the accepted decision | [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md) §Realized (2026-07-09) |
| A new risk (external bioconda toolchain on PATH; ~15s live-execution timing) is real and demo-relevant enough to record, not just implied by the commit message | [risks.md](../quality/risks.md) RISK-034 |
| Missing automated test coverage on the new execution endpoint is recorded as an open, honest gap rather than left implicit | [evaluation.md](../quality/evaluation.md) §What we do not claim (4) |

## Open questions & TODO

- `docs/design/frontend/handoffs/2026-07-09-backend-contracts.md` §"What is NOT built" item 2
  still lists "the pipeline-repair + archivist agents" as not-built alongside T-057 — those two
  agents were already done (T-058/T-059) *before* this handoff's own date. Left untouched: this
  is a dated, episodic handoff snapshot (like a journal), not a living canonical doc the
  Doc-update map routes updates to; correcting historical handoffs after the fact would corrupt
  the archive. Flagging here in case the maintainer wants a superseding handoff note instead.
- `docs/demo/run-of-show.md` / `docs/demo/demo_plan.md` do not mention Submit at all (checked:
  no hits for "Submit"), so there is no stale claim to fix there — but neither do they warn an
  operator that a *live* Submit demo needs `BAYLEAF_BIOCONDA_BIN` set before starting
  `uvicorn`, and the demo launch commands in `run-of-show.md`/`README.md` don't set it. Not
  edited (redesigning the demo script is a product call, not implied by this batch), but
  recorded as RISK-034's owner/revisit trigger.
- T-069/T-070/T-071 (Builder dry-run/diff wiring, run-selector, decision-card contamination
  gap) are unaffected by this batch and remain open as before — reconfirmed still accurate,
  not re-verified line-by-line this session.

## Distilled into

- [planning/tasks.md](../planning/tasks.md) — T-057 rewritten; T-072 annotated; T-073/074/075/076 added.
- [CLAUDE.md](../../CLAUDE.md) — Current code map: intake execution boundary, `RunbookThreshold.pipeline_gate`, shared `RUN_STATUS_META` + run switcher, editable germline template.
- [design/architecture.md](../design/architecture.md) — new "Frontend fixes batch 3" paragraph (all five commits) + corrected the stale "Submit is local-state only" deferral line.
- [design/data-platform-and-archivist.md](../design/data-platform-and-archivist.md) — new §4.6 (Monitoring signatures pagination, distinguished from T-072).
- [design/frontend/README.md](../design/frontend/README.md) — §5.1 Submit, §4 App shell (run switcher), §5.4 Decision cards, §6 Pipeline builder, §8 Invariants.
- [requirements/functional.md](../requirements/functional.md) — REQ-F-042 updated; REQ-F-045/047 addenda; new REQ-F-067/068.
- [adr/ADR-0003-deployment-agnostic-ports.md](../adr/ADR-0003-deployment-agnostic-ports.md) — factual "Realized (2026-07-09)" addendum (no decision altered).
- [quality/risks.md](../quality/risks.md) — new RISK-034.
- [quality/evaluation.md](../quality/evaluation.md) — "What we do not claim" item 4 (untested execution boundary).
