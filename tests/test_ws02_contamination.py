"""WS-02 — VerifyBamID2 FREEMIX contamination as a gated QC metric (offline, fixture-driven).

Proves the WIRING, not a tool run: a small REAL-FORMAT VerifyBamID2 ``.selfSM`` fixture is parsed
by the live ingest adapter (``pipeguard.ingest.nfcore``) into the registry-keyed ``SampleMetrics``
contract, lowered to a canonical ``MetricValue`` (``contamination.freemix``), and run through the
deterministic gate (``run_gate``) — asserting the verdict/finding the runbook threshold produces.

FREEMIX is a plain scalar "metric vs threshold" check, so it flows through the EXISTING generic
QC-scoring loop (``rules.evaluate_sample`` → ``runbook.qc_thresholds`` → ``_evaluate_metric``):
there is NO bespoke ``_check_freemix`` rule. This file is the red-first proof of that path.

OFFLINE ONLY: verifybamid2 is never installed or run here (that is a separate, deferred, live pass).
The ``.selfSM`` fixture reproduces verifybamid2's real output columns; the gate parses that fixture.

The SVD/UD resource panel verifybamid2 needs for a LIVE run is a labelled pipeline input, not
fabricated here (ADR-0004 posture) — this test only exercises the parse→gate spine on fixture data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeguard import run_gate
from pipeguard.ingest.nfcore import ingest_results_dir
from pipeguard.metrics import metric_values_for
from pipeguard.models import (
    RunArtifacts,
    Sample,
    SampleSheetEntry,
    Severity,
    Verdict,
)
from pipeguard.synthesis import StubSynthesizer

# --------------------------------------------------------------------- real-format fixture builders

# VerifyBamID2 writes a per-sample ``{prefix}.selfSM``. Its real header (tab-separated) leads with
# the estimated cross-sample contamination fraction FREEMIX as the 7th column; the remaining columns
# are the log-likelihood / chip-mixture diagnostics. The extractor locates FREEMIX by HEADER name
# (tolerant of column-order drift), not a hardcoded index.
_SELFSM_HEADER = (
    "#SEQ_ID\tRG\tCHIP_ID\t#SNPS\t#READS\tAVG_DP\tFREEMIX\tFREELK1\tFREELK0\t"
    "FREE_RH\tFREE_RA\tCHIPMIX\tCHIPLK1\tCHIPLK0\tCHIP_RH\tCHIP_RA\tDPREF\tRDPHET\tRDPALT"
)


def _selfsm(sample: str, *, freemix: float) -> str:
    """A minimal REAL-shaped verifybamid2 ``.selfSM`` with FREEMIX in its canonical 7th column."""
    row = (
        f"{sample}\tALL\tNA\t1000000\t50000000\t35.2\t{freemix}\t"
        "1234.5\t1250.0\tNA\tNA\tNA\tNA\tNA\tNA\tNA\t35.0\t1.0\t0.5"
    )
    return f"{_SELFSM_HEADER}\n{row}\n"


def _min_fastp(sample: str, pub: Path) -> None:
    """A minimal fastp.json so ``ingest_results_dir`` DISCOVERS the sample (discovery is by the
    union of ``*.fastp.json`` and MultiQC). The ``.selfSM`` alone would not surface a sample."""
    (pub / f"{sample}.fastp.json").write_text(
        json.dumps(
            {
                "summary": {
                    "before_filtering": {"total_reads": 1_000_000},
                    "after_filtering": {"q30_rate": 0.90},
                },
                "filtering_result": {"passed_filter_reads": 990_000},
                "duplication": {"rate": 0.05},
            }
        )
    )


def _results_with_freemix(tmp_path: Path, sample: str, *, freemix: float) -> Path:
    """A published ``results/`` dir with a discoverable sample + its verifybamid2 ``.selfSM``."""
    pub = tmp_path / "results"
    pub.mkdir(parents=True, exist_ok=True)
    _min_fastp(sample, pub)
    (pub / f"{sample}.verifybamid2.selfSM").write_text(_selfsm(sample, freemix=freemix))
    return pub


def _artifacts(sample: str, sm_list) -> RunArtifacts:  # type: ignore[no-untyped-def]
    return RunArtifacts(
        run_id="WS02-CONTAM",
        sample_sheet=[SampleSheetEntry(sample_id=sample)],
        samples=[
            Sample(
                sample_id=sample,
                subject_id=sample,
                tissue="blood",
                library_prep="panel",
                submitted_by="tester",
            )
        ],
        qc=sm_list,  # SampleMetrics straight from the adapter — the WS-06·PR2 Union
    )


def _card_for(sample: str, sm_list):  # type: ignore[no-untyped-def]
    cards = run_gate(_artifacts(sample, sm_list), synthesizer=StubSynthesizer())
    return {c.sample_id: c for c in cards}[sample]


# ============================================================ ingest: real .selfSM -> SampleMetrics


def test_selfsm_freemix_parses_into_contamination_metric(tmp_path: Path) -> None:
    """The real parse path: a verifybamid2 ``.selfSM`` -> ``contamination.freemix`` on the true
    (fraction) source scale, normalized identity to the canonical fraction."""
    pub = _results_with_freemix(tmp_path, "HG002", freemix=0.0312)
    ing = ingest_results_dir(pub)

    sm = next(s for s in ing.samples if s.sample_id == "HG002")
    assert "contamination.freemix" in sm.raw  # the metric was actually extracted, not invented
    obs = sm.raw["contamination.freemix"]
    assert obs.raw_unit == "fraction"  # DECLARED at the true source scale
    assert obs.raw_value == pytest.approx(0.0312)

    by_key = {mv.metric_key: mv.normalized_value for mv in metric_values_for(sm)}
    assert by_key["contamination.freemix"] == pytest.approx(0.0312)


def test_absent_selfsm_is_not_a_hole(tmp_path: Path) -> None:
    """verifybamid2 is NOT in the germline default profile, so an absent ``.selfSM`` is OPTIONAL —
    it must NOT be reported as an ``absent_source`` hole (which would flag every lean run)."""
    pub = tmp_path / "results"
    pub.mkdir()
    _min_fastp("HG002", pub)  # fastp present, no .selfSM

    ing = ingest_results_dir(pub)
    sm = next(s for s in ing.samples if s.sample_id == "HG002")
    assert "contamination.freemix" not in sm.raw
    absent = {(u.sample_id, u.leaf_key) for u in ing.unmapped}
    assert ("HG002", "contamination.freemix") not in absent  # optional tool, not a hole


# ==================================================== gate: FREEMIX threshold fires / clears


def test_high_freemix_holds_on_contamination(tmp_path: Path) -> None:
    """FREEMIX above the illustrative gate (0.02) -> a ``QC-FREEMIX`` WARN finding suggesting HOLD,
    scored by the GENERIC metric loop (no bespoke rule). The card verdict is HOLD-or-worse."""
    pub = _results_with_freemix(tmp_path, "HG002", freemix=0.0312)  # 3.12%: > 2% gate, < 5% hard
    ing = ingest_results_dir(pub)
    card = _card_for("HG002", ing.samples)

    freemix_findings = [f for f in card.findings if f.rule_id == "QC-FREEMIX"]
    assert len(freemix_findings) == 1
    f = freemix_findings[0]
    assert f.severity is Severity.WARN
    assert f.suggested_verdict is Verdict.HOLD
    # It gates on the contamination our_key via the generic loop, not a hand-written rule.
    assert any(e.source_field == "freemix" for e in f.evidence)
    # Card verdict is at least HOLD (contamination alone would HOLD; cluster_pf-missing also HOLDs).
    assert card.verdict in {Verdict.HOLD, Verdict.RERUN, Verdict.ESCALATE}


def test_critical_freemix_rerun(tmp_path: Path) -> None:
    """FREEMIX past the hard-fail (0.05) -> CRITICAL, suggesting RERUN (heavily contaminated)."""
    pub = _results_with_freemix(tmp_path, "HG002", freemix=0.08)
    ing = ingest_results_dir(pub)
    card = _card_for("HG002", ing.samples)

    f = next(f for f in card.findings if f.rule_id == "QC-FREEMIX")
    assert f.severity is Severity.CRITICAL
    assert f.suggested_verdict is Verdict.RERUN


def test_clean_freemix_not_flagged(tmp_path: Path) -> None:
    """A clean FREEMIX (below the gate) is NOT flagged on contamination — the metric clears even
    though the run may still HOLD for an unrelated reason (structural cluster_pf-missing)."""
    pub = _results_with_freemix(tmp_path, "HG002", freemix=0.001)
    ing = ingest_results_dir(pub)
    card = _card_for("HG002", ing.samples)

    assert not any(f.rule_id == "QC-FREEMIX" for f in card.findings)
    # Sanity: the contamination metric WAS observed (so "not flagged" means "passed", not "absent").
    by_key = {mv.metric_key: mv.normalized_value for mv in metric_values_for(ing.samples[0])}
    assert by_key["contamination.freemix"] == pytest.approx(0.001)
