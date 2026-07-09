"""PostgreSQL adapter for the persistence port (ADR-0003, ADR-0016).

The production sibling of :class:`~pipeguard.persistence.sqlite.SqliteRepository`: it
implements the same :class:`~pipeguard.persistence.repository.Repository` interface over a
Postgres server, so the core still never touches a DB directly and swapping the adapter is a
single factory line (:func:`pipeguard.persistence.get_repository`). Kept behind the optional
``[postgres]`` extra (``psycopg``) and **OFF by default** — mirroring the S3 artifact store —
so the offline demo/tests carry no new dependency and never open a socket.

Dialect notes vs the SQLite adapter (behaviour is identical; only the SQL differs):

1. **Upserts** use ``INSERT ... ON CONFLICT (pk) DO UPDATE`` (Postgres) instead of SQLite's
   ``INSERT OR REPLACE`` — same idempotent-on-identity contract (ADR-0002 replay determinism).
2. **JSON** columns are native ``JSONB`` (queryable), not TEXT — psycopg adapts a dict/list on
   write and returns it parsed on read, so the row mappers read straight through.
3. **Timestamps** are ``TIMESTAMPTZ`` — psycopg adapts an aware ``datetime`` both ways.
4. The table-layout version lives in a tiny ``pipeguard_meta`` row (Postgres has no
   ``PRAGMA user_version``); an incompatible layout is the same loud "delete + rebuild" error.

``psycopg`` is imported lazily inside ``__init__`` so this module imports cleanly without the
extra — the import error only surfaces when a Postgres repository is actually constructed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..identifiers import utc_now
from ..provenance import EntityRef, EventType, ProvenanceEvent
from .records import CardRow, FindingRow, RunBundle, RunRow, SampleRow
from .sqlite import PERSIST_SCHEMA_VERSION

_ENV_DATABASE_URL = "DATABASE_URL"

# Same five projection tables as the SQLite adapter, plus a one-row meta table carrying the
# table-layout version (Postgres has no PRAGMA user_version). JSONB where SQLite used TEXT-JSON;
# TIMESTAMPTZ where SQLite used ISO text.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeguard_meta (
    key    TEXT PRIMARY KEY,
    value  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id           TEXT PRIMARY KEY,
    analysis_run_id  TEXT,
    generated_by     TEXT,
    gate_provenance  JSONB NOT NULL DEFAULT '{}'::jsonb,
    status           TEXT NOT NULL,
    n_samples        INTEGER,
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    schema_version   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS samples (
    run_id           TEXT NOT NULL,
    sample_id        TEXT NOT NULL,
    analysis_run_id  TEXT,
    registered_at    TIMESTAMPTZ,
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
    created_at       TIMESTAMPTZ,
    schema_version   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_cards (
    run_id           TEXT NOT NULL,
    sample_id        TEXT NOT NULL,
    analysis_run_id  TEXT,
    verdict          TEXT NOT NULL,
    generated_by     TEXT,
    content_hash     TEXT,
    created_at       TIMESTAMPTZ,
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
    inputs           JSONB NOT NULL DEFAULT '[]'::jsonb,
    outputs          JSONB NOT NULL DEFAULT '[]'::jsonb,
    payload          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ,
    seq              BIGSERIAL,
    schema_version   INTEGER NOT NULL
);
"""

# Ordered so a truncate respects nothing but the fixed allowlist (no FKs between them).
_TABLES = ("runs", "samples", "findings", "decision_cards", "provenance_events")


def database_url_from_env() -> str | None:
    """The Postgres DSN from ``DATABASE_URL`` (None if unset), used by the factory."""
    import os

    raw = os.environ.get(_ENV_DATABASE_URL, "").strip()
    return raw or None


class PostgresRepository:
    """A Postgres-backed :class:`Repository` — the production projection adapter.

    Pass a DSN (``postgresql://user:pass@host/db``) or leave it to ``DATABASE_URL``. The
    connection is opened in autocommit mode (each upsert commits, matching the SQLite adapter's
    per-write commit) and held for the object's life; call :meth:`close` (or use it as a context
    manager) to release it.
    """

    def __init__(self, dsn: str | None = None) -> None:
        # Lazy import: psycopg is the optional [postgres] extra. Absent -> a clear error here,
        # never at module import, so `import pipeguard.persistence` works without the extra.
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise RuntimeError(
                "PostgresRepository needs the 'postgres' extra: `uv sync --extra postgres` "
                "(installs psycopg). It stays off by default so the offline demo needs no DB."
            ) from exc

        resolved = dsn or database_url_from_env()
        if not resolved:
            raise RuntimeError(
                "PostgresRepository needs a DSN — set DATABASE_URL (or pass dsn=...). "
                "See .env.example / deploy/postgres/."
            )
        # autocommit=True so a single execute is durable immediately, like the SQLite adapter's
        # commit-per-write; dict_row makes rows subscript by column name (like sqlite3.Row).
        # Typed `Any` (like the S3 adapter's boto3 client) so type-checking needs no psycopg stub.
        self._conn: Any = psycopg.connect(resolved, autocommit=True, row_factory=dict_row)
        self.initialize()

    # --- lifecycle -------------------------------------------------------
    def initialize(self) -> None:
        """Create the projection schema and stamp/verify the table-layout version.

        The projection is disposable (ADR-0002): an incompatible stored layout is a loud error
        telling the caller to drop + rebuild, never a silent run against a stale schema.
        """
        self._conn.execute(_SCHEMA)
        row = self._conn.execute(
            "SELECT value FROM pipeguard_meta WHERE key = 'persist_schema_version'"
        ).fetchone()
        stored = row["value"] if row is not None else None
        if stored is not None and stored != PERSIST_SCHEMA_VERSION:
            raise ValueError(
                f"persistence DB has table-layout version {stored}, but this build expects "
                f"{PERSIST_SCHEMA_VERSION}. The projection is disposable — drop the tables and "
                f"rebuild from the ledger (`rebuild-db`)."
            )
        self._conn.execute(
            """INSERT INTO pipeguard_meta (key, value) VALUES ('persist_schema_version', %s)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
            (PERSIST_SCHEMA_VERSION,),
        )

    def reset(self) -> None:
        """Delete every projected row (schema kept) so a rebuild starts clean."""
        # Table names come from the fixed `_TABLES` allowlist, never user input.
        self._conn.execute(f"TRUNCATE {', '.join(_TABLES)}")

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    def __enter__(self) -> PostgresRepository:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- writes (idempotent upserts on identity) -------------------------
    def save_run(self, run: RunRow) -> None:
        self._conn.execute(
            """INSERT INTO runs
               (run_id, analysis_run_id, generated_by, gate_provenance, status,
                n_samples, started_at, completed_at, schema_version)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (run_id) DO UPDATE SET
                 analysis_run_id = EXCLUDED.analysis_run_id,
                 generated_by = EXCLUDED.generated_by,
                 gate_provenance = EXCLUDED.gate_provenance,
                 status = EXCLUDED.status,
                 n_samples = EXCLUDED.n_samples,
                 started_at = EXCLUDED.started_at,
                 completed_at = EXCLUDED.completed_at,
                 schema_version = EXCLUDED.schema_version""",
            (
                run.run_id,
                run.analysis_run_id,
                run.generated_by,
                self._json(run.gate_provenance),
                run.status,
                run.n_samples,
                run.started_at,
                run.completed_at,
                run.schema_version,
            ),
        )

    def save_sample(self, sample: SampleRow) -> None:
        self._conn.execute(
            """INSERT INTO samples
               (run_id, sample_id, analysis_run_id, registered_at, schema_version)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (run_id, sample_id) DO UPDATE SET
                 analysis_run_id = EXCLUDED.analysis_run_id,
                 registered_at = EXCLUDED.registered_at,
                 schema_version = EXCLUDED.schema_version""",
            (
                sample.run_id,
                sample.sample_id,
                sample.analysis_run_id,
                sample.registered_at,
                sample.schema_version,
            ),
        )

    def save_finding(self, finding: FindingRow) -> None:
        self._conn.execute(
            """INSERT INTO findings
               (id, content_hash, analysis_run_id, run_id, sample_id, rule_id,
                gate, severity, signature, created_at, schema_version)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 content_hash = EXCLUDED.content_hash,
                 analysis_run_id = EXCLUDED.analysis_run_id,
                 run_id = EXCLUDED.run_id,
                 sample_id = EXCLUDED.sample_id,
                 rule_id = EXCLUDED.rule_id,
                 gate = EXCLUDED.gate,
                 severity = EXCLUDED.severity,
                 signature = EXCLUDED.signature,
                 created_at = EXCLUDED.created_at,
                 schema_version = EXCLUDED.schema_version""",
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
                finding.created_at,
                finding.schema_version,
            ),
        )

    def save_decision_card(self, card: CardRow) -> None:
        self._conn.execute(
            """INSERT INTO decision_cards
               (run_id, sample_id, analysis_run_id, verdict, generated_by,
                content_hash, created_at, schema_version)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (run_id, sample_id) DO UPDATE SET
                 analysis_run_id = EXCLUDED.analysis_run_id,
                 verdict = EXCLUDED.verdict,
                 generated_by = EXCLUDED.generated_by,
                 content_hash = EXCLUDED.content_hash,
                 created_at = EXCLUDED.created_at,
                 schema_version = EXCLUDED.schema_version""",
            (
                card.run_id,
                card.sample_id,
                card.analysis_run_id,
                card.verdict,
                card.generated_by,
                card.content_hash,
                card.created_at,
                card.schema_version,
            ),
        )

    def append_event(self, event: ProvenanceEvent) -> None:
        """Record one event verbatim; ON CONFLICT on the event id keeps a replay idempotent."""
        self._conn.execute(
            """INSERT INTO provenance_events
               (id, event_type, analysis_run_id, run_id, sample_id, actor,
                inputs, outputs, payload, created_at, schema_version)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 event_type = EXCLUDED.event_type,
                 analysis_run_id = EXCLUDED.analysis_run_id,
                 run_id = EXCLUDED.run_id,
                 sample_id = EXCLUDED.sample_id,
                 actor = EXCLUDED.actor,
                 inputs = EXCLUDED.inputs,
                 outputs = EXCLUDED.outputs,
                 payload = EXCLUDED.payload,
                 created_at = EXCLUDED.created_at,
                 schema_version = EXCLUDED.schema_version""",
            (
                event.id,
                event.event_type.value,
                event.analysis_run_id,
                event.run_id,
                event.sample_id,
                event.actor,
                self._json([e.model_dump(mode="json") for e in event.inputs]),
                self._json([e.model_dump(mode="json") for e in event.outputs]),
                self._json(event.payload),
                event.created_at,
                event.schema_version,
            ),
        )

    # --- reads -----------------------------------------------------------
    def list_runs(self) -> list[RunRow]:
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY started_at NULLS FIRST, run_id"
        ).fetchall()
        return [self._to_run(r) for r in rows]

    def get_run(self, run_id: str) -> RunRow | None:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = %s", (run_id,)).fetchone()
        return self._to_run(row) if row is not None else None

    def list_samples(self, run_id: str | None = None) -> list[SampleRow]:
        return [self._to_sample(r) for r in self._select("samples", run_id)]

    def list_findings(self, run_id: str | None = None) -> list[FindingRow]:
        return [self._to_finding(r) for r in self._select("findings", run_id)]

    def list_decision_cards(self, run_id: str | None = None) -> list[CardRow]:
        return [self._to_card(r) for r in self._select("decision_cards", run_id)]

    def list_events(self, run_id: str | None = None) -> list[ProvenanceEvent]:
        return [self._to_event(r) for r in self._select("provenance_events", run_id)]

    def get_run_bundle(self, run_id: str) -> RunBundle:
        return RunBundle(
            run=self.get_run(run_id),
            samples=self.list_samples(run_id),
            findings=self.list_findings(run_id),
            cards=self.list_decision_cards(run_id),
            events=self.list_events(run_id),
        )

    # --- helpers ---------------------------------------------------------
    @staticmethod
    def _json(value: Any) -> Any:
        """Wrap a dict/list so psycopg writes it as JSONB (parsed back to dict/list on read)."""
        from psycopg.types.json import Jsonb

        return Jsonb(value)

    def _select(self, table: str, run_id: str | None) -> list[Any]:
        """Ordered fetch from a fixed table, optionally scoped to one run.

        Insertion order is preserved by `seq` on events (a BIGSERIAL) and by the ledger's own
        deterministic ids elsewhere; the table name is drawn from a fixed allowlist, never
        user input.
        """
        if table not in _TABLES:
            raise ValueError(f"unknown table {table!r}")
        order = "seq" if table == "provenance_events" else "run_id, sample_id"
        # Fall back to run_id ordering for tables without a sample_id column.
        if table in ("runs",):
            order = "started_at NULLS FIRST, run_id"
        elif table == "findings":
            order = "created_at NULLS FIRST, id"
        if run_id is None:
            rows: list[Any] = self._conn.execute(
                f"SELECT * FROM {table} ORDER BY {order}"
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT * FROM {table} WHERE run_id = %s ORDER BY {order}", (run_id,)
            ).fetchall()
        return rows

    @staticmethod
    def _dt(value: Any) -> datetime | None:
        # psycopg returns an aware datetime for TIMESTAMPTZ; pass None through.
        return value if isinstance(value, datetime) else None

    def _to_run(self, row: dict[str, Any]) -> RunRow:
        return RunRow(
            run_id=row["run_id"],
            analysis_run_id=row["analysis_run_id"],
            generated_by=row["generated_by"],
            gate_provenance=row["gate_provenance"] or {},
            status=row["status"],
            n_samples=row["n_samples"],
            started_at=self._dt(row["started_at"]),
            completed_at=self._dt(row["completed_at"]),
            schema_version=row["schema_version"],
        )

    def _to_sample(self, row: dict[str, Any]) -> SampleRow:
        return SampleRow(
            run_id=row["run_id"],
            sample_id=row["sample_id"],
            analysis_run_id=row["analysis_run_id"],
            registered_at=self._dt(row["registered_at"]),
            schema_version=row["schema_version"],
        )

    def _to_finding(self, row: dict[str, Any]) -> FindingRow:
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
            created_at=self._dt(row["created_at"]),
            schema_version=row["schema_version"],
        )

    def _to_card(self, row: dict[str, Any]) -> CardRow:
        return CardRow(
            run_id=row["run_id"],
            sample_id=row["sample_id"],
            analysis_run_id=row["analysis_run_id"],
            verdict=row["verdict"],
            generated_by=row["generated_by"],
            content_hash=row["content_hash"],
            created_at=self._dt(row["created_at"]),
            schema_version=row["schema_version"],
        )

    def _to_event(self, row: dict[str, Any]) -> ProvenanceEvent:
        return ProvenanceEvent(
            id=row["id"],
            event_type=EventType(row["event_type"]),
            analysis_run_id=row["analysis_run_id"],
            run_id=row["run_id"],
            sample_id=row["sample_id"],
            actor=row["actor"],
            inputs=[EntityRef.model_validate(x) for x in (row["inputs"] or [])],
            outputs=[EntityRef.model_validate(x) for x in (row["outputs"] or [])],
            payload=row["payload"] or {},
            created_at=self._dt(row["created_at"]) or utc_now(),
            schema_version=row["schema_version"],
        )
