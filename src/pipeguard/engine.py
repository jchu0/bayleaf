"""Orchestration: turn a run directory (or RunArtifacts) into DecisionCards.

    load_run ─▶ evaluate_run (rules) ─▶ synthesize each sample ─▶ DecisionCard[]

As it runs, the gate emits an append-only trail of provenance events into an
:class:`EventLedger` (ADR-0002): one AnalysisRun per gate execution, then
sample.registered / finding.emitted / verdict.decided per sample, bracketed by
analysis_run.started / .completed. Pass a ledger to capture (and persist) them;
omit it and the events are still emitted into a throwaway in-memory ledger.

This is the single entry point the UI calls. Swapping Streamlit for FastAPI later
means calling `run_gate` from a request handler instead of a Streamlit script.
"""

from __future__ import annotations

import os
from pathlib import Path

from .identifiers import utc_now
from .models import RULE_PACK_VERSION, DecisionCard, RunArtifacts
from .parsers import load_run
from .provenance import AnalysisRun, EntityRef, EventLedger, EventType, ProvenanceEvent
from .rules import evaluate_run
from .runbook import DEFAULT_RUNBOOK, Runbook
from .synthesis import StubSynthesizer, Synthesizer

_VERDICT_ORDER = {"escalate": 0, "rerun": 1, "hold": 2, "proceed": 3}


def get_synthesizer() -> Synthesizer:
    """Select the synthesizer from the environment.

    Defaults to the zero-cost stub. Set `PIPEGUARD_SYNTHESIZER=claude` to use live
    Claude synthesis (requires `anthropic` + credentials). This is the one line
    that flips the whole system from offline to live.
    """
    choice = os.environ.get("PIPEGUARD_SYNTHESIZER", "stub").strip().lower()
    if choice == "claude":
        from .synthesis import ClaudeSynthesizer

        return ClaudeSynthesizer()
    return StubSynthesizer()


def run_gate(
    artifacts: RunArtifacts,
    runbook: Runbook | None = None,
    synthesizer: Synthesizer | None = None,
    ledger: EventLedger | None = None,
) -> list[DecisionCard]:
    """Evaluate every sample and return decision cards, most-urgent first.

    Emits the provenance event trail into `ledger` (a throwaway in-memory ledger
    if none is given). Each returned card is anchored to the AnalysisRun via
    `analysis_run_id`.
    """
    runbook = runbook or DEFAULT_RUNBOOK
    synthesizer = synthesizer or get_synthesizer()
    ledger = ledger if ledger is not None else EventLedger()

    arun = AnalysisRun(
        run_id=artifacts.run_id,
        generated_by=synthesizer.name,
        gate_provenance={
            "rule_pack_version": RULE_PACK_VERSION,
            "runbook_metrics": [t.metric for t in runbook.qc_thresholds],
        },
    )
    ledger.emit(
        ProvenanceEvent(
            event_type=EventType.ANALYSIS_RUN_STARTED,
            analysis_run_id=arun.id,
            run_id=artifacts.run_id,
            payload={"generated_by": arun.generated_by, "gate_provenance": arun.gate_provenance},
        )
    )

    findings_by_sample = evaluate_run(artifacts, runbook)
    cards: list[DecisionCard] = []
    for sample_id, findings in findings_by_sample.items():
        ledger.emit(
            ProvenanceEvent(
                event_type=EventType.SAMPLE_REGISTERED,
                analysis_run_id=arun.id,
                run_id=artifacts.run_id,
                sample_id=sample_id,
            )
        )
        for finding in findings:
            ledger.emit(
                ProvenanceEvent(
                    event_type=EventType.FINDING_EMITTED,
                    analysis_run_id=arun.id,
                    run_id=artifacts.run_id,
                    sample_id=sample_id,
                    actor="rule_engine",
                    outputs=[
                        EntityRef(
                            entity_type="finding",
                            id=finding.rule_id,
                            content_hash=finding.content_hash,
                        )
                    ],
                    payload={
                        "rule_id": finding.rule_id,
                        "gate": finding.gate.value,
                        "severity": finding.severity.value,
                        "signature": finding.signature,
                    },
                )
            )

        card = synthesizer.synthesize(sample_id, findings, artifacts)
        card.analysis_run_id = arun.id
        ledger.emit(
            ProvenanceEvent(
                event_type=EventType.VERDICT_DECIDED,
                analysis_run_id=arun.id,
                run_id=artifacts.run_id,
                sample_id=sample_id,
                actor="rule_engine",
                outputs=[
                    EntityRef(entity_type="card", id=card.sample_id, content_hash=card.content_hash)
                ],
                payload={"verdict": card.verdict.value, "generated_by": card.generated_by},
            )
        )
        cards.append(card)

    arun.status = "completed"
    arun.completed_at = utc_now()
    ledger.emit(
        ProvenanceEvent(
            event_type=EventType.ANALYSIS_RUN_COMPLETED,
            analysis_run_id=arun.id,
            run_id=artifacts.run_id,
            payload={"status": arun.status, "n_samples": len(cards)},
        )
    )

    # Surface the samples that need a human first. Stable sort keeps parse order
    # within a verdict (confidence is no longer computed — omitted until grounded).
    cards.sort(key=lambda c: _VERDICT_ORDER.get(c.verdict.value, 9))
    return cards


def run_gate_from_dir(
    run_dir: str | Path,
    runbook: Runbook | None = None,
    synthesizer: Synthesizer | None = None,
    ledger: EventLedger | None = None,
) -> tuple[RunArtifacts, list[DecisionCard]]:
    """Convenience: load a run directory and evaluate it in one call."""
    artifacts = load_run(run_dir)
    return artifacts, run_gate(artifacts, runbook, synthesizer, ledger)
