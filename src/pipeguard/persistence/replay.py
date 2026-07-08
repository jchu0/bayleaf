"""Replay a JSONL event ledger into the relational projection (ADR-0002).

This is the ADR-0002 payoff as a library call: the DB is disposable and rebuilt
deterministically from the append-only event log. The thin CLI wrapper lives in
:mod:`pipeguard.persistence.rebuild` (`python -m pipeguard.persistence.rebuild`);
keeping the reusable functions here means the package `__init__` never imports
the CLI module, so running it via `-m` does not double-import.

The ledger is the same one-JSON-line-per-event file written by
:class:`~pipeguard.provenance.EventLedger`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ..provenance import ProvenanceEvent
from .projector import project_events
from .repository import Repository


def read_ledger(ledger_path: str | Path) -> Iterator[ProvenanceEvent]:
    """Yield events from a JSONL ledger in file (= emission) order.

    Blank lines are skipped tolerantly; a malformed line raises, because the
    ledger is our own authoritative record and silent data loss there would
    defeat the point of replay determinism.
    """
    path = Path(ledger_path)
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            yield ProvenanceEvent.model_validate_json(line)


def rebuild_db(ledger_path: str | Path, repo: Repository, *, reset: bool = True) -> int:
    """Replay a JSONL event ledger into `repo`, returning the events projected.

    By default the projection is cleared first (`reset=True`) so the rebuild is a
    pure function of the ledger — the same input always yields the same DB, and
    rebuilding twice is idempotent. Pass `reset=False` to fold a ledger into an
    existing projection (upserts still keep it idempotent per record identity).
    """
    repo.initialize()
    if reset:
        repo.reset()
    return project_events(read_ledger(ledger_path), repo)
