"""Operator-driven pipeline execution — POST /api/pipelines/run (ADR-0003/0014).

Pins the guardrails that make operator execution safe WITHOUT running Nextflow in the offline
suite. The APPROVAL GATE (ADR-0014) is the headline: a run NAMES a saved pipeline and executes that
pipeline's approver-blessed (``emitted``) baseline resolved from the store — never a raw client
graph, so an unapproved draft is a 409 and a posted ``graph`` is rejected outright. Beyond the gate
it is role-gated (a viewer is refused), the run id is a slug, the approved graph must compile, and
every input KIND the graph needs must be supplied by a KEY that resolves to a real server-side file
(never a raw client path — traversal-safe). The happy path is tested with the background executor
monkeypatched to a no-op (the real ``nextflow run`` is exercised live, out of band).
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from scripts.seed_approved_germline import germline_graph_dict

import api.routers.pipeline_run as pr
from api.main import app

client = TestClient(app)

_REVIEWER = {"X-Bayleaf-Role": "reviewer", "X-Bayleaf-Actor": "a.rivera"}

# The default fixture is a REAL gate-able pipeline — the seeded germline chain (fastp → bwa-mem2 →
# markdup → mosdepth → bcftools call/norm → MultiQC), reused verbatim from the shared
# ``germline_graph_dict()`` so it can never drift from the real chain. Builder-Run now rejects a
# non-gate-able approved graph at submit (the parse contract), so the happy path must use a chain
# that actually produces the frozen-five QC — i.e. one that can yield a card. It needs three input
# kinds: reads + reference + panel_bed.
_GRAPH: dict[str, Any] = germline_graph_dict()

# A compilable but NON-gate-able graph (fastp → bwa-mem2 only): it produces a BAM but none of the
# frozen-five QC the post-run parse globs. Builder-Run must reject it at SUBMIT (the parse contract)
# rather than burn a full compute run that only dies at parse — the gap this suite freezes (WS-09
# #1 / audit G8), reaching parity with the intake path.
_NON_GATEABLE_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "n_fastp", "name": "fastp", "ins": ["fastq"], "outs": ["fastp_json", "fastq"]},
        {"id": "n_bwa", "name": "bwa-mem2", "ins": ["fastq", "reference_fasta"], "outs": ["bam"]},
    ],
    "edges": [{"from": {"node": "n_fastp", "idx": 1}, "to": {"node": "n_bwa", "idx": 0}}],
}


def _record(
    name: str, version: int, *, approved: bool, graph: dict[str, Any] | None = None
) -> dict[str, Any]:
    """One stored pipeline envelope. ``approved`` stamps ``emitted_at`` (the approval marker)."""
    rec: dict[str, Any] = {
        "id": f"{name}-{version}",
        "name": name,
        "version": version,
        "schema_version": "builder/0.1",
        "created_at": "2026-07-11T00:00:00+00:00",
        "graph": _GRAPH if graph is None else graph,
        "status": "approved" if approved else "draft",
    }
    if approved:
        rec["emitted_at"] = "2026-07-11T00:00:00+00:00"
    return rec


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


def _seed(monkeypatch: Any, *records: dict[str, Any]) -> None:
    """Point the endpoint's store factory at a fake store holding ``records``."""
    store = _FakeStore(list(records))
    monkeypatch.setattr(pr, "get_pipeline_store", lambda: store)


def _body(run_id: str = "RUN-TEST-EXEC", name: str = "exec-test", **inputs: str) -> dict[str, Any]:
    # The germline chain needs all three input kinds; supply them by default so the happy path
    # clears input validation. Individual tests override to probe a missing/unknown one.
    chosen = inputs or {
        "reads": "hg002-panel",
        "reference": "grch38-chr20",
        "panel_bed": "example-panel",
    }
    return {"name": name, "run_id": run_id, "sample": "HG002", "inputs": chosen}


def test_list_inputs_surfaces_present_server_side_inputs() -> None:
    cat = client.get("/api/pipelines/run/inputs").json()
    # Only what's on disk is surfaced; the real GIAB fixtures are present in this repo.
    assert {"reads", "reference", "panel_bed"} <= set(cat)
    assert any(o["key"] == "grch38-chr20" for o in cat["reference"])


def test_run_requires_reviewer_or_approver() -> None:
    denied = client.post(
        "/api/pipelines/run",
        json=_body(),
        headers={"X-Bayleaf-Role": "viewer", "X-Bayleaf-Actor": "v"},
    )
    assert denied.status_code == 403


def test_run_rejects_a_posted_graph_no_bypass() -> None:
    # The approval gate closes the old bypass: a client can't smuggle a raw graph to run (forbid).
    resp = client.post(
        "/api/pipelines/run",
        json={**_body(), "graph": {"name": "x", "nodes": [], "edges": []}},
        headers=_REVIEWER,
    )
    assert resp.status_code == 422


def test_run_rejects_a_bad_run_id() -> None:
    resp = client.post("/api/pipelines/run", json=_body(run_id="../etc"), headers=_REVIEWER)
    assert resp.status_code == 422 and "slug" in resp.json()["detail"]


def test_run_409_when_pipeline_has_no_approved_version(monkeypatch: Any) -> None:
    # A draft-only pipeline (never approved) can't run — the gate is a 409, not a silent bypass.
    _seed(monkeypatch, _record("exec-test", 1, approved=False))
    resp = client.post("/api/pipelines/run", json=_body(), headers=_REVIEWER)
    assert resp.status_code == 409 and "no approved version" in resp.json()["detail"]


def test_run_409_when_pipeline_is_unknown(monkeypatch: Any) -> None:
    _seed(monkeypatch)  # empty store
    resp = client.post("/api/pipelines/run", json=_body(name="never-saved"), headers=_REVIEWER)
    assert resp.status_code == 409 and "no approved version" in resp.json()["detail"]


def test_run_409_when_pinned_version_is_not_approved(monkeypatch: Any) -> None:
    # v1 approved, but the client pins v2 (only pending) → 409 naming the version.
    _seed(
        monkeypatch,
        _record("exec-test", 1, approved=True),
        _record("exec-test", 2, approved=False),
    )
    body = {**_body(), "version": 2}
    resp = client.post("/api/pipelines/run", json=body, headers=_REVIEWER)
    assert resp.status_code == 409 and "version 2" in resp.json()["detail"]


def test_run_requires_every_input_kind_the_approved_graph_consumes(monkeypatch: Any) -> None:
    # The approved germline graph needs reads + reference + panel_bed. Supply reads + panel_bed but
    # OMIT the reference → 422 naming the one missing category (the other two resolve, so which
    # category is reported is deterministic regardless of set-iteration order).
    _seed(monkeypatch, _record("exec-test", 1, approved=True))
    resp = client.post(
        "/api/pipelines/run",
        json=_body(reads="hg002-panel", panel_bed="example-panel"),
        headers=_REVIEWER,
    )
    assert resp.status_code == 422 and "reference" in resp.json()["detail"]


def test_run_rejects_an_unknown_input_key(monkeypatch: Any) -> None:
    # Supply valid reads + panel_bed but a bogus reference KEY → 422 naming the unknown reference
    # (reads + panel_bed resolve, so the reference is the sole, deterministic failure).
    _seed(monkeypatch, _record("exec-test", 1, approved=True))
    resp = client.post(
        "/api/pipelines/run",
        json=_body(reads="hg002-panel", reference="does-not-exist", panel_bed="example-panel"),
        headers=_REVIEWER,
    )
    assert resp.status_code == 422 and "unknown reference" in resp.json()["detail"]


def test_run_rejects_a_non_gateable_approved_pipeline(monkeypatch: Any) -> None:
    # G8 / WS-09 #1 — parity with the intake path: even an APPROVED pipeline must produce the
    # frozen-five QC the post-run parse globs, else it runs to completion in Nextflow then dies at
    # parse with no card — a full compute burn for a `failed` run. Builder-Run catches it at SUBMIT
    # via the parse contract (a structural check needing no tools), naming the frozen-five. A
    # fastp → bwa-mem2 graph yields only a BAM, so it is rejected here before any input resolution.
    _seed(monkeypatch, _record("exec-test", 1, approved=True, graph=_NON_GATEABLE_GRAPH))
    resp = client.post("/api/pipelines/run", json=_body(), headers=_REVIEWER)
    assert resp.status_code == 422 and "frozen-five" in resp.json()["detail"]


def test_run_happy_path_compiles_the_approved_graph(tmp_path: Any, monkeypatch: Any) -> None:
    # Monkeypatch the background executor to a no-op so the offline test never runs Nextflow, and
    # redirect the scratch dir into tmp so nothing lands in the repo.
    _seed(monkeypatch, _record("exec-test", 3, approved=True))
    monkeypatch.setattr(pr, "_NF_RUNS", tmp_path / ".nf-runs")
    called: dict[str, Any] = {}

    def _fake_execute(run_id: str, pipeline: Any, *a: Any, **k: Any) -> None:
        called["run_id"] = run_id
        called["pipeline"] = pipeline

    monkeypatch.setattr(pr, "_execute", _fake_execute)

    resp = client.post(
        "/api/pipelines/run", json=_body(run_id="RUN-TEST-EXEC-OK"), headers=_REVIEWER
    )
    assert resp.status_code == 202
    ack = resp.json()
    assert ack["status"] == "queued"
    assert ack["steps"][:2] == ["FASTP", "BWA_MEM2_MEM"]
    # The compiled APPROVED pipeline was materialized to scratch before the job was handed off.
    main_nf = tmp_path / ".nf-runs" / "RUN-TEST-EXEC-OK" / "pipeline" / "main.nf"
    assert main_nf.is_file() and "BWA_MEM2_MEM(FASTP.out.fastq" in main_nf.read_text()
    # Status is queryable.
    status = client.get("/api/pipelines/run/RUN-TEST-EXEC-OK").json()
    assert status["status"] in {"queued", "running", "complete", "failed"}


def test_run_pins_an_exact_approved_version(tmp_path: Any, monkeypatch: Any) -> None:
    # Two approved versions on file; pinning v2 runs that exact revision (not the latest).
    _seed(
        monkeypatch,
        _record("exec-test", 2, approved=True),
        _record("exec-test", 3, approved=True),
    )
    monkeypatch.setattr(pr, "_NF_RUNS", tmp_path / ".nf-runs")
    monkeypatch.setattr(pr, "_execute", lambda *a, **k: None)
    body = {**_body(run_id="RUN-TEST-PIN"), "version": 2}
    resp = client.post("/api/pipelines/run", json=body, headers=_REVIEWER)
    assert resp.status_code == 202 and resp.json()["status"] == "queued"


def test_status_unknown_job_is_404() -> None:
    assert client.get("/api/pipelines/run/NOPE").status_code == 404
