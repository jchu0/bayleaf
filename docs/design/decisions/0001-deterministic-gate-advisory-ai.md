# ADR 0001 — Deterministic gate, advisory AI

- **Status:** accepted
- **Date:** 2026-07-07 (MST)
- **Related:** 0006, requirements/nonfunctional.md

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

## Alternatives considered
- LLM makes the call end-to-end — rejected: non-deterministic, unauditable, and
  not credible for QC/variant gating.
- No AI, rules only — rejected: loses the cross-layer triage and narration that
  is the product's differentiator.

## Consequences
Recommendations are reproducible and traceable to a rule and a source file. Every
new check is a rule emitting a finding, not a prompt change. The AI's job is
bounded and independently evaluable (faithfulness to findings). "Not a clinical
decision system" holds even as capability grows.
