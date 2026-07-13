"""Advisory node-authoring read + accept-to-library (agent #6, T-046 / W2).

Two surfaces over the shipped node-authoring agent:

  1. **Read** — ``GET /api/builder/node-proposal`` makes the agent reachable from the Builder's
     "Author a tool node" modal. It mirrors the other advisory-agent reads verbatim (the read-only
     ``GET /api/monitoring/signatures/{sig}/repair`` shape): off the deterministic gate, no RBAC
     write, returns the agent's :class:`NodeProposal` as-is.
  2. **Accept → library (W2)** — ``POST /api/builder/node-proposal/accept`` writes an accepted
     proposal into the pluggable :mod:`api.library_store` as a versioned **draft** entry
     (``require_role``, capturing ``submitted_by``), and ``GET /api/builder/library`` lists the
     accepted entries. This is the backend the future Builder "Accept to library" button calls; the
     button itself lives in a Builder frontend file owned elsewhere and is intentionally not wired
     here.

The hard trust seam W2 is built around stays explicit on BOTH surfaces: they carry METADATA only —
a tool name, a pinned version, typed ports, suggested locators, a cited rationale. They NEVER author
a Nextflow ``script:``/``stub:`` body (those live solely in the hand-curated ``ProcessSpec``
catalog, ``bayleaf.nextflow.catalog``), never run a tool, and carry no verdict/confidence field
(ADR-0001/0003; ``advisory`` is pinned ``True`` on the model). An accepted entry is metadata a human
must still turn into a runnable ``ProcessSpec`` before anything compiles — compose ≠ execute. See
`docs/design/agent-authoring-contract.md`.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.agent_output_cache import cache_through
from api.auth import Actor, require_role
from api.library_store import get_library_store
from bayleaf.identifiers import new_id, utc_now
from bayleaf.node_author import (
    NODE_AUTHOR_CORPUS_VERSION,
    NodeProposal,
    check_conformance,
    get_node_author_agent,
    propose_node,
    render_scaffolds,
)

router = APIRouter(prefix="/api", tags=["node_author"])

# A generous but bounded request length — the retriever tokenizes a natural-language ask; anything
# past this is not a tool description. Kept lenient (an empty/blank request is valid: the agent
# returns a conservative "no tool-card matched — defer to a human" proposal, never a 4xx) so the
# tolerant-boundary posture matches the rest of the read-API.
_MAX_REQUEST_LEN = 2000

# The library-entry lifecycle. A newly accepted proposal is a ``draft``; the draft → ``approved``
# transition (reviewer/approver RBAC, riding the same audited flow the pipeline lifecycle uses) is
# the labelled deferred slice — the store already carries ``status`` so no migration is needed when
# it lands (agent-authoring-contract.md "Deferred").
LibraryStatus = Literal["draft", "approved"]


@router.get("/builder/node-proposal")
def get_node_proposal(
    request: str = Query(
        "",
        max_length=_MAX_REQUEST_LEN,
        description="A natural-language tool request or a bare tool name (e.g. 'trim adapters').",
    ),
) -> NodeProposal:
    """Advisory builder-node proposal for one natural-language request (agent #6, off the gate).

    Retrieves a matching curated tool-card and returns a proposed, HUMAN-REVIEWED
    :class:`NodeProposal` — typed ports, a pinned version, suggested locators, and a cited
    rationale. It authors METADATA, never a runnable command; it never wires an edge, adds a card,
    runs a tool, or sets a verdict (ADR-0001/0003). A blank or unmatched request yields a
    conservative "defer to a human" proposal that fabricates no tool or ports — never an error.
    Stub-first ($0) unless ``BAYLEAF_NODE_AUTHOR_AGENT=claude`` is set; it degrades to the stub
    on any live-API error. Cache-through (api/agent_output_cache): an identical request is served
    from the backend, not regenerated (no Claude re-call on navigation).
    """
    return _cached_proposal(request)


def _cached_proposal(request: str) -> NodeProposal:
    """The cache-through node proposal — shared by the proposal + scaffolds endpoints so a request
    that was already proposed (or scaffolded) reuses the SAME cached proposal (no repeat Claude
    call). Non-``None`` always (``propose_node`` returns a defer proposal, never ``None``)."""
    agent = get_node_author_agent()
    model = getattr(agent, "model", None) if agent.name == "claude" else None
    proposal = cache_through(
        namespace="node_author",
        key_inputs={
            "request": request,
            "agent": agent.name,
            "model": model,
            "corpus_version": NODE_AUTHOR_CORPUS_VERSION,
        },
        generate=lambda: propose_node(request, agent=agent),
        model_cls=NodeProposal,
        expected_by=agent.name,
    )
    return proposal if proposal is not None else propose_node(request)


class NodeScaffolds(BaseModel):
    """Filled DRAFT scaffolds for onboarding the proposed tool (P3 §3.4). ``scaffolds`` maps an
    artifact filename → its templated text; empty when the request matched no tool-card."""

    model_config = ConfigDict(extra="forbid")
    request: str
    matched: bool
    tool: str | None = None
    scaffolds: dict[str, str] = Field(default_factory=dict)


@router.get("/builder/node-proposal/scaffolds")
def get_node_scaffolds(
    request: str = Query(
        "", max_length=_MAX_REQUEST_LEN, description="Same request as node-proposal; scaffolds it."
    ),
) -> NodeScaffolds:
    """Starter scaffolds for the tool a request proposes (agent #6, off the gate; P3 §3.4).

    Re-derives the proposal (``propose_node``) and renders filled DRAFT artifacts — a `ProcessSpec`
    catalog entry, the Nextflow `process` skeleton, and (if the tool emits QC) a metric-registry
    entry — with the runnable command left as an explicit TODO. The agent lays out the conformant
    skeleton; a HUMAN authors the compute (compose ≠ execute, ADR-0001/0003). Read-only, runs no
    tool; an unmatched request yields an empty ``scaffolds`` (nothing to scaffold), never an error.
    """
    proposal = _cached_proposal(request)  # reuse the cached proposal from the proposal endpoint
    return NodeScaffolds(
        request=request,
        matched=proposal.matched,
        tool=proposal.tool,
        scaffolds=render_scaffolds(proposal),
    )


class AcceptNodeProposalIn(BaseModel):
    """The accept body — the natural-language ``request`` whose proposal is being accepted.

    ``extra="forbid"`` blocks any smuggled server-authored field. The client sends the *request*,
    NOT a fully-formed proposal: the server **re-derives** the proposal deterministically from the
    corpus (``propose_node``), so a caller can never author library metadata directly — it can only
    accept exactly what the agent proposes for that request. This is the load-bearing safety choice
    (the proposal's ports/version/locators are grounded in the curated corpus, never client input).
    """

    model_config = ConfigDict(extra="forbid")

    request: str = Field(
        ...,
        min_length=1,
        max_length=_MAX_REQUEST_LEN,
        description="The natural-language request whose proposal is accepted into the library.",
    )


class LibraryEntry(BaseModel):
    """An accepted tool-card **library entry** — a :class:`NodeProposal` accepted as a draft.

    The lifecycle fields (``id`` / ``status`` / ``submitted_by`` / timestamps) sit alongside the
    lifted ``tool`` / ``version`` (the store's index columns) and the full embedded ``proposal`` —
    so the entry carries the exact accepted metadata (ports, locators, citations, the four version
    stamps) losslessly. It is METADATA only: there is no ``script:``/``stub:`` command body anywhere
    on this shape, and (via the embedded proposal) no verdict/confidence field — a human authors the
    runnable ``ProcessSpec`` before anything compiles (compose ≠ execute).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    tool: str
    version: str | None = None
    status: LibraryStatus = "draft"
    submitted_by: str
    created_at: str
    updated_at: str
    proposal: NodeProposal


@router.post("/builder/node-proposal/accept", status_code=201)
def accept_node_proposal(
    body: AcceptNodeProposalIn,
    actor: Actor = Depends(require_role("reviewer", "approver")),
) -> LibraryEntry:
    """Accept an advisory proposal into the tool-card library as a versioned **draft** entry (W2).

    RBAC-gated (``reviewer``/``approver``, matching the pipeline draft-mint tier) and stamps
    ``submitted_by`` from the authenticated actor. The server RE-DERIVES the proposal from the
    request (never trusts a client-supplied proposal), guards that it matched a curated tool-card,
    and runs it through :func:`check_conformance` — so only a corpus-grounded, boundary-conformant
    proposal can enter the library (defense in depth).

    The stored entry is **METADATA** — ports, a pinned version, suggested locators, citations. It is
    **never** a Nextflow ``script:``/``stub:`` body: a human still authors the runnable
    ``ProcessSpec`` (``bayleaf.nextflow.catalog``) before the accepted tool can compile or run.
    Accepting changes nothing on the deterministic gate (ADR-0001) and runs no tool (ADR-0003).
    """
    proposal = propose_node(body.request)
    if not proposal.matched:
        # A "defer to a human" proposal fabricates no tool/ports — there is nothing to accept.
        raise HTTPException(
            status_code=422,
            detail="no curated tool-card matched this request — there is no node to accept.",
        )
    violations = check_conformance(proposal)
    if violations:  # a conformant agent never trips this; the guard makes the pin non-decorative
        codes = [v.code for v in violations]
        raise HTTPException(
            status_code=422,
            detail=f"proposal failed the authoring-boundary contract: {codes}",
        )
    now = utc_now().isoformat()
    entry = LibraryEntry(
        id=new_id("libentry"),
        tool=proposal.tool or "",
        version=proposal.version,
        status="draft",
        submitted_by=actor.id,
        created_at=now,
        updated_at=now,
        proposal=proposal,
    )
    stored = get_library_store().add(entry.model_dump(mode="json"))
    return LibraryEntry.model_validate(stored)


@router.get("/builder/library")
def list_library_entries(
    tool: str | None = Query(None, max_length=128, description="Filter to one accepted tool."),
    status: str | None = Query(
        None, description="Filter by lifecycle status ('draft' | 'approved')."
    ),
) -> list[LibraryEntry]:
    """List accepted tool-card library entries (off-gate, read-only), oldest first.

    Optional ``tool`` / ``status`` filters mirror the store's query grain. Each row is the full
    :class:`LibraryEntry` (its embedded proposal is metadata only — no command body, no verdict).
    """
    rows = get_library_store().list(tool=tool, status=status)
    return [LibraryEntry.model_validate(r) for r in rows]
