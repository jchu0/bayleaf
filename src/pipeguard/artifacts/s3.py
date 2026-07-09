"""The S3 artifact-store adapter — OFF by default, live pull opt-in (ADR-0003).

:class:`S3ArtifactStore` stages a run's objects from ``s3://bucket/<prefix>/<run_id>/`` into a
local temp directory, then the unchanged :func:`pipeguard.parsers.load_run` reads them — so the
deterministic gate is identical whether a run lives on disk or in a bucket. Its safety shape
deliberately mirrors :class:`pipeguard.notify.SlackNotifier` so the seam is safe to flip on:

  * ``boto3`` is imported LAZILY (it is an optional ``[s3]`` extra, not a core dep), so the
    package installs and runs without it.
  * The live pull is opt-in via ``PIPEGUARD_S3_LIVE`` (:func:`_s3_live_enabled`). Pulling real
    genomics artifacts from a cloud bucket is outward-facing and is where PHI would live, so it
    never turns on by default, by accident, or from a configured bucket/creds alone.
  * ANY error — absent ``boto3``, absent/invalid creds, an API failure, an unconfigured bucket —
    degrades to the offline :class:`~pipeguard.artifacts.local.LocalArtifactStore`. An artifact
    fetch can never break the gate, and no key, token, or URL is ever logged.

AWS credentials and region are resolved by ``boto3`` itself from the standard environment /
instance chain (``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` / ``AWS_REGION`` …); this
adapter never reads, holds, or logs them.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from .local import LocalArtifactStore, local_root_from_env
from .port import RunRef

# Env knobs (mirror the notify seam; nothing hardcoded — see .env.example).
_ENV_S3_LIVE = "PIPEGUARD_S3_LIVE"
_ENV_S3_BUCKET = "PIPEGUARD_S3_BUCKET"
_ENV_S3_PREFIX = "PIPEGUARD_S3_PREFIX"

# Placeholder so an unconfigured bucket degrades cleanly instead of building a bogus request.
_UNCONFIGURED_BUCKET = "unconfigured"

_TRUTHY = {"1", "true", "yes", "on"}


def _s3_live_enabled() -> bool:
    """Whether the outward-facing S3 pull is armed — the single safety switch.

    Off unless ``PIPEGUARD_S3_LIVE`` is explicitly truthy in the environment. Read from
    ``os.environ`` (not a module constant) so it is opt-in per process and can't be baked in:
    the demo and the test suite stay offline until a maintainer deliberately exports this flag.
    """
    return os.environ.get(_ENV_S3_LIVE, "").strip().lower() in _TRUTHY


class S3ArtifactStore:
    """S3 artifact store — OFF by default, live pull opt-in, degrade-to-local on any error.

    Constructing this does NOT touch the network (and neither does constructing the underlying
    ``boto3`` client) — only a :meth:`fetch` with the live flag armed lists/downloads objects.
    """

    name = "s3"

    def __init__(
        self,
        bucket: str | None = None,
        prefix: str | None = None,
        local_root: RunRef | None = None,
    ) -> None:
        # Never hardcode config — resolve from env, else a clearly-unconfigured placeholder so
        # an unarmed/misconfigured store degrades cleanly rather than issuing a bogus request.
        self._bucket = bucket or os.environ.get(_ENV_S3_BUCKET) or _UNCONFIGURED_BUCKET
        raw_prefix = prefix if prefix is not None else os.environ.get(_ENV_S3_PREFIX, "")
        self._prefix = raw_prefix.strip("/")
        # The offline store we degrade to on guard-off / misconfig / ANY error.
        self._fallback = LocalArtifactStore(
            root=local_root if local_root is not None else local_root_from_env()
        )
        self._client: Any = None  # boto3 S3 client, created lazily on first live use

    def _get_client(self) -> Any:
        """Lazily construct the S3 client (import + client build).

        Kept separate so the live path is a single, testable seam (a test injects a fake here).
        Raises when ``boto3`` is absent — which :meth:`fetch` catches and degrades on.
        Constructing a client does NOT touch the network; only list/download would.
        """
        if self._client is None:
            import boto3  # lazy: boto3 is an optional [s3] extra, intentionally not a core dep

            # Best-effort local .env load (python-dotenv ships with the [claude] extra; plain
            # environment variables still work without it).
            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:
                pass

            # boto3 resolves creds/region from the standard env/instance chain itself; this
            # adapter never reads, holds, or logs them.
            self._client = boto3.client("s3")
        return self._client

    def fetch(self, run_ref: RunRef) -> Path:
        """Stage the run from the bucket to a local temp dir, or degrade to the local store.

        Off by default: without ``PIPEGUARD_S3_LIVE`` armed (or with an unconfigured bucket)
        this delegates to the offline local store and opens no client and no socket. When armed,
        any failure still degrades to local — the gate can never break over an artifact fetch.
        """
        if not _s3_live_enabled() or self._bucket == _UNCONFIGURED_BUCKET:
            # PRIMARY GUARD: the remote pull is opt-in AND needs a configured bucket. Unarmed or
            # unconfigured, degrade to the offline local store — no client, no network. A
            # configured bucket + creds alone never pulls.
            return self._fallback.fetch(run_ref)

        # --- live-pull seam (reached only when PIPEGUARD_S3_LIVE is armed) -------------------
        try:
            client = self._get_client()  # lazy boto3 import + client construction
            return self._download_run(client, str(run_ref))
        except Exception:
            # ANY failure degrades to the offline local store — never break the gate over an
            # artifact fetch (absent boto3, missing/invalid creds, an API/transport error).
            # Nothing about the error (which may embed a key/URL) is logged.
            return self._fallback.fetch(run_ref)

    def _download_run(self, client: Any, run_ref: str) -> Path:
        """Download every object under ``s3://bucket/<prefix>/<run_ref>/`` into a fresh temp dir.

        Returns the temp dir for :func:`pipeguard.parsers.load_run` to read. If the prefix has no
        objects, the dir is empty — a signal the tolerant parser handles, not a crash.
        """
        key_prefix = f"{self._prefix}/{run_ref}/" if self._prefix else f"{run_ref}/"
        dest = Path(tempfile.mkdtemp(prefix="pipeguard-s3-"))
        response = client.list_objects_v2(Bucket=self._bucket, Prefix=key_prefix)
        for obj in response.get("Contents", []):
            key = obj["Key"]
            rel = key[len(key_prefix) :] if key.startswith(key_prefix) else Path(key).name
            # Skip the zero-byte "directory" placeholder keys an S3 console creates (…/).
            if not rel or rel.endswith("/"):
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(self._bucket, key, str(target))
        return dest
