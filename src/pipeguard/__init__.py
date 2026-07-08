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
    Gate,
    GateResult,
    RunArtifacts,
    Severity,
    SourceKind,
    Verdict,
)
from .parsers import load_run
from .provenance import (
    AnalysisRun,
    EntityRef,
    EventLedger,
    EventType,
    ProvenanceEvent,
)
from .rules import evaluate_run, evaluate_sample
from .runbook import DEFAULT_RUNBOOK, Runbook
from .triage import (
    KnowledgeEntry,
    TriageCitation,
    TriageNote,
    get_triage_agent,
    triage_card,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_RUNBOOK",
    "AnalysisRun",
    "Category",
    "DecisionCard",
    "EntityRef",
    "EventLedger",
    "EventType",
    "Evidence",
    "Finding",
    "Gate",
    "GateResult",
    "KnowledgeEntry",
    "ProvenanceEvent",
    "RunArtifacts",
    "Runbook",
    "Severity",
    "SourceKind",
    "TriageCitation",
    "TriageNote",
    "Verdict",
    "evaluate_run",
    "evaluate_sample",
    "get_synthesizer",
    "get_triage_agent",
    "load_run",
    "run_gate",
    "run_gate_from_dir",
    "triage_card",
]
