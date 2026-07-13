"""Shared "resolve + compile an APPROVED pipeline" mechanism for the two execution routers.

Both the intake sample-processing path (``routers/intake.py``) and the Builder-run path
(``routers/pipeline_run.py``) run an operator-**authored** pipeline the same way: the request NAMES
a saved pipeline, the server resolves that pipeline's approver-blessed (``emitted``) snapshot from
the ``PipelineGraphStore`` (the approval gate, ADR-0014 — a **409** if there is no approved version,
never a silent bypass), compiles that graph to a Nextflow bundle, and hands the compiled ``main.nf``
to the out-of-core driver. This is the single home for that mechanism so the two routers share ONE
approval gate and ONE compile path — never a raw client-posted graph.

Factored out of ``routers/pipeline_run.py`` (where :func:`resolve_approved` and :func:`to_graph`
originally lived, privately) so intake can reuse the exact same resolve+compile without importing a
sibling router's privates or duplicating the gate.

**compose ≠ execute holds at the CORE:** ``src/bayleaf/`` (including ``bayleaf.nextflow``) only
emits TEXT — it never runs a tool. Only the routers that call this module then shell out to the
driver. This module itself produces files on disk; it never launches a subprocess.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

# The post-run parse contract lives with the parser (``scripts/run_giab_pipeline.py``) so the
# submit-time gate and the parser share ONE constant and can't drift. Importing it here (not
# re-declaring it) is what makes "reject at submit" mean exactly "the parser would have required
# this" (WS-09). ``scripts`` is a first-class, strictly-typed package (mypy ``files``); this module
# only reads a frozenset from it — no cycle (scripts imports only the core, never ``api``).
from scripts.run_giab_pipeline import REQUIRED_OUTPUT_KINDS

from api.pipeline_store import PipelineGraphStore, last_emitted
from api.routers.nextflow import CompileRequest
from bayleaf.nextflow import (
    NextflowBundle,
    NfEdge,
    NfGraph,
    NfNode,
    catalog_entry,
    compile_graph,
    required_inputs,
)
from bayleaf.nextflow.compiler import CompileError


def resolve_approved(store: PipelineGraphStore, name: str, version: int | None) -> dict[str, Any]:
    """Resolve the APPROVED (emitted) stored envelope for ``name`` — the run's execution contract.

    The approval gate (ADR-0014): only an approver-blessed version may run. Approval stamps
    ``emitted_at`` on that version (``record_emission``), so "approved baseline" = the emitted
    snapshot. ``version`` pins an exact approved revision; omitted → the newest emitted one
    (``last_emitted``). A name with no emitted version (never approved, or unknown) is a **409** —
    the gate, not a silent bypass. A store backend hiccup degrades to a generic 503 (never leaks a
    path/DSN — mirrors the save/lifecycle routers).
    """
    try:
        if version is None:
            record = last_emitted(store, name)
        else:
            record = next(
                (
                    r
                    for r in store.get_versions(name)
                    if int(r.get("version") or 0) == version and r.get("emitted_at")
                ),
                None,
            )
    except Exception:  # store backend hiccup → generic 503, never leak a path/DSN
        raise HTTPException(status_code=503, detail="pipeline store unavailable") from None
    if record is None:
        detail = (
            f"no approved version of pipeline '{name}' — submit and approve it before running"
            if version is None
            else f"version {version} of pipeline '{name}' is not approved"
        )
        raise HTTPException(status_code=409, detail=detail)
    return record


def to_graph(req: CompileRequest) -> NfGraph:
    """Adapt a stored/compile-request envelope into the core's :class:`NfGraph`.

    Threads any operator-authored custom-script fields through (the stored graph round-trips them,
    ADR-0020) so an APPROVED custom pipeline actually runs the operator's body at the execution
    point ADR-0020 names — only an approver-blessed graph ever reaches this gate. Absent on ordinary
    catalogued nodes, so the germline/approved-baseline path is byte-unchanged.
    """
    return NfGraph(
        name=req.name,
        nodes=[
            NfNode(
                id=n.id,
                tool=n.name,
                ins=list(n.ins),
                outs=list(n.outs),
                script=n.script,
                container=n.container,
                conda=n.conda,
            )
            for n in req.nodes
        ],
        edges=[NfEdge(e.src.node, e.src.idx, e.to.node, e.to.idx) for e in req.edges],
    )


def compile_record(record: dict[str, Any], name: str) -> tuple[NfGraph, NextflowBundle]:
    """Compile an approved stored envelope's graph to a Nextflow bundle (never a client graph).

    Raises a 422 if the approved graph can't compile, or if it has no tool node to run (an
    empty/source-only graph compiles to an empty topo order — ``compile_graph`` does not treat that
    as an error — but launching the driver on it fails late and opaquely, so reject it up front with
    the same reason ``/api/pipelines/compile`` gives).
    """
    graph_dict = record.get("graph") or {}
    try:
        graph = to_graph(CompileRequest.model_validate({**graph_dict, "name": name}))
        bundle = compile_graph(graph)
    except (CompileError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail=f"cannot compile approved pipeline '{name}': {exc}"
        ) from exc
    if not any(not n.is_source() for n in graph.nodes):
        raise HTTPException(status_code=422, detail="the graph has no tool nodes to run")
    return graph, bundle


def check_parse_contract(graph: NfGraph, name: str) -> None:
    """Reject (422) an approved authored graph whose outputs can't yield a gate-able card.

    The out-of-core driver parses the frozen-five QC by globbing a compiled pipeline's published
    ``results/`` dir (``scripts/run_giab_pipeline.py::parse_sample``). A graph that can't PRODUCE
    every :data:`REQUIRED_OUTPUT_KINDS` kind would run to completion in Nextflow and only THEN die
    at parse with no card — a full compute burn for a ``failed`` run (WS-09 #1). We catch it at
    SUBMIT instead — a structural check needing no tools/data, so it is offline-verifiable.

    Only a CATALOGUED tool's output counts as parse-findable, and it is credited by its SPEC's
    published kinds (``catalog_entry(...).output_kinds()``), NOT the node's declared ``outs``: the
    compiler renders a catalogued process's ``output:``/``publishDir results`` straight from the
    spec, so a catalogued node always publishes its full spec outputs into ``results/`` no matter
    which ports the Builder wired. A custom/uncatalogued node is deliberately NOT credited: a custom
    body publishes to ``results/custom`` (not the ``results/`` the parser globs) and an uncatalogued
    node has no real command — neither can satisfy the contract, so trusting a claimed kind there
    would be a false accept the live parse would then reject."""
    produced: set[str] = set()
    for node in graph.nodes:
        spec = catalog_entry(node.tool)
        if spec is not None and not node.is_custom():
            produced.update(spec.output_kinds())
    missing = sorted(REQUIRED_OUTPUT_KINDS - produced)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=(
                f"authored pipeline '{name}' does not produce the output kind(s) {missing} the "
                "post-run QC parse requires (the frozen-five gate contract), so it can't yield a "
                "gate-able card — it would run to completion then fail at parse. Add the missing "
                "stage(s) before running."
            ),
        )


def check_inputs_suppliable(graph: NfGraph, name: str, suppliable: frozenset[str]) -> None:
    """Reject (422) an approved graph needing an external input kind the caller can't supply.

    The Builder-Run path lets an operator pick inputs by key and validates the graph's
    ``required_inputs`` against them (``routers/pipeline_run.py``). Intake has no such picker — it
    always supplies the fixed HG002 germline defaults — so an authored graph that consumes anything
    else would silently fall back to those defaults and process the WRONG inputs (wrong-but-runs,
    WS-09 #2). Reject it up front instead, naming the unsupported kind(s)."""
    unsupported = sorted(required_inputs(graph) - suppliable)
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail=(
                f"authored pipeline '{name}' needs external input kind(s) {unsupported} this run "
                f"can't supply (available: {sorted(suppliable)}) — it would otherwise fall back to "
                "the HG002 defaults and process the wrong inputs. Run it via the Builder-Run path "
                "with those inputs chosen, or remove the stage(s) that consume them."
            ),
        )


def materialize_bundle(bundle: NextflowBundle, dest_dir: Path) -> Path:
    """Write a compiled bundle's files under ``dest_dir`` and return the path to its ``main.nf``.

    Idempotent (a concurrent duplicate re-writes the same bytes); the caller hands the returned
    ``main.nf`` to the driver via ``--pipeline``.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in bundle.files.items():
        out_path = dest_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
    return dest_dir / "main.nf"
