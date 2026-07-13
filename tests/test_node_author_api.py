"""GET /api/builder/node-proposal — the advisory node-authoring read (agent #6, T-046 / W2).

Drives the router with a TestClient. The endpoint makes the shipped-but-unwired node-authoring
agent reachable from the Builder modal, mirroring the other advisory-agent reads: off the gate,
read-only, returns the agent's `NodeProposal` verbatim. These tests pin the W2 guardrails at the
wire: the payload is advisory metadata only (no verdict/confidence, no `script:`/`stub:` body), it
degrades gracefully on a blank/unmatched request, and it is stamped with the platform version so a
proposal pins tool + corpus + schema + platform.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from bayleaf.identifiers import PLATFORM_VERSION, SCHEMA_VERSION
from bayleaf.node_author import NODE_AUTHOR_CORPUS_VERSION

client = TestClient(app)


def test_matched_request_returns_advisory_proposal() -> None:
    resp = client.get(
        "/api/builder/node-proposal", params={"request": "trim adapters and QC reads"}
    )
    assert resp.status_code == 200
    body = resp.json()
    # Advisory, matched, grounded in the curated corpus — the deterministic stub path.
    assert body["advisory"] is True
    assert body["agent"] == "node_author"
    assert body["matched"] is True
    assert body["tool"] == "fastp"
    assert body["version"] and body["stage"]
    assert body["summary"] and body["rationale"]
    assert body["generated_by"] == "stub" and body["mode"] == "stub"


def test_proposal_is_metadata_only_never_a_command_or_a_verdict() -> None:
    """The wire payload carries no verdict/confidence and no runnable body (compose != execute)."""
    body = client.get("/api/builder/node-proposal", params={"request": "fastp"}).json()
    # G1: an advisory read cannot express a gate decision.
    assert "verdict" not in body
    assert "confidence" not in body
    # compose != execute: the proposal is ports/version/locators only — it never authors a Nextflow
    # `script:`/`stub:` body (those live solely in the hand-curated ProcessSpec catalog).
    assert "script" not in body
    assert "stub" not in body
    # Ports are typed; a kind outside the real vocabulary is surfaced reserved, never wired — a
    # port is `known` iff its kind is not in the reserved set.
    for port in (*body["inputs"], *body["outputs"]):
        assert port["known"] == (port["kind"] not in body["reserved_kinds"])


def test_proposal_cites_the_corpus_card_doc_and_tool() -> None:
    body = client.get("/api/builder/node-proposal", params={"request": "call variants"}).json()
    kinds = {c["source_kind"] for c in body["citations"]}
    assert kinds == {"knowledge", "card_doc", "tool"}
    # Knowledge hits carry a heuristic keyword-overlap score (never a calibrated probability).
    for c in body["citations"]:
        if c["source_kind"] == "knowledge":
            assert c["score"] is None or 0.0 <= c["score"] <= 1.0


def test_proposal_is_stamped_with_all_four_versions() -> None:
    """W2 'versioned to the platform version' — tool + corpus + schema + platform are all pinned."""
    body = client.get("/api/builder/node-proposal", params={"request": "mosdepth"}).json()
    assert body["platform_version"] == PLATFORM_VERSION
    assert body["schema_version"] == SCHEMA_VERSION
    assert body["corpus_version"] == NODE_AUTHOR_CORPUS_VERSION
    assert body["version"]  # the pinned TOOL version (distinct from the platform version)


def test_blank_request_defers_to_a_human_never_errors() -> None:
    """A blank/whitespace request is valid — a conservative defer-to-human proposal, not a 4xx."""
    for blank in ("", "   "):
        resp = client.get("/api/builder/node-proposal", params={"request": blank})
        assert resp.status_code == 200
        body = resp.json()
        assert body["advisory"] is True
        assert body["matched"] is False
        assert body["tool"] is None
        assert body["inputs"] == [] and body["outputs"] == []
        assert "human reviewer" in body["rationale"].lower()


def test_unmatched_request_fabricates_no_tool() -> None:
    body = client.get(
        "/api/builder/node-proposal", params={"request": "qwerty zxcvb nonsense request"}
    ).json()
    assert body["matched"] is False
    assert body["tool"] is None
    assert body["reserved_kinds"] == []
