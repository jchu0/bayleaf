# ADR-0011 — Tooling and reproducibility

| Field | Value |
|---|---|
| **Status** | Accepted · Implemented (T-012); batch-tier full-eval deferred to Phase 2 |
| **Date** | 2026-07-07 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0006](ADR-0006-ai-off-by-default-fallback.md), [tasks T-012](../planning/tasks.md) |

## Context

Session 1 left dependencies declared in **both** `requirements.txt` and
`pyproject.toml`, unpinned, with no type checking, linting, secret scanning, or
doc-drift gate. In a low-error-tolerance domain that is a reproducibility and
drift risk, and it will only get more expensive to fix as the code grows.

## Decision

1. **`pyproject.toml` is the single dependency source**, managed with **uv**
   (`uv.lock` pinned for a reproducible environment). `requirements.txt` is retired and
   the dev toolchain lives in a PEP 735 `[dependency-groups]`; `uv sync` installs the
   package editable (no `PYTHONPATH` shim). **Implemented in T-012 (2026-07-07).**
2. **mypy** (strict-ish) and **ruff** (lint + format) enforce the coding standards.
3. **Hook tiers:** pre-commit (ruff, secret scan, mypy), pre-push (pytest),
   batch/milestone (full evaluation incl. real-data validation, `pip-audit`).
   *Implemented:* tiers 1–2 in `.pre-commit-config.yaml`; the batch tier's
   `pip-audit` runs via `make audit`, while the full evaluation is deferred to
   Phase 2 (it needs the eval harness — see T-009).
4. Coding standards (type hints, docstrings, why-comments, typed config) are enforced.

## Assumptions

- uv is an acceptable toolchain for the team.
- The hook tiers match the batch-verification cadence (heavy checks on batch pushes).

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Keep pip + `requirements.txt` | Non-reproducible, and a dual source of truth that drifts |
| Poetry | Heavier and slower than uv for this size |
| No hooks | Lets standards, secrets, and docs drift silently |

## Consequences

| | |
|---|---|
| **Gains** | Reproducible env, enforced standards, no secret/doc drift |
| **Costs** | Tooling setup plus bringing the existing code up to pass mypy/ruff |
| **Follow-ups** | Phase 0, task T-012 |

## Revisit when

- uv or a specific hook proves to be more friction than value.
