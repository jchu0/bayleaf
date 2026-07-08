"""Projection record shapes for the relational DB (ADR-0002).

These are **lean projection rows**, not the rich domain models in
:mod:`pipeguard.models`. The relational DB is a *rebuildable projection of the
event ledger* (ADR-0002), so a projected row can only carry what the ledger
actually records — the `finding.emitted` / `verdict.decided` events snapshot an
entity's id + `content_hash` plus a small typed payload, not the full `Finding`
or `DecisionCard`. Reusing the frozen domain models here would force inventing
`title`/`detail`/`evidence` the ledger never captured, which the data-handling
guardrail forbids ("never invent data"). So each shape mirrors exactly the
fields the projector can derive from an event.

The full domain records (with narration, evidence, gate_results) remain the
in-memory contract produced by `run_gate`; they are reconstructed from the
authoritative ledger, not from this projection.

Related: `docs/data/schemas.md` (Run/Sample/Finding/DecisionCard/ProvenanceEvent),
`docs/data/provenance.md`, `pipeguard.provenance` (the event source).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..identifiers import SCHEMA_VERSION
from ..provenance import ProvenanceEvent


class RunRow(BaseModel):
    """Projected run row — one gate execution over a sequencing run.

    Phase 1 keeps one `AnalysisRun` per run (see `provenance.md` scope note), so
    the sequencing-run key (`run_id`) and its analysis-run anchor
    (`analysis_run_id`) collapse into a single projected row. `gate_provenance`
    is stored as JSON because it is a nested manifest that is never queried on
    directly.
    """

    run_id: str
    analysis_run_id: str | None = None
    generated_by: str | None = None
    gate_provenance: dict[str, Any] = Field(default_factory=dict)
    status: str = "started"  # started | completed | failed
    n_samples: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    schema_version: int = SCHEMA_VERSION


class SampleRow(BaseModel):
    """Projected sample row — a sample registered during a gate execution.

    The `sample.registered` event carries only identity (the intake sheet fields
    in `models.Sample` are not on the ledger yet), so this row is deliberately
    thin; richer sample metadata joins in when `sample.registered` payloads grow.
    """

    run_id: str
    sample_id: str
    analysis_run_id: str | None = None
    registered_at: datetime | None = None
    schema_version: int = SCHEMA_VERSION


class FindingRow(BaseModel):
    """Projected finding row — the ledger snapshot of one immutable finding.

    `content_hash` is preserved verbatim from the `finding.emitted` event so the
    projection carries the same identity as the authoritative record. Fields
    absent from the event (title, detail, evidence, category, suggested_verdict)
    are intentionally not reconstructed here.
    """

    id: str
    content_hash: str | None = None
    analysis_run_id: str | None = None
    run_id: str | None = None
    sample_id: str | None = None
    rule_id: str | None = None
    gate: str | None = None
    severity: str | None = None
    signature: str | None = None
    created_at: datetime | None = None
    schema_version: int = SCHEMA_VERSION


class CardRow(BaseModel):
    """Projected decision-card row — the ledger snapshot of one decision.

    One card per (sample x analysis_run) (schemas.md invariant 4). The
    `verdict.decided` event references the card by `sample_id` and carries its
    `content_hash`, which is preserved here so a rebuilt DB matches the log.
    """

    run_id: str
    sample_id: str
    analysis_run_id: str | None = None
    verdict: str
    generated_by: str | None = None
    content_hash: str | None = None
    created_at: datetime | None = None
    schema_version: int = SCHEMA_VERSION


class RunBundle(BaseModel):
    """Everything the projection knows about one run — the read-side aggregate.

    Returned by :meth:`Repository.get_run_bundle` so a caller (API/dashboard) can
    fetch a run's cards + provenance trail in one hop. `events` is returned in
    ledger (insertion) order so the trail reads as it was emitted.
    """

    run: RunRow | None = None
    samples: list[SampleRow] = Field(default_factory=list)
    findings: list[FindingRow] = Field(default_factory=list)
    cards: list[CardRow] = Field(default_factory=list)
    events: list[ProvenanceEvent] = Field(default_factory=list)
