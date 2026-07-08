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
from .persistence import (
    CardRow,
    FindingRow,
    Repository,
    RunBundle,
    RunRow,
    SampleRow,
    SqliteRepository,
    project_events,
    rebuild_db,
)
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
    "CardRow",
    "Category",
    "DecisionCard",
    "EntityRef",
    "EventLedger",
    "EventType",
    "Evidence",
    "Finding",
    "FindingRow",
    "Gate",
    "GateResult",
    "KnowledgeEntry",
    "ProvenanceEvent",
    "Repository",
    "RunArtifacts",
    "RunBundle",
    "RunRow",
    "Runbook",
    "SampleRow",
    "Severity",
    "SourceKind",
    "SqliteRepository",
    "TriageCitation",
    "TriageNote",
    "Verdict",
    "evaluate_run",
    "evaluate_sample",
    "get_synthesizer",
    "get_triage_agent",
    "load_run",
    "project_events",
    "rebuild_db",
    "run_gate",
    "run_gate_from_dir",
    "triage_card",
]
