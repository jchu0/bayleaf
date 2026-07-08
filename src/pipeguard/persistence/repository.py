"""The persistence port (ADR-0003) — a DB-agnostic repository interface.

The core never touches a database directly (ADR-0003): it speaks to this
:class:`Repository` protocol and a concrete adapter is injected at the edge
(`SqliteRepository` today, a Postgres adapter later). The interface is
deliberately small — it stores and reads back the **projection** of the event
ledger (ADR-0002), nothing more; it is not a general ORM.

Two seams use it:

1. :func:`pipeguard.persistence.project_events` writes a stream of
   :class:`~pipeguard.provenance.ProvenanceEvent` into whichever adapter is
   passed (both the live `run_gate` path and `rebuild_db` go through it, so the
   projection is identical regardless of how it was produced).
2. Read methods back the API/dashboard.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..provenance import ProvenanceEvent
from .records import CardRow, FindingRow, RunBundle, RunRow, SampleRow


@runtime_checkable
class Repository(Protocol):
    """A store for the ledger's relational projection (runs/samples/findings/
    cards/events). Adapters must make writes idempotent on a record's identity so
    replaying the same event twice is a no-op (ADR-0002 rebuild determinism)."""

    # --- lifecycle -------------------------------------------------------
    def initialize(self) -> None:
        """Create the projection schema if it does not exist (idempotent)."""
        ...

    def reset(self) -> None:
        """Clear every projected row so the DB can be rebuilt from scratch.

        The relational store is disposable (ADR-0002); `reset` + a replay makes a
        rebuild a pure function of the ledger.
        """
        ...

    # --- writes (idempotent upserts on identity) -------------------------
    def save_run(self, run: RunRow) -> None: ...
    def save_sample(self, sample: SampleRow) -> None: ...
    def save_finding(self, finding: FindingRow) -> None: ...
    def save_decision_card(self, card: CardRow) -> None: ...
    def append_event(self, event: ProvenanceEvent) -> None: ...

    # --- reads -----------------------------------------------------------
    def list_runs(self) -> list[RunRow]: ...
    def get_run(self, run_id: str) -> RunRow | None: ...
    def list_samples(self, run_id: str | None = None) -> list[SampleRow]: ...
    def list_findings(self, run_id: str | None = None) -> list[FindingRow]: ...
    def list_decision_cards(self, run_id: str | None = None) -> list[CardRow]: ...
    def list_events(self, run_id: str | None = None) -> list[ProvenanceEvent]: ...
    def get_run_bundle(self, run_id: str) -> RunBundle:
        """Cards + samples + findings + the full provenance trail for one run."""
        ...
