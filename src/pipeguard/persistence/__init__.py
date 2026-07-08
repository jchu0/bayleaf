"""Persistence layer: the relational projection of the event ledger (Phase 2).

The append-only JSONL ledger is authoritative; this package is the *rebuildable
projection* of it (ADR-0002), reached only through the :class:`Repository` port
(ADR-0003) so the core never touches a DB directly. `SqliteRepository` is the
default adapter (stdlib `sqlite3`, no new dependency); `project_events` maps the
event stream onto rows; `rebuild_db` replays a ledger file into a fresh DB.
"""

from .projector import project_events
from .records import CardRow, FindingRow, RunBundle, RunRow, SampleRow
from .replay import read_ledger, rebuild_db
from .repository import Repository
from .sqlite import PERSIST_SCHEMA_VERSION, SqliteRepository

__all__ = [
    "PERSIST_SCHEMA_VERSION",
    "CardRow",
    "FindingRow",
    "Repository",
    "RunBundle",
    "RunRow",
    "SampleRow",
    "SqliteRepository",
    "project_events",
    "read_ledger",
    "rebuild_db",
]
