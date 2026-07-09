"""Settings/config AUTHORING router (T-051) — a draft->approve override store, OFF the gate.

What this is: a fill-and-save surface for QC-threshold *overrides* with a reviewer/approver
RBAC lifecycle, mirroring the Pipeline Builder store's shape (``api/pipeline.py`` +
``api/pipeline_store.py``). An operator saves a threshold-override payload as a ``draft``; an
approver promotes the latest revision to ``approved``. Every save/transition is an immutable,
audited revision (append-only), so the history is a tamper-evident edit trail.

What this is NOT (the load-bearing guardrail, ADR-0001 / CLAUDE.md architecture 1): this router
**never mutates the live runbook** and never touches a verdict, finding, confidence, or rule.
``DEFAULT_RUNBOOK`` in ``src/pipeguard/runbook.py`` is untouched. This is an authoring/override
*ledger* — approving an override records intent; it does not change how any run is gated. A
future step (documented in the module + the integration notes, not built here) could read the
latest ``approved`` override for a name and layer it onto a per-run runbook *copy* at gate time,
keeping the deterministic core and the authoring surface cleanly separated.

Framework note: this is the delivery layer (``api/``), so importing FastAPI is fine — the
prohibition is on the framework-agnostic core, which this never imports. The pluggable,
env-selected sink lives in ``api/settings_store.py`` (ADR-0016), degrading to offline JSONL.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.auth import Actor, require_role
from api.settings_store import get_settings_store

_log = logging.getLogger(__name__)

# The review lifecycle a saved override moves through: a save mints a ``draft``; an approver
# promotes the latest revision to ``approved``. ``pending_review`` is RESERVED for a future
# submit-for-review transition (not built here) so the shape is forward-compatible — mirrors
# ``PipelineStatus`` in ``api/pipeline.py``.
SettingsStatus = Literal["draft", "pending_review", "approved"]

# --- Lenient sanity envelope for an override payload ----------------------------------------
# We deliberately DO NOT validate the exact override schema: the payload is a tolerant, versioned
# envelope kept as-is (units and shape vary, and the authoring UI is still churning), so a
# missing/odd field is a *signal*, not a crash (CLAUDE.md data-handling 2). We reject only
# payloads that are OBVIOUSLY nonsense so a fat-fingered save can't persist a garbage gate:
#   - not a JSON object, or an empty object (nothing to override);
#   - a threshold-ish numeric value that is non-finite (NaN/Inf) or wildly out of range.
# Bounds are intentionally WIDE (fractions live in ~[0,1], coverage ~30x, insert sizes in the
# hundreds) — this catches clear errors (a gate of 1e12, a negative coverage) without pretending
# to know each metric's true clinical range, which is not this tool's job (life-science guard 3).
_THRESHOLD_KEYS = frozenset(
    {"gate", "hard_fail", "borderline_band", "threshold", "value", "warn", "min", "max"}
)
# A value past this magnitude is garbage regardless of unit — no QC metric is measured in millions.
_ABS_BOUND = 1_000_000.0
# Keys that are relative fractions (a fraction OF the gate) must live in [0, 1]; a "band" of 5 is
# a clear unit error (someone typed 5% as 5, not 0.05).
_FRACTION_KEYS = frozenset({"borderline_band"})


def _is_number(value: Any) -> bool:
    """True for a real int/float, EXCLUDING bool (``True``/``False`` are ints in Python but a
    boolean gate is a type error, not a threshold)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_numeric(key: str, value: float) -> None:
    """Reject a single threshold-ish number that is non-finite or obviously out of range.

    Raises ``ValueError`` (mapped to 422 by the ``field_validator``) with the offending KEY only
    — never a leaked value/DSN. Keys are the client's own labels, not secrets.
    """
    if not math.isfinite(value):
        raise ValueError(f"threshold override '{key}' must be a finite number")
    if key in _FRACTION_KEYS:
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"threshold override '{key}' must be a fraction in [0, 1]")
        return
    # Gates/hard-fails are non-negative in every metric the runbook gates on; a negative one is a
    # clear error. The wide absolute bound catches fat-fingered garbage without unit assumptions.
    if value < 0 or value > _ABS_BOUND:
        raise ValueError(f"threshold override '{key}' is out of range")


def _sanity_check_payload(payload: dict[str, Any]) -> None:
    """Walk the override payload leniently, rejecting only obviously-nonsense threshold numbers.

    Recurses through nested dicts/lists (the override may be flat ``{our_key: {...}}`` or nested)
    and bounds-checks any value under a known threshold key. Everything else is tolerated as-is
    — an unrecognized field is a signal for a downstream consumer, never a reason to 422.
    """
    if not payload:
        raise ValueError("empty threshold override (nothing to save)")
    _walk(payload)


def _walk(node: Any) -> None:
    """Depth-first tolerant traversal applying :func:`_check_numeric` to threshold-keyed numbers."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _THRESHOLD_KEYS and _is_number(value):
                _check_numeric(key, float(value))
            else:
                _walk(value)  # recurse into nested structures; ignore non-threshold scalars
    elif isinstance(node, list):
        for item in node:
            _walk(item)
    # scalars under non-threshold keys are tolerated as-is (kept exactly, never validated)


class ThresholdOverrideIn(BaseModel):
    """The ``POST /api/settings/thresholds`` body — a threshold-override draft to save under a name.

    ``extra="forbid"`` is the structural guard (mirrors ``FeedbackContext`` / ``PipelineGraphIn``):
    it blocks any smuggled SERVER-authored field (``id``/``version``/``created_at``/``status``)
    AND any identity/audit field (``submitted_by``/``reviewed_by``/``approved_by``) — those are
    the server's to set from the authenticated :class:`Actor`, never the client's, so no
    operator identity/PII can enter through the body. ``name`` is charset-locked so it is a safe
    URL path segment for ``GET /api/settings/thresholds/{name}`` and can never forge a JSONL line.
    ``payload`` is arbitrary threshold-override JSON stored AS-IS after a LENIENT sanity check
    (see :func:`_sanity_check_payload`) — deliberately not validated field-by-field.
    """

    model_config = ConfigDict(extra="forbid")

    # Slug-like identifier (no spaces) — it doubles as the versioning key and a URL path segment,
    # so it borrows the pipeline/run_id charset discipline. Titles are slugified client-side.
    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    # Arbitrary override JSON (e.g. {"qc.q30": {"gate": 0.9, "hard_fail": 0.8}}). Internals are
    # opaque to the store; only the lenient sanity envelope below runs, never a schema match.
    payload: dict[str, Any]

    @field_validator("payload")
    @classmethod
    def _sanity(cls, v: dict[str, Any]) -> dict[str, Any]:
        # A 422 here (via ValueError) means the payload is obviously nonsense, not merely unknown
        # shape — the store stays tolerant of shape, strict only on clearly-broken numbers.
        _sanity_check_payload(v)
        return v


class ThresholdOverride(BaseModel):
    """A stored threshold-override revision: the tolerant envelope + server-authored provenance.

    The persisted + returned shape. ``id``/``created_at`` are minted server-side per save;
    ``version`` is a monotonic per-``name`` revision authored by the store under its write lock.
    ``payload`` round-trips byte-for-byte — the store never rewrites what it was handed.

    ``status`` + the ``*_by`` fields carry the draft->approve lifecycle. They are ALL
    server-authored from the authenticated :class:`Actor` at the transition (``submitted_by`` on
    save, ``approved_by`` on approve) — never client-set. Missing on an older stored record ->
    the defaults apply (tolerant read), so the shape needs no migration.
    """

    id: str
    name: str
    version: int
    created_at: str
    payload: dict[str, Any]
    status: SettingsStatus = "draft"
    submitted_by: str | None = None
    reviewed_by: str | None = None
    approved_by: str | None = None


class ThresholdOverrideAck(BaseModel):
    """The 201 response to a save. Echoes the server-authored ``id``/``version``/``created_at`` and
    the ``submitted_by`` actor (so the client learns which revision it authored) but NOT the
    payload back — no reflection surface, mirroring ``PipelineGraphAck``/``FeedbackAck``."""

    id: str
    name: str
    version: int
    created_at: str
    status: SettingsStatus = "draft"
    submitted_by: str | None = None


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.post("/thresholds", status_code=201)
def save_threshold_override(
    body: ThresholdOverrideIn,
    actor: Actor = Depends(require_role("reviewer", "approver")),
) -> ThresholdOverrideAck:
    """Save a QC-threshold override as a ``draft`` — an AUTHORING write, OFF the deterministic gate.

    Requires ``reviewer`` or ``approver`` (a ``viewer`` gets 403). Mints a server-authored ``id`` +
    ``created_at`` and captures ``submitted_by`` from the authenticated actor (never the body); the
    store authors the monotonic per-name ``version`` (max existing + 1) atomically, so re-saving a
    name yields 2, 3, …. The ``payload`` is stored AS-IS after a lenient sanity check — it never
    mutates the live runbook or feeds a rule/verdict. A write that fails (disk full, DB down
    mid-flight) maps to a generic 503 — never leaking the path, DSN, or the payload.
    """
    override_id = uuid.uuid4().hex  # stdlib uuid on purpose — no coupling to the core's ids
    created_at = datetime.now(timezone.utc).isoformat()
    # Everything but ``version``, which the store authors atomically under its lock. A save mints a
    # ``draft`` with ``submitted_by`` = the actor; the reviewer/approver fields stay null until the
    # approve transition (server-authored there too, never client-set — extra="forbid" on the body).
    record: dict[str, Any] = {
        "id": override_id,
        "created_at": created_at,
        "name": body.name,
        "payload": body.payload,
        "status": "draft",
        "submitted_by": actor.id,
        "reviewed_by": None,
        "approved_by": None,
    }
    try:
        stored = get_settings_store().append(record)
    except Exception:
        raise HTTPException(status_code=503, detail="settings store unavailable") from None
    return ThresholdOverrideAck(
        id=stored["id"],
        name=stored["name"],
        version=stored["version"],
        created_at=stored["created_at"],
        status=stored["status"],
        submitted_by=stored["submitted_by"],
    )


@router.get("/thresholds")
def list_threshold_overrides() -> list[ThresholdOverride]:
    """The override catalog: the LATEST revision of each distinct name, sorted by name.

    Read-only over authoring state (never the decision domain). The store keeps every revision;
    collapsing to the latest per name is a presentation concern kept in the API layer (CLAUDE.md
    architecture guardrail 1). Use ``GET /api/settings/thresholds/{name}`` for a name's full
    version history. Unauthenticated reads are fine (no ``require_role``) — this is not a write.
    """
    try:
        records = get_settings_store().list()
    except Exception:
        raise HTTPException(status_code=503, detail="settings store unavailable") from None
    latest: dict[str, dict[str, Any]] = {}
    for r in records:
        name = str(r["name"])
        if name not in latest or int(r["version"]) > int(latest[name]["version"]):
            latest[name] = r
    return [ThresholdOverride.model_validate(latest[name]) for name in sorted(latest)]


@router.get("/thresholds/{name}")
def get_threshold_override_versions(name: str) -> list[ThresholdOverride]:
    """One override's full revision history, ascending by ``version`` (the draft->approve trail).

    Read-only over authoring state. 404 if the name has no saved revisions (mirrors the run/pipeline
    endpoints' unknown-id 404). The store-read is wrapped so a backend failure maps to a generic
    503 without leaking the path/DSN; the 404 is raised OUTSIDE that guard so it is never masked.
    """
    try:
        records = get_settings_store().get_versions(name)
    except Exception:
        raise HTTPException(status_code=503, detail="settings store unavailable") from None
    if not records:
        raise HTTPException(status_code=404, detail=f"Unknown settings override '{name}'")
    return [ThresholdOverride.model_validate(r) for r in records]


@router.post("/thresholds/{name}/approve", status_code=201)
def approve_threshold_override(
    name: str,
    actor: Actor = Depends(require_role("approver")),
) -> ThresholdOverride:
    """Approve an override — an audited transition that requires ``approver`` (reviewer gets 403).

    Append-only, ON PURPOSE (the same immutable-audit-trail philosophy as the event ledger,
    ADR-0002): approving does NOT mutate the draft row; it writes a NEW revision that copies the
    latest payload with ``status=approved`` and ``approved_by`` = the authenticated actor. So the
    history preserves both the draft and the approval as distinct, tamper-evident edits, and
    ``GET /api/settings/thresholds`` (latest per name) now reports the approved revision.

    404 if the name has no revisions to approve. Still OFF the gate — this records approval intent
    into the override ledger; it does NOT change the live runbook or any verdict (see module doc).
    """
    store = get_settings_store()
    try:
        versions = store.get_versions(name)
    except Exception:
        raise HTTPException(status_code=503, detail="settings store unavailable") from None
    if not versions:
        raise HTTPException(status_code=404, detail=f"Unknown settings override '{name}'")
    latest = versions[-1]  # get_versions is ascending by version
    # New immutable approved revision carrying the latest payload forward. ``submitted_by`` /
    # ``reviewed_by`` are preserved from the prior revision (tolerant .get — an older row may omit
    # them); ``approved_by`` is authored HERE from the actor, never trusted from any input.
    record: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "name": name,
        "payload": latest.get("payload", {}),
        "status": "approved",
        "submitted_by": latest.get("submitted_by"),
        "reviewed_by": latest.get("reviewed_by"),
        "approved_by": actor.id,
    }
    try:
        stored = store.append(record)
    except Exception:
        raise HTTPException(status_code=503, detail="settings store unavailable") from None
    return ThresholdOverride.model_validate(stored)
