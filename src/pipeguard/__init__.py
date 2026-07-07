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
    "run_gate",
    "run_gate_from_dir",
    "get_synthesizer",
    "load_run",
    "evaluate_run",
    "evaluate_sample",
    "Runbook",
    "DEFAULT_RUNBOOK",
    "DecisionCard",
    "Finding",
    "Evidence",
    "RunArtifacts",
    "Verdict",
    "Severity",
    "Category",
]
