# Journal — 2026-07-09 (MST) — Backend parallel build (scale + authoring seams)

| Field | Value |
|---|---|
| **Focus** | While design works the frontend review→design brief, build the backend seams the brief tags "needs a new field/endpoint before the UI can be honest" — run lifecycle status/platform/date (A), synthetic data at scale (B), windowed monitoring + runs pagination (C), Pipeline Builder save/version store (D). |
| **Outcome** | A/B/C/D shipped in two commits ([7ebf660](#), [44c898a](#)); **258 tests pass**, mypy strict + ruff clean, pushed. D reconciled to the maintainer's builder-versioning decision (reserve draft→approve + RBAC). Task E (config authoring store) **deferred** with reasoning. All additive/backward-compatible; no verdict/rule logic touched; zero `frontend/` edits (design owns it). |

## Discussion

**Why parallel, and how it was partitioned.** The four tasks are the backend half of the
T-045 scale/authoring backlog — independent of the frontend design pass, and living entirely in
`src/pipeguard/` · `api/` · `data/` · `tests/`. They were built by a 4-agent workflow with
**disjoint file ownership**. The one real coupling: **A, C, D all edit `api/main.py`**, and **C
depends on A** (honest time-windowing needs A's real run date — the core `created_at` timestamps
cluster at server-recompute time, useless for recency). So the workflow ran a **sequential
A→C→D chain** (shared `main.py`) **alongside an independent B track** (`synthetic/` + `data/`).

**A — honest run status.** The bug: the runs list inferred "Released" from `n_attention === 0`,
so a still-running run with zero attention was mislabeled Released. The fix grounds status in
provenance, not a proxy: `running` until the `ANALYSIS_RUN_COMPLETED` event lands, then
`needs_review` if any sample is actionable, else `released`. Platform + date already sat unparsed
in the SampleSheet `[Header]` — now surfaced (raw ISO date string, no fabricated datetime).
Status is a run-**lifecycle** label, explicitly not a per-sample verdict (invariant 1 holds).

**B — real volume, honestly tagged.** The generator was already production-shaped, so scale was
a thin driver + zero-padded IDs (which fix a genuine latent bug: the log rule's `sid in line`
substring match made un-padded `S1` match `S10..S19`). One 30-sample run is **committed** as a
scale showcase; bulk volume regenerates on demand into a **git-ignored** sink (repo stays lean).
Also fixed a data-hygiene drift: `generate_run` now writes the `origin` marker itself, and the
marker + in-band log tag agree on `contrived` (the label the data docs define for
generated-from-a-failure-spec runs) — the drifted mock_run_02/03 markers were corrected.

**C — move the aggregation server-side.** Monitoring N-fanned-out every run's full detail and
summed *lifetime* totals in the browser. New `GET /api/monitoring` returns that payload
pre-aggregated with an optional 7d/14d/30d window (reusing `_aggregate_metrics`, kept in the API
layer per the architecture guardrail); `GET /api/runs` gained `verdict/q/sort/page/limit`
(byte-identical with no params). `auto_proceed_pct` is labeled a heuristic throughput ratio, not
a calibrated value.

**D — a store that tolerates churn, and reserves the review flow.** The Builder's node/edge shape
is still moving under the design pass, so the store keeps the graph as a **tolerant versioned
envelope** (arbitrary JSON kept as-is), mirroring the `FeedbackStore` seam (pluggable
JSONL/SQLite/Postgres, degrade-to-JSONL, never logs the DSN). After the build, I **reconciled D
to the maintainer's just-made builder-versioning decision** (draft→save→approve with
reviewer/approver RBAC, reserve version+status now): the envelope now reserves a `status`
lifecycle (draft/pending_review/approved) + `submitted_by`/`reviewed_by`/`approved_by` — all
**server-authored** when auth lands, never client-set, so no identity/PII enters through the
`extra="forbid"` body. The approve transition + auth are a documented, not-yet-built seam.

**Central verification caught one real thing.** The full suite flagged
`test_metrics_prometheus_exposition`, which pinned `runs_total 3 / samples_total 17` — B's new
committed scale run legitimately makes it 4 / 47. Rather than re-pin a brittle magic number I
made the test **robust**: it now cross-checks the Prometheus exposition against the `/api/runs`
aggregates (a genuinely separate code path), so a future fixture can't silently falsify it
(Doc-update map row 130).

**Why E (config/settings authoring store) was deferred, not built.** It looks like a sibling of
D, but its value is the **"sanity guardrails"** design asked for — config-*specific* validation
(threshold ranges) tied to the settings surface design is actively reworking. Building it now
would either mismatch their final shape or duplicate D's store *without* the validation that
justifies it — the scope-over-broadening case to hold on. Captured as a proposed task for the
maintainer's call.

**Commit granularity, honestly.** A/C/D share `api/main.py`, and interactive hunk-staging
(`git add -p`) isn't available in this environment, so they could not be split without risking a
non-building intermediate. They landed as one coherent "backend read-API + authoring seams"
commit (lettered A/C/D in the body); B is a clean separate commit.

## Decisions

| Decision | Distilled to |
|---|---|
| Run status is an honest tri-state from provenance (`running`/`needs_review`/`released`), NOT an `n_attention===0` inference; platform/run_date surfaced from the SampleSheet `[Header]` | [schemas.md](../data/schemas.md), [functional.md](../requirements/functional.md), [architecture.md](../design/architecture.md) |
| Windowed monitoring is a server-side aggregate (`GET /api/monitoring`, reusing `_aggregate_metrics`); runs list gains additive pagination/search | [architecture.md](../design/architecture.md), [functional.md](../requirements/functional.md), [data-platform-and-archivist.md](../design/data-platform-and-archivist.md) |
| The pipeline store is a tolerant versioned envelope reserving a draft→save→approve + reviewer/approver RBAC lifecycle (server-authored, no PII); a product store off the gate, mirroring FeedbackStore | [ADR-0016](../adr/ADR-0016-postgres-port.md), `api/pipeline.py`, [tasks.md](../planning/tasks.md) |
| Generated-run origin is `contrived` end-to-end (marker + log tag agree via `ORIGIN_LABEL`); definitions unchanged | [data/README.md](../../data/README.md), [strategy.md](../data/strategy.md) |
| Census-style tests cross-check a separate code path, not magic pins (prometheus ↔ `/api/runs`) | [evaluation.md](../quality/evaluation.md) |
| **Task E (config/settings authoring store) deferred** — its value (sanity-guardrail validation) is coupled to design's not-yet-final settings surface; don't duplicate D without it | [tasks.md](../planning/tasks.md) T-047 (proposed) |

## Open questions & TODO

1. **Task E** — maintainer's call whether to build the config/settings authoring store now
   (backend seam is design-independent; the validation is not). Proposed as T-047.
2. **Frontend rewire (design):** Monitoring should drop its N-fan-out and read `GET /api/monitoring`;
   the runs list should adopt `page/limit/verdict/q/sort`; RunOverview should read `summary.status`
   instead of inferring Released. These are contract-documented in the backend-contracts handoff.
3. **Honest window caveat:** the 7d/14d/30d windows anchor on `datetime.now(UTC)`; the committed
   fixtures are dated 2026-07-07..09, so dated windows only stay populated while wall-clock is near
   July 2026 (`window=all` is always correct). The window mechanics are unit-tested deterministically.

## Distilled into

- [docs/planning/tasks.md](../planning/tasks.md) — T-046 (node-authoring, prior) unchanged; A/B/C/D marked done; T-047 (config store) proposed
- [docs/requirements/functional.md](../requirements/functional.md) + [scope-and-wishlist.md](../requirements/scope-and-wishlist.md) — new REQ-F + built-status
- [docs/design/architecture.md](../design/architecture.md) + [data-platform-and-archivist.md](../design/data-platform-and-archivist.md) — API surface
- [docs/data/schemas.md](../data/schemas.md) — RunArtifacts fields · [strategy.md](../data/strategy.md) + [data/README.md](../../data/README.md) — synthetic scale
- [docs/adr/ADR-0016-postgres-port.md](../adr/ADR-0016-postgres-port.md) — the pipeline store as a new domain on the store seam
- [docs/quality/evaluation.md](../quality/evaluation.md) — test census · [CLAUDE.md](../../CLAUDE.md) — code map
- [docs/design/frontend/handoffs/2026-07-09-backend-contracts.md](../design/frontend/handoffs/2026-07-09-backend-contracts.md) — the new field/endpoint contract for design
