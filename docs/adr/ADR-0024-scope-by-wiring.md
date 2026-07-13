# ADR-0024 — Scope-by-wiring: agent file access derived from wired-tool output folders

| Field | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-07-13 (MST) |
| **Deciders** | maintainer (James), Claude |
| **Related** | [ADR-0022](ADR-0022-agent-observation-binding.md) (observation binding — this advances it), [ADR-0023](ADR-0023-agent-taxonomy-and-action-boundary.md), [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0020](ADR-0020-operator-authored-custom-processes.md) (sandboxed `GET /api/files`), [ADR-0005](ADR-0005-config-layer-and-profiles.md) (profiles), [design/agents.md](../design/agents.md) |

## Context

How much of a run an agent may read is currently governed two ways: a scoped node-read endpoint
(`GET /api/runs/{id}/nodes/{node}/observations`, `gather_node_observations` — ADR-0022) and a
**client-side-only advisory `AgentBinding`** that the server neither persists nor enforces. ADR-0022
explicitly deferred "persist bindings server-side, link a run to the graph it executed, intersect
grants." Separately, agent "granularity" has floated as a possible Settings control.

The maintainer's insight collapses both problems into one: **an agent's access should be exactly
the output folders of the tools it is wired to in the pipeline graph.** QC-triage wired to fastp +
mosdepth + MultiQC → read access to *those three tools' output folders*, dynamically. Wire it to
more tools → more access. This makes scope a **direct, visible property of the graph** the operator
already draws — no separate settings surface, no abstract permission model.

Two facts constrain the implementation: (1) real run data lives under an **operator-configured
data root** (e.g. an external volume like `/Volumes/James_T7/bayleaf-data`), never assume repo-local
`data/`; (2) a tool's output folder can contain PII-adjacent logs.

## Decision

1. **Scope = wiring.** A run-time agent's readable file set is the **union of the output folders
   of the tool nodes it is connected to by an edge** in the executed graph. No edge → no access.

2. **Server-enforced binding** (advances ADR-0022 from advisory hint to enforced): persist the
   agent↔node bindings, link a run to the **graph it actually executed**, and at read time
   intersect the request against `{output folders of wired tools} ∩ {run's executed graph}`.
   A binding that isn't backed by a real edge in the executed graph grants nothing.

3. **Paths resolve from the configured data root**, not repo-local `data/`. Tool output folders
   are computed as `‹run data root›/‹run id›/‹tool node output dir›`; the data root is an
   operator setting (reuses the `BAYLEAF_BROWSE_ROOTS` allowlist).

4. **Reuse the existing sandbox + de-id.** All reads go through the `GET /api/files` hardening
   (`resolve()` + `is_relative_to()` an allowlisted root, read-only, traversal-safe, ADR-0020)
   and `api.deid.scrub_text`. `outputs` grant = viewer+; the PII-adjacent `logs` grant = reviewer+
   (unchanged from ADR-0022's floor).

5. **Access ≠ authority (ADR-0001 preserved).** A wired agent can *read* a tool's outputs; it can
   never set/alter a verdict, finding, confidence, or data content. Scope-by-wiring governs
   *reading*, not deciding.

6. **Retire settings-based agent scoping.** There is no separate "agent granularity" Settings
   control to build; the graph is the control surface. Separately, the **"Operator profile"
   lean/granular bar** in Settings is a view-only, non-persisted toggle that duplicates the
   persisted **"Card density"** preference — consolidate it into Card density and remove the bar
   (a UI cleanup, not an agent-scope change).

## Assumptions

- The executed graph is (or can be) recorded per run — required to link a binding to reality.
- Tool nodes have a well-defined output directory the compiler/driver can name deterministically.
- Operators find "draw an edge to grant access" more legible than a permissions matrix.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Keep the client-side advisory `AgentBinding` (ADR-0022 status quo) | Not enforced — any viewer could request any node; the maintainer wants real, wiring-derived scope. |
| A Settings permissions matrix / "agent granularity" control | Another abstract surface to build + keep in sync with the graph; the graph already expresses the relationships. |
| Grant access to the whole run dir once any node is wired | Violates least-privilege; the point is per-tool granularity the operator dials via edges. |

## Consequences

| | |
|---|---|
| **Gains** | Least-privilege, operator-legible agent scope with zero extra config UI; closes ADR-0022's deferred enforcement; correct on external/operator-configured data roots. |
| **Costs** | Must persist bindings + record the executed graph per run; must resolve tool→folder paths robustly across data roots; enforcement path needs tests (an unwired folder must be unreadable). |
| **Follow-ups** | Persisted binding store + run→graph link; path resolver keyed on the configured data root; a test that an agent cannot read a tool folder it isn't wired to; the Settings profile-bar → Card-density consolidation. |

## Revisit when

- A legitimate agent need can't be expressed as "wire an edge" (e.g. cross-run reads — that's the
  archivist's DB path, ADR-forthcoming, not file wiring).
- Output-folder layout stops being deterministically nameable from the graph.
