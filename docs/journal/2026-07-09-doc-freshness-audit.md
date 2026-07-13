# Journal — 2026-07-09 (MST) — Doc-freshness audit (post-backend-batch drift sweep)

| Field | Value |
|---|---|
| **Focus** | While waiting on the frontend design, verify the whole doc corpus is fresh against the current code — a large backend batch (A/B/C/D + the Tier-0/1 RBAC surfaces) had landed and docs could lag despite in-flight sweeps. |
| **Outcome** | A 5-agent **read-only** audit (requirements · design · data · ADRs · planning/meta), each cross-checked vs code, surfaced **14 findings**. Fixed **13** (docs-only) via 4 disjoint write-agents; verified landed + docs-only. **1 flagged, not touched** — the root `README.md` (overwritten with the design handoff in the working tree; it's the maintainer's active design WIP). |

## Discussion

**Why audit rather than trust the sweeps.** The per-batch doc sweeps were done under time pressure
across many files; a cold, code-grounded audit is the honest check. Used **Explore** (read-only)
agents so the audit couldn't silently edit, then fanned out **write** agents by disjoint file to fix.

**The drift was almost entirely "built feature still marked deferred/reserved"** — the tell of docs
written before the feature and never revisited:
1. The **pipeline approve lifecycle** + **auth** were called a "not-yet-built seam" in three places
   (functional REQ-F-045, ADR-0016 item 6) though `pipelines_lifecycle.py` + `auth.py` ship them.
2. The **review-queue Ticket lifecycle** (ADR-0010) and **reviewer/approver RBAC** (ADR-0008) were
   marked deferred though `review_queue.py` + `auth.py` ship them.
3. The **notify seam** (architecture.md) listed only `stub|slack` — Teams + Discord adapters exist.
4. The **third AI seam** (feedback-triage agent) was missing from the seam table / "both AI seams".
5. Stale counts + contracts: the **test census** (one-pager: 159/10 → 320/19), `DecisionCard`
   missing **`metric_values`** in schemas.md, `/api/runs` §4.4 lagging (q-by-platform, status filter,
   facet header), the `metric_registry` `category` documented as a closed enum vs the code's free
   string (missing `run_qc`), and two tasks (T-036/T-040) falsely marked "unmerged" (both on main).

**The README is a genuine problem but not mine to fix here.** The repo-root product README was
overwritten (working tree) with the frontend design-handoff doc ("these are design references, not
shippable code"). That's wrong for the front door of a shipped/tested product, but it's part of the
maintainer's uncommitted design drop (`briefs/`, `handoffs/`, `source/`, `bayleaf.html`) — so it's
their call to restore + relocate, not something to revert unilaterally. Surfaced with a recommendation.

## Decisions

| Decision | Distilled to |
|---|---|
| Doc-freshness audit is a read-only Explore fan-out; fixes are disjoint write-agents, verified centrally | this journal |
| README restoration (product README vs design-handoff overwrite) is deferred to the maintainer (their WIP) | flagged in chat; not edited |

## Open questions & TODO

1. **README.md** — restore the product README (`git checkout HEAD -- README.md`) + move the design
   bundle under `docs/design/frontend/`? Awaiting the maintainer's call.

## Distilled into

- Fixed: [architecture.md](../design/architecture.md), [data-platform-and-archivist.md](../design/data-platform-and-archivist.md), [schemas.md](../data/schemas.md), [metric_registry.md](../data/metric_registry.md), [functional.md](../requirements/functional.md), [ADR-0008](../adr/ADR-0008-issue-taxonomy-suppression-escalation.md)/[0010](../adr/ADR-0010-ticketing-notify-read-api.md)/[0016](../adr/ADR-0016-postgres-port.md), [one-pager.md](../demo/one-pager.md), [tasks.md](../planning/tasks.md)
