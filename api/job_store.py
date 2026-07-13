"""Durable job store + a process-group-aware driver launcher for the two execution routers.

The intake (``routers/intake.py``) and Builder-run (``routers/pipeline_run.py``) endpoints both
launch the external Nextflow driver as a background job. Their old in-process ``dict`` registries
were **non-durable**: a backend restart lost every job's state and orphaned its ``data/<run_id>/`` /
``.nf-runs/<run_id>`` scratch, so a poller hung on ``running`` forever. This module makes that job
state survive a restart, over the shared :mod:`api.base_store` generic (ADR-0016):

  - :class:`JsonlJobStore` — default, zero-dep upsertable JSONL file (``PIPEGUARD_JOB_PATH``).
  - :class:`SqliteJobStore` — a ``jobs`` table (stdlib; ``PIPEGUARD_JOB_DB``).

``get_job_store()`` selects via ``PIPEGUARD_JOB_STORE`` (default ``jsonl``) and **degrades to the
offline JSONL** if the SQLite adapter can't be constructed, so a misconfigured DB never breaks the
execution path — it just falls back to the file. There is no Postgres adapter here (unlike the
share/review sinks): a job record is short-lived, single-node scratch bookkeeping, not shared
product state, so the two local backends suffice.

A job is **mutable** (queued → running → complete/failed), so the contract is ``upsert`` / ``get``
/ ``list`` keyed on ``(kind, run_id)`` — a job's kind (``intake`` vs ``builder-run``) plus its run
id. The router owns the record shape; the store only persists it. Restart recovery lives in the
router (it alone knows the run-dir path + which jobs THIS process actually launched a thread for).

This module is ALSO the single home for the shared driver-launch primitive (:func:`run_driver` +
:data:`DRIVER_TIMEOUT_S`), because the two routers must launch the driver identically. The old code
diverged — 900 s in intake, 1800 s in Builder-run — and ``subprocess.run(..., timeout=…)`` reaps
only the DIRECT child on a timeout, orphaning the Nextflow/JVM/tool subtree. One helper enforces one
timeout and one process-group kill for both. Compose ≠ execute still holds at the CORE
(``src/pipeguard/`` never shells out); only this API/driver layer launches a subprocess.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from api.base_store import JsonlDocStore, SqliteStore, select_backend

# The Protocol has a method named ``list`` (per its contract) which shadows the builtin inside the
# class bodies, so a ``-> list[...]`` annotation would resolve to the method. Module-level aliases
# (bound before any shadow) keep the annotations unambiguous — the same guard the review store uses.
_Record = dict[str, Any]
_Records = list[dict[str, Any]]

_ENV_JOB_STORE = "PIPEGUARD_JOB_STORE"
_ENV_JOB_PATH = "PIPEGUARD_JOB_PATH"
_ENV_JOB_DB = "PIPEGUARD_JOB_DB"

_REPO_ROOT = Path(__file__).resolve().parent.parent
# Default sinks live under ``.nf-runs/`` (already gitignored, the run-scratch home both routers
# use), so a demo run leaves no untracked file in the repo root and needs no .gitignore change.
_DEFAULT_JOB_PATH = _REPO_ROOT / ".nf-runs" / "jobs.events.jsonl"
_DEFAULT_JOB_DB = _REPO_ROOT / ".nf-runs" / "jobs.sqlite"

# The two job kinds the execution routers register (the discriminator half of the store key).
KIND_INTAKE = "intake"
KIND_BUILDER_RUN = "builder-run"

# Terminal statuses — a job in one of these never gets reconciled again. ``lost`` is the honest
# outcome for a job whose owning process died mid-run with no result dir on disk (see the routers'
# ``_reconcile``); the driver itself only ever sets queued/running/complete/failed.
TERMINAL_STATUSES = frozenset({"complete", "failed", "lost"})

# Operator-parked statuses (ADR-0021): an intake run submitted with ``mode=hold`` (``held``) or
# ``mode=schedule`` (``scheduled``) is registered WITHOUT launching the driver — the operator gates
# or schedules processing, then releases it (``POST /api/runs/{id}/release``). These are non-
# terminal but INTENTIONALLY never launched a thread, so ``_reconcile`` must treat them as parked
# (returned as-is), never mis-reconcile them to ``lost`` the way it does a job whose owner process
# actually died mid-run. A time-based auto-release scheduler is a DEFERRED seam (ADR-0021) — release
# is manual.
HELD_STATUSES = frozenset({"held", "scheduled"})

# One timeout for BOTH routers (was 900 s intake / 1800 s Builder). The larger value: a real live
# HG002 run through ``nextflow run`` can take a while, and prematurely reaping it mid-run is worse
# than waiting. Illustrative/configurable, not a clinical or SLA guarantee.
DRIVER_TIMEOUT_S = 1800

# Serialize file/DB writes within a worker so two concurrent upserts can't interleave a JSONL line
# or race a rewrite. Multi-worker (or two writes to the SAME job) needs a file lock / per-row DB
# transaction — a documented seam, not built (the same honest limit as ADR-0016 / the other sinks).
# Shared by both adapters of THIS store.
_WRITE_LOCK = threading.Lock()

_JOB_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS jobs (
    id         TEXT PRIMARY KEY,
    kind       TEXT,
    run_id     TEXT,
    status     TEXT,
    created_at TEXT,
    updated_at TEXT,
    record     TEXT NOT NULL
);
"""


def now_iso() -> str:
    """A UTC ISO-8601 timestamp for a job's created_at/updated_at (shared by both routers)."""
    return datetime.now(timezone.utc).isoformat()


def job_key(kind: str, run_id: str) -> str:
    """The store's primary key — ``kind`` namespaces the run id so an intake job and a Builder-run
    job that (only ever theoretically) share a run id can never collide on one record."""
    return f"{kind}:{run_id}"


def _keyed(record: _Record) -> str:
    return job_key(str(record.get("kind") or ""), str(record.get("run_id") or ""))


class JobStore(Protocol):
    """Durable, mutable sink for background execution jobs.

    ``upsert`` persists (insert-or-replace) one job keyed on ``(kind, run_id)`` and returns it;
    ``get`` returns one job by ``(run_id, kind)`` or ``None``; ``list`` returns jobs, optionally
    filtered by ``kind``, ordered by ``created_at``.
    """

    def upsert(self, record: _Record) -> _Record: ...
    def get(self, run_id: str, kind: str) -> _Record | None: ...
    def list(self, *, kind: str | None = None) -> _Records: ...


# --- JSONL (default, offline) ---------------------------------------------------------------


def job_path() -> Path:
    """The JSONL sink path, resolved at call-time from the env (so tests monkeypatch cleanly)."""
    raw = os.environ.get(_ENV_JOB_PATH, "").strip()
    return Path(raw) if raw else _DEFAULT_JOB_PATH


class JsonlJobStore(JsonlDocStore):
    """One job per line in a JSONL file — the zero-dependency default.

    ``upsert`` rewrites the whole file (the base's read → replace-or-append the matching key →
    atomic ``os.replace`` of a sibling temp file), so a crash mid-write leaves the old file intact
    rather than a half-written one. At demo scale (a handful of jobs) rewriting is fine. Reads are
    tolerant: a missing file → ``[]`` and a partial/corrupt line is skipped, not raised.
    """

    _lock = _WRITE_LOCK
    _tolerant = True

    def _resolve_path(self) -> Path:
        return job_path()

    def upsert(self, record: _Record) -> _Record:
        key = _keyed(record)

        def mutate(rows: _Records) -> _Records:
            for i, r in enumerate(rows):
                if _keyed(r) == key:
                    rows[i] = record
                    return rows
            rows.append(record)
            return rows

        self._rewrite(mutate)
        return record

    def get(self, run_id: str, kind: str) -> _Record | None:
        key = job_key(kind, run_id)
        return next((r for r in self._read_all() if _keyed(r) == key), None)

    def list(self, *, kind: str | None = None) -> _Records:
        rows = [r for r in self._read_all() if kind is None or r.get("kind") == kind]
        return sorted(rows, key=lambda r: (str(r.get("created_at") or ""), _keyed(r)))


# --- SQLite (a real DB, still offline + zero-dep) -------------------------------------------


def job_db_path() -> str:
    """The SQLite job-DB path (``PIPEGUARD_JOB_DB`` or the ``.nf-runs`` default)."""
    return os.environ.get(_ENV_JOB_DB, "").strip() or str(_DEFAULT_JOB_DB)


class SqliteJobStore(SqliteStore):
    """A ``jobs`` table in SQLite (stdlib). A fresh connection per op keeps it thread-safe under
    FastAPI's sync threadpool without pinning a connection to one thread."""

    _ddl = _JOB_DDL_SQLITE
    _mkdir_parent = True  # the default sink lives under a gitignored ``.nf-runs/`` (may not exist)

    def __init__(self, path: str | None = None) -> None:
        super().__init__(path or job_db_path())

    def upsert(self, record: _Record) -> _Record:
        with _WRITE_LOCK:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO jobs
                       (id, kind, run_id, status, created_at, updated_at, record)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        _keyed(record),
                        record.get("kind"),
                        record.get("run_id"),
                        record.get("status"),
                        record.get("created_at"),
                        record.get("updated_at"),
                        json.dumps(record, ensure_ascii=False),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return record

    def get(self, run_id: str, kind: str) -> _Record | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT record FROM jobs WHERE id = ?", (job_key(kind, run_id),)
            ).fetchone()
            return json.loads(row[0]) if row else None
        finally:
            conn.close()

    def list(self, *, kind: str | None = None) -> _Records:
        # ``kind`` is always a bound parameter — no SQL is built from caller input.
        where = " WHERE kind = ?" if kind is not None else ""
        params: list[Any] = [kind] if kind is not None else []
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT record FROM jobs{where} ORDER BY created_at, id", params
            ).fetchall()
            return [json.loads(r[0]) for r in rows]
        finally:
            conn.close()


def get_job_store() -> JobStore:
    """Select the job sink from the environment (default: the offline JSONL file).

    ``PIPEGUARD_JOB_STORE=sqlite`` swaps in the SQLite adapter; ANY failure constructing it (an
    unwritable path) degrades to the JSONL store — see :func:`api.base_store.select_backend`. Any
    other value (incl. the default) is JSONL.
    """
    jsonl: Callable[[], JobStore] = JsonlJobStore
    sqlite: Callable[[], JobStore] = SqliteJobStore
    return select_backend(_ENV_JOB_STORE, jsonl=jsonl, sqlite=sqlite)


# --- Shared driver launch (process-group-aware) ---------------------------------------------


def _kill_group(proc: subprocess.Popen[str]) -> None:
    """Reap the driver's WHOLE process group (Nextflow + JVM + tools), not just the direct child."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()  # group lookup failed → at least kill the direct child


def run_driver(
    cmd: list[str], *, cwd: str, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Launch the external pipeline driver in its OWN process group and reap the whole subtree.

    ``subprocess.run(..., timeout=…)`` kills only the DIRECT child on a timeout, orphaning the
    Nextflow/JVM/tool subtree it spawned. ``start_new_session=True`` makes the child a session /
    process-group leader (``setsid``), so on :class:`subprocess.TimeoutExpired` we ``os.killpg`` the
    whole group before re-raising — nothing lingers. Returns a :class:`subprocess.CompletedProcess`
    so callers keep the familiar ``.returncode`` / ``.stdout`` / ``.stderr`` shape.
    """
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=DRIVER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        out, err = proc.communicate()  # reap the now-killed group so no zombie lingers
        raise subprocess.TimeoutExpired(cmd, DRIVER_TIMEOUT_S, output=out, stderr=err) from None
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)
