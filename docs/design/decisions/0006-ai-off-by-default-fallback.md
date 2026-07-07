# ADR 0006 — AI off by default with a deterministic fallback

- **Status:** accepted
- **Date:** 2026-07-07 (MST)
- **Related:** 0001, 0005

## Context
Live AI calls cost money (a fixed ~$200 product API budget, separate from dev
tooling) and add latency and a failure mode. The system must remain usable,
testable, and demoable offline, and must not degrade if the API is unavailable
mid-run — a real risk on conference networks and during grading.

## Decision
Every AI component (the synthesizer and, later, each scoped agent) is **off by
default** and selected by configuration. Each has a deterministic fallback: if
the component is disabled or the call fails (including a safety refusal), the
deterministic verdict and findings still stand and only the narrative/triage is
absent. The `anthropic` dependency is imported lazily so the package installs and
tests pass without it. Model selection is configurable to trade cost for quality.

## Alternatives considered
- AI on by default — rejected: burns budget in dev/CI, and makes the demo
  hostage to network/API reliability.
- Pre-recorded AI responses only — rejected: loses the real, live reasoning that
  is central to the pitch; kept only as an optional cache.

## Consequences
Development and CI cost nothing and run offline. The demo has a built-in safety
net. Turning AI on is a one-line config change. Every agent inherits this
contract, which bounds blast radius as the agent count grows.
