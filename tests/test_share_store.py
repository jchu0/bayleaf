"""The pluggable share-egress-audit sink (ADR-0018 D3, ADR-0016) — offline guarantees.

Mirrors ``test_persistence.py``'s discipline for the DATA_EXPORTED share store: it pins the seam's
*guarantees* without a live server — the default is JSONL, a DB adapter round-trips a
``ProvenanceEvent`` exactly, the SQLite projection is byte-identical to the JSONL one, a
misconfigured DB degrades to JSONL instead of crashing the egress-audit path, and a corrupt JSONL
line is tolerated. The genuine Postgres-dialect check lives in ``test_persistence_postgres_live.py``
(skips unless a server is armed).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from api.share_store import (
    JsonlShareStore,
    SqliteShareStore,
    get_share_store,
)
from bayleaf.provenance import EntityRef, EventType, ProvenanceEvent

_T0 = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)


def _event(run_id: str, *, n: int = 0, actor: str = "human:b.chen") -> ProvenanceEvent:
    """A DATA_EXPORTED event with an explicit created_at (n seconds past _T0) for stable order."""
    h = f"hash{n}"
    return ProvenanceEvent(
        event_type=EventType.DATA_EXPORTED,
        run_id=run_id,
        actor=actor,
        created_at=_T0 + timedelta(seconds=n),
        outputs=[EntityRef(entity_type="share_bundle", id=h, content_hash=h)],
        payload={"policy_id": "safe-harbor-style-v1", "n_rows": n, "origin": "contrived"},
    )


def _use_jsonl(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.delenv("BAYLEAF_SHARE_STORE", raising=False)
    monkeypatch.setenv("BAYLEAF_SHARE_PATH", str(tmp_path / "share.events.jsonl"))


def test_jsonl_is_the_default_and_round_trips(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_share_store()
    assert isinstance(store, JsonlShareStore)  # default when no store env is set

    store.append(_event("RUN-A", n=1))
    store.append(_event("RUN-B", n=2))
    store.append(_event("RUN-A", n=3))

    got = store.for_run("RUN-A")
    assert [e.payload["n_rows"] for e in got] == [1, 3]  # oldest-first, filtered to RUN-A
    assert store.for_run("RUN-B") and store.for_run("RUN-NONE") == []
    # A recorded event round-trips as a full ProvenanceEvent (nothing lost to the columns).
    assert got[0].event_type is EventType.DATA_EXPORTED
    assert got[0].outputs[0].content_hash == "hash1"


def test_sqlite_round_trips_and_filters(monkeypatch: Any, tmp_path: Path) -> None:
    store = SqliteShareStore(str(tmp_path / "share.sqlite"))
    for n, run in ((1, "RUN-A"), (2, "RUN-B"), (3, "RUN-A")):
        store.append(_event(run, n=n))
    assert [e.payload["n_rows"] for e in store.for_run("RUN-A")] == [1, 3]
    assert len(store.for_run("RUN-B")) == 1
    assert store.for_run("RUN-NONE") == []


def test_sqlite_projection_matches_jsonl(monkeypatch: Any, tmp_path: Path) -> None:
    # The load-bearing parity test: the SAME events through JSONL and SQLite read back identical.
    _use_jsonl(monkeypatch, tmp_path)
    jsonl = get_share_store()
    sqlite = SqliteShareStore(str(tmp_path / "share.sqlite"))
    events = [_event("RUN-A", n=1), _event("RUN-B", n=2), _event("RUN-A", n=3)]
    for e in events:
        jsonl.append(e)
        sqlite.append(e)
    for run in ("RUN-A", "RUN-B", "RUN-NONE"):
        jl = [e.model_dump(mode="json") for e in jsonl.for_run(run)]
        sl = [e.model_dump(mode="json") for e in sqlite.for_run(run)]
        assert jl == sl, run  # byte-for-byte parity across the two backends


def test_sqlite_reappend_of_same_id_is_idempotent(tmp_path: Path) -> None:
    # A DB adapter keys on the event id (INSERT OR REPLACE), so a re-append is one row, not two.
    store = SqliteShareStore(str(tmp_path / "share.sqlite"))
    e = _event("RUN-A", n=1)
    store.append(e)
    store.append(e)
    assert len(store.for_run("RUN-A")) == 1


def test_postgres_selection_degrades_to_jsonl_without_dsn(monkeypatch: Any, tmp_path: Path) -> None:
    # =postgres with no DATABASE_URL must NOT crash the egress path — it degrades to JSONL.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("BAYLEAF_SHARE_STORE", "postgres")
    monkeypatch.setenv("BAYLEAF_SHARE_PATH", str(tmp_path / "share.events.jsonl"))
    store = get_share_store()
    assert isinstance(store, JsonlShareStore)
    store.append(_event("RUN-A", n=1))  # still writes, via the fallback
    assert len(store.for_run("RUN-A")) == 1


def test_jsonl_tolerates_a_corrupt_line(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_share_store()
    store.append(_event("RUN-A", n=1))
    # Wedge a partial/corrupt line in between (a crashed append) — it is skipped, not fatal.
    path = tmp_path / "share.events.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + '{"partial":\n', encoding="utf-8")
    store.append(_event("RUN-A", n=2))
    assert [e.payload["n_rows"] for e in store.for_run("RUN-A")] == [1, 2]
