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
from .notify import NotifyPort, NotifyStatus
from .parsers import load_run
from .persistence import Repository, project_events
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
    repo: Repository | None = None,
    notifier: NotifyPort | None = None,
) -> list[DecisionCard]:
    """Evaluate every sample and return decision cards, most-urgent first.

    Emits the provenance event trail into `ledger` (a throwaway in-memory ledger
    if none is given). Each returned card is anchored to the AnalysisRun via
    `analysis_run_id`.

    If a `repo` (an ADR-0003 :class:`~pipeguard.persistence.Repository` port) is
    passed, the event trail is projected into it once the run completes — through
    the *same* projector that `rebuild_db` uses, so the DB stays a pure projection
    of the ledger. Omit `repo` and nothing is persisted (default flow unchanged).

    If a `notifier` (an ADR-0010 :class:`~pipeguard.notify.NotifyPort`) is passed,
    each finished card is handed to it *after* the run completes — a downstream,
    off-critical-path dispatch (ADR-0001). The port's own policy skips clean
    PROCEED cards, so only actionable cards notify; each real notification emits a
    :attr:`~pipeguard.provenance.EventType.NOTIFICATION_EMITTED` event so the
    dispatch is auditable (ADR-0002). Omit `notifier` (the default) and no
    notification happens and no notify event is emitted — the trail is byte-for-byte
    unchanged. The notifier only consumes finished cards; it never sets or alters a
    verdict (ADR-0001).
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
                            id=finding.id,
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

    # Notify is an OPTIONAL, off-by-default, downstream dispatch (ADR-0010). It runs
    # only when a notifier is injected and strictly AFTER the run is decided, so it is
    # off the deterministic critical path and can never influence a verdict (ADR-0001).
    # The port's own policy skips clean PROCEED cards; only a real notification is
    # recorded, so the trail carries signal (actionable cards), not an all-clear per
    # sample. Each such notification is an auditable event (ADR-0002) whose payload
    # holds only the NotifyResult's non-secret facts — never a token or channel creds.
    if notifier is not None:
        for card in cards:
            result = notifier.notify(card)
            if result.status is NotifyStatus.SKIPPED or result.payload is None:
                continue
            ledger.emit(
                ProvenanceEvent(
                    event_type=EventType.NOTIFICATION_EMITTED,
                    analysis_run_id=arun.id,
                    run_id=artifacts.run_id,
                    sample_id=card.sample_id,
                    inputs=[
                        EntityRef(
                            entity_type="card",
                            id=card.sample_id,
                            content_hash=card.content_hash,
                        )
                    ],
                    outputs=[
                        EntityRef(
                            entity_type="notification",
                            id=card.sample_id,
                            content_hash=result.payload.content_hash,
                        )
                    ],
                    payload={
                        "adapter": result.adapter,
                        "status": result.status.value,
                        "delivered": result.delivered,
                        "verdict": card.verdict.value,
                    },
                )
            )

    # Project the authoritative event trail into the DB when a repository is
    # wired in — after the run completes (and after any notifications are recorded),
    # so the projection mirrors the full log.
    if repo is not None:
        project_events(ledger.events, repo)

    # Surface the samples that need a human first. Stable sort keeps parse order
    # within a verdict (confidence is no longer computed — omitted until grounded).
    cards.sort(key=lambda c: _VERDICT_ORDER.get(c.verdict.value, 9))
    return cards


def run_gate_from_dir(
    run_dir: str | Path,
    runbook: Runbook | None = None,
    synthesizer: Synthesizer | None = None,
    ledger: EventLedger | None = None,
    repo: Repository | None = None,
    notifier: NotifyPort | None = None,
) -> tuple[RunArtifacts, list[DecisionCard]]:
    """Convenience: load a run directory and evaluate it in one call."""
    artifacts = load_run(run_dir)
    return artifacts, run_gate(artifacts, runbook, synthesizer, ledger, repo, notifier)
