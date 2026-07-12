"""Review-queue / ticket domain (HITL, ADR-0010) — a PRODUCT surface, OFF the deterministic gate.

The Monitoring escalation and the agent-triage queue both assume a *writable* review queue with
reviewer/approver RBAC: an operator opens a ticket against a flagged sample, a reviewer
acknowledges/escalates it, and an approver resolves or suppresses it. This router is that queue.

Guardrail (CLAUDE.md architecture 1, ADR-0001): every endpoint here is **additive and off the
deterministic decision gate**. A ticket is a worklist item over an *already-decided* sample — it
records human follow-up, it NEVER calls ``run_gate``, touches the EventLedger/projection, or sets
or overrides a verdict/finding/confidence. It is deliberately *derived* state (it snapshots the
sample's ``gate``/``verdict``/``rule_id`` at open-time) and can never feed back into a decision.

Design:

  1. **Auth** comes entirely from ``api/auth.py`` (the shared primitive): writes/transitions are
     gated with ``Depends(require_role(...))`` and the acting ``actor.id`` is captured into every
     ``opened_by`` / ``actions[].actor`` audit field. Viewers can read the queue but never write.
  2. **Status machine + RBAC live in one table** (:data:`_ACTION_RULES`) so who-may-do-what and
     which-transition-is-legal are a single source of truth, unit-testable and easy to audit. The
     finer approver-only check (resolve/suppress) is enforced *inside* the handler because the
     required role depends on the request *body* (the action), which a static ``Depends`` can't see.
  3. **Persistence** is the pluggable, env-selected :mod:`api.review_store` (JSONL / SQLite /
     Postgres, degrade-to-JSONL) — mirrors the feedback/pipeline sinks, distinct from the decision
     Repository port. A store failure maps to a generic 503, never leaking a path/DSN.

Median-review-time seam (for the §7 Monitoring KPI): every action carries an ISO ``at`` timestamp
and the ticket carries ``created_at``, so a later KPI can read ``resolve.at - created_at`` per
ticket without any schema change here (see the module's ``integration_notes`` in the handoff).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, NamedTuple

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.auth import Actor, Role, require_role
from api.review_store import get_review_store

# Bump when the stored ticket shape changes so an out-of-band reader can branch on it.
REVIEW_SCHEMA_VERSION = 1

# Closed vocabularies. `gate`/`verdict` snapshot the decided sample (kept in step with
# pipeguard.models.Gate/Verdict), so a ticket carries the context it was opened against without
# re-reading — but they are *data on the ticket*, never re-fed to a rule.
TicketStatus = Literal["open", "in_review", "resolved"]
TicketPriority = Literal["high", "medium", "low"]
# The full audit vocabulary recorded in a ``TicketAction.action``. ``assign`` is an audit event
# (who now owns the ticket), NOT a status transition — see ``TransitionAction``.
ReviewActionName = Literal["acknowledge", "resolve", "escalate", "suppress", "reopen", "assign"]
# The status-transition subset — the ONLY actions ``POST /tickets/{id}/action`` accepts. ``assign``
# is deliberately EXCLUDED: it has its own endpoint and is absent from :data:`_ACTION_RULES`, so
# ``act_on_ticket`` (which indexes that table by the request action) can never receive it — a stray
# ``{"action": "assign"}`` on the action endpoint is a 422, never a KeyError/500.
TransitionAction = Literal["acknowledge", "resolve", "escalate", "suppress", "reopen"]
_Gate = Literal["preflight", "qc", "variant"]
_Verdict = Literal["proceed", "hold", "rerun", "escalate"]

# A rule id like ``PROV-001`` / ``qc.q30`` — bounded + charset-locked so it can never carry a
# newline (which would forge a JSONL line) or a control char (mirrors api/feedback.py's _RuleId).
_RULE_ID_PATTERN = r"^[A-Za-z0-9._:-]+$"
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


class _ActionRule(NamedTuple):
    """One row of the action table: who may perform it, which statuses it is legal from, and the
    status it transitions the ticket to. Kept immutable + centralized so RBAC and the status
    machine can't drift apart and are trivially unit-testable."""

    roles: tuple[Role, ...]
    from_statuses: tuple[TicketStatus, ...]
    to_status: TicketStatus


# Single source of truth for the ticket lifecycle. All actions require at least ``reviewer`` — the
# design (README §5.5) lets a reviewer resolve/suppress hold/rerun tickets, and gates the
# escalation-specific approver requirement in the UI (a reviewer never sees Resolve on an escalate
# ticket). ``suppress`` is keyed by the ticket's ``rule_id`` — it resolves this ticket AND marks the
# issue-class handled; class-wide muting of *future* tickets of that rule_id is a documented,
# not-built seam (would live in create()). An action from an illegal status is a 409.
_ACTION_RULES: dict[TransitionAction, _ActionRule] = {
    "acknowledge": _ActionRule(("reviewer", "approver"), ("open", "in_review"), "in_review"),
    "escalate": _ActionRule(("reviewer", "approver"), ("open", "in_review"), "in_review"),
    "resolve": _ActionRule(("reviewer", "approver"), ("open", "in_review"), "resolved"),
    "suppress": _ActionRule(("reviewer", "approver"), ("open", "in_review"), "resolved"),
    "reopen": _ActionRule(("reviewer", "approver"), ("resolved",), "open"),
}


class TicketAction(BaseModel):
    """One recorded action in a ticket's audit trail: what was done, by whom, and when.

    ``actor`` is the server-captured ``actor.id`` (never client-set); ``at`` is the ISO-8601 UTC
    timestamp the transition was recorded — the anchor a Monitoring median-review-time KPI reads.
    """

    action: ReviewActionName
    actor: str
    at: str


class Ticket(BaseModel):
    """A review-queue ticket: the stored + returned shape (the cards-as-tickets model, §4).

    Snapshots the decided sample's context (``run_id``/``sample_id``/``gate``/``verdict``/
    ``rule_id``) at open-time so the queue is self-contained, then tracks its own review
    lifecycle. ``opened_by`` and every ``actions[].actor`` are server-authored from the
    authenticated principal — no identity/PII enters through a request body. ``assignee`` is the
    current owner (a user id, or ``None`` when unassigned) set via the ``/assign`` endpoint — the
    review↔kanban link. ``created_at`` + ``actions[].at`` are the timestamps a median-review-time
    KPI reads. This is product state and never a verdict input (ADR-0001). ``assignee`` defaults to
    ``None`` so a ticket stored before the field existed round-trips cleanly (no migration).
    """

    id: str
    schema_version: int = REVIEW_SCHEMA_VERSION
    created_at: str
    run_id: str
    sample_id: str
    gate: _Gate
    verdict: _Verdict
    rule_id: str
    title: str
    priority: TicketPriority
    status: TicketStatus
    opened_by: str
    assignee: str | None = None
    actions: list[TicketAction] = Field(default_factory=list)


class TicketIn(BaseModel):
    """The ``POST /api/review/tickets`` body — the context to open a ticket against a sample.

    ``extra="forbid"`` blocks any smuggled server-authored field (``id``/``status``/``opened_by``/
    ``actions`` are the server's to set, never the client's). Ids/rule_id are charset-locked so
    they can never forge a JSONL line; ``title`` is bounded free text. ``gate``/``verdict`` are
    closed enums that snapshot the decided sample. No operator identity field is accepted — the
    opener is taken from the authenticated principal.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., max_length=128, pattern=_ID_PATTERN)
    sample_id: str = Field(..., max_length=64, pattern=_ID_PATTERN)
    gate: _Gate
    verdict: _Verdict
    rule_id: str = Field(..., max_length=64, pattern=_RULE_ID_PATTERN)
    title: str = Field(..., min_length=1, max_length=200)
    priority: TicketPriority = "medium"

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        # Coerce a whitespace-only title to a hard 422 (min_length runs on the raw value, so a
        # "   " would otherwise slip through and store as blank).
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must not be blank")
        return stripped


class ActionIn(BaseModel):
    """The ``POST /api/review/tickets/{id}/action`` body — just the action to apply.

    ``extra="forbid"`` so a caller can't smuggle an ``actor``/``at`` (both server-authored). The
    action's RBAC + legal-from status come from :data:`_ACTION_RULES`, not the request. ``action``
    is typed :data:`TransitionAction` (NOT :data:`ReviewActionName`), so ``assign`` — an audit event
    with its own endpoint, not a status transition — is rejected here with a 422 and can never reach
    ``act_on_ticket``'s :data:`_ACTION_RULES` lookup.
    """

    model_config = ConfigDict(extra="forbid")

    action: TransitionAction


class AssignIn(BaseModel):
    """The ``POST /api/review/tickets/{id}/assign`` body — the ticket's new owner (or ``None``).

    ``extra="forbid"`` blocks any smuggled server-authored field (``actor``/``at`` on the audit
    entry are the server's). ``assignee`` is a bounded, charset-locked user id — the SAME shape as
    an ``opened_by`` / ``actor.id``, so it can never forge a JSONL line — not an identity/PII
    payload (a user-id string is fine under the no-PII-in-a-body guardrail). ``None`` unassigns.
    """

    model_config = ConfigDict(extra="forbid")

    assignee: str | None = Field(default=None, max_length=64, pattern=_ID_PATTERN)


router = APIRouter(prefix="/api/review", tags=["review-queue"])


@router.post("/tickets", status_code=201)
def create_ticket(
    body: TicketIn,
    actor: Actor = Depends(require_role("reviewer", "approver")),
) -> Ticket:
    """Open a review ticket against a flagged sample — a PRODUCT write, OFF the deterministic gate.

    Requires reviewer or approver (a viewer is 403ed by the dependency). Mints a server-authored
    ``id``/``created_at``, sets ``status='open'`` and ``opened_by=actor.id`` (the authenticated
    principal, never the body — ``TicketIn`` is ``extra='forbid'``), and starts an empty audit
    trail. It NEVER calls ``run_gate`` or touches a verdict; the ``gate``/``verdict``/``rule_id``
    it stores are an inert snapshot of the already-decided sample. A store failure is a generic
    503 that never leaks the path/DSN (mirrors POST /api/feedback).
    """
    ticket_id = uuid.uuid4().hex  # stdlib uuid on purpose — no coupling to the core's ids
    created_at = datetime.now(timezone.utc).isoformat()
    record: dict[str, Any] = {
        **body.model_dump(),
        "id": ticket_id,
        "schema_version": REVIEW_SCHEMA_VERSION,
        "created_at": created_at,
        "status": "open",
        "opened_by": actor.id,
        "actions": [],
    }
    try:
        stored = get_review_store().create(record)
    except Exception:
        raise HTTPException(status_code=503, detail="review store unavailable") from None
    return Ticket.model_validate(stored)


@router.get("/tickets")
def list_tickets(
    response: Response,
    status: str | None = Query(None),
    run_id: str | None = Query(None),
    rule_id: str | None = Query(None),
    since: str | None = Query(None),
) -> list[Ticket]:
    """The review queue, newest-context first, filterable by status / run_id / rule_id / since.

    Read-only over product state (any role, including viewer). ``status`` is validated against the
    closed vocabulary (unknown → 400, the same closed-enum idiom the run-list uses); ``run_id`` /
    ``rule_id`` are exact-match filters. ``since`` (an ISO-8601 date/datetime) is a recency window:
    only tickets with ``created_at >= since`` are returned, so a client can load just the recent
    tail instead of every ticket ever. The ``X-PipeGuard-Ticket-Total`` response header carries the
    count for the status/run/rule filter set IGNORING ``since`` — mirroring the run-list's
    ``X-PipeGuard-Total-Count`` idiom — so a windowed view can still show "N resolved total". A
    store failure maps to a generic 503 without leaking the path/DSN.
    """
    if status is not None and status not in ("open", "in_review", "resolved"):
        raise HTTPException(
            status_code=400, detail="status must be one of open, in_review, resolved"
        )
    if since is not None:
        # Reject a garbage window the same way an unknown status is rejected (a closed contract),
        # never a silent empty result. fromisoformat accepts a bare date ("2026-06-11") too.
        try:
            datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="since must be an ISO-8601 date or datetime"
            ) from None
    try:
        records = get_review_store().list(status=status, run_id=run_id, rule_id=rule_id)
    except Exception:
        raise HTTPException(status_code=503, detail="review store unavailable") from None
    # Total for this status/run/rule set BEFORE the recency window, so the resolved tab can show a
    # true total even when it only loaded the last ~30 days.
    response.headers["X-PipeGuard-Ticket-Total"] = str(len(records))
    if since is not None:
        # Lexicographic compare is correct for zero-padded ISO-8601: a created_at datetime string
        # sorts against the ISO `since` prefix exactly as the timestamps order (UTC throughout).
        records = [r for r in records if str(r.get("created_at") or "") >= since]
    return [Ticket.model_validate(r) for r in records]


@router.post("/tickets/{ticket_id}/action")
def act_on_ticket(
    ticket_id: str,
    body: ActionIn,
    actor: Actor = Depends(require_role("reviewer", "approver")),
) -> Ticket:
    """Apply a lifecycle action to a ticket (acknowledge/escalate/resolve/suppress/reopen).

    RBAC + the legal transition are one table (:data:`_ACTION_RULES`). The dependency blocks a
    viewer (403); the finer approver-only check for ``resolve``/``suppress`` is enforced here
    because the required role depends on the *body* (a static ``Depends`` can't read it). Order of
    checks: unknown ticket → 404; insufficient role for this action → 403; action illegal from the
    current status → 409. On success it appends ``{action, actor.id, at}`` to the audit trail,
    transitions ``status``, and persists — it NEVER re-runs the gate or touches a verdict
    (ADR-0001).
    """
    store = get_review_store()
    try:
        record = store.get(ticket_id)
    except Exception:
        raise HTTPException(status_code=503, detail="review store unavailable") from None
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown ticket '{ticket_id}'")

    # body.action is a TransitionAction (assign is excluded by ActionIn's type), and _ACTION_RULES
    # has a row for every TransitionAction, so this lookup can never KeyError.
    rule = _ACTION_RULES[body.action]
    if actor.role not in rule.roles:
        # Name the required roles (not secret) so the caller can self-correct; never echo the
        # caller's id into the error (it would land in shared logs / client-visible bodies).
        raise HTTPException(
            status_code=403,
            detail=f"action '{body.action}' requires one of: {', '.join(rule.roles)}",
        )
    current_status = record.get("status")
    if current_status not in rule.from_statuses:
        # 409 Conflict: the ticket exists and the caller is authorized, but the action is illegal
        # from the ticket's current state (e.g. resolving an already-resolved ticket).
        raise HTTPException(
            status_code=409,
            detail=(
                f"action '{body.action}' not allowed from status '{current_status}' "
                f"(allowed from: {', '.join(rule.from_statuses)})"
            ),
        )

    # An escalation must have an accountable owner — an unassigned escalation is an orphan no
    # approver owns (UX review finding A). The UI routes escalate to a specific approver; enforce
    # the precondition here too so it isn't a UI-only guardrail on a permissive dev backend.
    if body.action == "escalate" and not record.get("assignee"):
        raise HTTPException(
            status_code=409,
            detail="action 'escalate' requires the ticket to be assigned to an owner first",
        )

    action_entry = {
        "action": body.action,
        "actor": actor.id,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    updated: dict[str, Any] = {
        **record,
        "status": rule.to_status,
        "actions": [*record.get("actions", []), action_entry],
    }
    try:
        stored = store.update(updated)
    except Exception:
        raise HTTPException(status_code=503, detail="review store unavailable") from None
    return Ticket.model_validate(stored)


@router.post("/tickets/{ticket_id}/assign")
def assign_ticket(
    ticket_id: str,
    body: AssignIn,
    actor: Actor = Depends(require_role("reviewer", "approver")),
) -> Ticket:
    """Assign (or unassign) a ticket's owner — a PRODUCT write, OFF the deterministic gate.

    Requires reviewer or approver (a viewer is 403ed by the dependency). Sets ``assignee`` (``None``
    unassigns — the review↔kanban link that says who owns the ticket) and appends an ``assign``
    audit entry ``{action, actor.id, at}``. Assigning is deliberately NOT a status transition: it is
    absent from :data:`_ACTION_RULES` and reachable only here, so it never moves the ticket through
    its lifecycle, never re-runs the gate, and never touches a verdict (ADR-0001). Order of checks:
    unknown ticket → 404. A store failure is a generic 503 that never leaks the path/DSN.
    """
    store = get_review_store()
    try:
        record = store.get(ticket_id)
    except Exception:
        raise HTTPException(status_code=503, detail="review store unavailable") from None
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown ticket '{ticket_id}'")

    action_entry = {
        "action": "assign",
        "actor": actor.id,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    updated: dict[str, Any] = {
        **record,
        "assignee": body.assignee,
        "actions": [*record.get("actions", []), action_entry],
    }
    try:
        stored = store.update(updated)
    except Exception:
        raise HTTPException(status_code=503, detail="review store unavailable") from None
    return Ticket.model_validate(stored)
