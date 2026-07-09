"""The pipeline-repair agent — advisory, OFF the deterministic critical path (ADR-0001).

Agent #2 in the roster (ADR-0012). Given a RECURRING ISSUE SIGNATURE from the monitoring
rollup, it retrieves a matching remediation template (ADR-0009) and emits a
:class:`RepairProposal` — a concrete, HUMAN-REVIEWED pipeline change (a stage to attach a
guard to, the gate phase it guards, and the fix prose). It **never** edits a pipeline and
**never** sets or overrides a verdict (ADR-0001): routing a proposal to the queue needs
approver sign-off (ADR-0008 §4). It is OFF by default with a deterministic fallback
(ADR-0006): :class:`StubRepairAgent` is the zero-cost default, and :class:`ClaudeRepairAgent`
falls back to the stub on any error.

Unlike QC-triage (which reasons over one flagged card), pipeline-repair reasons over a
cross-run failure *pattern*, so its default model is the higher Opus tier (ADR-0012 §3a).

Env knobs mirror the other agent seams:
  PIPEGUARD_PIPELINE_REPAIR_AGENT   "stub" (default, offline, $0) | "claude" (live API)
  PIPEGUARD_PIPELINE_REPAIR_MODEL   default "claude-opus-4-8" — the Opus-high tier, because
                                    this agent reasons over cross-run failure patterns
                                    (ADR-0012 §3a). Override to a cheaper tier for a lighter run.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from .models import (
    RecurringSignature,
    RepairCitation,
    RepairProposal,
)
from .retrieval import RemediationRetriever, RetrievalHit, Retriever

# Public agent identity carried on every proposal's `agent` field.
PIPELINE_REPAIR_AGENT = "pipeline_repair"

# Default advisory model tier (ADR-0012 §3a). The Opus-high tier (matching the narration
# default), because a systemic cross-run diagnosis is the hard, rare, high-stakes reasoning
# the ADR reserves the expensive model for — the opposite end from the frequent, cheap
# triage/feedback agents that run Sonnet/Haiku.
_DEFAULT_PIPELINE_REPAIR_MODEL = "claude-opus-4-8"


def _signature_query(sig: RecurringSignature) -> str:
    """Flatten a recurring signature into a free-text query for the retriever.

    The rule_id + title + gate carry the issue-class signal; the rule_id tokenizes to terms
    (``PROV-001`` -> ``prov`` + ``001``) that the corpus indexes on ``rule_ids`` for a direct
    hit, and the title supplies the descriptive keywords.
    """
    return f"{sig.rule_id} {sig.title} {sig.gate.value}"


def _assemble_proposal(
    sig: RecurringSignature,
    hits: list[RetrievalHit],
    *,
    summary: str,
    rationale: str,
    generated_by: str,
    model: str | None,
) -> RepairProposal:
    """Build a RepairProposal with DETERMINISTIC citations, attach_to, and scope.

    ``attach_to`` / ``scope`` come from the top-ranked corpus entry (falling back to the
    signature's own gate for scope when nothing matched) and the citations come from the
    retriever + the addressed rule/signature — never from the LLM — so a proposal's *target*
    and *provenance* stay grounded even on the live path (the model only phrases the
    ``summary`` / ``rationale``).
    """
    top = hits[0].entry if hits else None
    attach_to = top.attach_to if top else None
    # Scope defaults to the signature's own gate when the corpus offers none, so a proposal is
    # always anchored to a gate phase even for an unmatched signature.
    scope = top.scope if (top and top.scope is not None) else sig.gate
    citations: list[RepairCitation] = [
        RepairCitation(source_kind="knowledge", ref=h.entry.id, title=h.entry.title, score=h.score)
        for h in hits
    ]
    # The addressed rule + the recurring signature themselves are deterministic citations —
    # they anchor the proposal to exactly what recurred, independent of any corpus match.
    citations.append(RepairCitation(source_kind="rule", ref=sig.rule_id, title=sig.title))
    citations.append(RepairCitation(source_kind="signature", ref=sig.signature))
    return RepairProposal(
        agent=PIPELINE_REPAIR_AGENT,
        addresses_rule_id=sig.rule_id,
        addresses_signature=sig.signature,
        signature_count=sig.count,
        run_ids=list(sig.run_ids),
        summary=summary,
        rationale=rationale,
        attach_to=attach_to,
        scope=scope,
        citations=citations,
        generated_by=generated_by,
        model=model,
    )


class RepairAgent(Protocol):
    """Turns a recurring signature into an advisory RepairProposal.

    A recurring signature is by definition an open issue, so — unlike triage's Optional note —
    ``propose`` always returns a proposal (a conservative "defer to a human" one when nothing
    in the corpus matched).
    """

    name: str

    def propose(self, signature: RecurringSignature) -> RepairProposal: ...


class StubRepairAgent:
    """Deterministic, zero-cost repair: retrieve + template a proposal (no API call).

    It is the default agent so the whole flow runs offline, and it doubles as the fallback the
    live :class:`ClaudeRepairAgent` degrades to. With no corpus match it stays conservative and
    defers to a human rather than inventing a pipeline change.
    """

    name = "stub"

    def __init__(self, retriever: Retriever | None = None) -> None:
        # Injectable so tests (and a future embedding backend) can swap the corpus.
        self._retriever = retriever or RemediationRetriever.from_default_corpus()

    def _retrieve(self, signature: RecurringSignature) -> list[RetrievalHit]:
        return self._retriever.retrieve(_signature_query(signature), top_k=3)

    def propose(self, signature: RecurringSignature) -> RepairProposal:
        hits = self._retrieve(signature)
        if hits:
            top = hits[0].entry
            summary = top.summary
            rationale = top.rationale
        else:
            # No corpus match: propose nothing concrete, defer to a human, and suggest curating
            # a corpus entry — never guess a pipeline change for an unknown issue class.
            summary = (
                f"No remediation-corpus entry matched {signature.rule_id} "
                f"({signature.title}); no concrete pipeline change can be proposed from the corpus."
            )
            rationale = (
                "Review the recurring signature directly with a human reviewer, and consider "
                "adding a remediation-corpus entry for this issue class."
            )
        return _assemble_proposal(
            signature,
            hits,
            summary=summary,
            rationale=rationale,
            generated_by=self.name,
            model=None,
        )


# JSON schema for the proposal PROSE only. The stage to attach to, the gate scope, the
# citations, and the addressed rule/signature are not the model's to decide, so they are
# deliberately absent here.
_PROSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["summary", "rationale"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are the pipeline-repair analyst for an AI-assisted provenance and QC decision gate for "
    "a genomics sequencing run. A deterministic rule engine has flagged the SAME issue signature "
    "across multiple runs. Your job is ADVISORY only: given the recurring signature and the "
    "retrieved remediation templates, phrase a single concrete, human-reviewed remediation "
    "(the pipeline guard to add) and a short rationale for a lab operator.\n\n"
    "Rules you must follow:\n"
    "- You must NOT set, change, restate, or imply a verdict — the verdict is fixed elsewhere.\n"
    "- You are proposing a change for HUMAN review; never assert the fix is applied, and never "
    "claim to edit a pipeline yourself.\n"
    "- Ground every statement in the recurring signature and the retrieved remediations "
    "provided; do NOT invent metric values, IDs, thresholds, or stage names. Refer thresholds "
    "to 'the runbook's configured gate/band' rather than stating a number.\n"
    "- Use conservative, hedged language and flag uncertainty; this is a research/demo aid, not "
    "a clinical decision system.\n"
    "- Make no diagnostic, therapeutic, or pathogenicity claims.\n"
    "- Be specific and concise, no preamble."
)


class ClaudeRepairAgent:
    """Live Claude pipeline-repair — the deep cross-run reasoner (ADR-0012), OFF by default.

    Nothing here runs unless ``PIPEGUARD_PIPELINE_REPAIR_AGENT=claude``. Design guarantees
    mirror the triage/synthesizer seams so it is safe and cheap to flip on:
      * ``anthropic`` is imported lazily, so the package installs and runs without it.
      * The attach-to stage, gate scope, citations, and addressed rule/signature stay
        deterministic (from the retriever + the signature); Claude only writes the
        ``summary`` / ``rationale`` prose.
      * Any API error — including a safety ``refusal`` — falls back to the stub agent.
    """

    name = "claude"

    def __init__(
        self, model: str | None = None, max_tokens: int = 1024, retriever: Retriever | None = None
    ) -> None:
        self.model = model or os.environ.get(
            "PIPEGUARD_PIPELINE_REPAIR_MODEL", _DEFAULT_PIPELINE_REPAIR_MODEL
        )
        self.max_tokens = max_tokens
        self._fallback = StubRepairAgent(retriever)
        self._client: Any = None  # anthropic client, created lazily on first use

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic  # lazy: package works without anthropic installed

            # Best-effort local .env load (python-dotenv ships with the [claude] extra; plain
            # environment variables still work without it).
            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:
                pass

            self._client = anthropic.Anthropic()  # resolves credentials from env
        return self._client

    def propose(self, signature: RecurringSignature) -> RepairProposal:
        # Retrieve deterministically first: it grounds both the prompt AND the proposal's
        # attach_to/scope/citations, so the target + provenance survive even if the model
        # output is discarded.
        hits = self._fallback._retrieve(signature)

        try:
            # Build inside the try so any serialization surprise also degrades to the stub.
            payload = {
                "recurring_signature": {
                    "rule_id": signature.rule_id,
                    "title": signature.title,
                    "gate": signature.gate.value,
                    "count": signature.count,
                    "run_ids": list(signature.run_ids),
                },
                "retrieved_remediations": [
                    {
                        "id": h.entry.id,
                        "title": h.entry.title,
                        "summary": h.entry.summary,
                        "rationale": h.entry.rationale,
                        "attach_to": h.entry.attach_to.value if h.entry.attach_to else None,
                        "scope": h.entry.scope.value if h.entry.scope else None,
                        "source": h.entry.source,
                        "score": h.score,
                    }
                    for h in hits
                ],
            }
            user_content = (
                f"The signature '{signature.rule_id}' ({signature.title}) recurred "
                f"{signature.count} time(s) across runs {list(signature.run_ids)}.\n\n"
                f"Recurring signature and retrieved remediations (JSON):\n"
                f"{json.dumps(payload, indent=2)}\n\n"
                "Write the advisory repair proposal as JSON matching the required schema. "
                "Do not mention or restate a verdict, and do not claim to apply the fix."
            )
            client = self._get_client()
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
                output_config={"format": {"type": "json_schema", "schema": _PROSE_SCHEMA}},
            )
            # Guard the refusal path before reading content (life-sciences work can trip safety
            # classifiers; fall back rather than break the demo).
            if response.stop_reason == "refusal":
                return self._fallback.propose(signature)

            text = next((b.text for b in response.content if b.type == "text"), None)
            if not text:
                return self._fallback.propose(signature)
            prose = json.loads(text)

            return _assemble_proposal(
                signature,
                hits,
                summary=prose["summary"],
                rationale=prose["rationale"],
                generated_by=self.name,
                model=self.model,
            )
        except Exception:
            # Never let a live-API problem break the advisory path.
            return self._fallback.propose(signature)


def get_repair_agent() -> RepairAgent:
    """Select the pipeline-repair agent from the environment (default: the zero-cost stub).

    Set ``PIPEGUARD_PIPELINE_REPAIR_AGENT=claude`` to use the live agent (requires `anthropic`
    + credentials). This is the single line that flips repair from offline to live.
    """
    choice = os.environ.get("PIPEGUARD_PIPELINE_REPAIR_AGENT", "stub").strip().lower()
    if choice == "claude":
        return ClaudeRepairAgent()
    return StubRepairAgent()


def propose_repair(
    signature: RecurringSignature, agent: RepairAgent | None = None
) -> RepairProposal:
    """Advisory repair proposal for one recurring signature (mirrors `triage_card`).

    The public entry point: picks the env-selected agent unless one is injected, and returns
    its advisory proposal. The proposal never edits a pipeline or sets/overrides a verdict
    (ADR-0001) — it is a human-reviewed suggestion.
    """
    return (agent or get_repair_agent()).propose(signature)


# Static type check: both agents satisfy the RepairAgent protocol. An empty retriever keeps
# this import-time and does no corpus file I/O.
_EMPTY_RETRIEVER = RemediationRetriever(())
_STUB: RepairAgent = StubRepairAgent(_EMPTY_RETRIEVER)
_CLAUDE: RepairAgent = ClaudeRepairAgent(retriever=_EMPTY_RETRIEVER)
