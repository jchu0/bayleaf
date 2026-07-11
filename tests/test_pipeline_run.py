"""Operator-driven pipeline execution — POST /api/pipelines/run (ADR-0003).

Pins the guardrails that make operator execution safe WITHOUT running Nextflow in the offline
suite: it is role-gated (a viewer is refused), the run id is a slug, the graph must compile, and
every input KIND the graph needs must be supplied by a KEY that resolves to a real server-side file
(never a raw client path — traversal-safe). The happy path is tested with the background executor
monkeypatched to a no-op (the real `nextflow run` is exercised live, out of band). A human operator
absolutely CAN execute — this only checks they can't start a broken/underspecified run.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import api.routers.pipeline_run as pr
from api.main import app

client = TestClient(app)

_REVIEWER = {"X-PipeGuard-Role": "reviewer", "X-PipeGuard-Actor": "a.rivera"}


def _body(run_id: str = "RUN-TEST-EXEC", **inputs: str) -> dict[str, Any]:
    nodes = [
        {"id": "n_fastp", "name": "fastp", "ins": ["fastq"], "outs": ["fastp_json", "fastq"]},
        {"id": "n_bwa", "name": "bwa-mem2", "ins": ["fastq", "reference_fasta"], "outs": ["bam"]},
    ]
    edges = [{"from": {"node": "n_fastp", "idx": 1}, "to": {"node": "n_bwa", "idx": 0}}]
    chosen = inputs or {"reads": "hg002-panel", "reference": "grch38-chr20"}
    return {
        "graph": {"name": "exec-test", "nodes": nodes, "edges": edges},
        "run_id": run_id,
        "sample": "HG002",
        "inputs": chosen,
    }


def test_list_inputs_surfaces_present_server_side_inputs() -> None:
    cat = client.get("/api/pipelines/run/inputs").json()
    # Only what's on disk is surfaced; the real GIAB fixtures are present in this repo.
    assert {"reads", "reference", "panel_bed"} <= set(cat)
    assert any(o["key"] == "grch38-chr20" for o in cat["reference"])


def test_run_requires_reviewer_or_approver() -> None:
    denied = client.post(
        "/api/pipelines/run",
        json=_body(),
        headers={"X-PipeGuard-Role": "viewer", "X-PipeGuard-Actor": "v"},
    )
    assert denied.status_code == 403


def test_run_rejects_a_bad_run_id() -> None:
    resp = client.post("/api/pipelines/run", json=_body(run_id="../etc"), headers=_REVIEWER)
    assert resp.status_code == 422 and "slug" in resp.json()["detail"]


def test_run_requires_every_input_kind_the_graph_consumes() -> None:
    # The graph needs reads + a reference; supply only reads → 422 naming the missing category.
    resp = client.post("/api/pipelines/run", json=_body(reads="hg002-panel"), headers=_REVIEWER)
    assert resp.status_code == 422 and "reference" in resp.json()["detail"]


def test_run_rejects_an_unknown_input_key() -> None:
    resp = client.post(
        "/api/pipelines/run",
        json=_body(reads="hg002-panel", reference="does-not-exist"),
        headers=_REVIEWER,
    )
    assert resp.status_code == 422 and "unknown reference" in resp.json()["detail"]


def test_run_happy_path_compiles_materializes_and_queues(tmp_path: Any, monkeypatch: Any) -> None:
    # Monkeypatch the background executor to a no-op so the offline test never runs Nextflow, and
    # redirect the scratch dir into tmp so nothing lands in the repo.
    monkeypatch.setattr(pr, "_NF_RUNS", tmp_path / ".nf-runs")
    called: dict[str, Any] = {}

    def _fake_execute(run_id: str, pipeline: Any, *a: Any, **k: Any) -> None:
        called["run_id"] = run_id
        called["pipeline"] = pipeline

    monkeypatch.setattr(pr, "_execute", _fake_execute)

    body = _body(run_id="RUN-TEST-EXEC-OK")
    resp = client.post("/api/pipelines/run", json=body, headers=_REVIEWER)
    assert resp.status_code == 202
    ack = resp.json()
    assert ack["status"] == "queued"
    assert ack["steps"][:2] == ["FASTP", "BWA_MEM2_MEM"]
    # The compiled pipeline was materialized to the scratch dir before the job was handed off.
    main_nf = tmp_path / ".nf-runs" / "RUN-TEST-EXEC-OK" / "pipeline" / "main.nf"
    assert main_nf.is_file() and "BWA_MEM2_MEM(FASTP.out.fastq" in main_nf.read_text()
    # Status is queryable.
    status = client.get("/api/pipelines/run/RUN-TEST-EXEC-OK").json()
    assert status["status"] in {"queued", "running", "complete", "failed"}


def test_status_unknown_job_is_404() -> None:
    assert client.get("/api/pipelines/run/NOPE").status_code == 404
