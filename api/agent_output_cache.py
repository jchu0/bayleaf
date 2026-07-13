"""Generic persistent cache for advisory-agent OUTPUTS — one store, off the gate.

Rule-/input-derived agent outputs (a QC-triage note, a pipeline-repair proposal, a node-author
proposal, an archivist digest) are all: (1) derived from a STABLE input, (2) on the live path a
Claude call, and (3) re-fetched on navigation. This module caches them by a content key so an
identical request is served from the backend, not regenerated, and every output is **saved +
logged** (structured, ML-minable). It is the generalization of the triage-only cache.

Off the gate (ADR-0001): caching an advisory output never re-enters the deterministic gate or sets a
verdict. Three env-selected adapters (``BAYLEAF_AGENT_CACHE_STORE`` = jsonl default / sqlite /
postgres), degrade-to-JSONL, over :mod:`api.base_store` — same shape as the other off-gate sinks.

The ``cache_through`` helper is the single call site each endpoint uses:

    note = cache_through(
        namespace="triage",
        key_inputs={"run_id": ..., "signatures": [...], "agent": agent.name, ...},
        generate=lambda: triage_card(card, agent=agent),
        model_cls=TriageNote,
        expected_by=agent.name,   # don't cache a live→stub degrade under the live key
    )
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from api.base_store import JsonlDocStore, SqliteStore, select_backend

_Record = dict[str, Any]
_ModelT = TypeVar("_ModelT", bound=BaseModel)

_ENV_STORE = "BAYLEAF_AGENT_CACHE_STORE"
_ENV_PATH = "BAYLEAF_AGENT_CACHE_PATH"
_ENV_DB = "BAYLEAF_AGENT_CACHE_DB"
_ENV_DATABASE_URL = "DATABASE_URL"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PATH = _REPO_ROOT / "agent_output_cache.jsonl"
_DEFAULT_DB = _REPO_ROOT / "agent_output_cache.sqlite"

_WRITE_LOCK = threading.Lock()

_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS agent_output_cache (
    cache_key  TEXT PRIMARY KEY,
    namespace  TEXT,
    created_at TEXT,
    record     TEXT NOT NULL
);
"""
_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS agent_output_cache (
    cache_key  TEXT PRIMARY KEY,
    namespace  TEXT,
    created_at TIMESTAMPTZ,
    record     JSONB NOT NULL
);
"""


def agent_cache_key(namespace: str, key_inputs: dict[str, Any]) -> str:
    """A stable cache key: sha256 over the namespace + the key inputs (sorted). List values are
    sorted so order-independence holds; the caller puts every field that should invalidate the
    cache (input identity, agent name/model, corpus/version) into ``key_inputs``."""
    norm = {k: (sorted(v) if isinstance(v, list) else v) for k, v in key_inputs.items()}
    payload = json.dumps({"ns": namespace, "in": norm}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class AgentOutputCache(Protocol):
    def get(self, cache_key: str) -> _Record | None: ...
    def put(self, record: _Record) -> _Record: ...


# --- JSONL (default, offline) ---------------------------------------------------------------


def cache_path() -> Path:
    raw = os.environ.get(_ENV_PATH, "").strip()
    return Path(raw) if raw else _DEFAULT_PATH


class JsonlAgentOutputCache(JsonlDocStore):
    """One record per line; ``get`` returns the LAST record for a key (an upsert appends, latest
    wins). Tolerant of a partial line — a cache is rebuildable, so a skipped line is a harmless
    miss, not a crash."""

    _lock = _WRITE_LOCK
    _tolerant = True

    def _resolve_path(self) -> Path:
        return cache_path()

    def get(self, cache_key: str) -> _Record | None:
        matches = [r for r in self._read_all() if r.get("cache_key") == cache_key]
        return matches[-1] if matches else None

    def put(self, record: _Record) -> _Record:
        return self._append(record)


# --- SQLite ---------------------------------------------------------------------------------


def cache_db_path() -> str:
    return os.environ.get(_ENV_DB, "").strip() or str(_DEFAULT_DB)


class SqliteAgentOutputCache(SqliteStore):
    _ddl = _DDL_SQLITE

    def __init__(self, path: str | None = None) -> None:
        super().__init__(path or cache_db_path())

    def get(self, cache_key: str) -> _Record | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT record FROM agent_output_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
            return json.loads(row[0]) if row else None
        finally:
            conn.close()

    def put(self, record: _Record) -> _Record:
        with _WRITE_LOCK:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO agent_output_cache (cache_key, namespace, created_at, record) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(cache_key) DO UPDATE SET record=excluded."
                    "record, created_at=excluded.created_at, namespace=excluded.namespace",
                    (
                        record.get("cache_key"),
                        record.get("namespace"),
                        record.get("created_at"),
                        json.dumps(record, ensure_ascii=False),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return record


# --- Postgres (off by default) --------------------------------------------------------------


class PostgresAgentOutputCache:
    def __init__(self, dsn: str | None = None) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise RuntimeError("PostgresAgentOutputCache needs the 'postgres' extra.") from exc
        self._dsn = dsn or os.environ.get(_ENV_DATABASE_URL, "").strip()
        if not self._dsn:
            raise RuntimeError("PostgresAgentOutputCache needs DATABASE_URL.")
        self._psycopg = psycopg
        with self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(_DDL_POSTGRES)

    def get(self, cache_key: str) -> _Record | None:
        from psycopg.rows import dict_row

        with self._psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                "SELECT record FROM agent_output_cache WHERE cache_key = %s", (cache_key,)
            ).fetchone()
            return row["record"] if row else None

    def put(self, record: _Record) -> _Record:
        from psycopg.types.json import Jsonb

        with _WRITE_LOCK, self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(
                "INSERT INTO agent_output_cache (cache_key, namespace, created_at, record) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (cache_key) DO UPDATE SET "
                "record=excluded.record, created_at=excluded.created_at, "
                "namespace=excluded.namespace",
                (
                    record.get("cache_key"),
                    record.get("namespace"),
                    record.get("created_at"),
                    Jsonb(record),
                ),
            )
        return record


def get_agent_output_cache() -> AgentOutputCache:
    """Select the agent-output cache sink from the environment (default: the offline JSONL file)."""
    jsonl: Callable[[], AgentOutputCache] = JsonlAgentOutputCache
    sqlite: Callable[[], AgentOutputCache] = SqliteAgentOutputCache
    postgres: Callable[[], AgentOutputCache] = PostgresAgentOutputCache
    return select_backend(_ENV_STORE, jsonl=jsonl, sqlite=sqlite, postgres=postgres)


def cache_through(
    *,
    namespace: str,
    key_inputs: dict[str, Any],
    generate: Callable[[], _ModelT | None],
    model_cls: type[_ModelT],
    expected_by: str | None = None,
) -> _ModelT | None:
    """Serve ``generate()``'s pydantic output from the cache when a matching key exists, else
    generate + save + log. Returns ``None`` iff ``generate()`` does.

    ``expected_by`` (an agent name): when set, the output is cached only if its ``generated_by``
    equals it — so a transient live→stub degrade is NOT pinned under the live key (it retries).
    """
    key = agent_cache_key(namespace, key_inputs)
    store = get_agent_output_cache()
    hit = store.get(key)
    if hit is not None:
        return model_cls.model_validate(hit["payload"])
    obj = generate()
    if obj is not None:
        by = getattr(obj, "generated_by", None)
        if expected_by is None or by == expected_by:
            store.put(
                {
                    "cache_key": key,
                    "namespace": namespace,
                    "generated_by": by,
                    "model": getattr(obj, "model", None),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "key_inputs": key_inputs,
                    "payload": obj.model_dump(mode="json"),
                }
            )
    return obj
