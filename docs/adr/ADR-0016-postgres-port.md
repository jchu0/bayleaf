# ADR-0016 — Postgres port for persistence + feedback (guarded, off by default)

| Field | Value |
|---|---|
| **Status** | Accepted · PostgresRepository + pluggable feedback store BUILT (T-043) + pluggable **pipeline-graph store BUILT (T-049)** + pluggable **share-egress-audit store BUILT (2026-07-11, ADR-0018 D3)** + a **durable job store BUILT (2026-07-11, T-131, jsonl\|sqlite only — no Postgres adapter, by design)** + a **library store BUILT (2026-07-11, T-135, jsonl\|sqlite only, same no-Postgres-by-design shape as the job store)**, all OFF by default; **live-Postgres integration test BUILT + verified green** (`tests/test_persistence_postgres_live.py`, compose-gated + skip-safe); connection pooling + read-from-projection deferred |
| **Date** | 2026-07-09 (MST) · updated 2026-07-11 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](ADR-0003-deployment-agnostic-ports.md), [ADR-0010](ADR-0010-ticketing-notify-read-api.md), [ADR-0014](ADR-0014-productionization-fastapi-react.md), [ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md), [ADR-0018](ADR-0018-variant-interpretation-advisory-evidence.md) (share-egress sink, Realized item 3 — corrected from a stale "item 6" cross-reference, 2026-07-11), [design/agent-authoring-contract.md](../design/agent-authoring-contract.md) (the library entry's contract, item 9), [tasks.md](../planning/tasks.md), [journal 2026-07-11 P3 backlog](../journal/2026-07-11-p3-backlog.md), [journal 2026-07-11 fleet](../journal/2026-07-11-fleet.md) |

## Context

Two pulls converged: (1) in-app feedback (W12, [ADR-0010](ADR-0010-ticketing-notify-read-api.md))
was landing in a flat JSONL file and should go into a real, queryable database; (2) the
`Repository` persistence port ([ADR-0003](ADR-0003-deployment-agnostic-ports.md)) has always
documented `SqliteRepository → Postgres later` — the Postgres adapter was the anticipated
production seam, not yet built. The maintainer asked to **scope out the full port to Postgres**.

The constraint that shapes everything: the demo is offline-first, single-process, zero-dep
(uv single-source; `sqlite3` is stdlib "no new dependency"). A hard dependency on a running
Postgres would break the guaranteed-working offline fallback ([ADR-0014](ADR-0014-productionization-fastapi-react.md)).
So the port must be **real but guarded** — present as a production seam, invisible to the demo.

## Decision

1. **`PostgresRepository` implements the `Repository` port** over Postgres, behaviourally
   identical to `SqliteRepository`: the same five projection tables, **idempotent upserts**
   (`INSERT … ON CONFLICT (pk) DO UPDATE`) so a ledger replay stays a no-op (ADR-0002),
   `JSONB` + `TIMESTAMPTZ` columns, and a `pipeguard_meta` row for the table-layout version
   (Postgres has no `PRAGMA user_version`). It is a projection of the authoritative ledger,
   never a source of truth (ADR-0002), so it is disposable + rebuildable regardless of backend.
2. **Off by default, degrade never crash.** `get_repository()` reads `PIPEGUARD_REPOSITORY`
   (`sqlite` default | `postgres`) and, on **any** failure constructing the Postgres adapter
   (missing extra, no DSN, unreachable server), **degrades to SQLite** — the single line that
   flips the seam, mirroring `get_artifact_store()` (S3, [ADR-0003](ADR-0003-deployment-agnostic-ports.md)).
   `psycopg` is a **lazy import** behind the optional `[postgres]` extra, so the module imports
   and the demo runs with no Postgres dependency and no socket.
3. **Feedback is a separate concern from the decision projection.** Its store is a pluggable
   `FeedbackStore` (`jsonl` default | `sqlite` | `postgres`) with its **own `feedback` table**,
   never the `Repository`, and its writer **never imports the `pipeguard` core** — feedback
   stays off the deterministic gate (ADR-0001). `PIPEGUARD_FEEDBACK_STORE` selects the adapter;
   the DB options degrade to JSONL. `SqliteFeedbackStore` is exercised end-to-end in tests, so
   "feedback in a database" is proven without a live Postgres.
4. **Never leak the DSN.** `DATABASE_URL` carries a password; degradation logs the exception
   **type** only (`type(exc).__name__`), never `str(exc)`, and a write failure maps to a
   generic 503 that leaks neither the path nor the message.
5. **Trace + advisory categorization.** A required `source` field on the feedback contract
   records the exact UI surface (`decision-card` | `product-fab` | …), distinct from `target`,
   so every reaction is traceable. An **advisory feedback agent** (`api/feedback_agent.py`,
   stub-first / opt-in Claude, mirroring the triage seam) categorizes the corpus structurally
   (category / area / sentiment / priority + themes) out-of-band — no HTTP surface, and the
   Claude path is sent only the anonymous aggregate rollup, never raw messages.
6. **The pluggable-store pattern generalizes to a second product domain (T-049).** Saved
   Pipeline Builder graphs use the same seam: a `PipelineGraphStore` (`jsonl` default | `sqlite` |
   `postgres` via `PIPEGUARD_PIPELINE_STORE`, degrade-to-JSONL, its own `pipeline_graphs` table,
   never the `Repository`, never imports the core) with the identical DSN-safety discipline (item
   4). It stores a **tolerant versioned envelope** — the graph payload is arbitrary JSON kept
   as-is, so the builder's shape can churn without a migration — with a server-authored monotonic
   per-name `version`, and it **reserves** a `draft→save→approve` review lifecycle (`status` +
   reviewer/approver fields, server-authored, never client-set — no identity via the `extra="forbid"`
   body). This is the pattern's third instance (Repository / feedback / pipeline), so it earns a
   note here rather than its own ADR; the approve transition + auth are now realized —
   `api/routers/pipelines_lifecycle.py` adds `POST /{name}/submit` (draft→pending_review) and
   `POST /{name}/approve` (pending_review→approved, approver-only), each gated by
   `api/auth.require_role` ([ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md)).
7. **A fourth instance: the `data.exported` share-egress-audit sink (2026-07-11, ADR-0018 D3).**
   `api/share_store.py` (`ShareStore` Protocol + `JsonlShareStore`/`SqliteShareStore`/
   `PostgresShareStore`, `PIPEGUARD_SHARE_STORE=jsonl|sqlite|postgres`, degrade-to-JSONL,
   never-leak-the-DSN) records a `DATA_EXPORTED` `ProvenanceEvent` per de-identified share — audit
   telemetry, not product state, and deliberately **not** the `Repository` (a share never becomes
   a run/sample/finding/card, ADR-0001). It shipped JSONL-only at first (with D3's initial
   egress endpoint), then was brought to the same pluggable jsonl/sqlite/postgres shape as items
   3/6 the same day, closing the one remaining off-gate sink without a DB adapter. Verified
   against a live `postgres:16` (`tests/test_persistence_postgres_live.py`). See
   [data/provenance.md](../data/provenance.md#a-second-separate-sink-for-share-events-apishare_storepy).
8. **A fifth instance, and the first that deliberately stays TWO-backend, not three: the durable
   job store (2026-07-11, T-131, `595815e`, audit finding P3-2, `audit/SYNTHESIS.md` S5 `F5-R5`/`F5-R2`).**
   `api/job_store.py` (`JobStore` Protocol + `JsonlJobStore`/`SqliteJobStore`,
   `PIPEGUARD_JOB_STORE=jsonl|sqlite`, default `jsonl`, degrade-to-JSONL on any construction
   failure — the same discipline as items 3/6/7) replaces the `intake.py`/`pipeline_run.py`
   routers' in-memory `_jobs: dict[...]` job registries. Those dicts made a submitted-run job
   **non-durable**: a backend restart lost every job's status, so a poller kept hitting `running`
   forever for a job whose owning process was gone — the store makes that state (queued → running →
   complete/failed) survive a restart. A restart-recovered job that has no result on disk resolves
   to a new terminal status, **`lost`** (distinct from `failed`), so a poll never hangs. **No
   `PostgresJobStore` exists, and none is planned** — unlike items 3/6/7, a job record is
   short-lived, single-node scratch bookkeeping (which process launched which subprocess, on THIS
   machine) rather than shared product state a second reader needs, so the two local backends
   (JSONL default, SQLite for a real-DB deployment) suffice; `.nf-runs/jobs.{events.jsonl,sqlite}`
   are the default sinks, already gitignored (the same scratch home both routers use). The module
   is also the single home for the shared driver-launch primitive both routers now call
   (`run_driver()` + one `DRIVER_TIMEOUT_S = 1800`, was 900s intake / 1800s Builder-run,
   diverged): `subprocess.Popen(..., start_new_session=True)` makes the driver a process-group
   leader, so a timeout `os.killpg`s the WHOLE Nextflow/JVM/tool subtree instead of
   `subprocess.run(..., timeout=…)`'s direct-child-only reap, which orphaned the subtree
   (P3-7). Run-id reservation is now **atomic**: the run-dir-exists check and the in-flight `_active`
   set membership check happen together under one `threading.Lock`, so two concurrent submits of the
   same id can no longer both proceed to launch a thread (P3-8) — the loser now gets a clean 409
   instead of racing the winner. See
   [data/schemas.md §Persistence](../data/schemas.md#persistence-databases) and
   [architecture.md §Swappable seams](../design/architecture.md#swappable-seams-the-flex-points).
9. **A sixth instance, and the second that deliberately stays TWO-backend: the tool-card library
   store (2026-07-11, T-135, "W2 backend").** `api/library_store.py` (`LibraryStore` Protocol +
   `JsonlLibraryStore`/`SqliteLibraryStore`, `PIPEGUARD_LIBRARY_STORE=jsonl|sqlite`, default
   `jsonl`, degrade-to-JSONL on any construction failure — the same discipline as every store
   above) holds `LibraryEntry` records: a node-authoring `NodeProposal`
   ([agent-authoring-contract.md](../design/agent-authoring-contract.md)) a human has **accepted**
   into the tool-card library, via the new `POST /api/builder/node-proposal/accept`
   (`reviewer`/`approver`, `api/routers/node_author.py`). Like the job store (item 8), **no
   Postgres adapter exists, by design**: a library entry is a small, node-local corpus of accepted
   drafts (metadata — ports, a pinned version, suggested locators, citations; never a
   `script:`/`stub:` command body), not high-volume shared product state, so the two local backends
   suffice. The accept endpoint **re-derives** the proposal server-side from the request (never
   trusts a client-supplied proposal) and runs it through a new deterministic
   [`src/pipeguard/node_author/conformance.py`](../../src/pipeguard/node_author/conformance.py)
   `check_conformance()` — the mechanical enforcement of
   `agent-authoring-contract.md`'s capability pins (advisory-True, no verdict/confidence anywhere,
   no `script`/`stub` command-body key, closed port vocabulary with unknown→reserved, versioned four
   ways) — before an entry can be stored, so a smuggled gate value or command body 422s rather than
   landing in the library. Each accept mints a fresh, immutable `draft` entry (`add`/`get`/`list`
   only, no in-place update); the `draft`→`approved` transition riding the `pipelines_lifecycle` RBAC
   pattern is a labelled deferred slice. `.env.example` also gained the previously-undocumented
   `PIPEGUARD_JOB_STORE`/`_PATH`/`_DB` vars in the same commit (a hygiene fix — those vars were
   already read by `api/job_store.py` since T-131, item 8, just never listed). See
   [data/schemas.md §Persistence](../data/schemas.md#persistence-databases),
   [design/agent-authoring-contract.md](../design/agent-authoring-contract.md), and
   [journal 2026-07-11 fleet](../journal/2026-07-11-fleet.md).

## Assumptions

- The projection is disposable and rebuildable from the ledger, so a backend swap is safe and
  needs no data migration — `rebuild-db` replays into whichever adapter the factory selects.
- Feedback telemetry is best-effort: a degraded write (DB down → JSONL, or a 503) is acceptable;
  it never blocks or influences a decision.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Make Postgres a hard dependency / the default | Breaks the offline, single-process, zero-dep demo + the guaranteed fallback (ADR-0014). The guarded, degrade-to-SQLite seam gives the production path without that cost. |
| Put feedback rows in the `Repository`/decision projection | Feedback is off-gate telemetry; mixing it with runs/cards/events couples it to the decision domain and risks it re-entering a view. A separate table + store keeps the boundary. |
| One shared Postgres connection/pool object | Deferred: per-op short-lived connections are simplest + thread-safe for the demo scale; a pool is the documented next step. |
| Skip SQLite, only build Postgres | Postgres can't be exercised offline (no server), so the DB path would be untested. SQLite is the offline-testable DB that proves the seam; Postgres is the same code in a different dialect. |

## Consequences

| | |
|---|---|
| **Gains** | The anticipated production DB seam is real + guarded; feedback lands in a queryable DB; a backend swap is one env var; the offline demo/tests are untouched (no new dep, no socket). |
| **Costs** | A second SQL dialect to keep in parity with `SqliteRepository`; `psycopg` connect logic now exists in **six** off-gate places (repo + feedback + pipeline + settings + review + share stores, confirmed via `grep -rln "class Postgres" api/ src/` — was "three" when this row was first written, before the settings/review/share stores existed). **A seventh AND an eighth pluggable store — the job store (item 8) and the library store (item 9) — deliberately do NOT add a seventh/eighth Postgres dialect**: `grep -rln "class Postgres" api/ src/` still returns exactly the same six files (verified 2026-07-11), and neither `api/job_store.py` nor `api/library_store.py` defines a `class Postgres*` — so the dialect-parity cost above is unchanged by either. The Postgres SQL is not in the default-green CI path (it needs docker + the extra) — covered by the compose-gated live test + offline dialect review + parity tests. |
| **Follow-ups** | ~~A live-Postgres integration test~~ **DONE** (`tests/test_persistence_postgres_live.py` — compose-gated, skip-safe; verified green against real Postgres 16: projection byte-parity vs SQLite, idempotent replay, feedback JSONB round-trip, and — added 2026-07-11 — share-store round-trip; the review's UTC + `seq` fixes hold). Still open: connection pooling; Alembic-style migrations if the layout ever needs a non-disposable change; wiring the read-API to read the projection (today it recomputes); **multi-worker safety for every pluggable store, incl. the job and library stores** (a file lock / DB transaction) — the same honest, unchanged limit item 8 above notes for `api/job_store.py`'s `_WRITE_LOCK` (a single-process lock, not a cross-process one; `api/library_store.py`'s `_WRITE_LOCK` carries the identical limit). |

## Revisit when

- The read-API needs to serve from the projection (not recompute) — then Postgres read
  performance + pooling matter and the live integration test becomes load-bearing.
- Feedback volume warrants indexed queries / retention policy on the `feedback` table.
