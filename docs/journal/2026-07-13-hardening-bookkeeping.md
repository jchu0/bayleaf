# Journal — 2026-07-13 (MST) — Hardening-bookkeeping sweep (T-148/T-034/T-071a/T-041)

| Field | Value |
|---|---|
| **Focus** | Doc-only SWEEP for four hardening changes already merged to `main` (PRs #10–13) whose branches deliberately skipped `docs/planning/tasks.md`/`CLAUDE.md` to avoid cross-branch conflicts. Verify each against merged code (`6161e90`), update the tracker + code map accurately, sweep the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) for anything else the four changes obligate, and fix two stale sub-claims a code-grounded verify found. |
| **Participants** | doc-keeper (Claude), maintainer (async, via task brief) |
| **Outcome** | Verified all four merges against code; updated `tasks.md` (5 rows + header), `CLAUDE.md` (code map items 1c/1e/1g/4b/4c), `ADR-0024` (Status/Follow-ups), `TABLE_OF_CONTENTS.md` (ADR-0024 row), `quality/evaluation.md` (census 789/65→798/65 + by-size breakdown + two EVAL-NNN counts), and four docs with a stale "verifybamid2 unwired" claim the sweep found code-contradicted (`qc_metrics.md`, `metric_registry.md`, `functional.md`, `scope-and-wishlist.md`). No code changed. |

## Discussion

### Branch + verification approach

Created `docs/hardening-bookkeeping` off `main` (`6161e90`, the tip after PR #13 merged). Read
`docs/TABLE_OF_CONTENTS.md` (Doc-update map) and `docs/planning/tasks.md` first per the operating
contract. Rather than trust the task brief's summary of each PR, verified each claim directly
against code (`grep`/`Read`) before writing anything — per the "ground every claim in code"
guardrail, a doc-keeper session that just transcribes a PR description without checking it is the
exact failure mode it exists to prevent.

### T-148 — intake agent-binding capture (PR #10, commit `675a085`)

Read `api/routers/intake.py::submit_run` and `api/routers/pipeline_run.py::run_pipeline` side by
side: both now call `get_agent_binding_store().record(run_id, agent_bindings, captured_at=now)` at
submit, and the recorded bindings ride in the approved graph's `graph.agent_bindings` envelope
(normalized via `normalize_bindings`). Read `tests/test_node_observations.py`'s new `bound_run`
fixture + its three tests (`test_wired_agent_reads_scoped_outputs`, `test_unwired_agent_is_403`,
`test_wired_agent_grants_capped_to_binding`) — they exercise the enforcement against a POPULATED
`run_tree` publish dir, not just an empty-honest-view case, so a wired agent gets real scoped
fastp files back. Confirmed the two stated deferrals are real, not just claimed: `grep`ed for
`gather_node_observations` outside `api/routers/node_observations.py` — it is defined there
(the documented "triage-consumption seam") but nothing calls it, incl. `src/bayleaf/triage/agent.py`
(which has `ask()` but no node-observation grounding); and no `?agent=` auto-pass exists anywhere.

**Status call: `in-progress`, unchanged from before this PR.** The task brief suggested this framing
and the code confirms it's the honest call — ADR-0024's own Status line explicitly deferred
"intake-authored-run capture," and that's exactly what closed; the OTHER deferral on the same line
("the agent-consumption path that passes `agent` automatically") is untouched, plus the triage
consumer never existed. Marking `done` would overclaim a still-open capability (an agent can now be
denied/allowed correctly IF something asks with its identity — but nothing does yet).

### T-034 — metric rename (PR #11, commit `31c2180`)

`grep -rn "pct_reads_identified"` across the repo turned up exactly the residual the brief named:
`scripts/run_giab_pipeline.py`, `scripts/gate_giab.py`, and design/journal prose (historical,
correctly untouched) — no live code path or committed fixture still uses the old name except those
two scripts. `grep -rln "reads_passing_filter"` confirmed all 5 committed `qc_metrics.csv` fixtures
(`mock_run_01/02/03`, `mock_run_scale_30`, `RUN-2026-07-11-CLINVAR-RTH`) already carry the new
header — checked each file's actual first line, not just a filename match. Read `parsers.py`'s
fallback (`row.get("reads_passing_filter", row.get("pct_reads_identified"))`) — genuinely a
fallback, not a silent drop. Marked **done**: the rename is complete and self-consistent; the two
scripts are a labelled, covered residual, not a partial/broken migration.

### T-071(a) — optional-input compiler concept + dormant verifybamid2 (PR #12, commit `c0d7646`)

Read `catalog.OPTIONAL_INPUT_PARAMS`, `compiler.py`'s handling of it (`required_inputs()` excludes
an optional kind; `_source_channel` emits the param-gated `Channel.fromPath(...) : Channel.empty()`
form), and `germline.py`'s new `n_verifybamid` node. Read the regenerated
`pipelines/germline/modules/verifybamid2.nf` (a real, non-fabricated command reused from the
standalone module) and confirmed the drift-lock test still passes conceptually (the design doc
`nextflow-codegen.md` rule 9, already updated by the branch, documents this in full — did not
duplicate it in CLAUDE.md, just cross-referenced). Verified the three "still open" claims
independently rather than trusting the brief: `grep`ed `scripts/run_giab_pipeline.py` for
`selfSM`/`verifybamid` (zero hits — confirmed it still doesn't parse it), `grep`ed
`frontend/src/` for `verifybamid` (zero hits — confirmed no Builder card), and read the
multi-sample/SVD-staging caveat directly in `nextflow-codegen.md` rule 9's own prose (already
labelled there). All three genuinely still open.

**Also verified (not part of the task brief, found by reading the surrounding prose while fixing
T-071):** `docs/data/qc_metrics.md`, `docs/data/metric_registry.md`,
`docs/requirements/functional.md`, and `docs/requirements/scope-and-wishlist.md` all still asserted
"no pipeline committed in this repo runs verifybamid2" / "the compiler has no input-gated-
conditional concept for an optional add-on tool" — both now FALSE per the code just read. This is
the #1 drift class the doc-keeper role exists to catch (a built feature still marked
deferred/unwired) — just running in reverse (an UNDER-claim, not the more common over-claim). Fixed
all four, careful to keep `happy.nf`'s claim UNCHANGED (T-071a only touched verifybamid2 — hap.py
is still a genuinely unwired standalone module).

**T-071's stale sub-claim (a maintainer-flagged correction):** read `models.py`'s `DecisionCard`
directly — `gate_results` is a real `@computed_field` property (line ~290), present since
`git show 00305f5` (2026-07-07, "Phase 1a: evolve decision records to schemas.md + T-019
confidence"). Struck it from T-071(b)'s list rather than just noting it — leaving a disproven claim
next to a correction reads worse than removing it, and the row already explains why (verified
directly against the property + the introducing commit).

**Status call: `in-progress`** (was `todo`) — (a) is substantially landed with three labelled
follow-ups, (b) (linked-sample, provenance metadata, context-rail fields) is untouched. `todo`
would undersell (a)'s real progress; `done` would overclaim (b) and the follow-ups.

### T-041 — containerize (PR #13, commits `35d2243`, `e28a219`)

Confirmed `deploy/Dockerfile.api`, `deploy/docker-compose.yml`, `.dockerignore` exist; read
`api/main.py`'s `DATA_ROOT = run_store_root()`, the `BAYLEAF_CORS_ORIGINS` env read, and the
guarded `StaticFiles` mount. Confirmed via `find . -iname "*.tf"` that literally no Terraform file
exists anywhere in the repo — the commit message's "Terraform/IaC dropped" claim is not just a
description, it's the actual state. Read the commit message's own "Verified" section (docker build
+ a running-container smoke test against `/api/health`/`/api/runs`/`/`) and took it at face value
since it names specific, checkable assertions (not "should work"). Marked **done, Docker only**.
Also found `scope-and-wishlist.md`'s W3 row still said "+ unapplied Terraform" (the ORIGINAL plan,
now superseded — Terraform was dropped, not shipped-even-unapplied) — fixed it while in the
neighborhood. Added a short **Docker** section to `README.md` (build/run commands + the two env
vars) since a working container image nobody can discover from the README is a real gap, not just
a nice-to-have; checked `requirements/{functional,nonfunctional,constraints}.md` for a stale
"not yet containerized" claim first (none existed) before deciding whether a new REQ entry was
warranted — concluded it wasn't (no false claim to fix, and inventing a new REQ-F/NF entry
unprompted risks scope creep the maintainer has pushed back on before), left as an optional TODO.

### T-030 and T-071's two flagged sub-claims

`grep -n "exportUrl" frontend/src/api.ts` → line 358-359, a real function. `grep -rn
"api.exportUrl" frontend/src/` (excluding `api.ts` itself) → zero hits, and no `RunsBrowser.tsx`/
download button exists anywhere under `frontend/src/screens/`. So the maintainer's correction was
exactly right: the client method exists, only the UI is missing. Corrected the T-030 row without
touching `design/data-platform-and-archivist.md` §4.1, which already states this accurately (its
own "not adopted" / "no frontend download affordance" language doesn't claim the client method is
missing, so it needed no fix).

### Test census (Doc-update map 🔴 row: "add/remove/rename a test → `quality/evaluation.md`")

`uv sync --all-extras` was needed first (a fresh worktree's `.venv` lacked `fastapi`/etc. — an
environment-setup step, not a code issue). `uv run pytest --collect-only -q` → 798 (was 789).
`git diff --stat <PR#10's-merge-base>^1 6161e90 -- tests/` scoped precisely to the four target PRs
(NOT `aafd3c0`, which the initial git-status "recent commits" list showed but which predates the
triage-cache PR #6 — using that as a base would have wrongly attributed #6's test additions to the
four hardening PRs). Confirmed +9 across exactly 3 files via per-file `--collect-only`, matching the
789+9=798 arithmetic exactly.

**A full `uv run pytest -q` in this worktree surfaced 7 failures.** Investigated each rather than
assuming they were pre-existing: every one's traceback references a missing
`data/real-giab/`, `data/RUN-2026-06-05-GIAB-A`, `data/RUN-2026-07-04-GIAB-A`, or
`data/RUN-2026-07-08-GIAB-HG002` path — all gitignored, machine-local artifacts this isolated
worktree was never provisioned with (confirmed `data/RUN-2026-07-08-GIAB-HG002/` contains only a
committed `NOTE.md`, no `qc_metrics.csv`/`SampleSheet.csv` — those are generated-and-gitignored).
Cross-checked by running only the four PRs' new/touched test files in isolation: 132 passed, 1
skipped, only 1 failure (the same missing-data cause, in a test T-034 didn't even touch). Found
independent corroboration in the T-148 PR's OWN commit message (`675a085`): "make check's only reds
are 9 PRE-EXISTING, data-dependent failures (missing gitignored data/real-giab + un-committed
generated run CSVs) that fail identically on clean main in this fresh worktree — none touched by
this change" — the PR author hit and documented the identical root cause independently. Did not
fetch real GIAB data to "fix" this (out of scope for a docs-only sweep, and would not be a genuine
fix — it's a worktree-provisioning gap, not a doc or code defect). Reported the 790/8 expected
fully-provisioned figure with an explicit "not independently re-verified" flag rather than asserting
a pass count I couldn't actually reproduce clean.

### ADR-0024 / TABLE_OF_CONTENTS

Found `ADR-0024`'s own Status line and the ToC's mirrored row both still said "Deferred:
intake-authored capture + the auto agent-consumption `agent` pass" — the FIRST half is exactly what
T-148 just closed. `git log --oneline <base>..6161e90 -- docs/adr/ADR-0024-scope-by-wiring.md` →
empty, confirming none of the four PRs touched this ADR (they deliberately left doc bookkeeping to
this sweep, as the task brief said). Updated the ADR's Status + Follow-ups table and the ToC's
mirrored row together (a coupled pair — the map says "if hub and ADR disagree, the ADR wins," so
edited the ADR first, then propagated to the ToC).

## Decisions

| Decision | Distilled to |
|---|---|
| T-148 stays `in-progress` (intake-capture closes, triage-consumer + auto-`?agent=`-pass remain open) | [tasks.md](../planning/tasks.md) T-148 row, [ADR-0024](../adr/ADR-0024-scope-by-wiring.md) Status |
| T-034 → `done` (rename complete + self-consistent; the two-script residual is covered by the parser fallback, not a broken migration) | [tasks.md](../planning/tasks.md) T-034 row |
| T-071 → `in-progress` (was `todo`) — (a) substantially landed with 3 labelled follow-ups, (b) untouched, one stale sub-claim struck | [tasks.md](../planning/tasks.md) T-071 row |
| T-041 → `done, Docker only` (IaC/Terraform genuinely absent from the repo, not just described as dropped) | [tasks.md](../planning/tasks.md) T-041 row |
| Four docs' "verifybamid2 fully unwired" claims corrected to distinguish it (now dormant-wired) from `happy.nf` (still unwired) | `qc_metrics.md`, `metric_registry.md`, `functional.md`, `scope-and-wishlist.md` |
| Test census pass/skip NOT asserted as re-verified clean — reported as an unverified-but-expected figure with the local-data-gap explicitly named | [quality/evaluation.md](../quality/evaluation.md) |

## Open questions & TODO

- The by-size test-count narrative in `quality/evaluation.md` sums to 787 against the file's own
  claimed 798 total (an 11-test gap) — traced this to a **pre-existing** drift (the list summed to
  778 against a claimed 789 BEFORE this sweep's edits, i.e. the discrepancy predates and is
  unrelated to the four PRs). Not chased down further here — would need a full per-file recount
  across all 65 files, out of scope for this bookkeeping sweep. Worth a dedicated future recount.
- Re-verify the full `uv run pytest -q` suite (expected 790 pass / 8 skip) on a machine that has
  `data/real-giab/` + the generated `data/RUN-2026-*-GIAB-*` run dirs, to close the "not
  independently re-verified" flag left in `quality/evaluation.md`.
- `EVAL-006`'s sub-count ("`test_nextflow_compile.py` (9 offline + 1 machine-gated)") is stale
  independent of this sweep (it hasn't tracked the file's whole-count growth through several prior
  rounds either) — left untouched; flagging for a future EVAL-NNN audit pass rather than guessing at
  a fix without re-deriving which specific tests that sub-count is meant to cover.
- A formal `REQ-F`/`REQ-NF` entry for containerization (T-041/W3) doesn't exist yet — not invented
  this sweep (no stale claim to correct, and it risks scope creep); worth adding in a future
  requirements pass if containerization becomes a tracked capability rather than a delivery detail.

## Distilled into

- [planning/tasks.md](../planning/tasks.md) — T-148, T-034, T-071, T-041, T-030 rows + header;
  Roadmap Phase 4 row.
- [CLAUDE.md](../../CLAUDE.md) — code map items 1c, 1e (new T-071a paragraph), 1g, 4b (new
  ADR-0024/T-148 paragraph), 4c (new, containerization).
- [adr/ADR-0024-scope-by-wiring.md](../adr/ADR-0024-scope-by-wiring.md) — Status, Follow-ups.
- [TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md) — ADR-0024 row.
- [data/qc_metrics.md](../data/qc_metrics.md), [data/metric_registry.md](../data/metric_registry.md),
  [requirements/functional.md](../requirements/functional.md),
  [requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — verifybamid2 wiring
  claims corrected.
- [quality/evaluation.md](../quality/evaluation.md) — census (789/65→798/65), by-size breakdown,
  EVAL-018/EVAL-052 counts.
- [requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — W3 row.
- [README.md](../../README.md) — new Docker section.
