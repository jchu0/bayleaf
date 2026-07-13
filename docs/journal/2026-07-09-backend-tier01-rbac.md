# Journal — 2026-07-09 (MST) — Backend Tier-0/1 vs the updated design (auth + RBAC surfaces)

| Field | Value |
|---|---|
| **Focus** | Read the design agent's updated deliverables (`briefs/`, `handoffs/01-03`, the evolved `source/bayleaf.dc.html`), extract every backend obligation, and build the parallel-safe near-term backend the design assumes. |
| **Outcome** | Gap analysis (75 raw obligations → tiered). Built + shipped (2 commits, [e096bd7](#), [7855333](#), pushed; **317 tests**, mypy strict + ruff clean): the auth/RBAC primitive, three draft→approve RBAC surfaces (settings authoring = T-051, review-queue, pipeline lifecycle), the card-readout projection, and the Tier-0 runs-list reconciliations. ADR-0017 captures the decision. Tier-2 north-star surfaces deferred with a scope flag. |

## Discussion

**The design expanded a lot.** The evolved prototype (`bayleaf.dc.html`) is a north-star with
whole new surfaces (run submissions/ingest, a BaseSpace connector, conversational triage chat,
ticketing, two more advisory agents, a run hand-off). The three handoff READMEs are the nearer-term
spec. I fanned out five readers (brief + 3 handoffs + the prototype's `support.js` data layer) to
pull backend obligations into a structured list, then classified each against the shipped backend:
**already-shipped** (runs pagination, `/api/monitoring`, RunSummary status/platform/date, pipeline
save/version, full evidence), **Tier-0** cheap reconciliations, **Tier-1** real near-term work, and
**Tier-2** north-star. The maintainer chose "tackle all these in parallel, non-blocking" — i.e.
Tier-0 + Tier-1 + the auth foundation.

**Two load-bearing findings shaped the build.** (1) **Auth/identity is the cross-cutting unlock** —
every draft→approve flow (Builder, Settings, Review-queue) needs a real current-user+role source,
today hardcoded in the UI. Build it once and three tiers light up. (2) **Compose ≠ execute is at
risk** — the prototype's "Submit to pipeline" / "Hand off to Nextflow" push toward *running*
pipelines; per ADR-0001/0003 the gate emits config and hands off, never executes. So the
run-trigger surfaces stayed out, and the pipeline dry-run is strictly read-only.

**Two design choices kept the blast radius small.** (a) The Decision-card **QC readout is an
API-layer projection** (`api/card_readout.py` joins the card's `metric_values` with runbook
thresholds) rather than a core `DecisionCard` change — so the deterministic gate is untouched and
the demo-pinned verdict tests can't be perturbed. (b) New feature areas became **routers +
stores** (`api/routers/`, `api/settings_store.py`, `api/review_store.py`), each additive and
independently testable — which is exactly what let five tracks build in parallel with disjoint
file ownership, then integrate into `main.py` centrally.

**Kept `needs_review` (not renamed to the design's `review`).** It's descriptive and already
documented/tested; the frontend maps it for display. Cheaper than churning the shipped
contract/docs.

**Auth is honestly an MVP shim.** Header-trust with a permissive dev-default (role=approver) keeps
the offline demo/tests green with zero wiring; `current_actor` is the single swap point for a real
provider. Documented as such — it is not a production auth boundary yet (ADR-0017).

## Decisions

| Decision | Distilled to |
|---|---|
| An identity+RBAC primitive (dev shim) + one draft→approve lifecycle across pipeline/settings/review stores | [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), `api/auth.py` |
| Decision-card QC readout as an API-layer projection, core gate untouched | `api/card_readout.py`; [architecture.md](../design/architecture.md) |
| New surfaces as additive routers+stores (parallel-safe), integrated into main.py centrally | [architecture.md](../design/architecture.md); [CLAUDE.md](../../CLAUDE.md) code map |
| Tier-0: runs `status` filter + platform-aware `q` + sort aliases + facet-count header; keep `needs_review` name | [functional.md](../requirements/functional.md) REQ-F; [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md) |
| Defer Tier-2 (submissions/ingest, BaseSpace, chat triage, run hand-off, +2 agents) pending a scope call; keep compose≠execute | this journal; [tasks.md](../planning/tasks.md) |

## Open questions & TODO

1. **Tier-2 scope** — a maintainer call: run submissions/ingest, BaseSpace connector, conversational
   triage, pipeline-repair + archivist agents, run hand-off. The run-trigger ones must preserve
   compose≠execute.
2. **Decision-card CORE enrichment** still owed for the full design: per-gate sub-verdict rollup,
   linked-sample cross-link (S4↔S5 swap), sample-provenance metadata, context-rail fields. These
   touch the core card and were deliberately NOT in this burst (gate-output risk).
3. **Real identity provider** behind `current_actor`; **median-review-time KPI** wiring (the review
   store already records the timestamps); applying an approved config override onto a per-run
   Runbook copy at gate time.
4. **Non-backend flag:** the design agent rewrote the root `README.md` 280→49 lines in the working
   tree (left uncommitted) — likely dropped the guardrails/disclaimer; worth a look before it lands.

## Distilled into

- [docs/adr/ADR-0017-identity-rbac-authoring-lifecycle.md](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md) — the decision (new)
- [docs/planning/tasks.md](../planning/tasks.md) — T-051 done + new rows
- [docs/requirements/functional.md](../requirements/functional.md) · [design/architecture.md](../design/architecture.md) · [CLAUDE.md](../../CLAUDE.md) code map
- [docs/design/frontend/handoffs/2026-07-09-backend-contracts.md](../design/frontend/handoffs/2026-07-09-backend-contracts.md) — the new endpoint/header contract for the frontend
