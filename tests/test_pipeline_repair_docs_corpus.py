"""Pipeline-repair docs corpus (P3 §2, design/agent-capabilities.md §2) — offline.

The repair agent now grounds in bayleaf-system + tool docs, not just remediation templates: the
system corpus loads (curated system entries + catalog-derived tool docs), the combined retriever
surfaces a system doc for a system question, and the repair CHAT cites it (stub path, no live API).
"""

from __future__ import annotations

from typing import Any

from api.agent_chat import ask_system_agent
from bayleaf.pipeline_repair.retrieval import (
    RemediationRetriever,
    load_remediation_corpus,
    load_system_corpus,
)


def test_system_corpus_has_curated_and_catalog_tool_docs() -> None:
    corpus = load_system_corpus()
    kinds = {e.kind for e in corpus}
    assert "system_doc" in kinds and "tool_doc" in kinds
    ids = {e.id for e in corpus}
    assert "sys_deterministic_gate" in ids  # a curated system entry
    assert any(e.id.startswith("tool_") for e in corpus)  # derived from PROCESS_CATALOG
    # Tool docs are zero-drift from the catalog — fastp is a catalogued tool.
    assert any(e.category == "tool" and "fastp" in e.title.lower() for e in corpus)


def test_combined_retriever_surfaces_a_system_doc_for_a_system_question() -> None:
    retriever = RemediationRetriever((*load_remediation_corpus(), *load_system_corpus()))
    hits = retriever.retrieve("can the repair agent change the verdict or apply the fix?", top_k=5)
    assert any(h.entry.id == "sys_deterministic_gate" for h in hits)


def test_repair_chat_grounds_in_system_docs(monkeypatch: Any) -> None:
    """A run-independent repair question about the SYSTEM (not a specific signature) grounds in the
    docs corpus — the stub reply cites a system/tool doc. Advisory, offline."""
    monkeypatch.delenv("BAYLEAF_PIPELINE_REPAIR_AGENT", raising=False)  # force the offline stub
    reply = ask_system_agent(
        "pipeline_repair", "does bayleaf actually run the tools, or just compile Nextflow?", {}
    )
    assert reply.generated_by == "stub" and reply.model is None
    cited = {c.ref for c in reply.citations}
    assert "sys_compose_not_execute" in cited  # the compose-vs-execute system doc grounds it
    assert "verdict" not in reply.model_dump()  # advisory only (ADR-0001)
