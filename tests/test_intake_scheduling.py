"""Intake authored-pipeline execution + the operator processing gate (ADR-0021).

Covers the two things ``POST /api/runs`` gained on top of the seeded-germline default:

  1. **Authored pipeline for real runs** — an optional ``pipeline`` NAME resolves + compiles that
     saved pipeline's approver-blessed baseline via the SAME approval gate as ``POST
     /api/pipelines/run`` (409 if unapproved), and sample processing runs THAT graph (the compiled
     ``main.nf`` the driver receives via ``--pipeline``). Absent → the germline-panel default
     (backward-compatible).
  2. **Pause / schedule gate** — ``mode=hold``/``schedule`` registers the run WITHOUT firing the
     driver (``held``/``scheduled`` state); ``POST /api/runs/{id}/release`` fires it later.

Offline + deterministic: the background driver (``_run_pipeline``) is monkeypatched to a capturing
no-op, so no thread runs Nextflow; the driver-argv construction is exercised directly against a
seeded job record with ``run_driver`` captured. Never runs ``nextflow``.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.routers.intake as intake
from api.job_store import KIND_INTAKE
from api.main import app

client = TestClient(app)

# Capture the real driver-thread body BEFORE any fixture monkeypatches the module attr to a no-op,
# so the argv-construction tests can call the unpatched implementation directly.
_ORIGINAL_RUN_PIPELINE = intake._run_pipeline

_REVIEWER = {"X-PipeGuard-Role": "reviewer", "X-PipeGuard-Actor": "a.rivera"}
_VIEWER = {"X-PipeGuard-Role": "viewer", "X-PipeGuard-Actor": "v"}

# A minimal compilable authored graph (fastp → bwa-mem2), distinct from the germline default.
_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "n_fastp", "name": "fastp", "ins": ["fastq"], "outs": ["fastp_json", "fastq"]},
        {"id": "n_bwa", "name": "bwa-mem2", "ins": ["fastq", "reference_fasta"], "outs": ["bam"]},
    ],
    "edges": [{"from": {"node": "n_fastp", "idx": 1}, "to": {"node": "n_bwa", "idx": 0}}],
}


class _FakeStore:
    """In-memory PipelineGraphStore (only the methods the resolver / ``last_emitted`` reach)."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def get_versions(self, name: str) -> list[dict[str, Any]]:
        return sorted(
            (r for r in self._records if r.get("name") == name),
            key=lambda r: int(r.get("version") or 0),
        )

    def list(self, name: str | None = None) -> list[dict[str, Any]]:
        return [r for r in self._records if name is None or r.get("name") == name]

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        self._records.append(record)
        return record


def _record(name: str, version: int, *, approved: bool) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "id": f"{name}-{version}",
        "name": name,
        "version": version,
        "schema_version": "builder/0.1",
        "created_at": "2026-07-12T00:00:00+00:00",
        "graph": _GRAPH,
        "status": "approved" if approved else "draft",
    }
    if approved:
        rec["emitted_at"] = "2026-07-12T00:00:00+00:00"
    return rec


@pytest.fixture
def env(tmp_path: Any, monkeypatch: Any) -> dict[str, Any]:
    """Isolate the run dir, scratch, and job store into tmp; capture the fired driver thread."""
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(intake, "_DATA", data)
    monkeypatch.setattr(intake, "_NF_RUNS", tmp_path / ".nf-runs")
    monkeypatch.setenv("PIPEGUARD_JOB_STORE", "jsonl")
    monkeypatch.setenv("PIPEGUARD_JOB_PATH", str(tmp_path / "jobs.jsonl"))
    intake._active.clear()

    fired: list[str] = []
    monkeypatch.setattr(intake, "_run_pipeline", lambda run_id: fired.append(run_id))
    return {"data": data, "tmp": tmp_path, "fired": fired, "monkeypatch": monkeypatch}


def _seed_store(monkeypatch: Any, *records: dict[str, Any]) -> None:
    store = _FakeStore(list(records))
    monkeypatch.setattr(intake, "get_pipeline_store", lambda: store)


def _submit(**over: Any) -> Any:
    body = {
        "run_name": over.pop("run_name", "RUN-SCHED-1"),
        "platform": "NovaSeq X",
        "samples": [{"sample": "HG002"}],
    }
    body.update(over)
    return client.post("/api/runs", json=body, headers=_REVIEWER)


# --- 1. Authored pipeline for real runs -------------------------------------------------------


def test_authored_pipeline_immediate_compiles_and_fires_that_graph(env: dict[str, Any]) -> None:
    _seed_store(env["monkeypatch"], _record("panel-v2", 1, approved=True))
    resp = _submit(run_name="RUN-AUTHORED-OK", pipeline="panel-v2")
    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"
    # The driver thread fired for this run (immediate).
    assert env["fired"] == ["RUN-AUTHORED-OK"]
    # The persisted job records the authored pipeline + the compiled main.nf reflects THAT graph.
    job = intake.get_job_store().get("RUN-AUTHORED-OK", KIND_INTAKE)
    assert job is not None
    assert job["pipeline"] == "panel-v2" and job["mode"] == "immediate"
    main_nf = env["tmp"] / ".nf-runs" / "RUN-AUTHORED-OK" / "pipeline" / "main.nf"
    assert main_nf.is_file() and "BWA_MEM2_MEM(FASTP.out.fastq" in main_nf.read_text()


def test_authored_pipeline_unapproved_name_is_409(env: dict[str, Any]) -> None:
    _seed_store(env["monkeypatch"], _record("panel-v2", 1, approved=False))  # draft only
    resp = _submit(run_name="RUN-AUTHORED-DRAFT", pipeline="panel-v2")
    assert resp.status_code == 409 and "no approved version" in resp.json()["detail"]
    assert env["fired"] == []  # gate rejected before any thread


def test_authored_pipeline_unknown_name_is_409(env: dict[str, Any]) -> None:
    _seed_store(env["monkeypatch"])  # empty store
    resp = _submit(run_name="RUN-AUTHORED-UNK", pipeline="never-saved")
    assert resp.status_code == 409 and "no approved version" in resp.json()["detail"]


def test_run_driver_argv_carries_pipeline_when_authored(env: dict[str, Any]) -> None:
    # Exercise the real _run_pipeline argv construction against a seeded record (driver captured).
    captured: dict[str, Any] = {}

    def _fake_driver(cmd: list[str], *, cwd: str, env: dict[str, str]) -> Any:
        captured["cmd"] = cmd
        (env_dir := intake._DATA / "RUN-ARGV").mkdir(parents=True, exist_ok=True)
        (env_dir / "SampleSheet.csv").write_text("x", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    env["monkeypatch"].setattr(intake, "run_driver", _fake_driver)
    intake.get_job_store().upsert(
        {
            "kind": KIND_INTAKE,
            "run_id": "RUN-ARGV",
            "status": "queued",
            "created_at": intake.now_iso(),
            "updated_at": intake.now_iso(),
            "platform": "NovaSeq X",
            "run_date": "2026-07-12",
            "submitted_by": "a.rivera",
            "pipeline": "panel-v2",
            "pipeline_path": "/tmp/scratch/main.nf",
        }
    )
    # The fixture patched _run_pipeline to a no-op; call the ORIGINAL implementation here.
    _ORIGINAL_RUN_PIPELINE("RUN-ARGV")
    assert "--pipeline" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--pipeline") + 1] == "/tmp/scratch/main.nf"


def test_run_driver_argv_omits_pipeline_by_default(env: dict[str, Any]) -> None:
    captured: dict[str, Any] = {}

    def _fake_driver(cmd: list[str], *, cwd: str, env: dict[str, str]) -> Any:
        captured["cmd"] = cmd
        (env_dir := intake._DATA / "RUN-ARGV-DEF").mkdir(parents=True, exist_ok=True)
        (env_dir / "SampleSheet.csv").write_text("x", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    env["monkeypatch"].setattr(intake, "run_driver", _fake_driver)
    intake.get_job_store().upsert(
        {
            "kind": KIND_INTAKE,
            "run_id": "RUN-ARGV-DEF",
            "status": "queued",
            "created_at": intake.now_iso(),
            "updated_at": intake.now_iso(),
            "platform": "NovaSeq X",
            "run_date": "2026-07-12",
            "submitted_by": "a.rivera",
            "pipeline": None,
            "pipeline_path": None,
        }
    )
    _ORIGINAL_RUN_PIPELINE("RUN-ARGV-DEF")
    assert "--pipeline" not in captured["cmd"]


# --- 2. Pause / schedule gate -----------------------------------------------------------------


def test_hold_registers_without_firing(env: dict[str, Any]) -> None:
    resp = _submit(run_name="RUN-HOLD", mode="hold")
    assert resp.status_code == 202 and resp.json()["status"] == "held"
    assert env["fired"] == []  # the driver did NOT fire
    status = client.get("/api/runs/RUN-HOLD/intake-status").json()
    assert status["status"] == "held" and status["mode"] == "hold"
    assert "HG002" in status["processed_samples"]
    # A held job must NOT reconcile to 'lost' even though no thread is in _active.
    again = client.get("/api/runs/RUN-HOLD/intake-status").json()
    assert again["status"] == "held"


def test_release_fires_the_driver_and_marks_running(env: dict[str, Any]) -> None:
    _submit(run_name="RUN-REL", mode="hold")
    assert env["fired"] == []
    rel = client.post("/api/runs/RUN-REL/release", headers=_REVIEWER)
    assert rel.status_code == 202
    assert rel.json()["status"] == "running"
    assert env["fired"] == ["RUN-REL"]  # driver fired on release


def test_release_requires_reviewer_or_approver(env: dict[str, Any]) -> None:
    _submit(run_name="RUN-REL-RBAC", mode="hold")
    denied = client.post("/api/runs/RUN-REL-RBAC/release", headers=_VIEWER)
    assert denied.status_code == 403
    assert env["fired"] == []


def test_release_unknown_run_is_404(env: dict[str, Any]) -> None:
    assert client.post("/api/runs/NOPE/release", headers=_REVIEWER).status_code == 404


def test_release_non_parked_run_is_409(env: dict[str, Any]) -> None:
    _submit(run_name="RUN-IMM", mode="immediate")  # queued/immediate, not parked
    resp = client.post("/api/runs/RUN-IMM/release", headers=_REVIEWER)
    assert resp.status_code == 409 and "not held/scheduled" in resp.json()["detail"]


def test_schedule_parks_with_scheduled_at_and_does_not_fire(env: dict[str, Any]) -> None:
    when = "2026-07-15T09:00:00+00:00"
    resp = _submit(run_name="RUN-SCHED", mode="schedule", scheduled_at=when)
    assert resp.status_code == 202 and resp.json()["status"] == "scheduled"
    assert env["fired"] == []
    status = client.get("/api/runs/RUN-SCHED/intake-status").json()
    assert status["status"] == "scheduled" and status["scheduled_at"] == when
    # Released manually (auto-release is a deferred seam).
    rel = client.post("/api/runs/RUN-SCHED/release", headers=_REVIEWER)
    assert rel.status_code == 202 and rel.json()["status"] == "running"
    assert env["fired"] == ["RUN-SCHED"]


def test_schedule_without_scheduled_at_is_422(env: dict[str, Any]) -> None:
    resp = _submit(run_name="RUN-SCHED-BAD", mode="schedule")
    assert resp.status_code == 422 and "scheduled_at" in resp.json()["detail"]
    assert env["fired"] == []


def test_schedule_bad_timestamp_is_422(env: dict[str, Any]) -> None:
    resp = _submit(run_name="RUN-SCHED-TS", mode="schedule", scheduled_at="not-a-date")
    assert resp.status_code == 422 and "ISO-8601" in resp.json()["detail"]


# --- 3. Backward-compatibility -----------------------------------------------------------------


def test_default_submit_is_immediate_germline(env: dict[str, Any]) -> None:
    # No pipeline / no mode → the seeded germline default, fired immediately (unchanged behavior).
    resp = _submit(run_name="RUN-DEFAULT")
    assert resp.status_code == 202 and resp.json()["status"] == "queued"
    assert env["fired"] == ["RUN-DEFAULT"]
    job = intake.get_job_store().get("RUN-DEFAULT", KIND_INTAKE)
    assert job is not None
    assert job["pipeline"] is None and job["pipeline_path"] is None and job["mode"] == "immediate"


def test_duplicate_held_run_id_is_409(env: dict[str, Any]) -> None:
    # A parked (held) run reserves its id: a second submit of the same id is a 409, not overwritten.
    assert _submit(run_name="RUN-DUP", mode="hold").status_code == 202
    assert _submit(run_name="RUN-DUP", mode="hold").status_code == 409
