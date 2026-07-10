"""Execution-trace ingestion → EXEC-001 (the pipeline-repair agent's structured issue feed).

A Nextflow/nf-core ``trace.txt`` is READ, never run (composes ≠ executes, ADR-0001/0003): a
failed task becomes a structured EXEC-001 Finding that drives the sample to RERUN and flows to
the pipeline-repair agent through the recurring-signature rollup. Fully offline; the pinned demo
runs (which have no ``trace.txt``) are unaffected — asserted in ``test_no_trace_file...``.
"""

from pathlib import Path

from pipeguard import propose_repair, run_gate_from_dir
from pipeguard.models import TraceRecord, Verdict
from pipeguard.parsers import parse_execution_trace
from pipeguard.pipeline_repair import recurring_signature
from pipeguard.rules import _check_execution_trace
from pipeguard.runbook import DEFAULT_RUNBOOK
from pipeguard.synthetic.generator import FailureMode, RunSpec, SampleSpec, generate_run

# A realistic Nextflow trace: S02 FAILED (exit 1), S03 a nonzero exit despite a non-FAILED
# status (an OOM/time-kill), S01 clean.
_TRACE_TSV = (
    "task_id\tprocess\ttag\tstatus\texit\n"
    "1\tFASTP\tS01\tCOMPLETED\t0\n"
    "2\tALIGN_BWA\tS02\tFAILED\t1\n"
    "3\tALIGN_BWA\tS03\tCOMPLETED\t137\n"
)


def _parse(tmp_path: Path, body: str) -> list[TraceRecord]:
    p = tmp_path / "trace.txt"
    p.write_text(body)
    return parse_execution_trace(p)


def test_parse_execution_trace_tab_separated(tmp_path: Path) -> None:
    recs = _parse(tmp_path, _TRACE_TSV)
    assert [r.tag for r in recs] == ["S01", "S02", "S03"]
    assert recs[1].status == "FAILED" and recs[1].exit == 1
    assert recs[2].process == "ALIGN_BWA" and recs[2].exit == 137


def test_parse_execution_trace_is_tolerant(tmp_path: Path) -> None:
    assert parse_execution_trace(tmp_path / "absent.txt") == []  # absent -> [] (a signal)
    # A garbled file must not crash the boundary parse.
    assert isinstance(_parse(tmp_path, "junk\x00 not a trace"), list)


def test_exec_001_failed_task_is_a_rerun_finding(tmp_path: Path) -> None:
    trace = _parse(tmp_path, _TRACE_TSV)
    f = _check_execution_trace("S02", trace, DEFAULT_RUNBOOK)
    assert f is not None and f.rule_id == "EXEC-001"
    assert f.suggested_verdict is Verdict.RERUN
    assert f.gate.value == "preflight"
    assert any(e.source == "trace.txt" for e in f.evidence)  # cited, structured
    # A nonzero exit fires even when the status isn't literally FAILED (OOM/time kill).
    assert _check_execution_trace("S03", trace, DEFAULT_RUNBOOK) is not None


def test_exec_001_is_a_no_op_when_clean_or_absent(tmp_path: Path) -> None:
    trace = _parse(tmp_path, _TRACE_TSV)
    assert _check_execution_trace("S01", trace, DEFAULT_RUNBOOK) is None  # COMPLETED, exit 0
    assert _check_execution_trace("S02", [], DEFAULT_RUNBOOK) is None  # no trace at all
    assert _check_execution_trace("NOPE", trace, DEFAULT_RUNBOOK) is None  # unknown sample


def test_exec_001_tag_exact_match_no_crossfire() -> None:
    # tag == sid EXACT, so S1's failure never attaches to S10 (the substring trap PIPE-001's
    # log grep is prone to — the reason this rule matches the tag exactly).
    trace = [TraceRecord(tag="S1", status="FAILED", exit=1)]
    assert _check_execution_trace("S1", trace, DEFAULT_RUNBOOK) is not None
    assert _check_execution_trace("S10", trace, DEFAULT_RUNBOOK) is None


def _gen(tmp_path: Path, modes: list[FailureMode]) -> Path:
    spec = RunSpec(
        run_id="mock_run_exec",
        run_name="RUN-EXEC",
        date="2026-07-09",
        samples=[SampleSpec(sample_id=f"S0{i + 1}", mode=m) for i, m in enumerate(modes)],
    )
    return generate_run(spec, tmp_path)


def test_exec_001_end_to_end_through_the_gate(tmp_path: Path) -> None:
    run_dir = _gen(tmp_path, [FailureMode.CLEAN, FailureMode.PROCESS_FAILURE])
    assert (run_dir / "trace.txt").exists()  # the sixth artifact appears for a process failure
    _, cards = run_gate_from_dir(run_dir)
    by_id = {c.sample_id: c for c in cards}
    assert by_id["S02"].verdict is Verdict.RERUN
    assert any(f.rule_id == "EXEC-001" for f in by_id["S02"].findings)
    assert by_id["S01"].verdict is Verdict.PROCEED
    assert not any(f.rule_id == "EXEC-001" for f in by_id["S01"].findings)


def test_no_trace_file_means_no_exec_finding(tmp_path: Path) -> None:
    run_dir = _gen(tmp_path, [FailureMode.CLEAN, FailureMode.CLEAN])
    assert not (run_dir / "trace.txt").exists()  # no process failure -> no trace.txt emitted
    _, cards = run_gate_from_dir(run_dir)
    assert all(not any(f.rule_id == "EXEC-001" for f in c.findings) for c in cards)


def test_exec_001_feeds_the_repair_agent(tmp_path: Path) -> None:
    run_dir = _gen(tmp_path, [FailureMode.CLEAN, FailureMode.PROCESS_FAILURE])
    _, cards = run_gate_from_dir(run_dir)
    sig_key = next(f.signature for c in cards for f in c.findings if f.rule_id == "EXEC-001")
    sig = recurring_signature({run_dir.name: cards}, sig_key)
    assert sig is not None and sig.rule_id == "EXEC-001"
    prop = propose_repair(sig)
    assert prop.advisory is True
    assert prop.addresses_rule_id == "EXEC-001"
    assert "verdict" not in prop.model_dump()  # advisory only — never a verdict
    assert prop.summary.strip()  # a concrete, human-reviewed remediation
