"""The local artifact-store adapter — zero-dependency, offline default (ADR-0003).

:class:`LocalArtifactStore` wraps today's behavior: a run already lives in a directory on
disk, so :meth:`fetch` is (almost) the identity — it resolves ``run_ref`` to a
:class:`~pathlib.Path` and returns it for the unchanged :func:`bayleaf.parsers.load_run`
to read. It is the default adapter (see :func:`bayleaf.artifacts.get_artifact_store`) and
the fallback every remote store degrades to, so the whole gate runs offline with no
dependency and no network.

Tolerance, not validation: ``fetch`` does NOT require the directory to exist. A missing
run directory is a signal the tolerant parser already handles (:func:`load_run` returns an
empty bundle when its files are absent), so the store stays out of the business of judging
artifacts — that is the gate's job (ADR-0001).
"""

from __future__ import annotations

import os
from pathlib import Path

from .port import RunRef

# Optional base directory for resolving *relative* run refs. Env-driven (never hardcoded);
# unset -> refs are used as-is, which preserves the historical "pass a full path" behavior.
_ENV_LOCAL_ROOT = "BAYLEAF_ARTIFACT_LOCAL_ROOT"


class LocalArtifactStore:
    """Resolve a run reference to a local directory — identity over an on-disk run.

    With no ``root`` this is the pure identity (``fetch("data/mock_run_01")`` returns
    ``Path("data/mock_run_01")``), which is exactly the pre-port behavior. Given a ``root``
    (e.g. from ``BAYLEAF_ARTIFACT_LOCAL_ROOT``), a *relative* ``run_ref`` is resolved
    beneath it so runs can be addressed by bare name; an *absolute* ``run_ref`` is honored
    verbatim. It never touches the network and adds no dependency.
    """

    name = "local"

    def __init__(self, root: RunRef | None = None) -> None:
        # Store the optional base dir; None keeps fetch a strict identity (historical behavior).
        self._root = Path(root) if root is not None else None

    def fetch(self, run_ref: RunRef) -> Path:
        """Return the local directory for ``run_ref`` (joined under ``root`` if relative).

        No existence check: a missing directory is a signal :func:`load_run` tolerates, so
        the store returns a path either way rather than raising (ADR-0003 boundary tolerance).
        """
        ref = Path(run_ref)
        if self._root is not None and not ref.is_absolute():
            return self._root / ref
        return ref


def local_root_from_env() -> str | None:
    """Read the optional local-root override from the environment (None if unset/blank).

    Centralised so the factory and any adapter that falls back to local resolve the same
    base directory from the same env var, and it can never drift.
    """
    return os.environ.get(_ENV_LOCAL_ROOT) or None
