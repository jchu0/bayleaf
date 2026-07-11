"""The node-authoring agent — advisory, OFF the deterministic critical path (ADR-0001).

Agent #6 in the roster (T-046). Given a NATURAL-LANGUAGE request ("add a tool that trims
adapters", or a bare tool name), it retrieves a matching curated tool-card (ADR-0009) and emits a
:class:`NodeProposal` — a concrete, HUMAN-REVIEWED builder node: a tool name, a pinned version,
typed input/output ports (each a real ``ARTIFACT_KIND``, unknown kinds surfaced as reserved),
suggested locators, and a cited rationale. It **never** runs a tool (compose ≠ execute, ADR-0003)
and **never** sets or overrides a verdict (ADR-0001): a proposed node changes nothing on the gate
until a human wires it in the builder and approves. It is OFF by default with a deterministic
fallback (ADR-0006): :class:`StubNodeAuthor` is the zero-cost default, and :class:`ClaudeNodeAuthor`
falls back to the stub on any error.

Like the other advisory agents it is stub-first ($0, offline), imports ``anthropic`` lazily, and
the ports/version/locators/citations stay DETERMINISTIC (from the corpus) even on the live path —
only the ``summary`` / ``rationale`` prose is the model's to phrase.

Env knobs mirror the other agent seams:
  PIPEGUARD_NODE_AUTHOR_AGENT   "stub" (default, offline, $0) | "claude" (live API)
  PIPEGUARD_NODE_AUTHOR_MODEL   default "claude-sonnet-5" — the mid tier (ADR-0012). Authoring one
                                node from a described function is moderate composition (like the
                                per-card QC-triage agent), not the cross-run diagnosis the Opus
                                tier is reserved for; override for a lighter/heavier run.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from .models import ARTIFACT_KINDS as _ARTIFACT_KINDS
from .models import NODE_AUTHOR_CORPUS_VERSION, NodeCitation, NodeProposal, PortSpec
from .retrieval import RetrievalHit, Retriever, ToolCardRetriever

# Public agent identity carried on every proposal's `agent` field.
NODE_AUTHOR_AGENT = "node_author"

# Default advisory model tier (ADR-0012). The mid (Sonnet) tier: proposing one node from a
# described function is a moderate composition task — harder than the cheap categorization agents
# (Haiku) but not the rare, high-stakes cross-run reasoning that reserves the Opus tier for
# pipeline-repair. Matches the QC-triage default (per-item reasoning).
_DEFAULT_NODE_AUTHOR_MODEL = "claude-sonnet-5"

# Re-exported for the docstring/prompt: the closed set of real kinds the corpus version pins.
_ = NODE_AUTHOR_CORPUS_VERSION


def _assemble_proposal(
    request: str,
    hits: list[RetrievalHit],
    *,
    summary: str,
    rationale: str,
    generated_by: str,
    model: str | None,
) -> NodeProposal:
    """Build a NodeProposal with DETERMINISTIC ports, version, locators, and citations.

    The tool, version, stage, ports, and locators come from the top-ranked corpus entry (never the
    LLM), and :attr:`reserved_kinds` is computed from the ports' own ``known`` flag — so a
    proposal's *shape* and *provenance* stay grounded even on the live path (the model only phrases
    the ``summary`` / ``rationale``). With no hit it is a conservative "defer to a human" proposal
    that fabricates no tool and no ports.
    """
    top = hits[0].entry if hits else None
    if top is None:
        return NodeProposal(
            agent=NODE_AUTHOR_AGENT,
            request=request,
            matched=False,
            summary=summary,
            rationale=rationale,
            citations=[],
            generated_by=generated_by,
            model=model,
        )
    inputs: list[PortSpec] = list(top.inputs)
    outputs: list[PortSpec] = list(top.outputs)
    # Reserved = any port whose kind is outside the real vocabulary (its `known` flag is False).
    # Surfaced so a consumer sees the honest unregistered slots without ever wiring them.
    reserved = sorted({p.kind for p in (*inputs, *outputs) if not p.known})
    citations: list[NodeCitation] = [
        NodeCitation(source_kind="knowledge", ref=h.entry.id, title=h.entry.title, score=h.score)
        for h in hits
    ]
    # The card doc + the tool itself are deterministic citations — they anchor the proposal to the
    # exact source and tool independent of any keyword match.
    citations.append(NodeCitation(source_kind="card_doc", ref=top.source, title=top.title))
    citations.append(
        NodeCitation(source_kind="tool", ref=top.tool, title=f"{top.tool} {top.version}")
    )
    return NodeProposal(
        agent=NODE_AUTHOR_AGENT,
        request=request,
        matched=True,
        tool=top.tool,
        version=top.version,
        stage=top.stage,
        inputs=inputs,
        outputs=outputs,
        locators=list(top.locators),
        reserved_kinds=reserved,
        summary=summary,
        rationale=rationale,
        citations=citations,
        generated_by=generated_by,
        model=model,
    )


# Conservative prose for a request that matched no curated tool-card — the agent proposes nothing
# concrete and defers to a human rather than inventing a tool or its ports.
_NO_MATCH_SUMMARY = (
    "No curated tool-card matched this request; no node can be proposed from the corpus without "
    "inventing a tool or its ports."
)
_NO_MATCH_RATIONALE = (
    "Describe the tool by name or function to retrieve a match, review the request with a human "
    "reviewer, and consider adding a tool-card corpus entry for this tool. No ports are fabricated."
)


class NodeAuthorAgent(Protocol):
    """Turns a natural-language request into an advisory :class:`NodeProposal`.

    ``propose`` always returns a proposal (a conservative "defer to a human" one when nothing in the
    corpus matched or the request was empty), never ``None``.
    """

    name: str

    def propose(self, request: str) -> NodeProposal: ...


class StubNodeAuthor:
    """Deterministic, zero-cost node authoring: retrieve + template a proposal (no API call).

    It is the default agent so the whole flow runs offline, and it doubles as the fallback the live
    :class:`ClaudeNodeAuthor` degrades to. With no corpus match (or an empty request) it stays
    conservative and defers to a human rather than inventing a tool node.
    """

    name = "stub"

    def __init__(self, retriever: Retriever | None = None) -> None:
        # Injectable so tests (and a future embedding backend) can swap the corpus.
        self._retriever = retriever or ToolCardRetriever.from_default_corpus()

    def _retrieve(self, request: str) -> list[RetrievalHit]:
        """Retrieve over the trimmed request; an empty/whitespace request yields no hits."""
        query = request.strip()
        return self._retriever.retrieve(query, top_k=3) if query else []

    def propose(self, request: str) -> NodeProposal:
        hits = self._retrieve(request)
        if hits:
            top = hits[0].entry
            summary = top.summary
            rationale = top.rationale
        else:
            summary = _NO_MATCH_SUMMARY
            rationale = _NO_MATCH_RATIONALE
        return _assemble_proposal(
            request,
            hits,
            summary=summary,
            rationale=rationale,
            generated_by=self.name,
            model=None,
        )


# JSON schema for the proposal PROSE only. The tool, version, ports, locators, reserved kinds, and
# citations are not the model's to decide, so they are deliberately absent here (mirrors the
# pipeline-repair prose schema): the model phrases, the deterministic corpus grounds.
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
    "You are the pipeline node-authoring assistant for an AI-assisted provenance and QC decision "
    "gate for a genomics sequencing run. Given a natural-language request for a bioinformatics "
    "tool and a retrieved, curated tool-card (its real ports and pinned version), your job is "
    "ADVISORY only: phrase a single concrete, human-reviewed PROPOSAL for adding that tool as a "
    "builder node, plus a short rationale for a lab operator.\n\n"
    "Rules you must follow:\n"
    "- You are COMPOSING a node for HUMAN review; never claim to run the tool, execute a pipeline, "
    "or apply the change yourself (compose is not execute).\n"
    "- You must NOT set, change, restate, or imply a QC verdict or a confidence — those are fixed "
    "elsewhere by a deterministic gate.\n"
    "- Ground every statement in the provided tool-card; do NOT invent tools, ports, versions, "
    "flags, file paths, or metric values.\n"
    "- Every port kind MUST come from the provided vocabulary of real artifact kinds. A port kind "
    "outside that set is RESERVED (an inert slot) — never describe it as a live/wired connection.\n"
    "- Use conservative, hedged language; this is a research/demo aid, not a clinical decision "
    "system. Make no diagnostic, therapeutic, or pathogenicity claims.\n"
    "- Be specific and concise, no preamble."
)


class ClaudeNodeAuthor:
    """Live Claude node authoring — OFF by default. Nothing here runs unless
    ``PIPEGUARD_NODE_AUTHOR_AGENT=claude``. Design guarantees mirror the other agent seams so it is
    safe and cheap to flip on:
      * ``anthropic`` is imported lazily, so the package installs and runs without it.
      * The tool, version, ports, locators, reserved kinds, and citations stay deterministic (from
        the corpus); Claude only writes the ``summary`` / ``rationale`` prose.
      * Any API error — including a safety ``refusal`` — falls back to the stub agent.
    """

    name = "claude"

    def __init__(
        self, model: str | None = None, max_tokens: int = 1024, retriever: Retriever | None = None
    ) -> None:
        self.model = model or os.environ.get(
            "PIPEGUARD_NODE_AUTHOR_MODEL", _DEFAULT_NODE_AUTHOR_MODEL
        )
        self.max_tokens = max_tokens
        self._fallback = StubNodeAuthor(retriever)
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

    def propose(self, request: str) -> NodeProposal:
        # Retrieve deterministically first: it grounds both the prompt AND the proposal's
        # ports/version/locators/citations, so the shape + provenance survive even if the model
        # output is discarded. No match (or an empty request) → the conservative stub proposal;
        # there is nothing to phrase.
        hits = self._fallback._retrieve(request)
        if not hits:
            return self._fallback.propose(request)

        try:
            # Build inside the try so any serialization surprise also degrades to the stub.
            payload = {
                "request": request,
                "artifact_kind_vocabulary": sorted(_ARTIFACT_KINDS),
                "retrieved_tool_cards": [
                    {
                        "id": h.entry.id,
                        "tool": h.entry.tool,
                        "version": h.entry.version,
                        "stage": h.entry.stage,
                        "title": h.entry.title,
                        "inputs": [
                            {"kind": p.kind, "required": p.required, "reserved": not p.known}
                            for p in h.entry.inputs
                        ],
                        "outputs": [
                            {"kind": p.kind, "required": p.required, "reserved": not p.known}
                            for p in h.entry.outputs
                        ],
                        "summary": h.entry.summary,
                        "rationale": h.entry.rationale,
                        "source": h.entry.source,
                        "score": h.score,
                    }
                    for h in hits
                ],
            }
            user_content = (
                f"Request: {request!r}.\n\n"
                f"Retrieved tool-cards and the allowed artifact-kind vocabulary (JSON):\n"
                f"{json.dumps(payload, indent=2)}\n\n"
                "Write the advisory node proposal as JSON matching the required schema. Ground it "
                "in the top-ranked tool-card; do not invent ports or restate a verdict, and do not "
                "claim to run the tool."
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
                return self._fallback.propose(request)

            text = next((b.text for b in response.content if b.type == "text"), None)
            if not text:
                return self._fallback.propose(request)
            prose = json.loads(text)

            return _assemble_proposal(
                request,
                hits,
                summary=prose["summary"],
                rationale=prose["rationale"],
                generated_by=self.name,
                model=self.model,
            )
        except Exception:
            # Never let a live-API problem break the advisory path.
            return self._fallback.propose(request)


def get_node_author_agent() -> NodeAuthorAgent:
    """Select the node-author agent from the environment (default: the zero-cost stub).

    Set ``PIPEGUARD_NODE_AUTHOR_AGENT=claude`` to use the live agent (requires `anthropic` +
    credentials). This is the single line that flips node authoring from offline to live.
    """
    choice = os.environ.get("PIPEGUARD_NODE_AUTHOR_AGENT", "stub").strip().lower()
    if choice == "claude":
        return ClaudeNodeAuthor()
    return StubNodeAuthor()


def propose_node(request: str, agent: NodeAuthorAgent | None = None) -> NodeProposal:
    """Advisory builder-node proposal for one natural-language request (mirrors `propose_repair`).

    The public entry point: picks the env-selected agent unless one is injected, and returns its
    advisory proposal. The proposal never runs a tool, edits a pipeline, or sets/overrides a verdict
    (ADR-0001/0003) — it is a human-reviewed suggestion.
    """
    return (agent or get_node_author_agent()).propose(request)


# Static type check: both agents satisfy the NodeAuthorAgent protocol. An empty retriever keeps
# this import-time and does no corpus file I/O.
_EMPTY_RETRIEVER = ToolCardRetriever(())
_STUB: NodeAuthorAgent = StubNodeAuthor(_EMPTY_RETRIEVER)
_CLAUDE: NodeAuthorAgent = ClaudeNodeAuthor(retriever=_EMPTY_RETRIEVER)
