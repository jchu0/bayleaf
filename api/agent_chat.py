"""Advisory chat over the system agents (pipeline-repair / archivist) — OFF the gate.

The one place the chat surface's agent turn is produced (design/system-agents-chat.md). It mirrors
the QC-triage `ask` discipline for a run-independent question:

  1. **Ground deterministically first** — retrieve from the agent's own corpus/data. The grounding
     + the citations come from the retriever/rules, NEVER the LLM, so provenance survives even on
     the live path (the model only phrases the prose).
  2. **Stub-first ($0, ADR-0006)** — with the agent's env flag OFF, return a grounded,
     NON-fabricated answer explicitly framed as retrieval, with the deterministic citations.
  3. **Live Claude only when the agent's flag is set** — `BAYLEAF_PIPELINE_REPAIR_AGENT=claude` /
     `BAYLEAF_ARCHIVIST_AGENT=claude`. Any API error / refusal / empty output degrades to the stub.

Advisory only (ADR-0001): the reply carries no verdict/confidence; the agent answers, rules decide.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from api.chat import ChatCitation, ChatMessage
from bayleaf.identifiers import new_id

_DATA = Path(__file__).resolve().parent.parent / "data"

# Per-agent live-path config, reusing the SAME env flags the rest of the app uses so `=claude`
# turns chat live too. (flag env, model env, default model, system-prompt persona).
_AGENT_CFG: dict[str, tuple[str, str, str, str]] = {
    "pipeline_repair": (
        "BAYLEAF_PIPELINE_REPAIR_AGENT",
        "BAYLEAF_PIPELINE_REPAIR_MODEL",
        "claude-opus-4-8",
        "You are bayleaf's pipeline-repair assistant. Answer the operator's question about "
        "recurring pipeline issues and their remediations, grounded ONLY in the retrieved "
        "knowledge below. Be conservative and hedge; cite nothing the knowledge doesn't support; "
        "never claim to apply a fix, and never state or restate a verdict.",
    ),
    "archivist": (
        "BAYLEAF_ARCHIVIST_AGENT",
        "BAYLEAF_ARCHIVIST_MODEL",
        "claude-haiku-4-5-20251001",
        "You are bayleaf's archivist assistant. Answer the operator's organizational/historical "
        "question grounded ONLY in the run digest below. Report numbers from the digest verbatim; "
        "invent nothing; never state or restate a verdict.",
    ),
}

_ASK_MAX_TOKENS = 2048  # free-text answers run long; a small cap silently truncated (see triage)


# --- per-agent deterministic grounding ------------------------------------------------------


def _repair_grounding(
    question: str, context_refs: dict[str, Any]
) -> tuple[str, list[ChatCitation]]:
    """Retrieve remediation-corpus entries for the question — pipeline-repair's real corpus."""
    from bayleaf.pipeline_repair.retrieval import RemediationRetriever

    hits = RemediationRetriever.from_default_corpus().retrieve(question, top_k=3)
    citations = [
        ChatCitation(kind="knowledge", ref=h.entry.id, title=h.entry.title, score=h.score)
        for h in hits
    ]
    context = "\n".join(f"- {h.entry.title}: {h.entry.summary}" for h in hits)
    return context, citations


def _archive_grounding(
    question: str, context_refs: dict[str, Any]
) -> tuple[str, list[ChatCitation]]:
    """Ground the archivist chat: one run's digest when a run is named, else the cross-run historic
    aggregate (P3 — read-only DB retrieval with a run-dir-derivation fallback,
    design/agent-capabilities.md §1)."""
    run_id = str(context_refs.get("run_id") or "").strip()
    if not run_id or not (_DATA / run_id / "SampleSheet.csv").exists():
        # No specific run → answer organizational/historical questions over the whole run history.
        from api.archivist_retrieval import historic_grounding

        return historic_grounding(question)
    from api.archivist import archive_digest, build_run_input_from_dir

    digest = archive_digest([build_run_input_from_dir(_DATA / run_id)])
    citations = [ChatCitation(kind="run", ref=run_id, title=digest.summary[:80])]
    citations += [
        ChatCitation(kind="signature", ref=s.signature, title=s.title)
        for s in digest.recurring_signatures
    ]
    sig_lines = "\n".join(f"- {s.title} ({s.count}x)" for s in digest.recurring_signatures)
    context = f"Run {run_id} digest: {digest.summary}\nRecurring signatures:\n{sig_lines}".strip()
    return context, citations


_GROUNDERS: dict[str, Callable[[str, dict[str, Any]], tuple[str, list[ChatCitation]]]] = {
    "pipeline_repair": _repair_grounding,
    "archivist": _archive_grounding,
}


# --- answer producers -----------------------------------------------------------------------


def _stub_answer(question: str, context: str) -> str:
    """A grounded, NON-fabricated answer (AI off): surface the retrieved grounding, framed as
    retrieval — not generated prose (ADR-0006 honest fallback)."""
    if context:
        return (
            "AI assistance is off, so this is not a generated answer — it surfaces the grounded "
            f"knowledge that bears on your question:\n{context}\n\nEnable the agent (its "
            "BAYLEAF_*_AGENT=claude flag) for a written answer; the citations below are exact."
        )
    return (
        "AI assistance is off and no grounding matched your question. For the archivist, name a "
        "run (context_refs.run_id); for pipeline-repair, ask about a recurring issue. Or enable "
        "the agent (BAYLEAF_*_AGENT=claude) for a written answer."
    )


def _claude_answer(agent_id: str, question: str, context: str, model: str) -> str | None:
    """Live Claude prose grounded in `context`. Returns None on ANY error / refusal / empty output
    so the caller degrades to the grounded stub — never a crash, never fabricated provenance."""
    _, _, _, system = _AGENT_CFG[agent_id]
    try:
        import anthropic

        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass
        client = anthropic.Anthropic()
        user = (
            f"Operator question:\n{question}\n\n"
            f"Retrieved grounding (answer only from this):\n{context or '(no grounding matched)'}"
        )
        resp = client.messages.create(
            model=model,
            max_tokens=_ASK_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if resp.stop_reason == "refusal":  # life-science work can trip classifiers
            return None
        text = next((b.text for b in resp.content if b.type == "text"), None)
        return text or None
    except Exception:
        return None


def ask_system_agent(
    agent_id: str, question: str, context_refs: dict[str, Any] | None = None
) -> ChatMessage:
    """Produce the advisory agent turn for a chat message.

    Grounds deterministically, then answers stub-first (live Claude only when the agent's env flag
    is set, degrading to the stub on any failure). Citations are deterministic regardless of path.
    """
    refs = context_refs or {}
    grounder = _GROUNDERS[agent_id]  # KeyError = a programming error (router validates agent_id)
    context, citations = grounder(question, refs)

    flag_env, model_env, default_model, _ = _AGENT_CFG[agent_id]
    live = os.environ.get(flag_env, "stub").strip().lower() == "claude"
    generated_by, model, answer = "stub", None, _stub_answer(question, context)
    if live:
        model = os.environ.get(model_env, default_model)
        prose = _claude_answer(agent_id, question, context, model)
        if prose is not None:
            generated_by, answer = "claude", prose
        else:
            model = None  # degraded to the stub; don't claim a model authored it

    return ChatMessage(
        id=new_id("msg"),
        role="agent",
        content=answer,
        citations=citations,
        generated_by=generated_by,
        model=model,
    )
