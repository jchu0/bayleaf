"""System-agents chat endpoints (design/system-agents-chat.md) — off-gate product surface.

A run-independent chat with a system agent (pipeline-repair / archivist): send a message, list
your sessions, read one, archive/delete (VIEW-SCOPED soft-deletes — the record is retained in the
store for ML). Advisory only (ADR-0001): a chat never re-enters the deterministic gate and carries
no verdict/confidence. Sessions are scoped to the acting actor.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.agent_chat import ask_system_agent
from api.auth import Actor, current_actor
from api.chat import (
    SYSTEM_AGENTS,
    ChatMessage,
    ChatSendRequest,
    ChatSendResponse,
    ChatSession,
)
from api.chat_store import get_chat_store
from bayleaf.identifiers import new_id

router = APIRouter(prefix="/api/agents", tags=["agent_chat"])


def _load_owned(session_id: str, actor: Actor) -> ChatSession:
    """Load a session owned by the acting actor, else 404 (never leak another user's chat)."""
    record = get_chat_store().get(session_id)
    if record is None or record.get("actor_id") != actor.id:
        raise HTTPException(status_code=404, detail=f"Unknown chat session '{session_id}'")
    return ChatSession.from_record(record)


@router.get("")
def list_system_agents() -> list[dict[str, str]]:
    """The system agents available in the chat panel (id + display label)."""
    return [{"id": aid, "label": label} for aid, label in SYSTEM_AGENTS.items()]


@router.get("/chats")
def list_my_chats(
    include_archived: bool = False,
    actor: Actor = Depends(current_actor),
) -> list[ChatSession]:
    """The acting actor's chat sessions (newest last). Excludes deleted always, and archived unless
    ``include_archived`` — but both remain in the store (soft-delete)."""
    rows = get_chat_store().list(actor_id=actor.id)
    keep = {"active", "archived"} if include_archived else {"active"}
    return [ChatSession.from_record(r) for r in rows if r.get("status") in keep]


@router.get("/chats/{session_id}")
def get_chat(session_id: str, actor: Actor = Depends(current_actor)) -> ChatSession:
    return _load_owned(session_id, actor)


@router.post("/chats/{session_id}/archive")
def archive_chat(session_id: str, actor: Actor = Depends(current_actor)) -> ChatSession:
    session = _load_owned(session_id, actor)
    session.status = "archived"
    get_chat_store().update(session.to_record())
    return session


@router.post("/chats/{session_id}/restore")
def restore_chat(session_id: str, actor: Actor = Depends(current_actor)) -> ChatSession:
    session = _load_owned(session_id, actor)
    session.status = "active"
    get_chat_store().update(session.to_record())
    return session


@router.delete("/chats/{session_id}")
def delete_chat(session_id: str, actor: Actor = Depends(current_actor)) -> ChatSession:
    """VIEW-SCOPED soft-delete: flips status to 'deleted'; the record is RETAINED for ML."""
    session = _load_owned(session_id, actor)
    session.status = "deleted"
    get_chat_store().update(session.to_record())
    return session


@router.post("/{agent_id}/chat")
def send_message(
    agent_id: str,
    body: ChatSendRequest,
    actor: Actor = Depends(current_actor),
) -> ChatSendResponse:
    """Send a message to a system agent; persists the user turn + the advisory agent turn.

    Creates a session when ``session_id`` is absent. Requires an authenticated actor (the permissive
    dev floor) because a send can incur a live API call; cost stays gated by the agent's env flag.
    """
    if agent_id not in SYSTEM_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown system agent '{agent_id}'")

    store = get_chat_store()
    context_refs: dict[str, Any] = body.context_refs or {}

    if body.session_id:
        session = _load_owned(body.session_id, actor)
        if session.agent_id != agent_id:
            raise HTTPException(status_code=409, detail="Session belongs to a different agent")
        if context_refs:
            session.context_refs = {**session.context_refs, **context_refs}
        create = False
    else:
        session = ChatSession(
            session_id=new_id("chat"),
            actor_id=actor.id,
            agent_id=agent_id,
            title=body.message[:60],
            context_refs=context_refs,
        )
        create = True

    user_msg = ChatMessage(id=new_id("msg"), role="user", content=body.message)
    session.messages.append(user_msg)
    # Ground + answer (stub-first; live only if the agent's env flag is set). Advisory (ADR-0001).
    reply = ask_system_agent(agent_id, body.message, session.context_refs)
    session.messages.append(reply)
    session.updated_at = reply.ts

    store.create(session.to_record()) if create else store.update(session.to_record())
    return ChatSendResponse(session=session, reply=reply)
