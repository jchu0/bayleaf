"""Orchestration: turn a run directory (or RunArtifacts) into DecisionCards.

    load_run ─▶ evaluate_run (rules) ─▶ synthesize each sample ─▶ DecisionCard[]

This is the single entry point the UI calls. Swapping Streamlit for FastAPI
later means calling `run_gate` from a request handler instead of a Streamlit
script — the logic below does not change.
"""

from __future__ import annotations

import os
from pathlib import Path

from .models import DecisionCard, RunArtifacts
from .parsers import load_run
from .rules import evaluate_run
from .runbook import DEFAULT_RUNBOOK, Runbook
from .synthesis import StubSynthesizer, Synthesizer

_VERDICT_ORDER = {"escalate": 0, "rerun": 1, "hold": 2, "proceed": 3}


def get_synthesizer() -> Synthesizer:
    """Select the synthesizer from the environment.

    Defaults to the zero-cost stub. Set `PIPEGUARD_SYNTHESIZER=claude` to use
    live Claude synthesis (requires `anthropic` + credentials). This is the one
    line that flips the whole system from offline to live.
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
) -> list[DecisionCard]:
    """Evaluate every sample and return decision cards, most-urgent first."""
    runbook = runbook or DEFAULT_RUNBOOK
    synthesizer = synthesizer or get_synthesizer()

    findings_by_sample = evaluate_run(artifacts, runbook)
    cards = [
        synthesizer.synthesize(sample_id, findings, artifacts)
        for sample_id, findings in findings_by_sample.items()
    ]
    # Surface the samples that need a human first.
    cards.sort(key=lambda c: (_VERDICT_ORDER.get(c.verdict.value, 9), -c.confidence))
    return cards


def run_gate_from_dir(
    run_dir: str | Path,
    runbook: Runbook | None = None,
    synthesizer: Synthesizer | None = None,
) -> tuple[RunArtifacts, list[DecisionCard]]:
    """Convenience: load a run directory and evaluate it in one call."""
    artifacts = load_run(run_dir)
    return artifacts, run_gate(artifacts, runbook, synthesizer)
