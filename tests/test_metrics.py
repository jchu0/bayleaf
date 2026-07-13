"""Tests for the metric registry (docs/data/metric_registry.md) — offline, additive.

These pin the contract that makes the registry the stable layer above MultiQC key drift:
every seed metric loads, unit normalization is correct (including the `pct_*` trap where
the same metric arrives as a fraction from Picard and a percent from MultiQC), aliases
resolve, unknown keys are rejected, and a `MetricValue` round-trips through JSON with its
normalization baked in (ADR-0007 self-containment). The registry is NOT yet on the
parser/rules critical path — nothing here exercises the gate.
"""

from __future__ import annotations

import math

import pytest

from bayleaf.metrics import (
    MetricRegistry,
    UnknownMetricError,
    default_registry,
)
from bayleaf.models import CanonicalUnit, Gate, MetricValue

# The full seed vocabulary (metric_registry.md "Seed registry"). Pinned here so a
# dropped/renamed entry fails loudly rather than silently shrinking the vocabulary.
SEED_KEYS = {
    "preflight.phix_aligned",
    "qc.q30",
    "qc.reads_passing_filter",
    "qc.cluster_pf",
    "qc.duplication",
    "qc.pct_mapped",
    "qc.on_target",
    "qc.mean_target_coverage",
    "qc.breadth_20x",
    "qc.breadth_30x",
    "qc.zero_cov_targets",
    "qc.fold_enrichment",
    "qc.fold_80",
    "identity.ngscheckmate_match",
    "identity.sex_concordance",
    "contamination.freemix",
    "concordance.snp_f1",
    "variant.dp",
    "variant.gq",
    "variant.allele_balance",
    "variant.titv",
}


@pytest.fixture(scope="module")
def registry() -> MetricRegistry:
    return default_registry()


def test_registry_loads_all_seed_keys(registry: MetricRegistry) -> None:
    """Every seed metric parses into a typed entry; version is pinned at 1."""
    assert registry.version == 1
    assert set(registry.keys()) == SEED_KEYS
    # Every entry validated into the typed model (no raw dicts leaked through).
    for key in SEED_KEYS:
        entry = registry.entry(key)
        assert entry.our_key == key
        assert isinstance(entry.gate, Gate)
        assert isinstance(entry.canonical_unit, CanonicalUnit)


def test_default_registry_is_cached() -> None:
    """The packaged registry is loaded once (read-only) and reused."""
    assert default_registry() is default_registry()


def test_percent_to_fraction(registry: MetricRegistry) -> None:
    """A percent value for a `fraction` metric is divided by 100."""
    assert math.isclose(registry.normalize("qc.q30", 95.0, "percent"), 0.95)
    # A fraction for the same metric passes through unchanged.
    assert math.isclose(registry.normalize("qc.q30", 0.95, "fraction"), 0.95)


def test_percent_to_fraction_is_exact(registry: MetricRegistry) -> None:
    """Conversion divides by 100 (not `* 0.01`), so the result is the exact decimal.

    This is not pedantry: `normalized_value` is snapshotted into
    `MetricValue.content_hash` (the immutable identity), so `0.95` vs
    `0.9500000000000001` would give two different hashes for the same measurement.
    """
    assert registry.normalize("qc.q30", 95.0, "percent") == 0.95
    assert registry.normalize("qc.q30", 50.0, "percent") == 0.5


def test_bool_metric_rejects_non_boolean_value(registry: MetricRegistry) -> None:
    """A `bool` metric must carry 0/1; a stray value is a loud error, not stored nonsense."""
    assert registry.entry("identity.ngscheckmate_match").value_type.value == "bool"
    assert registry.normalize("identity.ngscheckmate_match", 1.0, "bool") == 1.0
    with pytest.raises(ValueError):
        registry.normalize("identity.ngscheckmate_match", 7.0, "bool")


def test_denormalize_is_the_inverse_of_normalize(registry: MetricRegistry) -> None:
    """denormalize renders a canonical value back into a display unit (for the finding text)."""
    # A fraction gate 0.85 shown as 85 percent.
    assert math.isclose(registry.denormalize("qc.q30", 0.85, "percent"), 85.0)
    # Identity when the target is already the canonical unit (fraction, and x for coverage).
    assert registry.denormalize("qc.q30", 0.841, "fraction") == 0.841
    assert registry.denormalize("qc.mean_target_coverage", 30.0, "x") == 30.0
    # Round-trips: normalize then denormalize returns the original.
    frac = registry.normalize("qc.q30", 84.1, "percent")
    assert math.isclose(registry.denormalize("qc.q30", frac, "percent"), 84.1)
    # An unsupported target unit raises rather than guessing (x has no percent form).
    with pytest.raises(ValueError):
        registry.denormalize("qc.mean_target_coverage", 30.0, "percent")


def test_x_stays_x(registry: MetricRegistry) -> None:
    """`x` (fold coverage) is identity — no rescale."""
    assert registry.entry("qc.mean_target_coverage").canonical_unit is CanonicalUnit.X
    assert math.isclose(registry.normalize("qc.mean_target_coverage", 150.0, "x"), 150.0)


def test_percent_canonical_stays_percent(registry: MetricRegistry) -> None:
    """A `percent`-canonical metric (PhiX) is NOT rescaled to a fraction."""
    assert registry.entry("preflight.phix_aligned").canonical_unit is CanonicalUnit.PERCENT
    assert math.isclose(registry.normalize("preflight.phix_aligned", 0.42, "percent"), 0.42)


def test_multiqc_pct_trap(registry: MetricRegistry) -> None:
    """The `pct_*` trap: same metric, two sources, two units — only the unit decides.

    `qc.breadth_20x` is a `fraction`. From Picard `PCT_TARGET_BASES_20X` it arrives as a
    fraction (identity); from mosdepth/MultiQC `20_x_pc` it arrives as a percent and MUST
    be divided by 100. The field name never decides the scale — the declared unit does.
    """
    assert registry.entry("qc.breadth_20x").canonical_unit is CanonicalUnit.FRACTION
    # Picard: fraction -> identity.
    assert math.isclose(registry.normalize("qc.breadth_20x", 0.992, "fraction"), 0.992)
    # mosdepth via MultiQC: percent -> /100. Both map to the same our_key via alias.
    assert registry.resolve_alias("20_x_pc") == "qc.breadth_20x"
    assert math.isclose(registry.normalize("qc.breadth_20x", 99.2, "percent"), 0.992)


def test_disallowed_raw_unit_rejected(registry: MetricRegistry) -> None:
    """A raw_unit the entry does not allow is a loud error, not a silent guess."""
    # mean_target_coverage only allows `x`; a stray percent must not be coerced.
    with pytest.raises(ValueError):
        registry.normalize("qc.mean_target_coverage", 50.0, "percent")


def test_unsupported_conversion_rejected() -> None:
    """An allowed-but-unconvertible unit pair raises rather than fabricating a factor."""
    # A hand-built registry whose allowed units include a pair with no conversion rule.
    reg = MetricRegistry.model_validate(
        {
            "version": 1,
            "entries": {
                "qc.weird": {
                    "our_key": "qc.weird",
                    "display_name": "Weird",
                    "gate": "qc",
                    "category": "coverage",
                    "canonical_unit": "fraction",
                    "value_type": "float",
                    "direction": "higher_is_better",
                    "source": {"module": "test"},
                    "raw_units_allowed": ["fraction", "x"],
                    "aliases": [],
                }
            },
            "alias_index": {},
        }
    )
    with pytest.raises(ValueError):
        reg.normalize("qc.weird", 1.0, "x")  # x -> fraction has no rule


def test_alias_resolution(registry: MetricRegistry) -> None:
    """Prior/variant MultiQC keys fold back to the canonical our_key."""
    assert registry.resolve_alias("pct_duplication") == "qc.duplication"
    assert registry.resolve_alias("percent_duplicates") == "qc.duplication"
    assert registry.resolve_alias("30_x_pc") == "qc.breadth_30x"
    assert registry.resolve_alias("ts_tv") == "variant.titv"
    # An our_key resolves to itself (idempotent).
    assert registry.resolve_alias("qc.q30") == "qc.q30"


def test_unknown_key_rejected(registry: MetricRegistry) -> None:
    """Unknown keys are rejected everywhere they could leak into the vocabulary."""
    with pytest.raises(UnknownMetricError):
        registry.entry("qc.not_a_real_metric")
    with pytest.raises(UnknownMetricError):
        registry.resolve_alias("totally_unknown_key")
    with pytest.raises(UnknownMetricError):
        registry.normalize("qc.not_a_real_metric", 1.0, "fraction")


def test_alias_collision_rejected_at_load() -> None:
    """A registry whose alias shadows another our_key fails to load (integrity check)."""
    with pytest.raises(ValueError):
        _bad_registry_with_colliding_alias()


def _bad_registry_with_colliding_alias() -> MetricRegistry:
    import tempfile
    from pathlib import Path

    yaml_text = (
        "metric_registry_version: 1\n"
        "metrics:\n"
        "  qc.a:\n"
        "    display_name: A\n"
        "    gate: qc\n"
        "    category: coverage\n"
        "    canonical_unit: fraction\n"
        "    value_type: float\n"
        "    direction: higher_is_better\n"
        "    source: {module: test}\n"
        "    raw_units_allowed: [fraction]\n"
        "    aliases: [qc.b]\n"  # collides with a registered our_key
        "  qc.b:\n"
        "    display_name: B\n"
        "    gate: qc\n"
        "    category: coverage\n"
        "    canonical_unit: fraction\n"
        "    value_type: float\n"
        "    direction: higher_is_better\n"
        "    source: {module: test}\n"
        "    raw_units_allowed: [fraction]\n"
        "    aliases: []\n"
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        p.write_text(yaml_text, encoding="utf-8")
        return MetricRegistry.load(p)


def test_observe_builds_metric_value(registry: MetricRegistry) -> None:
    """`observe` validates the key, normalizes, and snapshots the registry onto the record."""
    mv = registry.observe(
        metric_key="qc.breadth_20x",
        raw_value=99.2,
        raw_unit="percent",
        sample_id="S1",
        source_artifact_id="art_123",
        source_field="20_x_pc",
    )
    assert isinstance(mv, MetricValue)
    assert mv.gate is Gate.QC
    assert mv.canonical_unit is CanonicalUnit.FRACTION
    assert mv.metric_registry_version == registry.version
    assert math.isclose(mv.normalized_value, 0.992)
    assert math.isclose(mv.raw_value, 99.2)


def test_observe_rejects_unknown_key(registry: MetricRegistry) -> None:
    with pytest.raises(UnknownMetricError):
        registry.observe(
            metric_key="qc.made_up", raw_value=1.0, raw_unit="fraction", sample_id="S1"
        )


def test_metric_value_json_round_trip(registry: MetricRegistry) -> None:
    """A MetricValue survives `model_dump(mode="json")` -> `model_validate` unchanged.

    The normalized value and canonical unit are stored (snapshotted), so the record is
    interpretable with no registry in hand — the ledger/ML self-containment invariant.
    """
    mv = registry.observe(metric_key="qc.q30", raw_value=95.0, raw_unit="percent", sample_id="S1")
    dumped = mv.model_dump(mode="json")
    # JSON-native scalars only (the point of mode="json" for the ledger).
    assert dumped["canonical_unit"] == "fraction"
    assert dumped["gate"] == "qc"
    assert math.isclose(dumped["normalized_value"], 0.95)

    restored = MetricValue.model_validate(dumped)
    assert restored == mv
    assert restored.content_hash == mv.content_hash
