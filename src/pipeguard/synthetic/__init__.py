"""Synthetic run generator (T-013, synthetic half).

Writes contrived NovaSeq run directories in the exact on-disk shape the existing
parsers already read (``SampleSheet.csv`` / ``sample_metadata.csv`` /
``demux_stats.csv`` / ``qc_metrics.csv`` / ``pipeline.log``), driven by a spec of
per-sample *failure modes*. Each mode is tuned so the deterministic gate lands the
sample on an intended verdict — giving the demo several diverse runs instead of one.

Origin is always ``contrived`` (hand-authored formats, invented values); every run is
tagged both in-band (a ``pipeguard-synthetic`` note in ``pipeline.log``) and out-of-band
(an ``origin`` marker file), plus in ``data/README.md`` per ``docs/data/strategy.md`` —
never misrepresented as real GIAB.

The :mod:`~pipeguard.synthetic.scale` module drives the generator at volume: one large
N-sample run and many-run batches (with zero-padded IDs and a mixed failure spread) so
the frontend's scale affordances have real data to test against.
"""

from .generator import (
    DEMO_RUNS,
    INTENDED_VERDICT,
    ORIGIN_LABEL,
    FailureMode,
    RunSpec,
    SampleSpec,
    generate_run,
    intended_verdict,
)
from .scale import (
    BULK_DIR_NAME,
    COMMITTED_RUNS,
    COMMITTED_SCALE_RUN_ID,
    COMMITTED_SCALE_SEED,
    SCALE_RUN,
    build_bulk_specs,
    build_scale_spec,
    generate_bulk,
    generate_committed,
    planted_modes,
    sample_ids,
)

__all__ = [
    "BULK_DIR_NAME",
    "COMMITTED_RUNS",
    "COMMITTED_SCALE_RUN_ID",
    "COMMITTED_SCALE_SEED",
    "DEMO_RUNS",
    "INTENDED_VERDICT",
    "ORIGIN_LABEL",
    "SCALE_RUN",
    "FailureMode",
    "RunSpec",
    "SampleSpec",
    "build_bulk_specs",
    "build_scale_spec",
    "generate_bulk",
    "generate_committed",
    "generate_run",
    "intended_verdict",
    "planted_modes",
    "sample_ids",
]
