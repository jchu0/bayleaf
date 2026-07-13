"""Thin convenience: fetch a run through a store, then run the existing gate.

This wrapper lives in the artifacts package on purpose — so wiring a store into the gate
adds NO code to :mod:`bayleaf.engine`. It is a two-line composition: stage the run to a
local directory via the injected :class:`~bayleaf.artifacts.port.ArtifactStore`, then
hand that directory to the unchanged :func:`bayleaf.engine.run_gate_from_dir`. The store
only decides *where the bytes come from*; the gate's evaluation, provenance trail, and
verdicts are byte-for-byte what they would be if the same directory were passed directly.
"""

from __future__ import annotations

from ..engine import run_gate_from_dir
from ..models import DecisionCard, RunArtifacts
from ..notify import NotifyPort
from ..persistence import Repository
from ..provenance import EventLedger
from ..runbook import Runbook
from ..synthesis import Synthesizer
from .port import ArtifactStore, RunRef


def run_gate_from_store(
    store: ArtifactStore,
    run_ref: RunRef,
    runbook: Runbook | None = None,
    synthesizer: Synthesizer | None = None,
    ledger: EventLedger | None = None,
    repo: Repository | None = None,
    notifier: NotifyPort | None = None,
) -> tuple[RunArtifacts, list[DecisionCard]]:
    """Materialize ``run_ref`` via ``store`` and evaluate it through the existing gate.

    A drop-in for :func:`bayleaf.engine.run_gate_from_dir` that adds a store hop in front:
    ``store.fetch(run_ref)`` returns the local directory, which is then loaded and gated
    exactly as before. All downstream knobs (runbook, synthesizer, ledger, repo, notifier)
    forward unchanged, so the store never alters the decision path (ADR-0001/0003).
    """
    local_dir = store.fetch(run_ref)
    return run_gate_from_dir(local_dir, runbook, synthesizer, ledger, repo, notifier)
