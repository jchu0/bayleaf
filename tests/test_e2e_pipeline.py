"""End-to-end acceptance test: sample + metadata sheet → run → report, via the approval gate.

The acceptance criterion for the just-landed W1 (approval-gated ``POST /api/pipelines/run``), W3
(RunDetail Report data + downstream provenance stages ``filter | review | share`` + the
flag-for-review fix), and W4 (per-sample fan-out intent + full port wiring). It threads the real API
surface — intake (``api/routers/intake.py``), the Builder save/lifecycle
(``api/main.save_pipeline`` + ``api/routers/pipelines_lifecycle.py``), operator execution
(``api/routers/pipeline_run.py``), and the read-API (``GET /api/runs/{id}``) — over the committed
fixtures.

OFFLINE + DETERMINISTIC by construction (this sandbox has no ``nextflow`` and no guaranteed real
GIAB reads):

  * The intake driver thread (``intake._run_pipeline``) and the operator-run background executor
    (``pipeline_run._execute``) are monkeypatched to no-ops, so **no subprocess and no Nextflow ever
    run** — the test asserts the WIRING (registration, the approval gate, the compiled step order,
    the hand-off), never a live pipeline. This mirrors ``tests/test_pipeline_run.py``.
  * The operator-run input catalog (``pipeline_run._catalog``, which reads ``data/real-giab/`` off
    disk) is monkeypatched to a deterministic fixture so the happy path is identical whether or not
    real reads are present locally.
  * The pipeline store is isolated to a per-test ``tmp`` JSONL, so seeding an approved baseline
    never touches the repo default.

Env-gated live slice: ``test_approved_germline_pipeline_stub_runs_live`` confirms the SAME approved
graph the offline tests run is a real, ``nextflow -stub-run``-valid pipeline — **skipped** when
``nextflow`` is absent (mirrors ``test_nextflow_compile.py::test_generated_germline_stub_runs``).

Guardrails (CLAUDE.md / ADR-0001): the test never sets a verdict/confidence — it asserts what the
RULES decided. The flag-for-review evidence is ClinVar quoted VERBATIM (G3/G4); bayleaf authors no
pathogenicity. Compose != execute: every "run" is a hand-off assertion, not an execution.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from scripts.seed_approved_germline import germline_graph_dict, seed_approved_germline

import api.routers.intake as intake
import api.routers.pipeline_run as pr
from api.main import app
from bayleaf.nextflow import compile_graph, germline_graph

client = TestClient(app)

_REVIEWER = {"X-Bayleaf-Role": "reviewer", "X-Bayleaf-Actor": "a.rivera"}
_APPROVER = {"X-Bayleaf-Role": "approver", "X-Bayleaf-Actor": "b.chen"}
_VIEWER = {"X-Bayleaf-Role": "viewer", "X-Bayleaf-Actor": "v.iewer"}

# The committed fixtures the Report assertions read (never fabricated; pinned demo scenarios).
_MOCK = "mock_run_01"  # proceed / hold / escalate mix (the pinned scenario)
_RTH = "RUN-2026-07-11-CLINVAR-RTH"  # flag-for-review: HG002 escalates via VAR-FFR-001

# The seeded germline chain's topological step order (what the approved graph compiles to). The
# first two are the invariant head of the chain; BCFTOOLS_NORM is the tail — pinned so a wiring
# regression that drops/ reorders a process is caught.
_GERMLINE_STEPS_HEAD = ["FASTP", "BWA_MEM2_MEM"]


# --- helpers ---------------------------------------------------------------------------------


def _isolate_store(tmp_path: Path, monkeypatch: Any) -> None:
    """Point every ``get_*_store()`` caller (pipeline / share) at a tmp JSONL, so a test never reads
    real, session-polluted local state — e.g. a stray ``data.exported`` a local Share left in the
    gitignored ``share.events.jsonl`` (the stores read the env fresh per call, no cache)."""
    monkeypatch.delenv("BAYLEAF_PIPELINE_STORE", raising=False)  # default jsonl, whatever the env
    monkeypatch.setenv("BAYLEAF_PIPELINE_PATH", str(tmp_path / "pipeline_graphs.jsonl"))
    monkeypatch.delenv("BAYLEAF_SHARE_STORE", raising=False)
    monkeypatch.setenv("BAYLEAF_SHARE_PATH", str(tmp_path / "share.events.jsonl"))


def _fake_catalog(tmp_path: Path) -> dict[str, list[pr._InputOption]]:
    """A deterministic server-side input catalog (real files on disk, but tmp — so the happy path
    is environment-independent). The executor is a no-op, so the bytes are never read."""
    r1, r2 = tmp_path / "HG002.R1.fastq.gz", tmp_path / "HG002.R2.fastq.gz"
    ref, bed = tmp_path / "chr20.fa", tmp_path / "panel.bed"
    for p in (r1, r2, ref, bed):
        p.write_text("x", encoding="utf-8")
    return {
        "reads": [pr._InputOption("hg002-panel", "HG002 reads", "contrived", (r1, r2))],
        "reference": [pr._InputOption("grch38-chr20", "chr20", "contrived", (ref,))],
        "panel_bed": [pr._InputOption("example-panel", "panel", "contrived", (bed,))],
    }


def _run_body(name: str, run_id: str) -> dict[str, Any]:
    return {
        "name": name,
        "run_id": run_id,
        "sample": "HG002",
        "inputs": {
            "reads": "hg002-panel",
            "reference": "grch38-chr20",
            "panel_bed": "example-panel",
        },
    }


# === Stage 1: sample + metadata sheet creation → intake registration =========================
# The Submit screen parses a samplesheet + sample_metadata.csv CLIENT-SIDE (Submit.tsx) and hands
# the result to the JSON execution boundary POST /api/runs. These pin that server-side contract.


def test_sheet_creation_registers_run_and_skips_unfixtured_samples(monkeypatch: Any) -> None:
    """A multi-sample sheet (W4 fan-out) registers the run and honestly reports which samples can be
    processed — the Ashkenazim trio (HG002/HG003/HG004) has panel reads on disk so all three are
    processed; a sample with no reads (HG005) is *skipped* (registered, honestly not processed)."""
    monkeypatch.setattr(intake, "_run_pipeline", lambda *a, **k: None)  # stub the live driver
    body = {
        "run_name": "RUN-E2E-INTAKE",
        "study": "e2e",
        "assay": "germline-panel",
        "platform": "NovaSeq X",
        "samples": [
            {"sample": "HG002", "type": "WGS", "i7": "AAAACCCC", "i5": "GGGGTTTT", "study": "e2e"},
            {"sample": "HG003", "type": "WGS"},
            {"sample": "HG004", "type": "WGS"},
            {"sample": "HG005", "type": "WGS"},  # Han Chinese son — no panel reads on disk here
        ],
    }
    resp = client.post("/api/runs", json=body, headers=_REVIEWER)
    assert resp.status_code == 202
    ack = resp.json()
    assert ack["run_id"] == "RUN-E2E-INTAKE"  # the run_name slugifies to the run id
    assert ack["status"] == "queued"
    assert ack["processed_samples"] == ["HG002", "HG003", "HG004"]  # the on-disk trio, all run
    assert ack["skipped_samples"] == ["HG005"]  # no reads on disk → honestly not processed


def test_intake_parse_contract_rejects_pii_and_a_no_op_sheet(monkeypatch: Any) -> None:
    """SampleIn is ``extra='forbid'`` (a PII guard) and the boundary is role-gated + honest."""
    monkeypatch.setattr(intake, "_run_pipeline", lambda *a, **k: None)
    # A smuggled subject_id (PII) is rejected at the parse boundary — 422, nothing registered.
    pii = {"run_name": "RUN-E2E-PII", "samples": [{"sample": "HG002", "subject_id": "SUBJ-1"}]}
    assert client.post("/api/runs", json=pii, headers=_REVIEWER).status_code == 422
    # A sheet with no fixtured sample can't run — an honest 422, never a fabricated run.
    noproc = {"run_name": "RUN-E2E-NOPROC", "samples": [{"sample": "HG999"}]}
    r = client.post("/api/runs", json=noproc, headers=_REVIEWER)
    assert r.status_code == 422 and "no processable sample" in r.json()["detail"]
    # Intake is an execution boundary → a viewer is refused (require_role reviewer|approver).
    ok_body = {"run_name": "RUN-E2E-RBAC", "samples": [{"sample": "HG002"}]}
    assert client.post("/api/runs", json=ok_body, headers=_VIEWER).status_code == 403


# === Stage 2: Builder approval gate (W1) =====================================================
# A run NAMES a saved pipeline and executes that pipeline's approver-blessed (emitted) baseline —
# never a raw client graph. An unapproved draft is a 409; a posted graph is rejected outright.


def test_approval_gate_blocks_run_until_approved_then_accepts(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The W1 headline: compose → save (draft) → the run 409s (no approved version); submit →
    approve → the SAME run is accepted (202) and the approved germline graph compiles + runs."""
    _isolate_store(tmp_path, monkeypatch)
    name = "e2e-germline"
    body = _run_body(name, "RUN-E2E-EXEC")

    # Save a draft — then a run 409s: an unapproved pipeline can't execute (the gate, not a bypass).
    save = client.post("/api/pipelines", json={"name": name, "graph": germline_graph_dict()},
                       headers=_REVIEWER)  # fmt: skip
    assert save.status_code == 201 and save.json()["status"] == "draft"
    blocked = client.post("/api/pipelines/run", json=body, headers=_REVIEWER)
    assert blocked.status_code == 409 and "no approved version" in blocked.json()["detail"]

    # Submit → approve: only now is there an emitted baseline to run.
    assert client.post(f"/api/pipelines/{name}/submit", headers=_REVIEWER).status_code == 200
    assert client.post(f"/api/pipelines/{name}/approve", headers=_APPROVER).status_code == 200

    # Execute — the background driver is a no-op (no Nextflow), the catalog + scratch are tmp.
    monkeypatch.setattr(pr, "_catalog", lambda: _fake_catalog(tmp_path))
    monkeypatch.setattr(pr, "_NF_RUNS", tmp_path / ".nf-runs")
    captured: dict[str, Any] = {}
    monkeypatch.setattr(pr, "_execute", lambda *a, **k: captured.update(run_id=a[0], pipeline=a[1]))

    ok = client.post("/api/pipelines/run", json=body, headers=_REVIEWER)
    assert ok.status_code == 202
    ack = ok.json()
    assert ack["status"] == "queued"
    # The APPROVED germline graph compiled: the topological step order is the seeded chain.
    assert ack["steps"][:2] == _GERMLINE_STEPS_HEAD
    assert "BCFTOOLS_NORM" in ack["steps"]  # the tail process — the whole chain wired, not a stub
    # The background executor was handed THIS run, and the compiled pipeline was materialized first.
    assert captured["run_id"] == "RUN-E2E-EXEC"
    main_nf = tmp_path / ".nf-runs" / "RUN-E2E-EXEC" / "pipeline" / "main.nf"
    assert main_nf.is_file() and "BWA_MEM2_MEM(FASTP.out.fastq" in main_nf.read_text()
    # Status is queryable after hand-off.
    status = client.get("/api/pipelines/run/RUN-E2E-EXEC").json()
    assert status["status"] in {"queued", "running", "complete", "failed"}


def test_run_rejects_a_posted_graph_no_bypass() -> None:
    """The approval gate closes the old bypass: a client cannot smuggle a raw graph to run. The
    RunPipelineIn body is ``extra='forbid'``, so a posted ``graph`` is a 422 before anything runs —
    no store or approval needed to prove the door is shut."""
    body = {**_run_body("e2e-germline", "RUN-E2E-BYPASS"), "graph": {"nodes": [], "edges": []}}
    assert client.post("/api/pipelines/run", json=body, headers=_REVIEWER).status_code == 422


def test_seed_script_produces_an_approved_baseline_runnable_by_name(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The committed seed helper (the reproducible fix for the "no approved baseline" gap): it
    composes germline_graph() → save → submit → approve into the store, idempotently, so an approved
    ``germline-panel`` is runnable BY NAME without clicking through the Builder."""
    _isolate_store(tmp_path, monkeypatch)
    record, created = seed_approved_germline()
    assert created and record["status"] == "approved" and record["emitted_at"]
    # Idempotent: a second call appends nothing and returns the same approved revision.
    again, created_again = seed_approved_germline()
    assert not created_again and again["version"] == record["version"]

    # Runnable by name: the operator run resolves the seeded approved baseline (execution stubbed).
    monkeypatch.setattr(pr, "_catalog", lambda: _fake_catalog(tmp_path))
    monkeypatch.setattr(pr, "_NF_RUNS", tmp_path / ".nf-runs")
    monkeypatch.setattr(pr, "_execute", lambda *a, **k: None)
    ok = client.post(
        "/api/pipelines/run", json=_run_body("germline-panel", "RUN-E2E-SEEDED"), headers=_REVIEWER
    )
    assert ok.status_code == 202 and ok.json()["steps"][:2] == _GERMLINE_STEPS_HEAD


# === Stage 3: gate → cards → Report → provenance (W3) ========================================
# The Report reads what the RULES decided (ADR-0001) — the test asserts, never sets, a verdict.


def test_report_data_verdict_mix_and_per_sample_gate_outcomes() -> None:
    """The mock-run Report: the verdict mix + the per-sample gate outcome each sample's rules
    produced (S4 escalates at PREFLIGHT on a barcode/metadata fault; S5 holds at the QC gate)."""
    detail = client.get(f"/api/runs/{_MOCK}").json()
    assert detail["summary"]["counts"] == {"proceed": 3, "hold": 1, "rerun": 0, "escalate": 1}
    by_sample = {c["sample_id"]: c for c in detail["cards"]}
    assert by_sample["S4"]["verdict"] == "escalate"
    s4_gates = {(g["gate"], g["verdict"]) for g in by_sample["S4"]["gate_results"]}
    assert ("preflight", "escalate") in s4_gates
    assert by_sample["S5"]["verdict"] == "hold"
    s5_gates = {(g["gate"], g["verdict"]) for g in by_sample["S5"]["gate_results"]}
    assert ("qc", "hold") in s5_gates
    # Confidence is a heuristic omitted until grounded (T-019) — never fabricated on the Report.
    assert all(c["confidence"] is None for c in detail["cards"])


def test_report_flag_for_review_quotes_clinvar_verbatim() -> None:
    """The flag-for-review Report (W3): HG002 escalates via VAR-FFR-001 on the variant gate, and the
    ClinVar significance is QUOTED VERBATIM as cited evidence — bayleaf authors no pathogenicity
    (G3/G4, ADR-0004). The per-run arming (data/RUN-…-CLINVAR-RTH/flag_for_review) drives it; the
    core default stays disarmed."""
    detail = client.get(f"/api/runs/{_RTH}").json()
    assert detail["summary"]["counts"] == {"proceed": 0, "hold": 0, "rerun": 0, "escalate": 1}
    hg002 = next(c for c in detail["cards"] if c["sample_id"] == "HG002")
    assert hg002["verdict"] == "escalate"  # a deterministic rule routed it (rules decide)
    rth = next(f for f in hg002["findings"] if f["rule_id"] == "VAR-FFR-001")
    assert rth["gate"] == "variant"  # lands on the variant gate, not QC
    # The finding QUOTES ClinVar verbatim + cites the accession — it authors no significance.
    clnsig = next(e for e in rth["evidence"] if e["source_field"] == "CLNSIG")
    assert clnsig["value"] == "Pathogenic"  # verbatim — NOT bayleaf's determination
    assert clnsig["locator"] == "VCV000017661"  # the cited ClinVar accession
    assert "ClinVar" in clnsig["source"]
    # The prose defers to a human; it never claims bayleaf decided pathogenicity.
    assert "makes no pathogenicity determination" in rth["detail"]


def test_downstream_provenance_stages_read_honestly(tmp_path: Path, monkeypatch: Any) -> None:
    """W3 downstream lineage honesty. The frontend Provenance ``review | filter | share`` nodes
    derive from the API DATA this test asserts: the flag-for-review REVIEW node reads ESCALATE (the
    fired variant gate WINS over "skipped"), while FILTER / SHARE honestly read "not run in this
    build" (no artifact / no share event) — never a fabricated green."""
    _isolate_store(tmp_path, monkeypatch)  # isolate the SHARE store — no stray local export
    detail = client.get(f"/api/runs/{_RTH}").json()
    arts = client.get(f"/api/runs/{_RTH}/artifacts").json()

    # review = ESCALATE: the variant gate fired escalate, so the review node is NOT "skipped"...
    variant_outcomes = {
        (g["gate"], g["verdict"])
        for c in detail["cards"]
        for g in c["gate_results"]
        if g["gate"] == "variant"
    }
    assert ("variant", "escalate") in variant_outcomes
    # ...and no flag_for_review.json artifact exists — the FIRED GATE, not an artifact, is signal
    # (the RTH fixture carries variants.csv, not a .vcf/routing record).
    assert not any(a["stage"] == "review" for a in arts)

    # filter / share honestly did not run in this build: no filter-stage artifact, no share event.
    assert not any(a["stage"] in {"filter", "share"} for a in arts)
    assert not any(e["event_type"] == "data.exported" for e in detail["events"])

    # The mock run has no variant gate at all → its review node is honestly "not run" too.
    mock = client.get(f"/api/runs/{_MOCK}").json()
    assert not any(g["gate"] == "variant" for c in mock["cards"] for g in c["gate_results"])


def test_downstream_stage_seam_mapping_is_honest() -> None:
    """The W3 filename→stage seams (unit): a filtered/normalized VCF, a flag-for-review routing
    record, and a de-identified share manifest each land on their OWN downstream stage; the per-run
    flag_for_review ARMING marker (config, no extension) is never a data artifact."""
    from api.main import _artifact_stage_roles

    assert _artifact_stage_roles("HG002.norm.vcf.gz") == [("filter", "output")]
    assert _artifact_stage_roles("flag_for_review.json") == [("review", "output")]
    assert _artifact_stage_roles("share_manifest.json") == [("share", "output")]
    assert _artifact_stage_roles("flag_for_review") == []  # the arming marker is config, not data


# === Env-gated live confirmation =============================================================


def test_approved_germline_pipeline_stub_runs_live(tmp_path: Path) -> None:
    """Skip-safe live check: the SAME graph the offline tests approve+run must be a real,
    ``nextflow -stub-run``-valid pipeline. With ``nextflow`` on PATH, the compiled germline bundle
    validates end-to-end (every process' stub touches its outputs, so the whole DAG executes with no
    tools/data). Absent Nextflow → skip, never fail (this sandbox's default)."""
    nextflow = os.environ.get("BAYLEAF_NEXTFLOW_BIN") or shutil.which("nextflow")
    if not nextflow:
        pytest.skip("no `nextflow` on PATH — skipping the live stub-run check")

    bundle = compile_graph(germline_graph())
    for rel, content in bundle.files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    for name in ("r1.fastq.gz", "r2.fastq.gz", "panel.bed", "ref.fa", "ref.fa.fai",
                 "ref.fa.bwt.2bit.64"):  # fmt: skip
        (tmp_path / name).write_text("", encoding="utf-8")
    (tmp_path / "samplesheet.csv").write_text(
        "sample,fastq_1,fastq_2\nHG002,r1.fastq.gz,r2.fastq.gz\n", encoding="utf-8"
    )
    proc = subprocess.run(
        [nextflow, "run", str(tmp_path / "main.nf"), "-stub-run",
         "--input", str(tmp_path / "samplesheet.csv"),
         "--reference", str(tmp_path / "ref.fa"), "--panel_bed", str(tmp_path / "panel.bed")],
        cwd=tmp_path, capture_output=True, text=True, timeout=300, env=os.environ,
    )  # fmt: skip
    assert proc.returncode == 0, f"nextflow -stub-run failed:\n{proc.stdout}\n{proc.stderr}"
