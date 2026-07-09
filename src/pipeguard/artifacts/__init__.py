"""Artifact-store port + adapters (ADR-0003) — locate a run's files as a local dir.

A boundary port sibling to :mod:`pipeguard.notify` and :mod:`pipeguard.persistence`, sitting
strictly UPSTREAM of the deterministic gate: it materializes a run's artifacts to a local
directory, then the unchanged parser/rules read them. It never influences a verdict — rules
decide (ADR-0001); swapping a store changes only *where the bytes come from*.

  * :class:`LocalArtifactStore` is the zero-dependency, offline default — ``fetch`` is the
    identity over an on-disk run directory, and the fallback every remote store degrades to.
  * :class:`S3ArtifactStore` is OFF by default: it lazy-imports ``boto3`` (an optional
    ``[s3]`` extra) and only pulls from a bucket when ``PIPEGUARD_S3_LIVE`` is armed;
    otherwise — or on ANY error — it degrades to the local store and touches no network.

:func:`get_artifact_store` flips the adapter from ``PIPEGUARD_ARTIFACT_STORE=local|s3``
(default ``local``), mirroring :func:`pipeguard.notify.get_notifier`. :func:`run_gate_from_store`
is the thin convenience that stages a run through a store and runs the existing gate.
"""

from __future__ import annotations

import os

from .local import LocalArtifactStore, local_root_from_env
from .port import ArtifactStore, RunRef
from .run import run_gate_from_store
from .s3 import S3ArtifactStore

# Env knob selecting the adapter (mirrors PIPEGUARD_NOTIFIER); nothing hardcoded — see
# .env.example. Default is the offline local store so the demo/tests never reach a network.
_ENV_ARTIFACT_STORE = "PIPEGUARD_ARTIFACT_STORE"


def get_artifact_store() -> ArtifactStore:
    """Select the artifact store from the environment (default: the offline local store).

    Set ``PIPEGUARD_ARTIFACT_STORE=s3`` to use :class:`S3ArtifactStore` — whose live pull still
    stays guarded behind ``PIPEGUARD_S3_LIVE`` and degrades to local when unarmed or on error.
    This is the single line that flips the seam; an unknown value falls back to local, so a typo
    never silently arms a remote.
    """
    choice = os.environ.get(_ENV_ARTIFACT_STORE, "local").strip().lower()
    if choice == "s3":
        return S3ArtifactStore()
    return LocalArtifactStore(root=local_root_from_env())


__all__ = [
    "ArtifactStore",
    "LocalArtifactStore",
    "RunRef",
    "S3ArtifactStore",
    "get_artifact_store",
    "run_gate_from_store",
]
