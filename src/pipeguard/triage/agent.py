"""The QC-triage agent — advisory, OFF the deterministic critical path (ADR-0001).

The agent reads a flagged :class:`~pipeguard.models.DecisionCard`, retrieves matching
knowledge (ADR-0009), and emits a :class:`TriageNote` suggesting a likely cause and a
next action. It **never** touches the verdict — that stays a deterministic function of
the rule findings (ADR-0001). It is OFF by default with a deterministic fallback
(ADR-0006): `StubTriageAgent` is the zero-cost default, and `ClaudeTriageAgent` (the
one deep agent, ADR-0012) falls back to the stub on any error.

Env knobs mirror the synthesizer seam:
  PIPEGUARD_TRIAGE_AGENT   "stub" (default, offline, $0) | "claude" (live API)
  PIPEGUARD_TRIAGE_MODEL   default "claude-sonnet-5" — a cheaper tier than the
                           narration Opus default, per ADR-0012 (interface/advisory
                           agents run Sonnet/Haiku). Override for a harder run.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from ..models import DecisionCard, Finding, Verdict
from ..synthesis.base import top_finding
from .models import TriageCitation, TriageNote
from .retrieval import KeywordRetriever, RetrievalHit, Retriever

# Public agent identity carried on every note's `agent` field.
QC_TRIAGE_AGENT = "qc_triage"

# Default advisory model tier (ADR-0012). Cheaper than the narration Opus default
# because triage is frequent, lower-stakes, and grounded by retrieval + findings.
_DEFAULT_TRIAGE_MODEL = "claude-sonnet-5"


def _finding_query(findings: list[Finding]) -> str:
    """Flatten the findings into a free-text query for the retriever."""
    parts: list[str] = []
    for f in findings:
        parts.extend([f.rule_id, f.category.value, f.title, f.detail])
        parts.extend(e.source_field for e in f.evidence if e.source_field)
    return " ".join(parts)


def _assemble_note(
    card: DecisionCard,
    hits: list[RetrievalHit],
    *,
    likely_cause: str,
    suggested_action: str,
    generated_by: str,
    model: str | None,
) -> TriageNote:
    """Build a TriageNote with deterministic citations + finding references.

    Citations and the addressed rule_ids/signatures come from the rules and the
    retriever — never from the LLM — so provenance stays grounded even on the live
    path (the model only phrases `likely_cause`/`suggested_action`).
    """
    citations = [
        TriageCitation(source_kind="knowledge", ref=h.entry.id, title=h.entry.title, score=h.score)
        for h in hits
    ]
    citations.extend(
        TriageCitation(source_kind="finding", ref=f.rule_id, title=f.title) for f in card.findings
    )
    return TriageNote(
        agent=QC_TRIAGE_AGENT,
        sample_id=card.sample_id,
        addresses_rule_ids=list(dict.fromkeys(f.rule_id for f in card.findings)),
        addresses_signatures=list(dict.fromkeys(f.signature for f in card.findings)),
        likely_cause=likely_cause,
        suggested_action=suggested_action,
        citations=citations,
        generated_by=generated_by,
        model=model,
    )


class TriageAgent(Protocol):
    """Turns a flagged DecisionCard into an advisory TriageNote (None if clean)."""

    name: str

    def triage_card(self, card: DecisionCard) -> TriageNote | None: ...


class StubTriageAgent:
    """Deterministic, zero-cost triage: retrieve + template a note (no API call).

    It is the default agent so the whole flow runs offline, and it doubles as the
    fallback the live `ClaudeTriageAgent` degrades to. A clean PROCEED card (no
    findings) yields ``None`` — there is nothing to triage.
    """

    name = "stub"

    def __init__(self, retriever: Retriever | None = None) -> None:
        # Injectable so tests (and a future embedding backend) can swap the corpus.
        self._retriever = retriever or KeywordRetriever.from_default_corpus()

    def _retrieve(self, card: DecisionCard) -> list[RetrievalHit]:
        return self._retriever.retrieve(_finding_query(card.findings), top_k=3)

    def triage_card(self, card: DecisionCard) -> TriageNote | None:
        if not card.findings or card.verdict is Verdict.PROCEED:
            return None
        hits = self._retrieve(card)
        lead = top_finding(card.findings) or card.findings[0]
        if hits:
            top = hits[0].entry
            likely_cause = top.likely_cause
            suggested_action = top.suggested_action
        else:
            # No corpus match: stay conservative and defer to a human rather than guess.
            likely_cause = (
                f"No knowledge-corpus entry matched {lead.rule_id} ({lead.title}); "
                f"the candidate cause is unknown from the corpus."
            )
            suggested_action = (
                "Review the cited finding(s) directly with a human reviewer, and "
                "consider adding a knowledge-corpus entry for this signature."
            )
        return _assemble_note(
            card,
            hits,
            likely_cause=likely_cause,
            suggested_action=suggested_action,
            generated_by=self.name,
            model=None,
        )


# JSON schema for the advice PROSE only. The verdict, citations, and addressed
# findings are not the model's to decide, so they are deliberately absent here.
_ADVICE_SCHEMA = {
    "type": "object",
    "properties": {
        "likely_cause": {"type": "string"},
        "suggested_action": {"type": "string"},
    },
    "required": ["likely_cause", "suggested_action"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are the QC-triage analyst for an AI-assisted provenance and QC decision gate "
    "for a genomics sequencing run. A deterministic rule engine has already flagged one "
    "sample and decided its verdict. Your job is ADVISORY only: given the cited findings "
    "and retrieved knowledge, suggest the single most likely cause and a concrete next "
    "action for a lab operator.\n\n"
    "Rules you must follow:\n"
    "- You must NOT set, change, or restate a verdict — the verdict is fixed elsewhere.\n"
    "- Ground every statement in the findings and the retrieved knowledge provided; do "
    "not invent metric values, IDs, thresholds, or causes that are not present.\n"
    "- Use conservative, hedged language and flag uncertainty; this is a research/demo "
    "aid, not a clinical decision system.\n"
    "- Make no diagnostic, therapeutic, or pathogenicity claims.\n"
    "- Be specific and concise, no preamble."
)


class ClaudeTriageAgent:
    """Live Claude triage — the one deep agent (ADR-0012), OFF by default.

    Nothing here runs unless ``PIPEGUARD_TRIAGE_AGENT=claude``. Design guarantees
    mirror the synthesizer seam so it is safe and cheap to flip on:
      * `anthropic` is imported lazily, so the package installs and runs without it.
      * Citations/addressed findings stay deterministic (from the retriever + rules);
        Claude only writes the `likely_cause`/`suggested_action` prose.
      * Any API error — including a safety ``refusal`` — falls back to the stub agent.
    """

    name = "claude"

    def __init__(
        self, model: str | None = None, max_tokens: int = 1024, retriever: Retriever | None = None
    ) -> None:
        self.model = model or os.environ.get("PIPEGUARD_TRIAGE_MODEL", _DEFAULT_TRIAGE_MODEL)
        self.max_tokens = max_tokens
        self._fallback = StubTriageAgent(retriever)
        self._client: Any = None  # anthropic client, created lazily on first use

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic  # lazy: package works without anthropic installed

            # Best-effort local .env load (python-dotenv ships with the [claude] extra;
            # plain environment variables still work without it).
            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:
                pass

            self._client = anthropic.Anthropic()  # resolves credentials from env
        return self._client

    def triage_card(self, card: DecisionCard) -> TriageNote | None:
        if not card.findings or card.verdict is Verdict.PROCEED:
            return None

        # Retrieve deterministically first: it grounds both the prompt AND the note's
        # citations, so provenance survives even if the model output is discarded.
        hits = self._fallback._retrieve(card)

        try:
            # Build inside the try so a serialization surprise also degrades to the
            # stub. mode="json" keeps datetimes/enums JSON-safe (findings carry a
            # created_at datetime — python mode would break json.dumps here).
            payload = {
                "findings": [f.model_dump(mode="json") for f in card.findings],
                "retrieved_knowledge": [
                    {
                        "id": h.entry.id,
                        "title": h.entry.title,
                        "likely_cause": h.entry.likely_cause,
                        "suggested_action": h.entry.suggested_action,
                        "source": h.entry.source,
                        "score": h.score,
                    }
                    for h in hits
                ],
            }
            user_content = (
                f"Sample {card.sample_id} was flagged by the rule engine.\n\n"
                f"Findings and retrieved knowledge (JSON):\n{json.dumps(payload, indent=2)}\n\n"
                "Write the advisory triage note as JSON matching the required schema. "
                "Do not mention or restate a verdict."
            )
            client = self._get_client()
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
                output_config={"format": {"type": "json_schema", "schema": _ADVICE_SCHEMA}},
            )
            # Guard the refusal path before reading content (life-sciences work can
            # trip safety classifiers; fall back rather than break the demo).
            if response.stop_reason == "refusal":
                return self._fallback.triage_card(card)

            text = next((b.text for b in response.content if b.type == "text"), None)
            if not text:
                return self._fallback.triage_card(card)
            advice = json.loads(text)

            return _assemble_note(
                card,
                hits,
                likely_cause=advice["likely_cause"],
                suggested_action=advice["suggested_action"],
                generated_by=self.name,
                model=self.model,
            )
        except Exception:
            # Never let a live-API problem break the advisory path.
            return self._fallback.triage_card(card)


def get_triage_agent() -> TriageAgent:
    """Select the triage agent from the environment (default: the zero-cost stub).

    Set ``PIPEGUARD_TRIAGE_AGENT=claude`` to use the live agent (requires `anthropic`
    + credentials). This is the single line that flips triage from offline to live.
    """
    choice = os.environ.get("PIPEGUARD_TRIAGE_AGENT", "stub").strip().lower()
    if choice == "claude":
        return ClaudeTriageAgent()
    return StubTriageAgent()


def triage_card(card: DecisionCard, agent: TriageAgent | None = None) -> TriageNote | None:
    """Advisory triage for one decision card; ``None`` for a clean PROCEED card.

    The public entry point (mirrors `run_gate`'s relationship to the synthesizer):
    picks the env-selected agent unless one is injected, and returns its advisory
    note. The note never sets or overrides the card's verdict (ADR-0001).
    """
    agent = agent or get_triage_agent()
    return agent.triage_card(card)


# Static type check: both agents satisfy the TriageAgent protocol. An empty
# retriever keeps this import-time and does no corpus file I/O.
_EMPTY_RETRIEVER = KeywordRetriever(())
_STUB: TriageAgent = StubTriageAgent(_EMPTY_RETRIEVER)
_CLAUDE: TriageAgent = ClaudeTriageAgent(retriever=_EMPTY_RETRIEVER)
