"""Pluggable sink for System-agents chat sessions — a PRODUCT store, OFF the gate.

A chat session is a run-independent conversation between an operator and a system agent
(pipeline-repair / archivist): a mutable record carrying its ordered ``messages[]`` and a
``status`` the user drives (``active`` → ``archived`` → ``deleted``). It is product state, a
**separate concern** from the decision projection (the ``Repository`` port): a chat NEVER re-enters
the deterministic gate and can never set or override a verdict/finding/confidence (ADR-0001).

**Retain-for-ML (design/system-agents-chat.md, structure-for-ML principle):** the user-facing
archive/delete are **view-scoped soft-deletes** — they flip ``status`` and the record STAYS in the
store for downstream ML. There is no hard delete on this store.

This mirrors ``api/review_store.py`` over the shared :mod:`api.base_store` generic — three adapters,
env-selected via ``BAYLEAF_CHAT_STORE`` (default ``jsonl``); the DB adapters **degrade to the
offline JSONL** if selection fails (missing extra / no DSN / unreachable server), so a misconfigured
DB never breaks the write path.

  - :class:`JsonlChatStore` — default, zero-dep file (``BAYLEAF_CHAT_PATH``).
  - :class:`SqliteChatStore` — a ``chat_sessions`` table (stdlib; ``BAYLEAF_CHAT_DB``).
  - :class:`PostgresChatStore` — a ``chat_sessions`` table (the ``[postgres]`` extra).

Like the review sink, a session is **mutable**: appending a message or changing status is an
``update`` of the whole record. The router owns the RBAC + the append/status transitions and hands
the store a fully-formed record; the store only persists it. Concurrency is the same honest
single-worker limit the other sinks document (a per-session lock / DB transaction is the
documented, not-built seam).
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from api.base_store import JsonlDocStore, SqliteStore, select_backend

# ``list`` is a store method; module-level aliases (bound before the shadow) keep ``-> list[...]``
# annotations resolving to the type, not the method (same guard as review/pipeline stores).
_Record = dict[str, Any]
_Records = list[dict[str, Any]]

_ENV_CHAT_STORE = "BAYLEAF_CHAT_STORE"
_ENV_CHAT_PATH = "BAYLEAF_CHAT_PATH"
_ENV_CHAT_DB = "BAYLEAF_CHAT_DB"
_ENV_DATABASE_URL = "DATABASE_URL"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CHAT_PATH = _REPO_ROOT / "chat_sessions.jsonl"
_DEFAULT_CHAT_DB = _REPO_ROOT / "chat_sessions.sqlite"

# Serialize file/DB writes within a worker (same honest single-worker limit as the other sinks).
_WRITE_LOCK = threading.Lock()

# Indexed columns lifted out for filtering; the full session (incl. messages[]) always rides along
# as a JSON document, so a session round-trips exactly.
_CHAT_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT,
    updated_at TEXT,
    actor_id   TEXT,
    agent_id   TEXT,
    status     TEXT,
    record     TEXT NOT NULL
);
"""
_CHAT_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    actor_id   TEXT,
    agent_id   TEXT,
    status     TEXT,
    record     JSONB NOT NULL
);
"""


class ChatStore(Protocol):
    """Mutable sink for chat sessions.

    ``create`` persists a new session and returns it; ``get`` returns one by id (or ``None``);
    ``list`` returns sessions filtered by actor/agent/status, ordered by ``updated_at`` (newest
    last, stable by id); ``update`` replaces an existing session by id (append a message / flip
    status) and returns it, raising ``KeyError`` if the id is unknown.
    """

    def create(self, record: _Record) -> _Record: ...
    def get(self, session_id: str) -> _Record | None: ...
    def list(
        self,
        *,
        actor_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> _Records: ...
    def update(self, record: _Record) -> _Record: ...


def _indexed(record: dict[str, Any]) -> tuple[Any, ...]:
    """Pull the indexed columns out of a session (the full session rides along as JSON)."""
    return (
        record.get("session_id"),
        record.get("created_at"),
        record.get("updated_at"),
        record.get("actor_id"),
        record.get("agent_id"),
        record.get("status"),
    )


def _matches(
    record: dict[str, Any], actor_id: str | None, agent_id: str | None, status: str | None
) -> bool:
    """In-Python filter predicate (the JSONL adapter's ``WHERE``). Each ``None`` is a no-op, so the
    filters AND together — matching the SQL adapters' conjunctive dynamic ``WHERE``."""
    return (
        (actor_id is None or record.get("actor_id") == actor_id)
        and (agent_id is None or record.get("agent_id") == agent_id)
        and (status is None or record.get("status") == status)
    )


def _sort_key(r: dict[str, Any]) -> tuple[str, str]:
    return (str(r.get("updated_at") or ""), str(r.get("session_id") or ""))


# --- JSONL (default, offline) ---------------------------------------------------------------


def chat_path() -> Path:
    """The JSONL sink path, resolved at call-time from the env (so tests monkeypatch cleanly)."""
    raw = os.environ.get(_ENV_CHAT_PATH, "").strip()
    return Path(raw) if raw else _DEFAULT_CHAT_PATH


class JsonlChatStore(JsonlDocStore):
    """One session per line in a JSONL file — the zero-dependency default. The shared base's
    ``json.dumps`` escapes every value, so message text with ``\\n``/``"`` can't forge a second
    record; an ``update`` rewrites the whole file atomically (temp-file ``os.replace`` swap)."""

    _lock = _WRITE_LOCK
    _tolerant = False

    def _resolve_path(self) -> Path:
        return chat_path()

    def create(self, record: _Record) -> _Record:
        return self._append(record)

    def get(self, session_id: str) -> _Record | None:
        return next((r for r in self._read_all() if r.get("session_id") == session_id), None)

    def list(
        self,
        *,
        actor_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> _Records:
        rows = [r for r in self._read_all() if _matches(r, actor_id, agent_id, status)]
        return sorted(rows, key=_sort_key)

    def update(self, record: _Record) -> _Record:
        session_id = str(record["session_id"])

        def mutate(rows: _Records) -> _Records:
            for i, r in enumerate(rows):
                if r.get("session_id") == session_id:
                    rows[i] = record
                    return rows
            # The router 404s before this, so reaching here is a programming error — surfaced
            # loudly rather than silently appending a duplicate.
            raise KeyError(session_id)

        self._rewrite(mutate)
        return record


# --- SQLite (a real DB, still offline + zero-dep) -------------------------------------------


def chat_db_path() -> str:
    """The SQLite chat-DB path (``BAYLEAF_CHAT_DB`` or the repo-root default)."""
    return os.environ.get(_ENV_CHAT_DB, "").strip() or str(_DEFAULT_CHAT_DB)


class SqliteChatStore(SqliteStore):
    """A ``chat_sessions`` table in SQLite (stdlib). A fresh connection per op keeps it thread-safe
    under FastAPI's sync threadpool without pinning a connection to one thread."""

    _ddl = _CHAT_DDL_SQLITE

    def __init__(self, path: str | None = None) -> None:
        super().__init__(path or chat_db_path())

    def create(self, record: _Record) -> _Record:
        with _WRITE_LOCK:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO chat_sessions
                       (session_id, created_at, updated_at, actor_id, agent_id, status, record)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (*_indexed(record), json.dumps(record, ensure_ascii=False)),
                )
                conn.commit()
            finally:
                conn.close()
        return record

    def get(self, session_id: str) -> _Record | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT record FROM chat_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            return json.loads(row[0]) if row else None
        finally:
            conn.close()

    def list(
        self,
        *,
        actor_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> _Records:
        # Column names are literals we control; values are always bound parameters — no SQL is
        # built from caller input, so the dynamic WHERE can't be an injection vector.
        clauses: list[str] = []
        params: list[Any] = []
        for col, val in (("actor_id", actor_id), ("agent_id", agent_id), ("status", status)):
            if val is not None:
                clauses.append(f"{col} = ?")
                params.append(val)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT record FROM chat_sessions{where} ORDER BY updated_at, session_id", params
            ).fetchall()
            return [json.loads(r[0]) for r in rows]
        finally:
            conn.close()

    def update(self, record: _Record) -> _Record:
        session_id = str(record["session_id"])
        with _WRITE_LOCK:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """UPDATE chat_sessions
                       SET created_at=?, updated_at=?, actor_id=?, agent_id=?, status=?, record=?
                       WHERE session_id=?""",
                    (*_indexed(record)[1:], json.dumps(record, ensure_ascii=False), session_id),
                )
                if cur.rowcount == 0:
                    raise KeyError(session_id)
                conn.commit()
            finally:
                conn.close()
        return record


# --- Postgres (production; [postgres] extra, off by default) --------------------------------


class PostgresChatStore:
    """A ``chat_sessions`` table in Postgres. Lazy-imports psycopg (the ``[postgres]`` extra) and
    uses ``DATABASE_URL``; a fresh short-lived connection per op (a pool is the documented seam)."""

    def __init__(self, dsn: str | None = None) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise RuntimeError("PostgresChatStore needs the 'postgres' extra (psycopg).") from exc
        self._dsn = dsn or os.environ.get(_ENV_DATABASE_URL, "").strip()
        if not self._dsn:
            raise RuntimeError("PostgresChatStore needs DATABASE_URL.")
        self._psycopg = psycopg
        with self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(_CHAT_DDL_POSTGRES)  # fail fast at selection if unreachable

    def create(self, record: _Record) -> _Record:
        from psycopg.types.json import Jsonb

        with _WRITE_LOCK, self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(
                """INSERT INTO chat_sessions
                   (session_id, created_at, updated_at, actor_id, agent_id, status, record)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (session_id) DO NOTHING""",
                (*_indexed(record), Jsonb(record)),
            )
        return record

    def get(self, session_id: str) -> _Record | None:
        from psycopg.rows import dict_row

        with self._psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                "SELECT record FROM chat_sessions WHERE session_id = %s", (session_id,)
            ).fetchone()
            return row["record"] if row else None

    def list(
        self,
        *,
        actor_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> _Records:
        from psycopg.rows import dict_row

        clauses: list[str] = []
        params: list[Any] = []
        for col, val in (("actor_id", actor_id), ("agent_id", agent_id), ("status", status)):
            if val is not None:
                clauses.append(f"{col} = %s")
                params.append(val)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            rows = conn.execute(
                f"SELECT record FROM chat_sessions{where} ORDER BY updated_at, session_id", params
            ).fetchall()
            return [r["record"] for r in rows]

    def update(self, record: _Record) -> _Record:
        from psycopg.types.json import Jsonb

        session_id = str(record["session_id"])
        with _WRITE_LOCK, self._psycopg.connect(self._dsn, autocommit=True) as conn:
            cur = conn.execute(
                "UPDATE chat_sessions SET record = %s, updated_at = %s, status = %s "
                "WHERE session_id = %s",
                (Jsonb(record), record.get("updated_at"), record.get("status"), session_id),
            )
            if cur.rowcount == 0:
                raise KeyError(session_id)
        return record


def get_chat_store() -> ChatStore:
    """Select the chat-session sink from the environment (default: the offline JSONL file).

    ``BAYLEAF_CHAT_STORE=sqlite|postgres`` swaps in a DB adapter; ANY failure constructing it
    (missing extra / DSN, unwritable path, unreachable server) degrades to the JSONL store — see
    :func:`api.base_store.select_backend` (the shared degrade-to-JSONL ladder).
    """
    jsonl: Callable[[], ChatStore] = JsonlChatStore
    sqlite: Callable[[], ChatStore] = SqliteChatStore
    postgres: Callable[[], ChatStore] = PostgresChatStore
    return select_backend(_ENV_CHAT_STORE, jsonl=jsonl, sqlite=sqlite, postgres=postgres)
