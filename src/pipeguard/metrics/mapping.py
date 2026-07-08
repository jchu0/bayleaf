"""Map the parsed flat ``QCMetrics`` onto normalized ``MetricValue`` records (T-025, step 1).

The additive bridge from the current parse output (`QCMetrics`, a flat model on a per-tool
scale) to the registry's canonical vocabulary: each field is resolved to its `our_key` and
normalized to the canonical unit, producing self-contained `MetricValue` records
(ADR-0007 — the normalized value + version are snapshotted onto the record).

**Additive only (step 1):** nothing calls this on the critical path yet. The rules still
read `QCMetrics`; this only *builds* the registry-backed representation so the mapping +
normalization can be reviewed on real data before it is wired in (steps 2-3).
"""

from __future__ import annotations

from ..models import MetricValue, QCMetrics
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
)


def metric_values_for(
    qc: QCMetrics,
    *,
    analysis_run_id: str | None = None,
    source_artifact_id: str | None = None,
    registry: MetricRegistry | None = None,
) -> list[MetricValue]:
    """Build normalized ``MetricValue`` records from one sample's ``QCMetrics``.

    A missing (``None``) field is skipped, not defaulted — a missing metric is a signal,
    not a crash (CLAUDE.md data-handling). Unmapped fields (e.g. ``cluster_pf``) are omitted
    until the registry gains an entry for them. Order follows ``_QCMETRICS_MAP`` so the
    output is stable.
    """
    reg = registry or default_registry()
    values: list[MetricValue] = []
    for attr, our_key, raw_unit in _QCMETRICS_MAP:
        raw = getattr(qc, attr)
        if raw is None:
            continue
        values.append(
            reg.observe(
                metric_key=our_key,
                raw_value=raw,
                raw_unit=raw_unit,
                sample_id=qc.sample_id,
                analysis_run_id=analysis_run_id,
                source_artifact_id=source_artifact_id,
                source_field=attr,
            )
        )
    return values
