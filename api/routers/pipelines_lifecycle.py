"""Pipeline Builder authoring LIFECYCLE (ADR-0014) — draft→approve RBAC, dry-run, diff.

This router completes the authoring lifecycle the Builder design reserved but never built: the
``PipelineGraph`` envelope already carried ``status`` + ``submitted_by`` / ``reviewed_by`` /
``approved_by`` fields (``api/pipeline.py``) as a forward-compatible seam; here the transitions
that move those fields finally exist, plus two read-only inspectors the operator needs before
blessing a graph.

Four additive endpoints, all under ``/api/pipelines`` (they never collide with the existing
save/list/versions routes in ``main.py``, which are one path segment shorter):

  1. ``POST /{name}/submit``  — draft → pending_review; ``require_role('reviewer','approver')``;
     stamps ``submitted_by`` from the authenticated actor.
  2. ``POST /{name}/approve`` — pending_review → approved; ``require_role('approver')``; stamps
     ``approved_by``; ONLY an approved graph is "blessed", and approval records the emitted
     baseline the diff compares against.
  3. ``POST /{name}/dry-run`` — resolve the graph's run-layout locators against a REAL run dir
     and report per-locator matched|ambiguous|missing|invalid + the resolved paths. READ-ONLY:
     it globs the filesystem, it never executes a tool or hands off to an orchestrator —
     **compose != execute** (ADR-0001/0003). A POST (not GET) because it is an action taking a
     target run, but it writes nothing.
  4. ``GET  /{name}/diff``    — diff the working/latest graph's locators vs the last emitted
     (approved) snapshot, so an operator sees exactly what drifted since the last blessing.

Guardrails honored (CLAUDE.md): this is wholly OFF the deterministic decision gate (ADR-0001) —
it never touches a verdict, finding, confidence, or rule, and never imports the ``bayleaf``
core. Writes go only through the append-only pipeline store (``api/pipeline_store.py``); a store
failure degrades to a generic 503 that never leaks a path/DSN. It is deliberately isolated from
``api/main.py`` (it computes its own data root and pulls the store via the factory) so it mounts
with one ``include_router`` and is unit-testable on a throwaway app.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import Actor, require_role
from api.pipeline import PipelineStatus
from api.pipeline_store import (
    PipelineGraphStore,
    get_pipeline_store,
    last_emitted,
    latest_record,
    record_emission,
    record_transition,
)

_log = logging.getLogger(__name__)

# The router owns its data root independently of ``api.main`` (which also defines one) so it stays
# import-isolated + unit-testable on a bare app. api/routers/<file> -> parents[2] is the repo root.
_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"

# The per-locator resolution verdict of a dry-run. ``invalid`` is a first-class outcome, distinct
# from ``missing``: a locator whose pattern is empty, absolute, or escapes the run dir with ``..``
# must be flagged as malformed/unsafe — silently reporting it as merely "missing" would hide a
# path-traversal attempt in a client-authored graph. matched|ambiguous|missing are the resolvable
# outcomes; invalid is the "we refused to resolve this" outcome.
ResolveStatus = Literal["matched", "ambiguous", "missing", "invalid"]

router = APIRouter(prefix="/api/pipelines", tags=["pipelines-lifecycle"])


# --- Response contracts ----------------------------------------------------------------------


class TransitionResult(BaseModel):
    """The outcome of a lifecycle transition — the new revision + who/what changed.

    Deliberately does NOT echo the ``graph`` back (no reflection surface, mirroring the save
    ack). ``version`` is the freshly-authored revision the transition created; the ``*_by``
    fields report which audit slots are now filled. ``emitted_at`` is set only on approve (the
    approved version is the emitted baseline).
    """

    name: str
    version: int
    status: PipelineStatus
    submitted_by: str | None = None
    reviewed_by: str | None = None
    approved_by: str | None = None
    created_at: str
    emitted_at: str | None = None


class LocatorResolution(BaseModel):
    """One locator resolved against a real run dir: its spec + verdict + the paths it matched.

    ``paths`` are always relative-to-run-dir POSIX strings — an absolute host path is never
    emitted (it would leak the deployment's filesystem layout). Empty for missing/invalid.
    """

    node: str | None
    kind: str
    mode: Literal["path", "glob"]
    pattern: str
    required: bool
    role: str
    on_multiple: str
    status: ResolveStatus
    paths: list[str]


class DryRunResult(BaseModel):
    """A dry-run report: per-locator resolutions + a status tally, against ``run_id``.

    ``executed`` is a hard-coded ``False`` in the contract so a consumer can never mistake a
    dry-run for a real run — this endpoint composes/inspects, it never executes (ADR-0001/0003).
    """

    name: str
    version: int
    run_id: str
    executed: Literal[False] = False
    locators: list[LocatorResolution]
    summary: dict[str, int]


class LocatorDiff(BaseModel):
    """One locator's change between the working graph and the emitted baseline.

    ``before`` is the emitted-snapshot spec (``None`` when the locator was added); ``after`` is
    the working spec (``None`` when it was removed). The spec dict is the comparable subset
    (pattern/mode/required/on_multiple) so an identity-preserving relabel isn't flagged as a change.
    """

    key: str
    node: str | None
    kind: str
    role: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class DiffResult(BaseModel):
    """Working-vs-last-emitted locator diff for ``name``.

    ``has_baseline`` is ``False`` when the pipeline was never approved/emitted — then every
    working locator is reported under ``added`` (new relative to nothing), which is honest rather
    than pretending the working graph equals a non-existent baseline.
    """

    name: str
    has_baseline: bool
    working_version: int
    emitted_version: int | None
    emitted_at: str | None
    added: list[LocatorDiff]
    removed: list[LocatorDiff]
    changed: list[LocatorDiff]
    unchanged_count: int


# --- Tolerant locator extraction (the builder graph shape lives HERE, not in the store) ------


@dataclass(frozen=True)
class _Locator:
    """A normalized run-layout locator lifted out of a (tolerant, unvalidated) builder graph."""

    node: str | None
    kind: str
    mode: Literal["path", "glob"]
    pattern: str
    required: bool
    role: str
    on_multiple: str

    @property
    def key(self) -> str:
        # Diff identity: a locator is "the same one" across versions by the node it belongs to,
        # its artifact kind, and its I/O role. \x1f (unit separator) can't occur in these tokens,
        # so it is a collision-safe join. (A relabeled pattern keeps the key -> reads as a change.)
        return f"{self.node or ''}\x1f{self.kind}\x1f{self.role}"

    def spec(self) -> dict[str, Any]:
        """The comparable subset for the diff — the parts that define WHERE/HOW it resolves."""
        return {
            "pattern": self.pattern,
            "mode": self.mode,
            "required": self.required,
            "on_multiple": self.on_multiple,
        }


def _normalize_locator(raw: Any, node: str | None) -> _Locator | None:
    """Coerce one raw locator dict into a :class:`_Locator`, tolerating several builder shapes.

    Absorbs (a) the frontend node shape ``{kind, pg: path|glob, loc, required, role, on}``, (b) the
    emitted ``run_layout`` shape ``{glob|path, parser, required, role, on_multiple}``, and (c) a
    bare ``{kind, loc}`` (mode inferred from glob metachars). Anything without a locatable pattern
    is skipped (returns ``None``) rather than raising — a missing field is a signal, not a crash
    (CLAUDE.md data-handling 2).
    """
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or raw.get("name") or "").strip()
    mode: Literal["path", "glob"]
    pattern: str
    pg = raw.get("pg")
    if pg == "path" and raw.get("loc"):
        mode, pattern = "path", str(raw.get("loc"))
    elif pg == "glob" and raw.get("loc"):
        mode, pattern = "glob", str(raw.get("loc"))
    elif raw.get("glob"):
        mode, pattern = "glob", str(raw.get("glob"))
    elif raw.get("path"):
        mode, pattern = "path", str(raw.get("path"))
    elif raw.get("loc"):
        pat = str(raw.get("loc"))
        # Infer mode when the shape only carries a bare ``loc``: glob metachars -> a glob.
        mode = "glob" if any(ch in pat for ch in "*?[") else "path"
        pattern = pat
    else:
        return None
    return _Locator(
        node=node,
        kind=kind,
        mode=mode,
        pattern=pattern.strip(),
        required=bool(raw.get("required", False)),
        role=str(raw.get("role") or "output"),
        on_multiple=str(raw.get("on") or raw.get("on_multiple") or "error"),
    )


def _extract_locators(graph: Any) -> list[_Locator]:
    """Collect every locator from a tolerant builder graph, across the shapes it may take.

    Looks in three plausible places without assuming any single schema (the ``graph`` envelope is
    deliberately unvalidated, ``api/pipeline.py``): per-node ``locators`` (the frontend DAG), a
    flat top-level ``locators`` list, and a ``run_layout.artifacts`` kind->spec map (the emitted
    layout). Every branch is isinstance-guarded so a partial/odd payload yields fewer locators,
    never an exception.
    """
    out: list[_Locator] = []
    if not isinstance(graph, dict):
        return out

    nodes = graph.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            node_key = str(node_id) if node_id is not None else None
            locs = node.get("locators")
            if isinstance(locs, list):
                for raw in locs:
                    loc = _normalize_locator(raw, node_key)
                    if loc is not None:
                        out.append(loc)

    top = graph.get("locators")
    if isinstance(top, list):
        for raw in top:
            loc = _normalize_locator(raw, None)
            if loc is not None:
                out.append(loc)

    run_layout = graph.get("run_layout")
    if isinstance(run_layout, dict):
        artifacts = run_layout.get("artifacts")
        if isinstance(artifacts, dict):
            for kind, spec in artifacts.items():
                if isinstance(spec, dict):
                    loc = _normalize_locator({**spec, "kind": kind}, None)
                    if loc is not None:
                        out.append(loc)
    return out


# --- Safe locator resolution against a run dir (READ-ONLY, traversal-hardened) ---------------


def _run_dir(run_id: str) -> Path:
    """Resolve ``run_id`` to its on-disk dir under ``data/``, refusing anything that escapes it.

    Mirrors the read-API's discipline (a real run has a ``SampleSheet.csv``) WITHOUT importing
    ``api.main`` (the router stays isolated). The resolved dir must sit inside ``data/`` so a
    crafted ``run_id`` (``../secrets``) can never aim the dry-run resolver outside the data tree.
    """
    data_root = _DATA_ROOT.resolve()
    candidate = (_DATA_ROOT / run_id).resolve()
    if not candidate.is_relative_to(data_root):
        raise HTTPException(status_code=404, detail=f"Unknown run '{run_id}'")
    if not (candidate / "SampleSheet.csv").exists():
        raise HTTPException(status_code=404, detail=f"Unknown run '{run_id}'")
    return candidate


def _resolve_locator(run_dir: Path, loc: _Locator) -> tuple[ResolveStatus, list[str]]:
    """Resolve one locator against ``run_dir``; return its verdict + relative-POSIX matched paths.

    Read-only: it stats / globs the filesystem, never opens or executes anything. A client-authored
    pattern is untrusted, so absolute paths and any ``..`` escape are refused BEFORE touching the
    filesystem (``invalid``). Glob multiplicity is a verdict, not an error: 0 -> missing, 1 ->
    matched, >1 -> ambiguous UNLESS the locator's ``on_multiple`` is ``all`` (a set is expected).
    """
    pattern = loc.pattern.strip()
    if not pattern:
        return ("invalid", [])
    pp = PurePosixPath(pattern)
    if pp.is_absolute() or pattern.startswith(("/", "\\")) or ".." in pp.parts:
        return ("invalid", [])

    root = run_dir.resolve()
    if loc.mode == "path":
        target = (run_dir / pattern).resolve()
        if not target.is_relative_to(root):  # a symlink/normalization escape -> refuse
            return ("invalid", [])
        if target.exists():
            return ("matched", [target.relative_to(root).as_posix()])
        return ("missing", [])

    # glob: keep only hits that stay inside the run dir (defense-in-depth against symlink escapes).
    try:
        hits = sorted(m for m in run_dir.glob(pattern) if m.resolve().is_relative_to(root))
    except (ValueError, OSError, NotImplementedError):
        return ("invalid", [])
    rels = [m.resolve().relative_to(root).as_posix() for m in hits]
    if not hits:
        return ("missing", [])
    if len(hits) == 1:
        return ("matched", rels)
    return ("matched", rels) if loc.on_multiple == "all" else ("ambiguous", rels)


# --- Shared store guards ---------------------------------------------------------------------


def _require_latest(store: PipelineGraphStore, name: str) -> dict[str, Any]:
    """Fetch ``name``'s latest envelope or fail cleanly (404 unknown / 503 store down, no leak)."""
    try:
        latest = latest_record(store, name)
    except Exception:  # store backend hiccup -> generic 503, never leak path/DSN (mirror the save)
        raise HTTPException(status_code=503, detail="pipeline store unavailable") from None
    if latest is None:
        raise HTTPException(status_code=404, detail=f"Unknown pipeline '{name}'")
    return latest


def _require_status(record: dict[str, Any], expected: PipelineStatus, action: str) -> None:
    """409 unless the pipeline is in the exact state ``action`` may transition FROM.

    A guarded state machine: ``submit`` only from ``draft``, ``approve`` only from
    ``pending_review``. A wrong-state request is a 409 Conflict (the resource exists but is not in
    a transitionable state) rather than a silent no-op, so the operator learns why nothing moved.
    """
    current = str(record.get("status") or "draft")
    if current != expected:
        raise HTTPException(
            status_code=409,
            detail=f"cannot {action}: pipeline is '{current}', expected '{expected}'",
        )


def _diff_row(loc: _Locator, before: _Locator | None, after: _Locator | None) -> LocatorDiff:
    """Build one diff row from the identity-carrying locator + its before/after specs."""
    return LocatorDiff(
        key=loc.key,
        node=loc.node,
        kind=loc.kind,
        role=loc.role,
        before=before.spec() if before else None,
        after=after.spec() if after else None,
    )


def _to_transition_result(record: dict[str, Any]) -> TransitionResult:
    """Project a stored envelope into the transition response (tolerant of missing fields).

    Uses ``model_validate`` so the store's ``Any``-typed values are validated at the boundary
    (the ``status`` Literal in particular) without an unchecked cast.
    """
    return TransitionResult.model_validate(
        {
            "name": record.get("name"),
            "version": record.get("version"),
            "status": record.get("status") or "draft",
            "submitted_by": record.get("submitted_by"),
            "reviewed_by": record.get("reviewed_by"),
            "approved_by": record.get("approved_by"),
            "created_at": record.get("created_at") or "",
            "emitted_at": record.get("emitted_at"),
        }
    )


# --- Endpoints -------------------------------------------------------------------------------


@router.post("/{name}/submit", response_model=TransitionResult)
def submit_pipeline(
    name: str,
    actor: Actor = Depends(require_role("reviewer", "approver")),
) -> TransitionResult:
    """Submit a draft for review: draft → pending_review, stamping ``submitted_by`` = the actor.

    Guarded to reviewer/approver (a viewer cannot advance a graph); the one dependency both
    authorizes AND yields the actor whose id is captured into the audit field. Append-only: this
    records a new version, never mutating the draft. Unknown name → 404; not a draft → 409.
    """
    store = get_pipeline_store()
    latest = _require_latest(store, name)
    _require_status(latest, expected="draft", action="submit")
    try:
        updated = record_transition(
            store, name, {"status": "pending_review", "submitted_by": actor.id}
        )
    except Exception:
        raise HTTPException(status_code=503, detail="pipeline store unavailable") from None
    if updated is None:  # raced away between the read and the append -> treat as unknown
        raise HTTPException(status_code=404, detail=f"Unknown pipeline '{name}'")
    return _to_transition_result(updated)


@router.post("/{name}/approve", response_model=TransitionResult)
def approve_pipeline(
    name: str,
    actor: Actor = Depends(require_role("approver")),
) -> TransitionResult:
    """Approve a submitted graph: pending_review → approved, stamping ``approved_by`` = the actor.

    Approver-only. ONLY an approved graph is "blessed", and approval is the emit point: it records
    the approved version as the emitted baseline (``emitted_at``) that ``GET /diff`` compares the
    working graph against. It emits/composes a baseline — it NEVER triggers a run or hands off to
    an orchestrator (ADR-0001/0003). Unknown name → 404; not pending_review → 409.
    """
    store = get_pipeline_store()
    latest = _require_latest(store, name)
    _require_status(latest, expected="pending_review", action="approve")
    try:
        updated = record_emission(store, name, {"status": "approved", "approved_by": actor.id})
    except Exception:
        raise HTTPException(status_code=503, detail="pipeline store unavailable") from None
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Unknown pipeline '{name}'")
    return _to_transition_result(updated)


@router.post("/{name}/dry-run", response_model=DryRunResult)
def dry_run_pipeline(
    name: str,
    run_id: str = Query(
        "mock_run_01",
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        description="A real run dir under data/ to resolve the graph's locators against.",
    ),
) -> DryRunResult:
    """Resolve the latest graph's locators against a real run dir — READ-ONLY, never executes.

    Reports, per locator, whether it matched exactly one artifact, matched several (ambiguous),
    matched none (missing), or was malformed/unsafe (invalid), plus the resolved relative paths.
    This is the operator's pre-flight: does the composed run-layout actually locate this run's
    artifacts? It globs the filesystem and returns — it triggers no tool and no orchestrator
    hand-off (compose != execute, ADR-0001/0003). Unknown pipeline/run → 404.
    """
    store = get_pipeline_store()
    latest = _require_latest(store, name)
    run_dir = _run_dir(run_id)

    resolutions: list[LocatorResolution] = []
    summary: dict[str, int] = {"matched": 0, "ambiguous": 0, "missing": 0, "invalid": 0}
    for loc in _extract_locators(latest.get("graph") or {}):
        status, paths = _resolve_locator(run_dir, loc)
        summary[status] += 1
        resolutions.append(
            LocatorResolution(
                node=loc.node,
                kind=loc.kind,
                mode=loc.mode,
                pattern=loc.pattern,
                required=loc.required,
                role=loc.role,
                on_multiple=loc.on_multiple,
                status=status,
                paths=paths,
            )
        )
    return DryRunResult(
        name=name,
        version=int(latest.get("version") or 0),
        run_id=run_id,
        locators=resolutions,
        summary=summary,
    )


@router.get("/{name}/diff", response_model=DiffResult)
def diff_pipeline(name: str) -> DiffResult:
    """Diff the working (latest) graph's locators vs the last emitted (approved) snapshot.

    Shows exactly what drifted since the pipeline was last blessed: locators added, removed, or
    changed (pattern/mode/required/on_multiple), plus an unchanged count. With no emitted baseline
    yet (never approved), ``has_baseline`` is ``False`` and every working locator is reported as
    ``added``. Read-only over product state; unknown pipeline → 404.
    """
    store = get_pipeline_store()
    latest = _require_latest(store, name)
    try:
        baseline = last_emitted(store, name)
    except Exception:
        raise HTTPException(status_code=503, detail="pipeline store unavailable") from None

    working = {loc.key: loc for loc in _extract_locators(latest.get("graph") or {})}
    working_version = int(latest.get("version") or 0)

    added: list[LocatorDiff] = []
    removed: list[LocatorDiff] = []
    changed: list[LocatorDiff] = []
    unchanged = 0

    if baseline is None:
        # No emitted baseline yet -> every working locator is new relative to nothing.
        added = [_diff_row(loc, before=None, after=loc) for loc in working.values()]
        return DiffResult(
            name=name,
            has_baseline=False,
            working_version=working_version,
            emitted_version=None,
            emitted_at=None,
            added=added,
            removed=removed,
            changed=changed,
            unchanged_count=0,
        )

    emitted = {loc.key: loc for loc in _extract_locators(baseline.get("graph") or {})}
    for key, wloc in working.items():
        prior = emitted.get(key)
        if prior is None:
            added.append(_diff_row(wloc, before=None, after=wloc))
        elif prior.spec() != wloc.spec():
            changed.append(_diff_row(wloc, before=prior, after=wloc))
        else:
            unchanged += 1
    for key, eloc in emitted.items():
        if key not in working:
            removed.append(_diff_row(eloc, before=eloc, after=None))

    emitted_at = baseline.get("emitted_at")
    return DiffResult(
        name=name,
        has_baseline=True,
        working_version=working_version,
        emitted_version=int(baseline.get("version") or 0),
        emitted_at=str(emitted_at) if emitted_at else None,
        added=added,
        removed=removed,
        changed=changed,
        unchanged_count=unchanged,
    )
