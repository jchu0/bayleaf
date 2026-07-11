# Journal — 2026-07-10 (MST) — Wave 4: real Submit CSV parsing + API-client error detail

| Field | Value |
|---|---|
| **Focus** | Doc-keeper SWEEP for 2 commits (`f8d9ea0`→`1bb79b8`) landed after the Batch-8 sweep ([journal](2026-07-10-batch8-theme-monitoring-recharts.md), commit `e39bb4e`). Ground every claim in the real diffs (`git show <sha>`), then walk the [Doc-update map](../TABLE_OF_CONTENTS.md#doc-update-map) and update every doc it obligates, in the same sweep — with special attention to two long-standing limitations these commits close: the "Submit is a registration-only visual mock" framing, and the "no way to submit `sample_metadata.csv`" gap. |
| **Participants** | doc-keeper subagent (SWEEP mode) |
| **Outcome** | 2 commits swept, both frontend-only (`git diff --stat e39bb4e 1bb79b8 -- src/ api/ tests/` empty), no verdict/gate/ADR-0001 boundary changed. `f8d9ea0` adds `api.ts`'s `httpError()` so every failed `get`/`write`/`fetchRunsPage` throws the backend's real FastAPI `detail` (string or 422 array) instead of a bare `"422 Unprocessable Content"` — every off-gate write's error toast now shows the real reason, app-wide. `1bb79b8` reworks Submit from a **visual mock** (no `<input type=file>`, a hardcoded "Parsed 4 samples" chip) to **real CSV parsing**: an Illumina v2 SampleSheet (`[Header]` + `[*_Data]`) or a plain CSV, tolerant of missing columns; a new `sample_metadata.csv` (LIMS/subject sheet) attach path that merges tissue into the sample-type column and shows subject id per row (**client-side only** — `POST /api/runs`'s `SubmitRunIn`/`SampleIn` carry no subject field, confirmed by reading `api/routers/intake.py:55-72`, `extra="forbid"`); 25/page sample-table pagination; and a scale-aware submit toast (summarize, not join, past 5 names). Docs updated: `CLAUDE.md` code map (new Wave-4 paragraph + rewritten deferrals sentence), `docs/design/frontend/README.md` §5.1 Submit (rewritten), `docs/design/architecture.md` (one-clause addendum to the existing Toast-system paragraph), `docs/requirements/functional.md` (new REQ-F-074 + Related crosslink), `docs/planning/tasks.md` (new T-101 row). Waived with reasons below: `docs/design/data-platform-and-archivist.md`, `docs/requirements/scope-and-wishlist.md`, `docs/quality/risks.md`, `docs/quality/evaluation.md`, the ADR set, `data/schemas.md`/`provenance.md`/`metric_registry.md`, `data/licensing.md`/`requirements/constraints.md`, `design/agents.md`. |

## Discussion

### Grounding pass (`git show`, before writing any doc)

Confirmed dates first: `git log -1 --format=%ci f8d9ea0` and `... 1bb79b8` both return
`2026-07-10 18:32:27 -0700` — same MST calendar date as Batch 8, immediately after it (`git log
--oneline -8` shows `1bb79b8 → f8d9ea0 → e39bb4e[Batch-8 sweep] → f8a6f35[Batch 8 T-100] → …`).
Confirmed frontend-only: `git diff --stat e39bb4e 1bb79b8 -- src/ api/ tests/` returns **empty**
— no backend/data-contract/test trigger fires this sweep, matching the task's own framing.

1. **`f8d9ea0` — API client: surface FastAPI error detail.** Read the full diff (26 lines,
   `frontend/src/api.ts` only). A new `httpError(res: Response): Promise<Error>` reads the
   response body: a string `detail` (a 4xx `HTTPException`) is used verbatim; an array `detail`
   (FastAPI's 422 validation-error shape, `[{msg}]`) is mapped to `.msg`, filtered, and
   `; `-joined; a non-JSON body falls back to the old `${status} ${statusText}` line inside a
   `try/catch`. All three call sites — `get<T>`, `write<T>`, and the header-reading
   `fetchRunsPage` — replace their bare `throw new Error(...)` with `throw await httpError(res)`.
   Confirmed no other file changed (`git show --stat` = 1 file) and no wire-contract change (the
   function only reads an already-returned error body, it sends nothing new).
2. **`1bb79b8` — Submit: real samplesheet + sample_metadata.csv parsing, 100-sample pagination.**
   Read the full 419-line diff (`frontend/src/screens/Submit.tsx` only, no test file, no `api.ts`
   change here — the error-detail plumbing from commit 1 is what surfaces `POST /api/runs`'
   real 422 message on a no-fixture submit, per the commit's own verification note).
   - **Real parse, both formats.** `parseSamplesheet()` detects `[Header]`/`[*_Data]` markers
     (Illumina v2) and falls back to "first non-empty line is the column header" for a plain CSV;
     `colIndex()` resolves a column tolerantly by any of several accepted header-name aliases
     (`sample_id`/`sample`/`sampleid`/`sample name`, etc.) — a missing/renamed column degrades to
     an empty cell, never a crash, matching the repo's boundary-tolerance rule (CLAUDE.md
     Data-handling 2). `splitCsv()` is a small quoted-field splitter, explicitly **not** a full
     RFC parser (no embedded newlines) — read the comment, this is an honestly-scoped tolerance,
     not a claimed general CSV engine.
   - **`sample_metadata.csv` (the code's own inline label: "G2").** `parseMetadata()` resolves
     `Sample_ID`/`Subject_ID`/`Tissue`-family columns into a `Record<string, SampleMeta>`;
     `onMetaFile()` merges `tissue` into the existing `samples` array's `type` field and stores the
     map in `sampleMeta` state, which the sample-table row renderer reads to print
     `Subject ${subject}` under each sample name. Grounded the "client-side only" claim by reading
     `api/routers/intake.py`'s `SampleIn`/`SubmitRunIn` (lines 55–72): neither model has a
     `subject`/`subject_id` field, and both set `model_config = ConfigDict(extra="forbid")`, so
     even if the frontend tried to send one today it would 422 — the UI copy's own "held
     client-side for now (not yet sent — a labelled seam)" is accurate, not just claimed.
   - **Pagination.** `PER = 25`, `pages`/`curPage`/`pageStart`/`pagedSamples` derived from
     `samples.length`; the row renderer's local index `li` is offset by `pageStart` to a global
     `i` so `patchSample`/`removeSample`/`cycleType` (which index into the full `samples` array,
     unchanged) still land on the right row across pages — read this specifically to rule out an
     off-by-page-boundary edit bug.
   - **Scale-aware toast.** The submit handler's toast previously did
     `` `Processing ${ack.processed_samples.join(', ')}…` `` — for 100 processed names this would
     be one enormous string. Now a local `summarize()` lists up to 5 names, else `"N samples"`;
     applied to both `processed_samples` and `skipped_samples`.
   - **The parsed chip is now conditional** (`{uploadName && (...)}`) instead of always rendering
     a hardcoded `SampleSheet_2026-07-09.csv` / "Parsed 4 samples" block — confirmed by diffing the
     removed `<div>` against the new one guarded on real parse state.
   - `POST /api/runs`/`api/routers/intake.py` itself is **unchanged** — the execution boundary,
     the `HG002`-only fixture scoping, and the honest-skip behavior for every other sample are
     exactly as T-057 shipped them (2026-07-09). This commit only makes the **input** to that
     boundary real instead of mocked.

### Doc-update map sweep

Walked [the map](../TABLE_OF_CONTENTS.md#doc-update-map) row by row against the confirmed
frontend-only diff:

1. **🔴 ANY working session** → owed this journal. Done.
2. **🟠 `api/` endpoint or `frontend/` screen — new/changed capability** → owed
   `design/architecture.md` + `design/data-platform-and-archivist.md` +
   `requirements/functional.md` (REQ-F). **Partially fired.** `functional.md`: fired — new
   REQ-F-074. `architecture.md`: fired narrowly — the existing Toast-system paragraph (T-067) is
   exactly the place this error-detail improvement belongs, so it gets one addendum clause rather
   than a new bullet (the Submit capability itself is already narrated there via T-057 and stays
   accurate — it never claimed the upload was mocked, only that the execution boundary was real,
   which is still true). `data-platform-and-archivist.md`: **not fired** — its `subject_id`/
   `sample_metadata.csv` discussion (§ "Persist intake by widening `sample.registered`", the
   G-PII/G-DEID guardrails) is entirely about the **backend** persistence design, still wishlist/
   not-built; a client-side-only parse that is explicitly never sent to the backend changes
   nothing that doc claims. Waived.
3. **🔴 A task changes status / is created** → owed `planning/tasks.md`. Fired — new T-101 row
   (Wave 4, both commits, done).
4. **⚪ Files moved / a module added / a map trigger rotted** → owed `CLAUDE.md` code map. Fired —
   new Wave-4 paragraph + rewritten deferrals sentence (the old sentence didn't claim Submit's
   upload was mocked either, but it said nothing about the real parse or the sample_metadata seam,
   which is now worth naming given the deferrals line's job is precisely to track what's still
   client-side/unpersisted).
5. **⚪ Scope / wishlist / "built" changes** → `requirements/scope-and-wishlist.md`. **Not
   fired** — item 9 (no-code pipeline runner) already narrates "the samplesheet-submission form
   now has a real backend" (T-057) and that framing is unaffected; item 9's own scope (a
   schema-driven form-to-any-pipeline path) is a different, still-open axis from "does the upload
   panel actually parse a file," which was never what item 9 was about. No wishlist status flips.
   Waived.
6. **🔴 `models.py`/`parsers.py`/`persistence/`** → `data/schemas.md`. **Not fired** — confirmed
   zero `src/pipeguard/` changes in both diffs (the grounding-pass empty-diff check above is a
   superset of this).
7. **🔴 `tests/` added/removed/renamed, or an EVAL case** → `quality/evaluation.md`. **Not
   fired** — `git diff --stat e39bb4e 1bb79b8 -- tests/` is empty (subset of the check above); no
   Python test census to recount. Waived.
8. **🟠 `runbook.py`/`rules.py`** → `data/qc_metrics.md`. **Not fired.**
9. **🟠 `metrics/` registry** → `data/metric_registry.md`. **Not fired.**
10. **🟠 `provenance.py`/`engine.py`/`EventType`/JSONL ledger** → `data/provenance.md`. **Not
    fired** — no event vocabulary or ledger format touched; nothing here is persisted at all yet.
11. **🟠 A new advisory agent / model tier / corpus** → `design/agents.md` + ADR. **Not fired.**
12. **⚪ A load-bearing decision made/superseded** → a new ADR or an existing ADR's Decision/
    Status + a journal Decisions row. Considered: is "parse a samplesheet for real" or "surface
    HTTPException detail in a toast" ADR-worthy? **No** — neither touches an architectural
    invariant (ADR-0001 rules-decide/AI-advises, ADR-0002 ledger, ADR-0003 ports, ADR-0006
    AI-off-default, ADR-0014 FastAPI+React, ADR-0017 identity/RBAC — all untouched); both are
    implementation fixes to already-designed screens/seams. No new ADR.

**Waived, with reasons:** `quality/risks.md` (RISK-034 covers the **backend** toolchain-on-PATH
dependency of `POST /api/runs`'s execution boundary — unaffected by what the frontend does with a
file before it POSTs; no new risk class introduced by parsing a CSV client-side); `data/schemas.md`
/`data/provenance.md`/`data/metric_registry.md` (no wire-contract, event-vocabulary, or metric
change — see map rows 6/9/10 above); `data/licensing.md`/`requirements/constraints.md` (no new
dependency — `f8d9ea0` and `1bb79b8` add zero lines to `frontend/package.json`, confirmed by the
`git show --stat` output for both commits showing only `.ts`/`.tsx` files); `design/agents.md` +
the ADR set (no new/changed agent, no decision reversal — see map row 11/12 above);
`ops/telemetry-connectors.md` (no `/metrics` series change); `demo/*.md` (no demo-flow or command
change — this is in-app capability work, not a run-of-show step).

## Decisions

| Decision | Distilled to |
|---|---|
| No ADR needed for either commit — both are implementation fixes within existing, unchanged architectural invariants (ADR-0001/0002/0003/0006/0014/0017), not load-bearing design decisions | this journal (§Doc-update map sweep, item 12) |
| `subject_id`/`tissue` from `sample_metadata.csv` stays an explicitly client-side-only capture — no backend field added this session — preserving the data-platform design's G-PII/G-DEID guardrails (still wishlist/not-built) rather than quietly widening `SubmitRunIn` to accept identity data ahead of that design landing | [functional.md REQ-F-074](../requirements/functional.md), [tasks.md T-101](../planning/tasks.md), [data-platform-and-archivist.md](../design/data-platform-and-archivist.md) (unchanged by design) |

## Open questions & TODO

- **Next Submit step (named in REQ-F-074 and T-101):** persist `subject_id`/`tissue` server-side.
  This needs the data-platform design's "widen `sample.registered`" slice
  ([data-platform-and-archivist.md](../design/data-platform-and-archivist.md) § intake persistence)
  to land first, gated by the same G-PII/G-DEID guardrails already written there — not a frontend
  change alone.
- T-057's BaseSpace connector remains separate/open (unaffected by this Wave; still no
  `POST /basespace/...` endpoint or client method).
- `docs/design/frontend/README.md` still has no metadata table (Status/Last updated/Audience/
  Related) — a pre-existing gap already flagged in the Batch-8 journal, still out of this sweep's
  narrow scope.

## Distilled into

- [CLAUDE.md](../../CLAUDE.md) — new Wave-4 paragraph in the frontend code-map entry + rewritten deferrals sentence.
- [docs/design/frontend/README.md](../design/frontend/README.md) §5.1 Submit — rewritten.
- [docs/design/architecture.md](../design/architecture.md) — addendum clause on the existing Toast-system paragraph.
- [docs/requirements/functional.md](../requirements/functional.md) — new REQ-F-074 + Related crosslink.
- [docs/planning/tasks.md](../planning/tasks.md) — new T-101 row.
