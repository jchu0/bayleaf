"""The artifact-store port: locate a run's files as a local directory (ADR-0003).

Realizes the "artifact store" seam ADR-0003 left as future work. It is a *boundary*
port — a sibling of :mod:`pipeguard.notify` and :mod:`pipeguard.persistence`, with no
framework imports — that sits strictly UPSTREAM of the deterministic gate: it only
*materializes* a run's artifacts to a local directory, then the unchanged
:func:`pipeguard.parsers.load_run` reads them. It never inspects, transforms, or
influences a verdict (rules decide; ADR-0001) — swapping a store changes only *where*
the bytes come from, never *what the gate concludes* about them.

A store's single job is :meth:`ArtifactStore.fetch`: given a ``run_ref`` (a local path
for :class:`~pipeguard.artifacts.local.LocalArtifactStore`, a run id resolving to
``s3://bucket/prefix/<run_id>/`` for :class:`~pipeguard.artifacts.s3.S3ArtifactStore`),
return the local directory the gate should read. Parsing stays tolerant downstream —
a missing artifact is a signal :func:`load_run` handles, not a crash — so ``fetch`` is
free to return a directory whose contents are partial or (for a degraded remote) empty.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypeAlias, runtime_checkable

# A reference to a run's artifacts. Deliberately permissive (``str | Path``) so a local
# store can take a directory path and a remote store can take a bare run id, both through
# one signature. The store — not the core — decides how to resolve it to bytes on disk.
RunRef: TypeAlias = str | Path


@runtime_checkable
class ArtifactStore(Protocol):
    """Locate a run's artifacts and stage them as a local directory.

    The one seam a caller uses to decouple *where a run lives* from *how the gate reads
    it*. An adapter is injected at the edge (via :func:`pipeguard.artifacts.get_artifact_store`
    or directly) and must satisfy two guarantees so it stays safe and off the critical path:

      1. :meth:`fetch` returns a local directory that :func:`pipeguard.parsers.load_run` can
         read — nothing more. The store never parses, ranks, or judges the artifacts.
      2. A store must not raise for an *expected* miss (an absent object, absent creds, an
         off-by-default remote): it degrades to a local directory instead, because a missing
         artifact is a signal the tolerant parser handles — not a reason to break the gate.
    """

    name: str

    def fetch(self, run_ref: RunRef) -> Path:
        """Materialize the run referenced by ``run_ref`` and return its local directory."""
        ...
