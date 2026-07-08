"""CLI entry point for rebuilding the SQLite projection from a JSONL ledger.

    python -m pipeguard.persistence.rebuild <ledger.jsonl> <db.sqlite>

The reusable functions (`rebuild_db`, `read_ledger`) live in
:mod:`pipeguard.persistence.replay`; this module is a thin argument-parsing shell
around them so the package `__init__` never imports the CLI (no `-m` double-load).
"""

from __future__ import annotations

import argparse

from .replay import rebuild_db
from .sqlite import SqliteRepository


def main(argv: list[str] | None = None) -> int:
    """Parse args, rebuild the projection, and print a one-line summary."""
    parser = argparse.ArgumentParser(
        prog="python -m pipeguard.persistence.rebuild",
        description="Replay a JSONL provenance ledger into a SQLite projection.",
    )
    parser.add_argument("ledger", help="Path to the JSONL event ledger (authoritative log).")
    parser.add_argument("db", help="Path to the SQLite projection to (re)build.")
    args = parser.parse_args(argv)

    with SqliteRepository(args.db) as repo:
        n_events = rebuild_db(args.ledger, repo)
        n_runs = len(repo.list_runs())
        n_cards = len(repo.list_decision_cards())
    print(
        f"Rebuilt {args.db} from {args.ledger}: "
        f"{n_events} event(s) -> {n_runs} run(s), {n_cards} decision card(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
