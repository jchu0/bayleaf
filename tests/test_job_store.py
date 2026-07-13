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

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from api import job_store
from api.job_store import (
    DRIVER_TIMEOUT_S,
    KIND_BUILDER_RUN,
    KIND_INTAKE,
    JsonlJobStore,
    SqliteJobStore,
    get_job_store,
    now_iso,
    run_driver,
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
    monkeypatch.delenv("BAYLEAF_JOB_STORE", raising=False)
    monkeypatch.setenv("BAYLEAF_JOB_PATH", str(tmp_path / "jobs.events.jsonl"))


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
    monkeypatch.setenv("BAYLEAF_JOB_STORE", "sqlite")
    monkeypatch.setenv("BAYLEAF_JOB_DB", str(blocker / "nested" / "jobs.sqlite"))
    monkeypatch.setenv("BAYLEAF_JOB_PATH", str(tmp_path / "jobs.events.jsonl"))
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


def test_builder_run_with_no_result_recovers_lost(monkeypatch: Any, tmp_path: Path) -> None:
    """The Builder-run ``_reconcile`` **lost** branch — the mirror of the intake one, previously
    uncovered (only the Builder ``complete`` + disk-fallback branches were). A persisted running
    Builder job whose owning process is gone (not in ``_active``) AND whose result dir is absent
    resolves to ``lost``, never an eternal ``running`` spinner, and the reconciliation persists."""
    import api.routers.pipeline_run as pr

    store = _restart_env(monkeypatch, tmp_path, pr)
    store.upsert(_job(KIND_BUILDER_RUN, "RUN-B-GONE", status="running", steps=["FASTP"]))
    out = pr.run_status("RUN-B-GONE")  # no run dir on disk → the work is gone
    assert out.status == "lost" and out.error and "restarted" in out.error
    assert store.get("RUN-B-GONE", KIND_BUILDER_RUN)["status"] == "lost"  # type: ignore[index]


# --- shared timeout constant ----------------------------------------------------------------


def test_one_shared_driver_timeout_across_both_routers() -> None:
    import api.routers.intake as intake
    import api.routers.pipeline_run as pr

    # P3-7: both routers launch through the ONE shared helper/constant (no 900-vs-1800 asymmetry).
    assert intake.run_driver is pr.run_driver
    assert DRIVER_TIMEOUT_S == 1800


# --- atomic duplicate-run-id reservation (P3-8) ---------------------------------------------


def test_concurrent_same_run_id_submits_reserve_atomically(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """P3-8: two concurrent submits of the SAME run id → exactly ONE reserves and proceeds, the
    other gets a 409. This drives the REAL router reservation (``_lock`` + ``_active`` + the queued
    ``upsert``, all under one lock), not a re-implementation — with the background driver thread
    stubbed to a no-op so the winner never shells out to Nextflow. A ``threading.Barrier`` releases
    both threads at once so they genuinely contend on the reservation lock."""
    from fastapi import HTTPException

    import api.routers.intake as intake
    from api.auth import Actor

    _use_jsonl(monkeypatch, tmp_path)
    monkeypatch.setattr(intake, "_DATA", tmp_path / "data")
    monkeypatch.setattr(intake, "_active", set())
    # Stub the background job: the winner starts a thread, but it must NOT launch the real driver.
    monkeypatch.setattr(intake, "_run_pipeline", lambda *a, **k: None)

    actor = Actor(id="tester", role="reviewer")
    body = intake.SubmitRunIn(run_name="RUN-DUP", samples=[intake.SampleIn(sample="HG002")])

    statuses: list[str] = []
    codes: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def submit() -> None:
        barrier.wait()  # both threads leave the gate together → real contention on ``_lock``
        try:
            ack = intake.submit_run(body, actor)
            with lock:
                statuses.append(ack.status)
        except HTTPException as exc:
            with lock:
                codes.append(exc.status_code)

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert not any(t.is_alive() for t in threads)

    # The invariant: exactly one winner (queued) and exactly one 409 loser — never two runs.
    assert statuses == ["queued"], statuses
    assert codes == [409], codes
    # Reservation is single: one queued job persisted, and the id is claimed in ``_active`` once.
    store = get_job_store()
    dup_rows = [r for r in store.list(kind=KIND_INTAKE) if r["run_id"] == "RUN-DUP"]
    assert len(dup_rows) == 1 and dup_rows[0]["status"] == "queued"
    assert "RUN-DUP" in intake._active


# --- killpg process-group live reap (EVAL-008) ----------------------------------------------

# The reap test needs real POSIX process groups (os.killpg/getpgid, start_new_session) and a
# ``sh`` to fork a grandchild — skip cleanly where those don't exist (e.g. Windows).
_POSIX_GROUPS = hasattr(os, "killpg") and hasattr(os, "getpgid") and sys.platform != "win32"
_HAS_SH = shutil.which("sh") is not None
requires_pgroups = pytest.mark.skipif(
    not (_POSIX_GROUPS and _HAS_SH),
    reason="POSIX process groups + /bin/sh required to exercise the killpg subtree reap",
)

# A driver that forks a GRANDCHILD (``sleep``) which outlives the direct child (``sh`` blocks in
# ``wait``): the direct child echoes the grandchild's PID to stdout, then blocks. The grandchild's
# fds are redirected OFF the stdout pipe so the pipe closes when the direct child dies (whether the
# whole group is reaped or — in the stubbed negative control — only the direct child is), keeping
# ``run_driver``'s post-kill ``communicate()`` from blocking on the surviving grandchild.
_GRANDCHILD_CMD = ["sh", "-c", "sleep 30 >/dev/null 2>&1 & echo $! ; wait"]


def _alive(pid: int) -> bool:
    """True iff a signalable process with this pid exists — ``os.kill(pid, 0)``, stdlib only."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # exists but not ours to signal (not expected for a same-user child)
        return True
    return True


def _wait_until_dead(pid: int, timeout: float = 4.0) -> bool:
    """Poll until the pid is gone (reaped by init/subreaper) or the timeout elapses. Absorbs the
    tiny window between SIGKILL delivery and the OS actually reaping the orphaned grandchild."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.02)
    return not _alive(pid)


def _spawn_and_time_out(monkeypatch: Any, tmp_path: Path) -> int:
    """Run ``_GRANDCHILD_CMD`` through ``run_driver`` with a 1 s timeout; return the grandchild PID
    the direct child echoed to stdout. Asserts the TimeoutExpired path actually fired."""
    monkeypatch.setattr(job_store, "DRIVER_TIMEOUT_S", 1)  # tiny timeout keeps the test ~1 s
    with pytest.raises(subprocess.TimeoutExpired) as ei:
        run_driver(_GRANDCHILD_CMD, cwd=str(tmp_path), env=dict(os.environ))
    out = ei.value.output or ""
    return int(out.strip().splitlines()[0])


@requires_pgroups
def test_run_driver_timeout_reaps_the_whole_process_group(monkeypatch: Any, tmp_path: Path) -> None:
    """EVAL-008 live reap: a driver whose grandchild outlives the direct child is reaped WHOLE on a
    timeout. ``run_driver`` starts a new session (``start_new_session``), so on ``TimeoutExpired``
    it ``os.killpg``s the process group — the grandchild ``sleep`` dies with the direct ``sh``,
    proving the orphan-subtree fix. Without the group kill the grandchild would be reparented and
    linger (asserted by the negative-control test below)."""
    grandchild_pid = _spawn_and_time_out(monkeypatch, tmp_path)
    assert _wait_until_dead(grandchild_pid), (
        f"grandchild pid {grandchild_pid} survived the timeout — the process group was NOT reaped"
    )


@requires_pgroups
def test_reap_assertion_detects_an_orphan_when_killpg_is_stubbed(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """The reap test's teeth. Stub ``_kill_group`` down to a direct-child-only ``proc.kill()`` (the
    OLD, pre-fix behavior) and the SAME grandchild now ORPHANS — surviving the timeout — which
    proves the liveness assertion above genuinely detects a lingering subtree rather than passing
    vacuously. We then reap the deliberately-orphaned ``sleep`` ourselves so nothing leaks."""
    # Simulate the pre-fix code path: reap only the direct child, never the whole group.
    monkeypatch.setattr(job_store, "_kill_group", lambda proc: proc.kill())
    grandchild_pid = _spawn_and_time_out(monkeypatch, tmp_path)
    try:
        # Only the direct child was killed → the grandchild is reparented and SURVIVES: exactly the
        # orphan the killpg fix prevents. (A short grace poll avoids asserting on a startup race.)
        assert not _wait_until_dead(grandchild_pid, timeout=0.5), (
            "grandchild died without killpg — the reap test could pass vacuously"
        )
        assert _alive(grandchild_pid)
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(grandchild_pid, signal.SIGKILL)  # never leak the orphaned sleep
