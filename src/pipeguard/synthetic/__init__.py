"""Synthetic run generator (T-013, synthetic half).

Writes contrived NovaSeq run directories in the exact on-disk shape the existing
parsers already read (``SampleSheet.csv`` / ``sample_metadata.csv`` /
``demux_stats.csv`` / ``qc_metrics.csv`` / ``pipeline.log``), driven by a spec of
per-sample *failure modes*. Each mode is tuned so the deterministic gate lands the
sample on an intended verdict — giving the demo several diverse runs instead of one.

Origin is always ``contrived`` (hand-authored formats, invented values); every run
is tagged in-band (a ``pipeguard-synthetic`` note in ``pipeline.log``) and in
``data/README.md`` per ``docs/data/strategy.md`` — never misrepresented as real GIAB.
"""

from .generator import (
    DEMO_RUNS,
    INTENDED_VERDICT,
    FailureMode,
    RunSpec,
    SampleSpec,
    generate_run,
    intended_verdict,
)

__all__ = [
    "DEMO_RUNS",
    "INTENDED_VERDICT",
    "FailureMode",
    "RunSpec",
    "SampleSpec",
    "generate_run",
    "intended_verdict",
]
