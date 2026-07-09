"""Pluggable sink for in-app feedback telemetry (W12, ADR-0016) — OFF the decision gate.

Feedback is product telemetry, a **separate concern** from the decision projection (the
`Repository` port): its rows never mix with runs/cards/events. Three adapters, env-selected via
``PIPEGUARD_FEEDBACK_STORE`` (default ``jsonl``); the DB adapters mirror the persistence seam
and **degrade to the offline JSONL** if selection fails (missing extra / no DSN / unreachable
server), so a misconfigured DB never breaks the write path — it just falls back to the file.

  - :class:`JsonlFeedbackStore` — default, zero-dep append-only file (``PIPEGUARD_FEEDBACK_PATH``).
  - :class:`SqliteFeedbackStore` — a ``feedback`` table (stdlib; ``PIPEGUARD_FEEDBACK_DB``).
  - :class:`PostgresFeedbackStore` — a ``feedback`` table (``[postgres]`` extra; ``DATABASE_URL``).

Every adapter also exposes ``read_all`` so the advisory feedback agent can categorize the
corpus out-of-band — there is still no read-back HTTP endpoint (telemetry never re-enters a view).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol

_ENV_FEEDBACK_STORE = "PIPEGUARD_FEEDBACK_STORE"
_ENV_FEEDBACK_PATH = "PIPEGUARD_FEEDBACK_PATH"
_ENV_FEEDBACK_DB = "PIPEGUARD_FEEDBACK_DB"
_ENV_DATABASE_URL = "DATABASE_URL"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_FEEDBACK_PATH = _REPO_ROOT / "feedback.events.jsonl"
_DEFAULT_FEEDBACK_DB = _REPO_ROOT / "feedback.sqlite"

# Serialize file/DB appends within a worker so concurrent requests can't interleave a JSONL
# line or race a short-lived connection. Multi-worker needs a file lock / a pooled DB — a
# documented seam, not built (same honest limit as the JSONL note in ADR-0016).
_WRITE_LOCK = threading.Lock()
_log = logging.getLogger(__name__)

# The indexed columns lifted out of a record for querying; the full record is always kept as a
# JSON document alongside, so nothing is lost and read_all round-trips exactly.
_FEEDBACK_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS feedback (
    id             TEXT PRIMARY KEY,
    received_at    TEXT,
    target         TEXT,
    source         TEXT,
    run_id         TEXT,
    origin         TEXT,
    schema_version INTEGER,
    record         TEXT NOT NULL
);
"""
_FEEDBACK_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS feedback (
    id             TEXT PRIMARY KEY,
    received_at    TIMESTAMPTZ,
    target         TEXT,
    source         TEXT,
    run_id         TEXT,
    origin         TEXT,
    schema_version INTEGER,
    record         JSONB NOT NULL
);
"""


class FeedbackStore(Protocol):
    """Append-only telemetry sink. ``append`` persists one server-authored record dict;
    ``read_all`` returns every record (for out-of-band analysis / the feedback agent)."""

    def append(self, record: dict[str, Any]) -> None: ...
    def read_all(self) -> list[dict[str, Any]]: ...


def _indexed(record: dict[str, Any]) -> tuple[Any, ...]:
    """Pull the indexed columns out of a record (the full record rides along as JSON)."""
    ctx = record.get("context") or {}
    return (
        record.get("id"),
        record.get("received_at"),
        record.get("target"),
        record.get("source"),
        ctx.get("run_id"),
        record.get("origin"),
        record.get("schema_version"),
    )


# --- JSONL (default, offline) ---------------------------------------------------------------


def feedback_path() -> Path:
    """The JSONL sink path, resolved at call-time from the env (so tests monkeypatch cleanly)."""
    raw = os.environ.get(_ENV_FEEDBACK_PATH, "").strip()
    return Path(raw) if raw else _DEFAULT_FEEDBACK_PATH


class JsonlFeedbackStore:
    """Append-only JSONL file — the zero-dependency default. ``json.dumps`` escapes every
    value so a message with ``\\n`` or ``"`` can never forge a second line."""

    def append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        path = feedback_path()
        with _WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)

    def read_all(self) -> list[dict[str, Any]]:
        path = feedback_path()
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if line:
                    out.append(json.loads(line))
        return out


# --- SQLite (a real DB, still offline + zero-dep) -------------------------------------------


def feedback_db_path() -> str:
    """The SQLite feedback-DB path (``PIPEGUARD_FEEDBACK_DB`` or the repo-root default)."""
    return os.environ.get(_ENV_FEEDBACK_DB, "").strip() or str(_DEFAULT_FEEDBACK_DB)


class SqliteFeedbackStore:
    """A ``feedback`` table in SQLite (stdlib). A fresh connection per op keeps it thread-safe
    under FastAPI's sync threadpool without pinning a connection to one thread."""

    def __init__(self, path: str | None = None) -> None:
        self._path = path or feedback_db_path()
        # Fail fast at selection (so get_feedback_store can degrade) if the dir is unwritable.
        self._connect().close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.execute(_FEEDBACK_DDL_SQLITE)
        return conn

    def append(self, record: dict[str, Any]) -> None:
        with _WRITE_LOCK:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO feedback
                       (id, received_at, target, source, run_id, origin, schema_version, record)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (*_indexed(record), json.dumps(record, ensure_ascii=False)),
                )
                conn.commit()
            finally:
                conn.close()

    def read_all(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT record FROM feedback ORDER BY received_at, id").fetchall()
            return [json.loads(r[0]) for r in rows]
        finally:
            conn.close()


# --- Postgres (production; [postgres] extra, off by default) --------------------------------


class PostgresFeedbackStore:
    """A ``feedback`` table in Postgres. Lazy-imports psycopg (the ``[postgres]`` extra) and uses
    ``DATABASE_URL``; a fresh short-lived connection per op (a pool is the documented seam)."""

    def __init__(self, dsn: str | None = None) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise RuntimeError(
                "PostgresFeedbackStore needs the 'postgres' extra (psycopg)."
            ) from exc
        self._dsn = dsn or os.environ.get(_ENV_DATABASE_URL, "").strip()
        if not self._dsn:
            raise RuntimeError("PostgresFeedbackStore needs DATABASE_URL.")
        self._psycopg = psycopg
        with self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(_FEEDBACK_DDL_POSTGRES)  # fail fast at selection if unreachable

    def append(self, record: dict[str, Any]) -> None:
        from psycopg.types.json import Jsonb

        with _WRITE_LOCK, self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(
                """INSERT INTO feedback
                   (id, received_at, target, source, run_id, origin, schema_version, record)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING""",
                (*_indexed(record), Jsonb(record)),
            )

    def read_all(self) -> list[dict[str, Any]]:
        from psycopg.rows import dict_row

        with self._psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            rows = conn.execute("SELECT record FROM feedback ORDER BY received_at, id").fetchall()
            return [r["record"] for r in rows]


def get_feedback_store() -> FeedbackStore:
    """Select the feedback sink from the environment (default: the offline JSONL file).

    ``PIPEGUARD_FEEDBACK_STORE=sqlite|postgres`` swaps in a DB adapter; ANY failure constructing
    it (missing extra / DSN, unwritable path, unreachable server) degrades to the JSONL store —
    logged by exception *type* only, never ``str(exc)`` (which could carry a DSN password).
    """
    choice = os.environ.get(_ENV_FEEDBACK_STORE, "jsonl").strip().lower()
    if choice == "postgres":
        try:
            return PostgresFeedbackStore()
        except Exception as exc:  # degrade on ANY failure; never leak the DSN
            _log.warning(
                "PIPEGUARD_FEEDBACK_STORE=postgres unavailable (%s); using JSONL.",
                type(exc).__name__,
            )
    elif choice == "sqlite":
        try:
            return SqliteFeedbackStore()
        except Exception as exc:  # degrade on ANY failure
            _log.warning(
                "PIPEGUARD_FEEDBACK_STORE=sqlite unavailable (%s); using JSONL.", type(exc).__name__
            )
    return JsonlFeedbackStore()
