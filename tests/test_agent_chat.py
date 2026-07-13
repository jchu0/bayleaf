"""System-agents chat endpoints (design/system-agents-chat.md) — offline (stub agent, no live API).

Pins the surface's guarantees: a send creates a session and persists BOTH turns; the agent turn is
advisory (no verdict/confidence) + cited + stub-generated; sessions are scoped to the acting actor;
archive/delete are view-scoped soft-deletes that retain the record; an unknown agent 404s.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

_A = {"X-Bayleaf-Actor": "a.rivera", "X-Bayleaf-Role": "reviewer"}
_B = {"X-Bayleaf-Actor": "m.chen", "X-Bayleaf-Role": "reviewer"}


@pytest.fixture(autouse=True)
def _isolate_chat_store(monkeypatch: Any, tmp_path: Path) -> None:
    """Point the chat store at a tmp JSONL so tests never touch the repo-root sink."""
    monkeypatch.delenv("BAYLEAF_CHAT_STORE", raising=False)
    monkeypatch.setenv("BAYLEAF_CHAT_PATH", str(tmp_path / "chat.jsonl"))
    # Keep the agents on the offline stub regardless of the caller's shell env.
    monkeypatch.delenv("BAYLEAF_PIPELINE_REPAIR_AGENT", raising=False)
    monkeypatch.delenv("BAYLEAF_ARCHIVIST_AGENT", raising=False)


def _send(agent: str, message: str, headers: dict[str, str], session_id: str | None = None) -> Any:
    body: dict[str, Any] = {"message": message}
    if session_id:
        body["session_id"] = session_id
    return client.post(f"/api/agents/{agent}/chat", json=body, headers=headers)


def test_list_system_agents() -> None:
    r = client.get("/api/agents", headers=_A)
    assert r.status_code == 200
    ids = {a["id"] for a in r.json()}
    assert ids == {"pipeline_repair", "archivist"}


def test_send_creates_session_and_persists_both_turns() -> None:
    r = _send("pipeline_repair", "What causes a recurring barcode mismatch?", _A)
    assert r.status_code == 200
    data = r.json()
    session, reply = data["session"], data["reply"]
    assert [m["role"] for m in session["messages"]] == ["user", "agent"]
    assert reply["role"] == "agent"
    assert reply["generated_by"] == "stub" and reply["model"] is None  # offline default
    assert reply["citations"]  # pipeline-repair grounds in its remediation corpus
    assert "verdict" not in reply and "confidence" not in reply  # advisory only (ADR-0001)

    # Persisted + retrievable by the owner.
    got = client.get(f"/api/agents/chats/{session['session_id']}", headers=_A)
    assert got.status_code == 200
    assert len(got.json()["messages"]) == 2


def test_continue_an_existing_session() -> None:
    first = _send("pipeline_repair", "first question", _A).json()["session"]
    sid = first["session_id"]
    again = _send("pipeline_repair", "a follow-up", _A, session_id=sid).json()["session"]
    assert again["session_id"] == sid
    assert [m["role"] for m in again["messages"]] == ["user", "agent", "user", "agent"]


def test_sessions_are_scoped_to_the_actor() -> None:
    sid = _send("archivist", "mine", _A).json()["session"]["session_id"]
    # Actor B cannot see or load actor A's session.
    assert client.get("/api/agents/chats", headers=_B).json() == []
    assert client.get(f"/api/agents/chats/{sid}", headers=_B).status_code == 404
    assert [s["session_id"] for s in client.get("/api/agents/chats", headers=_A).json()] == [sid]


def test_archive_and_delete_are_soft_and_retain_the_record() -> None:
    sid = _send("pipeline_repair", "q", _A).json()["session"]["session_id"]

    client.post(f"/api/agents/chats/{sid}/archive", headers=_A)
    assert client.get("/api/agents/chats", headers=_A).json() == []  # hidden from active view
    incl = client.get("/api/agents/chats?include_archived=true", headers=_A).json()
    assert [s["session_id"] for s in incl] == [sid]  # still there

    client.delete(f"/api/agents/chats/{sid}", headers=_A)
    # Deleted from every list view, but the record is retained (owner can still load it directly).
    assert client.get("/api/agents/chats?include_archived=true", headers=_A).json() == []
    assert client.get(f"/api/agents/chats/{sid}", headers=_A).json()["status"] == "deleted"


def test_unknown_agent_404() -> None:
    assert _send("synthesizer", "hi", _A).status_code == 404


def test_send_to_wrong_agent_for_session_409() -> None:
    sid = _send("pipeline_repair", "q", _A).json()["session"]["session_id"]
    assert _send("archivist", "q2", _A, session_id=sid).status_code == 409
