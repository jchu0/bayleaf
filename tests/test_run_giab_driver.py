"""The Nextflow-first GIAB driver's executor auto-detection (W4, ADR-0003 — same graph, executor
by profile). Pins the branch only: `sbatch` on PATH → `slurm`, else the local-serial `standard`
fallback. CONFIG-VERIFIED, not cluster-verified — this env has no `sbatch`, so a real cluster run is
never asserted; only the selection logic is.
"""

from __future__ import annotations

import shutil

import pytest
from scripts.run_giab_pipeline import _detect_profile


def test_required_output_kinds_are_the_frozen_five_parse_contract() -> None:
    """WS-09: ``REQUIRED_OUTPUT_KINDS`` IS the post-run parse contract, one entry per glob
    ``parse_sample`` actually reads — so the submit-time gate that rejects a non-gate-able authored
    pipeline can NOT drift from what the parser demands (they share one constant)."""
    from scripts.run_giab_pipeline import _FROZEN_FIVE_OUTPUTS, REQUIRED_OUTPUT_KINDS

    # The kind set the routers validate against is exactly the mapping the parser globs by.
    assert frozenset(_FROZEN_FIVE_OUTPUTS) == REQUIRED_OUTPUT_KINDS
    # The globs are the SAME ones parse_sample has always used (byte-identical germline path).
    assert _FROZEN_FIVE_OUTPUTS["fastp_json"] == "fastp.json"
    assert _FROZEN_FIVE_OUTPUTS["mosdepth_summary"] == "*mosdepth.summary.txt"
    assert _FROZEN_FIVE_OUTPUTS["mosdepth_thresholds"] == "*thresholds.bed.gz"
    assert _FROZEN_FIVE_OUTPUTS["filtered_vcf"] == "norm.vcf.gz"


def test_germline_reference_chain_satisfies_the_parse_contract() -> None:
    """Anti-drift guard: the germline REFERENCE chain must itself produce every required output kind
    (else the pinned demo could never gate). Freezes the ``reference ⊇ contract`` invariant so a
    future required kind the reference doesn't produce is caught HERE, not in a live run."""
    from scripts.run_giab_pipeline import REQUIRED_OUTPUT_KINDS

    from bayleaf.nextflow import germline_graph

    produced = {kind for node in germline_graph().nodes for kind in node.outs}
    assert produced >= REQUIRED_OUTPUT_KINDS


def test_detect_profile_falls_back_to_standard_without_sbatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert _detect_profile() == "standard"


def test_detect_profile_picks_slurm_when_sbatch_is_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_which(name: str) -> str | None:
        return "/usr/bin/sbatch" if name == "sbatch" else None

    monkeypatch.setattr(shutil, "which", fake_which)
    assert _detect_profile() == "slurm"
