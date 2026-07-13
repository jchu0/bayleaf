"""Operator-driven EXECUTION of a Builder-composed pipeline (ADR-0003).

An operator composes a pipeline in the Builder and RUNS it here: this compiles the card graph to a
real Nextflow pipeline, then triggers ``scripts/run_giab_pipeline.py`` (the Nextflow-first driver)
against the operator's CHOSEN inputs as a background job — producing a gate-able ``data/<run_id>/``.

Human operators absolutely CAN execute (that is the point). The guardrails this respects are the
*other* two: AI **agents** stay advisory (never run a tool or set a verdict, ADR-0001), and the
decision **core** (``src/bayleaf/``) stays framework-agnostic (never shells out) — the execution
is orchestrated by Nextflow from this API/driver layer, exactly like the intake endpoint.

Only an APPROVED pipeline version runs (the approval gate, ADR-0014): the body NAMES a saved
pipeline, and the run compiles + executes that pipeline's approver-blessed (``emitted``) baseline
resolved from the pipeline store — never a raw client-posted graph, so an unapproved draft can't
run. Inputs are chosen by KEY from a server-side catalog of what is actually present (never a raw
client path — traversal-safe by construction). The graph's required input kinds are validated
against what the operator supplied, so a run can't start missing its reads/reference.
"""

from __future__ import annotations

import os
import re
import sys
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.agent_binding_store import get_agent_binding_store, normalize_bindings
from api.auth import Actor, require_role
from api.authored_pipeline import check_parse_contract, compile_record, resolve_approved
from api.job_store import (
    KIND_BUILDER_RUN,
    TERMINAL_STATUSES,
    get_job_store,
    now_iso,
    run_driver,
)
from api.pipeline_store import get_pipeline_store
from bayleaf.nextflow import required_inputs

# ``resolve_approved`` (the approval gate) and the graph→NfGraph adapter now live in
# ``api.authored_pipeline`` so the intake sample-processing path shares this exact resolve+compile
# mechanism (never a raw client graph). Re-exported here under the old private name so the rest of
# this router (and any test that reaches ``pr._resolve_approved``) is unchanged.
_resolve_approved = resolve_approved

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


# Run ids THIS process has reserved (a thread was — or is about to be — launched for them). Guarded
# by ``_lock``, it does double duty exactly like the intake router's set: (1) the ATOMIC
# duplicate-run-id guard — a run id is claimed under the lock before it is released, so two
# concurrent submits of the same id can't both proceed; (2) restart RECOVERY — a persisted
# non-terminal job whose id is NOT in this set was launched by a process that has since died, and
# ``_reconcile`` resolves it honestly (complete if the run dir is on disk, else lost). Job state
# itself is DURABLE in ``api/job_store.py`` — it survives a restart, closing the poller-hang gap.
_active: set[str] = set()
_lock = threading.Lock()


def _bioconda_env() -> dict[str, str]:
    """Prepend BAYLEAF_BIOCONDA_BIN to PATH so the driver finds nextflow + the bioconda tools."""
    env = dict(os.environ)
    bin_dir = os.environ.get("BAYLEAF_BIOCONDA_BIN", "").strip()
    if bin_dir:
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    return env


def _mark(run_id: str, status: str, *, error: str | None = None) -> None:
    """Persist a job status transition (queued → running → complete/failed). A no-op if the record
    has gone (never in normal flow — the record is written before the thread starts)."""
    store = get_job_store()
    rec = store.get(run_id, KIND_BUILDER_RUN)
    if rec is None:
        return
    rec["status"] = status
    rec["updated_at"] = now_iso()
    if error is not None:
        rec["error"] = error
    store.upsert(rec)


def _reconcile(run_id: str, job: dict[str, Any]) -> dict[str, Any]:
    """Resolve a persisted job that may have outlived the process that launched it (restart).

    A terminal job is returned as-is; a non-terminal job whose id IS in this process's ``_active``
    set is genuinely in-flight → returned as-is. Otherwise a prior process died mid-run: the run
    finished if its dir is on disk (→ ``complete``), else the work is gone (→ ``lost``). The
    reconciliation is persisted so subsequent polls see a stable terminal state.
    """
    if job.get("status") in TERMINAL_STATUSES:
        return job
    with _lock:
        live = run_id in _active
    if live:
        return job
    if (_DATA / run_id / "SampleSheet.csv").exists():
        job["status"] = "complete"
    else:
        job["status"] = "lost"
        job["error"] = job.get("error") or "job owner process is gone (backend restarted mid-run)"
    job["updated_at"] = now_iso()
    get_job_store().upsert(job)
    return job


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
    # Run the APPROVED baseline of THIS saved pipeline (never a raw posted graph) — the approval
    # gate: only an approver-blessed version may execute (ADR-0014/0001). `name` is the saved
    # pipeline's slug; `version` optionally pins an exact approved revision (else latest approved).
    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    version: int | None = Field(default=None, ge=1)
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
    """Run a saved pipeline's APPROVED baseline via Nextflow against the operator's chosen inputs
    (202; poll ``GET /api/pipelines/run/{run_id}``). The approval gate (ADR-0014): the body NAMES a
    saved pipeline — the run compiles + executes that pipeline's approver-blessed (``emitted``)
    snapshot from the store, so an unapproved draft can never run (409 if none). Compose ≠ execute
    holds at the CORE — the driver, not ``src/bayleaf/``, orchestrates Nextflow."""
    run_id = body.run_id.strip()
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=422, detail="run_id must be a slug (A-Za-z0-9._-)")
    if (_DATA / run_id).exists():
        raise HTTPException(status_code=409, detail=f"run '{run_id}' already exists")

    # The approval gate: resolve the approved (emitted) snapshot for this name and compile THAT
    # graph — never a client-posted one (409 if the pipeline has no approved version, ADR-0014).
    # ``resolve_approved`` + ``compile_record`` are the shared mechanism the intake path reuses.
    record = resolve_approved(get_pipeline_store(), body.name, body.version)
    graph, bundle = compile_record(record, body.name)

    # Parity with the intake path (WS-09 #1 / audit G8): reject an approved pipeline whose outputs
    # can't yield a gate-able card BEFORE launching the driver. Without this, a graph missing a
    # frozen-five stage runs to completion in Nextflow and only THEN dies at parse — a full compute
    # burn for a `failed` run. A structural check needing no tools, so it's cheap and offline-safe.
    check_parse_contract(graph, body.name)

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
    # Reserve the run id + persist the queued job ATOMICALLY under the lock (re-checking the run dir
    # and the in-flight reservation set together), so two concurrent same-id submits can't both
    # launch a thread — only the winner registers; the loser gets a 409 (the concurrent duplicate
    # compiles harmlessly to the same idempotent scratch files before losing the reservation).
    now = now_iso()
    conflict = False
    with _lock:
        if (_DATA / run_id).exists() or run_id in _active:
            conflict = True
        else:
            _active.add(run_id)
            get_job_store().upsert(
                {
                    "kind": KIND_BUILDER_RUN,
                    "run_id": run_id,
                    "status": "queued",
                    "error": None,
                    "created_at": now,
                    "updated_at": now,
                    "steps": steps,
                }
            )
    if conflict:
        raise HTTPException(status_code=409, detail=f"run '{run_id}' already exists")

    # Scope-by-wiring (ADR-0024): snapshot THIS run's executed-graph agent bindings so the
    # node-observation read path can enforce that an agent only reads nodes it is wired to. The
    # bindings ride in the approved graph's opaque envelope (graph.agent_bindings); the compiler
    # never dereferenced them (ADR-0022) — here they become the run's server-side access record.
    get_agent_binding_store().record(
        run_id,
        normalize_bindings((record.get("graph") or {}).get("agent_bindings")),
        captured_at=now,
    )

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
    _mark(run_id, "running")
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
        proc = run_driver(cmd, cwd=str(_REPO), env=_bioconda_env())
        ok = proc.returncode == 0 and (_DATA / run_id / "SampleSheet.csv").exists()
        if ok:
            _mark(run_id, "complete")
        else:
            tail = (proc.stderr or proc.stdout or "run failed").strip()
            _mark(run_id, "failed", error=tail[-400:])
    except Exception as e:  # incl. a driver timeout (the process group is already reaped)
        _mark(run_id, "failed", error=str(e)[-400:])
    finally:
        # Release the reservation only AFTER the terminal status is persisted (see the intake router
        # for why the ordering matters — a concurrent poll must never mis-reconcile a live run).
        with _lock:
            _active.discard(run_id)


@router.get("/pipelines/run/{run_id}")
def run_status(run_id: str) -> RunStatusOut:
    """queued | running | complete | failed | lost for a Builder run (or complete if on disk).

    The disk fallback mirrors the intake router: a run whose job record is unknown to this store but
    whose result dir is already on disk reads ``complete`` rather than a misleading 404.
    """
    job = get_job_store().get(run_id, KIND_BUILDER_RUN)
    if job is None:
        if (_DATA / run_id / "SampleSheet.csv").exists():
            return RunStatusOut(run_id=run_id, status="complete")
        raise HTTPException(status_code=404, detail=f"no run job '{run_id}'")
    job = _reconcile(run_id, job)
    return RunStatusOut(run_id=run_id, status=job["status"], error=job.get("error"))
