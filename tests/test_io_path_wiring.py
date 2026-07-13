"""PROVE the I/O-path cards actually WORK end-to-end — a selected input PATH resolves to REAL files
AND flows into the Nextflow driver argv (not "just decoration").

Two layers of flag translation sit between an operator's picked input and the tool that consumes it,
and this module pins each hop OFFLINE (never runs Nextflow — the live run stays env-gated at the
bottom, joining the skip-safe pattern of ``test_nextflow_compile.py``):

    picked KEY (dropdown)                    ── GET /api/pipelines/run/inputs = _catalog() ──┐
      │  POST /api/pipelines/run  (pipeline_run.py)                                          │
      ▼                                                                                      ▼
    _catalog()[category] → _InputOption(paths=(real files on disk))  ← key → a REAL path
      │  _execute() builds the DRIVER argv                                                   │
      ▼                                                                                      │
    scripts/run_giab_pipeline.py  --read1/--read2  --reference  --panel-bed  <selected paths>│
      │  run_nextflow() builds the NEXTFLOW argv                                             │
      ▼                                                                                      ▼
    nextflow run … --input <samplesheet(fastq_1,fastq_2)>  --reference  --panel_bed  <paths>

Card-kind → param mapping (the two-hop translation, asserted below):

    | card kind        | driver flag (API → script) | nextflow param (script → nextflow) |
    | fastq (reads)    | --read1 / --read2          | fastq_1/fastq_2 cols of --input samplesheet |
    | reference_fasta  | --reference                | --reference                        |
    | panel_bed        | --panel-bed                | --panel_bed                        |

Decoration guard (2a): ``_catalog()`` FILTERS by ``all(p.exists())``, so it can never SURFACE a
dangling string — but reads/reference point under the git-ignored ``data/real-giab/`` tree, so on a
bare clone only ``panel_bed`` (a committed fixture) is guaranteed present. That honest filtering is
verified, and the git-ignored seam is documented, here.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest
import scripts.run_giab_pipeline as drv
from fastapi.testclient import TestClient
from scripts.seed_approved_germline import germline_graph_dict

import api.routers.intake as intake
import api.routers.pipeline_run as pr
from api.job_store import KIND_INTAKE
from api.main import app
from pipeguard.nextflow.catalog import REFERENCE_PARAM

client = TestClient(app)

_REVIEWER = {"X-PipeGuard-Role": "reviewer", "X-PipeGuard-Actor": "a.rivera"}
_REPO = Path(__file__).resolve().parent.parent


# ================================================= 2a. catalog entries are REAL, not decoration


def test_every_catalog_entry_resolves_to_files_that_exist_on_disk() -> None:
    """A picked input resolves to a REAL path, never a dangling string. ``_catalog()`` returns only
    options whose every path is present (the honest filter), so this pins that invariant: for every
    surfaced option, in every category, every path in ``option.paths`` exists on disk."""
    cat = pr._catalog()
    assert set(cat) == {"reads", "reference", "panel_bed"}
    for category, options in cat.items():
        for opt in options:
            assert opt.paths, f"{category}/{opt.key} surfaced with no paths"
            for p in opt.paths:
                assert p.exists(), (
                    f"DECORATION BUG: catalog entry {category}/{opt.key} surfaced a dangling path "
                    f"{p} — _catalog() must never surface an option whose files are absent"
                )


def test_panel_bed_option_is_a_committed_fixture_guaranteed_present() -> None:
    """At least one input is a COMMITTED fixture (guaranteed present in a bare clone): the panel BED
    resolves to ``scripts/panel_regions.example.bed``, which is tracked in git and on disk. This is
    the one run-input that is real end-to-end without fetching git-ignored GIAB data."""
    panel = pr._catalog()["panel_bed"]
    assert panel, "the committed panel BED must always surface"
    opt = next(o for o in panel if o.key == "example-panel")
    (bed,) = opt.paths
    assert bed == _REPO / "scripts" / "panel_regions.example.bed"
    assert bed.is_file() and bed.stat().st_size > 0
    # committed to git (not a git-ignored/untracked artifact) — the clean-checkout guarantee
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(bed.relative_to(_REPO))],
        cwd=_REPO, capture_output=True, text=True,
    )  # fmt: skip
    assert tracked.returncode == 0, "panel_regions.example.bed must be committed, not git-ignored"


def test_reads_and_reference_raw_paths_are_the_gitignored_giab_seam() -> None:
    """DOCUMENTED SEAM (not a bug): the reads + reference options point under the git-ignored
    ``data/real-giab/`` tree, so they surface only on a machine that has fetched the real GIAB data.
    ``_catalog()``'s existence filter hides them honestly on a bare clone (no dangling string) — the
    run path is simply not runnable end-to-end from a fresh clone, which is fine because the live
    run is env-gated anyway. This pins WHERE those inputs live so a future upload path is a
    conscious change, not an accident."""
    giab = _REPO / "data" / "real-giab"
    reads_r1 = giab / "fastq" / "HG002.R1.fastq.gz"
    reads_r2 = giab / "fastq" / "HG002.R2.fastq.gz"
    reference = giab / "ref" / "chr20.fa"
    for p in (reads_r1, reads_r2, reference):
        assert giab in p.parents, f"{p} is expected to live under the git-ignored real-giab tree"
    # Whatever this machine's state, the filter's contract holds: a surfaced reads/reference option
    # (if any) points at these git-ignored files and, being surfaced, they must exist.
    for opt in pr._catalog()["reads"]:
        assert opt.paths == (reads_r1, reads_r2) and all(p.exists() for p in opt.paths)
    for opt in pr._catalog()["reference"]:
        assert opt.paths == (reference,) and reference.exists()


# ===================================================== 2b. selected paths → DRIVER argv (API)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    return path


def test_execute_builds_driver_argv_with_the_exact_selected_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The API layer: ``_execute`` (the background job the endpoint hands off) must place the EXACT
    selected ``_InputOption`` paths onto the driver argv under the right flags — ``--read1/--read2``
    for reads, ``--reference`` for the FASTA, ``--panel-bed`` for the BED. This is the hop the
    'decoration' worry targets: a picked path that never reaches the driver."""
    read1 = _touch(tmp_path / "SEL.R1.fastq.gz")
    read2 = _touch(tmp_path / "SEL.R2.fastq.gz")
    reference = _touch(tmp_path / "sel_ref.fa")
    panel = _touch(tmp_path / "sel_panel.bed")
    reads_opt = pr._InputOption("k-reads", "sel reads", "test", (read1, read2))
    ref_opt = pr._InputOption("k-ref", "sel ref", "test", (reference,))
    panel_opt = pr._InputOption("k-panel", "sel panel", "test", (panel,))

    captured: dict[str, Any] = {}

    def fake_run_driver(cmd: list[str], *, cwd: str, env: dict[str, str]) -> Any:
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 1, "", "stub")  # nonzero → no mark side effects

    monkeypatch.setattr(pr, "run_driver", fake_run_driver)
    monkeypatch.setattr(pr, "_mark", lambda *a, **k: None)

    pr._execute(
        "RUN-IO-EXEC", tmp_path / "main.nf", "HG002", "HiSeq 2500", "op", "test",
        reads_opt, ref_opt, panel_opt,
    )  # fmt: skip

    cmd = captured["cmd"]
    assert cmd[cmd.index("--read1") + 1] == str(read1)
    assert cmd[cmd.index("--read2") + 1] == str(read2)
    assert cmd[cmd.index("--reference") + 1] == str(reference)
    assert cmd[cmd.index("--panel-bed") + 1] == str(panel)
    # The argv targets the real driver script + carries the run identity.
    assert str(pr._SCRIPT) in cmd
    assert cmd[cmd.index("--run-id") + 1] == "RUN-IO-EXEC"


class _FakeJobStore:
    """Minimal in-memory JobStore so the endpoint test writes nothing to ``.nf-runs``."""

    def __init__(self) -> None:
        self._recs: dict[tuple[str, str], dict[str, Any]] = {}

    def upsert(self, rec: dict[str, Any]) -> None:
        self._recs[(rec["run_id"], rec["kind"])] = rec

    def get(self, run_id: str, kind: str) -> dict[str, Any] | None:
        return self._recs.get((run_id, kind))


class _FakeStore:
    """In-memory PipelineGraphStore (only what the resolver / ``last_emitted`` reach)."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def get_versions(self, name: str) -> list[dict[str, Any]]:
        return sorted(
            (r for r in self._records if r.get("name") == name),
            key=lambda r: int(r.get("version") or 0),
        )

    def list(self, name: str | None = None) -> list[dict[str, Any]]:
        return [r for r in self._records if name is None or r.get("name") == name]


# A saved-envelope graph that consumes ALL THREE operator input kinds (fastq + reference_fasta +
# panel_bed) so a run must resolve every category — the maximal I/O-card surface. This is the seeded
# germline chain (via the shared ``germline_graph_dict()``), which needs exactly those three kinds
# AND produces the frozen-five QC — so it also clears Builder-Run's submit-time parse contract
# (a hand-built partial chain would be rejected before input resolution, defeating this test).
_GRAPH_3KIND: dict[str, Any] = germline_graph_dict()


def _approved(name: str, graph: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{name}-1",
        "name": name,
        "version": 1,
        "schema_version": "builder/0.1",
        "created_at": "2026-07-11T00:00:00+00:00",
        "emitted_at": "2026-07-11T00:00:00+00:00",
        "status": "approved",
        "graph": graph,
    }


def test_run_endpoint_resolves_selected_keys_to_real_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end at the ENDPOINT: ``POST /api/pipelines/run`` resolves each picked KEY against the
    server-side catalog to an ``_InputOption`` carrying REAL paths, and hands those exact options to
    the driver stage. Hermetic — the catalog is pointed at temp fixtures so the test never depends
    on the git-ignored GIAB data, and the job/pipeline stores are faked (no ``.nf-runs`` writes)."""
    read1 = _touch(tmp_path / "in" / "HGX.R1.fastq.gz")
    read2 = _touch(tmp_path / "in" / "HGX.R2.fastq.gz")
    reference = _touch(tmp_path / "in" / "picked_ref.fa")
    panel = _touch(tmp_path / "in" / "picked_panel.bed")
    fake_cat: dict[str, list[pr._InputOption]] = {
        "reads": [pr._InputOption("my-reads", "reads", "test", (read1, read2))],
        "reference": [pr._InputOption("my-ref", "ref", "test", (reference,))],
        "panel_bed": [pr._InputOption("my-panel", "panel", "test", (panel,))],
    }
    monkeypatch.setattr(pr, "_catalog", lambda: fake_cat)
    monkeypatch.setattr(pr, "_NF_RUNS", tmp_path / ".nf-runs")
    store = _FakeStore([_approved("io3", _GRAPH_3KIND)])
    monkeypatch.setattr(pr, "get_pipeline_store", lambda: store)
    monkeypatch.setattr(pr, "get_job_store", lambda: _FakeJobStore())

    captured: dict[str, Any] = {}
    done = threading.Event()

    def fake_execute(
        run_id: str,
        pipeline: Path,
        sample: str,
        platform: str,
        submitted_by: str,
        origin: str,
        reads: pr._InputOption | None,
        reference_opt: pr._InputOption | None,
        panel_opt: pr._InputOption | None,
    ) -> None:
        captured.update(reads=reads, reference=reference_opt, panel=panel_opt)
        with pr._lock:  # mirror the real _execute cleanup so _active doesn't leak across tests
            pr._active.discard(run_id)
        done.set()

    monkeypatch.setattr(pr, "_execute", fake_execute)

    resp = client.post(
        "/api/pipelines/run",
        json={
            "name": "io3",
            "run_id": "RUN-IO-ENDPOINT",
            "sample": "HG002",
            "inputs": {"reads": "my-reads", "reference": "my-ref", "panel_bed": "my-panel"},
        },
        headers=_REVIEWER,
    )
    assert resp.status_code == 202, resp.text
    assert done.wait(timeout=5), "the run thread never invoked the driver stage"

    # The picked KEYS resolved to the EXACT selected real paths (not dangling strings).
    assert captured["reads"].paths == (read1, read2)
    assert captured["reference"].paths == (reference,)
    assert captured["panel"].paths == (panel,)


# ============================================================ 2b/2c. DRIVER argv → NEXTFLOW argv


def test_driver_wires_selected_paths_into_the_nextflow_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The final hop: ``run_nextflow`` must place the selected reference/panel onto the ``nextflow
    run`` argv (``--reference`` / ``--panel_bed``) and the selected reads into the SAMPLESHEET it
    passes via ``--input`` (fastq_1/fastq_2 columns) — NOT a ``--reads`` flag. Monkeypatches
    ``subprocess.run`` (captures argv, never launches Nextflow) and ``shutil.which`` (so the driver
    doesn't skip on a machine without Nextflow)."""
    read1 = _touch(tmp_path / "MY.R1.fastq.gz")
    read2 = _touch(tmp_path / "MY.R2.fastq.gz")
    reference = _touch(tmp_path / "myref.fa")
    panel = _touch(tmp_path / "mypanel.bed")
    pipeline = _touch(tmp_path / "main.nf")

    monkeypatch.setattr(drv, "_NF_RUNS", tmp_path / ".nf-runs")
    monkeypatch.setattr(
        drv.shutil, "which", lambda name: "/fake/bin/nextflow" if name == "nextflow" else None
    )

    captured: dict[str, Any] = {}

    def fake_subprocess_run(cmd: list[str], **kw: Any) -> Any:
        captured["cmd"] = cmd
        # Emulate the pipeline publishing its results dir so run_nextflow doesn't sys.exit.
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        (outdir / "results").mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(drv.subprocess, "run", fake_subprocess_run)

    cfg = drv.RunConfig(
        run_id="RUN-IO-NF",
        run_dir=tmp_path / "data" / "RUN-IO-NF",
        platform="HiSeq 2500",
        run_date="2026-07-11",
        submitted_by="tester",
        sample="MYSAMPLE",
        pipeline=pipeline,
        read1=read1,
        read2=read2,
        reference=reference,
        panel_bed=panel,
    )
    results = drv.run_nextflow(cfg)
    assert results.is_dir()
    cmd = captured["cmd"]

    # reference + panel flow as explicit nextflow params, with the EXACT selected paths.
    assert cmd[cmd.index("--reference") + 1] == str(reference)
    assert cmd[cmd.index("--panel_bed") + 1] == str(panel)
    # reads flow via the samplesheet (--input), NOT a --reads flag.
    assert "--reads" not in cmd
    samplesheet = Path(cmd[cmd.index("--input") + 1])
    sheet = samplesheet.read_text()
    assert sheet.splitlines()[0] == "sample,fastq_1,fastq_2"
    assert str(read1) in sheet and str(read2) in sheet
    assert "MYSAMPLE" in sheet
    # the pipeline actually run is the one we passed
    assert str(pipeline) in cmd


def test_io_card_kind_maps_to_the_correct_nextflow_param() -> None:
    """2c: each I/O-card kind maps to the correct param at BOTH hops. The API's kind→category map
    and the compiler's REFERENCE_PARAM map are the source of truth; ``test_driver_wires_...`` above
    proves the resulting argv. Documents the fastq exception: reads do NOT get a param of their
    own — they ride the samplesheet under ``--input``."""
    # Hop 1 (endpoint): card kind → operator input category → driver flag group.
    assert pr._KIND_TO_CATEGORY == {
        "fastq": "reads",
        "reference_fasta": "reference",
        "panel_bed": "panel_bed",
    }
    # Hop 2 (compiler → nextflow.config params): reference kinds → their nextflow param names.
    assert REFERENCE_PARAM["reference_fasta"] == "reference"
    assert REFERENCE_PARAM["panel_bed"] == "panel_bed"
    # fastq is deliberately absent from REFERENCE_PARAM — it is a samplesheet queue channel, not a
    # value param (the compiler renders `params.input` = the samplesheet, W4 fan-out).
    assert "fastq" not in REFERENCE_PARAM


# =========================================== intake (Submit) path carries NO input selection


def test_intake_submit_path_uses_driver_defaults_no_input_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """DOCUMENTS the OTHER execution path: ``POST /api/runs`` (Submit) carries NO operator input
    selection — its driver argv passes only run identity, so the driver falls back to its committed
    HG002 defaults. Only the Builder-Run path (above) selects I/O by catalog key. Asserting the
    intake driver cmd has no ``--read1/--reference/--panel-bed`` pins that boundary. The driver
    params now come from the persisted job record (ADR-0021): seed one, then run the thread body."""
    captured: dict[str, Any] = {}

    def fake_run_driver(cmd: list[str], *, cwd: str, env: dict[str, str]) -> Any:
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 1, "", "stub")

    monkeypatch.setenv("PIPEGUARD_JOB_STORE", "jsonl")
    monkeypatch.setenv("PIPEGUARD_JOB_PATH", str(tmp_path / "jobs.jsonl"))
    monkeypatch.setattr(intake, "run_driver", fake_run_driver)
    monkeypatch.setattr(intake, "_mark", lambda *a, **k: None)
    # A default (no authored pipeline) intake job record — the seeded germline path.
    intake.get_job_store().upsert(
        {
            "kind": KIND_INTAKE,
            "run_id": "RUN-IO-INTAKE",
            "status": "queued",
            "created_at": intake.now_iso(),
            "updated_at": intake.now_iso(),
            "platform": "NovaSeq X",
            "run_date": "2026-07-11",
            "submitted_by": "op",
            "pipeline": None,
            "pipeline_path": None,
        }
    )

    intake._run_pipeline("RUN-IO-INTAKE")

    cmd = captured["cmd"]
    assert str(intake._SCRIPT) in cmd
    assert cmd[cmd.index("--run-id") + 1] == "RUN-IO-INTAKE"
    assert cmd[cmd.index("--platform") + 1] == "NovaSeq X"
    # No input-path selection on the Submit path — the driver uses its HG002 defaults; and no
    # ``--pipeline`` (the default germline path), unlike an authored-pipeline submit.
    for flag in ("--read1", "--read2", "--reference", "--panel-bed", "--pipeline"):
        assert flag not in cmd


# ============================================================ 4. live nextflow run — ENV-GATED skip


def test_driver_argv_shape_is_accepted_by_the_committed_pipeline_stub_run(tmp_path: Path) -> None:
    """Skip-safe live check (joins ``test_nextflow_compile.py``'s pattern): if ``nextflow`` is on
    PATH, prove the DRIVER's exact argv contract (``--input`` samplesheet + ``--reference`` +
    ``--panel_bed``) is ACCEPTED by the COMMITTED ``pipelines/germline/main.nf`` the intake driver
    actually runs — every process' stub touches its outputs, so the whole DAG validates with no
    tools/data. Absent Nextflow → skip, never fail. This proves WIRING (the argv the driver builds
    is the argv the shipped pipeline consumes), not a real toolchain run."""
    nextflow = os.environ.get("PIPEGUARD_NEXTFLOW_BIN") or shutil.which("nextflow")
    if not nextflow:
        pytest.skip("no `nextflow` on PATH — skipping the live stub-run wiring check")

    # Build the driver's argv shape against the committed pipeline; supply empty stand-in inputs.
    pipeline = _REPO / "pipelines" / "germline" / "main.nf"
    assert pipeline.is_file(), "the committed germline pipeline must exist"
    ref = tmp_path / "ref.fa"
    for name in ("ref.fa", "ref.fa.fai", "ref.fa.bwt.2bit.64", "panel.bed"):
        (tmp_path / name).write_text("", encoding="utf-8")
    r1, r2 = tmp_path / "r1.fastq.gz", tmp_path / "r2.fastq.gz"
    r1.write_text("", encoding="utf-8")
    r2.write_text("", encoding="utf-8")
    samplesheet = tmp_path / "samplesheet.csv"
    samplesheet.write_text(f"sample,fastq_1,fastq_2\nHG002,{r1},{r2}\n", encoding="utf-8")

    proc = subprocess.run(
        [nextflow, "run", str(pipeline), "-stub-run",
         "--input", str(samplesheet),
         "--reference", str(ref), "--panel_bed", str(tmp_path / "panel.bed"),
         "--outdir", str(tmp_path / "out")],
        cwd=tmp_path, capture_output=True, text=True, timeout=300, env=os.environ,
    )  # fmt: skip
    assert proc.returncode == 0, (
        f"driver argv rejected by the pipeline:\n{proc.stdout}\n{proc.stderr}"
    )
