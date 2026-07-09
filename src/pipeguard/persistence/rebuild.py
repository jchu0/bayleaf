"""CLI entry point for rebuilding the relational projection from a JSONL ledger.

    python -m pipeguard.persistence.rebuild <ledger.jsonl> [<db.sqlite>]

The target adapter is chosen by :func:`pipeguard.persistence.get_repository` — SQLite by default
(a ``db`` path, or in-memory if omitted), or Postgres when ``PIPEGUARD_REPOSITORY=postgres`` +
``DATABASE_URL`` are set (ADR-0016), in which case ``db`` is ignored. The reusable functions
(`rebuild_db`, `read_ledger`) live in :mod:`pipeguard.persistence.replay`; this module is a thin
argument-parsing shell so the package `__init__` never imports the CLI (no `-m` double-load).
"""

from __future__ import annotations

import argparse
import contextlib

from . import get_repository
from .replay import rebuild_db


def main(argv: list[str] | None = None) -> int:
    """Parse args, rebuild the projection, and print a one-line summary."""
    parser = argparse.ArgumentParser(
        prog="python -m pipeguard.persistence.rebuild",
        description="Replay a JSONL provenance ledger into the relational projection.",
    )
    parser.add_argument("ledger", help="Path to the JSONL event ledger (authoritative log).")
    parser.add_argument(
        "db",
        nargs="?",
        help="SQLite projection path. Omit for Postgres (PIPEGUARD_REPOSITORY=postgres + DSN).",
    )
    args = parser.parse_args(argv)

    # get_repository honours PIPEGUARD_REPOSITORY (postgres|sqlite) + degrades to SQLite on any
    # failure, so a Postgres typo/outage never aborts a rebuild — it just rebuilds SQLite instead.
    with contextlib.closing(get_repository(sqlite_path=args.db)) as repo:
        n_events = rebuild_db(args.ledger, repo)
        n_runs = len(repo.list_runs())
        n_cards = len(repo.list_decision_cards())
    print(
        f"Rebuilt {type(repo).__name__} from {args.ledger}: "
        f"{n_events} event(s) -> {n_runs} run(s), {n_cards} decision card(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
