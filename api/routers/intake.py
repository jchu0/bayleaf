"""Intake / run-submission router — the app's execution boundary (``POST /api/runs``).

The Submit-samplesheet screen registers a run and hands off here; this endpoint TRIGGERS the
external pipeline driver (``scripts/run_giab_pipeline.py``) as a background subprocess and the
resulting ``data/<run_id>/`` becomes gate-able. The driver is **Nextflow-first** (ADR-0003): it
runs ``pipelines/germline/main.nf`` — the SAME pipeline the Pipeline Builder compiles from its
cards — via ``nextflow run``, then parses the published QC outputs into the run dir. **compose ≠
execute holds at the core:** ``src/bayleaf/`` never runs a tool — the API layer triggers the
external driver, which orchestrates the toolchain through Nextflow. The driver needs ``nextflow`` +
a JRE + the bioconda tools on PATH; inject the env bin via ``BAYLEAF_BIOCONDA_BIN`` (a plain
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
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from api.auth import Actor, require_role
from api.authored_pipeline import (
    check_inputs_suppliable,
    check_parse_contract,
    compile_record,
    materialize_bundle,
    resolve_approved,
)
from api.job_store import (
    HELD_STATUSES,
    KIND_INTAKE,
    TERMINAL_STATUSES,
    get_job_store,
    now_iso,
    run_driver,
)
from api.pipeline_store import get_pipeline_store

router = APIRouter(prefix="/api", tags=["intake"])

_REPO = Path(__file__).resolve().parent.parent.parent
_DATA = _REPO / "data"
_NF_RUNS = _REPO / ".nf-runs"
_SCRIPT = _REPO / "scripts" / "run_giab_pipeline.py"
# The only sample with real panel reads on disk (see run_giab_pipeline.py). A real multi-sample
# run would need the other GIAB reads fetched + a multi-sample pipeline — out of scope.
_FIXTURE_SAMPLES = {"HG002"}
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# The external input KINDS intake can actually supply: it always hands the driver the fixed HG002
# germline defaults (reads + reference + panel BED — see ``scripts/run_giab_pipeline.py``), with no
# operator input picker. An authored pipeline whose ``required_inputs`` exceeds this set can't run
# here (it would silently fall back to the HG002 defaults), so it is rejected at submit (WS-09 #2).
_INTAKE_SUPPLIABLE_KINDS: frozenset[str] = frozenset({"fastq", "reference_fasta", "panel_bed"})

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
    """The samplesheet a Submit hands off — registration metadata + the samples to process.

    ``pipeline`` (ADR-0021): the NAME of a saved, approver-blessed pipeline to run this run's
    samples through. Present → sample processing runs THAT authored pipeline (resolved + compiled
    via the same approval gate as ``POST /api/pipelines/run``; a 409 if the name has no approved
    version). Absent → the committed ``germline-panel`` reference the driver defaults to.

    ``mode`` (ADR-0021): the processing gate. ``immediate`` (default) fires the driver now;
    ``hold`` registers the run WITHOUT firing (an operator releases it later); ``schedule`` stores
    ``scheduled_at`` and parks the run the same way (a time-based auto-release is a DEFERRED seam —
    an operator releases it manually via ``POST /api/runs/{id}/release``).
    """

    model_config = ConfigDict(extra="forbid")
    run_name: str
    study: str = ""
    assay: str = ""
    platform: str = "NovaSeq X"
    samples: list[SampleIn]
    # Optional authored-pipeline name + pinned approved version (else latest approved).
    pipeline: str | None = None
    pipeline_version: int | None = None
    # Processing gate. ``scheduled_at`` is an ISO-8601 timestamp, required when mode == schedule.
    mode: Literal["immediate", "hold", "schedule"] = "immediate"
    scheduled_at: str | None = None


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
    # ADR-0021 processing-gate fields (additive; an older persisted job yields the defaults).
    # ``mode`` is the requested gate; ``scheduled_at`` is set only for a scheduled run; ``pipeline``
    # names the authored pipeline this run runs (``None`` → the germline-panel reference default).
    mode: str = "immediate"
    scheduled_at: str | None = None
    pipeline: str | None = None


def _bioconda_env() -> dict[str, str]:
    """Prepend BAYLEAF_BIOCONDA_BIN to PATH so the driver finds fastp/bwa-mem2/samtools/..."""
    env = dict(os.environ)
    bin_dir = os.environ.get("BAYLEAF_BIOCONDA_BIN", "").strip()
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
    if job.get("status") in HELD_STATUSES:
        # Operator-parked (hold/schedule): it INTENTIONALLY never launched a thread, so it is not in
        # ``_active`` — but it is not lost either. Return it as-is (release fires the driver later).
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


def _run_pipeline(run_id: str) -> None:
    """Background job: drive the external pipeline, then flip the job to complete/failed.

    Reads the driver params (platform / run_date / submitted_by / the optional compiled authored
    ``pipeline_path``) from the persisted job record, so an ``immediate`` submit and a later manual
    ``release`` of a held/scheduled run take the exact same path.
    """
    rec = get_job_store().get(run_id, KIND_INTAKE) or {}
    platform = str(rec.get("platform") or "")
    run_date = str(rec.get("run_date") or date.today().isoformat())
    submitted_by = str(rec.get("submitted_by") or "")
    pipeline_path = rec.get("pipeline_path")
    _mark(run_id, "running")
    cmd = [
        sys.executable, str(_SCRIPT), "--run-id", run_id, "--platform", platform,
        "--run-date", run_date, "--submitted-by", submitted_by,
    ]  # fmt: skip
    # Present → run the operator's approved authored pipeline; absent → the driver's committed
    # germline-panel reference default (backward-compatible). compose ≠ execute holds at the core.
    if pipeline_path:
        cmd += ["--pipeline", str(pipeline_path)]
    try:
        proc = run_driver(cmd, cwd=str(_REPO), env=_bioconda_env())
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


def _prepare_authored_pipeline(run_id: str, name: str, version: int | None) -> str:
    """Resolve + compile the named APPROVED pipeline and materialize it to this run's scratch.

    The SAME approval gate as ``POST /api/pipelines/run`` (ADR-0014/0021): a 409 if the name has no
    approved version, a 422 if the approved graph won't compile / has no tool node. Returns the path
    to the compiled ``main.nf`` the driver runs via ``--pipeline``. Never a raw client graph.

    WS-09 fail-fast: before materializing, validate the compiled graph against what intake can
    actually run — its required external inputs must all be HG002 defaults intake supplies
    (:func:`check_inputs_suppliable`), and its declared outputs must satisfy the frozen-five parse
    contract (:func:`check_parse_contract`). Either fails with a 422 UP FRONT, so a non-gate-able or
    unfillable authored graph never launches a full Nextflow compute that would die at parse.
    """
    record = resolve_approved(get_pipeline_store(), name, version)
    graph, bundle = compile_record(record, name)
    check_inputs_suppliable(graph, name, _INTAKE_SUPPLIABLE_KINDS)
    check_parse_contract(graph, name)
    main_nf = materialize_bundle(bundle, _NF_RUNS / run_id / "pipeline")
    return str(main_nf)


@router.post("/runs", status_code=202)
def submit_run(
    body: SubmitRunIn, actor: Actor = Depends(require_role("reviewer", "approver"))
) -> SubmitRunAck:
    """Register a run + gate processing (ADR-0021). Returns 202 immediately; poll intake-status.

    ``pipeline`` runs an operator-authored approved pipeline (else the germline-panel default);
    ``mode`` decides whether the driver fires now (``immediate``), is parked for a manual release
    (``hold``), or is scheduled (``schedule`` + ``scheduled_at``, released manually — auto-release
    is a deferred seam). Running a non-default authored pipeline still requires reviewer/approver
    (the endpoint gate). An authored pipeline is validated at SUBMIT against what intake can run —
    its required inputs must be HG002 defaults intake supplies AND its outputs must satisfy the
    frozen-five parse contract — so a non-gate-able / unfillable graph is a 422 up front, never a
    full compute that dies at parse (WS-09). compose ≠ execute holds at the core — only the driver
    shells out."""
    run_id = body.run_name.strip()
    if not _RUN_ID_RE.match(run_id):
        run_id = re.sub(r"[^A-Za-z0-9._-]+", "-", body.run_name).strip("-") or "RUN"
    if (_DATA / run_id).exists():  # fast pre-check (the authoritative one is under _lock below)
        raise HTTPException(status_code=409, detail=f"run '{run_id}' already exists")

    if body.mode == "schedule":
        raw = (body.scheduled_at or "").strip()
        if not raw:
            raise HTTPException(status_code=422, detail="mode 'schedule' requires 'scheduled_at'")
        try:  # validate it parses as ISO-8601 (tolerate a trailing 'Z')
            datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=422, detail="scheduled_at must be an ISO-8601 timestamp"
            ) from None

    submitted = [s.sample for s in body.samples]
    processed = [s for s in submitted if s in _FIXTURE_SAMPLES]
    skipped = [s for s in submitted if s not in _FIXTURE_SAMPLES]
    if not processed:
        raise HTTPException(
            status_code=422,
            detail="no processable sample — only HG002 has panel reads on disk for this demo",
        )

    # Resolve + compile the authored pipeline (if named) BEFORE reserving the run id, so a 409/422
    # from the approval gate leaves no half-registered job. Absent → the driver's germline default.
    pipeline_path = (
        _prepare_authored_pipeline(run_id, body.pipeline, body.pipeline_version)
        if body.pipeline
        else None
    )

    # The processing gate (ADR-0021): immediate fires the driver now; hold/schedule register the run
    # WITHOUT launching a thread (an operator releases it later). Initial status mirrors the mode.
    initial_status = {"immediate": "queued", "hold": "held", "schedule": "scheduled"}[body.mode]

    now = now_iso()
    # Per-sample job state (W4): a processed sample starts at the run's initial status (it tracks
    # the run's lifecycle); a skipped sample is ``skipped`` up front (no reads on disk, never runs).
    # Order follows the submitted samplesheet so the UI can render them in the operator's order.
    sample_states = [
        {"sample": s, "status": initial_status if s in _FIXTURE_SAMPLES else "skipped"}
        for s in submitted
    ]
    record = {
        "kind": KIND_INTAKE,
        "run_id": run_id,
        "status": initial_status,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "processed": processed,
        "skipped": skipped,
        "samples": sample_states,
        # Driver params, persisted so a later manual release fires the driver identically.
        "platform": body.platform,
        "run_date": date.today().isoformat(),
        "submitted_by": actor.id,
        "pipeline": body.pipeline,
        "pipeline_path": pipeline_path,
        "mode": body.mode,
        "scheduled_at": body.scheduled_at,
    }
    # Reserve the run id + persist the job ATOMICALLY under the lock: re-check the run dir, the
    # in-flight reservation set, AND any persisted PARKED (held/scheduled) job together — two
    # concurrent submits of the same id can't both proceed. The parked-job check is what covers a
    # held/scheduled run: it has no data dir and is not in ``_active`` (no thread), so neither of
    # the other two guards would catch a duplicate of it. A stale queued/running persisted job
    # (owner process died) is deliberately NOT a conflict — ``_reconcile`` resolves it to
    # complete/lost, and blocking a fresh resubmit on it would strand the run id. Only an
    # ``immediate`` run reserves ``_active`` (it launches a thread); a parked run is registered
    # without one.
    conflict = False
    with _lock:
        existing = get_job_store().get(run_id, KIND_INTAKE)
        if (
            (_DATA / run_id).exists()
            or run_id in _active
            or (existing is not None and existing.get("status") in HELD_STATUSES)
        ):
            conflict = True
        else:
            if body.mode == "immediate":
                _active.add(run_id)
            get_job_store().upsert(record)
    if conflict:
        raise HTTPException(status_code=409, detail=f"run '{run_id}' already exists")

    if body.mode == "immediate":
        threading.Thread(target=_run_pipeline, args=(run_id,), daemon=True).start()
    return SubmitRunAck(
        run_id=run_id,
        status=initial_status,
        processed_samples=processed,
        skipped_samples=skipped,
    )


@router.post("/runs/{run_id}/release", status_code=202)
def release_run(
    run_id: str, actor: Actor = Depends(require_role("reviewer", "approver"))
) -> IntakeStatus:
    """Release a HELD or SCHEDULED run → fire the driver now (ADR-0021).

    The manual counterpart to a time-based auto-release scheduler (a DEFERRED seam): an operator
    decides a parked run may process now. Only a ``held``/``scheduled`` job is releasable — a 404 if
    unknown, a 409 if it is already queued/running/terminal. Requires reviewer/approver."""
    job = get_job_store().get(run_id, KIND_INTAKE)
    if job is None:
        raise HTTPException(status_code=404, detail=f"no intake job for '{run_id}'")
    if job.get("status") not in HELD_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"run '{run_id}' is not held/scheduled (status={job.get('status')})",
        )
    # Reserve in ``_active`` BEFORE flipping off the parked status, so a concurrent poll never sees
    # a non-parked job not in ``_active`` and mis-reconciles the now-live run as lost. Then fire the
    # driver thread (which reads the persisted driver params + re-marks running, idempotently).
    with _lock:
        _active.add(run_id)
    _mark(run_id, "running")
    threading.Thread(target=_run_pipeline, args=(run_id,), daemon=True).start()
    job = get_job_store().get(run_id, KIND_INTAKE) or job
    return _status_out(run_id, job)


def _status_out(run_id: str, job: dict[str, Any]) -> IntakeStatus:
    """Project a persisted job record into the wire ``IntakeStatus``."""
    return IntakeStatus(
        run_id=run_id,
        status=job["status"],
        error=job.get("error"),
        processed_samples=job.get("processed", []),
        skipped_samples=job.get("skipped", []),
        samples=[SampleStatus(**s) for s in job.get("samples", [])],
        mode=str(job.get("mode") or "immediate"),
        scheduled_at=job.get("scheduled_at"),
        pipeline=job.get("pipeline"),
    )


@router.get("/runs/{run_id}/intake-status")
def intake_status(run_id: str) -> IntakeStatus:
    """queued | held | scheduled | running | complete | failed | lost (or complete if on disk)."""
    job = get_job_store().get(run_id, KIND_INTAKE)
    if job is None:
        if (_DATA / run_id / "SampleSheet.csv").exists():
            return IntakeStatus(run_id=run_id, status="complete")
        raise HTTPException(status_code=404, detail=f"no intake job for '{run_id}'")
    job = _reconcile(run_id, job)
    return _status_out(run_id, job)
