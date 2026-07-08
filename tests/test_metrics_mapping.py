"""Tests for the QCMetrics -> MetricValue mapping (T-025 step 1, additive).

The mapping resolves each flat QCMetrics field to its registry our_key and normalizes it to
the canonical unit. These pin the field->our_key->unit table and the normalization on real
data; nothing here touches a verdict (the mapping is not yet on the critical path).
"""

from __future__ import annotations

import math
from pathlib import Path

from pipeguard import load_run
from pipeguard.metrics import metric_values_for
from pipeguard.models import CanonicalUnit, MetricValue, QCMetrics

DATA = Path(__file__).resolve().parent.parent / "data" / "mock_run_01"


def _by_key(values: list[MetricValue]) -> dict[str, MetricValue]:
    return {v.metric_key: v for v in values}


def test_maps_qcmetrics_to_normalized_metric_values() -> None:
    qc = QCMetrics(
        sample_id="S5",
        q30=84.1,
        pct_reads_identified=78.2,
        mean_coverage=29.2,
        dup_rate=22.6,
        cluster_pf=83.4,
    )
    values = metric_values_for(qc, analysis_run_id="arun_test")
    by = _by_key(values)
    # All five QCMetrics fields now resolve to a registry our_key.
    assert set(by) == {
        "qc.q30",
        "qc.reads_passing_filter",
        "qc.mean_target_coverage",
        "qc.duplication",
        "qc.cluster_pf",
    }
    # Percent rates normalize to fractions; coverage stays x.
    assert math.isclose(by["qc.q30"].normalized_value, 0.841)
    assert by["qc.q30"].canonical_unit is CanonicalUnit.FRACTION
    assert by["qc.q30"].raw_value == 84.1 and by["qc.q30"].raw_unit == "percent"
    assert math.isclose(by["qc.duplication"].normalized_value, 0.226)
    assert math.isclose(by["qc.cluster_pf"].normalized_value, 0.834)
    assert math.isclose(by["qc.mean_target_coverage"].normalized_value, 29.2)
    assert by["qc.mean_target_coverage"].canonical_unit is CanonicalUnit.X
    # Provenance: each carries the sample, the source field, and the pinned registry version.
    for v in values:
        assert v.sample_id == "S5"
        assert v.analysis_run_id == "arun_test"
        assert v.metric_registry_version == 1
    assert by["qc.q30"].source_field == "q30"


def test_missing_field_is_skipped_not_defaulted() -> None:
    qc = QCMetrics(sample_id="S1", q30=None, mean_coverage=40.0)
    keys = {v.metric_key for v in metric_values_for(qc)}
    assert "qc.q30" not in keys  # None -> skipped, not coerced to 0
    assert "qc.mean_target_coverage" in keys


def test_cluster_pf_maps_to_its_registry_key() -> None:
    values = metric_values_for(QCMetrics(sample_id="S1", cluster_pf=89.0))
    assert [v.metric_key for v in values] == ["qc.cluster_pf"]
    assert math.isclose(values[0].normalized_value, 0.89)  # 89% -> fraction


def test_runbook_thresholds_key_on_registered_metrics() -> None:
    """Every DEFAULT_RUNBOOK threshold's our_key is in the registry's controlled vocabulary.

    This is the runbook<->registry linkage guard: a threshold that gates on an unregistered
    metric (a typo, or a metric we forgot to register) fails loudly here.
    """
    from pipeguard.metrics import default_registry
    from pipeguard.runbook import DEFAULT_RUNBOOK

    reg = default_registry()
    for t in DEFAULT_RUNBOOK.qc_thresholds:
        reg.entry(t.our_key)  # raises UnknownMetricError if not registered


def test_maps_real_mock_run_01_s5() -> None:
    arts = load_run(DATA)
    s5 = next(q for q in arts.qc if q.sample_id == "S5")
    by = _by_key(metric_values_for(s5))
    assert math.isclose(by["qc.q30"].normalized_value, 0.841)  # 84.1% -> fraction
    assert math.isclose(by["qc.mean_target_coverage"].normalized_value, 29.2)
    # Round-trips through JSON with its normalization baked in (ledger self-containment).
    dumped = by["qc.q30"].model_dump(mode="json")
    assert dumped["normalized_value"] == by["qc.q30"].normalized_value
    assert dumped["metric_key"] == "qc.q30"
