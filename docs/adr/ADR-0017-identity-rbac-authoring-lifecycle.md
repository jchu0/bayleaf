# ADR-0017 — Identity, RBAC, and the draft→approve authoring lifecycle

| Field | Value |
|---|---|
| **Status** | Accepted · MVP **dev-shim identity + RBAC BUILT** (`api/auth.py`), permissive by default; the draft→approve lifecycle is realized for pipeline graphs / config overrides / review tickets. A real identity provider + multi-worker version integrity are deferred seams. |
| **Date** | 2026-07-09 (MST) |
| **Deciders** | maintainer + Claude Code |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md) · [ADR-0010](ADR-0010-ticketing-notify-read-api.md) · [ADR-0014](ADR-0014-productionization-fastapi-react.md) · [ADR-0016](ADR-0016-postgres-port.md) · [design/architecture.md](../design/architecture.md) · [design/frontend/handoffs/2026-07-09-backend-contracts.md](../design/frontend/handoffs/2026-07-09-backend-contracts.md) · [planning/tasks.md](../planning/tasks.md) |

## Context

The updated frontend design introduces **authored, governed artifacts** — saved pipeline
graphs, QC-threshold/config overrides, and review-queue tickets — each with a
reviewer/approver **approval flow**. Until now the app had no identity or authorization source
(the UI hard-codes `a.rivera / Reviewer`), and rules-decide / AI-advises (ADR-0001) means none
of these authoring flows may ever touch a verdict — they are **product state off the gate**.
We need one identity+authz source and one approval pattern, without dragging real auth
infrastructure into a hackathon demo that must stay offline and single-process.

## Decision

1. **A minimal identity primitive** (`api/auth.py`). `Role = viewer | reviewer | approver`;
   a frozen `Actor{id, role}`; `current_actor()` reads `X-PipeGuard-Actor` / `X-PipeGuard-Role`
   headers with a **permissive dev-default** (`id=dev, role=approver`) so the offline demo and
   the existing test suite need no auth wiring; `require_role(*allowed)` is a dependency that
   **403s** on an insufficient role and otherwise yields the `Actor`. `current_actor` is the
   **single swap point** for a real identity provider — this is an explicit **dev shim**
   (header-trust, spoofable), *not* a production auth boundary.
2. **One uniform draft→save→approve lifecycle** across three product stores. A save mints a
   `draft` with a server-captured `submitted_by`; a reviewer/approver promotes it; only an
   **approver** approves (captures `approved_by`). Authorization is **set-membership** on `Role`,
   never ordinal. This realizes the lifecycle previously only *reserved* on the pipeline envelope
   (ADR-0016) and extends it to config overrides + tickets.
3. **All three stores mirror the pluggable-store seam** (`jsonl` default | `sqlite` | `postgres`,
   degrade-to-JSONL, the DSN never logged), are **distinct from the decision `Repository`**, and
   never re-enter the gate (ADR-0016 pattern, now four product stores: feedback / pipeline /
   settings / review).
4. **Guardrails hold the boundary.** Identity is **server-captured** into audit/`*_by` fields,
   never client-set into the envelope (`extra="forbid"`). A pipeline **dry-run resolves locators
   READ-ONLY** — compose ≠ execute (ADR-0001/0003); nothing here triggers a run. An approved
   config override, when a future step applies it, is layered onto a **per-run `Runbook` copy**,
   never `DEFAULT_RUNBOOK`, and can never set or override a verdict/finding/confidence.

## Assumptions

- Header-trust identity is acceptable for the demo because the app is offline/single-tenant; a
  real deployment replaces `current_actor` with a verified provider, leaving `require_role` and
  every `actor.id` capture site unchanged.
- The approval flow is advisory governance over product state, not a safety control — it gates
  *who may author config*, never *what the gate decides*.

## Consequences

| | |
|---|---|
| **Gains** | One authz source unblocks three RBAC surfaces at once; the approval pattern is uniform and testable; the offline demo/tests are untouched (permissive default); the boundary (off-gate, server-captured identity, read-only dry-run) is explicit. |
| **Costs** | The default provides **no real protection** until `current_actor` is swapped (documented); per-name version authoring is atomic only within one worker (the same honest limit the other stores carry); approve appends a revision per transition (audit-every-transition, not idempotent). |
| **Follow-ups** | A real identity provider behind `current_actor`; a per-record lock / DB sequence for multi-worker version integrity; applying an approved config override onto a per-run Runbook copy at gate time (the documented off-gate seam). |

## Alternatives considered

| Option | Why not |
|---|---|
| Real auth (OAuth/OIDC/session) now | Drags infra + credentials + an outbound surface into an offline demo; the shim with a single swap point gives the shape without the cost. |
| No RBAC — trust the client's claimed role | The design's whole point is reviewer-vs-approver separation; even a shim must model the two roles so the UI and the audit trail are meaningful. |
| A separate approval lifecycle per surface | Three subtly-different flows to keep in parity; one shared `require_role` + draft→approve shape is less to get wrong. |

## Revisit when

- The app gains real multi-user deployment (then `current_actor` must become a verified provider
  and 401-vs-403 semantics matter upstream).
- Concurrent authoring at multi-worker scale makes per-name version races real.
