"""WS-04 — hap.py GIAB SNP-F1 concordance as a gated QC metric (offline, fixture-driven).

Proves the WIRING, not a tool run: a small REAL-FORMAT hap.py ``summary.csv`` fixture is parsed by
the live ingest adapter (``pipeguard.ingest.nfcore``) into the registry-keyed ``SampleMetrics``
contract, lowered to a canonical ``MetricValue`` (``concordance.snp_f1``), and run through the
deterministic gate (``run_gate``) — asserting the verdict/finding the runbook threshold produces.

SNP-F1 is a plain scalar "metric vs threshold" check (monotonic-good-high, so a one-sided FLOOR),
so it flows through the EXISTING generic QC-scoring loop (``rules.evaluate_sample`` →
``runbook.qc_thresholds`` → ``_evaluate_metric``): there is NO bespoke ``_check_concordance`` rule.

OFFLINE ONLY: hap.py is never installed or run here (that is a separate, deferred, live pass). The
``summary.csv`` fixture reproduces hap.py's real output columns; the gate parses that fixture.

The GIAB truth VCF + high-confidence BED hap.py needs for a LIVE run are LABELLED pipeline inputs,
never invented or hardcoded here (ADR-0004: never fabricate truth) — this test only exercises the
parse→gate spine on fixture data.
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

# hap.py writes a per-sample ``{prefix}.summary.csv`` with one row per (Type, Filter) combination
# (INDEL/ALL, INDEL/PASS, SNP/ALL, SNP/PASS). Concordance is read from the SNP + PASS row's
# METRIC.F1_Score column. The INDEL rows carry a DIFFERENT F1 so a naive "first F1" parser would
# read the wrong value — the extractor must select SNP/PASS by (Type, Filter).
_HAPPY_HEADER = (
    "Type,Filter,TRUTH.TOTAL,TRUTH.TP,TRUTH.FN,QUERY.TOTAL,QUERY.FP,QUERY.UNK,FP.gt,FP.al,"
    "METRIC.Recall,METRIC.Precision,METRIC.Frac_NA,METRIC.F1_Score,"
    "TRUTH.TOTAL.TiTv_ratio,QUERY.TOTAL.TiTv_ratio,TRUTH.TOTAL.het_hom_ratio,QUERY.TOTAL.het_hom_ratio"
)


def _happy_summary(
    *, snp_f1: float, snp_recall: float = 0.9867, snp_precision: float = 0.9970
) -> str:
    """A minimal REAL-shaped hap.py ``summary.csv`` with the parametrized SNP/PASS F1."""
    rows = [
        _HAPPY_HEADER,
        # INDEL rows carry a distinct F1 (0.9818) — the extractor must NOT pick these.
        "INDEL,ALL,500000,490000,10000,510000,5000,8000,300,200,0.9800,0.9900,0.0157,0.9850,,,1.4,1.42",
        "INDEL,PASS,500000,485000,15000,495000,3000,7000,200,150,0.9700,0.9940,0.0141,0.9818,,,1.4,1.41",
        "SNP,ALL,3000000,2960000,40000,3020000,9000,22000,600,400,0.9867,0.9970,0.0073,0.9918,2.05,2.06,1.5,1.52",
        (
            f"SNP,PASS,3000000,2955000,45000,3010000,8000,20000,500,300,"
            f"{snp_recall},{snp_precision},0.0066,{snp_f1},2.05,2.06,1.5,1.52"
        ),
    ]
    return "\n".join(rows) + "\n"


def _min_fastp(sample: str, pub: Path) -> None:
    """A minimal fastp.json so ``ingest_results_dir`` DISCOVERS the sample (discovery is by the
    union of ``*.fastp.json`` and MultiQC). The ``summary.csv`` alone would not surface a sample."""
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


def _results_with_happy(tmp_path: Path, sample: str, *, snp_f1: float) -> Path:
    """A published ``results/`` dir with a discoverable sample + its hap.py ``summary.csv``."""
    pub = tmp_path / "results"
    pub.mkdir(parents=True, exist_ok=True)
    _min_fastp(sample, pub)
    (pub / f"{sample}.happy.summary.csv").write_text(_happy_summary(snp_f1=snp_f1))
    return pub


def _artifacts(sample: str, sm_list) -> RunArtifacts:  # type: ignore[no-untyped-def]
    return RunArtifacts(
        run_id="WS04-CONCORDANCE",
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


# ================================================= ingest: real summary.csv -> SampleMetrics


def test_happy_summary_parses_snp_pass_f1(tmp_path: Path) -> None:
    """The real parse path: a hap.py ``summary.csv`` -> ``concordance.snp_f1`` read from the
    SNP/PASS row (NOT the INDEL rows, whose distinct 0.9818 F1 would fool a naive parser)."""
    pub = _results_with_happy(tmp_path, "HG002", snp_f1=0.9723)
    ing = ingest_results_dir(pub)

    sm = next(s for s in ing.samples if s.sample_id == "HG002")
    assert "concordance.snp_f1" in sm.raw  # extracted, not invented
    obs = sm.raw["concordance.snp_f1"]
    assert obs.raw_unit == "fraction"
    assert obs.raw_value == pytest.approx(0.9723)  # the SNP/PASS value, not INDEL's 0.9818

    by_key = {mv.metric_key: mv.normalized_value for mv in metric_values_for(sm)}
    assert by_key["concordance.snp_f1"] == pytest.approx(0.9723)


def test_absent_happy_is_not_a_hole(tmp_path: Path) -> None:
    """hap.py is NOT in the germline default profile (it needs GIAB truth inputs), so an absent
    ``summary.csv`` is OPTIONAL — it must NOT be reported as an ``absent_source`` hole."""
    pub = tmp_path / "results"
    pub.mkdir()
    _min_fastp("HG002", pub)  # fastp present, no summary.csv

    ing = ingest_results_dir(pub)
    sm = next(s for s in ing.samples if s.sample_id == "HG002")
    assert "concordance.snp_f1" not in sm.raw
    absent = {(u.sample_id, u.leaf_key) for u in ing.unmapped}
    assert ("HG002", "concordance.snp_f1") not in absent  # optional tool, not a hole


# ========================================================= gate: SNP-F1 floor fires / clears


def test_low_snp_f1_holds_on_concordance(tmp_path: Path) -> None:
    """SNP-F1 below the illustrative floor (0.99) -> a ``QC-SNP_F1`` WARN finding suggesting HOLD,
    scored by the GENERIC metric loop against a one-sided FLOOR (higher-is-better)."""
    pub = _results_with_happy(tmp_path, "HG002", snp_f1=0.9723)  # < 0.99 floor, >= 0.95 hard-fail
    ing = ingest_results_dir(pub)
    card = _card_for("HG002", ing.samples)

    hits = [f for f in card.findings if f.rule_id == "QC-SNP_F1"]
    assert len(hits) == 1
    f = hits[0]
    assert f.severity is Severity.WARN
    assert f.suggested_verdict is Verdict.HOLD
    assert any(e.source_field == "snp_f1" for e in f.evidence)
    assert card.verdict in {Verdict.HOLD, Verdict.RERUN, Verdict.ESCALATE}


def test_critical_snp_f1_rerun(tmp_path: Path) -> None:
    """SNP-F1 below the hard-fail (0.95) -> CRITICAL, suggesting RERUN (concordance far off)."""
    pub = _results_with_happy(tmp_path, "HG002", snp_f1=0.90)
    ing = ingest_results_dir(pub)
    card = _card_for("HG002", ing.samples)

    f = next(f for f in card.findings if f.rule_id == "QC-SNP_F1")
    assert f.severity is Severity.CRITICAL
    assert f.suggested_verdict is Verdict.RERUN


def test_high_snp_f1_not_flagged(tmp_path: Path) -> None:
    """A high SNP-F1 (>= 0.99 floor) is NOT flagged on concordance — the metric clears even though
    the run may still HOLD for an unrelated reason (structural cluster_pf-missing)."""
    pub = _results_with_happy(tmp_path, "HG002", snp_f1=0.998)
    ing = ingest_results_dir(pub)
    card = _card_for("HG002", ing.samples)

    assert not any(f.rule_id == "QC-SNP_F1" for f in card.findings)
    # Sanity: the concordance metric WAS observed (so "not flagged" means "passed", not "absent").
    by_key = {mv.metric_key: mv.normalized_value for mv in metric_values_for(ing.samples[0])}
    assert by_key["concordance.snp_f1"] == pytest.approx(0.998)
