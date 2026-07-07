# ADR-0001 — Deterministic gate, advisory AI

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-07 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | ADR-0006, ADR-0007 |

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

## Revisit when

- There is validated evidence an AI-produced verdict is as reliable and auditable
  as the rule engine (out of current scope; would also reopen the biomedical
  guardrail).
