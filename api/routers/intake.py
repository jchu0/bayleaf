"""Intake / run-submission router — the app's execution boundary (``POST /api/runs``).

The Submit-samplesheet screen registers a run and hands off here; this endpoint TRIGGERS the
external pipeline driver (``scripts/run_giab_pipeline.py``) as a background subprocess and the
resulting ``data/<run_id>/`` becomes gate-able. The driver is **Nextflow-first** (ADR-0003): it
runs ``pipelines/germline/main.nf`` — the SAME pipeline the Pipeline Builder compiles from its
cards — via ``nextflow run``, then parses the published QC outputs into the run dir. **compose ≠
execute holds at the core:** ``src/pipeguard/`` never runs a tool — the API layer triggers the
external driver, which orchestrates the toolchain through Nextflow. The driver needs ``nextflow`` +
a JRE + the bioconda tools on PATH; inject the env bin via ``PIPEGUARD_BIOCONDA_BIN`` (a plain
``uv run uvicorn`` without it fails every submit).

Demo scope: only ``HG002`` has real panel reads on disk, so the endpoint processes exactly the
samples in a server-side fixture registry and reports the rest as honestly *skipped* (registered,
not processed) — never fabricating a run for a sample with no reads.

Job state is DURABLE (``api/job_store.py``): a job survives a backend restart, so a poll after a
restart recovers honestly (``complete`` if the run dir is on disk, else ``lost``) instead of hanging
on ``running`` forever. Duplicate-run-id and the driver launch are shared with the Builder-run
router: one atomic reservation guards the run id, and one process-group-aware helper reaps the whole
Nextflow/JVM subtree on a timeout.
"""

from __future__ import annotations

import os
import re
import sys
import threading
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from api.auth import Actor, require_role
from api.job_store import (
    KIND_INTAKE,
    TERMINAL_STATUSES,
    get_job_store,
    now_iso,
    run_driver,
)

router = APIRouter(prefix="/api", tags=["intake"])

_REPO = Path(__file__).resolve().parent.parent.parent
_DATA = _REPO / "data"
_SCRIPT = _REPO / "scripts" / "run_giab_pipeline.py"
# The only sample with real panel reads on disk (see run_giab_pipeline.py). A real multi-sample
# run would need the other GIAB reads fetched + a multi-sample pipeline — out of scope.
_FIXTURE_SAMPLES = {"HG002"}
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Run ids THIS process has reserved (a thread was — or is about to be — launched for them). Guarded
# by ``_lock``. It serves two jobs: (1) the ATOMIC duplicate-run-id guard — a run id is claimed here
# under the lock before the lock is released, so two concurrent submits of the same id can't both
# proceed; (2) restart RECOVERY — a persisted non-terminal job whose id is NOT in this set was
# launched by a process that has since died, so ``_reconcile`` resolves it honestly (see below).
_active: set[str] = set()
_lock = threading.Lock()


class SampleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample: str
    type: str = ""
    i7: str = ""
    i5: str = ""
    study: str = ""


class SubmitRunIn(BaseModel):
    """The samplesheet a Submit hands off — registration metadata + the samples to process."""

    model_config = ConfigDict(extra="forbid")
    run_name: str
    study: str = ""
    assay: str = ""
    platform: str = "NovaSeq X"
    samples: list[SampleIn]


class SubmitRunAck(BaseModel):
    run_id: str
    status: str
    processed_samples: list[str]
    skipped_samples: list[str]


class SampleStatus(BaseModel):
    """Per-sample job state for a (potentially multi-sample) submit. A ``processed`` sample tracks
    the run's lifecycle (queued → running → complete/failed/lost); a ``skipped`` sample never runs
    (no panel reads on disk), so its status is frozen at ``skipped``."""

    sample: str
    status: str


class IntakeStatus(BaseModel):
    run_id: str
    status: str
    error: str | None = None
    processed_samples: list[str] = []
    skipped_samples: list[str] = []
    # Per-sample progress for a multi-sample run (W4). Additive: an older persisted job with no
    # ``samples`` key simply yields an empty list. The run-level ``status`` above stays the summary.
    samples: list[SampleStatus] = []


def _bioconda_env() -> dict[str, str]:
    """Prepend PIPEGUARD_BIOCONDA_BIN to PATH so the driver finds fastp/bwa-mem2/samtools/..."""
    env = dict(os.environ)
    bin_dir = os.environ.get("PIPEGUARD_BIOCONDA_BIN", "").strip()
    if bin_dir:
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    return env


def _mirror_samples(rec: dict[str, Any], status: str) -> None:
    """Reflect a run-level transition onto each PROCESSED sample in the record's per-sample list.

    The driver runs the whole processed set in ONE Nextflow invocation, so per-sample state is
    coarse — every processed sample mirrors the run's status (queued → running → complete/failed).
    A ``skipped`` sample never ran, so its status is left frozen at ``skipped``. A record with no
    ``samples`` key (older jobs) is a no-op.
    """
    for s in rec.get("samples", []):
        if s.get("status") != "skipped":
            s["status"] = status


def _mark(run_id: str, status: str, *, error: str | None = None) -> None:
    """Persist a job status transition (queued → running → complete/failed). A no-op if the record
    has gone (never in normal flow — the record is written before the thread starts)."""
    store = get_job_store()
    rec = store.get(run_id, KIND_INTAKE)
    if rec is None:
        return
    rec["status"] = status
    rec["updated_at"] = now_iso()
    if error is not None:
        rec["error"] = error
    _mirror_samples(rec, status)
    store.upsert(rec)


def _reconcile(run_id: str, job: dict[str, Any]) -> dict[str, Any]:
    """Resolve a persisted job that may have outlived the process that launched it (restart).

    A terminal job is returned as-is. A non-terminal job whose id IS in this process's ``_active``
    set is genuinely in-flight here → returned as-is. Otherwise a prior process died mid-run: the
    run finished if its dir is on disk (→ ``complete``), else the work is gone (→ ``lost``). The
    reconciliation is persisted so subsequent polls (and the frontend) see a stable terminal state.
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
    _mirror_samples(job, job["status"])  # keep per-sample state consistent with the reconciliation
    get_job_store().upsert(job)
    return job


def _run_pipeline(run_id: str, platform: str, run_date: str, submitted_by: str) -> None:
    """Background job: drive the external pipeline, then flip the job to complete/failed."""
    _mark(run_id, "running")
    try:
        proc = run_driver(
            [sys.executable, str(_SCRIPT), "--run-id", run_id, "--platform", platform,
             "--run-date", run_date, "--submitted-by", submitted_by],
            cwd=str(_REPO), env=_bioconda_env(),
        )  # fmt: skip
        ok = proc.returncode == 0 and (_DATA / run_id / "SampleSheet.csv").exists()
        if ok:
            _mark(run_id, "complete")
        else:
            tail = (proc.stderr or proc.stdout or "pipeline failed").strip()
            _mark(run_id, "failed", error=tail[-400:])
    except Exception as e:  # incl. a driver timeout (the process group is already reaped)
        _mark(run_id, "failed", error=str(e)[-400:])
    finally:
        # Release the reservation only AFTER the terminal status is persisted, so a concurrent poll
        # never sees a non-terminal, not-in-``_active`` job and mis-reconciles a live run as lost.
        with _lock:
            _active.discard(run_id)


@router.post("/runs", status_code=202)
def submit_run(
    body: SubmitRunIn, actor: Actor = Depends(require_role("reviewer", "approver"))
) -> SubmitRunAck:
    """Register a run + kick off processing. Returns 202 immediately; poll intake-status."""
    run_id = body.run_name.strip()
    if not _RUN_ID_RE.match(run_id):
        run_id = re.sub(r"[^A-Za-z0-9._-]+", "-", body.run_name).strip("-") or "RUN"
    if (_DATA / run_id).exists():  # fast pre-check (the authoritative one is under _lock below)
        raise HTTPException(status_code=409, detail=f"run '{run_id}' already exists")

    submitted = [s.sample for s in body.samples]
    processed = [s for s in submitted if s in _FIXTURE_SAMPLES]
    skipped = [s for s in submitted if s not in _FIXTURE_SAMPLES]
    if not processed:
        raise HTTPException(
            status_code=422,
            detail="no processable sample — only HG002 has panel reads on disk for this demo",
        )

    # Reserve the run id + persist the queued job ATOMICALLY under the lock: re-check the run dir
    # and the in-flight reservation set together, so two concurrent submits of the same id can't
    # both proceed (only the winner registers + launches a thread; the loser gets a 409).
    now = now_iso()
    # Per-sample job state (W4): a processed sample starts ``queued`` (it will track the run's
    # lifecycle); a skipped sample is ``skipped`` up front (no reads on disk, it never runs). Order
    # follows the submitted samplesheet so the UI can render them in the operator's order.
    sample_states = [
        {"sample": s, "status": "queued" if s in _FIXTURE_SAMPLES else "skipped"} for s in submitted
    ]
    conflict = False
    with _lock:
        if (_DATA / run_id).exists() or run_id in _active:
            conflict = True
        else:
            _active.add(run_id)
            get_job_store().upsert(
                {
                    "kind": KIND_INTAKE,
                    "run_id": run_id,
                    "status": "queued",
                    "error": None,
                    "created_at": now,
                    "updated_at": now,
                    "processed": processed,
                    "skipped": skipped,
                    "samples": sample_states,
                }
            )
    if conflict:
        raise HTTPException(status_code=409, detail=f"run '{run_id}' already exists")

    threading.Thread(
        target=_run_pipeline,
        args=(run_id, body.platform, date.today().isoformat(), actor.id),
        daemon=True,
    ).start()
    return SubmitRunAck(
        run_id=run_id, status="queued", processed_samples=processed, skipped_samples=skipped
    )


@router.get("/runs/{run_id}/intake-status")
def intake_status(run_id: str) -> IntakeStatus:
    """queued | running | complete | failed | lost for a submitted run (or complete if on disk)."""
    job = get_job_store().get(run_id, KIND_INTAKE)
    if job is None:
        if (_DATA / run_id / "SampleSheet.csv").exists():
            return IntakeStatus(run_id=run_id, status="complete")
        raise HTTPException(status_code=404, detail=f"no intake job for '{run_id}'")
    job = _reconcile(run_id, job)
    return IntakeStatus(
        run_id=run_id,
        status=job["status"],
        error=job.get("error"),
        processed_samples=job.get("processed", []),
        skipped_samples=job.get("skipped", []),
        samples=[SampleStatus(**s) for s in job.get("samples", [])],
    )
