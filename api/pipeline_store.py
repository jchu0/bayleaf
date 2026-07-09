"""Pluggable sink for saved Pipeline Builder graphs (ADR-0014/0016) — a PRODUCT store.

A saved builder graph is product state, a **separate concern** from the decision projection
(the ``Repository`` port): its rows never mix with runs/cards/events and never re-enter the
gate. This mirrors ``api/feedback_store.py`` exactly — three adapters, env-selected via
``PIPEGUARD_PIPELINE_STORE`` (default ``jsonl``); the DB adapters mirror the persistence seam
and **degrade to the offline JSONL** if selection fails (missing extra / no DSN / unreachable
server), so a misconfigured DB never breaks the save path — it just falls back to the file.

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
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol

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
# not built (same honest limit as the JSONL note in ADR-0016 / feedback_store.py).
_WRITE_LOCK = threading.Lock()
_log = logging.getLogger(__name__)

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


class JsonlPipelineGraphStore:
    """Append-only JSONL file — the zero-dependency default. ``json.dumps`` escapes every value
    so an arbitrary ``graph`` payload with ``\\n`` or ``"`` can never forge a second line."""

    def _read_all(self) -> _Records:
        path = pipeline_path()
        if not path.exists():
            return []
        out: _Records = []
        with path.open(encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def append(self, record: _Record) -> _Record:
        # Read-then-append UNDER the lock so the max-version scan and the write are one atomic
        # step within the worker — no two concurrent saves of a name can pick the same version.
        with _WRITE_LOCK:
            stored = {**record, "version": _next_version(self._read_all(), str(record["name"]))}
            line = json.dumps(stored, ensure_ascii=False) + "\n"
            path = pipeline_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        return stored

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


class SqlitePipelineGraphStore:
    """A ``pipeline_graphs`` table in SQLite (stdlib). A fresh connection per op keeps it
    thread-safe under FastAPI's sync threadpool without pinning a connection to one thread."""

    def __init__(self, path: str | None = None) -> None:
        self._path = path or pipeline_db_path()
        # Fail fast at selection (so get_pipeline_store can degrade) if the dir is unwritable.
        self._connect().close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.execute(_PIPELINE_DDL_SQLITE)
        return conn

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
    it (missing extra / DSN, unwritable path, unreachable server) degrades to the JSONL store —
    logged by exception *type* only, never ``str(exc)`` (which could carry a DSN password).
    """
    choice = os.environ.get(_ENV_PIPELINE_STORE, "jsonl").strip().lower()
    if choice == "postgres":
        try:
            return PostgresPipelineGraphStore()
        except Exception as exc:  # degrade on ANY failure; never leak the DSN
            _log.warning(
                "PIPEGUARD_PIPELINE_STORE=postgres unavailable (%s); using JSONL.",
                type(exc).__name__,
            )
    elif choice == "sqlite":
        try:
            return SqlitePipelineGraphStore()
        except Exception as exc:  # degrade on ANY failure
            _log.warning(
                "PIPEGUARD_PIPELINE_STORE=sqlite unavailable (%s); using JSONL.", type(exc).__name__
            )
    return JsonlPipelineGraphStore()
