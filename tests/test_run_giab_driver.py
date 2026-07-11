"""The Nextflow-first GIAB driver's executor auto-detection (W4, ADR-0003 — same graph, executor
by profile). Pins the branch only: `sbatch` on PATH → `slurm`, else the local-serial `standard`
fallback. CONFIG-VERIFIED, not cluster-verified — this env has no `sbatch`, so a real cluster run is
never asserted; only the selection logic is.
"""

from __future__ import annotations

import shutil

import pytest
from scripts.run_giab_pipeline import _detect_profile


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
