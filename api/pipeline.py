"""Pipeline Builder save/version data contract (ADR-0014) — a PRODUCT-domain envelope.

Framework boundary + guardrail (CLAUDE.md 1, ADR-0001): this module holds the pipeline
*contract* (the pydantic models), with **no** FastAPI import and **no** import of the
``bayleaf`` core — a saved builder graph is product state, wholly OFF the deterministic
decision gate. It never becomes a verdict, finding, provenance event, or ledger row. It
mirrors ``api/feedback.py``: a self-contained product seam beside the read-API, with its
pluggable, env-selected sink in ``api/pipeline_store.py`` (ADR-0016).

Scoping note (deliberate): the builder's node/edge shape is still churning under an active
design pass, so ``graph`` is stored as a **tolerant, versioned envelope** — an arbitrary JSON
dict kept as-is, never deeply validated. ``schema_version`` tags which builder payload shape
the ``graph`` speaks (e.g. ``builder/0.1``) so a consumer can branch on it; ``version`` is a
server-authored monotonic revision per ``name``. This lets the builder churn without breaking
the store or forcing a migration on every field rename.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# The builder payload shape the `graph` dict speaks, when the client omits it. This is the
# ENVELOPE tag (builder/<major.minor>), not a record-format integer — the graph internals are
# intentionally unvalidated, so a consumer keys off this to interpret them.
DEFAULT_SCHEMA_VERSION = "builder/0.1"

# The review lifecycle a saved graph moves through: a save mints a `draft`; a (not-yet-built)
# review transition promotes it to `pending_review`, and an approver to `approved`. Reserved
# NOW per the maintainer's builder-versioning decision (draft → save → approve with reviewer/
# approver RBAC) so the shape is forward-compatible before the approval flow + auth exist.
PipelineStatus = Literal["draft", "pending_review", "approved"]


class PipelineGraphIn(BaseModel):
    """The ``POST /api/pipelines`` body — a builder graph to save under a name.

    ``extra="forbid"`` blocks any smuggled server-authored field (``id``/``version``/
    ``created_at`` are the server's to set, never the client's). ``name``/``profile``/
    ``schema_version`` are charset-locked identifiers so ``name`` is a safe path segment for
    ``GET /api/pipelines/{name}`` and can never forge a JSONL line or escape a path. ``graph``
    is an arbitrary JSON object stored AS-IS — deliberately not validated node-by-node so the
    builder's shape can churn (see the module docstring).
    """

    model_config = ConfigDict(extra="forbid")

    # Slug-like identifier (no spaces) — it doubles as the versioning key and a URL path segment,
    # so it borrows the run_id charset discipline. A display title should be slugified client-side.
    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    schema_version: str = Field(
        DEFAULT_SCHEMA_VERSION, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"
    )
    # The emitted run_layout / graph payload. Any JSON object; internals are opaque to the store.
    graph: dict[str, Any]
    profile: str | None = Field(None, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")


class PipelineGraph(BaseModel):
    """A stored builder graph: the tolerant envelope plus the server-authored id/version/time.

    The persisted + returned shape. ``id`` and ``created_at`` are minted server-side per save;
    ``version`` is a monotonic per-``name`` revision authored by the store under its write lock
    (max existing + 1), so two saves of the same name yield versions 1, 2, … deterministically.
    ``graph`` round-trips byte-for-byte — the store never rewrites the payload it was handed.

    ``status`` + the ``*_by`` fields RESERVE the draft → save → approve review flow (reviewer/
    approver RBAC) the maintainer chose for the Builder: a save is a ``draft``; the promote/
    approve transitions and their auth are a documented, not-yet-built seam. The ``*_by`` fields
    are **server-authored** from the authenticated principal when auth lands — never client-set
    (``PipelineGraphIn`` is ``extra="forbid"`` and does not declare them), so no identity/PII
    enters through the save body. Missing on an older stored record → the defaults apply
    (tolerant read), so reserving them now needs no migration.
    """

    id: str
    name: str
    schema_version: str
    version: int
    created_at: str
    graph: dict[str, Any]
    profile: str | None = None
    # Reserved review lifecycle + RBAC (see the class docstring) — default draft / unassigned.
    status: PipelineStatus = "draft"
    submitted_by: str | None = None
    reviewed_by: str | None = None
    approved_by: str | None = None


class PipelineGraphAck(BaseModel):
    """The 201 response to a save. Echoes the server-authored ``id``/``version``/``created_at``
    (so the client learns which revision it just created) but NOT the graph back — no reflection
    surface, mirroring ``FeedbackAck``'s minimalism. ``status`` reports the created revision's
    review-lifecycle state — always ``draft`` on save (the approve transition is a separate,
    not-yet-built step), so a client knows a fresh save is an unapproved draft."""

    id: str
    name: str
    version: int
    schema_version: str
    created_at: str
    status: PipelineStatus = "draft"
