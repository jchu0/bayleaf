"""Compile a Pipeline-Builder card graph into a runnable Nextflow (DSL2) pipeline (ADR-0003).

A stateless, off-gate transform: it takes the Builder's live ``{nodes, edges}`` (the exact shape it
saves) and returns the generated pipeline — either as JSON (for the Builder's preview) or a ``.zip``
(a downloadable ``main.nf`` + ``modules/*.nf`` + ``nextflow.config`` the user runs with
``nextflow run``). It never persists anything, never runs Nextflow or a tool, and never touches a
verdict — compose ≠ execute holds (the pure codegen lives in ``pipeguard.nextflow``).
"""

from __future__ import annotations

import io
import re
import zipfile

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from pipeguard.nextflow import CompileError, NfEdge, NfGraph, NfNode, compile_graph

router = APIRouter(prefix="/api", tags=["nextflow"])


class CompileNode(BaseModel):
    """One Builder card: `name` is the tool (a catalog key); `ins`/`outs` are kind ports."""

    id: str
    name: str
    ins: list[str] = Field(default_factory=list)
    outs: list[str] = Field(default_factory=list)


class CompilePort(BaseModel):
    node: str
    idx: int


class CompileEdge(BaseModel):
    # `from` is a Python keyword — accept the wire name and expose it as `src`.
    src: CompilePort = Field(alias="from")
    to: CompilePort

    model_config = {"populate_by_name": True}


class CompileRequest(BaseModel):
    name: str = "pipeline"
    nodes: list[CompileNode]
    edges: list[CompileEdge] = Field(default_factory=list)


class CompileResponse(BaseModel):
    name: str
    files: dict[str, str]
    main_nf: str
    steps: list[str]  # the topological tool order (a quick human summary of the DAG)


def _sanitize(name: str) -> str:
    """A Nextflow-manifest-safe pipeline name (the compiler also uses it for the dir)."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-._")
    return cleaned or "pipeline"


def _to_graph(req: CompileRequest) -> NfGraph:
    return NfGraph(
        name=_sanitize(req.name),
        nodes=[NfNode(id=n.id, tool=n.name, ins=list(n.ins), outs=list(n.outs)) for n in req.nodes],
        edges=[NfEdge(e.src.node, e.src.idx, e.to.node, e.to.idx) for e in req.edges],
    )


@router.post("/pipelines/compile", response_model=None)
def compile_pipeline(
    req: CompileRequest,
    format: str = Query("json", pattern="^(json|zip)$"),
) -> Response | CompileResponse:
    """Compile a Builder graph → a Nextflow bundle. `format=json` (preview) or `zip` (download).

    A bad graph (a cycle, an edge to a missing node/port) is a 422 with the compiler's reason — the
    same tolerant-boundary posture as the rest of the API. An empty graph is a 422 (nothing to run).
    """
    if not req.nodes:
        raise HTTPException(status_code=422, detail="the graph has no tool nodes to compile")
    try:
        bundle = compile_graph(_to_graph(req))
    except CompileError as exc:
        raise HTTPException(status_code=422, detail=f"cannot compile graph: {exc}") from exc

    if format == "zip":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel, content in bundle.files.items():
                zf.writestr(f"{bundle.name}/{rel}", content)
        return Response(
            content=buf.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{bundle.name}-nextflow.zip"'},
        )

    # A quick DAG summary (topological order) parsed from the generated README's Steps section.
    steps = [
        line.split("`")[1]
        for line in bundle.files["README.md"].splitlines()
        if re.match(r"^\d+\. `", line)
    ]
    return CompileResponse(
        name=bundle.name, files=bundle.files, main_nf=bundle.main_nf, steps=steps
    )
