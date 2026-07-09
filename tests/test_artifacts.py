"""Tests for the artifact-store port (offline, local-first).

These run fully offline. They pin the guarantees that make the seam safe: the port only
*locates* a run's files (it never touches a verdict), the local adapter is the identity over
an on-disk directory, missing artifacts degrade instead of crashing, and staging a run through
a store yields byte-for-byte the same gate result as reading the directory directly — so the
store changes only *where the bytes come from*, never *what the gate decides* (ADR-0001/0003).

The S3 adapter (OFF by default) is exercised in :mod:`tests.test_artifacts_s3` with an injected
fake client — never a real bucket.
"""

from pathlib import Path

from pipeguard import run_gate_from_dir
from pipeguard.artifacts import (
    ArtifactStore,
    LocalArtifactStore,
    get_artifact_store,
    run_gate_from_store,
)
from pipeguard.synthesis import StubSynthesizer

DATA = Path(__file__).resolve().parent.parent / "data" / "mock_run_01"


# --- the local adapter: fetch is (root-joined) identity, and it never crashes ----------


def test_local_fetch_is_identity_without_root():
    """With no root, fetch returns the ref verbatim — exactly the pre-port behavior."""
    store = LocalArtifactStore()
    assert store.fetch(DATA) == DATA
    assert store.fetch("data/mock_run_01") == Path("data/mock_run_01")


def test_local_fetch_joins_relative_ref_under_root():
    """A relative ref is resolved beneath root; an absolute ref is honored verbatim."""
    store = LocalArtifactStore(root="/base/runs")
    assert store.fetch("run_x") == Path("/base/runs/run_x")
    assert store.fetch("/abs/run_y") == Path("/abs/run_y")


def test_local_fetch_tolerates_missing_directory(tmp_path):
    """A missing run directory is a signal the parser handles, not a reason to raise."""
    missing = tmp_path / "does_not_exist"
    # No exception, and no requirement that the directory exists.
    assert LocalArtifactStore().fetch(missing) == missing


# --- the port only LOCATES: staging a run == reading the directory directly ------------


def test_run_gate_from_store_matches_run_gate_from_dir():
    """The store is off the decision path: same directory in, byte-for-byte same cards out."""
    store = LocalArtifactStore()
    _, via_store = run_gate_from_store(store, DATA, synthesizer=StubSynthesizer())
    _, direct = run_gate_from_dir(DATA, synthesizer=StubSynthesizer())

    by_store = {c.sample_id: c.verdict.value for c in via_store}
    by_direct = {c.sample_id: c.verdict.value for c in direct}
    assert by_store == by_direct
    # Pin the demo scenario so a regression in the seam is obvious (matches test_gate.py).
    assert by_store["S4"] == "escalate"
    assert by_store["S5"] == "hold"


def test_run_gate_from_store_degrades_on_missing_run(tmp_path):
    """A missing run degrades to an empty result — the tolerant boundary, not a crash."""
    store = LocalArtifactStore()
    artifacts, cards = run_gate_from_store(store, tmp_path / "nope")
    assert cards == []
    assert artifacts.samples == []


# --- the env factory + protocol conformance -------------------------------------------


def test_get_artifact_store_defaults_to_local(monkeypatch):
    monkeypatch.delenv("PIPEGUARD_ARTIFACT_STORE", raising=False)
    store = get_artifact_store()
    assert isinstance(store, LocalArtifactStore)
    assert store.name == "local"


def test_local_store_satisfies_the_port():
    """The adapter structurally satisfies the runtime-checkable ArtifactStore protocol."""
    assert isinstance(LocalArtifactStore(), ArtifactStore)
