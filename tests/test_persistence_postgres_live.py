"""LIVE Postgres integration test for the persistence + feedback adapters (ADR-0016).

The offline suite (``test_persistence.py``) can only pin the Postgres seam's *guarantees*
(default is SQLite, a missing extra/DSN degrades, the SQL string declares the right DDL) — it
never runs a single statement against a real server, so a genuine dialect bug (a wrong ON
CONFLICT target, a TIMESTAMPTZ that reads back in the server's zone, a missing ``seq`` order)
would survive it. This module closes that gap by exercising :class:`PostgresRepository` and
:class:`PostgresFeedbackStore` against an actual Postgres.

**Safe in CI / offline by construction** — mirroring the discipline in ``test_artifacts_s3.py``
(never touch a real remote unless explicitly armed): a module-level ``importorskip`` drops the
whole file when the optional ``[postgres]`` extra is absent, and the ``pg_dsn`` fixture *probes*
the server and :func:`pytest.skip`\\ s (never fails/errors) when nothing is reachable. So with no
Postgres the module SKIPS; it only asserts when a live server answers.

Bring one up and run it against it::

    docker compose -f deploy/postgres/docker-compose.yml up -d
    uv sync --extra postgres
    DATABASE_URL=postgresql://bayleaf:bayleaf@localhost:5432/bayleaf \\
        uv run pytest tests/test_persistence_postgres_live.py -v
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

# The whole module needs psycopg; without the [postgres] extra there is nothing to test — skip
# the file rather than error, exactly like test_artifacts_s3 tolerates an absent boto3.
pytest.importorskip("psycopg")

from api.feedback_store import PostgresFeedbackStore
from api.share_store import PostgresShareStore
from bayleaf import (
    EventLedger,
    SqliteRepository,
    Verdict,
    load_run,
    rebuild_db,
    run_gate,
)
from bayleaf.persistence.postgres import PostgresRepository
from bayleaf.persistence.repository import Repository
from bayleaf.provenance import EntityRef, EventType, ProvenanceEvent
from bayleaf.synthesis import StubSynthesizer

DATA = Path(__file__).resolve().parent.parent / "data" / "mock_run_01"

# The compose default (deploy/postgres/docker-compose.yml); DATABASE_URL overrides it, so a live
# run can point at whatever host port the container is mapped to.
_DEFAULT_DSN = "postgresql://bayleaf:bayleaf@localhost:5432/bayleaf"


def _dsn() -> str:
    """Resolve the DSN from ``DATABASE_URL``, falling back to the compose default."""
    return os.environ.get("DATABASE_URL", "").strip() or _DEFAULT_DSN


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    """The DSN of a reachable Postgres, or SKIP the test.

    Probes the server with a short-lived connection so an offline/CI machine (no server on the
    DSN) skips cleanly instead of erroring. The exception is reported by *type only* — never
    ``str(exc)``, which can carry the DSN password (the same discretion feedback_store uses when
    it degrades)."""
    import psycopg

    dsn = _dsn()
    try:
        # connect_timeout bounds the probe so a firewalled host skips promptly, not after a hang.
        with psycopg.connect(dsn, connect_timeout=3):
            pass
    except Exception as exc:  # unreachable server / bad creds / no DB -> SKIP, don't fail
        pytest.skip(f"no reachable Postgres for the live test ({type(exc).__name__})")
    return dsn


def _dump(repo: Repository) -> dict[str, list[dict[str, object]]]:
    """Order-stable JSON snapshot of every projection table, for cross-adapter equality.

    Adapted from ``test_persistence._dump`` but typed to the ``Repository`` port so the SAME
    snapshot works for both the SQLite and Postgres adapters — that is what makes a byte-for-byte
    ``==`` a real parity assertion across backends."""
    return {
        "runs": [r.model_dump(mode="json") for r in repo.list_runs()],
        "samples": [s.model_dump(mode="json") for s in repo.list_samples()],
        "findings": [f.model_dump(mode="json") for f in repo.list_findings()],
        "cards": [c.model_dump(mode="json") for c in repo.list_decision_cards()],
        "events": [e.model_dump(mode="json") for e in repo.list_events()],
    }


def _ledger_for_demo(path: Path) -> Path:
    """Run the gate on the pinned demo into a file-backed ledger at ``path``; return the path."""
    ledger = EventLedger(path=path)
    run_gate(load_run(DATA), synthesizer=StubSynthesizer(), ledger=ledger)
    return path


# --- parity: a Postgres projection is byte-identical to the SQLite one ------------------------


def test_postgres_projection_matches_sqlite(pg_dsn: str, tmp_path: Path) -> None:
    """Rebuild ONE authoritative ledger into both adapters; the projections must be identical.

    This is the load-bearing test: an identical ``_dump`` across backends proves the two recent
    review fixes actually hold against a real server —
      1. **UTC-normalized reads**: every TIMESTAMPTZ comes back with a ``+00:00`` offset (Postgres
         hands them out in the session zone; ``_dt`` re-normalizes), matching SQLite's always-UTC
         ISO text — otherwise the ``started_at``/``created_at`` strings would differ.
      2. **Insertion-order reads**: rows come back in ledger order via the ``seq`` BIGSERIAL
         (SQLite gets this free from ``rowid``) — otherwise samples/findings/cards/events could
         reorder on a backend swap and the list equality would fail.
    """
    ledger_path = _ledger_for_demo(tmp_path / "run.events.jsonl")

    sqlite_repo = SqliteRepository(":memory:")
    rebuild_db(ledger_path, sqlite_repo)

    pg_repo = PostgresRepository(pg_dsn)
    rebuild_db(ledger_path, pg_repo)  # reset=True: a clean, deterministic rebuild every run

    sqlite_dump = _dump(sqlite_repo)
    pg_dump = _dump(pg_repo)
    assert pg_dump == sqlite_dump

    # Spot-check the guarantees the equality rides on, so a failure message is legible. pydantic's
    # JSON mode renders a UTC datetime with a trailing "Z"; a Postgres read that came back in a
    # non-UTC session zone would render an offset like "-07:00" and never reach here (it would have
    # broken the equality above) — so the "Z" is a direct witness of the _dt UTC normalization.
    assert all(r["started_at"].endswith("Z") for r in pg_dump["runs"] if r["started_at"])
    assert [c["sample_id"] for c in pg_dump["cards"]] == [
        c["sample_id"] for c in sqlite_dump["cards"]
    ]
    verdicts = {c["sample_id"]: c["verdict"] for c in pg_dump["cards"]}
    assert verdicts == {
        "S1": Verdict.PROCEED.value,
        "S2": Verdict.PROCEED.value,
        "S3": Verdict.PROCEED.value,
        "S4": Verdict.ESCALATE.value,
        "S5": Verdict.HOLD.value,
    }
    assert len(pg_dump["events"]) == 16  # 1 + 5 + 4 + 5 + 1, like the offline scenario

    sqlite_repo.close()
    pg_repo.close()


def test_postgres_replay_is_idempotent(pg_dsn: str, tmp_path: Path) -> None:
    """Folding the SAME ledger in a second time (WITHOUT reset) is a no-op.

    ``reset=False`` is deliberate: it does NOT truncate first, so the second pass relies purely on
    the ``INSERT ... ON CONFLICT (pk) DO UPDATE`` upserts to keep the projection unchanged. A
    replay that duplicated rows (wrong/missing conflict target) would fail this; a plain
    reset+rebuild would hide it."""
    ledger_path = _ledger_for_demo(tmp_path / "run.events.jsonl")
    pg_repo = PostgresRepository(pg_dsn)

    rebuild_db(ledger_path, pg_repo)  # reset=True: clean baseline
    snapshot = _dump(pg_repo)

    rebuild_db(ledger_path, pg_repo, reset=False)  # replay via upserts only
    assert _dump(pg_repo) == snapshot

    pg_repo.close()


# --- feedback telemetry: a real Postgres round-trip ------------------------------------------


def _truncate_feedback(dsn: str) -> None:
    """Empty the feedback table so a rerun starts clean (the table name is a fixed literal)."""
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("TRUNCATE feedback")


def test_postgres_feedback_round_trips(pg_dsn: str) -> None:
    """Append a decision + a product record, then read them back faithfully.

    The records are shaped like the ones ``api/main.submit_feedback`` actually stores (server
    fields ``id``/``received_at``/``schema_version``/``origin`` + the validated body + ``context``)
    so this exercises the real JSONB round-trip: the full record rides in the ``record`` column and
    must come back ``==`` the dict that went in. ``received_at`` is staggered so ``read_all``'s
    ``ORDER BY received_at, id`` is deterministic (decision before product)."""
    # Construct the store FIRST — its __init__ creates the `feedback` table (CREATE TABLE IF NOT
    # EXISTS); truncating before that would hit an UndefinedTable on a fresh database.
    store = PostgresFeedbackStore(pg_dsn)
    _truncate_feedback(pg_dsn)

    decision: dict[str, object] = {
        "target": "decision",
        "source": "decision-card",
        "signal": "disagree",
        "reason_code": "threshold_too_strict",
        "kind": None,
        "message": "The Q30 hold felt too strict for this run",
        "context": {
            "run_id": "mock_run_01",
            "sample_id": "S5",
            "verdict": "hold",
            "gate": "qc",
            "rule_ids": ["qc.q30"],
            "card_content_hash": None,
            "route": "/runs/mock_run_01",
            "screen": "Decision cards",
        },
        "id": "live-test-decision-0001",
        "schema_version": 1,
        "received_at": "2026-07-09T10:00:00+00:00",
        "app_version": "0.1.0",
        "origin": "synthetic",
    }
    product: dict[str, object] = {
        "target": "product",
        "source": "product-fab",
        "signal": None,
        "reason_code": None,
        "kind": "idea",
        "message": "A per-run export button would help",
        "context": {
            "run_id": None,
            "sample_id": None,
            "verdict": None,
            "gate": None,
            "rule_ids": [],
            "card_content_hash": None,
            "route": "/",
            "screen": "Overview",
        },
        "id": "live-test-product-0002",
        "schema_version": 1,
        "received_at": "2026-07-09T11:00:00+00:00",
        "app_version": "0.1.0",
        "origin": "unknown",
    }

    store.append(decision)
    store.append(product)

    assert store.read_all() == [decision, product]

    # Idempotent by id (ON CONFLICT DO NOTHING): re-appending the same records adds nothing.
    store.append(decision)
    assert store.read_all() == [decision, product]

    _truncate_feedback(pg_dsn)  # leave the table clean for the next run


# --- share egress audit: a real Postgres round-trip (ADR-0018 D3) ----------------------------


def _truncate_share(dsn: str) -> None:
    """Empty the share_events table so a rerun starts clean (the table name is a fixed literal)."""
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("TRUNCATE share_events")


def _share_event(run_id: str, n: int) -> ProvenanceEvent:
    """A DATA_EXPORTED event shaped like the one ``api.main.share_run`` records."""
    h = f"hash{n}"
    return ProvenanceEvent(
        event_type=EventType.DATA_EXPORTED,
        run_id=run_id,
        actor="human:b.chen",
        created_at=datetime(2026, 7, 11, 12, n, 0, tzinfo=timezone.utc),
        outputs=[EntityRef(entity_type="share_bundle", id=h, content_hash=h)],
        payload={"policy_id": "safe-harbor-style-v1", "n_rows": n, "origin": "contrived"},
    )


def test_postgres_share_store_round_trips(pg_dsn: str) -> None:
    """Append DATA_EXPORTED events, then read them back per-run faithfully.

    Exercises the real JSONB + TIMESTAMPTZ round-trip: the full ProvenanceEvent rides in the
    ``record`` column and must come back ``==`` the event that went in (a dialect bug — wrong
    ON CONFLICT target, a TZ that reads back in the server's zone — would fail this, where the
    offline suite can't). ``for_run`` filters by run_id and orders oldest-first; the id is the
    idempotency key (ON CONFLICT DO NOTHING)."""
    # Construct FIRST so __init__ creates share_events (CREATE TABLE IF NOT EXISTS) before TRUNCATE.
    store = PostgresShareStore(pg_dsn)
    _truncate_share(pg_dsn)

    a1, b1, a2 = _share_event("RUN-A", 1), _share_event("RUN-B", 2), _share_event("RUN-A", 3)
    store.append(a1)
    store.append(b1)
    store.append(a2)

    got = [e.model_dump(mode="json") for e in store.for_run("RUN-A")]
    assert got == [a1.model_dump(mode="json"), a2.model_dump(mode="json")]  # oldest-first, filtered
    assert len(store.for_run("RUN-B")) == 1
    assert store.for_run("RUN-NONE") == []

    # Idempotent by id: re-appending the same event adds no row.
    store.append(a1)
    assert len(store.for_run("RUN-A")) == 2

    _truncate_share(pg_dsn)  # leave the table clean for the next run
