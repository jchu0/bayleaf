"""Metric registry — the canonical metric vocabulary (docs/data/metric_registry.md).

The stable layer above drifting MultiQC/tool keys: `MetricRegistry` loads the versioned
`metric_registry.yaml`, and `MetricValue` (in `pipeguard.models`) records observations
normalized against it. ADDITIVE — not yet on the parser/rules critical path.
"""

from __future__ import annotations

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
]
