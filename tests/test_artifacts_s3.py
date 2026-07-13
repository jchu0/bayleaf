"""Tests for the S3 artifact-store adapter (offline; OFF by default).

These run fully offline (no boto3 required, no network, no real bucket). They pin the
guarantees that make the remote seam safe to flip on later, mirroring the Slack notify tests:
the pull is OFF unless ``BAYLEAF_S3_LIVE`` is armed, a configured bucket/creds alone never
pull, ANY error (absent boto3, an API failure) degrades to the offline local store, and the
(deferred) live-pull seam is exercised with an INJECTED FAKE CLIENT — never the wire. The one
place objects are actually "downloaded", they are copied from a local fixture dir by the fake.
"""

import filecmp
import shutil
import sys
from pathlib import Path

import pytest

from bayleaf import run_gate_from_dir
from bayleaf.artifacts import (
    ArtifactStore,
    LocalArtifactStore,
    S3ArtifactStore,
    get_artifact_store,
    run_gate_from_store,
)
from bayleaf.synthesis import StubSynthesizer

DATA = Path(__file__).resolve().parent.parent / "data" / "mock_run_01"


@pytest.fixture(autouse=True)
def _disarm_s3(monkeypatch):
    """Belt-and-suspenders: NO test may pull from a real bucket — even on a machine whose
    shell/.env has BAYLEAF_S3_LIVE + creds set. The live pull is env-armed, so force it OFF
    and clear the store config for every test; the few tests that exercise the live seam
    re-arm it explicitly (after this autouse fixture runs) and inject a fake client."""
    for var in (
        "BAYLEAF_S3_LIVE",
        "BAYLEAF_S3_BUCKET",
        "BAYLEAF_S3_PREFIX",
        "BAYLEAF_ARTIFACT_STORE",
        "BAYLEAF_ARTIFACT_LOCAL_ROOT",
    ):
        monkeypatch.delenv(var, raising=False)


class _FakeS3Client:
    """A minimal stand-in for a boto3 S3 client that stages files from a local source dir.

    It records every call so a test can assert the wiring SHAPE (Bucket / Prefix / Key) without a
    real bucket or the network — the same tactic the Slack notify tests use for `chat_postMessage`.
    """

    def __init__(self, source: Path) -> None:
        self._source = source
        self.calls: list[tuple[str, dict]] = []

    def list_objects_v2(self, **kwargs):
        self.calls.append(("list", kwargs))
        prefix = kwargs.get("Prefix", "")
        # Advertise one object per file in the source dir, keyed under the requested prefix.
        return {
            "Contents": [
                {"Key": f"{prefix}{p.name}"} for p in sorted(self._source.iterdir()) if p.is_file()
            ]
        }

    # Bucket/Key/Filename mirror boto3's positional signature (pep8-naming isn't enabled).
    def download_file(self, Bucket, Key, Filename):
        self.calls.append(("download", {"Bucket": Bucket, "Key": Key, "Filename": Filename}))
        # "Download" == copy the corresponding local fixture file to the staging path.
        shutil.copyfile(self._source / Key.rsplit("/", 1)[-1], Filename)


# --- the env factory + protocol conformance -------------------------------------------


def test_get_artifact_store_selects_s3_from_env(monkeypatch):
    monkeypatch.setenv("BAYLEAF_ARTIFACT_STORE", "s3")
    store = get_artifact_store()
    assert isinstance(store, S3ArtifactStore)
    assert store.name == "s3"


def test_get_artifact_store_unknown_value_falls_back_to_local(monkeypatch):
    monkeypatch.setenv("BAYLEAF_ARTIFACT_STORE", "gcs-typo")
    assert isinstance(get_artifact_store(), LocalArtifactStore)


def test_s3_store_satisfies_the_port():
    assert isinstance(S3ArtifactStore(), ArtifactStore)


# --- OFF by default: unarmed / unconfigured degrades to local, no client, no network ----


def test_s3_not_armed_degrades_to_local(monkeypatch):
    """With BAYLEAF_S3_LIVE unset, fetch degrades to the local store and builds no client."""
    store = S3ArtifactStore()  # unconfigured bucket + unarmed

    def _fail():
        raise AssertionError("_get_client must not be called when the pull is not armed")

    monkeypatch.setattr(store, "_get_client", _fail)
    # Degrades to the local identity path — NOT a staged temp dir.
    assert store.fetch("mock_run_01") == Path("mock_run_01")


def test_s3_never_pulls_when_not_armed_even_with_bucket(monkeypatch):
    """A configured bucket + prefix alone never trigger a pull — only BAYLEAF_S3_LIVE does."""
    store = S3ArtifactStore(bucket="test-bucket", prefix="runs")

    def _fail():
        raise AssertionError("_get_client must not be called when the pull is not armed")

    monkeypatch.setattr(store, "_get_client", _fail)
    assert store.fetch("mock_run_01") == Path("mock_run_01")


# --- armed but failing: ANY error degrades to local (never breaks the gate) -------------


def test_s3_armed_client_error_degrades_to_local(monkeypatch):
    monkeypatch.setenv("BAYLEAF_S3_LIVE", "1")
    store = S3ArtifactStore(bucket="test-bucket")

    def _boom():
        raise RuntimeError("boto3 client build / credentials failure")

    monkeypatch.setattr(store, "_get_client", _boom)
    assert store.fetch("mock_run_01") == Path("mock_run_01")


def test_s3_armed_missing_boto3_degrades_to_local(monkeypatch):
    """Armed but boto3 absent: the lazy import fails and the store degrades to local."""
    monkeypatch.setenv("BAYLEAF_S3_LIVE", "1")
    # Force the lazy `import boto3` inside the real _get_client to raise ImportError.
    monkeypatch.setitem(sys.modules, "boto3", None)
    store = S3ArtifactStore(bucket="test-bucket")
    assert store.fetch("mock_run_01") == Path("mock_run_01")


# --- the live-pull seam, proven with a FAKE client — no real bucket, no wire -------------


def test_s3_live_seam_stages_objects_with_fake_client(monkeypatch):
    """The one place a "download" happens — armed AND a fake client injected.

    Proves the wiring shape: list under s3://bucket/<prefix>/<run>/, download each object to a
    fresh temp dir. The default demo/suite never reaches here.
    """
    monkeypatch.setenv("BAYLEAF_S3_LIVE", "1")
    fake = _FakeS3Client(source=DATA)
    store = S3ArtifactStore(bucket="test-bucket", prefix="runs")
    monkeypatch.setattr(store, "_get_client", lambda: fake)

    dest = store.fetch("mock_run_01")

    # Every source file was staged into the temp dir, byte-for-byte.
    source_files = sorted(p.name for p in DATA.iterdir() if p.is_file())
    staged_files = sorted(p.name for p in dest.iterdir() if p.is_file())
    assert staged_files == source_files
    for name in source_files:
        assert filecmp.cmp(dest / name, DATA / name, shallow=False)

    # The list call used the right bucket + composed prefix; a download per object followed.
    list_calls = [c for c in fake.calls if c[0] == "list"]
    assert len(list_calls) == 1
    assert list_calls[0][1]["Bucket"] == "test-bucket"
    assert list_calls[0][1]["Prefix"] == "runs/mock_run_01/"
    assert sum(1 for c in fake.calls if c[0] == "download") == len(source_files)


def test_run_gate_from_store_via_s3_fake_client_matches_direct(monkeypatch):
    """End-to-end: staging via the S3 seam then gating yields the same verdicts as reading the
    directory directly — the store changes only where the bytes come from (ADR-0001/0003)."""
    monkeypatch.setenv("BAYLEAF_S3_LIVE", "1")
    fake = _FakeS3Client(source=DATA)
    store = S3ArtifactStore(bucket="test-bucket", prefix="runs")
    monkeypatch.setattr(store, "_get_client", lambda: fake)

    _, via_s3 = run_gate_from_store(store, "mock_run_01", synthesizer=StubSynthesizer())
    _, direct = run_gate_from_dir(DATA, synthesizer=StubSynthesizer())

    assert {c.sample_id: c.verdict.value for c in via_s3} == {
        c.sample_id: c.verdict.value for c in direct
    }
