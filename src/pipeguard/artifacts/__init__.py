"""Artifact-store port + adapters (ADR-0003) — locate a run's files as a local dir.

A boundary port sibling to :mod:`pipeguard.notify` and :mod:`pipeguard.persistence`, sitting
strictly UPSTREAM of the deterministic gate: it materializes a run's artifacts to a local
directory, then the unchanged parser/rules read them. It never influences a verdict — rules
decide (ADR-0001); swapping a store changes only *where the bytes come from*.

  * :class:`LocalArtifactStore` is the zero-dependency, offline default — ``fetch`` is the
    identity over an on-disk run directory, and the fallback every remote store degrades to.

:func:`get_artifact_store` selects the adapter (default local); :func:`run_gate_from_store` is
the thin convenience that stages a run through a store and runs the existing gate.
"""

from __future__ import annotations

from .local import LocalArtifactStore, local_root_from_env
from .port import ArtifactStore, RunRef
from .run import run_gate_from_store


def get_artifact_store() -> ArtifactStore:
    """Select the artifact store (default: the offline local store).

    Mirrors :func:`pipeguard.notify.get_notifier`. Only the offline local store exists so
    far; a remote adapter registers here later behind its own env switch.
    """
    return LocalArtifactStore(root=local_root_from_env())


__all__ = [
    "ArtifactStore",
    "LocalArtifactStore",
    "RunRef",
    "get_artifact_store",
    "run_gate_from_store",
]
