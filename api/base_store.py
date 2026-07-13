"""The ONE generic JSONL document store the seven off-gate sinks share (WS-06 Gap 6, ADR-0016).

``api/feedback_store`` / ``library_store`` / ``review_store`` / ``pipeline_store`` /
``settings_store`` / ``job_store`` / ``share_store`` were the SAME "indexed columns + full-JSON
document, env-selected backend, degrade-to-JSONL" shape copy-pasted seven times. That copy is
collapsed here: :class:`JsonlStore` owns the single copy of the JSONL read loop, the locked
append-a-line write, the locked read-modify-append (version authoring), and the locked atomic
whole-file rewrite (upsert/update). Each concrete store becomes a THIN typed subclass that supplies
encode/decode + a path provider + its module write lock, and expresses its public methods
(``for_run`` / ``append`` / ``add`` / ``create`` / ``update`` / ``upsert`` / ``list`` / ``get`` /
``get_versions``) over these primitives — so no concrete store carries its own read/append loop.

Two families of record ride the base:
  - :class:`JsonlDocStore` — records are plain JSON documents (``dict``), encoded with
    ``json.dumps(..., ensure_ascii=False)`` and decoded with ``json.loads`` (six of the seven).
  - :class:`JsonlStore` directly, parametrised on a pydantic model — the share sink encodes a
    ``ProvenanceEvent`` via ``model_dump_json`` / ``model_validate_json``.

Scope: this unifies the **JSONL** path (the default, offline, zero-dependency backend) and the
SQLite connection lifecycle (:class:`SqliteStore`). The off-by-default Postgres adapters are left
as-is per store (a package rename / a real DB pool are separate deferred passes, ADR-0016).

Behaviour is byte- and interface-preserving: a record's JSONL bytes are identical to the
pre-refactor serialization, and every concrete store keeps its exact public method signatures (the
routers under ``api/routers/*`` call them). This is a pure structural refactor.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, Generic, TypeVar

_log = logging.getLogger(__name__)

#: A stored record: a pydantic model (share) or a plain JSON document (the other six).
ModelT = TypeVar("ModelT")
#: The store Protocol a ``get_*_store`` selector returns.
StoreT = TypeVar("StoreT")


class JsonlStore(Generic[ModelT]):
    """Generic append/rewrite JSONL document store — the single home for the JSONL boilerplate.

    A concrete store subclasses this and provides:
      - :meth:`_resolve_path` — its ``BAYLEAF_*_PATH`` sink (resolved at call-time so tests
        monkeypatch cleanly);
      - :meth:`_encode` / :meth:`_decode` — one record <-> one JSONL line;
      - :attr:`_lock` — its MODULE-level ``_WRITE_LOCK`` (so the JSONL / SQLite / Postgres adapters
        of ONE store share one lock, while unrelated stores stay independent — no global lock);
      - :attr:`_tolerant` — whether a partial/corrupt line is skipped (True) or surfaced (False),
        set per store to preserve each store's existing read behaviour exactly.

    then expresses its public methods over :meth:`_read_all`, :meth:`_append`,
    :meth:`_append_authored`, and :meth:`_rewrite`.
    """

    #: Each concrete subclass points this at its module ``_WRITE_LOCK``. The base default is only a
    #: placeholder (the base is never instantiated directly).
    _lock: ClassVar[Any] = threading.Lock()
    #: Whether a partial/corrupt JSONL line is tolerated on read. Overridden per store.
    _tolerant: ClassVar[bool] = True

    # --- hooks a concrete store overrides -------------------------------------------------------

    def _resolve_path(self) -> Path:
        """The JSONL sink path (resolved fresh per call so an env monkeypatch takes effect)."""
        raise NotImplementedError

    def _encode(self, model: ModelT) -> str:
        """Serialize one record to a single JSONL line (WITHOUT the trailing newline)."""
        raise NotImplementedError

    def _decode(self, line: str) -> ModelT:
        """Parse one JSONL line back into a record."""
        raise NotImplementedError

    # --- the single shared read loop ------------------------------------------------------------

    def _read_all(self) -> list[ModelT]:
        """Every persisted record, in file (append) order. A missing file -> ``[]``; a blank line is
        skipped; a partial/corrupt line is skipped when :attr:`_tolerant`, else it surfaces (a
        crashed append is a signal, not a crash — the tolerant boundary of CLAUDE.md)."""
        path = self._resolve_path()
        if not path.exists():
            return []
        out: list[ModelT] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            if self._tolerant:
                try:
                    out.append(self._decode(line))
                except ValueError:
                    continue  # tolerate a partial/corrupt line
            else:
                out.append(self._decode(line))
        return out

    # --- the single shared writers --------------------------------------------------------------

    def _write_line(self, path: Path, model: ModelT) -> None:
        """Append one encoded record as a line. ``_encode`` escapes every value, so a payload with a
        newline or quote can never forge a second line."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(self._encode(model) + "\n")

    def _append(self, model: ModelT) -> ModelT:
        """Append one record under the write lock (the plain append: share/feedback/library)."""
        path = self._resolve_path()
        with self._lock:
            self._write_line(path, model)
        return model

    def _append_authored(self, build: Callable[[list[ModelT]], ModelT]) -> ModelT:
        """Read-then-append UNDER one lock acquisition: ``build`` sees the current records and
        returns the record to append (monotonic per-name version authoring, pipeline/settings) — so
        no two concurrent saves of a name can pick the same version within a worker."""
        with self._lock:
            model = build(self._read_all())
            self._write_line(self._resolve_path(), model)
        return model

    def _rewrite(self, mutate: Callable[[list[ModelT]], list[ModelT]]) -> None:
        """Read-modify-write the WHOLE file atomically under the lock: ``mutate`` transforms the
        current rows (upsert-by-key for job, replace-by-id for review) and may raise (e.g. a missing
        id) before any write. Writes a sibling temp file then ``os.replace``-swaps it, so a crash
        mid-rewrite leaves the old file intact rather than a half-written one."""
        with self._lock:
            rows = mutate(self._read_all())
            path = self._resolve_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(self._encode(row) + "\n")
            tmp.replace(path)


class JsonlDocStore(JsonlStore[dict[str, Any]]):
    """A :class:`JsonlStore` whose records are plain JSON documents (dicts).

    Encodes with ``json.dumps(..., ensure_ascii=False)`` (space separators, non-ASCII preserved) and
    decodes with ``json.loads`` — byte-identical to the six copy-pasted dict stores' prior output.
    """

    def _encode(self, model: dict[str, Any]) -> str:
        return json.dumps(model, ensure_ascii=False)

    def _decode(self, line: str) -> dict[str, Any]:
        obj: dict[str, Any] = json.loads(line)
        return obj


class SqliteStore:
    """The shared SQLite connection lifecycle for the DB adapters (the JSONL boilerplate's DB twin).

    A concrete SQLite store sets :attr:`_ddl` (its ``CREATE TABLE IF NOT EXISTS``), optionally
    :attr:`_mkdir_parent` (create the DB's parent dir first — the job sink lives under a gitignored
    ``.nf-runs/``), then reuses :meth:`_connect`. A fresh connection per op keeps it thread-safe
    under FastAPI's sync threadpool without pinning a connection to one thread; the constructor
    opens once to FAIL FAST at selection so ``get_*_store`` can degrade to JSONL on a bad path.
    """

    _ddl: ClassVar[str]
    _mkdir_parent: ClassVar[bool] = False

    def __init__(self, path: str) -> None:
        self._path = path
        if self._mkdir_parent:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._connect().close()  # fail fast at selection if the dir is unwritable

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.execute(self._ddl)
        return conn


def select_backend(
    env_var: str,
    *,
    jsonl: Callable[[], StoreT],
    sqlite: Callable[[], StoreT] | None = None,
    postgres: Callable[[], StoreT] | None = None,
) -> StoreT:
    """Select an off-gate sink from ``env_var`` (default: the offline JSONL file) — the ONE copy of
    the degrade-to-JSONL ladder the seven ``get_*_store`` functions share.

    ``=sqlite`` / ``=postgres`` swap in a DB adapter when its factory is provided; ANY failure
    constructing it (missing extra / DSN, unwritable path, unreachable server) degrades to the JSONL
    store — logged by exception *type* only, never ``str(exc)`` (which could carry a DSN password).
    A choice with no matching factory (e.g. ``=postgres`` where a store has no Postgres adapter)
    falls through to JSONL, matching the prior per-store behaviour.
    """
    choice = os.environ.get(env_var, "jsonl").strip().lower()
    if choice == "postgres" and postgres is not None:
        try:
            return postgres()
        except Exception as exc:  # degrade on ANY failure; never leak the DSN
            _log.warning("%s=postgres unavailable (%s); using JSONL.", env_var, type(exc).__name__)
    elif choice == "sqlite" and sqlite is not None:
        try:
            return sqlite()
        except Exception as exc:  # degrade on ANY failure
            _log.warning("%s=sqlite unavailable (%s); using JSONL.", env_var, type(exc).__name__)
    return jsonl()
