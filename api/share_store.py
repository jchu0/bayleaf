"""Pluggable sink for de-identified share/report egress events (ADR-0018 D3, ADR-0016) — off-gate.

A ``DATA_EXPORTED`` :class:`~pipeguard.provenance.ProvenanceEvent` records that a de-identified
share left the boundary, so a data-out is auditable in the SAME provenance vocabulary as the gate's
decisions. This is a SEPARATE sink from the gate's own :class:`~pipeguard.provenance.EventLedger`:
the gate ledger is a deterministic, cacheable re-derivation per run (``api.main._evaluate`` is
``@lru_cache``) and must stay byte-stable; a share is a live, actor-driven side effect that must
survive that cache and a process restart. It never reads, sets, or overrides a verdict/finding/gate
input — it only records that data left (ADR-0001 holds).

Three adapters, env-selected via ``PIPEGUARD_SHARE_STORE`` (default ``jsonl``), matching the other
off-gate sinks (feedback/pipeline/review/settings). The DB adapters mirror the persistence seam and
**degrade to the offline JSONL** if selection fails (missing extra / no DSN / unreachable server),
so a misconfigured DB never breaks the egress-audit path — it just falls back to the file.

  - :class:`JsonlShareStore` — default, zero-dep append-only file (``PIPEGUARD_SHARE_PATH``).
  - :class:`SqliteShareStore` — a ``share_events`` table (stdlib; ``PIPEGUARD_SHARE_DB``).
  - :class:`PostgresShareStore` — a ``share_events`` table (``[postgres]`` extra; ``DATABASE_URL``).

Query grain is ``for_run(run_id)`` (oldest-first) — exactly what ``get_run`` needs to merge the
share events into a run's trail.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol

from pipeguard.provenance import ProvenanceEvent

_ENV_SHARE_STORE = "PIPEGUARD_SHARE_STORE"
_ENV_SHARE_PATH = "PIPEGUARD_SHARE_PATH"
_ENV_SHARE_DB = "PIPEGUARD_SHARE_DB"
_ENV_DATABASE_URL = "DATABASE_URL"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SHARE_PATH = _REPO_ROOT / "share.events.jsonl"
_DEFAULT_SHARE_DB = _REPO_ROOT / "share.sqlite"

# Serialize appends within a worker so concurrent shares can't interleave a JSONL line or race a
# short-lived connection (same honest single-worker limit as api.feedback_store; a file lock / pool
# is the multi-worker seam noted in ADR-0016).
_WRITE_LOCK = threading.Lock()
_log = logging.getLogger(__name__)

# Indexed columns lifted out of an event for querying; the full event always rides along as a JSON
# document, so a read round-trips a ProvenanceEvent exactly (nothing is lost to the columns).
_SHARE_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS share_events (
    id         TEXT PRIMARY KEY,
    created_at TEXT,
    run_id     TEXT,
    event_type TEXT,
    actor      TEXT,
    record     TEXT NOT NULL
);
"""
_SHARE_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS share_events (
    id         TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ,
    run_id     TEXT,
    event_type TEXT,
    actor      TEXT,
    record     JSONB NOT NULL
);
"""


class ShareStore(Protocol):
    """Append-only egress-audit sink. ``append`` persists one ``DATA_EXPORTED`` event; ``for_run``
    returns every recorded share event for a run, oldest first (for the trail merge in get_run)."""

    def append(self, event: ProvenanceEvent) -> None: ...
    def for_run(self, run_id: str) -> list[ProvenanceEvent]: ...


def _sqlite_cols(event: ProvenanceEvent) -> tuple[Any, ...]:
    """The indexed columns for the SQLite/JSONL row (created_at as an ISO string)."""
    return (
        event.id,
        event.created_at.isoformat(),
        event.run_id,
        event.event_type.value,
        event.actor,
    )


# --- JSONL (default, offline) ---------------------------------------------------------------


def share_path() -> Path:
    """The JSONL sink path, resolved at call-time from the env (so tests monkeypatch cleanly)."""
    raw = os.environ.get(_ENV_SHARE_PATH, "").strip()
    return Path(raw) if raw else _DEFAULT_SHARE_PATH


class JsonlShareStore:
    """Append-only JSONL file — the zero-dependency default. Tolerant reads: a missing file → ``[]``
    and a partial/corrupt line is skipped, not raised (a broken append is a signal, not a crash)."""

    def append(self, event: ProvenanceEvent) -> None:
        line = event.model_dump_json() + "\n"
        path = share_path()
        with _WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)

    def for_run(self, run_id: str) -> list[ProvenanceEvent]:
        path = share_path()
        if not path.exists():
            return []
        out: list[ProvenanceEvent] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                event = ProvenanceEvent.model_validate_json(line)
            except ValueError:
                continue  # tolerate a partial/corrupt line
            if event.run_id == run_id:
                out.append(event)
        return out


# --- SQLite (a real DB, still offline + zero-dep) -------------------------------------------


def share_db_path() -> str:
    """The SQLite share-DB path (``PIPEGUARD_SHARE_DB`` or the repo-root default)."""
    return os.environ.get(_ENV_SHARE_DB, "").strip() or str(_DEFAULT_SHARE_DB)


class SqliteShareStore:
    """A ``share_events`` table in SQLite (stdlib). A fresh connection per op keeps it thread-safe
    under FastAPI's sync threadpool without pinning a connection to one thread."""

    def __init__(self, path: str | None = None) -> None:
        self._path = path or share_db_path()
        # Fail fast at selection (so get_share_store can degrade) if the dir is unwritable.
        self._connect().close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.execute(_SHARE_DDL_SQLITE)
        return conn

    def append(self, event: ProvenanceEvent) -> None:
        with _WRITE_LOCK:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO share_events
                       (id, created_at, run_id, event_type, actor, record)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (*_sqlite_cols(event), event.model_dump_json()),
                )
                conn.commit()
            finally:
                conn.close()

    def for_run(self, run_id: str) -> list[ProvenanceEvent]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT record FROM share_events WHERE run_id = ? ORDER BY created_at, id",
                (run_id,),
            ).fetchall()
            return [ProvenanceEvent.model_validate_json(r[0]) for r in rows]
        finally:
            conn.close()


# --- Postgres (production; [postgres] extra, off by default) --------------------------------


class PostgresShareStore:
    """A ``share_events`` table in Postgres. Lazy-imports psycopg (the ``[postgres]`` extra) and
    uses ``DATABASE_URL``; a fresh short-lived connection per op (a pool is the documented seam)."""

    def __init__(self, dsn: str | None = None) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise RuntimeError("PostgresShareStore needs the 'postgres' extra (psycopg).") from exc
        self._dsn = dsn or os.environ.get(_ENV_DATABASE_URL, "").strip()
        if not self._dsn:
            raise RuntimeError("PostgresShareStore needs DATABASE_URL.")
        self._psycopg = psycopg
        with self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(_SHARE_DDL_POSTGRES)  # fail fast at selection if unreachable

    def append(self, event: ProvenanceEvent) -> None:
        from psycopg.types.json import Jsonb

        with _WRITE_LOCK, self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(
                """INSERT INTO share_events (id, created_at, run_id, event_type, actor, record)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING""",
                (
                    event.id,
                    event.created_at,  # a real datetime → TIMESTAMPTZ (psycopg adapts it)
                    event.run_id,
                    event.event_type.value,
                    event.actor,
                    Jsonb(event.model_dump(mode="json")),
                ),
            )

    def for_run(self, run_id: str) -> list[ProvenanceEvent]:
        from psycopg.rows import dict_row

        with self._psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            rows = conn.execute(
                "SELECT record FROM share_events WHERE run_id = %s ORDER BY created_at, id",
                (run_id,),
            ).fetchall()
            return [ProvenanceEvent.model_validate(r["record"]) for r in rows]


def get_share_store() -> ShareStore:
    """Select the share-egress-audit sink from the environment (default: the offline JSONL file).

    ``PIPEGUARD_SHARE_STORE=sqlite|postgres`` swaps in a DB adapter; ANY failure constructing it
    (missing extra / DSN, unwritable path, unreachable server) degrades to the JSONL store — logged
    by exception *type* only, never ``str(exc)`` (which could carry a DSN password).
    """
    choice = os.environ.get(_ENV_SHARE_STORE, "jsonl").strip().lower()
    if choice == "postgres":
        try:
            return PostgresShareStore()
        except Exception as exc:  # degrade on ANY failure; never leak the DSN
            _log.warning(
                "PIPEGUARD_SHARE_STORE=postgres unavailable (%s); using JSONL.", type(exc).__name__
            )
    elif choice == "sqlite":
        try:
            return SqliteShareStore()
        except Exception as exc:  # degrade on ANY failure
            _log.warning(
                "PIPEGUARD_SHARE_STORE=sqlite unavailable (%s); using JSONL.", type(exc).__name__
            )
    return JsonlShareStore()
