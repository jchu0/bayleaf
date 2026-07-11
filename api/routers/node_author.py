"""Advisory node-authoring read (agent #6, T-046 / W2) — the read path over `propose_node`.

A single read-only endpoint that makes the shipped-but-unwired node-authoring agent reachable from
the Builder's "Author a tool node" modal. It mirrors the other advisory-agent reads verbatim (the
read-only ``GET /api/monitoring/signatures/{sig}/repair`` shape): off the deterministic gate, no
RBAC write, returns the agent's :class:`NodeProposal` as-is.

The hard trust seam W2 is built around stays explicit here: the endpoint returns METADATA only —
a tool name, a pinned version, typed ports, suggested locators, a cited rationale. It NEVER authors
a Nextflow ``script:``/``stub:`` body (those live solely in the hand-curated ``ProcessSpec``
catalog, ``pipeguard.nextflow.catalog``), never writes a Builder card, never runs a tool, and
carries no verdict/confidence field (ADR-0001/0003; ``advisory`` is pinned ``True`` on the model).
A human reviews the proposal, and a human authors the runnable body before anything compiles —
compose ≠ execute. See `docs/design/agent-authoring-contract.md`.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from pipeguard.node_author import NodeProposal, propose_node

router = APIRouter(prefix="/api", tags=["node_author"])

# A generous but bounded request length — the retriever tokenizes a natural-language ask; anything
# past this is not a tool description. Kept lenient (an empty/blank request is valid: the agent
# returns a conservative "no tool-card matched — defer to a human" proposal, never a 4xx) so the
# tolerant-boundary posture matches the rest of the read-API.
_MAX_REQUEST_LEN = 2000


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
    Stub-first ($0) unless ``PIPEGUARD_NODE_AUTHOR_AGENT=claude`` is set; it degrades to the stub
    on any live-API error.
    """
    return propose_node(request)
