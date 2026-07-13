"""Advisory pipeline-repair agent + its remediation corpus and retrieval seam (agent #2).

Advisory only and OFF the deterministic critical path (ADR-0001): given a recurring issue
signature from the monitoring rollup, the agent proposes a concrete, HUMAN-REVIEWED pipeline
remediation and never edits a pipeline or sets/overrides a verdict. Public entry point is
:func:`propose_repair`; the corpus/retriever + the :func:`assemble_recurring_signatures`
helper are exposed so the on-demand API endpoint (and the offline tests) can build the agent's
input from the same signature-counting logic the monitoring view uses, and so a future
embedding/pgvector backend can replace the keyword scorer behind the same interface.
"""

from .agent import (
    PIPELINE_REPAIR_AGENT,
    ClaudeRepairAgent,
    RepairAgent,
    StubRepairAgent,
    get_repair_agent,
    propose_repair,
)
from .models import (
    PipelineStage,
    RecurringSignature,
    RemediationEntry,
    RepairCitation,
    RepairProposal,
    assemble_recurring_signatures,
    recurring_signature,
)
from .retrieval import (
    RemediationRetriever,
    RetrievalHit,
    Retriever,
    load_remediation_corpus,
    load_system_corpus,
)

__all__ = [
    "PIPELINE_REPAIR_AGENT",
    "ClaudeRepairAgent",
    "PipelineStage",
    "RecurringSignature",
    "RemediationEntry",
    "RemediationRetriever",
    "RepairAgent",
    "RepairCitation",
    "RepairProposal",
    "RetrievalHit",
    "Retriever",
    "StubRepairAgent",
    "assemble_recurring_signatures",
    "get_repair_agent",
    "load_remediation_corpus",
    "load_system_corpus",
    "propose_repair",
    "recurring_signature",
]
