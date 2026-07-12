"""Pluggable sink for accepted tool-card **library entries** (node-author W2, ADR-0016) — off-gate.

A *library entry* is an advisory :class:`~pipeguard.node_author.NodeProposal` a human has
**accepted** into the tool-card library as a versioned **draft**: its typed ports, pinned versions,
and suggested locators — METADATA a human still turns into a runnable ``ProcessSpec`` (compose ≠
execute, ADR-0003; see ``docs/design/agent-authoring-contract.md``). It is product state, wholly OFF
the deterministic decision gate (ADR-0001): a library entry NEVER re-enters the gate and can never
set or override a verdict/finding/confidence — the accepted proposal carries no such field.

This mirrors the other off-gate sinks (``api/review_store.py`` / ``api/share_store.py`` /
``api/job_store.py``) — a pluggable store, env-selected via ``PIPEGUARD_LIBRARY_STORE`` (default
``jsonl``); a DB adapter **degrades to the offline JSONL** if selection fails (unwritable path), so
a misconfigured DB never breaks the accept path — it just falls back to the file.

  - :class:`JsonlLibraryStore` — default, zero-dep append file (``PIPEGUARD_LIBRARY_PATH``).
  - :class:`SqliteLibraryStore` — a ``library_entries`` table (stdlib; ``PIPEGUARD_LIBRARY_DB``).

No Postgres adapter here (like ``job_store``, unlike the share/review sinks): the library is a
small, node-local corpus of accepted drafts, not high-volume shared product state, so the two local
backends suffice; a Postgres adapter is the same documented, not-yet-built seam (ADR-0016).

An accept **appends** a new entry (each accept mints a fresh, immutable draft record), so the
contract is ``add`` / ``get`` / ``list`` — a draft → approved transition that would ``update`` an
entry in place is the labelled deferred slice (agent-authoring-contract.md). Concurrency is the same
honest single-worker limit the other sinks document: a per-row lock / DB transaction is the seam.
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
# ``list`` inside the class bodies — so a ``-> list[...]`` return annotation would resolve to the
# method, not the type. Module-level aliases (bound before any shadow) keep the annotations
# unambiguous (the same guard the review/job stores use).
_Record = dict[str, Any]
_Records = list[dict[str, Any]]

_ENV_LIBRARY_STORE = "PIPEGUARD_LIBRARY_STORE"
_ENV_LIBRARY_PATH = "PIPEGUARD_LIBRARY_PATH"
_ENV_LIBRARY_DB = "PIPEGUARD_LIBRARY_DB"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LIBRARY_PATH = _REPO_ROOT / "library_entries.jsonl"
_DEFAULT_LIBRARY_DB = _REPO_ROOT / "library_entries.sqlite"

# Serialize file/DB writes within a worker so two concurrent accepts can't interleave a JSONL line
# or race a rewrite. Multi-worker (or two writes to the SAME entry) needs a file lock / per-row DB
# transaction — a documented seam, not built (the same honest limit as ADR-0016 / the other sinks).
_WRITE_LOCK = threading.Lock()
_log = logging.getLogger(__name__)

# The indexed columns lifted out of a record for filtering; the full entry always rides along as a
# JSON document, so nothing is lost and an entry round-trips exactly.
_LIBRARY_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS library_entries (
    id           TEXT PRIMARY KEY,
    created_at   TEXT,
    tool         TEXT,
    version      TEXT,
    status       TEXT,
    submitted_by TEXT,
    record       TEXT NOT NULL
);
"""


class LibraryStore(Protocol):
    """Append-only sink for accepted tool-card library entries.

    ``add`` persists a new entry record and returns it; ``get`` returns one entry by id (or
    ``None``); ``list`` returns entries, optionally filtered by ``tool`` / ``status``, ordered by
    ``created_at`` (then id) — oldest first, stable.
    """

    def add(self, record: _Record) -> _Record: ...
    def get(self, entry_id: str) -> _Record | None: ...
    def list(self, *, tool: str | None = None, status: str | None = None) -> _Records: ...


def _indexed(record: dict[str, Any]) -> tuple[Any, ...]:
    """Pull the indexed columns out of an entry (the full entry rides along as JSON)."""
    return (
        record.get("id"),
        record.get("created_at"),
        record.get("tool"),
        record.get("version"),
        record.get("status"),
        record.get("submitted_by"),
    )


def _matches(record: dict[str, Any], tool: str | None, status: str | None) -> bool:
    """In-Python filter predicate (the JSONL adapter's equivalent of a SQL ``WHERE``).

    Each ``None`` filter is a no-op (matches everything), so the two filters AND together — the
    same conjunctive semantics the SQL adapter builds with its dynamic ``WHERE`` clause.
    """
    return (tool is None or record.get("tool") == tool) and (
        status is None or record.get("status") == status
    )


# --- JSONL (default, offline) ---------------------------------------------------------------


def library_path() -> Path:
    """The JSONL sink path, resolved at call-time from the env (so tests monkeypatch cleanly)."""
    raw = os.environ.get(_ENV_LIBRARY_PATH, "").strip()
    return Path(raw) if raw else _DEFAULT_LIBRARY_PATH


class JsonlLibraryStore:
    """One accepted entry per line in a JSONL file — the zero-dependency default.

    ``json.dumps`` escapes every value so an arbitrary ``summary``/``rationale`` with ``\\n`` or
    ``"`` can never forge a second record. Reads are tolerant: a missing file → ``[]`` and a
    partial/corrupt line is skipped, not raised (a crashed append is a signal, not a crash).
    """

    def _read_all(self) -> _Records:
        path = library_path()
        if not path.exists():
            return []
        out: _Records = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # tolerate a partial/corrupt line
        return out

    def add(self, record: _Record) -> _Record:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        path = library_path()
        with _WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        return record

    def get(self, entry_id: str) -> _Record | None:
        return next((r for r in self._read_all() if r.get("id") == entry_id), None)

    def list(self, *, tool: str | None = None, status: str | None = None) -> _Records:
        rows = [r for r in self._read_all() if _matches(r, tool, status)]
        return sorted(rows, key=lambda r: (str(r.get("created_at") or ""), str(r.get("id") or "")))


# --- SQLite (a real DB, still offline + zero-dep) -------------------------------------------


def library_db_path() -> str:
    """The SQLite library-DB path (``PIPEGUARD_LIBRARY_DB`` or the repo-root default)."""
    return os.environ.get(_ENV_LIBRARY_DB, "").strip() or str(_DEFAULT_LIBRARY_DB)


class SqliteLibraryStore:
    """A ``library_entries`` table in SQLite (stdlib). A fresh connection per op keeps it
    thread-safe under FastAPI's sync threadpool without pinning a connection to one thread."""

    def __init__(self, path: str | None = None) -> None:
        self._path = path or library_db_path()
        # Fail fast at selection (so get_library_store can degrade) if the dir is unwritable.
        self._connect().close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.execute(_LIBRARY_DDL_SQLITE)
        return conn

    def add(self, record: _Record) -> _Record:
        with _WRITE_LOCK:
            conn = self._connect()
            try:
                # INSERT OR REPLACE keys on the entry id, so re-adding the same id is idempotent
                # (one row, not two) — the accept path mints a fresh id per accept, so this only
                # matters for an explicit re-add of an already-stored record.
                conn.execute(
                    """INSERT OR REPLACE INTO library_entries
                       (id, created_at, tool, version, status, submitted_by, record)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (*_indexed(record), json.dumps(record, ensure_ascii=False)),
                )
                conn.commit()
            finally:
                conn.close()
        return record

    def get(self, entry_id: str) -> _Record | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT record FROM library_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            return json.loads(row[0]) if row else None
        finally:
            conn.close()

    def list(self, *, tool: str | None = None, status: str | None = None) -> _Records:
        # Column names are literals we control; values are always bound parameters — no SQL is
        # built from caller input, so the dynamic WHERE can't be an injection vector.
        clauses: list[str] = []
        params: list[Any] = []
        for col, val in (("tool", tool), ("status", status)):
            if val is not None:
                clauses.append(f"{col} = ?")
                params.append(val)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT record FROM library_entries{where} ORDER BY created_at, id", params
            ).fetchall()
            return [json.loads(r[0]) for r in rows]
        finally:
            conn.close()


def get_library_store() -> LibraryStore:
    """Select the library sink from the environment (default: the offline JSONL file).

    ``PIPEGUARD_LIBRARY_STORE=sqlite`` swaps in the SQLite adapter; ANY failure constructing it (an
    unwritable path) degrades to the JSONL store — logged by exception *type* only. Any other value
    (incl. the default) is JSONL. There is no Postgres adapter (see the module docstring).
    """
    choice = os.environ.get(_ENV_LIBRARY_STORE, "jsonl").strip().lower()
    if choice == "sqlite":
        try:
            return SqliteLibraryStore()
        except Exception as exc:  # degrade on ANY failure; never break the accept path
            _log.warning(
                "PIPEGUARD_LIBRARY_STORE=sqlite unavailable (%s); using JSONL.", type(exc).__name__
            )
    return JsonlLibraryStore()
