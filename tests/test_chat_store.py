"""The pluggable System-agents chat-session sink (design/system-agents-chat.md, ADR-0016) — offline.

Pins the seam's guarantees without a live server: JSONL is the default, create/get/list/update
round-trip, list filters AND together, an update appends a message / flips status, the user-facing
archive/delete is a **soft-delete that retains the record** (structure-for-ML), an update of an
unknown id raises, and the SQLite projection is byte-for-byte the same records as JSONL.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api.chat_store import (
    JsonlChatStore,
    SqliteChatStore,
    get_chat_store,
)


def _session(
    sid: str,
    *,
    actor_id: str = "a.rivera",
    agent_id: str = "pipeline_repair",
    status: str = "active",
    updated_at: str = "2026-07-13T12:00:00+00:00",
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "session_id": sid,
        "created_at": "2026-07-13T12:00:00+00:00",
        "updated_at": updated_at,
        "actor_id": actor_id,
        "agent_id": agent_id,
        "title": f"chat {sid}",
        "context_refs": {},
        "status": status,
        "messages": messages or [],
    }


def _use_jsonl(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.delenv("BAYLEAF_CHAT_STORE", raising=False)
    monkeypatch.setenv("BAYLEAF_CHAT_PATH", str(tmp_path / "chat.jsonl"))


def _use_sqlite(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("BAYLEAF_CHAT_STORE", "sqlite")
    monkeypatch.setenv("BAYLEAF_CHAT_DB", str(tmp_path / "chat.sqlite"))


def test_jsonl_is_the_default_and_round_trips(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_chat_store()
    assert isinstance(store, JsonlChatStore)  # default when no store env is set

    store.create(_session("s1"))
    store.create(_session("s2", agent_id="archivist"))
    got = store.get("s1")
    assert got is not None and got["agent_id"] == "pipeline_repair"
    assert store.get("missing") is None


def test_list_filters_and_together(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_chat_store()
    store.create(_session("s1", actor_id="a.rivera", agent_id="pipeline_repair"))
    store.create(_session("s2", actor_id="a.rivera", agent_id="archivist"))
    store.create(_session("s3", actor_id="m.chen", agent_id="pipeline_repair"))

    mine = store.list(actor_id="a.rivera")
    assert {s["session_id"] for s in mine} == {"s1", "s2"}
    mine_repair = store.list(actor_id="a.rivera", agent_id="pipeline_repair")
    assert [s["session_id"] for s in mine_repair] == ["s1"]


def test_update_appends_a_message_and_bumps_updated_at(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_chat_store()
    store.create(_session("s1"))

    rec = store.get("s1")
    assert rec is not None
    rec["messages"].append({"role": "user", "content": "why did S4 fail?"})
    rec["messages"].append({"role": "agent", "content": "barcode mismatch", "citations": []})
    rec["updated_at"] = "2026-07-13T12:05:00+00:00"
    store.update(rec)

    back = store.get("s1")
    assert back is not None
    assert [m["role"] for m in back["messages"]] == ["user", "agent"]
    assert back["updated_at"] == "2026-07-13T12:05:00+00:00"


def test_archive_and_delete_are_soft_retaining_the_record(monkeypatch: Any, tmp_path: Path) -> None:
    """View-scoped soft-delete: status flips, the record STAYS for ML (no hard delete)."""
    _use_jsonl(monkeypatch, tmp_path)
    store = get_chat_store()
    store.create(_session("s1"))

    rec = store.get("s1")
    assert rec is not None
    rec["status"] = "deleted"
    store.update(rec)

    # The user's active view no longer shows it...
    assert store.list(actor_id="a.rivera", status="active") == []
    # ...but the record is retained in the store (mineable for ML).
    still = store.get("s1")
    assert still is not None and still["status"] == "deleted"
    assert store.list(status="deleted")[0]["session_id"] == "s1"


def test_update_unknown_id_raises(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_chat_store()
    try:
        store.update(_session("nope"))
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected KeyError updating an unknown session")


def test_sqlite_projection_matches_jsonl(monkeypatch: Any, tmp_path: Path) -> None:
    """The SQLite adapter stores + returns byte-identical records to the JSONL one."""
    _use_sqlite(monkeypatch, tmp_path)
    store = get_chat_store()
    assert isinstance(store, SqliteChatStore)

    store.create(_session("s1", messages=[{"role": "user", "content": 'hi\nthere "q"'}]))
    rec = store.get("s1")
    assert rec is not None
    rec["messages"].append({"role": "agent", "content": "cited answer", "citations": ["k1"]})
    rec["updated_at"] = "2026-07-13T12:06:00+00:00"
    store.update(rec)

    back = store.get("s1")
    assert back is not None
    assert back["messages"][0]["content"] == 'hi\nthere "q"'  # newline/quote survive intact
    assert [m["role"] for m in back["messages"]] == ["user", "agent"]
    assert [s["session_id"] for s in store.list(actor_id="a.rivera")] == ["s1"]
