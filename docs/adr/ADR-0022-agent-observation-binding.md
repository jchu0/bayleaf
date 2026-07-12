# ADR-0022 — Agent attachment is a persisted, read-only observation binding (off the compiled graph)

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-12 (MST) |
| **Deciders** | maintainer (James Hu), doc-keeper |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md) (rules decide / AI advises) · [ADR-0003](ADR-0003-deployment-agnostic-ports.md) (compose ≠ execute) · [ADR-0012](ADR-0012-agent-scoping-model-tiering.md) (agent scoping / least-privilege) · [ADR-0018](ADR-0018-variant-interpretation-advisory-evidence.md) (the same conservative de-id module) · [design/agents.md](../design/agents.md) (roster + the observation-binding model + taxonomy) · [design/agent-authoring-contract.md](../design/agent-authoring-contract.md) (attach-as-observation, off the compiled graph) · [design/nextflow-codegen.md](../design/nextflow-codegen.md) (the compiler that never sees a binding) · `frontend/src/types.ts` (`AgentBinding`) · `api/routers/node_observations.py` (the read path) · `api/deid.py` (`scrub_text`) |

## Context

The Pipeline Builder lets an operator attach an advisory agent (e.g. QC-triage) to a
pipeline. Before this decision the attachment was an **ephemeral `advisoryAttach: Set<nodeId>`**
in React state: it was lost on reload, carried no grant granularity, and had no read path — an
attached agent could not actually *observe* anything. Two forces made that untenable:

1. **The attachment must persist and be scoped.** An operator who attaches QC-triage to the
   `mosdepth` node expects that intent to survive a save/reload and to mean something concrete —
   "this agent may read this node's results," not "this agent may read the whole run."
2. **The attachment must never touch what the pipeline runs or decides.** An agent lives off the
   deterministic critical path ([ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md)) and the
   core never runs a tool from agent-authored metadata ([ADR-0003](ADR-0003-deployment-agnostic-ports.md),
   compose ≠ execute). If an attachment could reach the Nextflow compiler, agent-driven state would
   become a route into codegen — exactly the seam those two ADRs exist to protect.

At the same time the Builder palette had drifted: it listed **Pipeline-repair** and **Archivist**
alongside QC-triage and Node-authoring, implying all four attach to a *node*. But repair and
archivist act on **runs / recurring signatures / the whole organization**, not on a single pipeline
node — mixing the two blurred what "attach an agent here" even means.

## Decision

1. **Model an attachment as a typed, persisted `AgentBinding`, not an ephemeral set.**
   `AgentBinding = { agent: string; node: string; grants: ('outputs'|'logs')[] }`
   (`frontend/src/types.ts`). A binding is an **observation grant**: it lets an agent *read* one
   graph node's results; it never wires a data edge, adds a card, or sets a verdict/confidence.

2. **Persist bindings in a SIBLING save-envelope key the compiler never dereferences.** Bindings
   live in `graph.agent_bindings` (a peer of `locator_edits` / `reference_locators` in
   `BuilderGraphPayload`, `BuilderShared.tsx`), **not** inside the compile/run payload. The
   compile/run payload stays a pure function of `{ nodes.map(toCompileNode), edges }`, and the
   backend `CompileRequest` is `extra="ignore"` — so a graph compiles **byte-identical with or
   without any binding**. An attachment structurally *cannot* alter the emitted Nextflow (compose ≠
   execute by construction) or a verdict (ADR-0001).

3. **Grants are least-privilege and default-safe.** `outputs` (the node's published artifacts) is
   the default and the only seeded grant; `logs` (the node's `.command.log`/`.command.err`) is
   **opt-in, off by default**, because a task log can echo subject-id PII. `reconcileBindings`
   (`BuilderShared.tsx`) prunes any binding whose node was deleted or whose agent is not
   node-attachable, and normalizes the grant array on load of a foreign/older envelope.

4. **Only node-scoped agents are attachable; system agents move off the canvas.** The attachable
   set (`ATTACHABLE_AGENT_IDS`) is **QC-triage today** — the one agent that reasons over a single
   node's results. **Pipeline-repair and Archivist move OUT of the Builder palette to Agent-triage
   launchers** (`screens/AgentTriage.tsx`), because they act on runs / signatures / the organization,
   not a node. The Builder palette keeps QC-triage (node-attachable) + Node-authoring (authors a
   card, roster #6).

5. **A binding is backed by a scoped, de-identified read path (Phase 4).**
   `GET /api/runs/{run_id}/nodes/{node_id}/observations?grants=outputs[,logs]`
   (`api/routers/node_observations.py`, `require_role("viewer", ...)`) returns the agent's granted,
   node-scoped view:
   a. `outputs` — the node's published files, scoped by matching the tool's **catalogued
      output-port `path(…)` globs** against the run's Nextflow publish dir
      (`.nf-runs/<run_id>/nf-out/results/`). Never the whole run — only this node's files.
   b. `logs` — the DE-IDENTIFIED tail of the node's task logs, routed through
      `api.deid.scrub_text` (pseudonymizes the run's known subject ids from `sample_metadata.csv`
      + regex-redacts email/6+-digit PII). Raw stderr is never emitted.
   The response model pins `advisory: Literal[True]` and carries no verdict/confidence field; the
   endpoint is traversal-hardened (bare `run_id`, every resolved path re-checked inside the run dir)
   and **honest-empty** (a fixture-only run, or an uncatalogued/authored-graph node, returns an
   empty view with a `note`, never fabricated outputs). `gather_node_observations()` is the reusable
   **triage-consumption seam**.

## Assumptions

1. The compiler will remain a pure function of `{nodes, edges}` — new save-envelope keys are
   metadata siblings, never compile inputs. (Enforced structurally: `CompileRequest` is
   `extra="ignore"`; the byte-identical-compile invariant is the proof.)
2. QC-triage is the only agent that benefits from a *node*-scoped view for now; repair/archivist are
   genuinely run-/org-scoped. Revisit if a new agent needs per-node attachment.
3. `scrub_text` is a **conservative demo heuristic, not HIPAA de-identification** — the same honesty
   posture as the rest of `api/deid.py` ([ADR-0018](ADR-0018-variant-interpretation-advisory-evidence.md));
   a validated NLP PHI scrubber stays a documented seam.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| **Keep the ephemeral `advisoryAttach: Set`** | Lost on reload, no grant granularity, no read path — an attached agent could observe nothing. This ADR is the replacement. |
| **Wire the agent as a real graph node/edge** | The compiler would dereference it and it could change the emitted Nextflow — a direct compose ≠ execute (ADR-0003) and ADR-0001 violation. The binding is deliberately OFF the compiled topology. |
| **Store bindings INSIDE the compile/run payload** | The compiler would see them; even if ignored today, the coupling invites a future codegen that reads them. A sibling envelope key the payload never includes keeps the byte-identical-compile invariant structural, not conventional. |
| **Grant whole-run read (the entire output tree)** | Over-broad — violates least-privilege ([ADR-0012](ADR-0012-agent-scoping-model-tiering.md)). A binding is a *narrowing* to one node's files, not a widening. |
| **Return raw task logs on the `logs` grant** | A tool can echo a subject id into a path or log line — raw stderr would leak PII. Logs are opt-in AND de-identified before they leave the machine. |
| **Leave repair/archivist in the Builder palette** | Implies they attach to a node; they act on runs/signatures/the org. Moving them to Agent-triage launchers makes the pipeline-vs-system agent taxonomy honest. |

## Consequences

| | |
|---|---|
| **Gains** | An attachment now persists, is grant-scoped, and is *backed by a real read path* — while being structurally incapable of touching the compiled pipeline or a verdict. The pipeline-vs-system agent taxonomy is explicit (node-attachable QC-triage/Node-authoring in the Builder; run-/org-scoped repair/archivist on Agent-triage). Least-privilege + de-identified logs keep the read path safe. |
| **Costs** | A second observation surface to keep honest (the endpoint's scoping globs must track the catalog). The de-id is a heuristic, not certified. Node → tool resolution only covers catalogued tools + the seeded germline graph's node ids. |
| **Follow-ups** | (a) **Agent consumption** — `gather_node_observations()` is the seam, but QC-triage does not yet call it (it stays a narrator over rule findings); wiring it in is the labelled next step. (b) **UI display** of a bound node's observations. (c) **Authored-pipeline node → graph linkage** is not tracked, so an authored-graph node id degrades to honest-empty rather than resolving its files. (d) A validated PHI scrubber replacing the `scrub_text` heuristic. |

## Revisit when

1. A new agent needs a per-node scoped view (widen `ATTACHABLE_AGENT_IDS` + re-check the taxonomy).
2. The compiler ever needs to read a save-envelope key beyond `{nodes, edges}` (the byte-identical
   invariant would no longer hold — reopen the compose ≠ execute argument first).
3. The `logs` grant graduates from a demo heuristic toward a real de-identification requirement.
