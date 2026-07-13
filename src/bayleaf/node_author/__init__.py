"""Advisory node-authoring agent + its tool-card corpus and retrieval seam (agent #6, T-046).

Advisory only and OFF the deterministic critical path (ADR-0001): given a natural-language request
for a bioinformatics tool, the agent proposes a concrete, HUMAN-REVIEWED builder node — a tool
name, a pinned version, typed input/output ports (each a real ``ARTIFACT_KIND``; unknown kinds are
surfaced as reserved slots, never wired), and suggested locators. It never runs a tool
(compose ≠ execute, ADR-0003) and never sets/overrides a verdict. Public entry point is
:func:`propose_node`; the corpus/retriever are exposed so an on-demand API endpoint (and the
offline tests) can build over the same tool-card corpus, and so a future embedding/pgvector backend
can replace the keyword scorer behind the same interface.
"""

from .agent import (
    NODE_AUTHOR_AGENT,
    ClaudeNodeAuthor,
    NodeAuthorAgent,
    StubNodeAuthor,
    get_node_author_agent,
    propose_node,
)
from .conformance import (
    ConformanceViolation,
    check_conformance,
    is_conformant,
)
from .importer import import_from_nextflow_schema
from .models import (
    ARTIFACT_KINDS,
    NODE_AUTHOR_CORPUS_VERSION,
    PIPELINE_STAGES,
    LocatorSuggestion,
    NodeCitation,
    NodeProposal,
    PortSpec,
    ToolCardEntry,
)
from .retrieval import (
    RetrievalHit,
    Retriever,
    ToolCardRetriever,
    load_tool_card_corpus,
)
from .scaffolds import render_scaffolds

__all__ = [
    "ARTIFACT_KINDS",
    "NODE_AUTHOR_AGENT",
    "NODE_AUTHOR_CORPUS_VERSION",
    "PIPELINE_STAGES",
    "ClaudeNodeAuthor",
    "ConformanceViolation",
    "LocatorSuggestion",
    "NodeAuthorAgent",
    "NodeCitation",
    "NodeProposal",
    "PortSpec",
    "RetrievalHit",
    "Retriever",
    "StubNodeAuthor",
    "ToolCardEntry",
    "ToolCardRetriever",
    "check_conformance",
    "get_node_author_agent",
    "import_from_nextflow_schema",
    "is_conformant",
    "load_tool_card_corpus",
    "propose_node",
    "render_scaffolds",
]
