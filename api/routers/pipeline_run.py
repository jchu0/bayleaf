"""Operator-driven EXECUTION of a Builder-composed pipeline (ADR-0003).

An operator composes a pipeline in the Builder and RUNS it here: this compiles the card graph to a
real Nextflow pipeline, then triggers ``scripts/run_giab_pipeline.py`` (the Nextflow-first driver)
against the operator's CHOSEN inputs as a background job — producing a gate-able ``data/<run_id>/``.

Human operators absolutely CAN execute (that is the point). The guardrails this respects are the
*other* two: AI **agents** stay advisory (never run a tool or set a verdict, ADR-0001), and the
decision **core** (``src/pipeguard/``) stays framework-agnostic (never shells out) — the execution
is orchestrated by Nextflow from this API/driver layer, exactly like the intake endpoint.

Inputs are chosen by KEY from a server-side catalog of what is actually present (never a raw
client path — traversal-safe by construction). The graph's required input kinds are validated
against what the operator supplied, so a run can't start missing its reads/reference.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from api.auth import Actor, require_role
from api.routers.nextflow import CompileRequest
from pipeguard.nextflow import NfEdge, NfGraph, NfNode, compile_graph, required_inputs
from pipeguard.nextflow.compiler import CompileError

router = APIRouter(prefix="/api", tags=["pipeline-run"])

_REPO = Path(__file__).resolve().parent.parent.parent
_DATA = _REPO / "data"
_NF_RUNS = _REPO / ".nf-runs"
_SCRIPT = _REPO / "scripts" / "run_giab_pipeline.py"
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# The artifact kinds an operator supplies, mapped to the input category they satisfy. Only these
# kinds are operator-suppliable; any other required kind means the graph can't be run here yet.
_KIND_TO_CATEGORY = {"fastq": "reads", "reference_fasta": "reference", "panel_bed": "panel_bed"}


@dataclass(frozen=True)
class _InputOption:
    key: str
    label: str
    origin: str
    paths: tuple[Path, ...]  # reads = (R1, R2); reference/panel = (file,)


# The server-side input catalog — what is actually on disk for this demo. Real data only; a run
# against arbitrary uploaded reads is a labelled seam (no upload path exists yet).
def _catalog() -> dict[str, list[_InputOption]]:
    giab = _DATA / "real-giab"
    raw: dict[str, list[_InputOption]] = {
        "reads": [
            _InputOption(
                "hg002-panel",
                "GIAB HG002 panel reads (real)",
                "real-giab",
                (giab / "fastq" / "HG002.R1.fastq.gz", giab / "fastq" / "HG002.R2.fastq.gz"),
            )
        ],
        "reference": [
            _InputOption(
                "grch38-chr20",
                "GRCh38 chr20 — bwa-mem2 + faidx indexed",
                "real-giab",
                (giab / "ref" / "chr20.fa",),
            )
        ],
        "panel_bed": [
            _InputOption(
                "example-panel",
                "Example 13-window chr20 panel BED",
                "real-giab",
                (_REPO / "scripts" / "panel_regions.example.bed",),
            )
        ],
    }
    # Honest: only surface an option whose files are all present.
    return {cat: [o for o in opts if all(p.exists() for p in o.paths)] for cat, opts in raw.items()}


@dataclass
class _Job:
    status: str  # queued | running | complete | failed
    run_id: str
    error: str | None = None
    steps: list[str] = field(default_factory=list)


_jobs: dict[str, _Job] = {}
_lock = threading.Lock()


def _bioconda_env() -> dict[str, str]:
    """Prepend PIPEGUARD_BIOCONDA_BIN to PATH so the driver finds nextflow + the bioconda tools."""
    env = dict(os.environ)
    bin_dir = os.environ.get("PIPEGUARD_BIOCONDA_BIN", "").strip()
    if bin_dir:
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    return env


class InputOptionOut(BaseModel):
    key: str
    label: str
    origin: str


class RunInputsCatalog(BaseModel):
    reads: list[InputOptionOut]
    reference: list[InputOptionOut]
    panel_bed: list[InputOptionOut]


class RunInputsChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reads: str | None = None
    reference: str | None = None
    panel_bed: str | None = None


class RunPipelineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    graph: CompileRequest
    run_id: str
    sample: str = "HG002"
    platform: str = "HiSeq 2500"
    inputs: RunInputsChoice = RunInputsChoice()


class RunPipelineAck(BaseModel):
    run_id: str
    status: str
    steps: list[str]


class RunStatusOut(BaseModel):
    run_id: str
    status: str
    error: str | None = None


def _to_graph(req: CompileRequest) -> NfGraph:
    return NfGraph(
        name=req.name,
        nodes=[NfNode(id=n.id, tool=n.name, ins=list(n.ins), outs=list(n.outs)) for n in req.nodes],
        edges=[NfEdge(e.src.node, e.src.idx, e.to.node, e.to.idx) for e in req.edges],
    )


@router.get("/pipelines/run/inputs")
def list_run_inputs() -> RunInputsCatalog:
    """The server-side inputs an operator can pick from (only what is present on disk)."""
    cat = _catalog()

    def out(c: str) -> list[InputOptionOut]:
        return [InputOptionOut(key=o.key, label=o.label, origin=o.origin) for o in cat[c]]

    return RunInputsCatalog(
        reads=out("reads"), reference=out("reference"), panel_bed=out("panel_bed")
    )


@router.post("/pipelines/run", status_code=202)
def run_pipeline(
    body: RunPipelineIn,
    actor: Actor = Depends(require_role("reviewer", "approver")),
) -> RunPipelineAck:
    """Compile the operator's graph and RUN it via Nextflow against their chosen inputs (202; poll
    ``GET /api/pipelines/run/{run_id}``). Compose ≠ execute holds at the CORE — the driver, not
    ``src/pipeguard/``, orchestrates Nextflow."""
    run_id = body.run_id.strip()
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=422, detail="run_id must be a slug (A-Za-z0-9._-)")
    if (_DATA / run_id).exists():
        raise HTTPException(status_code=409, detail=f"run '{run_id}' already exists")

    graph = _to_graph(body.graph)
    try:
        bundle = compile_graph(graph)
    except CompileError as exc:
        raise HTTPException(status_code=422, detail=f"cannot compile graph: {exc}") from exc

    # Validate the operator supplied every input KIND the graph consumes, and resolve each choice to
    # a real server-side path by KEY (never a raw client path — traversal-safe).
    cat = _catalog()
    needed = {_KIND_TO_CATEGORY[k] for k in required_inputs(graph) if k in _KIND_TO_CATEGORY}
    unsupported = {k for k in required_inputs(graph) if k not in _KIND_TO_CATEGORY}
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail=f"graph needs input kind(s) not runnable here yet: {sorted(unsupported)}",
        )
    chosen: dict[str, _InputOption] = {}
    for category in needed:
        key = getattr(body.inputs, category)
        if not key:
            raise HTTPException(status_code=422, detail=f"missing input: choose a '{category}'")
        opt = next((o for o in cat[category] if o.key == key), None)
        if opt is None:
            raise HTTPException(status_code=422, detail=f"unknown {category} input '{key}'")
        chosen[category] = opt

    # Materialize the compiled pipeline next to its run scratch, then kick off the driver.
    pipeline_dir = _NF_RUNS / run_id / "pipeline"
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in bundle.files.items():
        out_path = pipeline_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")

    reads = chosen.get("reads")
    reference = chosen.get("reference")
    panel = chosen.get("panel_bed")
    origin = next((o.origin for o in chosen.values()), "unknown")

    steps = [
        line.split("`")[1]
        for line in bundle.files["README.md"].splitlines()
        if re.match(r"^\d+\. `", line)
    ]
    with _lock:
        _jobs[run_id] = _Job(status="queued", run_id=run_id, steps=steps)
    threading.Thread(
        target=_execute,
        args=(run_id, pipeline_dir / "main.nf", body.sample, body.platform, actor.id, origin,
              reads, reference, panel),
        daemon=True,
    ).start()  # fmt: skip
    return RunPipelineAck(run_id=run_id, status="queued", steps=steps)


def _execute(
    run_id: str,
    pipeline: Path,
    sample: str,
    platform: str,
    submitted_by: str,
    origin: str,
    reads: _InputOption | None,
    reference: _InputOption | None,
    panel: _InputOption | None,
) -> None:
    """Background job: run the compiled pipeline via the driver, then flip complete/failed."""
    with _lock:
        _jobs[run_id].status = "running"
    cmd = [
        sys.executable, str(_SCRIPT), "--run-id", run_id, "--pipeline", str(pipeline),
        "--sample", sample, "--platform", platform, "--run-date", date.today().isoformat(),
        "--submitted-by", submitted_by, "--origin", origin,
    ]  # fmt: skip
    if reads:
        cmd += ["--read1", str(reads.paths[0]), "--read2", str(reads.paths[1])]
    if reference:
        cmd += ["--reference", str(reference.paths[0])]
    if panel:
        cmd += ["--panel-bed", str(panel.paths[0])]
    try:
        proc = subprocess.run(
            cmd, cwd=str(_REPO), env=_bioconda_env(), capture_output=True, text=True, timeout=1800
        )
        ok = proc.returncode == 0 and (_DATA / run_id / "SampleSheet.csv").exists()
        with _lock:
            if ok:
                _jobs[run_id].status = "complete"
            else:
                _jobs[run_id].status = "failed"
                _jobs[run_id].error = (proc.stderr or proc.stdout or "run failed").strip()[-400:]
    except Exception as e:
        with _lock:
            _jobs[run_id].status = "failed"
            _jobs[run_id].error = str(e)[-400:]


@router.get("/pipelines/run/{run_id}")
def run_status(run_id: str) -> RunStatusOut:
    with _lock:
        job = _jobs.get(run_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"no run job '{run_id}'")
    return RunStatusOut(run_id=job.run_id, status=job.status, error=job.error)
