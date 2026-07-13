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

WS-09 (submit-time fail-fast): an authored pipeline is validated at SUBMIT against what intake can
actually run — its required external inputs must all be HG002 defaults intake supplies, and its
declared outputs must satisfy the frozen-five parse contract — so a non-gate-able graph is a 422 up
front instead of a full compute burn that dies at parse. These are asserted here.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
from fastapi.testclient import TestClient
from scripts.seed_approved_germline import germline_graph_dict

import api.routers.intake as intake
from api.job_store import KIND_INTAKE
from api.main import app

client = TestClient(app)

# Capture the real driver-thread body BEFORE any fixture monkeypatches the module attr to a no-op,
# so the argv-construction tests can call the unpatched implementation directly.
_ORIGINAL_RUN_PIPELINE = intake._run_pipeline

_REVIEWER = {"X-Bayleaf-Role": "reviewer", "X-Bayleaf-Actor": "a.rivera"}
_VIEWER = {"X-Bayleaf-Role": "viewer", "X-Bayleaf-Actor": "v"}

# The default authored graph for the happy-path tests: the FULL germline chain (produces the
# frozen-five outputs the post-run parse needs + consumes only HG002-default inputs), so it clears
# the WS-09 submit-time gate exactly like the committed reference does.
_GRAPH: dict[str, Any] = germline_graph_dict()

# A minimal compilable authored graph (fastp → bwa-mem2) that produces NO mosdepth/norm outputs, so
# it can't yield a gate-able card — the shape WS-09 rejects at submit.
_NONGERMLINE_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "n_fastp", "name": "fastp", "ins": ["fastq"], "outs": ["fastp_json", "fastq"]},
        {"id": "n_bwa", "name": "bwa-mem2", "ins": ["fastq", "reference_fasta"], "outs": ["bam"]},
    ],
    "edges": [{"from": {"node": "n_fastp", "idx": 1}, "to": {"node": "n_bwa", "idx": 0}}],
}


def _graph_faking_outputs_via_custom() -> dict[str, Any]:
    """A catalogued fastp plus CUSTOM nodes that merely *declare* the mosdepth/norm output kinds. A
    custom body publishes to ``results/custom``, not the ``results/`` the parser globs, so this
    graph still can't yield a gate-able card — the submit gate must reject it, NOT be fooled by the
    declared kinds (an anti-scaffold guard: crediting node ``outs`` instead of catalogued spec
    outputs would let this false-pass)."""
    return {
        "nodes": [
            {"id": "n_fastp", "name": "fastp", "ins": ["fastq"], "outs": ["fastp_json", "fastq"]},
            {
                "id": "n_fake_cov",
                "name": "custom-cov",
                "ins": ["fastq"],
                "outs": ["mosdepth_summary", "mosdepth_thresholds"],
                "script": "echo cov",
            },
            {
                "id": "n_fake_vcf",
                "name": "custom-vcf",
                "ins": ["fastq"],
                "outs": ["filtered_vcf"],
                "script": "echo vcf",
            },
        ],
        "edges": [
            {"from": {"node": "n_fastp", "idx": 1}, "to": {"node": "n_fake_cov", "idx": 0}},
            {"from": {"node": "n_fastp", "idx": 1}, "to": {"node": "n_fake_vcf", "idx": 0}},
        ],
    }


def _graph_needing_unsupported_input() -> dict[str, Any]:
    """The germline chain (so it PASSES the parse contract) plus a custom stage that consumes a
    ``truth_vcf`` external input intake can't supply — so ONLY the input-parity check can reject it,
    making the test unambiguous about which guard fired."""
    g = germline_graph_dict()
    g["nodes"].append(
        {
            "id": "n_concordance",
            "name": "custom-concordance",
            "ins": ["truth_vcf"],
            "outs": ["report"],
            "script": "echo concordance",  # a non-empty body ⇒ a custom process, not a placeholder
        }
    )
    return g


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


def _record(
    name: str, version: int, *, approved: bool, graph: dict[str, Any] | None = None
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "id": f"{name}-{version}",
        "name": name,
        "version": version,
        "schema_version": "builder/0.1",
        "created_at": "2026-07-12T00:00:00+00:00",
        "graph": _GRAPH if graph is None else graph,
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
    monkeypatch.setenv("BAYLEAF_JOB_STORE", "jsonl")
    monkeypatch.setenv("BAYLEAF_JOB_PATH", str(tmp_path / "jobs.jsonl"))
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


def test_nongermline_authored_pipeline_rejected_at_submit(env: dict[str, Any]) -> None:
    """WS-09 #1: an approved authored pipeline whose outputs can't satisfy the frozen-five parse
    contract is rejected at SUBMIT (422) BEFORE any compute — not left to run to completion in
    Nextflow then die at parse. fastp→bwa-mem2 produces no mosdepth/norm outputs, so it can never
    yield a gate-able card; the germline reference (which does) still passes submit."""
    _seed_store(
        env["monkeypatch"],
        _record("aln-only", 1, approved=True, graph=_NONGERMLINE_GRAPH),
        _record("germline-ref", 1, approved=True),  # default graph = the full germline chain
    )
    resp = _submit(run_name="RUN-NONGERMLINE", pipeline="aln-only")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    # Names the missing output kind(s) the parse requires — an actionable, honest message.
    assert "mosdepth_summary" in detail and "filtered_vcf" in detail
    assert env["fired"] == []  # rejected up front — no driver thread, no compute burn
    # Nothing was half-registered: the 422 fires before the run id is reserved.
    assert intake.get_job_store().get("RUN-NONGERMLINE", KIND_INTAKE) is None
    # The germline reference DOES pass submit (202) and fires — only the bad shape is refused.
    ok = _submit(run_name="RUN-GERMLINE-OK", pipeline="germline-ref")
    assert ok.status_code == 202 and "RUN-GERMLINE-OK" in env["fired"]


def test_custom_nodes_declaring_required_kinds_do_not_fool_the_parse_gate(
    env: dict[str, Any],
) -> None:
    """Anti-scaffold guard for WS-09 #1: the parse gate credits only CATALOGUED spec outputs (which
    publish to ``results/``), never a custom node's merely-declared kinds (which publish to
    ``results/custom``). A graph that fakes the mosdepth/norm outputs via custom nodes is still a
    422 — the live parse would find nothing gate-able, so the gate must too."""
    _seed_store(
        env["monkeypatch"],
        _record("fake-outputs", 1, approved=True, graph=_graph_faking_outputs_via_custom()),
    )
    resp = _submit(run_name="RUN-FAKE-OUT", pipeline="fake-outputs")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "mosdepth_summary" in detail and "filtered_vcf" in detail
    assert env["fired"] == []


def test_intake_rejects_authored_graph_with_unfilled_inputs(env: dict[str, Any]) -> None:
    """WS-09 #2: intake refuses (422) an authored graph whose required inputs it can't supply —
    parity with the Builder-Run path's ``required_inputs`` validation. Intake only ever supplies the
    HG002 germline defaults (fastq / reference_fasta / panel_bed); a graph needing a ``truth_vcf``
    would otherwise fall back to those defaults and process the WRONG inputs (wrong-but-runs). A
    valid germline submit whose inputs are all defaults still succeeds."""
    _seed_store(
        env["monkeypatch"],
        _record("needs-truth", 1, approved=True, graph=_graph_needing_unsupported_input()),
        _record("germline-ref", 1, approved=True),
    )
    resp = _submit(run_name="RUN-UNFILLED", pipeline="needs-truth")
    assert resp.status_code == 422
    assert "truth_vcf" in resp.json()["detail"]  # names the input intake can't supply
    assert env["fired"] == []  # rejected before any driver thread
    assert intake.get_job_store().get("RUN-UNFILLED", KIND_INTAKE) is None
    # Parity: a germline submit (all inputs are HG002 defaults) still fires.
    ok = _submit(run_name="RUN-INPUT-OK", pipeline="germline-ref")
    assert ok.status_code == 202 and "RUN-INPUT-OK" in env["fired"]


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


def test_scheduled_run_is_honest_manual_release_only(env: dict[str, Any]) -> None:
    """WS-09 #3 (MED — honesty): a ``schedule`` run is NOT auto-fired at its time (no background
    scheduler exists). Its status stays truthfully ``scheduled`` across repeated polls — never an
    eternal spinner that silently claims it will run — and the ONLY way it advances is an explicit
    manual release. This freezes the honest labeling so a half-scheduler can't regress in."""
    past = "2000-01-01T00:00:00+00:00"  # already elapsed — an auto-scheduler would have fired it
    resp = _submit(run_name="RUN-SCHED-HONEST", mode="schedule", scheduled_at=past)
    assert resp.status_code == 202 and resp.json()["status"] == "scheduled"
    assert env["fired"] == []
    # Repeated polls keep reporting `scheduled` — the elapsed time never auto-transitions the run.
    for _ in range(3):
        status = client.get("/api/runs/RUN-SCHED-HONEST/intake-status").json()
        assert status["status"] == "scheduled" and status["scheduled_at"] == past
    assert env["fired"] == []  # still not fired after elapsed-time polls — no auto-release
    # Only a manual release advances it (the documented, honest counterpart to auto-scheduling).
    rel = client.post("/api/runs/RUN-SCHED-HONEST/release", headers=_REVIEWER)
    assert rel.status_code == 202 and rel.json()["status"] == "running"
    assert env["fired"] == ["RUN-SCHED-HONEST"]


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
