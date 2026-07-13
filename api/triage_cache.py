"""Cache-through for rule-derived QC-triage notes (off the gate).

Thin wrapper over the generic :func:`api.agent_output_cache.cache_through`: the note is generated
once per stable card signature + agent identity, then served from the backend on repeat requests
(navigating away and back doesn't regenerate or re-call Claude), and every note is saved + logged.

Advisory + off the gate (ADR-0001): caching never re-enters the deterministic gate or sets a
verdict. The cache is skipped honestly for a live→stub degrade (``expected_by``), so a transient API
blip doesn't pin a fallback under the live key.
"""

from __future__ import annotations

from api.agent_output_cache import cache_through
from bayleaf.models import DecisionCard, Verdict
from bayleaf.triage import TriageNote, get_triage_agent, triage_card
from bayleaf.triage.models import TRIAGE_CORPUS_VERSION


def get_or_create_triage(run_id: str, card: DecisionCard) -> TriageNote | None:
    """The cached triage note for a card; ``None`` for a clean/PROCEED card (never cached)."""
    if not card.findings or card.verdict is Verdict.PROCEED:
        return None
    agent = get_triage_agent()
    model = getattr(agent, "model", None) if agent.name == "claude" else None
    return cache_through(
        namespace="triage",
        key_inputs={
            "run_id": run_id,
            "sample_id": card.sample_id,
            "signatures": [f.signature for f in card.findings],
            "agent": agent.name,
            "model": model,
            "corpus_version": TRIAGE_CORPUS_VERSION,
        },
        generate=lambda: triage_card(card, agent=agent),
        model_cls=TriageNote,
        expected_by=agent.name,
    )
