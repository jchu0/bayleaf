#!/usr/bin/env python3
"""Fetch a small, panel-scoped subset of the real GIAB HG002 benchmark (origin ``real-giab``).

Why this script exists
----------------------
PipeGuard validates its coverage/faithfulness gates against *real* truth data,
but raw reads and truth artifacts must never live in git (CLAUDE.md Data-handling
rule 1). So the reproducible record is committed as an accession *manifest*
(``scripts/giab_hg002_manifest.json``) plus this fetch script; the bytes land in a
git-ignored ``data/real-giab/`` and are re-fetchable on demand.

What it fetches (grounded in the NIST GIAB v4.2.1 release; see the manifest)
    1. ``truth-vcf``        — HG002 GRCh38 v4.2.1 small-variant truth calls (~149M).
    2. ``truth-vcf-index``  — the tabix ``.tbi`` for that VCF (~1.6M).
    3. ``high-conf-bed``    — the v4.2.1 high-confidence regions BED (~11M).
    4. ``reads`` (opt-in)   — a *panel-region slice* of the 2x250 Illumina BAM.
       The whole BAM is 122G and is NEVER downloaded: ``--with-reads`` streams
       only the reads overlapping ``--panel-bed`` via ``samtools``.

Toolchain split (CLAUDE.md coding standard 4)
    The truth-artifact downloads use only the Python stdlib (``urllib`` +
    ``hashlib``), so the core path runs anywhere with network. The optional
    ``--panel-bed`` restriction and ``--with-reads`` slice shell out to the
    genomics toolchain (``tabix``/``bcftools``/``samtools``), which is installed
    separately (bioconda/containers) and is not part of the app's ``uv`` env.
    Those steps fail loudly with an install hint if a tool is missing.

Design for testability
    All decision logic (manifest parse, target-path construction, checksum
    verify, the ``--dry-run`` plan, tool/connectivity errors) is pure and
    network-free; the one network seam (``opener``) is injectable so
    ``tests/test_fetch_giab.py`` exercises the happy path with an in-memory
    response and never touches the wire.

This is a research/demo QC substrate, not a clinical pipeline: the truth data
grounds faithfulness checks, it makes no diagnostic claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

LOG = logging.getLogger("fetch_giab_hg002")

# Default manifest ships next to this script; the target dir is a git-ignored
# sibling of the repo's other run bundles so it never risks being committed.
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
DEFAULT_MANIFEST = _SCRIPT_DIR / "giab_hg002_manifest.json"

# Streaming download chunk. 1 MiB keeps memory flat on the ~149M truth VCF.
_CHUNK = 1024 * 1024


# --------------------------------------------------------------------------- #
# Errors — every one carries an operator-actionable message (fail loudly).
# --------------------------------------------------------------------------- #
class FetchError(RuntimeError):
    """Base for all fetch failures; message is meant to be shown to the user."""


class MissingToolError(FetchError):
    """A required external CLI (samtools/tabix/bcftools/...) is not on PATH."""


class ConnectivityError(FetchError):
    """A URL could not be reached (offline, DNS, or a moved/renamed accession)."""


class ChecksumMismatchError(FetchError):
    """A downloaded file's checksum did not match the pinned value in the manifest."""


class ManifestError(FetchError):
    """The manifest is missing or malformed."""


# --------------------------------------------------------------------------- #
# Network seam — a single injectable opener so tests never hit the wire.
# --------------------------------------------------------------------------- #
class Readable(Protocol):
    """Minimal read surface shared by ``HTTPResponse`` and ``io.BytesIO`` (for tests)."""

    def read(self, amt: int = ..., /) -> bytes: ...


# An opener maps a URL to a context manager yielding a byte stream. The default
# uses urllib; tests pass a fake that yields an in-memory buffer.
UrlOpener = Callable[[str], AbstractContextManager[Readable]]


@contextmanager
def _default_opener(url: str) -> Iterator[Readable]:
    """Open ``url`` for streaming reads via urllib, normalizing failures.

    Any transport-level failure is re-raised as :class:`ConnectivityError` with a
    hint, because the most common causes here are being offline or an accession
    that GIAB has moved/renamed — both of which the operator can act on.
    """
    try:
        with urllib.request.urlopen(url) as response:
            yield response
    except (urllib.error.URLError, OSError) as exc:
        raise ConnectivityError(
            f"Could not reach {url!r}: {exc}. "
            "Check your network connection, or re-verify the accession against the "
            "GIAB FTP (paths in scripts/giab_hg002_manifest.json can change between releases)."
        ) from exc


# --------------------------------------------------------------------------- #
# Manifest model (tolerant parse — a missing field is a signal, not a crash).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Artifact:
    """One fetchable (or slice-source) entry from the manifest."""

    key: str
    kind: str
    url: str
    filename: str
    required: bool
    download: bool
    md5: str | None = None
    sha256: str | None = None
    index_url: str | None = None
    index_filename: str | None = None
    index_md5: str | None = None
    approx_size: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class Manifest:
    """The committed, reproducible record of exactly what a fetch pulls."""

    origin: str
    reference: str
    benchmark_release: str
    target_subdir: str
    artifacts: list[Artifact] = field(default_factory=list)

    def by_kind(self, kind: str) -> Artifact | None:
        """First artifact of ``kind``, or ``None`` (kinds are unique in practice)."""
        return next((a for a in self.artifacts if a.kind == kind), None)


def _req_str(obj: dict[str, object], key: str, ctx: str) -> str:
    """Read a required string field, failing with a located, actionable message."""
    val = obj.get(key)
    if not isinstance(val, str) or not val:
        raise ManifestError(f"{ctx}: missing/empty required string field {key!r}")
    return val


def _opt_str(obj: dict[str, object], key: str) -> str | None:
    """Read an optional string field; anything non-string (incl. JSON null) -> None."""
    val = obj.get(key)
    return val if isinstance(val, str) else None


def _opt_bool(obj: dict[str, object], key: str, default: bool) -> bool:
    """Read an optional bool field, tolerating absence."""
    val = obj.get(key)
    return val if isinstance(val, bool) else default


def parse_manifest(raw: str) -> Manifest:
    """Parse manifest JSON text into a :class:`Manifest`.

    Tolerant by contract (CLAUDE.md Data-handling rule 2): only the fields the
    fetch actually depends on are required; the rest degrade to ``None``.
    """
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise ManifestError("manifest root must be a JSON object")

    entries = doc.get("artifacts")
    if not isinstance(entries, list) or not entries:
        raise ManifestError("manifest has no 'artifacts' list")

    artifacts: list[Artifact] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ManifestError(f"artifacts[{i}] is not an object")
        ctx = f"artifacts[{i}]"
        artifacts.append(
            Artifact(
                key=_req_str(entry, "key", ctx),
                kind=_req_str(entry, "kind", ctx),
                url=_req_str(entry, "url", ctx),
                filename=_req_str(entry, "filename", ctx),
                required=_opt_bool(entry, "required", default=False),
                download=_opt_bool(entry, "download", default=True),
                md5=_opt_str(entry, "md5"),
                sha256=_opt_str(entry, "sha256"),
                index_url=_opt_str(entry, "index_url"),
                index_filename=_opt_str(entry, "index_filename"),
                index_md5=_opt_str(entry, "index_md5"),
                approx_size=_opt_str(entry, "approx_size"),
                notes=_opt_str(entry, "notes"),
            )
        )

    return Manifest(
        origin=_opt_str(doc, "origin") or "real-giab",
        reference=_opt_str(doc, "reference") or "unknown",
        benchmark_release=_opt_str(doc, "benchmark_release") or "unknown",
        target_subdir=_opt_str(doc, "target_subdir") or "data/real-giab",
        artifacts=artifacts,
    )


def load_manifest(path: Path) -> Manifest:
    """Load and parse the manifest at ``path``."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
    return parse_manifest(raw)


# --------------------------------------------------------------------------- #
# Pure helpers — paths + checksums (unit-tested without network).
# --------------------------------------------------------------------------- #
def target_path(target_root: Path, filename: str) -> Path:
    """Where ``filename`` lands under the git-ignored target root.

    The basename is taken from the manifest (never from the URL) so a moved
    accession can't redirect a write outside ``target_root``. A degenerate
    basename (``.``/``..``/empty) is rejected rather than collapsing ``dest`` to
    ``target_root`` itself.
    """
    name = Path(filename).name
    # Reject empty (`.`/trailing-slash → "") and `..`, which would resolve to the parent
    # of target_root — a `Path(filename).name` of ".." is non-empty but still escapes.
    if name in ("", ".", ".."):
        raise ManifestError(f"artifact filename {filename!r} has no usable basename")
    return target_root / name


def _hash_file(path: Path, algo: str) -> str:
    """Stream ``path`` through ``algo`` (md5/sha256) and return the hex digest."""
    h = hashlib.new(algo)
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def sha256_of(path: Path) -> str:
    """Hex SHA-256 of a file (streamed)."""
    return _hash_file(path, "sha256")


def md5_of(path: Path) -> str:
    """Hex MD5 of a file (streamed).

    MD5 is used only to cross-check GIAB's own published md5sums — it is an
    integrity check against a trusted publisher, not a security boundary.
    """
    return _hash_file(path, "md5")


@dataclass(frozen=True)
class ChecksumResult:
    """Outcome of verifying a file against whatever the manifest pinned."""

    verified: bool  # True iff at least one pinned checksum matched
    unpinned: bool  # True iff the manifest pinned nothing (integrity NOT enforced)
    computed_sha256: str


def verify_checksum(path: Path, *, md5: str | None, sha256: str | None) -> ChecksumResult:
    """Verify ``path`` against pinned ``md5``/``sha256``; raise on any mismatch.

    Contract:
        * A pinned value that mismatches -> :class:`ChecksumMismatchError` (loud).
        * Nothing pinned -> ``unpinned=True`` and the caller logs the computed
          sha256 so it can be pinned in the manifest for reproducible re-fetches
          (GIAB ships no checksums file for the v4.2.1 truth artifacts).
    Always computes sha256 so the result can report it for pinning.
    """
    computed_sha256 = sha256_of(path)
    pinned = False

    if sha256 is not None:
        pinned = True
        if computed_sha256.lower() != sha256.lower():
            raise ChecksumMismatchError(
                f"sha256 mismatch for {path.name}: expected {sha256}, got {computed_sha256}. "
                "Delete the file and re-fetch; if it persists, the accession may have changed."
            )
    if md5 is not None:
        pinned = True
        computed_md5 = md5_of(path)
        if computed_md5.lower() != md5.lower():
            raise ChecksumMismatchError(
                f"md5 mismatch for {path.name}: expected {md5}, got {computed_md5}. "
                "Delete the file and re-fetch; if it persists, the accession may have changed."
            )

    return ChecksumResult(verified=pinned, unpinned=not pinned, computed_sha256=computed_sha256)


def require_tool(name: str) -> str:
    """Return the resolved path to CLI ``name`` or raise an actionable error.

    The genomics tools live in the separate bioconda/container toolchain, so the
    hint points there rather than at pip/uv.
    """
    resolved = shutil.which(name)
    if resolved is None:
        raise MissingToolError(
            f"required tool {name!r} not found on PATH. "
            f"Install the genomics toolchain (e.g. `conda install -c bioconda {name}`) "
            "or run this step inside the project's genomics container; it is intentionally "
            "separate from the app's `uv` environment."
        )
    return resolved


# --------------------------------------------------------------------------- #
# Actions — a single resolved plan drives BOTH --dry-run printing and execution,
# so the two can never drift.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DownloadAction:
    """Download one artifact to ``dest`` and verify it against pinned checksums."""

    key: str
    url: str
    dest: Path
    md5: str | None
    sha256: str | None
    required: bool

    def describe(self) -> str:
        pin = "sha256" if self.sha256 else ("md5" if self.md5 else "unpinned (sha256 logged)")
        return f"DOWNLOAD {self.key}: {self.url}\n    -> {self.dest}  [checksum: {pin}]"


@dataclass(frozen=True)
class ReadsSliceAction:
    """Stream a panel-region slice of the remote BAM (whole BAM never downloaded)."""

    source_url: str
    index_url: str
    index_dest: Path
    index_md5: str | None
    panel_bed: Path
    dest: Path

    def describe(self) -> str:
        return (
            f"DOWNLOAD bam-index: {self.index_url}\n"
            f"    -> {self.index_dest}  [checksum: {'md5' if self.index_md5 else 'unpinned'}]\n"
            f"SLICE reads to panel: samtools view -b -M -L {self.panel_bed} "
            f"-X {self.source_url} {self.index_dest}\n"
            f"    -> {self.dest}  (SKIP whole-genome download; region-restricted subset only)"
        )


@dataclass(frozen=True)
class VcfPanelRestrictAction:
    """Restrict the downloaded truth VCF to the panel BED (a genuine panel subset)."""

    source_vcf: Path
    panel_bed: Path
    dest: Path

    def describe(self) -> str:
        return (
            f"RESTRICT truth VCF to panel: bcftools view -R {self.panel_bed} {self.source_vcf}\n"
            f"    -> {self.dest}  (panel-scoped truth subset)"
        )


Action = DownloadAction | ReadsSliceAction | VcfPanelRestrictAction


def resolve_actions(
    manifest: Manifest,
    target_root: Path,
    *,
    with_reads: bool,
    panel_bed: Path | None,
) -> list[Action]:
    """Compute the ordered action list from the manifest + flags (pure).

    Ordering matters: truth artifacts download first, then any panel restriction
    that consumes them. The reads slice is opt-in and never implies a whole-BAM
    download.
    """
    actions: list[Action] = []

    for art in manifest.artifacts:
        # Structural guard on the load-bearing safety rule (CLAUDE.md Data-handling 1):
        # the whole reads BAM (122G) is NEVER downloaded, only sliced. Refuse it here in
        # code — regardless of the manifest's `download` flag — so a manifest edit flipping
        # `download: true` on the reads source can't queue a whole-BAM pull.
        if art.kind == "reads-bam-source" or art.index_url is not None:
            continue
        if not art.download:
            continue  # optional/derived artifacts opt out of the plain download
        actions.append(
            DownloadAction(
                key=art.key,
                url=art.url,
                dest=target_path(target_root, art.filename),
                md5=art.md5,
                sha256=art.sha256,
                required=art.required,
            )
        )

    if panel_bed is not None:
        vcf = manifest.by_kind("truth-vcf")
        if vcf is not None:
            src = target_path(target_root, vcf.filename)
            actions.append(
                VcfPanelRestrictAction(
                    source_vcf=src,
                    panel_bed=panel_bed,
                    dest=src.with_suffix("").with_suffix(".panel.vcf.gz"),
                )
            )

    if with_reads:
        reads = manifest.by_kind("reads-bam-source")
        if reads is None or reads.index_url is None or reads.index_filename is None:
            raise ManifestError(
                "--with-reads requested but the manifest has no 'reads-bam-source' entry "
                "with an index_url/index_filename to slice from."
            )
        if panel_bed is None:
            raise FetchError(
                "--with-reads requires --panel-bed: reads are only ever fetched as a "
                "region-restricted slice, never as the whole 122G BAM."
            )
        index_dest = target_path(target_root, reads.index_filename)
        actions.append(
            ReadsSliceAction(
                source_url=reads.url,
                index_url=reads.index_url,
                index_dest=index_dest,
                index_md5=reads.index_md5,
                panel_bed=panel_bed,
                dest=target_root / "HG002.GRCh38.panel.bam",
            )
        )

    return actions


def format_plan(actions: Sequence[Action], target_root: Path) -> str:
    """Render the resolved actions as a human-readable, numbered dry-run plan."""
    lines = [
        f"PLAN — GIAB HG002 fetch (origin=real-giab) into {target_root}",
        f"  {len(actions)} step(s); nothing is downloaded in --dry-run:",
        "",
    ]
    for i, action in enumerate(actions, start=1):
        body = action.describe().replace("\n", "\n    ")
        lines.append(f"  {i}. {body}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Execution — network + genomics-tool steps (guarded; skipped by --dry-run).
# --------------------------------------------------------------------------- #
def download(url: str, dest: Path, *, opener: UrlOpener) -> None:
    """Stream ``url`` to ``dest`` atomically.

    Writes to a ``.part`` sibling and renames on success, so an interrupted
    download never leaves a truncated file that a later run would mistake for
    complete (idempotency correctness). ``opener`` is injected for testability.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    LOG.info("downloading %s -> %s", url, dest)
    with opener(url) as response, part.open("wb") as out:
        for block in iter(lambda: response.read(_CHUNK), b""):
            out.write(block)
    part.replace(dest)  # atomic on the same filesystem


def fetch_download_action(action: DownloadAction, *, opener: UrlOpener, force: bool) -> None:
    """Execute one :class:`DownloadAction`: idempotent skip, download, verify."""
    if action.dest.exists() and not force:
        # Idempotent: verify what's already there rather than re-pulling ~149M.
        result = verify_checksum(action.dest, md5=action.md5, sha256=action.sha256)
        if result.unpinned:
            LOG.info(
                "exists, skipping (unpinned) %s  sha256=%s",
                action.dest.name,
                result.computed_sha256,
            )
        else:
            LOG.info("exists, checksum OK, skipping %s", action.dest.name)
        return

    download(action.url, action.dest, opener=opener)
    result = verify_checksum(action.dest, md5=action.md5, sha256=action.sha256)
    if result.unpinned:
        # GIAB ships no checksums file for the truth artifacts: log the computed
        # digest so the operator can pin it in the manifest for future runs.
        LOG.warning(
            "%s downloaded but NOT integrity-checked (no checksum pinned). "
            "Pin sha256=%s in scripts/giab_hg002_manifest.json for reproducible re-fetch.",
            action.dest.name,
            result.computed_sha256,
        )
    else:
        LOG.info("verified %s against pinned checksum", action.dest.name)


def fetch_reads_slice(action: ReadsSliceAction, *, opener: UrlOpener, force: bool) -> None:
    """Download+verify the BAM index, then stream a panel-region slice via samtools."""
    samtools = require_tool("samtools")  # fail loudly before any download

    if not action.index_dest.exists() or force:
        download(action.index_url, action.index_dest, opener=opener)
    index_check = verify_checksum(action.index_dest, md5=action.index_md5, sha256=None)
    if index_check.unpinned:
        # Mirror the truth-artifact path: warn (don't fail) when the index has no pinned
        # md5, so a future manifest that drops the pin doesn't silently skip verification.
        LOG.warning(
            "bam index %s downloaded but NOT integrity-checked (no md5 pinned in the manifest).",
            action.index_dest.name,
        )
    else:
        LOG.info("bam index verified: %s", action.index_dest.name)

    # `-M -L <bed>` restricts to the panel regions; `-X ... <index_dest>` supplies the
    # locally-verified index so htslib streams only the overlapping blocks from the remote
    # BAM instead of re-fetching the index over the wire. The 122G BAM is never fully
    # transferred. NOTE: confirm the exact samtools flags on a toolchain machine
    # (samtools built with libcurl/remote support) — see scripts/README.md.
    cmd = [
        samtools, "view", "-b", "-M", "-L", str(action.panel_bed),
        "-X", "-o", str(action.dest), action.source_url, str(action.index_dest),
    ]  # fmt: skip
    LOG.info("slicing reads to panel: %s", " ".join(cmd))
    _run(cmd)
    _run([samtools, "index", str(action.dest)])
    LOG.info("wrote panel reads subset: %s", action.dest)


def restrict_vcf_to_panel(action: VcfPanelRestrictAction) -> None:
    """Restrict the downloaded truth VCF to the panel BED via bcftools."""
    bcftools = require_tool("bcftools")
    if not action.source_vcf.exists():
        raise FetchError(
            f"cannot restrict to panel: expected truth VCF at {action.source_vcf} "
            "(run without --dry-run so the download step runs first)."
        )
    cmd = [
        bcftools, "view", "-R", str(action.panel_bed),
        "-Oz", "-o", str(action.dest), str(action.source_vcf),
    ]  # fmt: skip
    LOG.info("restricting truth VCF to panel: %s", " ".join(cmd))
    _run(cmd)
    _run([require_tool("tabix"), "-p", "vcf", str(action.dest)])
    LOG.info("wrote panel truth subset: %s", action.dest)


def _run(cmd: list[str]) -> None:
    """Run a subprocess, converting a nonzero exit into an actionable FetchError."""
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        raise FetchError(f"command failed ({exc.returncode}): {' '.join(cmd)}") from exc


def execute(actions: Iterable[Action], *, opener: UrlOpener, force: bool) -> None:
    """Run each resolved action in order, dispatching on its type."""
    for action in actions:
        if isinstance(action, DownloadAction):
            fetch_download_action(action, opener=opener, force=force)
        elif isinstance(action, ReadsSliceAction):
            fetch_reads_slice(action, opener=opener, force=force)
        else:
            restrict_vcf_to_panel(action)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser (separated out so tests can introspect it)."""
    parser = argparse.ArgumentParser(
        prog="fetch_giab_hg002",
        description="Fetch a small, panel-scoped subset of the real GIAB HG002 benchmark.",
    )
    parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_MANIFEST,
        help="Path to the accession manifest JSON (default: alongside this script).",
    )  # fmt: skip
    parser.add_argument(
        "--target-dir", type=Path, default=None,
        help="Download destination (default: <repo>/<manifest target_subdir>; git-ignored).",
    )  # fmt: skip
    parser.add_argument(
        "--panel-bed", type=Path, default=None,
        help="Restrict truth VCF (and, with --with-reads, reads) to this panel BED.",
    )  # fmt: skip
    parser.add_argument(
        "--with-reads", action="store_true",
        help="Also stream a panel-region slice of the reads BAM (requires --panel-bed + samtools).",
    )  # fmt: skip
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the resolved plan and exit without downloading anything.",
    )  # fmt: skip
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download even if a destination file already exists.",
    )  # fmt: skip
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging.",
    )  # fmt: skip
    return parser


def resolve_target_root(manifest: Manifest, target_dir: Path | None) -> Path:
    """Pick the download root: explicit --target-dir wins, else repo/<target_subdir>."""
    if target_dir is not None:
        return target_dir
    return _REPO_ROOT / manifest.target_subdir


def main(argv: Sequence[str] | None = None, *, opener: UrlOpener = _default_opener) -> int:
    """Entry point. Returns a process exit code (0 ok, 2 on a handled FetchError).

    ``opener`` is injectable purely so tests can drive ``main`` end-to-end with an
    in-memory response; production always uses the urllib default.
    """
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if bool(args.verbose) else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        manifest = load_manifest(args.manifest)
        target_root = resolve_target_root(manifest, args.target_dir)
        actions = resolve_actions(
            manifest,
            target_root,
            with_reads=bool(args.with_reads),
            panel_bed=args.panel_bed,
        )

        if bool(args.dry_run):
            print(format_plan(actions, target_root))
            return 0

        LOG.info(
            "fetching GIAB %s %s (%s) into %s",
            manifest.reference,
            manifest.benchmark_release,
            manifest.origin,
            target_root,
        )
        execute(actions, opener=opener, force=bool(args.force))
        LOG.info("done. Remember: %s is git-ignored — never commit its contents.", target_root)
        return 0
    except FetchError as exc:
        LOG.error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
