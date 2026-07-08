"""Offline tests for the GIAB HG002 fetch script (T-013 GIAB half).

These pin the *pure* logic of ``scripts/fetch_giab_hg002.py`` — manifest parsing,
target-path construction, checksum verification, the ``--dry-run`` plan, and the
"tool/connectivity missing -> actionable error" paths — without ever hitting the
network or the genomics toolchain. The single network seam (``opener``) is
injected with an in-memory response, so ``main`` is driven end-to-end with zero
bytes on the wire. Runs under the app's ``uv`` env like the rest of the suite.
"""

from __future__ import annotations

import hashlib
import io
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from scripts.fetch_giab_hg002 import (
    DEFAULT_MANIFEST,
    ChecksumMismatchError,
    ConnectivityError,
    DownloadAction,
    FetchError,
    Manifest,
    ManifestError,
    MissingToolError,
    ReadsSliceAction,
    UrlOpener,
    VcfPanelRestrictAction,
    _default_opener,
    download,
    fetch_download_action,
    format_plan,
    load_manifest,
    main,
    parse_manifest,
    require_tool,
    resolve_actions,
    resolve_target_root,
    sha256_of,
    target_path,
    verify_checksum,
)

# A minimal but structurally faithful manifest for the pure-logic tests. Mirrors
# the shape of the committed scripts/giab_hg002_manifest.json.
_MANIFEST_JSON = """
{
  "origin": "real-giab",
  "reference": "GRCh38",
  "benchmark_release": "NISTv4.2.1",
  "target_subdir": "data/real-giab",
  "artifacts": [
    {"key": "truth_vcf", "kind": "truth-vcf", "download": true, "required": true,
     "url": "https://example.test/HG002.vcf.gz", "filename": "HG002.vcf.gz"},
    {"key": "truth_vcf_index", "kind": "truth-vcf-index", "download": true, "required": true,
     "url": "https://example.test/HG002.vcf.gz.tbi", "filename": "HG002.vcf.gz.tbi"},
    {"key": "high_conf_bed", "kind": "high-conf-bed", "download": true, "required": true,
     "url": "https://example.test/HG002.bed", "filename": "HG002.bed"},
    {"key": "reads_bam_source", "kind": "reads-bam-source", "download": false, "required": false,
     "url": "https://example.test/HG002.bam", "filename": "HG002.bam",
     "index_url": "https://example.test/HG002.bam.bai", "index_filename": "HG002.bam.bai",
     "index_md5": "0123456789abcdef0123456789abcdef"}
  ]
}
"""


def _manifest() -> Manifest:
    return parse_manifest(_MANIFEST_JSON)


def _make_opener(mapping: dict[str, bytes]) -> UrlOpener:
    """Build an injectable opener that serves fixed bytes per URL (no network)."""

    @contextmanager
    def opener(url: str) -> Iterator[io.BytesIO]:
        if url not in mapping:
            raise urllib.error.URLError(f"unmapped url {url}")
        yield io.BytesIO(mapping[url])

    return opener


# --------------------------------------------------------------------------- #
# Manifest parsing (tolerant contract)
# --------------------------------------------------------------------------- #
def test_parse_manifest_reads_all_fields() -> None:
    m = _manifest()
    assert m.origin == "real-giab"
    assert m.reference == "GRCh38"
    vcf = m.by_kind("truth-vcf")
    assert vcf is not None
    assert vcf.url.endswith("HG002.vcf.gz") and vcf.download is True and vcf.required is True
    reads = m.by_kind("reads-bam-source")
    assert reads is not None
    assert reads.download is False  # source-only: never downloaded whole
    assert reads.index_md5 == "0123456789abcdef0123456789abcdef"


def test_parse_manifest_tolerates_missing_optionals() -> None:
    """Absent optional fields degrade to None, not a crash (Data-handling rule 2)."""
    m = parse_manifest(
        '{"artifacts": [{"key": "k", "kind": "truth-vcf", "url": "https://x/y.vcf.gz",'
        ' "filename": "y.vcf.gz"}]}'
    )
    art = m.artifacts[0]
    assert art.md5 is None and art.sha256 is None and art.notes is None
    assert art.download is True and art.required is False  # documented defaults


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",  # root not an object
        '{"artifacts": []}',  # empty list
        '{"artifacts": [{"kind": "x", "url": "u", "filename": "f"}]}',  # missing key
        '{"artifacts": [{"key": "k", "url": "u", "filename": "f"}]}',  # missing kind
    ],
)
def test_parse_manifest_rejects_malformed(raw: str) -> None:
    with pytest.raises(ManifestError):
        parse_manifest(raw)


def test_load_committed_manifest_is_grounded_in_real_giab() -> None:
    """The committed manifest loads and carries the REAL GIAB accessions/md5s."""
    m = load_manifest(DEFAULT_MANIFEST)
    assert m.origin == "real-giab" and m.reference == "GRCh38"
    vcf = m.by_kind("truth-vcf")
    assert vcf is not None and "NISTv4.2.1/GRCh38" in vcf.url
    assert vcf.filename == "HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz"
    reads = m.by_kind("reads-bam-source")
    assert reads is not None and reads.download is False
    # Real md5s published by GIAB (HG002_corrected_md5sums.feb19upload.txt).
    assert reads.md5 == "56c30eaa4e2f25ff0ac80ef30e09d78e"
    assert reads.index_md5 == "a3c2b449df6509ca83fbd3fea22b9aee"


# --------------------------------------------------------------------------- #
# Path construction
# --------------------------------------------------------------------------- #
def test_target_path_uses_basename_only(tmp_path: Path) -> None:
    # Even a filename with path separators cannot escape the target root.
    assert target_path(tmp_path, "a/b/HG002.vcf.gz") == tmp_path / "HG002.vcf.gz"


def test_resolve_target_root_prefers_explicit(tmp_path: Path) -> None:
    m = _manifest()
    assert resolve_target_root(m, tmp_path) == tmp_path
    # Default derives from the repo root + manifest subdir.
    assert resolve_target_root(m, None).as_posix().endswith("data/real-giab")


# --------------------------------------------------------------------------- #
# Checksum verification
# --------------------------------------------------------------------------- #
def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def test_verify_checksum_unpinned_reports_computed(tmp_path: Path) -> None:
    f = _write(tmp_path / "f.bin", b"hello giab")
    result = verify_checksum(f, md5=None, sha256=None)
    assert result.unpinned is True and result.verified is False
    assert result.computed_sha256 == hashlib.sha256(b"hello giab").hexdigest()


def test_verify_checksum_pinned_sha256_ok(tmp_path: Path) -> None:
    data = b"payload"
    f = _write(tmp_path / "f.bin", data)
    good = hashlib.sha256(data).hexdigest()
    result = verify_checksum(f, md5=None, sha256=good)
    assert result.verified is True and result.unpinned is False


def test_verify_checksum_sha256_mismatch_raises(tmp_path: Path) -> None:
    f = _write(tmp_path / "f.bin", b"payload")
    with pytest.raises(ChecksumMismatchError, match="sha256 mismatch"):
        verify_checksum(f, md5=None, sha256="deadbeef")


def test_verify_checksum_pinned_md5_ok_and_mismatch(tmp_path: Path) -> None:
    data = b"reads"
    f = _write(tmp_path / "f.bin", data)
    good_md5 = hashlib.md5(data).hexdigest()
    assert verify_checksum(f, md5=good_md5, sha256=None).verified is True
    with pytest.raises(ChecksumMismatchError, match="md5 mismatch"):
        verify_checksum(f, md5="00000000000000000000000000000000", sha256=None)


# --------------------------------------------------------------------------- #
# Tool presence
# --------------------------------------------------------------------------- #
def test_require_tool_found() -> None:
    # `sh` exists on any POSIX runner; assert we get an absolute path back.
    assert Path(require_tool("sh")).is_absolute()


def test_require_tool_missing_is_actionable() -> None:
    with pytest.raises(MissingToolError, match="bioconda"):
        require_tool("definitely-not-a-real-tool-xyz")


# --------------------------------------------------------------------------- #
# Action resolution + dry-run plan
# --------------------------------------------------------------------------- #
def test_resolve_actions_default_downloads_three_truth_artifacts(tmp_path: Path) -> None:
    actions = resolve_actions(_manifest(), tmp_path, with_reads=False, panel_bed=None)
    assert all(isinstance(a, DownloadAction) for a in actions)
    keys = {a.key for a in actions if isinstance(a, DownloadAction)}
    assert keys == {"truth_vcf", "truth_vcf_index", "high_conf_bed"}
    # The 122G reads BAM source is never turned into a download action.
    urls = {a.url for a in actions if isinstance(a, DownloadAction)}
    assert not any(u.endswith(".bam") for u in urls)


def test_resolve_actions_panel_bed_adds_vcf_restriction(tmp_path: Path) -> None:
    actions = resolve_actions(_manifest(), tmp_path, with_reads=False, panel_bed=Path("p.bed"))
    restrict = [a for a in actions if isinstance(a, VcfPanelRestrictAction)]
    assert len(restrict) == 1
    assert restrict[0].dest.name.endswith(".panel.vcf.gz")


def test_resolve_actions_with_reads_needs_panel_bed(tmp_path: Path) -> None:
    with pytest.raises(FetchError, match="--with-reads requires --panel-bed"):
        resolve_actions(_manifest(), tmp_path, with_reads=True, panel_bed=None)


def test_resolve_actions_with_reads_slices_not_whole_download(tmp_path: Path) -> None:
    actions = resolve_actions(_manifest(), tmp_path, with_reads=True, panel_bed=Path("p.bed"))
    slices = [a for a in actions if isinstance(a, ReadsSliceAction)]
    assert len(slices) == 1
    slice_action = slices[0]
    assert slice_action.source_url.endswith("HG002.bam")
    assert slice_action.dest.name.endswith(".panel.bam")
    # No DownloadAction ever targets the whole BAM.
    assert not any(isinstance(a, DownloadAction) and a.url.endswith("HG002.bam") for a in actions)


def test_format_plan_is_readable_and_safe(tmp_path: Path) -> None:
    actions = resolve_actions(_manifest(), tmp_path, with_reads=True, panel_bed=Path("p.bed"))
    plan = format_plan(actions, tmp_path)
    assert "nothing is downloaded in --dry-run" in plan
    assert "https://example.test/HG002.vcf.gz" in plan
    assert "SKIP whole-genome download" in plan  # the reads-slice guarantee is visible


# --------------------------------------------------------------------------- #
# Download seam (injected opener; no network)
# --------------------------------------------------------------------------- #
def test_download_is_atomic_and_leaves_no_part(tmp_path: Path) -> None:
    dest = tmp_path / "sub" / "out.bin"
    download(
        "https://example.test/x", dest, opener=_make_opener({"https://example.test/x": b"DATA"})
    )
    assert dest.read_bytes() == b"DATA"
    assert not dest.with_name(dest.name + ".part").exists()


def test_fetch_download_action_downloads_and_verifies(tmp_path: Path) -> None:
    data = b"vcf-bytes"
    url = "https://example.test/HG002.vcf.gz"
    action = DownloadAction(
        key="truth_vcf",
        url=url,
        dest=tmp_path / "HG002.vcf.gz",
        md5=None,
        sha256=hashlib.sha256(data).hexdigest(),
        required=True,
    )
    fetch_download_action(action, opener=_make_opener({url: data}), force=False)
    assert action.dest.read_bytes() == data


def test_fetch_download_action_is_idempotent_skip(tmp_path: Path) -> None:
    """A pre-existing (unpinned) file is not re-downloaded: opener must not be called."""
    dest = tmp_path / "HG002.bed"
    dest.write_bytes(b"already here")

    def exploding_opener(url: str) -> object:
        raise AssertionError("opener called despite existing file")

    action = DownloadAction(
        key="high_conf_bed",
        url="https://example.test/HG002.bed",
        dest=dest,
        md5=None,
        sha256=None,
        required=True,
    )
    fetch_download_action(action, opener=exploding_opener, force=False)  # must not raise
    assert dest.read_bytes() == b"already here"


def test_fetch_download_action_rejects_bad_checksum(tmp_path: Path) -> None:
    url = "https://example.test/HG002.vcf.gz"
    action = DownloadAction(
        key="truth_vcf",
        url=url,
        dest=tmp_path / "HG002.vcf.gz",
        md5=None,
        sha256="deadbeef",
        required=True,
    )
    with pytest.raises(ChecksumMismatchError):
        fetch_download_action(action, opener=_make_opener({url: b"whatever"}), force=False)


# --------------------------------------------------------------------------- #
# Connectivity error mapping
# --------------------------------------------------------------------------- #
def test_default_opener_maps_urlerror_to_connectivity(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str) -> object:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(ConnectivityError, match="re-verify the accession"):  # noqa: SIM117
        with _default_opener("https://example.test/x"):
            pass


# --------------------------------------------------------------------------- #
# main() end-to-end (dry-run + a fully-mocked fetch)
# --------------------------------------------------------------------------- #
def test_main_dry_run_prints_plan_and_downloads_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["--target-dir", str(tmp_path), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PLAN — GIAB HG002 fetch" in out
    assert list(tmp_path.iterdir()) == []  # truly nothing written


def test_main_fetches_all_truth_artifacts_with_mock_opener(tmp_path: Path) -> None:
    m = load_manifest(DEFAULT_MANIFEST)
    mapping = {a.url: f"bytes-for-{a.key}".encode() for a in m.artifacts if a.download}
    rc = main(["--target-dir", str(tmp_path)], opener=_make_opener(mapping))
    assert rc == 0
    for art in m.artifacts:
        expected = tmp_path / art.filename
        assert expected.exists() == art.download  # only download:true land on disk
    # The whole BAM was never fetched.
    assert not (tmp_path / "HG002.GRCh38.2x250.bam").exists()


def test_main_returns_error_code_on_connectivity_failure(tmp_path: Path) -> None:
    def failing_opener(url: str) -> object:
        raise ConnectivityError("simulated offline")

    rc = main(["--target-dir", str(tmp_path)], opener=failing_opener)
    assert rc == 2  # handled FetchError -> nonzero exit, not a traceback


def test_committed_manifest_download_bytes_land_with_expected_names(tmp_path: Path) -> None:
    """Sanity: names on disk match the committed manifest (guards path drift)."""
    m = load_manifest(DEFAULT_MANIFEST)
    mapping = {a.url: b"x" for a in m.artifacts if a.download}
    main(["--target-dir", str(tmp_path)], opener=_make_opener(mapping))
    got = {p.name for p in tmp_path.iterdir()}
    assert got == {a.filename for a in m.artifacts if a.download}
    assert sha256_of(next(tmp_path.iterdir())) == hashlib.sha256(b"x").hexdigest()
