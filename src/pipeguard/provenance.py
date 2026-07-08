"""The provenance/event seam (ADR-0002).

Every gate execution is an :class:`AnalysisRun`; every meaningful step emits an
append-only :class:`ProvenanceEvent` into an :class:`EventLedger`. The event log
is authoritative — a queryable DB is a rebuildable *projection* of it, and lands
in Phase 2 along with strict-replay determinism. Today the ledger is in-memory
with optional JSONL persistence.

This module is standalone (imports only `identifiers`) so the core data contract
in `models` never depends on the event layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .identifiers import SCHEMA_VERSION, new_id, utc_now


class EventType(str, Enum):
    """The event vocabulary of the decision core (schemas.md)."""

    RUN_REGISTERED = "run.registered"
    SAMPLE_REGISTERED = "sample.registered"
    ANALYSIS_RUN_STARTED = "analysis_run.started"
    ARTIFACT_INGESTED = "artifact.ingested"
    METRIC_PARSED = "metric.parsed"
    FINDING_EMITTED = "finding.emitted"
    VERDICT_DECIDED = "verdict.decided"
    ANALYSIS_RUN_COMPLETED = "analysis_run.completed"
    NOTIFICATION_EMITTED = "notification.emitted"
    TICKET_ACTIONED = "ticket.actioned"
    RESOLUTION_RECORDED = "resolution.recorded"


class EntityRef(BaseModel):
    """A pointer to an entity an event consumed or produced."""

    entity_type: str  # artifact | metric | finding | card | ticket | ...
    id: str
    content_hash: str | None = None  # present for immutable entities (findings, cards)


class AnalysisRun(BaseModel):
    """One gate execution over a run, under pinned versions — the anchor every
    finding/card/event hangs off (schemas.md).

    Phase 1 captures the **gate provenance** (our rule pack, runbook, timestamps).
    The **pipeline provenance** (sarek params_hash / execution_trace) is added in
    Phase 2 with real sarek data.
    """

    id: str = Field(default_factory=lambda: new_id("arun"))
    run_id: str
    generated_by: str = "stub"  # narration provenance
    model: str | None = None
    gate_provenance: dict[str, Any] = Field(default_factory=dict)
    status: str = "started"  # started | completed | failed
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    schema_version: int = SCHEMA_VERSION


class ProvenanceEvent(BaseModel):
    """One append-only entry in the provenance ledger."""

    id: str = Field(default_factory=lambda: new_id("evt"))
    event_type: EventType
    analysis_run_id: str | None = None
    run_id: str | None = None
    sample_id: str | None = None
    actor: str = "system"  # system | rule_engine | agent | human:<id>
    inputs: list[EntityRef] = Field(default_factory=list)
    outputs: list[EntityRef] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    schema_version: int = SCHEMA_VERSION


class EventLedger:
    """Append-only event ledger: in-memory, with optional JSONL persistence.

    The JSONL file (when a path is given) is the authoritative record; the
    in-memory list is a convenience for the current process. A DB projection is
    Phase 2.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._events: list[ProvenanceEvent] = []
        self._path = Path(path) if path is not None else None
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: ProvenanceEvent) -> ProvenanceEvent:
        """Append one event (and persist it if this ledger is file-backed)."""
        self._events.append(event)
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(event.model_dump_json() + "\n")
        return event

    @property
    def events(self) -> list[ProvenanceEvent]:
        return list(self._events)

    def by_type(self, event_type: EventType) -> list[ProvenanceEvent]:
        return [e for e in self._events if e.event_type is event_type]
