"""Map the parsed flat ``QCMetrics`` onto normalized ``MetricValue`` records (T-025).

The bridge from the current parse output (`QCMetrics`, a flat model on a per-tool scale) to
the registry's canonical vocabulary: each field is resolved to its `our_key` and normalized
to the canonical unit, producing self-contained `MetricValue` records (ADR-0007 — the
normalized value + version are snapshotted onto the record).

ON the critical path: `rules.evaluate_sample` calls this per sample and gates each threshold
on the resulting `MetricValue.normalized_value` (canonical), so a change in a source's raw
unit can't silently move a verdict. The field->our_key->raw_unit table below is the one place
the source scale is declared.
"""

from __future__ import annotations

from ..models import MetricValue, QCMetrics, RawObservation, SampleMetrics
from .registry import MetricRegistry, default_registry

# QCMetrics attribute -> (registry our_key, the raw_unit the parsed value is on). Explicit,
# not alias-resolved: the flat `QCMetrics` field names are not registry aliases, and the
# scale each field is on (percent for rates, x for coverage — see data/mock_run_01 and the
# runbook `unit`) must be *declared*, never guessed (the pct_* trap the registry defends).
_QCMETRICS_MAP: tuple[tuple[str, str, str], ...] = (
    ("q30", "qc.q30", "percent"),
    ("pct_reads_identified", "qc.reads_passing_filter", "percent"),
    ("mean_coverage", "qc.mean_target_coverage", "x"),
    ("dup_rate", "qc.duplication", "percent"),
    ("cluster_pf", "qc.cluster_pf", "percent"),
    # Additional registered metrics (present only in a richer QC report). Each raw_unit below is the
    # scale the parsed value is on — declared, never guessed (the pct_* trap). They populate the
    # preflight / variant gate groups when a run emits them; absent → skipped (see the None guard).
    ("phix_aligned", "preflight.phix_aligned", "percent"),
    ("breadth_20x", "qc.breadth_20x", "fraction"),
    ("breadth_30x", "qc.breadth_30x", "fraction"),
    ("pct_mapped", "qc.pct_mapped", "fraction"),
    ("on_target", "qc.on_target", "fraction"),
    ("variant_dp", "variant.dp", "x"),
    ("variant_gq", "variant.gq", "phred"),
    ("variant_titv", "variant.titv", "ratio"),
)


def producible_metric_keys() -> frozenset[str]:
    """The registry ``our_key``s the current parse layer can actually produce a value for (the keys
    in ``_QCMETRICS_MAP``). A runbook may only EXPECT a metric the system can examine, so
    ``runbook.expected_metrics`` is validated against this set (WS-01) — a typo or a
    registered-but-unwired key can't silently become a permanent, unclearable, misdiagnosed HOLD."""
    return frozenset(our_key for _, our_key, _ in _QCMETRICS_MAP)


def sample_metrics_from_qcmetrics(qc: QCMetrics) -> SampleMetrics:
    """Lower the flat frozen-CSV ``QCMetrics`` into the registry-keyed ``SampleMetrics`` contract
    (WS-06 transition bridge). Uses the SAME ``_QCMETRICS_MAP`` (field → our_key → raw_unit), so a
    ``QCMetrics`` produces byte-identical normalized values whether consumed directly or via
    ``SampleMetrics``. A ``None`` field is skipped (a missing metric is a signal); ``raw`` follows
    ``_QCMETRICS_MAP`` insertion order so downstream output stays stable."""
    raw: dict[str, RawObservation] = {}
    for attr, our_key, raw_unit in _QCMETRICS_MAP:
        value = getattr(qc, attr)
        if value is None:
            continue
        raw[our_key] = RawObservation(raw_value=value, raw_unit=raw_unit, source_field=attr)
    return SampleMetrics(sample_id=qc.sample_id, raw=raw)


def metric_values_for(
    source: QCMetrics | SampleMetrics,
    *,
    analysis_run_id: str | None = None,
    source_artifact_id: str | None = None,
    registry: MetricRegistry | None = None,
) -> list[MetricValue]:
    """Build normalized ``MetricValue`` records from one sample's ingested metrics.

    Accepts either the flat ``QCMetrics`` (lowered internally via ``sample_metrics_from_qcmetrics``,
    so every existing caller is unchanged and byte-identical) OR the registry-keyed
    ``SampleMetrics`` an adapter emits directly (WS-03). Then a GENERIC loop over the map
    calls ``reg.observe(...)`` — NO field enumeration, so registering a metric is a registry entry,
    not a new named model field. A missing metric is simply absent from the map (a signal, not a
    crash — CLAUDE.md data-handling).

    Note on ``cluster_pf`` (audit P3-1/P3-10): it IS in ``_QCMETRICS_MAP`` and registered, but a
    reads-only fastq→BAM path can't produce this run-level SAV/InterOp metric, so it typically
    arrives absent → its required=True runbook threshold NA-flags → a STRUCTURAL, EXPECTED HOLD on
    every reads-based run (the pinned demo relies on HG002 → HOLD). A deferred SAV-source policy,
    not a mapping gap; see ``runbook.py`` cluster_pf.
    """
    reg = registry or default_registry()
    sm = source if isinstance(source, SampleMetrics) else sample_metrics_from_qcmetrics(source)
    values: list[MetricValue] = []
    for our_key, obs in sm.raw.items():
        values.append(
            reg.observe(
                metric_key=our_key,
                raw_value=obs.raw_value,
                raw_unit=obs.raw_unit,
                sample_id=sm.sample_id,
                analysis_run_id=analysis_run_id,
                source_artifact_id=source_artifact_id,
                source_field=obs.source_field,
            )
        )
    return values
