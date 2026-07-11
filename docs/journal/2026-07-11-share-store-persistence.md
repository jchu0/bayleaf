# Journal — 2026-07-11 (MST) — D3 share sink: persistence parity (jsonl/sqlite/postgres)

| Field | Value |
|---|---|
| **Focus** | SWEEP the docs owed by one already-landed commit (`9a4ef5f`, offline suite 409 passed / 4 skipped, ruff+mypy clean, live-Postgres test verified green against a real `postgres:16`): the D3 de-identified-share egress audit sink goes from JSONL-only to the full pluggable jsonl/sqlite/postgres shape, matching the other four off-gate sinks (feedback/pipeline/review/settings). Pure doc-keeper work — no product code, tests, or fixtures touched. |
| **Participants** | doc-keeper subagent, invoked in SWEEP mode |
| **Outcome** | Every doc obligated by the Doc-update map for this commit is updated and grounded directly in the code read (`api/share_store.py`, `api/main.py`, `tests/test_share_store.py`, `tests/test_persistence_postgres_live.py`). Fixed every stale `api/share_ledger.py` / `PIPEGUARD_SHARE_LEDGER` / `share_events(...)` / `record_share_event` reference found across the canonical docs (present-tense claims only — the two prior journal entries that correctly describe the pre-rename state at the time they were written were left alone, per "journal is the archive, never rewritten"). |

## Discussion

### What landed in code (verified by reading, not the commit message)

1. **`api/share_store.py`** (replaces `api/share_ledger.py`, deleted in the same commit — confirmed
   via `git show --stat 9a4ef5f`). Read the whole module: a `ShareStore` `Protocol` (`append`,
   `for_run`) + three adapters —
   - `JsonlShareStore` (default): append-only, gitignored JSONL at `PIPEGUARD_SHARE_PATH`
     (default `share.events.jsonl` at repo root); tolerant reads (missing file → `[]`, a corrupt
     line is skipped).
   - `SqliteShareStore`: a `share_events` table (stdlib `sqlite3`, `PIPEGUARD_SHARE_DB`, default
     `share.sqlite`); a fresh connection per op (thread-safe under FastAPI's sync threadpool).
   - `PostgresShareStore`: a `share_events` table (`[postgres]` extra, lazy `psycopg` import,
     `DATABASE_URL`); fails fast at construction (so `get_share_store()` can degrade) if the
     server is unreachable.
   `get_share_store()` reads `PIPEGUARD_SHARE_STORE` (default `jsonl`); `sqlite`/`postgres`
   selection degrades to `JsonlShareStore` on **any** construction failure, logged by
   `type(exc).__name__` only — never `str(exc)`, which could carry a DSN password. This exactly
   mirrors `get_repository()` / `get_feedback_store()` / the settings/review/pipeline stores
   (ADR-0016).
2. **`api/main.py`.** `get_run` and `share_run` now call `get_share_store().for_run(run_id)` /
   `.append(event)` — replacing the old free functions `share_events(run_id)` /
   `record_share_event(event)`. Confirmed via `git show 9a4ef5f -- api/main.py`: a 10-line diff,
   no other behavior change (the merge-into-`RunDetail.events`-at-read-time logic is untouched).
3. **Tests.** `tests/test_share_store.py` (new, 6 tests): jsonl default, sqlite round-trip,
   sqlite==jsonl parity (both adapters see the same events for a run), degrade-to-jsonl when
   `PIPEGUARD_SHARE_STORE=postgres` has no `DATABASE_URL`, idempotent re-append (same event id
   twice doesn't duplicate a row), tolerant corrupt-line read. `tests/test_persistence_postgres_live.py`
   gains `test_postgres_share_store_round_trips` (now 4 live tests, was 3) — compose-gated,
   skip-safe, and per the task's own report, verified green against a real `postgres:16`.
4. **`.env.example` / `.gitignore`.** Already updated by the requesting session (confirmed present:
   the `PIPEGUARD_SHARE_STORE`/`_PATH`/`_DB` block at `.env.example` lines 203-211); not touched by
   this doc-keeper pass, per the task's own instruction.

### Doc-update map sweep

Walked [TABLE_OF_CONTENTS.md#doc-update-map](../TABLE_OF_CONTENTS.md#doc-update-map) against the
commit. This is a **storage-backend-only** change — no `EventType`, field, or endpoint contract
changed — so most of the usual "new capability" rows don't fire; what does:

1. **🔴 new tests → `quality/evaluation.md`.** Recounted with `uv run pytest --collect-only -q`
   (413 collected, was 406) + `uv run pytest -q` (409 passed / 4 skipped, was 403/3) +
   `git ls-files 'tests/*.py' | wc -l` (27, was 26). Updated the headline sentence + the per-file
   list (inserted `test_share_store` (6), bumped `test_persistence_postgres_live` 3→4). Extended
   **EVAL-051**'s Target/Automated fields to name the new sink module and the new test files;
   fixed its Method's "share ledger redirected to a tmp path" wording to "share store."
2. **⚪ decision made → an ADR.** This is an extension of an already-accepted decision
   (ADR-0016's pluggable-store pattern), not a new load-bearing choice — no new ADR. Added a new
   numbered item to ADR-0016's Decision list (item 7: "a fourth instance"), fixed its stale "three
   off-gate places" Costs line (now six, confirmed via `grep -rln "class Postgres" api/ src/`),
   and added a "persistence parity" item to ADR-0018's own Realized section (item 3, renumbering
   the "still unbuilt" summary to item 4) since that's where the D3 share-egress build history
   already lives. Extended ADR-0002's Realized §3 (the `data.exported` EventType) with a short
   persistence-parity note, since that section is what first documented the ledger/sink's
   existence.
3. **🔴 `provenance.py` / the ledger format → `data/provenance.md`.** Renamed the module reference
   throughout, rewrote the "second, separate ledger" section as "second, separate **sink**"
   (`#a-second-separate-sink-for-share-events-apishare_storepy`, and fixed the ADR-0002/ADR-0018
   inbound anchors to match) describing all three adapters, the degrade-to-JSONL discipline, and
   the honest "multi-worker safety is a documented seam, not built" limit — mirroring
   `api/feedback_store.py`'s own framing so the two don't drift into inconsistent honesty levels.
4. **🟠 `api/` capability change → `design/architecture.md` + `design/data-platform-and-archivist.md`.**
   Fixed the Wave 11 bullet's stale module name; added a short "Persistence follow-up" bullet
   naming the commit, the rename, and the still-open multi-worker seam. Fixed the de-id paragraph
   in data-platform-and-archivist.md (§2.1d area) the same way, and added ADR-0016 + the new
   journal to that doc's Related field (it referenced ADR-0018 and ADR-0002 but never ADR-0016,
   even though it already described the feedback/pipeline/settings/review store family — an
   oversight from before the share sink existed, fixed here).
5. **⚪ scope/wishlist → `scope-and-wishlist.md`.** Wishlist #14's D3 paragraph named
   `api/share_ledger.py` in present tense — fixed to `api/share_store.py` + the pluggable-shape
   framing.
6. **🔴 task status → `tasks.md`.** New row **T-122** (persistence parity), pointing back to
   T-120 (the sink's original build). T-120's own row text is left as-is (it accurately described
   what existed *when T-120 shipped*, before this commit) — the same "don't retrofit a completed
   task's own narrative" convention the doc set already follows (e.g., T-115's `Truncate.tsx`
   "no call sites" line was *narrowed* by a new T-116 row, not rewritten in place).
7. **🔴 doc create/move/rename → `TABLE_OF_CONTENTS.md`.** No new canonical doc, no status flip —
   only this journal, which the journal/ folder's existing ToC row already covers. Not edited,
   same reasoning the 2026-07-11 d2-d3 journal used for the same situation.

### What I deliberately did not touch

- **`docs/data/schemas.md`.** The commit changed a storage *backend*, not the `ProvenanceEvent`
  record contract or the `EventType` vocabulary — schemas.md owns the record shape, not the
  adapter, and neither changed. Grepped for `share_ledger`/`share_store`/`DATA_EXPORTED` in the
  file: only the pre-existing event-vocab list line, unaffected. **Waiving** the 🔴 "models.py /
  parsers.py / persistence — new/renamed field" row: no field, type, or `schema_version` changed.
- **`docs/requirements/functional.md` REQ-F-084.** Fixed the one stale `api/share_ledger.py`
  mention (the module name is part of the requirement's own citation), but did not add a new
  REQ-F — the requirement itself (an approver-gated, audited, de-identified share endpoint) is
  unchanged; only its storage backend gained options.
- **`docs/design/variant-interpretation.md`.** Grepped for `share_ledger`/`share_store`: no hits.
  The design doc's §0 build-status note describes the *endpoint's* behavior, not its storage
  adapter, and stays accurate as written.
- **The two prior journal entries** (`2026-07-11-d2-d3-share-egress.md`,
  `2026-07-10-wave6-route-to-human-deid.md`) — left untouched. They accurately describe the state
  of the code *at the time they were written* (before this commit existed); rewriting a journal
  entry after the fact would violate "journal is the archive, never the source of truth." A
  reader who lands there via search will see the module name that existed then, which is honest
  for a dated log — the canonical docs (ADRs, provenance.md) are where the current name lives.
- **`docs/adr/ADR-0016-postgres-port.md`'s own title in the ToC ADR table**
  (`docs/TABLE_OF_CONTENTS.md` line 83, "the `Repository` Postgres adapter + a pluggable feedback
  store") stays a truncated summary that already omitted pipeline/settings/review before this
  commit — a pre-existing minor staleness, not caused by this change; noted here rather than
  silently expanded, since touching the ADR index title is a bigger edit than this task's scope
  warrants on its own.

## Decisions

| Decision | Distilled to |
|---|---|
| Document the persistence-parity upgrade as a new numbered item in ADR-0016's existing Decision list (item 7, "a fourth instance") and a new item in ADR-0018's existing Realized section (item 3), rather than a new ADR — this is a mechanical extension of the already-accepted pluggable-store pattern (ADR-0016), not a new load-bearing choice. | `docs/adr/ADR-0016-postgres-port.md`, `docs/adr/ADR-0018-variant-interpretation-advisory-evidence.md` |
| Leave the prior two journal entries' `api/share_ledger.py` mentions unedited (they were correct when written); only fix present-tense claims in canonical docs (ADRs, provenance.md, architecture.md, CLAUDE.md, scope-and-wishlist.md, functional.md, evaluation.md, tasks.md's new row). | This journal's "What I deliberately did not touch" section |

## Open questions & TODO

- Multi-worker concurrency (a file lock / connection pool) remains an open, documented seam for
  **every** pluggable store in the repo (repo/feedback/pipeline/settings/review/share) — not
  specific to this commit, unchanged by it.
- `docs/TABLE_OF_CONTENTS.md`'s ADR-0016 table-row title is a stale truncated summary (predates
  even the settings/review stores) — flagged, not fixed, in this pass; a candidate for a future
  small cleanup sweep.

## Distilled into

- [docs/adr/ADR-0002-event-driven-core-provenance-ledger.md](../adr/ADR-0002-event-driven-core-provenance-ledger.md) — Realized §3 persistence-parity note
- [docs/adr/ADR-0016-postgres-port.md](../adr/ADR-0016-postgres-port.md) — new item 7, Status/Date/Related, Costs/Follow-ups fixed
- [docs/adr/ADR-0018-variant-interpretation-advisory-evidence.md](../adr/ADR-0018-variant-interpretation-advisory-evidence.md) — new Realized item 3, Related field
- [docs/data/provenance.md](../data/provenance.md) — module rename, pluggable-sink section rewrite, Related field
- [docs/design/architecture.md](../design/architecture.md) — Wave 11 fix + new persistence-follow-up bullet
- [docs/design/data-platform-and-archivist.md](../design/data-platform-and-archivist.md) — de-id paragraph fix, Related field
- [docs/requirements/functional.md](../requirements/functional.md) — REQ-F-084 module reference
- [docs/requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — #14 module reference
- [docs/quality/evaluation.md](../quality/evaluation.md) — census (413/27, 409 pass/4 skip), EVAL-051 extended, Related field
- [docs/planning/tasks.md](../planning/tasks.md) — new T-122
- [CLAUDE.md](../../CLAUDE.md) — code map item 2 + new persistence-follow-up paragraph
