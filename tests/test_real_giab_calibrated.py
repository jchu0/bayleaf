"""WS-02 / WS-04 — the LIVE pass, frozen: the CALIBRATED genome-wide FREEMIX + real hap.py SNP-F1
flow through the ingest→gate spine on GENUINE tool output (not a synthetic-format fixture).

The WS-02/WS-04 offline tests prove the WIRING with hand-built real-FORMAT fixtures and explicitly
defer "a real tool run" to a live pass. That live pass ran (2026-07-13, `data/real-giab/
T7_RUN_STATUS.md`): VerifyBamID2 2.0.3 on the genome-wide HG002 2x250 BAM produced a
**calibrated** FREEMIX — it PASSED the marker sanity check NATIVELY (no `--DisableSanityCheck`),
unlike the chr20-capped heuristic — and the real germline pipeline (chr20/21/22, 300,175 variants)
produced a hap.py `summary.csv` scored against the GIAB v4.2.1 truth.

The tiny tool outputs are committed VERBATIM under `tests/fixtures/giab_real/` (origin: `real-giab`,
genome-wide calibrated / chr20-21-22 Track-A concordance — NOT the 122 GB BAM, which stays on the
external SSD). This test reads those real bytes through the SAME public `ingest_results_dir` →
`run_gate` path the demo uses, so the calibrated numbers are a permanent, CI-runnable proof — the
last mile that turns WS-02/WS-04 from "parser-wired, fixture-tested" into "proven on real
calibrated tool output". The thresholds stay illustrative/configurable, never clinical (guardrail).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from bayleaf import run_gate
from bayleaf.ingest.nfcore import ingest_results_dir
from bayleaf.models import RunArtifacts, Sample, SampleSheetEntry, Severity, Verdict
from bayleaf.synthesis import StubSynthesizer

_FIX = Path(__file__).parent / "fixtures" / "giab_real"

# The exact calibrated values in the committed tool outputs (verified against T7_RUN_STATUS.md).
_FREEMIX = 0.000220096  # HG002.wgs.genomewide.selfSM, FREEMIX col (sanity-check passed natively)
_SNP_F1 = 0.989276  # HG002.subset.happy.summary.csv, SNP/PASS METRIC.F1_Score


def _real_results(tmp_path: Path) -> Path:
    """A published ``results/`` dir carrying HG002's REAL calibrated tool outputs (copied verbatim
    from the committed fixtures) plus a minimal fastp.json so ``ingest_results_dir`` discovers the
    sample. Files keep an ``HG002`` prefix so the adapter's per-sample glob associates them."""
    pub = tmp_path / "results"
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "HG002.fastp.json").write_text(
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
    shutil.copy(_FIX / "HG002.wgs.genomewide.selfSM", pub / "HG002.wgs.genomewide.selfSM")
    shutil.copy(_FIX / "HG002.subset.happy.summary.csv", pub / "HG002.subset.happy.summary.csv")
    return pub


def _sample_metrics(tmp_path: Path):  # type: ignore[no-untyped-def]
    ing = ingest_results_dir(_real_results(tmp_path))
    return next(s for s in ing.samples if s.sample_id == "HG002")


def test_real_genomewide_freemix_is_calibrated(tmp_path: Path) -> None:
    """The genuine genome-wide ``.selfSM`` parses into ``contamination.freemix`` at the CALIBRATED
    value on its true (fraction) scale — the parser reads real VerifyBamID2 bytes, not a fixture."""
    sm = _sample_metrics(tmp_path)
    assert "contamination.freemix" in sm.raw  # extracted from the real file, never invented
    obs = sm.raw["contamination.freemix"]
    assert obs.raw_unit == "fraction"
    assert obs.raw_value == pytest.approx(_FREEMIX)


def test_real_happy_snp_f1_parses(tmp_path: Path) -> None:
    """The genuine hap.py ``summary.csv`` parses into ``concordance.snp_f1`` at the real SNP/PASS
    F1 — selected by (Type=SNP, Filter=PASS), never by row position (INDELs can't be misread)."""
    sm = _sample_metrics(tmp_path)
    assert "concordance.snp_f1" in sm.raw
    obs = sm.raw["concordance.snp_f1"]
    assert obs.raw_unit == "fraction"
    assert obs.raw_value == pytest.approx(_SNP_F1)


def test_real_calibrated_metrics_gate_end_to_end(tmp_path: Path) -> None:
    """The real metrics run through the deterministic gate: a clean 0.02% FREEMIX clears the
    contamination gate (no ``QC-FREEMIX`` finding), while SNP-F1 0.9893 sits just under the
    illustrative 0.99 concordance gate (above the 0.95 hard-fail) → an honest borderline WARN.
    Both are scored by the GENERIC metric loop — no bespoke rule for either."""
    sm = _sample_metrics(tmp_path)
    art = RunArtifacts(
        run_id="REAL-GIAB-CAL",
        sample_sheet=[SampleSheetEntry(sample_id="HG002")],
        samples=[
            Sample(
                sample_id="HG002",
                subject_id="HG002",
                tissue="blood",
                library_prep="wgs",
                submitted_by="tester",
            )
        ],
        qc=[sm],
    )
    card = {c.sample_id: c for c in run_gate(art, synthesizer=StubSynthesizer())}["HG002"]

    # Contamination is CLEAN — a calibrated 0.02% is far below the 2% gate, so no QC-FREEMIX fires.
    assert not [f for f in card.findings if f.rule_id == "QC-FREEMIX"]

    # Concordance 0.9893 < the illustrative 0.99 gate but > the 0.95 hard-fail → a borderline WARN
    # suggesting HOLD (real, honest QC signal on genuine data).
    snp = [f for f in card.findings if f.rule_id == "QC-SNP_F1"]
    assert len(snp) == 1
    assert snp[0].severity is Severity.WARN
    assert snp[0].suggested_verdict is Verdict.HOLD
