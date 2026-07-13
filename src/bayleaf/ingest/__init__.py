"""Boundary-only ingestion adapters: a published pipeline ``results/`` dir → the registry-keyed
``SampleMetrics`` contract (WS-06·PR1), upstream of the deterministic gate.

An adapter reads the artifacts a real nf-core/MultiQC pipeline already PUBLISHES (fastp.json,
mosdepth summary/thresholds, ``multiqc_data/multiqc_data.json``) and emits ``SampleMetrics`` with
each metric's ``raw_unit`` DECLARED at its true source scale (never guessed — the pct_* trap). It
carries NO verdict logic (ADR-0001): the verdict stays a deterministic function of ``Finding``s the
rules compute over the produced metrics. A missing file is a signal (skip), an unknown key is
surfaced honestly (``unmapped``), and nothing is ever fabricated or defaulted to a passing value.
"""

from __future__ import annotations

from .nfcore import IngestResult, UnmappedKey, ingest_results_dir

__all__ = ["IngestResult", "UnmappedKey", "ingest_results_dir"]
