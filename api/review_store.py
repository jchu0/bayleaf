"""Pluggable sink for review-queue tickets (HITL, ADR-0010) — a PRODUCT store, OFF the gate.

A review ticket is a human-in-the-loop worklist item: an operator opened it against a flagged
sample so a reviewer/approver can acknowledge → resolve/suppress → (re)open it. It is product
state, a **separate concern** from the decision projection (the ``Repository`` port): a ticket
NEVER re-enters the deterministic gate and can never set or override a verdict/finding/confidence
(ADR-0001). This mirrors ``api/pipeline_store.py`` over the shared :mod:`api.base_store` generic —
three adapters, env-selected via ``PIPEGUARD_REVIEW_STORE`` (default ``jsonl``); the DB adapters
**degrade to the offline JSONL** if selection fails (missing extra / no DSN / unreachable server),
so a misconfigured DB never breaks the write path — it just falls back to the file.

  - :class:`JsonlReviewStore` — default, zero-dep file (``PIPEGUARD_REVIEW_PATH``).
  - :class:`SqliteReviewStore` — a ``review_tickets`` table (stdlib; ``PIPEGUARD_REVIEW_DB``).
  - :class:`PostgresReviewStore` — a ``review_tickets`` table (the ``[postgres]`` extra).

Unlike the append-only feedback/pipeline sinks, a ticket is **mutable**: an action transitions its
status and appends to ``actions[]``. So the contract is create / get / list / update rather than a
pure append. The router (``routers/review_queue.py``) owns the RBAC + status-machine and hands the
store a fully-formed record; the store only persists it. Concurrency is the same honest
single-worker limit the other sinks document: a read-validate-write on one ticket is not guarded
across workers — a per-ticket lock / a DB transaction is the documented (not-built) seam.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from api.base_store import JsonlDocStore, SqliteStore, select_backend

# The store Protocol has a method named ``list`` (per its contract), which shadows the builtin
# ``list`` inside the class bodies — so a ``-> list[...]`` return annotation would resolve to the
# method, not the type. Module-level aliases (bound before any shadow) keep the annotations
# unambiguous (same guard the pipeline/feedback stores use).
_Record = dict[str, Any]
_Records = list[dict[str, Any]]

_ENV_REVIEW_STORE = "PIPEGUARD_REVIEW_STORE"
_ENV_REVIEW_PATH = "PIPEGUARD_REVIEW_PATH"
_ENV_REVIEW_DB = "PIPEGUARD_REVIEW_DB"
_ENV_DATABASE_URL = "DATABASE_URL"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_REVIEW_PATH = _REPO_ROOT / "review_tickets.jsonl"
_DEFAULT_REVIEW_DB = _REPO_ROOT / "review_tickets.sqlite"

# Serialize file/DB writes within a worker so two concurrent requests can't interleave a JSONL
# line or race a rewrite. Multi-worker (or two actions on the SAME ticket) needs a file lock /
# a per-row DB transaction — a documented seam, not built (same honest limit as ADR-0016). Shared
# by all three adapters of THIS store.
_WRITE_LOCK = threading.Lock()

# The indexed columns lifted out of a record for filtering; the full ticket (incl. actions[]) is
# always kept as a JSON document alongside, so nothing is lost and a ticket round-trips exactly.
_REVIEW_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS review_tickets (
    id         TEXT PRIMARY KEY,
    created_at TEXT,
    run_id     TEXT,
    sample_id  TEXT,
    gate       TEXT,
    verdict    TEXT,
    rule_id    TEXT,
    status     TEXT,
    priority   TEXT,
    opened_by  TEXT,
    record     TEXT NOT NULL
);
"""
_REVIEW_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS review_tickets (
    id         TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ,
    run_id     TEXT,
    sample_id  TEXT,
    gate       TEXT,
    verdict    TEXT,
    rule_id    TEXT,
    status     TEXT,
    priority   TEXT,
    opened_by  TEXT,
    record     JSONB NOT NULL
);
"""


class ReviewStore(Protocol):
    """Mutable sink for review-queue tickets.

    ``create`` persists a new ticket record and returns it; ``get`` returns one ticket by id (or
    ``None``); ``list`` returns tickets, optionally filtered by status/run_id/rule_id, ordered by
    ``created_at``; ``update`` replaces an existing ticket by id (used to record an action +
    status transition) and returns it, raising ``KeyError`` if the id is unknown.
    """

    def create(self, record: _Record) -> _Record: ...
    def get(self, ticket_id: str) -> _Record | None: ...
    def list(
        self,
        *,
        status: str | None = None,
        run_id: str | None = None,
        rule_id: str | None = None,
    ) -> _Records: ...
    def update(self, record: _Record) -> _Record: ...


def _indexed(record: dict[str, Any]) -> tuple[Any, ...]:
    """Pull the indexed columns out of a ticket (the full ticket rides along as JSON)."""
    return (
        record.get("id"),
        record.get("created_at"),
        record.get("run_id"),
        record.get("sample_id"),
        record.get("gate"),
        record.get("verdict"),
        record.get("rule_id"),
        record.get("status"),
        record.get("priority"),
        record.get("opened_by"),
    )


def _matches(
    record: dict[str, Any], status: str | None, run_id: str | None, rule_id: str | None
) -> bool:
    """In-Python filter predicate (the JSONL adapter's equivalent of a SQL ``WHERE``).

    Each ``None`` filter is a no-op (matches everything), so the three filters AND together —
    the same conjunctive semantics the SQL adapters build with their dynamic ``WHERE`` clauses.
    """
    return (
        (status is None or record.get("status") == status)
        and (run_id is None or record.get("run_id") == run_id)
        and (rule_id is None or record.get("rule_id") == rule_id)
    )


# --- JSONL (default, offline) ---------------------------------------------------------------


def review_path() -> Path:
    """The JSONL sink path, resolved at call-time from the env (so tests monkeypatch cleanly)."""
    raw = os.environ.get(_ENV_REVIEW_PATH, "").strip()
    return Path(raw) if raw else _DEFAULT_REVIEW_PATH


class JsonlReviewStore(JsonlDocStore):
    """One ticket per line in a JSONL file — the zero-dependency default.

    The shared base's ``json.dumps`` escapes every value so an arbitrary ``title`` with ``\\n`` or
    ``"`` can never forge a second record. An ``update`` rewrites the whole file atomically (the
    base's temp-file ``os.replace`` swap), so a crash mid-write leaves the old file intact.
    """

    _lock = _WRITE_LOCK
    _tolerant = False

    def _resolve_path(self) -> Path:
        return review_path()

    def create(self, record: _Record) -> _Record:
        return self._append(record)

    def get(self, ticket_id: str) -> _Record | None:
        return next((r for r in self._read_all() if r.get("id") == ticket_id), None)

    def list(
        self,
        *,
        status: str | None = None,
        run_id: str | None = None,
        rule_id: str | None = None,
    ) -> _Records:
        rows = [r for r in self._read_all() if _matches(r, status, run_id, rule_id)]
        return sorted(rows, key=lambda r: (str(r.get("created_at") or ""), str(r.get("id") or "")))

    def update(self, record: _Record) -> _Record:
        ticket_id = str(record["id"])

        def mutate(rows: _Records) -> _Records:
            for i, r in enumerate(rows):
                if r.get("id") == ticket_id:
                    rows[i] = record
                    return rows
            # Update of a ticket that isn't there — the router 404s before this, so reaching here
            # is a programming error, surfaced loudly rather than silently appending.
            raise KeyError(ticket_id)

        self._rewrite(mutate)
        return record


# --- SQLite (a real DB, still offline + zero-dep) -------------------------------------------


def review_db_path() -> str:
    """The SQLite review-DB path (``PIPEGUARD_REVIEW_DB`` or the repo-root default)."""
    return os.environ.get(_ENV_REVIEW_DB, "").strip() or str(_DEFAULT_REVIEW_DB)


class SqliteReviewStore(SqliteStore):
    """A ``review_tickets`` table in SQLite (stdlib). A fresh connection per op keeps it
    thread-safe under FastAPI's sync threadpool without pinning a connection to one thread."""

    _ddl = _REVIEW_DDL_SQLITE

    def __init__(self, path: str | None = None) -> None:
        super().__init__(path or review_db_path())

    def create(self, record: _Record) -> _Record:
        with _WRITE_LOCK:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO review_tickets
                       (id, created_at, run_id, sample_id, gate, verdict, rule_id,
                        status, priority, opened_by, record)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (*_indexed(record), json.dumps(record, ensure_ascii=False)),
                )
                conn.commit()
            finally:
                conn.close()
        return record

    def get(self, ticket_id: str) -> _Record | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT record FROM review_tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
            return json.loads(row[0]) if row else None
        finally:
            conn.close()

    def list(
        self,
        *,
        status: str | None = None,
        run_id: str | None = None,
        rule_id: str | None = None,
    ) -> _Records:
        # Column names are literals we control; values are always bound parameters — no SQL is
        # built from caller input, so the dynamic WHERE can't be an injection vector.
        clauses: list[str] = []
        params: list[Any] = []
        for col, val in (("status", status), ("run_id", run_id), ("rule_id", rule_id)):
            if val is not None:
                clauses.append(f"{col} = ?")
                params.append(val)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT record FROM review_tickets{where} ORDER BY created_at, id", params
            ).fetchall()
            return [json.loads(r[0]) for r in rows]
        finally:
            conn.close()

    def update(self, record: _Record) -> _Record:
        ticket_id = str(record["id"])
        with _WRITE_LOCK:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """UPDATE review_tickets
                       SET created_at=?, run_id=?, sample_id=?, gate=?, verdict=?, rule_id=?,
                           status=?, priority=?, opened_by=?, record=?
                       WHERE id=?""",
                    (*_indexed(record)[1:], json.dumps(record, ensure_ascii=False), ticket_id),
                )
                if cur.rowcount == 0:
                    raise KeyError(ticket_id)
                conn.commit()
            finally:
                conn.close()
        return record


# --- Postgres (production; [postgres] extra, off by default) --------------------------------


class PostgresReviewStore:
    """A ``review_tickets`` table in Postgres. Lazy-imports psycopg (the ``[postgres]`` extra) and
    uses ``DATABASE_URL``; a fresh short-lived connection per op (a pool is the documented seam)."""

    def __init__(self, dsn: str | None = None) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise RuntimeError("PostgresReviewStore needs the 'postgres' extra (psycopg).") from exc
        self._dsn = dsn or os.environ.get(_ENV_DATABASE_URL, "").strip()
        if not self._dsn:
            raise RuntimeError("PostgresReviewStore needs DATABASE_URL.")
        self._psycopg = psycopg
        with self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(_REVIEW_DDL_POSTGRES)  # fail fast at selection if unreachable

    def create(self, record: _Record) -> _Record:
        from psycopg.types.json import Jsonb

        with _WRITE_LOCK, self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(
                """INSERT INTO review_tickets
                   (id, created_at, run_id, sample_id, gate, verdict, rule_id,
                    status, priority, opened_by, record)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING""",
                (*_indexed(record), Jsonb(record)),
            )
        return record

    def get(self, ticket_id: str) -> _Record | None:
        from psycopg.rows import dict_row

        with self._psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                "SELECT record FROM review_tickets WHERE id = %s", (ticket_id,)
            ).fetchone()
            return row["record"] if row else None

    def list(
        self,
        *,
        status: str | None = None,
        run_id: str | None = None,
        rule_id: str | None = None,
    ) -> _Records:
        from psycopg.rows import dict_row

        clauses: list[str] = []
        params: list[Any] = []
        for col, val in (("status", status), ("run_id", run_id), ("rule_id", rule_id)):
            if val is not None:
                clauses.append(f"{col} = %s")
                params.append(val)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            rows = conn.execute(
                f"SELECT record FROM review_tickets{where} ORDER BY created_at, id", params
            ).fetchall()
            return [r["record"] for r in rows]

    def update(self, record: _Record) -> _Record:
        from psycopg.types.json import Jsonb

        ticket_id = str(record["id"])
        with _WRITE_LOCK, self._psycopg.connect(self._dsn, autocommit=True) as conn:
            cur = conn.execute(
                "UPDATE review_tickets SET record = %s, status = %s WHERE id = %s",
                (Jsonb(record), record.get("status"), ticket_id),
            )
            if cur.rowcount == 0:
                raise KeyError(ticket_id)
        return record


def get_review_store() -> ReviewStore:
    """Select the review-ticket sink from the environment (default: the offline JSONL file).

    ``PIPEGUARD_REVIEW_STORE=sqlite|postgres`` swaps in a DB adapter; ANY failure constructing it
    (missing extra / DSN, unwritable path, unreachable server) degrades to the JSONL store — see
    :func:`api.base_store.select_backend` (the shared degrade-to-JSONL ladder).
    """
    jsonl: Callable[[], ReviewStore] = JsonlReviewStore
    sqlite: Callable[[], ReviewStore] = SqliteReviewStore
    postgres: Callable[[], ReviewStore] = PostgresReviewStore
    return select_backend(_ENV_REVIEW_STORE, jsonl=jsonl, sqlite=sqlite, postgres=postgres)
