"""Pluggable sink for saved Pipeline Builder graphs (ADR-0014/0016) — a PRODUCT store.

A saved builder graph is product state, a **separate concern** from the decision projection
(the ``Repository`` port): its rows never mix with runs/cards/events and never re-enter the
gate. This mirrors ``api/feedback_store.py`` over the shared :mod:`api.base_store` generic — three
adapters, env-selected via ``PIPEGUARD_PIPELINE_STORE`` (default ``jsonl``); the DB adapters
**degrade to the offline JSONL** if selection fails (missing extra / no DSN / unreachable server),
so a misconfigured DB never breaks the save path — it just falls back to the file.

  - :class:`JsonlPipelineGraphStore` — default, zero-dep append-only file
    (``PIPEGUARD_PIPELINE_PATH``).
  - :class:`SqlitePipelineGraphStore` — a ``pipeline_graphs`` table
    (stdlib; ``PIPEGUARD_PIPELINE_DB``).
  - :class:`PostgresPipelineGraphStore` — a ``pipeline_graphs`` table
    (``[postgres]`` extra; ``DATABASE_URL``).

Versioning contract: ``append`` authors a monotonic ``version`` per ``name`` (max existing + 1)
UNDER the write lock, so it is atomic within a worker — the same honest single-worker limit the
feedback sink documents (multi-worker needs a file lock / a real DB sequence, a documented seam).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from api.base_store import JsonlDocStore, SqliteStore, select_backend

# The store Protocol has a method named ``list`` (per its contract), which shadows the builtin
# ``list`` inside the class bodies — so a ``-> list[...]`` return annotation resolves to the method,
# not the type. Module-level aliases (bound before any shadow) keep the annotations unambiguous.
_Record = dict[str, Any]
_Records = list[dict[str, Any]]

_ENV_PIPELINE_STORE = "PIPEGUARD_PIPELINE_STORE"
_ENV_PIPELINE_PATH = "PIPEGUARD_PIPELINE_PATH"
_ENV_PIPELINE_DB = "PIPEGUARD_PIPELINE_DB"
_ENV_DATABASE_URL = "DATABASE_URL"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PIPELINE_PATH = _REPO_ROOT / "pipeline_graphs.jsonl"
_DEFAULT_PIPELINE_DB = _REPO_ROOT / "pipeline_graphs.sqlite"

# Serialize appends within a worker so concurrent saves can't interleave a JSONL line or race the
# max-version read-then-write. Multi-worker needs a file lock / a DB sequence — a documented seam,
# not built (same honest limit as the JSONL note in ADR-0016 / feedback_store.py). Shared by all
# three adapters of THIS store.
_WRITE_LOCK = threading.Lock()

# The indexed columns lifted out of a record for querying; the full record is always kept as a
# JSON document alongside, so nothing is lost and the graph payload round-trips exactly.
_PIPELINE_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS pipeline_graphs (
    id             TEXT PRIMARY KEY,
    created_at     TEXT,
    name           TEXT,
    version        INTEGER,
    schema_version TEXT,
    profile        TEXT,
    record         TEXT NOT NULL
);
"""
_PIPELINE_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS pipeline_graphs (
    id             TEXT PRIMARY KEY,
    created_at     TIMESTAMPTZ,
    name           TEXT,
    version        INTEGER,
    schema_version TEXT,
    profile        TEXT,
    record         JSONB NOT NULL
);
"""


class PipelineGraphStore(Protocol):
    """Append-only, versioned sink for saved builder graphs.

    ``append`` persists one server-partial record dict (everything but ``version``), AUTHORS the
    monotonic per-name ``version`` atomically, and returns the completed stored record. ``list``
    returns every stored envelope (optionally filtered to one name); ``get_versions`` returns one
    name's revisions ascending by ``version``.
    """

    def append(self, record: _Record) -> _Record: ...
    def list(self, name: str | None = None) -> _Records: ...
    def get_versions(self, name: str) -> _Records: ...


def _next_version(existing: list[dict[str, Any]], name: str) -> int:
    """The next monotonic revision for ``name`` = max existing version for that name + 1.

    Missing/malformed versions are treated as 0 (tolerant boundary, CLAUDE.md data-handling 2),
    so a first save of a name yields 1 and a corrupt row can never crash the version author.
    """
    versions = (int(r.get("version") or 0) for r in existing if r.get("name") == name)
    return max(versions, default=0) + 1


def _indexed(record: dict[str, Any]) -> tuple[Any, ...]:
    """Pull the indexed columns out of a record (the full record rides along as JSON)."""
    return (
        record.get("id"),
        record.get("created_at"),
        record.get("name"),
        record.get("version"),
        record.get("schema_version"),
        record.get("profile"),
    )


# --- JSONL (default, offline) ---------------------------------------------------------------


def pipeline_path() -> Path:
    """The JSONL sink path, resolved at call-time from the env (so tests monkeypatch cleanly)."""
    raw = os.environ.get(_ENV_PIPELINE_PATH, "").strip()
    return Path(raw) if raw else _DEFAULT_PIPELINE_PATH


class JsonlPipelineGraphStore(JsonlDocStore):
    """Append-only JSONL file — the zero-dependency default. The base's ``json.dumps`` escapes every
    value so an arbitrary ``graph`` payload with ``\\n`` or ``"`` can't forge a second line."""

    _lock = _WRITE_LOCK
    _tolerant = False

    def _resolve_path(self) -> Path:
        return pipeline_path()

    def append(self, record: _Record) -> _Record:
        # Read-then-append UNDER one lock (the base's ``_append_authored``) so the max-version scan
        # and the write are one atomic step — no two concurrent name-saves pick the same version.
        return self._append_authored(
            lambda rows: {**record, "version": _next_version(rows, str(record["name"]))}
        )

    def list(self, name: str | None = None) -> _Records:
        rows = self._read_all()
        if name is not None:
            rows = [r for r in rows if r.get("name") == name]
        return sorted(rows, key=lambda r: (str(r.get("name") or ""), int(r.get("version") or 0)))

    def get_versions(self, name: str) -> _Records:
        rows = [r for r in self._read_all() if r.get("name") == name]
        return sorted(rows, key=lambda r: int(r.get("version") or 0))


# --- SQLite (a real DB, still offline + zero-dep) -------------------------------------------


def pipeline_db_path() -> str:
    """The SQLite pipeline-DB path (``PIPEGUARD_PIPELINE_DB`` or the repo-root default)."""
    return os.environ.get(_ENV_PIPELINE_DB, "").strip() or str(_DEFAULT_PIPELINE_DB)


class SqlitePipelineGraphStore(SqliteStore):
    """A ``pipeline_graphs`` table in SQLite (stdlib). A fresh connection per op keeps it
    thread-safe under FastAPI's sync threadpool without pinning a connection to one thread."""

    _ddl = _PIPELINE_DDL_SQLITE

    def __init__(self, path: str | None = None) -> None:
        super().__init__(path or pipeline_db_path())

    def append(self, record: _Record) -> _Record:
        with _WRITE_LOCK:
            conn = self._connect()
            try:
                # MAX(version) + INSERT on the same connection under the lock = atomic per-name
                # versioning within the worker (mirrors the JSONL read-then-append discipline).
                row = conn.execute(
                    "SELECT MAX(version) FROM pipeline_graphs WHERE name = ?", (record["name"],)
                ).fetchone()
                stored = {**record, "version": int(row[0] or 0) + 1}
                conn.execute(
                    """INSERT INTO pipeline_graphs
                       (id, created_at, name, version, schema_version, profile, record)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (*_indexed(stored), json.dumps(stored, ensure_ascii=False)),
                )
                conn.commit()
            finally:
                conn.close()
        return stored

    def list(self, name: str | None = None) -> _Records:
        conn = self._connect()
        try:
            if name is None:
                rows = conn.execute(
                    "SELECT record FROM pipeline_graphs ORDER BY name, version"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT record FROM pipeline_graphs WHERE name = ? ORDER BY version", (name,)
                ).fetchall()
            return [json.loads(r[0]) for r in rows]
        finally:
            conn.close()

    def get_versions(self, name: str) -> _Records:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT record FROM pipeline_graphs WHERE name = ? ORDER BY version", (name,)
            ).fetchall()
            return [json.loads(r[0]) for r in rows]
        finally:
            conn.close()


# --- Postgres (production; [postgres] extra, off by default) --------------------------------


class PostgresPipelineGraphStore:
    """A ``pipeline_graphs`` table in Postgres. Lazy-imports psycopg (the ``[postgres]`` extra) and
    uses ``DATABASE_URL``; a fresh short-lived connection per op (a pool is the documented seam)."""

    def __init__(self, dsn: str | None = None) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise RuntimeError(
                "PostgresPipelineGraphStore needs the 'postgres' extra (psycopg)."
            ) from exc
        self._dsn = dsn or os.environ.get(_ENV_DATABASE_URL, "").strip()
        if not self._dsn:
            raise RuntimeError("PostgresPipelineGraphStore needs DATABASE_URL.")
        self._psycopg = psycopg
        with self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(_PIPELINE_DDL_POSTGRES)  # fail fast at selection if unreachable

    def append(self, record: _Record) -> _Record:
        from psycopg.types.json import Jsonb

        with _WRITE_LOCK, self._psycopg.connect(self._dsn, autocommit=True) as conn:
            row = conn.execute(
                "SELECT MAX(version) FROM pipeline_graphs WHERE name = %s", (record["name"],)
            ).fetchone()
            current = int(row[0]) if row and row[0] is not None else 0
            stored = {**record, "version": current + 1}
            conn.execute(
                """INSERT INTO pipeline_graphs
                   (id, created_at, name, version, schema_version, profile, record)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING""",
                (*_indexed(stored), Jsonb(stored)),
            )
        return stored

    def list(self, name: str | None = None) -> _Records:
        from psycopg.rows import dict_row

        with self._psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            if name is None:
                rows = conn.execute(
                    "SELECT record FROM pipeline_graphs ORDER BY name, version"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT record FROM pipeline_graphs WHERE name = %s ORDER BY version", (name,)
                ).fetchall()
            return [r["record"] for r in rows]

    def get_versions(self, name: str) -> _Records:
        from psycopg.rows import dict_row

        with self._psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            rows = conn.execute(
                "SELECT record FROM pipeline_graphs WHERE name = %s ORDER BY version", (name,)
            ).fetchall()
            return [r["record"] for r in rows]


def get_pipeline_store() -> PipelineGraphStore:
    """Select the pipeline sink from the environment (default: the offline JSONL file).

    ``PIPEGUARD_PIPELINE_STORE=sqlite|postgres`` swaps in a DB adapter; ANY failure constructing
    it (missing extra / DSN, unwritable path, unreachable server) degrades to the JSONL store — see
    :func:`api.base_store.select_backend` (the shared degrade-to-JSONL ladder).
    """
    jsonl: Callable[[], PipelineGraphStore] = JsonlPipelineGraphStore
    sqlite: Callable[[], PipelineGraphStore] = SqlitePipelineGraphStore
    postgres: Callable[[], PipelineGraphStore] = PostgresPipelineGraphStore
    return select_backend(_ENV_PIPELINE_STORE, jsonl=jsonl, sqlite=sqlite, postgres=postgres)


# --- Lifecycle transitions over the append-only versioned stream (ADR-0014) -----------------
# The Builder's draft -> pending_review -> approved lifecycle and its emitted-snapshot baseline
# are recorded by APPENDING a new version of the envelope, never by mutating a stored row. Why
# append, not update: the JSONL default has no in-place update primitive, and append-only is the
# project's ledger discipline (ADR-0002) — every transition becomes an immutable, auditable
# revision, and the "current" state of a pipeline is simply its latest version. These compose
# over the store Protocol (``get_versions`` + ``append``) so ONE implementation serves the JSONL
# / SQLite / Postgres adapters with no per-adapter duplication, and they never peer inside the
# tolerant ``graph`` envelope (its shape stays the delivery layer's concern).
#
# Concurrency: read-latest-then-append is atomic only WITHIN a worker (``append`` authors the
# version under the store's write lock, but the latest-read happens just before it). That is the
# same honest single-worker limit the save path already documents; multi-worker needs a DB
# sequence / row lock — a documented seam, not built.


def latest_record(store: PipelineGraphStore, name: str) -> _Record | None:
    """The highest-``version`` stored envelope for ``name``, or ``None`` if it has no revisions.

    ``get_versions`` is ascending by version, so the last element is the current state. Returns
    ``None`` (not a raise) for an unknown name so a caller can map it to a 404 explicitly.
    """
    versions = store.get_versions(name)
    return versions[-1] if versions else None


def record_transition(store: PipelineGraphStore, name: str, updates: _Record) -> _Record | None:
    """Append a new version of ``name``'s latest envelope with ``updates`` overlaid (append-only).

    Copies the latest stored envelope, overlays ``updates`` (e.g. a new ``status`` plus a ``*_by``
    audit field captured from the authenticated actor), mints a fresh server ``id`` +
    ``created_at``, and appends it so the store authors the next ``version`` under its lock. The
    ``graph`` / ``profile`` / prior audit fields carry forward untouched (the tolerant envelope is
    never rewritten). Returns the new stored record, or ``None`` if ``name`` has no versions (an
    unknown pipeline -> the caller raises 404). The state-machine check (which status may go to
    which) is the caller's job: this store method is deliberately policy-free and shape-agnostic.
    """
    latest = latest_record(store, name)
    if latest is None:
        return None
    # Drop the server-authored ``version`` so ``append`` re-authors the next one; a fresh id +
    # timestamp mark this as a distinct revision in the audit trail (never reusing the prior row's).
    new_record: _Record = {
        **latest,
        **updates,
        "id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    new_record.pop("version", None)
    return store.append(new_record)


def record_emission(
    store: PipelineGraphStore, name: str, updates: _Record | None = None
) -> _Record | None:
    """Record an emitted snapshot of ``name``'s latest envelope — the ``diff`` baseline.

    An emission is a transition that additionally stamps ``emitted_at``, marking that version as
    the last-emitted / blessed baseline ``GET .../diff`` compares the working graph against.
    Approval is the emit point: an approved graph is the blessed thing that gets composed into a
    ``run_layout`` (compose != execute — this NEVER triggers a run, ADR-0001/0003), so ``approve``
    calls this with ``{"status": "approved", "approved_by": actor.id}``. The ``graph`` envelope
    carries forward unchanged, so the snapshot's locators are recoverable at diff time without the
    store ever needing to understand the builder's graph shape.
    """
    stamped: _Record = {**(updates or {}), "emitted_at": datetime.now(timezone.utc).isoformat()}
    return record_transition(store, name, stamped)


def last_emitted(store: PipelineGraphStore, name: str) -> _Record | None:
    """The newest emitted snapshot for ``name`` — its highest-version record with ``emitted_at``.

    ``None`` means the pipeline has never been approved/emitted — the diff endpoint reports "no
    baseline yet" rather than fabricating an empty one (absence is a signal, not a crash).
    """
    emitted = [r for r in store.get_versions(name) if r.get("emitted_at")]
    return emitted[-1] if emitted else None
