# ADR-0017 — Identity, RBAC, and the draft→approve authoring lifecycle

| Field | Value |
|---|---|
| **Status** | Accepted · MVP **dev-shim identity + RBAC BUILT** (`api/auth.py`), permissive by default; the draft→approve lifecycle is realized for pipeline graphs / config overrides / review tickets, and (2026-07-11, W1) now gates a real Nextflow EXECUTION too, not just config authoring. A real identity provider + multi-worker version integrity are deferred seams. |
| **Date** | 2026-07-09 (MST) · updated 2026-07-11 (MST, W1 approval-gated execution) |
| **Deciders** | maintainer + Claude Code |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md) · [ADR-0003](ADR-0003-deployment-agnostic-ports.md) (the execution path W1 gates) · [ADR-0010](ADR-0010-ticketing-notify-read-api.md) · [ADR-0014](ADR-0014-productionization-fastapi-react.md) · [ADR-0016](ADR-0016-postgres-port.md) · [design/architecture.md](../design/architecture.md) · [design/frontend/handoffs/2026-07-09-backend-contracts.md](../design/frontend/handoffs/2026-07-09-backend-contracts.md) · [planning/tasks.md](../planning/tasks.md) (T-126) · [journal 2026-07-11 audit+W1-W4+E2E](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md) |

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
   a frozen `Actor{id, role}`; `current_actor()` reads `X-bayleaf-Actor` / `X-bayleaf-Role`
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

## Realized addendum (2026-07-10) — a frontend demo login layer, no decision change

The frontend gained a client-side login screen (`frontend/src/auth.ts` + `screens/Login.tsx`,
T-081, commit `0f7e85f`) that fronts every route and chooses which `Actor{id, role}` the app
sends as `X-bayleaf-Actor`/`-Role`. This is **additive framing, not a new decision**: it does
not change `api/auth.py`, `current_actor()`, `require_role`, or any backend authorization
boundary described above — it only decides which of the already-permitted `Actor`s the UI acts
as, and it is itself an equally-explicit **dev-only** layer (four hardcoded demo accounts, one
shared password, `localStorage` session with no token, a labelled CAPTCHA placeholder). `isAdmin`
(the Admin-panel governance gate, REQ-F-066) is a **frontend-only** capability derived from the
login roster, layered *above* the `viewer|reviewer|approver` `Role` this ADR defines — it never
becomes a fourth wire role, and `api/auth.py` has no concept of "admin." See
[risks.md](../quality/risks.md) RISK-035 and
[functional.md](../requirements/functional.md) REQ-F-069/REQ-F-066 for the full framing.

## Realized addendum (2026-07-10) — explicit-confirm gate on off-gate writes, no decision change

The frontend gained a reusable confirm-gate primitive (`frontend/src/components/
ConfirmDialog.tsx`, a `ConfirmProvider`/`useConfirm()`, commit `d65c9c1`, "Wave 3") enforcing
the maintainer's standing rule that no single accidental click may fire a cascading/
state-changing off-gate write. The review queue (`ReviewQueue.tsx`) routes Resolve/Escalate/
Reopen/Suppress and the batch Resolve/Suppress actions through it, each confirm naming its
effect and that it is recorded in the audit log (Suppress is DANGER-toned, naming the
cross-run cascade); Admin's Act-as (`Admin.tsx`) swaps its native `window.confirm` (T-092) for
the same dialog. **Additive framing, not a new decision:** the actions still call the exact
same backend writes this ADR's draft→approve/`*_by` audit guardrails already cover
(`api/routers/review_queue.py`'s `ticketAction`, the client-mock `RoleContext.setActor`) — no
new endpoint, no wire change, `current_actor()`/`require_role` untouched. This is the
frontend-UX realization of Decision 4 above ("identity is server-captured into audit/`*_by`
fields"): the confirm step makes the human side of that attribution **deliberate**, not just
recorded after the fact. Low-stakes/non-destructive actions (acknowledge, un-suppress)
intentionally stay direct one-clicks — gating them would add friction without mitigating a real
accidental-click risk. See [architecture.md](../design/architecture.md) §Invariants,
[risks.md](../quality/risks.md) RISK-035, and
[functional.md](../requirements/functional.md) REQ-F-075 for the full framing.

## Realized addendum (2026-07-11, W1) — the draft→approve lifecycle now gates a real EXECUTION, not just config

Until this landing, the draft→approve lifecycle this ADR defines governed **product state only**
(a saved pipeline graph, a config-threshold override, a review ticket) — never anything that
actually ran. A second execution path, `POST /api/pipelines/run` (`api/routers/pipeline_run.py`,
ADR-0003), let an operator run their **live canvas graph** with no approved-status check at all —
a real Fable-5 release-hardening-audit finding (P1-6/P3-14, `audit/SYNTHESIS.md`,
[tasks T-125](../planning/tasks.md)): the endpoint was authz-gated (`require_role("reviewer",
"approver")`) but not *lifecycle*-gated, so an unapproved, unreviewed draft could execute for
real (compile → Nextflow → a gate-able run dir).

**The fix (T-126, commit `94c19da`):** the endpoint's body now NAMES a saved pipeline rather than
carrying a raw graph (`RunPipelineIn` is `extra="forbid"`, so a smuggled `graph` field 422s
before anything compiles); the server resolves that pipeline's approver-blessed (`emitted`)
snapshot from `PipelineGraphStore` (`_resolve_approved`) and compiles + runs **that** — never the
client's live, possibly-unreviewed canvas state. A name with no approved version is a **409**
("no approved version of pipeline '…' — submit and approve it before running"), matching the
existing draft→submit→approve status vocabulary this ADR defines rather than inventing a new one.
The Builder's "Run" action is disabled client-side until the current pipeline is approved. A
committed helper, `scripts/seed_approved_germline.py`, idempotently drives the SAME
save→submit→approve lifecycle (via `record_transition`/`record_emission`, the exact functions the
API uses) to seed a runnable `germline-panel` baseline, since a fresh store otherwise has no
approved pipeline to name.

**Additive framing, mostly — one real behavior change, stated plainly:** this does not add a new
role, a new transition, or a new store; it makes an *existing* lifecycle stage (approved) a
**precondition for a capability this ADR did not originally scope** (execution). The lifecycle's
job widened from "gate who may author config" to "gate who may author config **and what may run**"
— still advisory governance over product state, never touching the deterministic gate's verdict
(ADR-0001; `run_pipeline` produces a new `data/<run_id>/` directory that `run_gate` later
evaluates unchanged). See [functional.md REQ-F-086](../requirements/functional.md),
[design/nextflow-codegen.md](../design/nextflow-codegen.md),
[tasks T-126](../planning/tasks.md),
[journal 2026-07-11](../journal/2026-07-11-audit-hardening-w1-w4-e2e.md).
