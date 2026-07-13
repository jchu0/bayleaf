"""Cache-through for rule-derived QC-triage notes (off the gate).

Wraps :func:`bayleaf.triage.triage_card` with a persistent cache (:mod:`api.triage_cache_store`):
the note is generated once per stable card signature + agent identity, then served from the cache on
every repeat request (e.g. navigating away and back), so the live Claude path isn't re-called for an
identical result. Each note is **saved + logged** in the backend, not regenerated per request.

Advisory + off the gate (ADR-0001): caching never re-enters the deterministic gate or sets a
verdict. Cache policy is honest about failures — a note is cached only when the note the agent
produced matches the agent that was SELECTED, so a transient live-API degradation-to-stub is NOT
cached under the live key (it retries on the next request rather than pinning a fallback forever).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from api.triage_cache_store import get_triage_cache_store, triage_cache_key
from bayleaf.models import DecisionCard, Verdict
from bayleaf.triage import TriageNote, get_triage_agent, triage_card
from bayleaf.triage.models import TRIAGE_CORPUS_VERSION

_log = logging.getLogger(__name__)


def get_or_create_triage(run_id: str, card: DecisionCard) -> TriageNote | None:
    """The cached triage note for a card: served from the backend cache on a hit, else generated,
    saved, and logged. ``None`` for a clean/PROCEED card (nothing to triage — never cached)."""
    if not card.findings or card.verdict is Verdict.PROCEED:
        return None

    agent = get_triage_agent()
    model = getattr(agent, "model", None) if agent.name == "claude" else None
    key = triage_cache_key(
        run_id=run_id,
        sample_id=card.sample_id,
        signatures=[f.signature for f in card.findings],
        agent=agent.name,
        model=model,
        corpus_version=TRIAGE_CORPUS_VERSION,
    )
    store = get_triage_cache_store()

    hit = store.get(key)
    if hit is not None:
        _log.info("triage cache HIT run=%s sample=%s key=%s", run_id, card.sample_id, key)
        return TriageNote.model_validate(hit["note"])

    note = triage_card(card, agent=agent)
    # Cache only a note the SELECTED agent actually produced: if a live agent degraded to the stub
    # (generated_by != agent.name), don't pin that transient fallback under the live key — retry.
    if note is not None and note.generated_by == agent.name:
        store.put(
            {
                "cache_key": key,
                "run_id": run_id,
                "sample_id": card.sample_id,
                "generated_by": note.generated_by,
                "model": note.model,
                "corpus_version": note.corpus_version,
                "addresses_signatures": note.addresses_signatures,
                "note": note.model_dump(mode="json"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _log.info(
            "triage cache MISS→stored run=%s sample=%s by=%s key=%s",
            run_id,
            card.sample_id,
            note.generated_by,
            key,
        )
    return note
