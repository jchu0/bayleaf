"""PHASE 4 — a bound advisory agent's SCOPED READ of a node's published outputs.

Covers ``GET /api/runs/{run_id}/nodes/{node_id}/observations``:

  1. outputs are SCOPED to the node — fastp's publish globs surface fastp's files, never a sibling
     process's BAM in the same publish dir; node resolves by germline node id AND by tool key.
  2. 'logs' is OPT-IN (absent from a default outputs-only request), reviewer+-gated (WS-08), AND
     de-identified — a planted subject id + email + MRN-shaped digits are scrubbed from the tail.
  3. a node with nothing on disk → honest-empty (source='none' + a note), never a crash.
  4. auth — viewer reads outputs (viewer+) but is 403'd on the 'logs' grant (reviewer+); an
     unknown/invalid principal role is rejected (400).
  5. a traversal-crafted run id is rejected (404) before any path is touched.

Offline + deterministic: the module's ``_NF_RUNS``/``_DATA`` roots are monkeypatched to a tmp dir
holding a hand-built Nextflow publish + work tree. Nothing runs Nextflow.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api.routers.node_observations as obs
from api.main import app

client = TestClient(app)

_RUN = "RUN-TEST-OBS"
_VIEWER = {"X-Bayleaf-Role": "viewer", "X-Bayleaf-Actor": "v"}
_REVIEWER = {"X-Bayleaf-Role": "reviewer", "X-Bayleaf-Actor": "r"}

# Planted PII that MUST NOT survive the de-id scrub in a returned log tail.
_SUBJECT = "SUBJ-00042-JohnDoe"
_EMAIL = "jane.patient@hospital.org"
_MRN = "7654321"  # a 6+-digit run (MRN/DOB/accession shape)


@pytest.fixture
def run_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake run: a Nextflow publish dir (fastp + a sibling BAM) + a fastp task work dir + the
    intake ``sample_metadata.csv`` carrying the subject id. Returns the tmp root."""
    nf_runs = tmp_path / ".nf-runs"
    data = tmp_path / "data"
    monkeypatch.setattr(obs, "_NF_RUNS", nf_runs)
    monkeypatch.setattr(obs, "_DATA", data)

    results = nf_runs / _RUN / "nf-out" / "results"
    results.mkdir(parents=True)
    # fastp's four published outputs …
    for name in (
        "HG002.trim.R1.fastq.gz",
        "HG002.trim.R2.fastq.gz",
        "HG002.fastp.json",
        "HG002.fastp.html",
    ):
        (results / name).write_text("x", encoding="utf-8")
    # … and a SIBLING process's output that must NOT leak into fastp's scoped view.
    (results / "HG002.dedup.bam").write_text("bam", encoding="utf-8")

    # A fastp task work dir with a NEXTFLOW TASK header + a log carrying planted PII.
    task = nf_runs / _RUN / "work" / "ab" / "cdef0123456789"
    task.mkdir(parents=True)
    (task / ".command.run").write_text(
        "#!/bin/bash\n# NEXTFLOW TASK: FASTP (HG002)\n", encoding="utf-8"
    )
    (task / ".command.err").write_text(
        f"processing subject {_SUBJECT} contact {_EMAIL} mrn {_MRN}\ncoverage 54\n",
        encoding="utf-8",
    )
    (task / ".command.log").write_text("fastp done\n", encoding="utf-8")

    meta = data / _RUN
    meta.mkdir(parents=True)
    (meta / "sample_metadata.csv").write_text(
        f"Sample_ID,Subject_ID,Tissue\nHG002,{_SUBJECT},blood\n", encoding="utf-8"
    )
    return tmp_path


def _get(node: str, grants: str | None = None, headers: dict[str, str] = _VIEWER) -> dict:
    url = f"/api/runs/{_RUN}/nodes/{node}/observations"
    if grants is not None:
        url += f"?grants={grants}"
    resp = client.get(url, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_outputs_scoped_to_node_by_germline_id(run_tree: Path) -> None:
    body = _get("n_fastp")  # a seeded germline graph node id
    assert body["tool"] == "fastp"
    assert body["process"] == "FASTP"
    assert body["source"] == "nextflow-publish"
    names = {a["name"] for a in body["outputs"]}
    assert names == {
        "HG002.trim.R1.fastq.gz",
        "HG002.trim.R2.fastq.gz",
        "HG002.fastp.json",
        "HG002.fastp.html",
    }
    assert "HG002.dedup.bam" not in names  # a sibling process's file is NOT in fastp's scope
    kinds = {a["kind"] for a in body["outputs"]}
    assert "fastp_json" in kinds and "fastp_html" in kinds
    # 'logs' is opt-in: a default (outputs-only) request returns none.
    assert body["logs"] == []
    assert body["advisory"] is True


def test_outputs_scoped_by_tool_key(run_tree: Path) -> None:
    body = _get("fastp")  # a direct catalog tool key resolves the same
    assert body["tool"] == "fastp"
    assert {a["name"] for a in body["outputs"]} == {
        "HG002.trim.R1.fastq.gz",
        "HG002.trim.R2.fastq.gz",
        "HG002.fastp.json",
        "HG002.fastp.html",
    }


def test_logs_opt_in_and_deidentified(run_tree: Path) -> None:
    body = _get("n_fastp", grants="outputs,logs", headers=_REVIEWER)  # logs is reviewer+ (WS-08)
    assert "logs" in body["grants"]
    assert body["logs"], "the fastp task's log streams should be attributed + returned"
    blob = "\n".join(line for tail in body["logs"] for line in tail["lines"])
    # The planted PII is scrubbed from the returned tail.
    assert _SUBJECT not in blob
    assert _EMAIL not in blob
    assert _MRN not in blob
    # …but real, non-sensitive content survives (the scrub is targeted, not a blackout).
    assert "coverage" in blob or "fastp done" in blob
    for tail in body["logs"]:
        assert tail["deid_policy"]  # the policy id is stamped on every tail


def test_logs_grant_denied_to_viewer(run_tree: Path) -> None:
    """WS-08: the PII-adjacent 'logs' grant is reviewer+ — a plain viewer requesting it is 403'd,
    closing 'any viewer can read any node's de-identified task logs'. Outputs stay viewer+."""
    denied = client.get(f"/api/runs/{_RUN}/nodes/n_fastp/observations?grants=logs", headers=_VIEWER)
    assert denied.status_code == 403
    # …the same viewer can still read outputs (the low-sensitivity published-file listing).
    ok = client.get(f"/api/runs/{_RUN}/nodes/n_fastp/observations", headers=_VIEWER)
    assert ok.status_code == 200 and ok.json()["grants"] == ["outputs"]


def test_logs_grant_allowed_to_reviewer(run_tree: Path) -> None:
    """WS-08: reviewer+ may read the de-identified logs — available, just role-gated."""
    resp = client.get(
        f"/api/runs/{_RUN}/nodes/n_fastp/observations?grants=outputs,logs", headers=_REVIEWER
    )
    assert resp.status_code == 200 and "logs" in resp.json()["grants"]


def test_node_with_no_outputs_is_honest_empty(run_tree: Path) -> None:
    body = _get("n_bwa")  # bwa-mem2 published no *.aligned.bam in this fixture
    assert body["tool"] == "bwa-mem2"
    assert body["source"] == "none"
    assert body["outputs"] == []
    assert body["note"]  # an honest explanation, not a crash


def test_unresolved_node_is_honest_empty(run_tree: Path) -> None:
    body = _get("n_not_a_real_node")
    assert body["tool"] is None
    assert body["source"] == "none"
    assert body["outputs"] == []
    assert "did not resolve" in (body["note"] or "")


def test_unknown_grant_is_422(run_tree: Path) -> None:
    resp = client.get(
        f"/api/runs/{_RUN}/nodes/n_fastp/observations?grants=secrets", headers=_VIEWER
    )
    assert resp.status_code == 422


def test_viewer_allowed_invalid_principal_rejected(run_tree: Path) -> None:
    ok = client.get(f"/api/runs/{_RUN}/nodes/n_fastp/observations", headers=_VIEWER)
    assert ok.status_code == 200  # viewer is within viewer+
    bad = client.get(
        f"/api/runs/{_RUN}/nodes/n_fastp/observations",
        headers={"X-Bayleaf-Role": "banana", "X-Bayleaf-Actor": "x"},
    )
    assert bad.status_code == 400  # an unrecognized principal role is rejected, not defaulted


def test_traversal_run_id_rejected(run_tree: Path) -> None:
    resp = client.get("/api/runs/evil..evil/nodes/fastp/observations", headers=_VIEWER)
    assert resp.status_code == 404
    # and the guard rejects an explicit traversal id directly.
    with pytest.raises(HTTPException) as ei:
        obs._guard_run_id("../etc")
    assert ei.value.status_code == 404
