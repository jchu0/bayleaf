"""Sandboxed server-side file browser for the Pipeline Builder's data pickers (off-gate, read-only).

The compute host holds the GB-scale genomics inputs (FASTQ folders, reference FASTAs, panel BEDs)
that a Builder locator points at, so the "Browse…" picker for those inputs must list them
**server-side** — the browser never sees the files, only names/sizes/kinds. This router exposes one
read:

  ``GET /api/files?root=<key>&path=<rel>`` — list the directories + files directly under an
  **allowlisted** root, one level at a time.

Two hard boundaries make this safe to point at a real data host:

  1. **Allowlist, not free filesystem access.** ``root`` is a *key* into a small configured map
     (default ``{"data": <repo>/data}``, env-overridable via ``PIPEGUARD_BROWSE_ROOTS``), never a
     raw path — a caller can only ever browse inside a root an operator deliberately exposed.
  2. **Traversal-hardening (mirrors the artifact-download idiom in ``api/main.py``).** The requested
     ``root/path`` is ``resolve()``-d and asserted to still live INSIDE the resolved root; a ``..``
     escape, an absolute path component, or a symlink pointing out of the root is rejected (400/403)
     rather than followed. An unknown root key is 404; a missing directory is an honest 404, not a
     crash.

Wholly OFF the deterministic decision gate (ADR-0001): it lists file metadata, never reads content,
never touches a verdict/finding/confidence, and never runs a tool (ADR-0003). Auth is the lowest
role (any authenticated actor) — allowlisted browsing is read-only, but not anonymous.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from api.auth import Actor, require_role

router = APIRouter(prefix="/api", tags=["files"])

# The repo's ``data/`` dir — the default (and only, absent an override) allowlisted browse root.
# Computed independently of ``api.main.DATA_ROOT`` to avoid a circular import (main mounts this
# router). ``api/routers/files.py`` → parent(routers) → parent(api) → parent(repo) / "data".
_DEFAULT_DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data"

# Env override: a comma-separated ``key=abs_path`` map (e.g. "data=/srv/runs,ref=/srv/reference").
# Read per request (not cached at import) so a deployment/test can retarget the roots without a
# reimport — matching the per-call env reads in ``api.auth`` / ``api.deid``.
_ENV_BROWSE_ROOTS = "PIPEGUARD_BROWSE_ROOTS"

# Bound the query params so a hostile client can't drive a giant path/key through the resolver.
_MAX_ROOT_KEY_LEN = 128
_MAX_PATH_LEN = 4096

# The closed artifact-kind vocabulary this browser infers from a filename extension, so the Builder
# can pre-select the right locator kind. Inference only — a null kind ("I don't recognize it") is a
# first-class, honest answer, never a guess.
FileKind = Literal["fastq", "vcf", "bam", "panel_bed", "reference_fasta"]


class FileEntry(BaseModel):
    """One directory entry: a child directory or file directly under the listed path.

    ``size`` is bytes and populated for files ONLY (a directory carries ``None`` — its "size" is not
    meaningful here and stat-summing a GB-scale tree would be wasteful). ``kind`` is the
    extension-inferred artifact kind (or ``None`` when unrecognized — an honest non-answer).
    """

    model_config = ConfigDict(frozen=True)

    name: str
    is_dir: bool
    size: int | None = None
    kind: FileKind | None = None


class FileListing(BaseModel):
    """A one-level directory listing under an allowlisted root.

    ``root`` echoes the requested allowlist key; ``path`` is the normalized directory path relative
    to that root (``""`` = the root itself); ``parent`` is the relative parent path for an "up" link
    (``None`` at the root). ``entries`` is directories-first, then case-insensitive by name.
    """

    model_config = ConfigDict(frozen=True)

    root: str
    path: str
    parent: str | None
    entries: list[FileEntry]


def _browse_roots() -> dict[str, Path]:
    """Resolve the allowlisted browse roots: the ``PIPEGUARD_BROWSE_ROOTS`` override or the default.

    The override is a tolerant ``key=abs_path,key2=abs_path2`` string — a blank or ``=``-less
    segment is skipped rather than raising (a boundary parse is a signal, not a crash). If the
    override is absent or parses to nothing usable, the default ``{"data": <repo>/data}`` is used so
    the picker never dead-ends. Paths are NOT resolved here; the endpoint resolves the selected root
    at use time as part of the within-root assertion.
    """
    raw = os.environ.get(_ENV_BROWSE_ROOTS, "").strip()
    if not raw:
        return {"data": _DEFAULT_DATA_ROOT}
    roots: dict[str, Path] = {}
    for segment in raw.split(","):
        key, sep, path_str = segment.strip().partition("=")
        if not sep:
            continue  # tolerant: skip a malformed (``=``-less) segment
        key = key.strip()
        path_str = path_str.strip()
        if key and path_str:
            roots[key] = Path(path_str)
    return roots or {"data": _DEFAULT_DATA_ROOT}


def _infer_kind(name: str) -> FileKind | None:
    """Infer an artifact kind from a filename extension (double extensions like ``.vcf.gz`` too).

    Returns ``None`` for anything unrecognized — the browser reports "kind unknown" honestly rather
    than forcing a guess. Case-insensitive.
    """
    lower = name.lower()
    if lower.endswith((".fastq.gz", ".fastq", ".fq.gz", ".fq")):
        return "fastq"
    if lower.endswith((".vcf.gz", ".vcf")):
        return "vcf"
    if lower.endswith(".bam"):
        return "bam"
    if lower.endswith(".bed"):
        return "panel_bed"
    if lower.endswith((".fasta.gz", ".fasta", ".fa.gz", ".fa")):
        return "reference_fasta"
    return None


def _posix_parent(rel: str) -> str:
    """The parent of a non-empty relative posix path (``""`` when the parent is the root)."""
    parent = PurePosixPath(rel).parent
    return "" if str(parent) == "." else str(parent)


@router.get("/files")
def list_files(
    root: str = Query(
        ...,
        max_length=_MAX_ROOT_KEY_LEN,
        description="Allowlisted root key (e.g. 'data') — a configured key, never a raw path.",
    ),
    path: str = Query(
        "",
        max_length=_MAX_PATH_LEN,
        description="Directory to list, relative to the root ('' or omitted = the root itself).",
    ),
    _actor: Actor = Depends(require_role("viewer", "reviewer", "approver")),
) -> FileListing:
    """List directories + files one level under an allowlisted root (sandboxed, read-only).

    Traversal-hardened exactly like the artifact download in ``api/main.py``: the requested
    ``root/path`` is resolved and asserted to remain INSIDE the resolved root. A ``..`` component or
    an absolute path is a **400**; a path (or symlink) that resolves outside the root is a **403**;
    an unknown root key or a missing directory is a **404**. Nothing here reads file content, runs a
    tool, or touches a verdict (ADR-0001/0003).
    """
    base = _browse_roots().get(root)
    if base is None:
        raise HTTPException(status_code=404, detail=f"unknown root '{root}'")

    # Reject obvious escapes with a 400 BEFORE resolving — an explicit, honest rejection for the
    # two illegal shapes a browse UI never needs. The within-root assertion below is the real
    # backstop (it also catches symlink escapes the pre-checks can't see), so this is defense in
    # depth, not the sole guard.
    raw = path.strip()
    if raw.startswith("/"):
        raise HTTPException(status_code=400, detail="absolute path not allowed")
    rel = raw.strip("/")
    if any(part == ".." for part in rel.split("/")):
        raise HTTPException(status_code=400, detail="path traversal ('..') not allowed")

    base_resolved = base.resolve()
    target = (base / rel).resolve() if rel else base_resolved
    # THE load-bearing check: after resolving every symlink, the target must still be the root or a
    # descendant of it. A crafted path or an escaping symlink lands outside → 403, never followed.
    if target != base_resolved and not target.is_relative_to(base_resolved):
        raise HTTPException(status_code=403, detail="path escapes the allowlisted root")
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="directory not found")

    entries: list[FileEntry] = []
    for child in target.iterdir():
        # Tolerant stat: a broken symlink or a race-removed entry yields is_dir=False / size=None
        # rather than a 500 — a boundary read is a signal, not a crash (CLAUDE.md data handling).
        try:
            is_dir = child.is_dir()
        except OSError:
            is_dir = False
        size: int | None = None
        if not is_dir:
            try:
                size = child.stat().st_size
            except OSError:
                size = None
        entries.append(
            FileEntry(
                name=child.name,
                is_dir=is_dir,
                size=size,
                kind=None if is_dir else _infer_kind(child.name),
            )
        )
    # Directories first, then case-insensitive by name — a stable, human-friendly order.
    entries.sort(key=lambda entry: (not entry.is_dir, entry.name.lower()))

    # Echo the CANONICAL path relative to the resolved root (symlink-free), so the returned path and
    # its parent link are always well-formed regardless of how the client spelled the request.
    rel_out = "" if target == base_resolved else target.relative_to(base_resolved).as_posix()
    parent = None if rel_out == "" else _posix_parent(rel_out)
    return FileListing(root=root, path=rel_out, parent=parent, entries=entries)
