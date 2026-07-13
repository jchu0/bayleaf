"""Server-side agent-binding persistence per run — the run→executed-graph linkage (ADR-0024).

ADR-0022 shipped the ``AgentBinding {agent, node, grants}`` as a CLIENT-SIDE hint in the Builder
graph envelope (``graph.agent_bindings``); the server neither persisted nor enforced it. ADR-0024
makes scope-by-wiring REAL: an agent may read a node's observations ONLY if it is wired to that node
in the graph the run executed. This store is the missing linkage — when a run launches from an
approved graph, its bindings are SNAPSHOTTED here keyed by ``run_id`` (write-once; a run's executed
graph is fixed), so the read path can later intersect a request against real wiring.

Off the gate (ADR-0001): a binding governs READING a node's published files, never a verdict. This
mirrors the other off-gate sinks over :mod:`api.base_store` — three env-selected adapters
(``BAYLEAF_AGENT_BINDING_STORE`` = jsonl default / sqlite / postgres), degrade-to-JSONL on any DB
failure. Records are structured for ML (run id + captured_at + the binding list).
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from api.base_store import JsonlDocStore, SqliteStore, select_backend

_Record = dict[str, Any]

_ENV_STORE = "BAYLEAF_AGENT_BINDING_STORE"
_ENV_PATH = "BAYLEAF_AGENT_BINDING_PATH"
_ENV_DB = "BAYLEAF_AGENT_BINDING_DB"
_ENV_DATABASE_URL = "DATABASE_URL"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PATH = _REPO_ROOT / "agent_bindings.jsonl"
_DEFAULT_DB = _REPO_ROOT / "agent_bindings.sqlite"

_WRITE_LOCK = threading.Lock()

_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS agent_bindings (
    run_id      TEXT PRIMARY KEY,
    captured_at TEXT,
    record      TEXT NOT NULL
);
"""
_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS agent_bindings (
    run_id      TEXT PRIMARY KEY,
    captured_at TIMESTAMPTZ,
    record      JSONB NOT NULL
);
"""


def normalize_bindings(raw: Any) -> list[_Record]:
    """Coerce a graph's ``agent_bindings`` (arbitrary client JSON) into clean {agent,node,grants}
    records — tolerant at the boundary (a missing field is a signal, not a crash, per CLAUDE.md).

    Drops any entry without both an ``agent`` and a ``node``; keeps only the known grants
    (``outputs``/``logs``); de-dupes grants preserving order. Never raises on malformed input.
    """
    out: list[_Record] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent") or "").strip()
        node = str(item.get("node") or "").strip()
        if not agent or not node:
            continue
        grants_in = item.get("grants") or []
        grants: list[str] = []
        if isinstance(grants_in, list):
            for g in grants_in:
                gs = str(g).strip().lower()
                if gs in ("outputs", "logs") and gs not in grants:
                    grants.append(gs)
        out.append({"agent": agent, "node": node, "grants": grants or ["outputs"]})
    return out


def granted_grants(bindings: list[_Record], agent: str, node: str) -> list[str] | None:
    """The grants an ``agent`` holds on a ``node`` per these bindings, or ``None`` if NOT wired.

    ``None`` (not bound) is the enforcement signal — distinct from ``[]`` (bound but no grants). The
    read path denies a not-bound (agent, node); a bound one is capped to exactly these grants.
    """
    for b in bindings:
        if b.get("agent") == agent and b.get("node") == node:
            grants = b.get("grants") or []
            return [str(g) for g in grants]
    return None


class AgentBindingStore(Protocol):
    """Write-once-per-run sink for a run's executed-graph agent bindings."""

    def record(self, run_id: str, bindings: list[_Record], *, captured_at: str) -> _Record: ...
    def get(self, run_id: str) -> _Record | None: ...


def _build_record(run_id: str, bindings: list[_Record], captured_at: str) -> _Record:
    return {"run_id": run_id, "captured_at": captured_at, "bindings": bindings}


# --- JSONL (default, offline) ---------------------------------------------------------------


def binding_path() -> Path:
    raw = os.environ.get(_ENV_PATH, "").strip()
    return Path(raw) if raw else _DEFAULT_PATH


class JsonlAgentBindingStore(JsonlDocStore):
    """One run's bindings per line — the zero-dependency default. ``get`` returns the LAST record
    for a run id (a re-recorded run wins), so it is robust to an accidental duplicate append."""

    _lock = _WRITE_LOCK
    _tolerant = False

    def _resolve_path(self) -> Path:
        return binding_path()

    def record(self, run_id: str, bindings: list[_Record], *, captured_at: str) -> _Record:
        return self._append(_build_record(run_id, bindings, captured_at))

    def get(self, run_id: str) -> _Record | None:
        matches = [r for r in self._read_all() if r.get("run_id") == run_id]
        return matches[-1] if matches else None


# --- SQLite ---------------------------------------------------------------------------------


def binding_db_path() -> str:
    return os.environ.get(_ENV_DB, "").strip() or str(_DEFAULT_DB)


class SqliteAgentBindingStore(SqliteStore):
    """An ``agent_bindings`` table (stdlib). ``run_id`` is the PK; a re-record upserts."""

    _ddl = _DDL_SQLITE

    def __init__(self, path: str | None = None) -> None:
        super().__init__(path or binding_db_path())

    def record(self, run_id: str, bindings: list[_Record], *, captured_at: str) -> _Record:
        rec = _build_record(run_id, bindings, captured_at)
        with _WRITE_LOCK:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO agent_bindings (run_id, captured_at, record) VALUES (?, ?, ?) "
                    "ON CONFLICT(run_id) DO UPDATE SET captured_at=excluded.captured_at, "
                    "record=excluded.record",
                    (run_id, captured_at, json.dumps(rec, ensure_ascii=False)),
                )
                conn.commit()
            finally:
                conn.close()
        return rec

    def get(self, run_id: str) -> _Record | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT record FROM agent_bindings WHERE run_id = ?", (run_id,)
            ).fetchone()
            return json.loads(row[0]) if row else None
        finally:
            conn.close()


# --- Postgres (off by default) --------------------------------------------------------------


class PostgresAgentBindingStore:
    """An ``agent_bindings`` table in Postgres (the ``[postgres]`` extra); a fresh conn per op."""

    def __init__(self, dsn: str | None = None) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise RuntimeError("PostgresAgentBindingStore needs the 'postgres' extra.") from exc
        self._dsn = dsn or os.environ.get(_ENV_DATABASE_URL, "").strip()
        if not self._dsn:
            raise RuntimeError("PostgresAgentBindingStore needs DATABASE_URL.")
        self._psycopg = psycopg
        with self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(_DDL_POSTGRES)

    def record(self, run_id: str, bindings: list[_Record], *, captured_at: str) -> _Record:
        from psycopg.types.json import Jsonb

        rec = _build_record(run_id, bindings, captured_at)
        with _WRITE_LOCK, self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(
                "INSERT INTO agent_bindings (run_id, captured_at, record) VALUES (%s, %s, %s) "
                "ON CONFLICT (run_id) DO UPDATE SET captured_at=excluded.captured_at, "
                "record=excluded.record",
                (run_id, captured_at, Jsonb(rec)),
            )
        return rec

    def get(self, run_id: str) -> _Record | None:
        from psycopg.rows import dict_row

        with self._psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                "SELECT record FROM agent_bindings WHERE run_id = %s", (run_id,)
            ).fetchone()
            return row["record"] if row else None


def get_agent_binding_store() -> AgentBindingStore:
    """Select the agent-binding sink from the environment (default: the offline JSONL file)."""
    jsonl: Callable[[], AgentBindingStore] = JsonlAgentBindingStore
    sqlite: Callable[[], AgentBindingStore] = SqliteAgentBindingStore
    postgres: Callable[[], AgentBindingStore] = PostgresAgentBindingStore
    return select_backend(_ENV_STORE, jsonl=jsonl, sqlite=sqlite, postgres=postgres)
