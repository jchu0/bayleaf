"""The pluggable tool-card library sink (node-author W2, ADR-0016) — offline guarantees.

Mirrors ``test_share_store.py`` / ``test_job_store``'s discipline: it pins the seam's *guarantees*
without a live server — the default is JSONL, the SQLite adapter round-trips an entry exactly, the
SQLite projection is byte-identical to the JSONL one, a misconfigured SQLite path degrades to JSONL
instead of crashing the accept path, and a corrupt JSONL line is tolerated. There is no Postgres
adapter here (the library is small node-local state), so no live-DB test is needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api.library_store import (
    JsonlLibraryStore,
    SqliteLibraryStore,
    get_library_store,
)


def _entry(
    entry_id: str,
    tool: str,
    *,
    n: int = 0,
    status: str = "draft",
    submitted_by: str = "a.rivera",
    version: str = "1.0.0",
) -> dict[str, Any]:
    """A minimal library-entry record with an explicit created_at (n seconds) for stable order."""
    created_at = f"2026-07-11T12:00:{n:02d}+00:00"
    return {
        "id": entry_id,
        "tool": tool,
        "version": version,
        "status": status,
        "submitted_by": submitted_by,
        "created_at": created_at,
        "updated_at": created_at,
        # The embedded proposal is opaque to the store — a small stand-in is enough to prove the
        # full record round-trips losslessly.
        "proposal": {"agent": "node_author", "tool": tool, "advisory": True},
    }


def _use_jsonl(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.delenv("BAYLEAF_LIBRARY_STORE", raising=False)
    monkeypatch.setenv("BAYLEAF_LIBRARY_PATH", str(tmp_path / "library_entries.jsonl"))


def test_jsonl_is_the_default_and_round_trips(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_library_store()
    assert isinstance(store, JsonlLibraryStore)  # default when no store env is set

    store.add(_entry("lib1", "fastp", n=1))
    store.add(_entry("lib2", "mosdepth", n=2))
    store.add(_entry("lib3", "fastp", n=3, status="approved"))

    # get by id round-trips the full record (nothing lost to the index columns).
    got = store.get("lib1")
    assert got is not None and got["tool"] == "fastp"
    assert got["proposal"]["advisory"] is True
    assert store.get("missing") is None

    # list is oldest-first and filterable by tool / status (the two AND together).
    assert [e["id"] for e in store.list()] == ["lib1", "lib2", "lib3"]
    assert [e["id"] for e in store.list(tool="fastp")] == ["lib1", "lib3"]
    assert [e["id"] for e in store.list(status="approved")] == ["lib3"]
    assert [e["id"] for e in store.list(tool="fastp", status="draft")] == ["lib1"]
    assert store.list(tool="nonesuch") == []


def test_sqlite_round_trips_and_filters(tmp_path: Path) -> None:
    store = SqliteLibraryStore(str(tmp_path / "library.sqlite"))
    store.add(_entry("lib1", "fastp", n=1))
    store.add(_entry("lib2", "mosdepth", n=2))
    store.add(_entry("lib3", "fastp", n=3, status="approved"))
    assert [e["id"] for e in store.list(tool="fastp")] == ["lib1", "lib3"]
    assert [e["id"] for e in store.list(status="approved")] == ["lib3"]
    assert store.get("lib2") is not None and store.get("lib2")["tool"] == "mosdepth"
    assert store.get("missing") is None


def test_sqlite_projection_matches_jsonl(monkeypatch: Any, tmp_path: Path) -> None:
    # The load-bearing parity test: the SAME entries through JSONL and SQLite read back identical.
    _use_jsonl(monkeypatch, tmp_path)
    jsonl = get_library_store()
    sqlite = SqliteLibraryStore(str(tmp_path / "library.sqlite"))
    entries = [
        _entry("lib1", "fastp", n=1),
        _entry("lib2", "mosdepth", n=2, status="approved"),
        _entry("lib3", "fastp", n=3),
    ]
    for e in entries:
        jsonl.add(e)
        sqlite.add(e)
    for kwargs in ({}, {"tool": "fastp"}, {"status": "approved"}, {"tool": "nonesuch"}):
        assert jsonl.list(**kwargs) == sqlite.list(**kwargs), kwargs  # byte-for-byte parity


def test_sqlite_reappend_of_same_id_is_idempotent(tmp_path: Path) -> None:
    # The SQLite adapter keys on the entry id (INSERT OR REPLACE), so a re-add is one row, not two.
    store = SqliteLibraryStore(str(tmp_path / "library.sqlite"))
    e = _entry("lib1", "fastp", n=1)
    store.add(e)
    store.add(e)
    assert len(store.list()) == 1


def test_sqlite_degrades_to_jsonl_on_unwritable_path(monkeypatch: Any, tmp_path: Path) -> None:
    # =sqlite pointed at a DB under a nonexistent dir must NOT crash accept — it degrades to JSONL.
    monkeypatch.setenv("BAYLEAF_LIBRARY_STORE", "sqlite")
    monkeypatch.setenv("BAYLEAF_LIBRARY_DB", str(tmp_path / "no" / "such" / "dir" / "x.sqlite"))
    monkeypatch.setenv("BAYLEAF_LIBRARY_PATH", str(tmp_path / "library_entries.jsonl"))
    store = get_library_store()
    assert isinstance(store, JsonlLibraryStore)  # degraded to the file
    store.add(_entry("lib1", "fastp", n=1))  # still writes, via the fallback
    assert len(store.list()) == 1


def test_jsonl_tolerates_a_corrupt_line(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_library_store()
    store.add(_entry("lib1", "fastp", n=1))
    # Wedge a partial/corrupt line in between (a crashed append) — it is skipped, not fatal.
    path = tmp_path / "library_entries.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + '{"partial":\n', encoding="utf-8")
    store.add(_entry("lib2", "mosdepth", n=2))
    assert [e["id"] for e in store.list()] == ["lib1", "lib2"]
