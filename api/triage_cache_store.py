"""Persistent cache for rule-derived QC-triage notes — a PRODUCT store, OFF the gate.

A triage note is DERIVED from a card's rule findings (+ the retrieval corpus + the agent). On the
live path each generation is a Claude call; navigating away and back re-fetches the endpoint and
would regenerate it — cost + latency for an identical result. This store caches the generated note
keyed by a **stable card signature** so a repeat request is served from the cache, not regenerated,
and every note is **saved + logged** in the backend (structured, ML-minable) rather than being
ephemeral per request.

The cache key encodes staleness: it hashes the card's findings' rule-version-independent
``signature``s + the agent identity (name/model) + the corpus version, so a changed card, a flipped
agent, or a bumped corpus yields a NEW key (regenerate); an unchanged card reuses. Keying on finding
signatures (not the per-run-gate ``analysis_run_id``) keeps hits stable across restarts.

Off the gate (ADR-0001): caching a note never re-enters the deterministic gate or sets a verdict.
Three env-selected adapters (``BAYLEAF_TRIAGE_CACHE_STORE`` = jsonl default / sqlite / postgres),
degrade-to-JSONL on any DB failure — mirrors the other off-gate sinks over :mod:`api.base_store`.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from api.base_store import JsonlDocStore, SqliteStore, select_backend

_Record = dict[str, Any]

_ENV_STORE = "BAYLEAF_TRIAGE_CACHE_STORE"
_ENV_PATH = "BAYLEAF_TRIAGE_CACHE_PATH"
_ENV_DB = "BAYLEAF_TRIAGE_CACHE_DB"
_ENV_DATABASE_URL = "DATABASE_URL"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PATH = _REPO_ROOT / "triage_cache.jsonl"
_DEFAULT_DB = _REPO_ROOT / "triage_cache.sqlite"

_WRITE_LOCK = threading.Lock()

_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS triage_cache (
    cache_key  TEXT PRIMARY KEY,
    run_id     TEXT,
    sample_id  TEXT,
    created_at TEXT,
    record     TEXT NOT NULL
);
"""
_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS triage_cache (
    cache_key  TEXT PRIMARY KEY,
    run_id     TEXT,
    sample_id  TEXT,
    created_at TIMESTAMPTZ,
    record     JSONB NOT NULL
);
"""


def triage_cache_key(
    *,
    run_id: str,
    sample_id: str,
    signatures: list[str],
    agent: str,
    model: str | None,
    corpus_version: str,
) -> str:
    """A stable cache key for a card's triage note. Hashes the SORTED finding signatures (stable
    across restarts + rule versions) plus the agent identity + corpus version, so any change that
    would alter the note yields a new key."""
    payload = json.dumps(
        {
            "run_id": run_id,
            "sample_id": sample_id,
            "signatures": sorted(signatures),
            "agent": agent,
            "model": model,
            "corpus_version": corpus_version,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class TriageCacheStore(Protocol):
    """get(cache_key) → the cached record or None; put(record) upserts by ``cache_key``."""

    def get(self, cache_key: str) -> _Record | None: ...
    def put(self, record: _Record) -> _Record: ...


# --- JSONL (default, offline) ---------------------------------------------------------------


def cache_path() -> Path:
    raw = os.environ.get(_ENV_PATH, "").strip()
    return Path(raw) if raw else _DEFAULT_PATH


class JsonlTriageCacheStore(JsonlDocStore):
    """One cache record per line; ``get`` returns the LAST record for a key (an upsert appends, so
    the latest wins on read) and ``put`` appends. A crash mid-append is tolerated (a partial line is
    skipped on read) — a cache is rebuildable, so an occasional miss is harmless."""

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


class SqliteTriageCacheStore(SqliteStore):
    """A ``triage_cache`` table (stdlib); ``cache_key`` PK, ``put`` upserts."""

    _ddl = _DDL_SQLITE

    def __init__(self, path: str | None = None) -> None:
        super().__init__(path or cache_db_path())

    def get(self, cache_key: str) -> _Record | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT record FROM triage_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
            return json.loads(row[0]) if row else None
        finally:
            conn.close()

    def put(self, record: _Record) -> _Record:
        with _WRITE_LOCK:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO triage_cache (cache_key, run_id, sample_id, created_at, record) "
                    "VALUES (?, ?, ?, ?, ?) ON CONFLICT(cache_key) DO UPDATE SET record=excluded."
                    "record, created_at=excluded.created_at",
                    (
                        record.get("cache_key"),
                        record.get("run_id"),
                        record.get("sample_id"),
                        record.get("created_at"),
                        json.dumps(record, ensure_ascii=False),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return record


# --- Postgres (off by default) --------------------------------------------------------------


class PostgresTriageCacheStore:
    """A ``triage_cache`` table in Postgres (the ``[postgres]`` extra); a fresh conn per op."""

    def __init__(self, dsn: str | None = None) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise RuntimeError("PostgresTriageCacheStore needs the 'postgres' extra.") from exc
        self._dsn = dsn or os.environ.get(_ENV_DATABASE_URL, "").strip()
        if not self._dsn:
            raise RuntimeError("PostgresTriageCacheStore needs DATABASE_URL.")
        self._psycopg = psycopg
        with self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(_DDL_POSTGRES)

    def get(self, cache_key: str) -> _Record | None:
        from psycopg.rows import dict_row

        with self._psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                "SELECT record FROM triage_cache WHERE cache_key = %s", (cache_key,)
            ).fetchone()
            return row["record"] if row else None

    def put(self, record: _Record) -> _Record:
        from psycopg.types.json import Jsonb

        with _WRITE_LOCK, self._psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(
                "INSERT INTO triage_cache (cache_key, run_id, sample_id, created_at, record) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (cache_key) DO UPDATE SET "
                "record=excluded.record, created_at=excluded.created_at",
                (
                    record.get("cache_key"),
                    record.get("run_id"),
                    record.get("sample_id"),
                    record.get("created_at"),
                    Jsonb(record),
                ),
            )
        return record


def get_triage_cache_store() -> TriageCacheStore:
    """Select the triage-cache sink from the environment (default: the offline JSONL file)."""
    jsonl: Callable[[], TriageCacheStore] = JsonlTriageCacheStore
    sqlite: Callable[[], TriageCacheStore] = SqliteTriageCacheStore
    postgres: Callable[[], TriageCacheStore] = PostgresTriageCacheStore
    return select_backend(_ENV_STORE, jsonl=jsonl, sqlite=sqlite, postgres=postgres)
