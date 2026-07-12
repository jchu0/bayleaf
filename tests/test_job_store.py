"""The durable execution-job store (``api/job_store.py``, P3-2/P3-7) — offline guarantees.

Mirrors ``test_share_store.py``/``test_review_queue.py`` discipline for the job sink that makes the
intake + Builder-run endpoints survive a backend restart. It pins the seam's *guarantees* without a
live server: the default is JSONL, ``upsert`` is insert-or-replace keyed on ``(kind, run_id)``, the
two kinds don't collide on a shared run id, the SQLite projection is byte-identical to the JSONL
one, a misconfigured SQLite path degrades to JSONL instead of crashing the execution path, a corrupt
line is tolerated. The restart-recovery half (the routers' ``_reconcile``) is exercised directly:
a persisted ``running`` job whose owning process is gone resolves to ``complete`` (result on disk)
or ``lost`` (nothing on disk), never an eternal spinner.

The shared process-group driver launcher (``run_driver``) is covered by monkeypatching so no real
``nextflow`` is invoked — the offline suite never shells out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api.job_store import (
    DRIVER_TIMEOUT_S,
    KIND_BUILDER_RUN,
    KIND_INTAKE,
    JsonlJobStore,
    SqliteJobStore,
    get_job_store,
    now_iso,
)


def _job(kind: str, run_id: str, *, status: str = "queued", **extra: Any) -> dict[str, Any]:
    now = now_iso()
    rec: dict[str, Any] = {
        "kind": kind,
        "run_id": run_id,
        "status": status,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    rec.update(extra)
    return rec


def _use_jsonl(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.delenv("PIPEGUARD_JOB_STORE", raising=False)
    monkeypatch.setenv("PIPEGUARD_JOB_PATH", str(tmp_path / "jobs.events.jsonl"))


# --- round-trip + upsert semantics ----------------------------------------------------------


def test_jsonl_is_the_default_and_round_trips(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_job_store()
    assert isinstance(store, JsonlJobStore)  # default when no store env is set

    store.upsert(_job(KIND_INTAKE, "RUN-A", processed=["HG002"], skipped=["HG003"]))
    store.upsert(_job(KIND_BUILDER_RUN, "RUN-B", steps=["FASTP", "BWA_MEM2_MEM"]))

    got = store.get("RUN-A", KIND_INTAKE)
    assert got is not None and got["processed"] == ["HG002"] and got["skipped"] == ["HG003"]
    assert store.get("RUN-B", KIND_BUILDER_RUN)["steps"] == ["FASTP", "BWA_MEM2_MEM"]  # type: ignore[index]
    assert store.get("RUN-NONE", KIND_INTAKE) is None
    assert {r["run_id"] for r in store.list()} == {"RUN-A", "RUN-B"}
    assert [r["run_id"] for r in store.list(kind=KIND_INTAKE)] == ["RUN-A"]


def test_upsert_replaces_not_duplicates(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_job_store()
    store.upsert(_job(KIND_INTAKE, "RUN-A", status="queued"))
    store.upsert(_job(KIND_INTAKE, "RUN-A", status="running"))
    store.upsert(_job(KIND_INTAKE, "RUN-A", status="complete"))
    rows = store.list(kind=KIND_INTAKE)
    assert len(rows) == 1 and rows[0]["status"] == "complete"  # one row, latest status wins


def test_kind_namespaces_the_run_id(monkeypatch: Any, tmp_path: Path) -> None:
    # The same run id under two kinds is two distinct records — no collision on the store key.
    _use_jsonl(monkeypatch, tmp_path)
    store = get_job_store()
    store.upsert(_job(KIND_INTAKE, "RUN-X", status="running"))
    store.upsert(_job(KIND_BUILDER_RUN, "RUN-X", status="complete"))
    assert store.get("RUN-X", KIND_INTAKE)["status"] == "running"  # type: ignore[index]
    assert store.get("RUN-X", KIND_BUILDER_RUN)["status"] == "complete"  # type: ignore[index]


# --- SQLite parity + degrade-to-jsonl -------------------------------------------------------


def test_sqlite_round_trips(tmp_path: Path) -> None:
    store = SqliteJobStore(str(tmp_path / "jobs.sqlite"))
    store.upsert(_job(KIND_INTAKE, "RUN-A", processed=["HG002"]))
    store.upsert(_job(KIND_INTAKE, "RUN-A", status="complete", processed=["HG002"]))  # replace
    assert len(store.list(kind=KIND_INTAKE)) == 1
    got = store.get("RUN-A", KIND_INTAKE)
    assert got is not None and got["status"] == "complete" and got["processed"] == ["HG002"]


def test_sqlite_projection_matches_jsonl(monkeypatch: Any, tmp_path: Path) -> None:
    # The load-bearing parity test: the SAME jobs through JSONL and SQLite read back identical.
    _use_jsonl(monkeypatch, tmp_path)
    jsonl = get_job_store()
    sqlite = SqliteJobStore(str(tmp_path / "jobs.sqlite"))
    jobs = [
        _job(KIND_INTAKE, "RUN-A", processed=["HG002"]),
        _job(KIND_BUILDER_RUN, "RUN-B", steps=["FASTP"]),
    ]
    for j in jobs:
        jsonl.upsert(j)
        sqlite.upsert(j)
    for kind, run in ((KIND_INTAKE, "RUN-A"), (KIND_BUILDER_RUN, "RUN-B"), (KIND_INTAKE, "RUN-Z")):
        assert jsonl.get(run, kind) == sqlite.get(run, kind), run
    assert jsonl.list() == sqlite.list()


def test_sqlite_selection_degrades_to_jsonl(monkeypatch: Any, tmp_path: Path) -> None:
    # =sqlite pointed at an unconstructable path must NOT crash — it degrades to JSONL.
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a dir", encoding="utf-8")  # parent-of-DB is a plain file
    monkeypatch.setenv("PIPEGUARD_JOB_STORE", "sqlite")
    monkeypatch.setenv("PIPEGUARD_JOB_DB", str(blocker / "nested" / "jobs.sqlite"))
    monkeypatch.setenv("PIPEGUARD_JOB_PATH", str(tmp_path / "jobs.events.jsonl"))
    store = get_job_store()
    assert isinstance(store, JsonlJobStore)  # fell back rather than raising
    store.upsert(_job(KIND_INTAKE, "RUN-A"))  # still writes, via the fallback
    assert store.get("RUN-A", KIND_INTAKE) is not None


def test_jsonl_tolerates_a_corrupt_line(monkeypatch: Any, tmp_path: Path) -> None:
    _use_jsonl(monkeypatch, tmp_path)
    store = get_job_store()
    store.upsert(_job(KIND_INTAKE, "RUN-A", status="complete"))
    path = tmp_path / "jobs.events.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + '{"partial":\n', encoding="utf-8")
    store.upsert(_job(KIND_BUILDER_RUN, "RUN-B", status="complete"))  # a corrupt line is skipped
    assert {r["run_id"] for r in store.list()} == {"RUN-A", "RUN-B"}


# --- restart recovery (the routers' _reconcile) ---------------------------------------------


def _restart_env(monkeypatch: Any, tmp_path: Path, module: Any) -> Any:
    """Point a router's job store at a tmp JSONL, its data dir at tmp, and simulate a fresh process
    (an empty ``_active`` — this process has launched no thread)."""
    _use_jsonl(monkeypatch, tmp_path)
    monkeypatch.setattr(module, "_DATA", tmp_path / "data")
    monkeypatch.setattr(module, "_active", set())
    return get_job_store()


def test_running_intake_job_with_result_on_disk_recovers_complete(
    monkeypatch: Any, tmp_path: Path
) -> None:
    import api.routers.intake as intake

    store = _restart_env(monkeypatch, tmp_path, intake)
    store.upsert(_job(KIND_INTAKE, "RUN-DONE", status="running", processed=["HG002"], skipped=[]))
    # The run actually finished on disk before the restart.
    rundir = tmp_path / "data" / "RUN-DONE"
    rundir.mkdir(parents=True)
    (rundir / "SampleSheet.csv").write_text("Sample_ID\nHG002\n", encoding="utf-8")

    st = intake.intake_status("RUN-DONE")
    assert st.status == "complete"
    # The reconciliation is persisted, so a re-read is stable (no re-spin on the next poll).
    assert store.get("RUN-DONE", KIND_INTAKE)["status"] == "complete"  # type: ignore[index]


def test_running_intake_job_with_no_result_recovers_lost(monkeypatch: Any, tmp_path: Path) -> None:
    import api.routers.intake as intake

    store = _restart_env(monkeypatch, tmp_path, intake)
    store.upsert(_job(KIND_INTAKE, "RUN-GONE", status="running"))
    st = intake.intake_status("RUN-GONE")  # no run dir on disk → the work is gone
    assert st.status == "lost" and st.error and "restarted" in st.error
    assert store.get("RUN-GONE", KIND_INTAKE)["status"] == "lost"  # type: ignore[index]


def test_running_job_still_active_is_not_reconciled(monkeypatch: Any, tmp_path: Path) -> None:
    import api.routers.intake as intake

    store = _restart_env(monkeypatch, tmp_path, intake)
    monkeypatch.setattr(intake, "_active", {"RUN-LIVE"})  # THIS process is running it right now
    store.upsert(_job(KIND_INTAKE, "RUN-LIVE", status="running"))
    st = intake.intake_status("RUN-LIVE")
    assert st.status == "running"  # a genuinely-live job is left alone


def test_builder_run_status_recovers_and_has_disk_fallback(
    monkeypatch: Any, tmp_path: Path
) -> None:
    import api.routers.pipeline_run as pr

    store = _restart_env(monkeypatch, tmp_path, pr)
    # (a) A persisted running Builder job with a finished run dir recovers to complete.
    store.upsert(_job(KIND_BUILDER_RUN, "RUN-B1", status="running", steps=["FASTP"]))
    d1 = tmp_path / "data" / "RUN-B1"
    d1.mkdir(parents=True)
    (d1 / "SampleSheet.csv").write_text("x", encoding="utf-8")
    assert pr.run_status("RUN-B1").status == "complete"

    # (b) The disk fallback: a run whose job record is unknown but whose dir is on disk reads
    # complete, not a misleading 404 (the P3-2 Builder-run half).
    d2 = tmp_path / "data" / "RUN-ONDISK"
    d2.mkdir(parents=True)
    (d2 / "SampleSheet.csv").write_text("x", encoding="utf-8")
    assert pr.run_status("RUN-ONDISK").status == "complete"


# --- shared timeout constant ----------------------------------------------------------------


def test_one_shared_driver_timeout_across_both_routers() -> None:
    import api.routers.intake as intake
    import api.routers.pipeline_run as pr

    # P3-7: both routers launch through the ONE shared helper/constant (no 900-vs-1800 asymmetry).
    assert intake.run_driver is pr.run_driver
    assert DRIVER_TIMEOUT_S == 1800
