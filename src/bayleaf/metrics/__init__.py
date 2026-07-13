"""Metric registry — the canonical metric vocabulary (docs/data/metric_registry.md).

The stable layer above drifting MultiQC/tool keys: `MetricRegistry` loads the versioned
`metric_registry.yaml`, and `MetricValue` (in `bayleaf.models`) records observations
normalized against it. ON the QC-gate critical path (T-025): the rules normalize each
metric through the registry and gate on the canonical value.
"""

from __future__ import annotations

from .mapping import metric_values_for, producible_metric_keys, sample_metrics_from_qcmetrics
from .registry import (
    MetricDirection,
    MetricEntry,
    MetricRegistry,
    MetricSource,
    UnknownMetricError,
    ValueType,
    default_registry,
)

__all__ = [
    "MetricDirection",
    "MetricEntry",
    "MetricRegistry",
    "MetricSource",
    "UnknownMetricError",
    "ValueType",
    "default_registry",
    "metric_values_for",
    "producible_metric_keys",
    "sample_metrics_from_qcmetrics",
]
