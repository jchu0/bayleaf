"""pipeguard — AI-assisted provenance & QC decision gate for genomics runs.

Framework-agnostic core. The Streamlit MVP and any future FastAPI service both
import from here; nothing in this package depends on a UI framework.
"""

from .engine import get_synthesizer, run_gate, run_gate_from_dir
from .models import (
    Category,
    DecisionCard,
    Evidence,
    Finding,
    RunArtifacts,
    Severity,
    Verdict,
)
from .parsers import load_run
from .rules import evaluate_run, evaluate_sample
from .runbook import DEFAULT_RUNBOOK, Runbook

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_RUNBOOK",
    "Category",
    "DecisionCard",
    "Evidence",
    "Finding",
    "RunArtifacts",
    "Runbook",
    "Severity",
    "Verdict",
    "evaluate_run",
    "evaluate_sample",
    "get_synthesizer",
    "load_run",
    "run_gate",
    "run_gate_from_dir",
]
