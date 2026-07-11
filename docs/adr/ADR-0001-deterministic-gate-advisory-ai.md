# ADR-0001 — Deterministic gate, advisory AI

| Field | Value |
|---|---|
| **Status** | Accepted · Realized (rules decide, AI narrates; off-path extended to every later seam) |
| **Date** | 2026-07-07 (MST) · updated 2026-07-08 (MST) · updated 2026-07-11 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0006](ADR-0006-ai-off-by-default-fallback.md), [ADR-0007](ADR-0007-ml-ready-structured-outputs.md), [ADR-0010](ADR-0010-ticketing-notify-read-api.md), [ADR-0012](ADR-0012-agent-scoping-model-tiering.md), [ADR-0013](ADR-0013-gate-architecture-verdict-policy.md), [ADR-0015](ADR-0015-layered-data-contract.md) |

## Context

The system recommends whether a genomics sample should proceed, hold, rerun, or
escalate. In a rare-disease context the cost of a wrong or unexplained call is
high, and a recommendation is only useful if a reviewer can trust and audit it.
An LLM asked to judge a numeric threshold or an ID match directly is both
unreliable and unconvincing to a bioinformatician.

## Decision

Deterministic rules decide; the AI narrates and advises. A rule engine computes
cited findings and the verdict/confidence from the runbook. The AI layer (a
synthesizer today, scoped agents later) explains findings, suggests likely
causes, and drafts next steps — but never computes, sets, or overrides a verdict.
Agents sit **off** the deterministic critical path: if the AI is disabled or
fails, the verdict and findings still stand.

## Assumptions

- Reviewers trust a cited, rule-derived finding more than an LLM assertion.
- The AI's durable value is cross-layer triage and narration, not judgment.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| LLM makes the call end-to-end | Non-deterministic, unauditable, not credible for gating |
| Rules only, no AI | Loses the cross-layer triage/narration that is the product's differentiator |

## Consequences

| | |
|---|---|
| **Gains** | Reproducible, source-traceable recommendations; the AI's job is bounded and independently evaluable (faithfulness to findings) |
| **Costs** | Every new check must be encoded as a rule, not a prompt tweak |
| **Follow-ups** | Define the faithfulness check in `quality/evaluation.md` |

## Realized (2026-07-08 · item 3 added 2026-07-11)

1. **Rules decide, AI narrates.** `rules.py` emits cited `Finding`s with suggested
   verdicts; `synthesis/base.py::aggregate_verdict` picks the most-severe verdict
   deterministically (never the LLM); `DecisionCard.confidence` is omitted until
   grounded (T-019).
2. **Off-critical-path extended to every later AI/dispatch seam.** The QC-triage agent
   ([ADR-0012](ADR-0012-agent-scoping-model-tiering.md), `triage/`) and the notify port
   ([ADR-0010](ADR-0010-ticketing-notify-read-api.md), `notify/`) both run *after* the
   verdict is decided — a failure in either leaves findings + verdict intact.
3. **The Pipeline Builder's deterministic boundary moved OFF the canvas (2026-07-11, commit
   `3d531de`).** The gate and its deterministic-ingest predecessor were never composable nodes —
   no data edge feeds them, nothing about them is editable — yet an earlier pass had them rendered
   as movable canvas cards (`3d531de`'s two predecessor commits, `73b2a68`/`4d4823d`, same day).
   The maintainer's synthesis: a fixed boundary card still implies a false peer relationship with
   the tools an operator actually composes, and eats canvas real estate besides. `BuilderCanvas.tsx`
   now renders **only** composable content (tools/refs/input/output) plus the movable, port-less
   advisory agent (canvas node count 15→13); the deterministic ingest→gate→verdict handoff is a
   new read-only view, `frontend/src/components/DecisionBoundaryModal.tsx`, reachable from the
   toolbar's "⋯ More" menu, captioned "rules decide; not part of what you compose." `Save`/`Emit`/
   `POST /api/pipelines/compile` still serialize only `{nodes: userNodes, edges: userEdges}` —
   unchanged; the gate/ingest were never in that payload before or after. Both remaining gate
   verdict bars (the linked-run strip's and the old gate card's) were also removed the same day
   (`4d4823d`) — the Builder now shows **no verdict palette anywhere**, only the rule engine's
   own decision surfaces (Decision cards, Provenance) do. This is a UI-level reinforcement of this
   ADR's decision, not a new one — see [journal
   2026-07-11](../journal/2026-07-11-builder-boundary-and-edges.md) and [design/frontend/README.md
   §6](../design/frontend/README.md#6-pipeline-builder--full-model).

## Revisit when

- There is validated evidence an AI-produced verdict is as reliable and auditable
  as the rule engine (out of current scope; would also reopen the biomedical
  guardrail).
