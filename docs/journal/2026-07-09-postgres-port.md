# Journal — 2026-07-09 (MST) — Postgres port + feedback→DB + feedback agent

| Field | Value |
|---|---|
| **Focus** | Three maintainer asks off W12: (1) icon-only feedback FAB, (2) feedback into a database ("we already have postgres"), (3) trace fidelity + a feedback-categorization agent. |
| **Participants** | James Hu, Claude Code (+ a review workflow of subagents). |
| **Outcome** | FAB icon-on-hover; the full Postgres port (PostgresRepository + pluggable feedback store) landed guarded OFF-by-default; a required `source` trace field; an advisory feedback agent. ADR-0016 recorded. 223 tests green. |

## Discussion

**#1 — FAB.** Made the global feedback FAB an icon-only circle that expands leftward to the
"Feedback" label on hover (icon stays anchored at the fixed corner). Standard `group-hover`;
aria-label/title keep it accessible collapsed.

**#2 — the DB, and a corrected premise.** The maintainer said "we already have postgres so
lets use it." We don't — the persistence layer is `SqliteRepository` (stdlib, zero-dep), and
the code explicitly documents Postgres as the *"later"* adapter behind the `Repository` port;
the only docker-compose is for telemetry. Surfaced that via a question rather than acting on the
premise; the maintainer chose **"scope out the full port to postgres."**

Built it as a **guarded production seam**, mirroring the S3 artifact-store pattern so the
offline demo/tests stay zero-dep and never open a socket:
- `PostgresRepository` implements the `Repository` port, behaviourally identical to the SQLite
  adapter — same five tables, `ON CONFLICT DO UPDATE` idempotent upserts (replay stays a no-op,
  ADR-0002), `JSONB` + `TIMESTAMPTZ`, a `bayleaf_meta` layout-version row. `psycopg` is lazy
  (the `[postgres]` extra); the module imports fine without it.
- `get_repository()` flips `BAYLEAF_REPOSITORY=sqlite|postgres` and **degrades to SQLite on
  any failure**, logging the exception *type* only — never `str(exc)`, which could carry the DSN
  password. `rebuild-db` now targets either backend.
- **Feedback is a separate concern from the decision projection.** A pluggable `FeedbackStore`
  (`jsonl` default | `sqlite` | `postgres`) with its own `feedback` table, never the Repository,
  and a writer that never imports the core — so feedback stays off the gate (ADR-0001).
  `SqliteFeedbackStore` is a real DB that's **offline-testable**, so "feedback in a database" is
  proven end-to-end in tests without a live Postgres.

Postgres can't be exercised offline (no server), so — like the S3 seam — it's covered by
dialect review + parity tests (factory selection, degradation, no-DSN-never-connects, identical
table set), not CI against a live DB. `deploy/postgres/docker-compose.yml` (dev-only password
via an env default) is there for when someone wants to run it.

**#3a — trace.** Assessed the existing trace: decision feedback already carries route + screen
+ run/sample + verdict + gate + rule_ids + the card `content_hash` — strong. Added one required
`source` field (the exact UI surface: `decision-card` | `product-fab` | …), distinct from
`target`, so future surfaces (triage-note, review-queue) stay traceable. Both frontend surfaces
send it.

**#3b — feedback agent.** An advisory agent mirroring the QC-triage seam (stub-first / opt-in
Claude / deterministic fallback, `BAYLEAF_FEEDBACK_AGENT`). It reads the `FeedbackStore` and
emits a structured `FeedbackAssessment` — per-item category/area/sentiment/priority from the
structured fields + an aggregate rollup + recurring themes. Off-gate, no HTTP surface (run via
`python -m api.feedback_agent`). **PII-safe:** the deterministic path parses no message text,
and the Claude path is sent only the anonymous aggregate rollup — never a raw message or id.

**Process note.** The uncommitted `docs/design/frontend/` churn (the maintainer's separate
Pipeline-Builder work) collided with pre-commit's stash/rollback when a hook touched a staged
file; worked around it by stashing that churn myself before each commit, then restoring it. Left
it entirely untouched throughout.

## Decisions

| Decision | Distilled to |
|---|---|
| Full Postgres port as a guarded, OFF-by-default seam (degrade to SQLite; `[postgres]` extra; mirrors S3) — NOT a hard dep / default | [ADR-0016](../adr/ADR-0016-postgres-port.md) |
| Feedback = a separate pluggable `FeedbackStore` (jsonl/sqlite/postgres), never the decision `Repository` | [ADR-0016](../adr/ADR-0016-postgres-port.md); [tasks.md](../planning/tasks.md) T-043 |
| Degradation logs exception *type* only + 503 never leaks the DSN/message | [ADR-0016](../adr/ADR-0016-postgres-port.md) §4 |
| A required `source` trace field; an advisory feedback agent with a PII-safe aggregate-only Claude path | [ADR-0016](../adr/ADR-0016-postgres-port.md) §5 |

## Open questions & TODO

- **Live-Postgres integration test** (compose-gated, opt-in) — the SQL dialect is review-checked,
  not CI-run.
- **Connection pooling** — per-op short-lived connections today; a pool is the next step.
- **Migrations** — the projection is disposable/rebuildable, so none needed yet; revisit if a
  non-disposable layout change ever lands.
- `psycopg.connect` logic exists in two off-gate places (repo + feedback store) — acceptable
  duplication to keep feedback off the core, flagged for the review.

## Distilled into

- [docs/adr/ADR-0016-postgres-port.md](../adr/ADR-0016-postgres-port.md) — the port scope
- [docs/planning/tasks.md](../planning/tasks.md) — T-043
