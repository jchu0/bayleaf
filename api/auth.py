"""Minimal auth/identity primitive for the read-API's off-gate write surfaces (ADR-0010/0016).

One shared source of *who is acting* and *what they may do*, so the new draft->approve RBAC
flows (Settings, Review-queue, Pipeline lifecycle) stop hardcoding ``a.rivera / Reviewer`` in
the UI and instead read a single current-user+role dependency. This lives in ``api/`` (the
delivery layer, which already speaks FastAPI) and is wholly **OFF the deterministic decision
gate** (ADR-0001): it can gate who may *write* product state, but it never touches a verdict,
finding, confidence, or rule — those stay in the framework-agnostic ``src/pipeguard/`` core.

Design (MVP-first, production-ready seam):

  - :data:`Role` — the closed RBAC vocabulary (``viewer`` < ``reviewer`` < ``approver``).
  - :class:`Actor` — the authenticated principal (``id`` + ``role``); ``id`` is what gets
    captured into audit / ``*_by`` fields on a transition.
  - :func:`current_actor` — a FastAPI dependency that reads the ``X-PipeGuard-Actor`` /
    ``X-PipeGuard-Role`` headers. **Dev-default is permissive** — with no headers it returns
    ``Actor(id="dev", role="approver")`` so the offline demo and the existing test suite pass
    with no auth wiring and no endpoint behavior changes.
  - :func:`require_role` — a dependency *factory*; ``Depends(require_role("approver"))`` 403s
    (not 401) when the caller's role is not in the allowed set, and otherwise **returns the
    Actor** so a guarded endpoint gets identity and authorization from one dependency.

**Production seam (documented, not built).** The permissive header-trust here is a *dev shim*,
not an identity system: any client can name itself. A real deployment swaps :func:`current_actor`
for a verified identity provider (session cookie / OIDC / signed JWT) that returns the same
:class:`Actor` — every ``require_role(...)`` gate and every ``actor.id`` capture site keeps
working unchanged because they depend only on the :class:`Actor` contract, never on how it was
derived. That swap is the single chokepoint to harden; nothing downstream moves.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, get_args

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict

# Closed RBAC vocabulary. Ordered least->most privileged by convention, but authorization is
# set-membership (``require_role``), not an ordinal compare — so a grant is always explicit and
# a new role can slot in without every call site silently widening. Keep in sync with the
# frontend's role labels and the reserved ``*_by`` lifecycle in ``api/pipeline.py``.
Role = Literal["viewer", "reviewer", "approver"]

# The permissive dev principal returned when no auth headers are present. Permissive on PURPOSE:
# the offline demo and the existing endpoints/tests must run with zero auth wiring, so the
# default can satisfy any ``require_role`` gate. A real identity provider replaces this shim
# (see the module docstring) — this default never ships as the production auth decision.
DEV_DEFAULT_ID = "dev"
DEV_DEFAULT_ROLE: Role = "approver"

# The valid role tokens, derived from the Literal so this can never drift from ``Role``.
_ROLES: tuple[Role, ...] = get_args(Role)

# Header names carrying the (dev-shim) principal. Case-insensitive on the wire per HTTP.
_ACTOR_HEADER = "X-PipeGuard-Actor"
_ROLE_HEADER = "X-PipeGuard-Role"

# Bound + charset-lock the actor id BEFORE it is captured into an audit / ``*_by`` field or a
# log line: this is the same defensive discipline the other write seams use (feedback/pipeline
# stores) so a header can never smuggle a newline/control char into a JSONL row or forge a log
# line. A username (``a.rivera``) or an email-ish handle is allowed; nothing exotic.
_ACTOR_ID_MAX_LEN = 128
_ACTOR_ID_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._@+-")


class Actor(BaseModel):
    """The authenticated principal for an off-gate write: an identity plus its RBAC role.

    ``id`` is the stable handle captured into audit / ``*_by`` fields on a transition (e.g.
    ``approved_by``); ``role`` decides what the principal may do via :func:`require_role`.
    Frozen so an endpoint can't accidentally mutate the caller mid-request. This is a product/
    identity contract only — it is never a verdict input and never re-enters the decision gate.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    role: Role


def _normalize_actor_id(raw: str | None) -> str:
    """Trim + validate the actor-id header, falling back to the dev id when absent.

    Absent/blank -> the dev default (so the header-free offline path works). Present-but-invalid
    (too long, or a disallowed char such as a newline that could forge a log/JSONL line) is a
    hard 400 rather than a silent coercion — an explicit bad identity should surface, not be
    quietly rewritten to ``dev``.
    """
    value = (raw or "").strip()
    if not value:
        return DEV_DEFAULT_ID
    if len(value) > _ACTOR_ID_MAX_LEN or any(ch not in _ACTOR_ID_ALLOWED for ch in value):
        raise HTTPException(status_code=400, detail="invalid actor id")
    return value


def _normalize_role(raw: str | None) -> Role:
    """Trim + validate the role header, falling back to the permissive dev role when absent.

    Absent/blank -> the dev default role. Present-but-unknown is a hard 400: silently coercing
    an unrecognized role would be a privilege decision made by accident, so an explicit unknown
    role must fail loudly instead of defaulting (which could over- or under-grant).
    """
    value = (raw or "").strip().lower()
    if not value:
        return DEV_DEFAULT_ROLE
    if value not in _ROLES:
        # Roles are not secret, so naming the allowed set is a usability win, not a leak.
        raise HTTPException(status_code=400, detail=f"unknown role (allowed: {', '.join(_ROLES)})")
    # mypy narrows `value` to `Role` here via the membership guard above (no cast needed).
    return value


def current_actor(
    actor_header: str | None = Header(default=None, alias=_ACTOR_HEADER),
    role_header: str | None = Header(default=None, alias=_ROLE_HEADER),
) -> Actor:
    """FastAPI dependency resolving the current principal from the dev-shim auth headers.

    Reads ``X-PipeGuard-Actor`` / ``X-PipeGuard-Role``. With **no headers** it returns the
    permissive dev default (``id="dev"``, ``role="approver"``) so the offline demo and the
    existing tests run with zero auth wiring and no endpoint behavior changes. Each header is
    resolved independently and tolerantly (a partial header set still works); a *present but
    malformed* value is a 400 (see the ``_normalize_*`` helpers) rather than a silent coercion.

    Swap this one function for a verified identity provider in production (module docstring);
    everything that depends on it keys off the returned :class:`Actor`, not the header trust.
    """
    return Actor(id=_normalize_actor_id(actor_header), role=_normalize_role(role_header))


def require_role(*allowed: Role) -> Callable[..., Actor]:
    """Build a dependency that authorizes the current actor against ``allowed`` and returns it.

    Usage: ``actor: Actor = Depends(require_role("reviewer", "approver"))`` on a write/transition
    endpoint. The one dependency both **gates** (403 when ``actor.role`` is not in ``allowed``)
    and **yields identity** (so the handler can capture ``actor.id`` into an audit / ``*_by``
    field) — no second lookup, no way to run the body unauthorized.

    A blocked caller gets **403 Forbidden**, not 401: with the permissive dev-default the request
    is always authenticated (there is a principal), so the failure is insufficient *privilege*,
    which is 403 by definition. A real identity provider that can reject *unauthenticated*
    requests would raise 401 upstream in ``current_actor``; this gate stays a pure 403 authz check.
    """

    def _guard(actor: Actor = Depends(current_actor)) -> Actor:
        if actor.role not in allowed:
            # Name the allowed roles (not secret) so the client can self-correct; never echo the
            # caller's id back in the error (it would land in shared logs / client-visible bodies).
            raise HTTPException(
                status_code=403,
                detail=f"role '{actor.role}' not permitted (requires one of: {', '.join(allowed)})",
            )
        return actor

    return _guard
