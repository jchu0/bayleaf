"""SQLite adapter for the persistence port (ADR-0003).

The default relational projection of the event ledger. `sqlite3` is stdlib, so
this adds no runtime dependency; a Postgres adapter can implement the same
:class:`~pipeguard.persistence.repository.Repository` interface later.

Design notes:

1. **Projection, never authoritative** (ADR-0002). Every row is derived from a
   ledger event; nothing is written here that the log does not already hold.
2. **Idempotent writes.** All upserts use `INSERT OR REPLACE` keyed on the
   record's identity (event id / finding id / run_id / (run_id, sample_id)), so
   replaying the same ledger is a no-op — the payoff behind rebuild determinism.
3. **JSON columns where a row is not indexed on** (`gate_provenance`, and an
   event's `inputs`/`outputs`/`payload`) — kept as text rather than exploded
   into tables the MVP never queries.
4. **UTC storage.** Timestamps are stored as ISO-8601 strings (display-tz is the
   edge's job, per schemas.md convention 2). `rowid` preserves ledger insertion
   order for a deterministic replay of the trail.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from ..identifiers import utc_now
from ..provenance import EntityRef, EventType, ProvenanceEvent
from .records import CardRow, FindingRow, RunBundle, RunRow, SampleRow

# Bump on a breaking change to the *table* layout (distinct from the per-record
# schema_version, which versions the record shape). Stored in PRAGMA user_version.
PERSIST_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id           TEXT PRIMARY KEY,
    analysis_run_id  TEXT,
    generated_by     TEXT,
    gate_provenance  TEXT NOT NULL DEFAULT '{}',  -- JSON
    status           TEXT NOT NULL,
    n_samples        INTEGER,
    started_at       TEXT,                          -- ISO-8601 UTC
    completed_at     TEXT,
    schema_version   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS samples (
    run_id           TEXT NOT NULL,
    sample_id        TEXT NOT NULL,
    analysis_run_id  TEXT,
    registered_at    TEXT,
    schema_version   INTEGER NOT NULL,
    PRIMARY KEY (run_id, sample_id)
);

CREATE TABLE IF NOT EXISTS findings (
    id               TEXT PRIMARY KEY,
    content_hash     TEXT,
    analysis_run_id  TEXT,
    run_id           TEXT,
    sample_id        TEXT,
    rule_id          TEXT,
    gate             TEXT,
    severity         TEXT,
    signature        TEXT,
    created_at       TEXT,
    schema_version   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_cards (
    run_id           TEXT NOT NULL,
    sample_id        TEXT NOT NULL,
    analysis_run_id  TEXT,
    verdict          TEXT NOT NULL,
    generated_by     TEXT,
    content_hash     TEXT,
    created_at       TEXT,
    schema_version   INTEGER NOT NULL,
    PRIMARY KEY (run_id, sample_id)
);

CREATE TABLE IF NOT EXISTS provenance_events (
    id               TEXT PRIMARY KEY,
    event_type       TEXT NOT NULL,
    analysis_run_id  TEXT,
    run_id           TEXT,
    sample_id        TEXT,
    actor            TEXT,
    inputs           TEXT NOT NULL DEFAULT '[]',   -- JSON list[EntityRef]
    outputs          TEXT NOT NULL DEFAULT '[]',   -- JSON list[EntityRef]
    payload          TEXT NOT NULL DEFAULT '{}',   -- JSON
    created_at       TEXT,
    schema_version   INTEGER NOT NULL
);
"""

_TABLES = ("runs", "samples", "findings", "decision_cards", "provenance_events")


def _iso(dt: datetime | None) -> str | None:
    """Serialize a UTC timestamp to ISO-8601 text (None passes through)."""
    return dt.isoformat() if dt is not None else None


def _parse_dt(value: Any) -> datetime | None:
    """Parse ISO-8601 text back to an aware datetime (None passes through)."""
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


class SqliteRepository:
    """A SQLite-backed :class:`Repository` — the default projection adapter.

    Pass a filesystem path for a durable projection or ``":memory:"`` for an
    ephemeral one (tests). The connection is held open for the object's life;
    call :meth:`close` (or use it as a context manager) to release it.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        # str() so a Path is accepted; ":memory:" stays a sentinel, not a file.
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self.initialize()

    # --- lifecycle -------------------------------------------------------
    def initialize(self) -> None:
        """Create the projection schema and stamp the table-layout version.

        On an existing DB, the stored `user_version` is checked before use: the
        projection is disposable (ADR-0002), so an incompatible layout is a loud
        error telling the caller to delete + rebuild-db, not a silent run against
        a stale schema.
        """
        stored = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if stored not in (0, PERSIST_SCHEMA_VERSION):
            raise ValueError(
                f"persistence DB has table-layout version {stored}, but this build "
                f"expects {PERSIST_SCHEMA_VERSION}. The projection is disposable — "
                f"delete the DB and rebuild it from the ledger (`make rebuild-db`)."
            )
        self._conn.executescript(_SCHEMA)
        self._conn.execute(f"PRAGMA user_version = {PERSIST_SCHEMA_VERSION}")
        self._conn.commit()

    def reset(self) -> None:
        """Delete every projected row (schema kept) so a rebuild starts clean."""
        for table in _TABLES:
            # Table name is from the fixed `_TABLES` allowlist, never user input.
            self._conn.execute(f"DELETE FROM {table}")
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    def __enter__(self) -> SqliteRepository:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- writes ----------------------------------------------------------
    def save_run(self, run: RunRow) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, analysis_run_id, generated_by, gate_provenance, status,
                n_samples, started_at, completed_at, schema_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.run_id,
                run.analysis_run_id,
                run.generated_by,
                json.dumps(run.gate_provenance, sort_keys=True),
                run.status,
                run.n_samples,
                _iso(run.started_at),
                _iso(run.completed_at),
                run.schema_version,
            ),
        )
        self._conn.commit()

    def save_sample(self, sample: SampleRow) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO samples
               (run_id, sample_id, analysis_run_id, registered_at, schema_version)
               VALUES (?, ?, ?, ?, ?)""",
            (
                sample.run_id,
                sample.sample_id,
                sample.analysis_run_id,
                _iso(sample.registered_at),
                sample.schema_version,
            ),
        )
        self._conn.commit()

    def save_finding(self, finding: FindingRow) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO findings
               (id, content_hash, analysis_run_id, run_id, sample_id, rule_id,
                gate, severity, signature, created_at, schema_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                finding.id,
                finding.content_hash,
                finding.analysis_run_id,
                finding.run_id,
                finding.sample_id,
                finding.rule_id,
                finding.gate,
                finding.severity,
                finding.signature,
                _iso(finding.created_at),
                finding.schema_version,
            ),
        )
        self._conn.commit()

    def save_decision_card(self, card: CardRow) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO decision_cards
               (run_id, sample_id, analysis_run_id, verdict, generated_by,
                content_hash, created_at, schema_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                card.run_id,
                card.sample_id,
                card.analysis_run_id,
                card.verdict,
                card.generated_by,
                card.content_hash,
                _iso(card.created_at),
                card.schema_version,
            ),
        )
        self._conn.commit()

    def append_event(self, event: ProvenanceEvent) -> None:
        """Record one event verbatim. INSERT OR REPLACE on the event id keeps a
        replay idempotent. Primitive payload values round-trip exactly; a
        non-JSON-native value (datetime/enum) would be stringified via `default=str`
        — fine for the current all-primitive vocabulary, revisit when a richer
        payload lands so the live and replayed paths encode it identically."""
        self._conn.execute(
            """INSERT OR REPLACE INTO provenance_events
               (id, event_type, analysis_run_id, run_id, sample_id, actor,
                inputs, outputs, payload, created_at, schema_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.id,
                event.event_type.value,
                event.analysis_run_id,
                event.run_id,
                event.sample_id,
                event.actor,
                json.dumps([e.model_dump(mode="json") for e in event.inputs]),
                json.dumps([e.model_dump(mode="json") for e in event.outputs]),
                json.dumps(event.payload, default=str),
                _iso(event.created_at),
                event.schema_version,
            ),
        )
        self._conn.commit()

    # --- reads -----------------------------------------------------------
    def list_runs(self) -> list[RunRow]:
        rows = self._conn.execute("SELECT * FROM runs ORDER BY started_at, run_id").fetchall()
        return [self._to_run(r) for r in rows]

    def get_run(self, run_id: str) -> RunRow | None:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._to_run(row) if row is not None else None

    def list_samples(self, run_id: str | None = None) -> list[SampleRow]:
        rows = self._select("samples", run_id)
        return [self._to_sample(r) for r in rows]

    def list_findings(self, run_id: str | None = None) -> list[FindingRow]:
        rows = self._select("findings", run_id)
        return [self._to_finding(r) for r in rows]

    def list_decision_cards(self, run_id: str | None = None) -> list[CardRow]:
        rows = self._select("decision_cards", run_id)
        return [self._to_card(r) for r in rows]

    def list_events(self, run_id: str | None = None) -> list[ProvenanceEvent]:
        rows = self._select("provenance_events", run_id)
        return [self._to_event(r) for r in rows]

    def get_run_bundle(self, run_id: str) -> RunBundle:
        return RunBundle(
            run=self.get_run(run_id),
            samples=self.list_samples(run_id),
            findings=self.list_findings(run_id),
            cards=self.list_decision_cards(run_id),
            events=self.list_events(run_id),
        )

    # --- helpers ---------------------------------------------------------
    def _select(self, table: str, run_id: str | None) -> list[sqlite3.Row]:
        """Ordered fetch from a fixed table, optionally scoped to one run.

        `rowid` order preserves ledger insertion order (deterministic trail). The
        table name is drawn from a fixed allowlist — never user input.
        """
        # `table` is only ever passed a `_TABLES` literal by callers; the guard
        # makes that explicit so the f-string interpolation is never user input.
        if table not in _TABLES:
            raise ValueError(f"unknown table {table!r}")
        if run_id is None:
            return self._conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
        return self._conn.execute(
            f"SELECT * FROM {table} WHERE run_id = ? ORDER BY rowid", (run_id,)
        ).fetchall()

    @staticmethod
    def _to_run(row: sqlite3.Row) -> RunRow:
        return RunRow(
            run_id=row["run_id"],
            analysis_run_id=row["analysis_run_id"],
            generated_by=row["generated_by"],
            gate_provenance=json.loads(row["gate_provenance"]),
            status=row["status"],
            n_samples=row["n_samples"],
            started_at=_parse_dt(row["started_at"]),
            completed_at=_parse_dt(row["completed_at"]),
            schema_version=row["schema_version"],
        )

    @staticmethod
    def _to_sample(row: sqlite3.Row) -> SampleRow:
        return SampleRow(
            run_id=row["run_id"],
            sample_id=row["sample_id"],
            analysis_run_id=row["analysis_run_id"],
            registered_at=_parse_dt(row["registered_at"]),
            schema_version=row["schema_version"],
        )

    @staticmethod
    def _to_finding(row: sqlite3.Row) -> FindingRow:
        return FindingRow(
            id=row["id"],
            content_hash=row["content_hash"],
            analysis_run_id=row["analysis_run_id"],
            run_id=row["run_id"],
            sample_id=row["sample_id"],
            rule_id=row["rule_id"],
            gate=row["gate"],
            severity=row["severity"],
            signature=row["signature"],
            created_at=_parse_dt(row["created_at"]),
            schema_version=row["schema_version"],
        )

    @staticmethod
    def _to_card(row: sqlite3.Row) -> CardRow:
        return CardRow(
            run_id=row["run_id"],
            sample_id=row["sample_id"],
            analysis_run_id=row["analysis_run_id"],
            verdict=row["verdict"],
            generated_by=row["generated_by"],
            content_hash=row["content_hash"],
            created_at=_parse_dt(row["created_at"]),
            schema_version=row["schema_version"],
        )

    @staticmethod
    def _to_event(row: sqlite3.Row) -> ProvenanceEvent:
        return ProvenanceEvent(
            id=row["id"],
            event_type=EventType(row["event_type"]),
            analysis_run_id=row["analysis_run_id"],
            run_id=row["run_id"],
            sample_id=row["sample_id"],
            actor=row["actor"],
            inputs=[EntityRef.model_validate(x) for x in json.loads(row["inputs"])],
            outputs=[EntityRef.model_validate(x) for x in json.loads(row["outputs"])],
            payload=json.loads(row["payload"]),
            created_at=_parse_dt(row["created_at"]) or utc_now(),
            schema_version=row["schema_version"],
        )
