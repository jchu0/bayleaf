"""API contract for the System-agents chat surface (design/system-agents-chat.md).

Pydantic models for a run-independent conversation with a **system agent** (pipeline-repair /
archivist). These are the wire + storage shapes; :mod:`api.chat_store` persists a ``ChatSession``
(as a JSON document) and :mod:`api.agent_chat` produces the agent turns. Advisory only (ADR-0001):
there is deliberately NO verdict/confidence field anywhere here — the agent answers, the rules
decide. Every persisted field is typed + timestamped (structure-for-ML).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# The system agents reachable from this surface (ADR-0022 taxonomy: cross-run / org-wide advisory).
# QC-triage stays per-run (its own page); node-author stays in the Builder; monitoring is a
# tool-agent on the graph (ADR-0023) — none of those are chat agents here.
SYSTEM_AGENTS: dict[str, str] = {
    "pipeline_repair": "Pipeline repair",
    "archivist": "Archivist",
}

ChatStatus = Literal["active", "archived", "deleted"]
ChatRole = Literal["user", "agent"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatCitation(BaseModel):
    """One traceable reference behind an agent answer — a corpus entry, a run, or a signature.

    Kept separable from the prose (life-science guardrail): a reader traces every answer back to a
    grounded id. ``score`` is a heuristic keyword-overlap value in [0, 1] for retrieval hits (NOT a
    calibrated probability), ``None`` otherwise.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["knowledge", "run", "signature"]
    ref: str = Field(..., description="Corpus id / run id / signature id")
    title: str | None = None
    score: float | None = Field(None, ge=0.0, le=1.0)


class ChatMessage(BaseModel):
    """One turn in a chat session (append-only within a session's ``messages[]``)."""

    id: str
    role: ChatRole
    content: str
    ts: str = Field(default_factory=_utc_now_iso)
    citations: list[ChatCitation] = Field(default_factory=list)
    generated_by: str | None = Field(
        None, description="'stub' | 'claude' for agent turns; None for a user turn"
    )
    model: str | None = Field(None, description="LLM id when generated_by='claude'")


class ChatSession(BaseModel):
    """A run-independent conversation with one system agent. Mutable: messages append and ``status``
    transitions (active → archived → deleted). Archive/delete are VIEW-SCOPED soft-deletes — the
    record is retained in the store for ML (design/system-agents-chat.md)."""

    session_id: str
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    actor_id: str
    agent_id: str
    title: str = ""
    context_refs: dict[str, Any] = Field(default_factory=dict)
    status: ChatStatus = "active"
    messages: list[ChatMessage] = Field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        """The JSON document persisted by :mod:`api.chat_store` (byte-stable, ML-minable)."""
        return self.model_dump(mode="json")

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> ChatSession:
        return cls.model_validate(record)


class ChatSendRequest(BaseModel):
    """Send a message to a system agent. A new session is created when ``session_id`` is absent."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    context_refs: dict[str, Any] | None = Field(
        None, description="Optional grounding hints (e.g. {'run_id': '...'}); non-PII only"
    )


class ChatSendResponse(BaseModel):
    """The agent's reply plus the (created-or-updated) session it belongs to."""

    session: ChatSession
    reply: ChatMessage
