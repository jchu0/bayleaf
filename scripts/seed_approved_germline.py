"""Seed an APPROVED germline-panel pipeline into the pipeline store (the W1 approval baseline).

``POST /api/pipelines/run`` (ADR-0014) only runs a pipeline that has an approver-blessed
(``emitted``) version — an unapproved draft is a 409. A fresh store has no such baseline, so a
demo/E2E "Run" beat has nothing to name. This committed, idempotent helper closes that gap: it
composes the seeded germline card graph (``pipeguard.nextflow.germline_graph`` — the SAME chain the
Builder ships and the compiler emits under ``pipelines/germline/``) and drives it through the real
lifecycle — save → submit → approve — so an approved ``germline-panel`` baseline is runnable **by
name** without clicking through the Builder.

It writes only through the append-only pipeline store (``api/pipeline_store.py``) via the same
lifecycle helpers the API uses (``record_transition`` / ``record_emission``), so the seeded trail is
byte-for-byte the shape a real save→approve produces. It is wholly OFF the deterministic decision
gate (ADR-0001): a saved builder graph is product state — it never becomes a verdict, finding, or
ledger row, and this script never runs a tool (compose != execute, ADR-0003).

    uv run python -m scripts.seed_approved_germline                 # seed into the default store
    uv run python -m scripts.seed_approved_germline --name my-panel # under a custom name

Run as a MODULE (``-m``) from the repo root so the app-layer ``api`` package (deliberately not part
of the installable library) is importable. Idempotent: if the name already has an approved
(emitted) version, it reports it and appends nothing (re-running never mints duplicate revisions).
Point it at any store via the usual env (``PIPEGUARD_PIPELINE_STORE`` / ``PIPEGUARD_PIPELINE_PATH``
/ ``PIPEGUARD_PIPELINE_DB``).
"""

from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timezone
from typing import Any

from api.pipeline import DEFAULT_SCHEMA_VERSION
from api.pipeline_store import (
    PipelineGraphStore,
    get_pipeline_store,
    last_emitted,
    record_emission,
    record_transition,
)
from pipeguard.nextflow import germline_graph

# The name the demo runs by: `POST /api/pipelines/run {"name": "germline-panel", ...}`.
DEFAULT_NAME = "germline-panel"


def germline_graph_dict() -> dict[str, Any]:
    """The seeded germline chain as a Builder-envelope ``{nodes, edges}`` dict — the graph shape the
    store round-trips and ``POST /api/pipelines/run`` compiles.

    Projects the framework-agnostic ``NfGraph`` (``NfNode.tool`` / ``NfEdge.from_node`` …) into the
    exact wire shape the compiler's ``CompileRequest`` validates: a node is ``{id, name, ins,
    outs}`` (``name`` = the tool/catalog key) and an edge is ``{from:{node,idx}, to:{node,idx}}``.
    Kept here (not in the framework-agnostic core) because it is the API/Builder envelope, not core
    state — and reused by the E2E acceptance test so "what the seed approves" and "what the test
    approves" are the same graph by construction.
    """
    graph = germline_graph()
    return {
        "nodes": [
            {"id": n.id, "name": n.tool, "ins": list(n.ins), "outs": list(n.outs)}
            for n in graph.nodes
        ],
        "edges": [
            {
                "from": {"node": e.from_node, "idx": e.from_idx},
                "to": {"node": e.to_node, "idx": e.to_idx},
            }
            for e in graph.edges
        ],
    }


def _draft_record(name: str, submitted_by: str) -> dict[str, Any]:
    """The initial draft envelope — mirrors ``api.main.save_pipeline`` (server-authored fields).

    ``version`` is deliberately omitted so the store authors the monotonic per-name revision under
    its write lock (exactly as a real save does); every other server field is stamped here.
    """
    return {
        "id": uuid.uuid4().hex,
        "name": name,
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "graph": germline_graph_dict(),
        "profile": None,
        "status": "draft",
        "submitted_by": submitted_by,
        "reviewed_by": None,
        "approved_by": None,
    }


def seed_approved_germline(
    name: str = DEFAULT_NAME,
    *,
    submitted_by: str = "seed.reviewer",
    approved_by: str = "seed.approver",
    store: PipelineGraphStore | None = None,
) -> tuple[dict[str, Any], bool]:
    """Ensure ``name`` has an approved germline baseline; return ``(record, created)``.

    Idempotent: if ``name`` already has an emitted (approved) version, that record is returned with
    ``created=False`` and nothing is appended. Otherwise it drives the append-only lifecycle
    save (draft) → submit (pending_review) → approve (emitted) and returns the approved record with
    ``created=True``. Uses the same store + lifecycle helpers the API does, so the seeded trail is
    indistinguishable from a real save→approve.
    """
    store = store or get_pipeline_store()
    existing = last_emitted(store, name)
    if existing is not None:
        return existing, False

    store.append(_draft_record(name, submitted_by))
    record_transition(store, name, {"status": "pending_review", "submitted_by": submitted_by})
    approved = record_emission(store, name, {"status": "approved", "approved_by": approved_by})
    if approved is None:  # pragma: no cover - the draft was just appended, so this cannot happen
        raise RuntimeError(f"failed to approve seeded pipeline '{name}'")
    return approved, True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", default=DEFAULT_NAME, help=f"pipeline name (default: {DEFAULT_NAME})")
    ap.add_argument("--submitted-by", default="seed.reviewer", help="audit id for the submit step")
    ap.add_argument("--approved-by", default="seed.approver", help="audit id for the approve step")
    args = ap.parse_args()

    record, created = seed_approved_germline(
        args.name, submitted_by=args.submitted_by, approved_by=args.approved_by
    )
    verb = "seeded" if created else "already approved"
    print(
        f"{verb}: pipeline '{record['name']}' v{record['version']} "
        f"(status={record['status']}, approved_by={record.get('approved_by')}) "
        f"— runnable by name via POST /api/pipelines/run."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
