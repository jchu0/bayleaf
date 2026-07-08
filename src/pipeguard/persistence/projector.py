"""Project a stream of provenance events into the relational store (ADR-0002).

This is the one place that turns the authoritative event log into the queryable
projection. Both seams go through it, which is what makes the DB a *pure
function of the ledger*:

1. the live `run_gate` path (when a repository is injected), and
2. `rebuild_db`, replaying a JSONL ledger from scratch.

Only the current event vocabulary is projected (`analysis_run.started/completed`,
`sample.registered`, `finding.emitted`, `verdict.decided`); reserved event types
(`run.registered`, `artifact.ingested`, `metric.parsed`, ticket/resolution) are
still recorded verbatim in `provenance_events` — they gain projected rows when
their producers land in Phase 2. Nothing is invented: a row carries only what the
event snapshotted.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..provenance import EventType, ProvenanceEvent
from .records import CardRow, FindingRow, RunRow, SampleRow
from .repository import Repository


def project_events(events: Iterable[ProvenanceEvent], repo: Repository) -> int:
    """Replay `events` into `repo`, returning the number of events processed.

    Every event is appended verbatim (the full trail is preserved); the subset in
    the projected vocabulary additionally upserts a run/sample/finding/card row.
    Idempotent by construction: rows are keyed on stable ids, so replaying the
    same events twice yields the same projection.

    A run's summary fields (`status`, `n_samples`, `completed_at`) are known only
    at `analysis_run.completed`, so run rows are accumulated across the stream and
    flushed once at the end — the same final state whether replayed live or from
    a file. Every row's `schema_version` is taken from its source event, so the
    projection is a pure function of the *ledger* (not the current code version).
    """
    runs: dict[str, RunRow] = {}
    count = 0
    for event in events:
        count += 1
        repo.append_event(event)
        et = event.event_type

        if et is EventType.ANALYSIS_RUN_STARTED and event.run_id:
            run = runs.setdefault(
                event.run_id, RunRow(run_id=event.run_id, schema_version=event.schema_version)
            )
            run.analysis_run_id = event.analysis_run_id
            run.generated_by = _as_str(event.payload.get("generated_by"))
            gate_prov = event.payload.get("gate_provenance")
            run.gate_provenance = gate_prov if isinstance(gate_prov, dict) else {}
            run.status = "started"
            run.started_at = event.created_at

        elif et is EventType.ANALYSIS_RUN_COMPLETED and event.run_id:
            run = runs.setdefault(
                event.run_id, RunRow(run_id=event.run_id, schema_version=event.schema_version)
            )
            run.analysis_run_id = run.analysis_run_id or event.analysis_run_id
            run.status = _as_str(event.payload.get("status")) or "completed"
            run.completed_at = event.created_at
            n_samples = event.payload.get("n_samples")
            if isinstance(n_samples, int):
                run.n_samples = n_samples

        elif et is EventType.SAMPLE_REGISTERED and event.run_id and event.sample_id:
            repo.save_sample(
                SampleRow(
                    run_id=event.run_id,
                    sample_id=event.sample_id,
                    analysis_run_id=event.analysis_run_id,
                    registered_at=event.created_at,
                    schema_version=event.schema_version,
                )
            )

        elif et is EventType.FINDING_EMITTED:
            ref = event.outputs[0] if event.outputs else None
            if ref is not None:
                repo.save_finding(
                    FindingRow(
                        id=ref.id,
                        content_hash=ref.content_hash,
                        analysis_run_id=event.analysis_run_id,
                        run_id=event.run_id,
                        sample_id=event.sample_id,
                        rule_id=_as_str(event.payload.get("rule_id")),
                        gate=_as_str(event.payload.get("gate")),
                        severity=_as_str(event.payload.get("severity")),
                        signature=_as_str(event.payload.get("signature")),
                        created_at=event.created_at,
                        schema_version=event.schema_version,
                    )
                )

        elif et is EventType.VERDICT_DECIDED and event.run_id:
            ref = event.outputs[0] if event.outputs else None
            # The card is keyed by sample_id in the ledger (ref.id == sample_id).
            sample_id = event.sample_id or (ref.id if ref is not None else None)
            verdict = _as_str(event.payload.get("verdict"))
            if sample_id and verdict:
                repo.save_decision_card(
                    CardRow(
                        run_id=event.run_id,
                        sample_id=sample_id,
                        analysis_run_id=event.analysis_run_id,
                        verdict=verdict,
                        generated_by=_as_str(event.payload.get("generated_by")),
                        content_hash=ref.content_hash if ref is not None else None,
                        created_at=event.created_at,
                        schema_version=event.schema_version,
                    )
                )

    for run in runs.values():
        repo.save_run(run)
    return count


def _as_str(value: object) -> str | None:
    """Coerce a payload value to str for a text column (None passes through)."""
    return None if value is None else str(value)
