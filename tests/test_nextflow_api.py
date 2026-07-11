"""POST /api/pipelines/compile — the Builder-graph → Nextflow endpoint (ADR-0003).

Drives the router with a TestClient over the Builder's real save shape (`{nodes:[{id,name,ins,
outs}], edges:[{from:{node,idx},to:{node,idx}}]}`): a valid graph returns the generated bundle (JSON
preview + a .zip download), and a bad/empty graph is a 422 with the compiler's reason. Stateless,
off-gate: nothing is persisted, no verdict touched.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _germline_body() -> dict[str, Any]:
    """The seeded germline chain in the Builder's wire shape (name = tool, edges by port index)."""
    nodes = [
        {"id": "n_fastp", "name": "fastp", "ins": ["fastq"], "outs": ["fastp_json", "fastq"]},
        {"id": "n_bwa", "name": "bwa-mem2", "ins": ["fastq", "reference_fasta"], "outs": ["bam"]},
        {
            "id": "n_markdup",
            "name": "samtools markdup",
            "ins": ["bam"],
            "outs": ["bam", "bai", "markdup_metrics"],
        },
        {
            "id": "n_call",
            "name": "bcftools call",
            "ins": ["bam", "reference_fasta", "panel_bed"],
            "outs": ["vcf"],
        },
        {
            "id": "n_norm",
            "name": "bcftools norm",
            "ins": ["vcf", "reference_fasta"],
            "outs": ["filtered_vcf"],
        },
    ]
    edges = [
        {"from": {"node": "n_fastp", "idx": 1}, "to": {"node": "n_bwa", "idx": 0}},  # fastq (idx 1)
        {"from": {"node": "n_bwa", "idx": 0}, "to": {"node": "n_markdup", "idx": 0}},
        {"from": {"node": "n_markdup", "idx": 0}, "to": {"node": "n_call", "idx": 0}},
        {"from": {"node": "n_call", "idx": 0}, "to": {"node": "n_norm", "idx": 0}},
    ]
    return {"name": "my germline!", "nodes": nodes, "edges": edges}


def test_compile_returns_a_bundle_wired_from_the_ports() -> None:
    resp = client.post("/api/pipelines/compile", json=_germline_body())
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "my-germline"  # sanitized for a Nextflow manifest name
    assert "main.nf" in body["files"] and "nextflow.config" in body["files"]
    assert body["steps"] == [
        "FASTP", "BWA_MEM2_MEM", "SAMTOOLS_MARKDUP", "BCFTOOLS_CALL", "BCFTOOLS_NORM",
    ]  # fmt: skip
    # The typed-port edge (fastp's fastq at idx 1) resolves to the right channel, not fastp_json.
    assert "BWA_MEM2_MEM(FASTP.out.fastq, ch_reference)" in body["main_nf"]
    assert "fastp -i ${read1}" in body["files"]["modules/fastp.nf"]


def test_compile_zip_download() -> None:
    resp = client.post("/api/pipelines/compile?format=zip", json=_germline_body())
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert "my-germline/main.nf" in names
    assert any(n.endswith("modules/fastp.nf") for n in names)


def test_empty_graph_is_422() -> None:
    resp = client.post("/api/pipelines/compile", json={"name": "empty", "nodes": [], "edges": []})
    assert resp.status_code == 422
    assert "no tool nodes" in resp.json()["detail"]


def test_cyclic_graph_is_422_with_reason() -> None:
    body = {
        "name": "loop",
        "nodes": [
            {"id": "a", "name": "fastp", "ins": ["vcf"], "outs": ["vcf"]},
            {"id": "b", "name": "bcftools norm", "ins": ["vcf"], "outs": ["vcf"]},
        ],
        "edges": [
            {"from": {"node": "a", "idx": 0}, "to": {"node": "b", "idx": 0}},
            {"from": {"node": "b", "idx": 0}, "to": {"node": "a", "idx": 0}},
        ],
    }
    resp = client.post("/api/pipelines/compile", json=body)
    assert resp.status_code == 422
    assert "cycle" in resp.json()["detail"]
