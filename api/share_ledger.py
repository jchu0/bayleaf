"""Append-only ledger for de-identified share/report egress events (ADR-0018 D3).

Every de-identified share that leaves the read-API records a ``DATA_EXPORTED``
:class:`~pipeguard.provenance.ProvenanceEvent` here, so a data-out is auditable in the SAME
provenance vocabulary as the gate's decisions.

Why a SEPARATE ledger from the gate's own :class:`~pipeguard.provenance.EventLedger`: the gate
ledger is a deterministic re-derivation per run (``api.main._evaluate`` is ``@lru_cache``) and must
stay byte-stable and cacheable. A share is the opposite — a live, actor-driven side effect that
must survive both that cache and a process restart. So it lands in its own gitignored JSONL that
``get_run`` merges into the trail at read time. This module never reads, sets, or overrides a
verdict/finding/gate input — it only records that data left the boundary (ADR-0001 holds).

JSONL only (no sqlite/postgres projection yet — a documented seam, mirroring EventLedger's own
"DB projection is Phase 2"). Path via ``PIPEGUARD_SHARE_LEDGER``; default a gitignored repo file.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from pipeguard.provenance import ProvenanceEvent

_ENV_SHARE_LEDGER = "PIPEGUARD_SHARE_LEDGER"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PATH = _REPO_ROOT / "share.events.jsonl"

# Serialize appends within a worker so concurrent shares can't interleave a JSONL line (same
# honest single-worker limit as api.feedback_store; a file lock is the multi-worker seam).
_WRITE_LOCK = threading.Lock()


def _ledger_path() -> Path:
    """Resolve the share-ledger JSONL path (env override → gitignored repo default)."""
    raw = os.environ.get(_ENV_SHARE_LEDGER, "").strip()
    return Path(raw) if raw else _DEFAULT_PATH


def record_share_event(event: ProvenanceEvent) -> ProvenanceEvent:
    """Append one ``DATA_EXPORTED`` event to the gitignored share ledger (creating it if absent)."""
    path = _ledger_path()
    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json() + "\n")
    return event


def share_events(run_id: str) -> list[ProvenanceEvent]:
    """Every recorded share event for ``run_id``, oldest first.

    Tolerant at the boundary (CLAUDE.md data-handling): a missing file → ``[]`` and a
    partial/corrupt line is skipped, not raised — a broken append is a signal, not a crash.
    """
    path = _ledger_path()
    if not path.exists():
        return []
    out: list[ProvenanceEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = ProvenanceEvent.model_validate_json(stripped)
        except ValueError:
            continue  # a partial/corrupt line is tolerated, not fatal
        if event.run_id == run_id:
            out.append(event)
    return out
