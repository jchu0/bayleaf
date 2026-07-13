"""Advisory QC-triage agent + its knowledge corpus and retrieval seam (ADR-0009/0012).

Advisory only and OFF the deterministic critical path (ADR-0001): the agent narrates a
likely cause and next action for a *flagged* card and never sets or overrides a verdict.
Public entry point is :func:`triage_card`; the corpus/retriever are exposed so a future
embedding/pgvector backend can replace the keyword scorer behind the same interface.
"""

from .agent import (
    QC_TRIAGE_AGENT,
    ClaudeTriageAgent,
    StubTriageAgent,
    TriageAgent,
    ask_agent,
    get_triage_agent,
    triage_card,
)
from .models import AgentReply, KnowledgeEntry, TriageCitation, TriageNote
from .retrieval import (
    KeywordRetriever,
    RetrievalHit,
    Retriever,
    load_knowledge_corpus,
)

__all__ = [
    "QC_TRIAGE_AGENT",
    "AgentReply",
    "ClaudeTriageAgent",
    "KeywordRetriever",
    "KnowledgeEntry",
    "RetrievalHit",
    "Retriever",
    "StubTriageAgent",
    "TriageAgent",
    "TriageCitation",
    "TriageNote",
    "ask_agent",
    "get_triage_agent",
    "load_knowledge_corpus",
    "triage_card",
]
