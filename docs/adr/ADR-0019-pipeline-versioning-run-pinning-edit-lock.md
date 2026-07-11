# ADR-0019 — Pipeline versioning, run-version pinning, and the edit-lock lifecycle

| Field | Value |
|---|---|
| **Status** | Proposed (maintainer design input 2026-07-11 MST — git-backing recommended, staged build; not yet built) |
| **Date** | 2026-07-11 (MST) |
| **Deciders** | maintainer (design dialogue 2026-07-11), Pipeline Builder implementation pass |
| **Related** | [ADR-0003](ADR-0003-deployment-agnostic-ports.md) (compose ≠ execute; Nextflow/git pipeline portability), [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md) (event-driven provenance ledger — run→version is provenance), [ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md) (RBAC + draft→approve authoring lifecycle; the versioned `PipelineGraphStore`, T-049), [ADR-0015](ADR-0015-layered-data-contract.md) (layered data contract), [ADR-0016](ADR-0016-postgres-port.md) (pluggable-store family), [ADR-0014](ADR-0014-productionization-fastapi-react.md) (FastAPI/React productionization), [design/frontend/README.md](../design/frontend/README.md) §6 (Pipeline Builder), [design/builder-cards/README.md](../design/builder-cards/README.md), [requirements/functional.md](../requirements/functional.md) (Pipeline Builder REQs), [planning/tasks.md](../planning/tasks.md) |

## Context

The Pipeline Builder began as a **read-only** view of a seeded "linked run" pipeline (`RUN-2026-07-07-A` → the germline chain). The maintainer wants its cards **editable / movable / removable**, like the composed (author-a-tool) nodes.

That surfaced a coupling. The per-card **run-status** (the left-spine indicator added in the card redesign) comes from the *linked run* (`vstatus` on the seeded tool cards); all *editing* lives in a separate editable-node layer (`UserNode`/`UserCard`) that has **no run**, hence no status. Making the same cards both editable **and** status-bearing forces a decision about how a pipeline relates to the runs that used it — i.e. **versioning and mutability**, not just a card visual.

The maintainer's model: a run is produced by a specific pipeline **version**; processed samples must stay **immutably linked** to the exact version that produced them (provenance). A pipeline that is **mid-run must be locked** against edits (no mid-run changes). Once its run is **complete or deliberately stopped**, the pipeline may be edited, and saving the edit **mints a new version** — the old version, and the samples pinned to it, are untouched.

## Decision

1. **Pipelines are versioned, immutable records.** Each Save mints a new immutable version in the existing
   `PipelineGraphStore` (the versioned envelope from ADR-0017 / T-049). A prior version is never mutated in place.
2. **A run pins `{pipeline_name, pipeline_version}`.** Every processed sample is linked to that exact version —
   immutable provenance (ADR-0002). Viewing/editing a run's pipeline happens on the Builder screen, which shows the
   pinned name + version and the run's per-step status.
3. **Edit-lock lifecycle keyed to run state.** While a run is **active** (in-progress) its pinned pipeline version is
   **locked** (read-only) — this is what makes the run-status meaningful and prevents mid-run drift. When the run is
   **complete or stopped**, the pipeline becomes **editable**, and the edit is a *new version* on Save. (The demo's
   linked run is complete, so it is editable; a still-running run stays locked.)
4. **Git is the versioning *model*, the store is the *implementation*, git-backing is the production *seam*.** Real
   genomics pipelines are git-versioned (Nextflow/nf-core; ADR-0003, "compose ≠ execute"), so run→version pinning is
   conceptually a git ref — which gives immutable versions, real version-to-version diffs (the Builder's Diff tab), and
   lineage. For now this is realized through the versioned `PipelineGraphStore` (**no live `git` calls from the app**);
   backing that store with a git repository (one commit/tag per version; runs pin a revision) is a documented
   **production seam**, not built in the demo.

## Assumptions

- The existing `PipelineGraphStore` versioned envelope (ADR-0017 store family; jsonl/sqlite/postgres) can carry an
  immutable per-version record plus a run→version pin.
- Run state (active vs complete/stopped) is derivable — the intake-execution boundary
  (`GET /api/runs/{id}/intake-status` → `queued|running|complete|failed`) already provides it.
- Editing a completed run's pipeline (→ a new version) does **not** rewrite history: the run and its samples stay
  pinned to the version they ran on.
- Git-backing can be added later without changing the app's contract (the store is the seam).

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Separate pipeline **folder** per version | Reinvents versioning, worse — no diff, no lineage, storage duplication; the Builder already has a Diff tab that wants version-to-version diffs. |
| **Live git** operations from the app now | Unneeded plumbing/infra for the demo; the versioned store already yields immutable versions. Git is kept as the production **backing** seam. |
| **Mutable** pipelines (edit in place) | Breaks provenance — a run's samples could no longer be reproduced against the exact pipeline that produced them. |
| **Always-editable** (no lock) | Permits mid-run edits → the run-status becomes meaningless and results non-reproducible. |
| Keep the Builder **read-only**, edit only via Fork-to-draft | The maintainer wants the run's own cards editable **in place**; a fork loses the run-status binding and reads as a disconnected copy. |

## Consequences

| | |
|---|---|
| **Gains** | Run-status and editability coexist coherently; immutable, reproducible provenance (sample → exact pipeline version); versioned profiles + a real Diff; a lock rule that prevents mid-run drift; a clean production path (git-backed store). |
| **Costs** | A real data model — runs must carry `{pipeline_name, version}`, the store must version immutably and expose a lock derived from run state; more surface than a card-visual tweak; delivered in two slices. |
| **Follow-ups** | **Slice 1 (frontend-led):** Builder renders the germline as editable `UserNode`s carrying the run's status; **locked when the run is active, editable-mints-a-new-version when complete**; + reference sources as nodes, FASTQ-input & output/sink cards, spine+branch layout, Save→new version via the existing store. **Slice 2 (backend):** real `run → {pipeline_name, version}` linkage + sample-version immutability + store version/lock semantics; the git-backed store seam. |

## Revisit when

- A run needs to span **multiple** pipeline versions (e.g. a resumed/patched run), which the single-pin model can't express.
- The versioned store outgrows jsonl/sqlite and **git-backing becomes the real backend** (promote the seam to an implementation).
- Regulatory/audit needs demand **signed, tamper-evident** version history beyond what the store provides.
