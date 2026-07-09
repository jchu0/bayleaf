"""Persistence layer: the relational projection of the event ledger (Phase 2).

The append-only JSONL ledger is authoritative; this package is the *rebuildable
projection* of it (ADR-0002), reached only through the :class:`Repository` port
(ADR-0003) so the core never touches a DB directly. `SqliteRepository` is the
default adapter (stdlib `sqlite3`, no new dependency); `PostgresRepository` is the
production adapter (behind the optional `[postgres]` extra, OFF by default,
ADR-0016). `get_repository` flips between them from the environment; `project_events`
maps the event stream onto rows; `rebuild_db` replays a ledger file into a fresh DB.
"""

from __future__ import annotations

import logging
import os

from .postgres import PostgresRepository, database_url_from_env
from .projector import project_events
from .records import CardRow, FindingRow, RunBundle, RunRow, SampleRow
from .replay import read_ledger, rebuild_db
from .repository import Repository
from .sqlite import PERSIST_SCHEMA_VERSION, SqliteRepository

# Env knobs selecting the adapter (mirrors PIPEGUARD_ARTIFACT_STORE / PIPEGUARD_NOTIFIER).
# Default is the offline SQLite store so the demo/tests never reach a network.
_ENV_REPOSITORY = "PIPEGUARD_REPOSITORY"
_ENV_SQLITE_PATH = "PIPEGUARD_DB_PATH"
_log = logging.getLogger(__name__)


def get_repository(*, sqlite_path: str | None = None) -> Repository:
    """Select the projection adapter from the environment (default: offline SQLite).

    ``PIPEGUARD_REPOSITORY=postgres`` uses :class:`PostgresRepository` (needs the ``[postgres]``
    extra + ``DATABASE_URL``); anything else — or ANY failure constructing it (missing extra or
    DSN, an unreachable server) — degrades to :class:`SqliteRepository`, so a typo or a down
    database never breaks the app. This is the single line that flips the seam. The failure is
    logged by exception *type* only — never ``str(exc)``, which could carry the DSN password.
    """
    choice = os.environ.get(_ENV_REPOSITORY, "sqlite").strip().lower()
    if choice == "postgres":
        try:
            return PostgresRepository()
        except Exception as exc:  # degrade on ANY failure; never leak the DSN (str(exc))
            _log.warning(
                "PIPEGUARD_REPOSITORY=postgres unavailable (%s); falling back to SQLite.",
                type(exc).__name__,
            )
    path = sqlite_path or os.environ.get(_ENV_SQLITE_PATH, "").strip() or ":memory:"
    return SqliteRepository(path)


__all__ = [
    "PERSIST_SCHEMA_VERSION",
    "CardRow",
    "FindingRow",
    "PostgresRepository",
    "Repository",
    "RunBundle",
    "RunRow",
    "SampleRow",
    "SqliteRepository",
    "database_url_from_env",
    "get_repository",
    "project_events",
    "read_ledger",
    "rebuild_db",
]
