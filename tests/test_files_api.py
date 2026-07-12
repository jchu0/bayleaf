"""GET /api/files — the sandboxed server-side file browser (off-gate, read-only).

Drives the router with a TestClient and pins its two hard boundaries: the **allowlist** (a root is a
configured key, never a raw path — an unknown key 404s) and the **traversal-hardening** (a ``..``
escape, an absolute path, or an escaping symlink is rejected AND provably cannot exfiltrate a file
outside the root). Plus the listing contract: kind inference (``.vcf.gz`` → ``vcf``), dirs-first
ordering, and a correct parent link on a nested subdir. The browse roots are redirected to a tmp
sandbox via ``PIPEGUARD_BROWSE_ROOTS`` (read per request) so the suite controls the layout and can
plant a secret OUTSIDE the root to prove no escape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

# A sentinel that must NEVER appear in any response — it lives in a file OUTSIDE the sandbox
# root, so seeing it would mean a traversal escaped the allowlist.
_SECRET = "TOP-SECRET-OUTSIDE-THE-ROOT"


def _make_sandbox(monkeypatch: Any, tmp_path: Path) -> Path:
    """Build a controlled sandbox root, point the allowlist at it, and plant a secret just outside.

    Layout::

        tmp_path/
          SECRET.txt              <- the out-of-root sentinel (must never be reachable)
          sandbox/                <- the allowlisted root, key "sandbox"
            reads/HG002_R1.fastq.gz
            reads/HG002_R2.fastq.gz
            reference/hg38.fasta
            calls/sample.vcf.gz
            panel.bed
            notes.txt

    Returns the sandbox root path.
    """
    (tmp_path / "SECRET.txt").write_text(_SECRET, encoding="utf-8")
    root = tmp_path / "sandbox"
    (root / "reads").mkdir(parents=True)
    (root / "reference").mkdir()
    (root / "calls").mkdir()
    (root / "reads" / "lane1").mkdir()  # a two-level nesting for the parent-link test
    (root / "reads" / "HG002_R1.fastq.gz").write_text("@r1\n", encoding="utf-8")
    (root / "reads" / "HG002_R2.fastq.gz").write_text("@r2\n", encoding="utf-8")
    (root / "reference" / "hg38.fasta").write_text(">chr1\n", encoding="utf-8")
    (root / "calls" / "sample.vcf.gz").write_text("##fileformat=VCFv4.2\n", encoding="utf-8")
    (root / "panel.bed").write_text("chr1\t0\t100\n", encoding="utf-8")
    (root / "notes.txt").write_text("hello", encoding="utf-8")
    monkeypatch.setenv("PIPEGUARD_BROWSE_ROOTS", f"sandbox={root}")
    return root


# ── (a) listing a root returns entries ──────────────────────────────────────────────────────────


def test_list_the_data_root_returns_entries() -> None:
    """The default allowlist ('data' → repo data/) lists real run directories, no env needed."""
    resp = client.get("/api/files", params={"root": "data"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["root"] == "data"
    assert body["path"] == ""  # the root itself
    assert body["parent"] is None  # nothing above the root
    names = {e["name"] for e in body["entries"]}
    assert "mock_run_01" in names  # a known committed run dir
    # Dirs sort before files: the first non-dir entry may not precede a dir.
    kinds = [e["is_dir"] for e in body["entries"]]
    assert kinds == sorted(kinds, reverse=True)  # all True (dirs) precede all False (files)


def test_list_a_sandbox_root_lists_dirs_first_then_name(monkeypatch: Any, tmp_path: Path) -> None:
    _make_sandbox(monkeypatch, tmp_path)
    resp = client.get("/api/files", params={"root": "sandbox"})
    assert resp.status_code == 200
    body = resp.json()
    names = [e["name"] for e in body["entries"]]
    # Directories (calls, reads, reference) first — alpha — then files (notes.txt, panel.bed).
    assert names == ["calls", "reads", "reference", "notes.txt", "panel.bed"]
    # A directory carries no size; a file does.
    by_name = {e["name"]: e for e in body["entries"]}
    assert by_name["reads"]["is_dir"] is True and by_name["reads"]["size"] is None
    assert by_name["panel.bed"]["is_dir"] is False and by_name["panel.bed"]["size"] > 0


# ── (b) traversal attempts are rejected AND provably do not escape ────────────────────────────────


def test_dotdot_traversal_is_rejected_and_does_not_escape(monkeypatch: Any, tmp_path: Path) -> None:
    _make_sandbox(monkeypatch, tmp_path)
    resp = client.get("/api/files", params={"root": "sandbox", "path": "../"})
    assert resp.status_code == 400
    assert _SECRET not in resp.text  # never reached the out-of-root file
    # A deeper, secret-targeting traversal is likewise a 400 and reveals nothing.
    resp2 = client.get("/api/files", params={"root": "sandbox", "path": "../SECRET.txt"})
    assert resp2.status_code == 400
    assert _SECRET not in resp2.text


def test_absolute_path_is_rejected_and_does_not_escape(monkeypatch: Any, tmp_path: Path) -> None:
    _make_sandbox(monkeypatch, tmp_path)
    secret_abs = tmp_path / "SECRET.txt"
    resp = client.get("/api/files", params={"root": "sandbox", "path": str(secret_abs)})
    assert resp.status_code == 400  # absolute path rejected before the filesystem is touched
    assert _SECRET not in resp.text


def test_symlink_escaping_the_root_is_forbidden(monkeypatch: Any, tmp_path: Path) -> None:
    """A symlink INSIDE the root that points OUT of it must 403 when browsed (resolve-within check).

    This is the case the pre-checks (``..`` / absolute) can't see — the path spelling is clean; only
    resolving the symlink reveals it escapes. The download-hardening idiom's ``resolve()`` is what
    catches it.
    """
    root = _make_sandbox(monkeypatch, tmp_path)
    escape = root / "escape_link"
    escape.symlink_to(tmp_path, target_is_directory=True)  # -> the sandbox's PARENT (out of root)
    resp = client.get("/api/files", params={"root": "sandbox", "path": "escape_link"})
    assert resp.status_code == 403
    assert _SECRET not in resp.text  # the parent (holding SECRET.txt) was never listed


# ── (c) unknown root → 404 ────────────────────────────────────────────────────────────────────────


def test_unknown_root_key_is_404(monkeypatch: Any, tmp_path: Path) -> None:
    _make_sandbox(monkeypatch, tmp_path)  # only "sandbox" is allowlisted
    resp = client.get("/api/files", params={"root": "etc"})
    assert resp.status_code == 404
    assert "unknown root" in resp.json()["detail"]


def test_missing_directory_is_404(monkeypatch: Any, tmp_path: Path) -> None:
    _make_sandbox(monkeypatch, tmp_path)
    resp = client.get("/api/files", params={"root": "sandbox", "path": "nope/missing"})
    assert resp.status_code == 404


# ── (d) kind inference ────────────────────────────────────────────────────────────────────────────


def test_kind_inference_across_extensions(monkeypatch: Any, tmp_path: Path) -> None:
    root = _make_sandbox(monkeypatch, tmp_path)
    # A .vcf.gz (double extension) → "vcf".
    calls = client.get("/api/files", params={"root": "sandbox", "path": "calls"}).json()
    vcf = next(e for e in calls["entries"] if e["name"] == "sample.vcf.gz")
    assert vcf["kind"] == "vcf"
    # fastq(.gz), reference fasta, and panel bed each infer their kind.
    reads = client.get("/api/files", params={"root": "sandbox", "path": "reads"}).json()
    assert all(e["kind"] == "fastq" for e in reads["entries"] if not e["is_dir"])
    ref = client.get("/api/files", params={"root": "sandbox", "path": "reference"}).json()
    assert next(e for e in ref["entries"] if e["name"] == "hg38.fasta")["kind"] == "reference_fasta"
    top_resp = client.get("/api/files", params={"root": "sandbox"})
    top = top_resp.json()
    by_name = {e["name"]: e for e in top["entries"]}
    assert by_name["panel.bed"]["kind"] == "panel_bed"
    # An unrecognized extension is an honest null, never a guess.
    assert by_name["notes.txt"]["kind"] is None
    # A directory never carries a kind.
    assert by_name["reads"]["kind"] is None
    # The response echoes only the allowlist KEY, never the root's absolute on-disk path.
    assert top["root"] == "sandbox"
    assert str(root) not in top_resp.text


# ── (e) a nested subdir returns the correct parent ────────────────────────────────────────────────


def test_nested_subdir_returns_correct_parent(monkeypatch: Any, tmp_path: Path) -> None:
    _make_sandbox(monkeypatch, tmp_path)
    # One level down: parent is the root ("").
    reads = client.get("/api/files", params={"root": "sandbox", "path": "reads"}).json()
    assert reads["path"] == "reads"
    assert reads["parent"] == ""  # up-link points at the root
    # Two levels down: parent is the intermediate dir.
    lane = client.get("/api/files", params={"root": "sandbox", "path": "reads/lane1"}).json()
    assert lane["path"] == "reads/lane1"
    assert lane["parent"] == "reads"
    # A trailing slash is tolerated and normalizes to the canonical rel path (same listing).
    trailing = client.get("/api/files", params={"root": "sandbox", "path": "reads/"}).json()
    assert trailing["path"] == "reads" and trailing["parent"] == ""
    # A LEADING slash is an absolute path → rejected (400), not silently normalized.
    assert client.get("/api/files", params={"root": "sandbox", "path": "/reads"}).status_code == 400


# ── auth: any authenticated actor (lowest role) may browse ────────────────────────────────────────


def test_viewer_role_may_browse(monkeypatch: Any, tmp_path: Path) -> None:
    """The lowest role (viewer) is enough — allowlisted browsing is read-only, but not anonymous."""
    _make_sandbox(monkeypatch, tmp_path)
    resp = client.get(
        "/api/files",
        params={"root": "sandbox"},
        headers={"X-PipeGuard-Actor": "reader", "X-PipeGuard-Role": "viewer"},
    )
    assert resp.status_code == 200
