"""Node-author starter scaffolds (P3 §3.4, design/agent-capabilities.md §3) — offline.

The agent renders filled DRAFT scaffolds (ProcessSpec + Nextflow process, and a metric entry when
the tool emits QC) from a proposal, with the runnable command left an explicit TODO — never authored
(compose ≠ execute). An unmatched request scaffolds nothing. The endpoint exposes it read-only.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from bayleaf.node_author import propose_node, render_scaffolds

client = TestClient(app)


def test_render_scaffolds_for_a_matched_tool() -> None:
    proposal = propose_node("fastp")
    assert proposal.matched
    scaffolds = render_scaffolds(proposal)
    assert set(scaffolds) >= {"tool_card.py", "process.nf"}
    card, nf = scaffolds["tool_card.py"], scaffolds["process.nf"]
    # The skeleton is wired (tool + a real UPPER_SNAKE process name) but the command is a TODO —
    # the agent never authors a runnable script:/stub: body.
    assert "ProcessSpec(" in card and "tool='fastp'" in card
    assert "process FASTP {" in nf
    assert "<TODO" in card and "<TODO" in nf  # command left for the human
    assert "DRAFT" in card  # labelled a draft, not a runnable artifact


def test_unmatched_request_scaffolds_nothing() -> None:
    proposal = propose_node("a nonexistent imaginary tool xyzzy")
    assert not proposal.matched
    assert render_scaffolds(proposal) == {}


def test_scaffolds_endpoint_is_read_only_and_matches() -> None:
    r = client.get("/api/builder/node-proposal/scaffolds", params={"request": "mosdepth"})
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] is True and body["tool"] == "mosdepth"
    assert "process.nf" in body["scaffolds"]
    assert "MOSDEPTH" in body["scaffolds"]["process.nf"]


def test_scaffolds_endpoint_empty_for_no_match() -> None:
    r = client.get("/api/builder/node-proposal/scaffolds", params={"request": "xyzzy not a tool"})
    assert r.status_code == 200
    assert r.json()["scaffolds"] == {}
