"""Typed loader for the metric registry (docs/data/metric_registry.md).

The registry is the **canonical metric vocabulary** — the stable layer above drifting
MultiQC/tool keys. This module loads `metric_registry.yaml` into typed, frozen entries
and exposes the three operations parsers will eventually need:

  * `entry(our_key)`         — look up a registered metric (controlled vocabulary);
  * `resolve_alias(key)`     — map a prior/variant MultiQC key back to its `our_key`;
  * `normalize(...)`         — convert a raw value into the metric's `canonical_unit`.

WHY this exists as code (not just a doc): a `MultiQC` key rename must never silently
break a gate. `aliases[]` maps the drift back to a stable `our_key`, and `canonical_unit`
is the single source of truth for normalization — see the `pct_*` trap handled in
`normalize` below.

ON THE CRITICAL PATH (T-025): `rules.evaluate_sample` normalizes each metric through this
registry and gates on `MetricValue.normalized_value`; `denormalize` renders the canonical
threshold back into the display unit for the finding text.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import Enum
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ..identifiers import utc_now
from ..models import CanonicalUnit, Gate, MetricValue

# The registry ships inside the package so importlib.resources can read it from a wheel
# (mirrors bayleaf.triage's knowledge corpus). Kept as module constants so a
# non-default path (tests, overrides) is the only thing a caller varies.
_REGISTRY_PACKAGE = "bayleaf.metrics"
_REGISTRY_RESOURCE = "metric_registry.yaml"


class UnknownMetricError(KeyError):
    """Raised when a key is not a registered `our_key` and not a known alias.

    A subclass of `KeyError` because it means "not in the controlled vocabulary" — the
    registry rejects unknown metrics rather than inventing an entry (metric_registry.md
    rule 4: thresholds/records may only key on registered `our_key`s).
    """


class MetricDirection(str, Enum):
    """How a metric relates to "good" — informs thresholding, not normalization."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    TARGET_BAND = "target_band"


class ValueType(str, Enum):
    """The scalar type the raw value is expected to take."""

    FLOAT = "float"
    INT = "int"
    BOOL = "bool"


class MetricSource(BaseModel):
    """Where a metric is parsed from — the source contract for one `our_key`."""

    model_config = ConfigDict(frozen=True)

    module: str = Field(..., description="Tool/MultiQC module, e.g. picard_collecthsmetrics")
    source_file: str | None = Field(None, description="Artifact/file the value is parsed from")
    raw_field: str | None = Field(None, description="Exact field/column key in the source")
    json_path: str | None = Field(None, description="Dotted path when the source is JSON")


class MetricEntry(BaseModel):
    """One registered metric: what a number under this `our_key` means.

    Frozen because the registry is a versioned artifact — an entry only changes when
    `metric_registry_version` bumps, never in place.
    """

    model_config = ConfigDict(frozen=True)

    our_key: str = Field(..., description="Canonical vocabulary key, e.g. qc.breadth_20x")
    display_name: str
    gate: Gate
    # `category` is a free string, not an enum: the seed table's vocabulary (e.g.
    # `run_qc`) drifts from the doc's `Entry shape` enum, and category is descriptive
    # metadata — not load-bearing for normalization — so we tolerate it rather than
    # reject valid seed rows.
    category: str
    canonical_unit: CanonicalUnit
    value_type: ValueType
    direction: MetricDirection
    source: MetricSource
    raw_units_allowed: list[str] = Field(default_factory=list)
    parser: str | None = None
    parser_version: str | None = None
    aliases: list[str] = Field(default_factory=list)


# Unit conversions keyed on (raw_unit, canonical_unit). Identity conversions (raw ==
# canonical, e.g. `x` -> `x`) are handled before this table, so it only holds the real
# scale changes. This is intentionally a *closed* set: an unlisted pair raises rather
# than guessing, so a mis-declared unit surfaces as an error instead of a silent 100x.
# Conversions divide/multiply by exactly 100 (not `* 0.01`) so the normalized value —
# which is snapshotted into MetricValue.content_hash — is the clean decimal the spec
# states (`95.0` percent -> `0.95`, not `0.9500000000000001`).
_CONVERSIONS: dict[tuple[str, str], Callable[[float], float]] = {
    # The MultiQC pct trap: a value labeled `percent` (0-100) for a `fraction` metric
    # must be divided by 100; the reverse multiplies. Field *names* (`pct_*`) are not
    # trusted — only the caller-supplied raw_unit is.
    ("percent", "fraction"): lambda v: v / 100.0,
    ("fraction", "percent"): lambda v: v * 100.0,
}


class MetricRegistry(BaseModel):
    """The loaded, validated metric vocabulary plus an alias index.

    Construct via `MetricRegistry.load(...)` (validates the YAML and builds the alias
    index); direct construction is for callers that already hold validated entries.
    """

    model_config = ConfigDict(frozen=True)

    version: int
    # Typed as read-only `Mapping` (not `dict`) so mypy rejects
    # `default_registry().entries[k] = ...` — the registry is a process-shared, lru_cached
    # singleton and an in-place mutation would poison it for every caller.
    entries: Mapping[str, MetricEntry]
    # alias -> our_key. Built once at load; keeps `resolve_alias` O(1).
    alias_index: Mapping[str, str] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> MetricRegistry:
        """Load and validate the registry from YAML.

        `path=None` reads the packaged `metric_registry.yaml` via importlib.resources so
        it works in a non-editable (wheel) install. Raises `ValueError` on a structurally
        invalid file and `UnknownMetricError`-adjacent `ValueError` on an alias that
        collides with another entry — registry integrity is checked at load, once.
        """
        if path is None:
            text = files(_REGISTRY_PACKAGE).joinpath(_REGISTRY_RESOURCE).read_text(encoding="utf-8")
        else:
            text = path.read_text(encoding="utf-8")

        raw: Any = yaml.safe_load(text)
        if not isinstance(raw, dict):
            raise ValueError("metric registry must be a mapping at the top level")

        version = raw.get("metric_registry_version")
        if not isinstance(version, int):
            raise ValueError("metric registry is missing an integer `metric_registry_version`")

        metrics = raw.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError("metric registry `metrics` must be a mapping of our_key -> entry")

        entries: dict[str, MetricEntry] = {}
        alias_index: dict[str, str] = {}
        for our_key, body in metrics.items():
            if not isinstance(body, dict):
                raise ValueError(f"metric registry entry {our_key!r} must be a mapping")
            # Inject the mapping key as `our_key` so the entry is self-describing.
            entry = MetricEntry.model_validate({**body, "our_key": our_key})
            entries[our_key] = entry

        # Build the alias index in a second pass so alias/our_key collisions are caught
        # against the *full* set of registered keys, not just the ones seen so far.
        for our_key, entry in entries.items():
            for alias in entry.aliases:
                if alias in entries:
                    raise ValueError(
                        f"alias {alias!r} on {our_key!r} collides with a registered our_key"
                    )
                existing = alias_index.get(alias)
                if existing is not None and existing != our_key:
                    raise ValueError(f"alias {alias!r} maps to both {existing!r} and {our_key!r}")
                alias_index[alias] = our_key

        return cls(version=version, entries=entries, alias_index=alias_index)

    def keys(self) -> list[str]:
        """All registered `our_key`s, in registry (insertion) order."""
        return list(self.entries)

    def entry(self, our_key: str) -> MetricEntry:
        """Return the entry for `our_key`, or raise `UnknownMetricError`.

        Only accepts a canonical `our_key` — use `resolve_alias` first to fold a variant
        MultiQC key in. This is the controlled-vocabulary gate (metric_registry.md rule 4).
        """
        try:
            return self.entries[our_key]
        except KeyError:
            raise UnknownMetricError(our_key) from None

    def resolve_alias(self, key: str) -> str:
        """Map any known key (an `our_key` or an alias) to its canonical `our_key`.

        Raises `UnknownMetricError` for a key that is neither — the shield against
        MultiQC key drift only works if an unrecognized key is a loud failure, not a
        silently dropped metric.
        """
        if key in self.entries:
            return key
        our_key = self.alias_index.get(key)
        if our_key is None:
            raise UnknownMetricError(key)
        return our_key

    def normalize(self, our_key: str, raw_value: float, raw_unit: str) -> float:
        """Convert `raw_value` (in `raw_unit`) to the metric's `canonical_unit`.

        Normalization keys on the caller-supplied `raw_unit`, never on the field name —
        this is what defuses the MultiQC `pct_*` trap (metric_registry.md rule 3): the
        same logical metric arrives as a fraction from Picard and a percent from
        mosdepth/MultiQC, so only the declared unit tells us the scale.

        Rejects a `raw_unit` the entry does not allow, and an unsupported unit pair,
        rather than guessing — a mis-declared unit must surface as an error, not a
        silent 100x. `our_key` must already be canonical (`resolve_alias` first).
        """
        entry = self.entry(our_key)  # controlled-vocabulary check
        canonical = entry.canonical_unit.value

        # Guard the declared value_type: a bool metric must carry 0/1 and an int metric
        # an integral value, so a mis-sourced number (e.g. a bool key handed 7.0) fails
        # loud here instead of being stored as a nonsense normalized_value downstream.
        if entry.value_type is ValueType.BOOL and raw_value not in (0.0, 1.0):
            raise ValueError(
                f"{our_key!r} is a bool metric; raw_value must be 0 or 1, got {raw_value!r}"
            )
        if entry.value_type is ValueType.INT and raw_value != int(raw_value):
            raise ValueError(
                f"{our_key!r} is an int metric; raw_value must be integral, got {raw_value!r}"
            )

        if entry.raw_units_allowed and raw_unit not in entry.raw_units_allowed:
            raise ValueError(
                f"raw_unit {raw_unit!r} not allowed for {our_key!r} "
                f"(allowed: {entry.raw_units_allowed})"
            )

        if raw_unit == canonical:
            return raw_value  # identity — e.g. `x` stays `x`, a fraction stays a fraction

        convert = _CONVERSIONS.get((raw_unit, canonical))
        if convert is None:
            raise ValueError(
                f"no unit conversion from {raw_unit!r} to {canonical!r} for {our_key!r}"
            )
        return convert(raw_value)

    def denormalize(self, our_key: str, value: float, to_unit: str) -> float:
        """Convert a value in the metric's `canonical_unit` back to `to_unit`.

        The inverse of `normalize`, over the same closed conversion table — used to render a
        canonical threshold in a metric's raw/display unit (a fraction gate 0.85 shown as
        85 percent) without a hardcoded factor. Identity when `to_unit` is the canonical
        unit; raises on an unsupported pair rather than guessing.
        """
        entry = self.entry(our_key)  # controlled-vocabulary check
        canonical = entry.canonical_unit.value
        if to_unit == canonical:
            return value
        convert = _CONVERSIONS.get((canonical, to_unit))
        if convert is None:
            raise ValueError(
                f"no unit conversion from {canonical!r} to {to_unit!r} for {our_key!r}"
            )
        return convert(value)

    def observe(
        self,
        *,
        metric_key: str,
        raw_value: float,
        raw_unit: str,
        sample_id: str,
        analysis_run_id: str | None = None,
        source_artifact_id: str | None = None,
        source_field: str | None = None,
        source_locator: str | None = None,
    ) -> MetricValue:
        """Build a `MetricValue`: validate the key, normalize, and snapshot the registry.

        The registry — not the model — computes `normalized_value` and stamps
        `canonical_unit` + `metric_registry_version` onto the record, so the resulting
        `MetricValue` is standalone-interpretable (ADR-0007) and round-trips through
        `model_dump(mode="json")` without needing the registry again.
        """
        entry = self.entry(metric_key)  # rejects unknown our_key
        normalized = self.normalize(metric_key, raw_value, raw_unit)
        return MetricValue(
            sample_id=sample_id,
            metric_key=metric_key,
            gate=entry.gate,
            raw_value=raw_value,
            raw_unit=raw_unit,
            normalized_value=normalized,
            canonical_unit=entry.canonical_unit,
            metric_registry_version=self.version,
            analysis_run_id=analysis_run_id,
            source_artifact_id=source_artifact_id,
            source_field=source_field,
            source_locator=source_locator,
            parser_version=entry.parser_version,
            created_at=utc_now(),
        )


@lru_cache(maxsize=1)
def default_registry() -> MetricRegistry:
    """The packaged registry, loaded and cached once (read-only, so caching is safe)."""
    return MetricRegistry.load()
