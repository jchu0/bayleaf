"""Intake / run-submission router — the app's execution boundary (``POST /api/runs``).

The Submit-samplesheet screen registers a run and hands off here; this endpoint TRIGGERS the
external pipeline driver (``scripts/run_giab_pipeline.py``) as a background subprocess and the
resulting ``data/<run_id>/`` becomes gate-able. **compose ≠ execute holds at the core:**
``src/pipeguard/`` never runs a tool — the API layer triggers the external driver, exactly like
the Pipeline Builder's Nextflow hand-off. The driver needs the bioconda toolchain on PATH; inject
it via ``PIPEGUARD_BIOCONDA_BIN`` (a plain ``uv run uvicorn`` without it fails every submit).

Demo scope: only ``HG002`` has real panel reads on disk, so the endpoint processes exactly the
samples in a server-side fixture registry and reports the rest as honestly *skipped* (registered,
not processed) — never fabricating a run for a sample with no reads.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from api.auth import Actor, require_role

router = APIRouter(prefix="/api", tags=["intake"])

_REPO = Path(__file__).resolve().parent.parent.parent
_DATA = _REPO / "data"
_SCRIPT = _REPO / "scripts" / "run_giab_pipeline.py"
# The only sample with real panel reads on disk (see run_giab_pipeline.py). A real multi-sample
# run would need the other GIAB reads fetched + a multi-sample pipeline — out of scope.
_FIXTURE_SAMPLES = {"HG002"}
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass
class _Job:
    status: str  # queued | running | complete | failed
    processed: list[str]
    skipped: list[str]
    error: str | None = None


# In-process job registry (dict + lock) — a demo-scale analogue of a real orchestrator's job store.
_jobs: dict[str, _Job] = {}
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


class IntakeStatus(BaseModel):
    run_id: str
    status: str
    error: str | None = None
    processed_samples: list[str] = []
    skipped_samples: list[str] = []


def _bioconda_env() -> dict[str, str]:
    """Prepend PIPEGUARD_BIOCONDA_BIN to PATH so the driver finds fastp/bwa-mem2/samtools/..."""
    env = dict(os.environ)
    bin_dir = os.environ.get("PIPEGUARD_BIOCONDA_BIN", "").strip()
    if bin_dir:
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    return env


def _run_pipeline(run_id: str, platform: str, run_date: str, submitted_by: str) -> None:
    """Background job: drive the external pipeline, then flip the job to complete/failed."""
    with _lock:
        _jobs[run_id].status = "running"
    try:
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT), "--run-id", run_id, "--platform", platform,
             "--run-date", run_date, "--submitted-by", submitted_by],
            cwd=str(_REPO), env=_bioconda_env(), capture_output=True, text=True, timeout=900,
        )  # fmt: skip
        ok = proc.returncode == 0 and (_DATA / run_id / "SampleSheet.csv").exists()
        with _lock:
            if ok:
                _jobs[run_id].status = "complete"
            else:
                tail = (proc.stderr or proc.stdout or "pipeline failed").strip()
                _jobs[run_id].status = "failed"
                _jobs[run_id].error = tail[-400:]
    except Exception as e:
        with _lock:
            _jobs[run_id].status = "failed"
            _jobs[run_id].error = str(e)[-400:]


@router.post("/runs", status_code=202)
def submit_run(
    body: SubmitRunIn, actor: Actor = Depends(require_role("reviewer", "approver"))
) -> SubmitRunAck:
    """Register a run + kick off processing. Returns 202 immediately; poll intake-status."""
    run_id = body.run_name.strip()
    if not _RUN_ID_RE.match(run_id):
        run_id = re.sub(r"[^A-Za-z0-9._-]+", "-", body.run_name).strip("-") or "RUN"
    if (_DATA / run_id).exists():
        raise HTTPException(status_code=409, detail=f"run '{run_id}' already exists")

    submitted = [s.sample for s in body.samples]
    processed = [s for s in submitted if s in _FIXTURE_SAMPLES]
    skipped = [s for s in submitted if s not in _FIXTURE_SAMPLES]
    if not processed:
        raise HTTPException(
            status_code=422,
            detail="no processable sample — only HG002 has panel reads on disk for this demo",
        )

    with _lock:
        _jobs[run_id] = _Job(status="queued", processed=processed, skipped=skipped)
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
    """queued | running | complete | failed for a submitted run (or complete if it's on disk)."""
    with _lock:
        job = _jobs.get(run_id)
    if job is None:
        if (_DATA / run_id / "SampleSheet.csv").exists():
            return IntakeStatus(run_id=run_id, status="complete")
        raise HTTPException(status_code=404, detail=f"no intake job for '{run_id}'")
    return IntakeStatus(
        run_id=run_id,
        status=job.status,
        error=job.error,
        processed_samples=job.processed,
        skipped_samples=job.skipped,
    )
