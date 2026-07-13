"""WS-03 — nf-core/MultiQC ``results/`` ingestion adapter (offline, fixture-driven).

These tests exercise the REAL parse path (``pipeguard.ingest.nfcore``), never a mock: a
hand-built ``results/`` publish tree (a ``fastp.json`` + mosdepth summary/thresholds +
``multiqc_data/multiqc_data.json``, shaped like what ``pipelines/germline/main.nf`` publishes)
is parsed into the registry-keyed ``SampleMetrics`` contract (WS-06·PR1) and lowered to canonical
``MetricValue``s via ``metrics.metric_values_for`` — the same normalization the gate consumes.

Anti-scaffold posture (the "confident surface vs thin wiring" trap this workstream closes):
  * an equivalence test pins the adapter's canonical values against the INDEPENDENTLY-derived
    driver path (``scripts.run_giab_pipeline`` → ``qc_metrics.csv`` → ``parse_qc_metrics``), so a
    hand-returned constant can't pass — it would have to reproduce every normalized value AND stay
    coupled to the driver's extraction, i.e. actually parse the files;
  * a renamed MultiQC key must still resolve (``registry.resolve_alias`` gets its first real,
    non-test call site) — a scaffold that key-matches canonical names drops the drifted column;
  * an unknown key is surfaced as ``unmapped``, never invented or silently dropped;
  * a missing file yields honest-empty (field ABSENT, not ``0.0``), never a crash.

The LIVE ingress (a real ``nextflow run`` producing ``results/``) is env-gated and NOT exercised
here — it needs the ``hackathon`` conda env + JRE + bioconda; this file pins the adapter at the
fixture-``results/`` contract and the live leg is flagged for the maintainer's Nextflow pass.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from pipeguard.ingest.nfcore import ingest_results_dir
from pipeguard.metrics import metric_values_for
from pipeguard.settings import run_store_root

# --------------------------------------------------------------- fixture publish-dir builders
# Shaped to match scripts/run_giab_pipeline.py's parse_fastp / parse_mosdepth expectations, so the
# same publish dir feeds BOTH the driver and the adapter (the equivalence proof below).


def _fastp_json(*, q30_rate: float, total_reads: int, passed: int, dup_rate: float) -> str:
    """A minimal fastp report carrying exactly the fields the fastp extractor reads."""
    return json.dumps(
        {
            "summary": {
                "before_filtering": {"total_reads": total_reads},
                "after_filtering": {"q30_rate": q30_rate},
            },
            "filtering_result": {"passed_filter_reads": passed},
            "duplication": {"rate": dup_rate},
        }
    )


def _mosdepth_summary(mean: float) -> str:
    # cols: chrom length bases mean min max — the extractor reads split('\t')[3] on total_region.
    return f"chrom\tlength\tbases\tmean\tmin\tmax\ntotal_region\t2000\t100000\t{mean}\t10\t80\n"


def _thresholds_bed(*, span: int, ge20: int, ge30: int) -> str:
    # cols: #chrom start end region 1X 10X 20X 30X — uses (end-start), c[6] (20x), c[7] (30x).
    return (
        "#chrom\tstart\tend\tregion\t1X\t10X\t20X\t30X\n"
        f"chr20\t0\t{span}\treg\t{span}\t{span}\t{ge20}\t{ge30}\n"
    )


def _norm_vcf(n_variants: int) -> str:
    lines = ["##fileformat=VCFv4.2", "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"]
    lines += [f"chr20\t{100 + i}\t.\tA\tG\t50\tPASS\t." for i in range(n_variants)]
    return "\n".join(lines) + "\n"


def _write_structured_sample(
    pub: Path,
    sample: str,
    *,
    mean: float = 50.0,
    total_reads: int = 1_000_000,
    q30_rate: float = 0.90,
    passed: int = 990_000,
    dup_rate: float = 0.05,
    span: int = 2000,
    ge20: int = 1800,
    ge30: int = 1600,
    n_variants: int = 3,
    skip: tuple[str, ...] = (),
) -> None:
    """Write one sample's ``${id}.*`` structured tool outputs shaped like the germline publish dir.

    ``skip`` omits kinds (``fastp`` / ``mosdepth_summary`` / ``thresholds`` / ``norm``) for the
    deliberately-partial cases. The ``norm.vcf.gz`` is written by default so a REAL-shaped publish
    dir is reproduced (the driver's ``parse_publish_dir`` requires it); the adapter ignores it.
    """
    pub.mkdir(parents=True, exist_ok=True)
    if "fastp" not in skip:
        (pub / f"{sample}.fastp.json").write_text(
            _fastp_json(
                q30_rate=q30_rate, total_reads=total_reads, passed=passed, dup_rate=dup_rate
            )
        )
    if "mosdepth_summary" not in skip:
        (pub / f"{sample}.panel.mosdepth.summary.txt").write_text(_mosdepth_summary(mean))
    if "thresholds" not in skip:
        with gzip.open(pub / f"{sample}.panel.thresholds.bed.gz", "wt", encoding="utf-8") as fh:
            fh.write(_thresholds_bed(span=span, ge20=ge20, ge30=ge30))
    if "norm" not in skip:
        with gzip.open(pub / f"{sample}.norm.vcf.gz", "wt", encoding="utf-8") as fh:
            fh.write(_norm_vcf(n_variants))


def _write_multiqc(
    pub: Path,
    *,
    per_sample: dict[str, dict[str, float]],
    headers: dict[str, dict[str, str]] | None = None,
) -> None:
    """Write a ``multiqc_data/multiqc_data.json`` general-stats block.

    ``per_sample`` maps sample_id -> {column_key: value}; ``headers`` maps column_key -> a MultiQC
    header dict (its ``suffix`` declares the SCALE, e.g. ``{"suffix": "%"}`` for a percent column —
    the adapter reads the unit from this DECLARATION, never guesses it from the key name). MultiQC's
    real ``multiqc_data.json`` carries ``report_general_stats_data`` (list, one dict per module) and
    a parallel ``report_general_stats_headers``.
    """
    mqc_dir = pub / "multiqc_data"
    mqc_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "report_general_stats_data": [per_sample],
        "report_general_stats_headers": [headers or {}],
    }
    (mqc_dir / "multiqc_data.json").write_text(json.dumps(doc))


def _by_key(sm) -> dict[str, float]:  # type: ignore[no-untyped-def]
    """{our_key -> normalized_value} for one SampleMetrics — the gate-ready canonical view."""
    return {mv.metric_key: mv.normalized_value for mv in metric_values_for(sm)}


# =============================================================== Gap A — results/ -> SampleMetrics


def test_adapter_parses_results_dir_into_sample_metrics(tmp_path: Path) -> None:
    """The real parse path: structured tool files -> SampleMetrics -> canonical MetricValues."""
    pub = tmp_path / "results"
    _write_structured_sample(pub, "HG002")

    result = ingest_results_dir(pub)
    assert [s.sample_id for s in result.samples] == ["HG002"]
    sm = result.samples[0]

    vals = _by_key(sm)
    assert vals["qc.q30"] == pytest.approx(0.90)  # fastp q30_rate fraction, identity-normalized
    assert vals["qc.mean_target_coverage"] == pytest.approx(50.0)  # mosdepth total_region mean (x)
    assert vals["qc.duplication"] == pytest.approx(0.05)  # fastp duplication.rate (fraction)
    assert vals["qc.breadth_20x"] == pytest.approx(1800 / 2000)  # mosdepth thresholds ratio
    assert vals["qc.breadth_30x"] == pytest.approx(1600 / 2000)
    assert vals["qc.reads_passing_filter"] == pytest.approx(990_000 / 1_000_000)


def test_adapter_qcmetrics_equal_bespoke_driver_path(tmp_path: Path) -> None:
    """Equivalence: over the SAME publish dir, the adapter's canonical values equal the driver's
    independent extraction (scripts.run_giab_pipeline -> qc_metrics.csv -> parse_qc_metrics).

    This is the anti-scaffold spine: a stub can't fake it without reproducing every normalized
    value AND staying coupled to the driver's parse — i.e. actually reading the files.
    """
    from scripts.run_giab_pipeline import RunConfig, parse_publish_dir, write_run_dir_multi

    from pipeguard.parsers import parse_qc_metrics

    pub = tmp_path / "results"
    _write_structured_sample(pub, "HG002", mean=54.2, q30_rate=0.882, dup_rate=0.0057)

    # Driver path — the independently-derived reference (percent-scaled CSV -> declared unit)
    run_dir = tmp_path / "data" / "RUN-EQ"
    cfg = RunConfig(
        run_id="RUN-EQ",
        run_dir=run_dir,
        platform="NovaSeq",
        run_date="2026-07-12",
        submitted_by="tester",
    )
    write_run_dir_multi(cfg, parse_publish_dir(pub))
    driver_qc = parse_qc_metrics(run_dir / "qc_metrics.csv")[0]
    driver_vals = {mv.metric_key: mv.normalized_value for mv in metric_values_for(driver_qc)}

    # Adapter path over the same publish dir
    adapter_sm = ingest_results_dir(pub).samples[0]
    adapter_vals = _by_key(adapter_sm)

    shared = set(driver_vals) & set(adapter_vals)
    assert shared >= {
        "qc.q30",
        "qc.mean_target_coverage",
        "qc.duplication",
        "qc.breadth_20x",
        "qc.breadth_30x",
        "qc.reads_passing_filter",
    }
    for key in shared:
        assert adapter_vals[key] == pytest.approx(driver_vals[key]), key


def test_adapter_emits_native_source_units_not_prescaled(tmp_path: Path) -> None:
    """fastp duplication.rate is a FRACTION at source; the adapter must DECLARE raw_unit='fraction'
    so normalize yields 0.0057 — not the driver's x100-then-/100 round-trip, and not 0.000057."""
    pub = tmp_path / "results"
    _write_structured_sample(pub, "HG002", dup_rate=0.0057)

    sm = ingest_results_dir(pub).samples[0]
    dup = sm.raw["qc.duplication"]
    assert dup.raw_unit == "fraction"  # DECLARED at the true source scale, never guessed
    assert dup.raw_value == pytest.approx(0.0057)
    assert _by_key(sm)["qc.duplication"] == pytest.approx(0.0057)


# =============================================================== Gap B — live alias resolution


def test_renamed_multiqc_key_still_resolves_on_the_live_path(tmp_path: Path) -> None:
    """A drifted MultiQC general-stats header (percent_q30 / 20_x_pc / pct_duplication) must still
    fold to qc.q30 / qc.breadth_20x / qc.duplication via registry.resolve_alias — the FIRST real
    (non-test) call site of the anti-drift alias index."""
    pub = tmp_path / "results"
    _write_multiqc(
        pub,
        per_sample={
            "NA12878": {"percent_q30": 90.0, "20_x_pc": 99.2, "pct_duplication": 5.0},
        },
        headers={
            "percent_q30": {"suffix": "%"},
            "20_x_pc": {"suffix": "%"},
            "pct_duplication": {"suffix": "%"},
        },
    )

    result = ingest_results_dir(pub)
    assert [s.sample_id for s in result.samples] == ["NA12878"]
    vals = _by_key(result.samples[0])
    assert vals["qc.q30"] == pytest.approx(0.90)  # 90.0 percent -> 0.90 fraction
    assert vals["qc.breadth_20x"] == pytest.approx(0.992)  # 99.2 percent -> 0.992
    assert vals["qc.duplication"] == pytest.approx(0.05)


def test_resolve_alias_has_a_real_call_site_under_ingest() -> None:
    """Standing guard (Gap B): resolve_alias must be invoked on the live ingest path, not just
    referenced in a docstring — freezes the 'aliases[] is dead weight' regression."""
    src = Path(__file__).resolve().parents[1] / "src" / "pipeguard" / "ingest" / "nfcore.py"
    text = src.read_text(encoding="utf-8")
    assert ".resolve_alias(" in text


# =============================================================== Anti-scaffold guards


def test_unknown_multiqc_key_is_unmapped_not_dropped(tmp_path: Path) -> None:
    """An unregistered column is reported in ``unmapped`` and NEVER invented as a metric."""
    pub = tmp_path / "results"
    _write_structured_sample(pub, "HG002")
    _write_multiqc(
        pub,
        per_sample={"HG002": {"totally_unknown_metric": 1.23}},
        headers={"totally_unknown_metric": {}},
    )

    result = ingest_results_dir(pub)
    sm = next(s for s in result.samples if s.sample_id == "HG002")
    assert "totally_unknown_metric" not in sm.raw  # never fabricated as an our_key
    assert not any(k.startswith("unknown") for k in sm.raw)
    unmapped_keys = {u.leaf_key for u in result.unmapped}
    assert "totally_unknown_metric" in unmapped_keys  # surfaced honestly, not silently dropped


def test_missing_mosdepth_file_yields_honest_empty_not_crash(tmp_path: Path) -> None:
    """A partial publish dir (fastp present, mosdepth absent): coverage/breadth are ABSENT from
    the SampleMetrics (never a fabricated 0.0), and the absence is reported. No crash."""
    pub = tmp_path / "results"
    _write_structured_sample(pub, "HG002", skip=("mosdepth_summary", "thresholds"))

    result = ingest_results_dir(pub)  # must not raise
    sm = next(s for s in result.samples if s.sample_id == "HG002")
    # fastp-derived keys present…
    assert "qc.q30" in sm.raw
    # …mosdepth-derived keys ABSENT (not defaulted to 0.0)
    assert "qc.mean_target_coverage" not in sm.raw
    assert "qc.breadth_20x" not in sm.raw
    assert "qc.breadth_30x" not in sm.raw
    # the absence is a reported signal, not a silent hole
    absent = {(u.sample_id, u.leaf_key) for u in result.unmapped}
    assert ("HG002", "qc.mean_target_coverage") in absent


def test_empty_results_dir_is_honest_empty_not_crash(tmp_path: Path) -> None:
    """No tool outputs at all: an empty result, not a crash (the adapter parses tolerantly at the
    boundary — unlike the driver's fail-loud discover_samples, an adapter never explodes)."""
    pub = tmp_path / "results"
    pub.mkdir()
    result = ingest_results_dir(pub)
    assert result.samples == []


def test_nonexistent_results_dir_is_honest_empty_not_crash(tmp_path: Path) -> None:
    result = ingest_results_dir(tmp_path / "does_not_exist")
    assert result.samples == []


# ========================================================= Gap D — configurable run-store root


def test_run_store_root_defaults_to_repo_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIPEGUARD_DATA_ROOT", raising=False)
    root = run_store_root()
    assert root.name == "data"
    assert root.is_absolute()


def test_run_store_root_honors_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PIPEGUARD_DATA_ROOT", str(tmp_path))
    assert run_store_root() == tmp_path


def test_run_store_root_is_resolved_at_call_time_not_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Resolution is per-call: a mid-process setenv must be visible on the very next call (so a
    test/deploy can repoint discovery), never captured once at import."""
    monkeypatch.delenv("PIPEGUARD_DATA_ROOT", raising=False)
    first = run_store_root()
    assert first.name == "data"
    monkeypatch.setenv("PIPEGUARD_DATA_ROOT", str(tmp_path))
    assert run_store_root() == tmp_path
