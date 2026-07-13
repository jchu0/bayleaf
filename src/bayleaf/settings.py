"""Typed, call-time configuration resolvers for the framework-agnostic core.

WHY this module exists (WS-03d): run-store discovery must not be hardcoded to the repo ``data/``
dir, so ingestion and API discovery can be repointed for a test or a deployment. The single
resolver here is the canonical answer to "where do run dirs live?".

WHY ``BAYLEAF_DATA_ROOT`` (not a new ``BAYLEAF_RUN_ROOT``): the read-API already resolves runs
under ``BAYLEAF_DATA_ROOT`` at call-time (``api/card_readout.py::_data_root``). Introducing a
second env name would be exactly the "third divergent knob" the WS-03 review flags as a risk — so
this consolidates on the existing name and gives the API's scattered import-time ``data/`` constants
(``api/main.py``, ``api/routers/files.py``, ``api/routers/pipelines_lifecycle.py``) one place to
converge onto later (a precise, deferred follow-up — not done here to keep this change small).

WHY a plain resolver, not ``pydantic-settings``: the codebase has no ``BaseSettings`` anywhere and
``pydantic-settings`` is not a dependency; adding it for a single path setting would be an
unjustified dependency and a duplicate of the existing ``os.environ`` call-time pattern
(CLAUDE.md dependency + reuse guardrails). Resolution is per-call so a mid-process ``setenv``
(a test's ``monkeypatch``, a deploy's env) is honored immediately — never captured at import.
"""

from __future__ import annotations

import os
from pathlib import Path

# The default when ``BAYLEAF_DATA_ROOT`` is unset: the repo's committed ``data/`` dir.
# ``settings.py`` lives at ``src/bayleaf/`` so the repo root is three parents up.
_DEFAULT_DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data"

# The env var that repoints run-store discovery. Named to MATCH the read-API's existing knob
# (api/card_readout.py) rather than introduce a divergent one.
RUN_ROOT_ENV = "BAYLEAF_DATA_ROOT"


def run_store_root() -> Path:
    """Return the root directory under which run dirs are discovered/materialized.

    Resolved at call-time from ``BAYLEAF_DATA_ROOT`` (else the repo ``data/`` default), so a test
    or deployment can repoint it via an env var without any import-time coupling.
    """
    raw = os.environ.get(RUN_ROOT_ENV, "").strip()
    return Path(raw) if raw else _DEFAULT_DATA_ROOT
