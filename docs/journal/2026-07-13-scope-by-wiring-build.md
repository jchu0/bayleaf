# 2026-07-13 (MST) — Scope-by-wiring (ADR-0024) build: server-enforced agent file access

**Topic:** Built P2 — turned ADR-0022's client-side advisory `AgentBinding` into ADR-0024's
server-enforced scope: an agent may read a node's observations ONLY if it is wired to that node in
the run's executed graph, capped to the binding's grants.

## Key discovery (kept scope tight)

The Builder graph is stored as an **opaque `dict[str, Any]` round-tripped byte-for-byte**, and the
frontend already sends `agent_bindings` inside it (`PipelineBuilder.tsx:499`). So `graph.agent_bindings`
already persists server-side — **no envelope schema change was needed** (my first fear). The real
gaps were only the run→executed-graph linkage and the enforcement, exactly as ADR-0022 deferred.

## Increments (each its own commit, `make check` green)

1. **`80b51a9` P2.1 store + resolver** — `api/agent_binding_store.py` (run→bindings over the shared
   store generic; jsonl/sqlite/postgres, degrade-to-JSONL). Two pure helpers: `normalize_bindings`
   (tolerant coercion of arbitrary client JSON) and `granted_grants` (bound→grants; **NOT-bound→None**,
   the deny signal, distinct from bound-but-`[]`). 5 offline tests.
2. **`f827b43` P2.2 capture + P2.3 enforce** —
   a. *Capture* (`pipeline_run.py`): at Builder-Run launch, `normalize_bindings(record["graph"]
      ["agent_bindings"])` is snapshotted to the store keyed by `run_id`, right after the run is
      committed to launch (never for a run that 422s). Compiler still never dereferences bindings —
      compile byte-identical (ADR-0022 preserved).
   b. *Enforce* (`node_observations.py`): a new optional `agent` query param. When supplied AND the
      run's bindings were captured, the agent must be wired to the node (else **403**) and the
      response grants are **capped** to the binding's grants. Node-scope + wire-role gates still
      apply underneath. Additive back-compat: no `agent`, or an uncaptured run → prior behavior.
   c. 5 offline enforcement tests (unbound→403, bound→200, grants capped, two back-compat).
3. **P2.4 Settings cleanup** (this commit) — removed the view-only "Operator profile" (lean/granular)
   bar (ADR-0024 §6): it was a non-persisted local toggle that only gated the Metric-catalog section,
   which now always shows. `Density` ('split'/'brief'/'dense') is card *layout*, a different axis, so
   nothing merged into it; the lean/granular config PROFILE stays an ADR-0005 backend concept.

## Verification

`make check` green (full suite **761 passed / 8 skipped**, mypy 100 files, ruff clean); frontend
`tsc -b` + vite + lint clean. Access ≠ authority held throughout (ADR-0001): bindings govern
*reading* a node's files, never a verdict.

## Honest deferrals (labelled in ADR-0024 status)

1. **Only Builder-Run captures** bindings today; the intake-authored-run path (`api/routers/intake.py`)
   shares `resolve_approved` and can capture the same way — a small follow-up.
2. Enforcement is **opt-in by the `agent` param**: the agent-consumption path (agents reading their
   own scoped view) isn't wired yet (ADR-0022 deferral), so nothing passes `agent` automatically in
   production yet. The mechanism is ready + tested; the caller is the remaining wire-up.

**Related:** [ADR-0024](../adr/ADR-0024-scope-by-wiring.md) · [ADR-0022](../adr/ADR-0022-agent-observation-binding.md) ·
[ADR-0023](../adr/ADR-0023-agent-taxonomy-and-action-boundary.md) · [agents.md](../design/agents.md) ·
[TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md)
