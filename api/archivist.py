"""Advisory Archivist agent (#3) — the "librarian" over the data platform, OFF the gate.

Mirrors the QC-triage agent (ADR-0009/0012) and the feedback agent (`api/feedback_agent.py`):
stub-first ($0, offline, deterministic) with an opt-in Claude path that falls back to the stub on
ANY error. It reads across the api-layer projection the rules pipeline ignores — the already-decided
:class:`~bayleaf.models.DecisionCard`s plus the run's on-disk artifact pointers — and emits a
STRUCTURED, human-readable :class:`ArchiveDigest`: it indexes / rolls up / summarizes a released run
(or a cross-run set) and PROPOSES an organizational / archival action + a prepared export manifest.

It is ORGANIZATIONAL, never diagnostic. Per the design's hard boundaries
(``docs/design/data-platform-and-archivist.md`` §5.2 / Appendix A), this fulfils the ``ArchiveNote``
contract: `advisory` is pinned ``True`` and there is deliberately NO verdict/decision/confidence
field, so the agent is *structurally* unable to set, change, or restate a verdict (ADR-0001). It
sits off the deterministic critical path (never inside `run_gate`/`load_run`), never mutates the
ledger or any source record, and **proposes** organization — it never opens a payload, moves,
deletes, or relabels an artifact. A run's `origin` (`real-giab`/`synthetic`/`contrived`) is kept.

Scope (MVP slice of the Appendix): summarize/index the two surfaces from data already in hand. The
durable ArtifactRef registry, output-tree ingestion, and audit-grade (ledger-read) export manifest
are deferred (design §2.2 / Appendix B). This builds the smallest useful advisory core over a clean
seam: one ``digest(runs)`` method — one run → a per-run digest + manifest; many → a cross-run index.

Env: ``BAYLEAF_ARCHIVIST_AGENT`` = "stub" (default) | "claude"; ``BAYLEAF_ARCHIVIST_MODEL``
default ``claude-haiku-4-5-20251001`` — organizing is a cheap, low-stakes task, so the cheapest tier
(ADR-0012). PII posture (design §5.2.7 least-privilege): the deterministic index uses only the cards
+ artifact pointers (which carry NO intake identity — subject_id/tissue/submitted_by never reach
this agent), and the Claude path is sent ONLY de-identified aggregate counts, never a raw record.

Run out-of-band via ``python -m api.archivist`` (a read-only, on-demand librarian pass).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, computed_field

from bayleaf import EventLedger, load_run, run_gate
from bayleaf.identifiers import SCHEMA_VERSION, new_id, utc_now
from bayleaf.identifiers import content_hash as _content_hash
from bayleaf.models import DecisionCard
from bayleaf.provenance import EventType

# Public agent identity carried on every digest's `agent` field.
ARCHIVIST_AGENT = "archivist"

# Cheapest tier (ADR-0012): indexing/summarizing is organizational, not diagnostic.
_DEFAULT_ARCHIVIST_MODEL = "claude-haiku-4-5-20251001"

# Bump when the deterministic index/manifest shape or the stub's phrasing changes so cached digests
# stay traceable (mirrors TRIAGE_CORPUS_VERSION / the feedback assessment versioning discipline).
ARCHIVIST_DIGEST_VERSION = "1.0.0"

# Verdict display order — matches the API's run-summary/monitoring ordering so the rollup is stable.
_VERDICT_ORDER: tuple[str, ...] = ("proceed", "hold", "rerun", "escalate")

# Files that are provenance markers or index/byte-code sidecars, not archivable data artifacts.
_SKIP_NAMES = {"origin"}
_SKIP_SUFFIXES = {".pyc"}

# Only hash small artifacts inline — the librarian registers a *pointer*, never slurps a raw-reads
# file to compute a checksum (a missing hash is honest: "pointer registered, not yet hashed").
_HASH_CAP_BYTES = 32 * 1024 * 1024


def _classify_kind(name: str) -> str:
    """The archivist's own organizational taxonomy for an artifact (a librarian classification).

    Distinct from the API's pipeline-stage/role mapping: this is *how a librarian shelves it*
    (reads / alignment / variant / coverage / intake / qc / provenance / index / manifest / other),
    derived purely from the filename so no file is ever opened to classify it.
    """
    lower = name.lower()
    if lower.endswith((".fastq", ".fastq.gz", ".fq", ".fq.gz")):
        return "reads"
    if lower.endswith((".bam", ".cram")):
        return "alignment"
    if lower.endswith((".vcf", ".vcf.gz")):
        return "variant"
    if lower.endswith((".bai", ".tbi", ".csi")):
        return "index"
    if "mosdepth" in lower or lower.endswith(".bed.gz") or "coverage" in lower:
        return "coverage"
    if lower in {"samplesheet.csv", "sample_metadata.csv"}:
        return "intake"
    if lower in {"qc_metrics.csv", "demux_stats.csv"} or "fastp" in lower:
        return "qc"
    if lower.endswith(".log"):
        return "provenance"
    if lower.endswith(".sha256") or "manifest" in lower:
        return "manifest"
    return "other"


class ArtifactRef(BaseModel):
    """A NON-authoritative pointer to one on-disk artifact — a checksum + origin, never the payload.

    The archivist registers pointers to a disposable index/manifest; it never opens, moves, or
    deletes the file. `sha256` is ``None`` for an artifact too large to hash inline (honest gap,
    not a fabricated value). `origin` rides along so a consumer never mistakes a synthetic/contrived
    artifact for real data (CLAUDE.md data-handling); it is preserved verbatim, never relabeled.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    kind: str = Field(..., description="Librarian classification (see `_classify_kind`)")
    sha256: str | None = Field(None, description="Content hash; None if unhashed (too large)")
    size_bytes: int = 0
    origin: str = "unknown"


class RunArchiveInput(BaseModel):
    """The structured, already-decided view of ONE run the archivist organizes.

    Assembled by the caller from the api-layer projection (the `_evaluate` cards + the run's
    artifact listing), so the archivist never runs the gate, opens a payload, or reaches into the
    ledger. It deliberately carries NO intake-identity fields (subject_id/tissue/submitted_by): the
    librarian organizes decisions + artifact pointers, so operator/subject PII is structurally
    absent from anything it can index or egress (design §5.2.7 least-privilege).
    """

    run_id: str
    status: str = "unknown"  # running | needs_review | released (run LIFECYCLE, not a verdict)
    run_date: str | None = None
    platform: str | None = None
    origin: str = "unknown"
    cards: list[DecisionCard] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)


class ArchiveSignature(BaseModel):
    """One recurring issue signature across the covered runs, ranked by count (an index entry)."""

    signature: str
    rule_id: str
    title: str
    gate: str
    count: int


class ArchiveCitation(BaseModel):
    """One traceable reference behind a digest — the exact run / signature the summary covers.

    Keeps the digest grounded (design §5.2.8): every organizational claim traces to a real run id
    or a real finding signature, so the librarian can only summarize what exists, never fabricate.
    """

    model_config = ConfigDict(frozen=True)

    source_kind: Literal["run", "signature", "artifact"]
    ref: str
    title: str | None = None


class ArchiveDigest(BaseModel):
    """The Archivist's ADVISORY organizational digest / index (the ``ArchiveNote`` contract, §5.2).

    Fulfils the design's hard boundary structurally: `advisory` is pinned ``True`` and there is
    deliberately NO verdict/decision/confidence field — the librarian organizes, the rules decide
    (ADR-0001). All organizational fields are DETERMINISTIC (computed from the cards + artifact
    pointers); only `summary` prose is refined by the optional Claude path. `archive_ready` restates
    each run's already-decided LIFECYCLE state (`released`) — an organizational readiness flag,
    never a new decision and never fed back to the gate.
    """

    id: str = Field(default_factory=lambda: new_id("digest"))
    advisory: Literal[True] = True
    agent: str = ARCHIVIST_AGENT
    generated_by: str = Field("stub", description="'stub' or 'claude' — provenance of the summary")
    model: str | None = Field(
        None, description="LLM id when generated_by='claude'; None for the deterministic stub"
    )
    scope: Literal["run", "index"] = "index"
    run_ids: list[str] = Field(default_factory=list, description="The run(s) this digest covers")
    n_runs: int = 0
    n_samples: int = 0
    n_attention: int = 0
    verdict_counts: dict[str, int] = Field(default_factory=dict)
    by_origin: dict[str, int] = Field(default_factory=dict, description="Runs by origin label")
    by_status: dict[str, int] = Field(default_factory=dict, description="Runs by lifecycle status")
    n_archive_ready: int = Field(
        0, description="Runs in the 'released' lifecycle state (organizationally archivable)"
    )
    archive_ready: bool = Field(
        False, description="All covered runs are 'released' (readiness label, not a verdict)"
    )
    n_artifacts: int = 0
    total_size_bytes: int = 0
    recurring_signatures: list[ArchiveSignature] = Field(default_factory=list)
    manifest: list[ArtifactRef] = Field(
        default_factory=list, description="Prepared export manifest (pointers only; nothing moves)"
    )
    proposed_action: str = Field("", description="Deterministic organizational/archival proposal")
    summary: str = Field("", description="Human-readable digest — the ONLY LLM-refined field")
    citations: list[ArchiveCitation] = Field(default_factory=list)
    disclaimer: str = (
        "Advisory organizational/archival index — not a QC verdict, not calibrated, not clinical. "
        "Nothing here moves, deletes, relabels, or re-decides a run."
    )
    digest_version: str = ARCHIVIST_DIGEST_VERSION
    schema_version: int = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=utc_now)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        """Stable identity over the digest payload (excludes id/created_at)."""
        return _content_hash(
            {
                "advisory": self.advisory,
                "agent": self.agent,
                "generated_by": self.generated_by,
                "model": self.model,
                "scope": self.scope,
                "run_ids": self.run_ids,
                "verdict_counts": self.verdict_counts,
                "by_origin": self.by_origin,
                "by_status": self.by_status,
                "n_archive_ready": self.n_archive_ready,
                "archive_ready": self.archive_ready,
                "n_artifacts": self.n_artifacts,
                "total_size_bytes": self.total_size_bytes,
                "recurring_signatures": [s.model_dump() for s in self.recurring_signatures],
                "manifest": [a.model_dump() for a in self.manifest],
                "proposed_action": self.proposed_action,
                "summary": self.summary,
                "digest_version": self.digest_version,
            }
        )


def _human_size(n: int) -> str:
    """Compact human-readable byte size for the prose summary."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _recurring_signatures(cards: list[DecisionCard], limit: int = 6) -> list[ArchiveSignature]:
    """Rank finding signatures across the covered cards (the issue index), most-frequent first."""
    counter: Counter[str] = Counter()
    meta: dict[str, tuple[str, str, str]] = {}
    for card in cards:
        for f in card.findings:
            counter[f.signature] += 1
            # First-seen wins for the label; the signature is the stable, rule-version-independent
            # recurrence key.
            meta.setdefault(f.signature, (f.rule_id, f.title, f.gate.value))
    out: list[ArchiveSignature] = []
    for sig, count in counter.most_common(limit):
        rule_id, title, gate = meta[sig]
        out.append(
            ArchiveSignature(signature=sig, rule_id=rule_id, title=title, gate=gate, count=count)
        )
    return out


def _date_range(runs: list[RunArchiveInput]) -> str | None:
    """The [min..max] run-date span across the covered runs, or a single date, else None."""
    dates = sorted(r.run_date for r in runs if r.run_date)
    if not dates:
        return None
    return dates[0] if dates[0] == dates[-1] else f"{dates[0]}..{dates[-1]}"


def _proposed_action(
    *, scope: str, runs: list[RunArchiveInput], n_archive_ready: int, n_attention: int
) -> str:
    """Deterministic ORGANIZATIONAL proposal — archival prep only, never a QC recommendation.

    Anchored strictly on each run's already-decided lifecycle status, so the archivist reflects an
    existing organizational state; it never derives a new decision from the verdicts.
    """
    if not runs:
        return "No runs to archive."
    if scope == "run":
        run = runs[0]
        n_art = len(run.artifacts)
        if run.status == "released":
            return (
                f"Run is released with no samples pending review — organizationally ready to "
                f"archive its {n_art} artifact(s) (origin {run.origin}). The prepared manifest "
                f"indexes them; no file is moved, deleted, or relabeled."
            )
        if run.status == "needs_review":
            return (
                f"Run has {n_attention} sample(s) still pending review — hold from archival until "
                f"reviewed; the prepared manifest indexes its {n_art} artifact(s) for when it is "
                f"released."
            )
        return "Run is still executing — not yet archivable; re-run the digest once it completes."
    n_running = sum(1 for r in runs if r.status == "running")
    n_pending = sum(1 for r in runs if r.status == "needs_review")
    return (
        f"Indexed {len(runs)} run(s): {n_archive_ready} released and archive-ready, {n_pending} "
        f"pending review, {n_running} still running. Released runs are organizationally ready to "
        f"archive; review the pending runs before archival. No file is moved or relabeled."
    )


def _summary_prose(
    *,
    scope: str,
    runs: list[RunArchiveInput],
    verdict_counts: dict[str, int],
    by_origin: dict[str, int],
    by_status: dict[str, int],
    n_samples: int,
    n_attention: int,
    n_artifacts: int,
    total_size_bytes: int,
    n_archive_ready: int,
    signatures: list[ArchiveSignature],
) -> str:
    """The deterministic human-readable digest (the stub's prose; Claude refines only this)."""
    if not runs:
        return "No runs to archive."
    verdicts = ", ".join(f"{v}={verdict_counts[v]}" for v in _VERDICT_ORDER if verdict_counts[v])
    # A clean run (or index) can have no recurring signatures; index [0] must stay guarded,
    # not evaluated eagerly — a released run with 0 attention otherwise 500s the digest.
    sig_note = (
        f" Top recurring signature: {signatures[0].title} ({signatures[0].count}x)."
        if signatures
        else ""
    )
    if scope == "run":
        run = runs[0]
        when = f", {run.run_date}" if run.run_date else ""
        ready = (
            "Organizationally ready to archive."
            if run.status == "released"
            else f"Hold from archival: {n_attention} sample(s) pending review."
            if run.status == "needs_review"
            else "Still running — not yet archivable."
        )
        return (
            f"Run {run.run_id} — origin {run.origin}, status {run.status}{when}. "
            f"{n_samples} sample(s): {verdicts or 'none'}; {n_attention} need review. "
            f"{n_artifacts} artifact(s), {_human_size(total_size_bytes)}. {ready}{sig_note}"
        )
    span = _date_range(runs)
    when = f" spanning {span}" if span else ""
    origins = ", ".join(f"{o}={n}" for o, n in sorted(by_origin.items()))
    statuses = ", ".join(f"{s}={n}" for s, n in sorted(by_status.items()))
    return (
        f"Indexed {len(runs)} run(s){when}: {n_samples} sample(s), {n_attention} need review. "
        f"By origin: {origins}. By status: {statuses}. "
        f"{n_archive_ready} released and archive-ready.{sig_note}"
    )


def _build_digest(
    runs: list[RunArchiveInput], *, generated_by: str, model: str | None
) -> ArchiveDigest:
    """Assemble the fully DETERMINISTIC digest — the single source of every organizational number.

    Shared by the stub (as-is) and the Claude path (as its grounded base before prose refinement),
    so the citations, manifest, counts, and proposal are identical regardless of the summary author.
    """
    scope: Literal["run", "index"] = "run" if len(runs) == 1 else "index"
    all_cards = [c for r in runs for c in r.cards]
    n_samples = len(all_cards)
    n_attention = sum(1 for c in all_cards if c.is_actionable)
    verdict_counts = dict.fromkeys(_VERDICT_ORDER, 0)
    for c in all_cards:
        verdict_counts[c.verdict.value] = verdict_counts.get(c.verdict.value, 0) + 1
    by_origin = dict(Counter(r.origin for r in runs))
    by_status = dict(Counter(r.status for r in runs))
    n_archive_ready = sum(1 for r in runs if r.status == "released")
    n_artifacts = sum(len(r.artifacts) for r in runs)
    total_size_bytes = sum(a.size_bytes for r in runs for a in r.artifacts)
    signatures = _recurring_signatures(all_cards)

    # Manifest only for a single-run digest — a cross-run index is a bounded rollup, not a
    # per-artifact export (design keeps the ArtifactRef registry target-state).
    manifest = list(runs[0].artifacts) if scope == "run" else []

    citations: list[ArchiveCitation] = [
        ArchiveCitation(source_kind="run", ref=r.run_id, title=f"{r.status} · {r.origin}")
        for r in runs
    ]
    citations.extend(
        ArchiveCitation(source_kind="signature", ref=s.signature, title=f"{s.title} ({s.count}x)")
        for s in signatures
    )

    proposed_action = _proposed_action(
        scope=scope, runs=runs, n_archive_ready=n_archive_ready, n_attention=n_attention
    )
    summary = _summary_prose(
        scope=scope,
        runs=runs,
        verdict_counts=verdict_counts,
        by_origin=by_origin,
        by_status=by_status,
        n_samples=n_samples,
        n_attention=n_attention,
        n_artifacts=n_artifacts,
        total_size_bytes=total_size_bytes,
        n_archive_ready=n_archive_ready,
        signatures=signatures,
    )
    return ArchiveDigest(
        generated_by=generated_by,
        model=model,
        scope=scope,
        run_ids=[r.run_id for r in runs],
        n_runs=len(runs),
        n_samples=n_samples,
        n_attention=n_attention,
        verdict_counts=verdict_counts,
        by_origin=by_origin,
        by_status=by_status,
        n_archive_ready=n_archive_ready,
        archive_ready=bool(runs) and n_archive_ready == len(runs),
        n_artifacts=n_artifacts,
        total_size_bytes=total_size_bytes,
        recurring_signatures=signatures,
        manifest=manifest,
        proposed_action=proposed_action,
        summary=summary,
        citations=citations,
    )


class ArchivistAgent(Protocol):
    """Turns a set of already-decided runs into an advisory ArchiveDigest (an organizational
    index)."""

    name: str

    def digest(self, runs: list[RunArchiveInput]) -> ArchiveDigest: ...


class StubArchivist:
    """Deterministic, zero-cost librarian — the default AND the fallback.

    Produces the full index + manifest + digest prose from the structured run data, with no API
    call, so the whole capability runs offline. It doubles as the fallback the live
    `ClaudeArchivist` degrades to on any error.
    """

    name = "stub"

    def digest(self, runs: list[RunArchiveInput]) -> ArchiveDigest:
        return _build_digest(runs, generated_by=self.name, model=None)


# JSON schema for the SUMMARY PROSE only. Every organizational number, the manifest, and the
# citations are not the model's to author, so they are deliberately absent here (mirrors the triage
# advice schema): the model phrases, the deterministic base grounds.
_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are a data librarian / archivist for an internal genomics QC decision-gate tool. You are "
    "given an ANONYMOUS, AGGREGATED organizational rollup of ALREADY-DECIDED runs (counts by "
    "verdict / origin / lifecycle-status, artifact counts, and recurring issue signatures — no raw "
    "sample identities, no patient data). Write a SHORT, plain, human-readable summary to help a "
    "lab operator ORGANIZE and ARCHIVE these runs.\n\n"
    "Rules you must follow:\n"
    "- This is ORGANIZATIONAL / archival only. You must NOT set, change, restate, or imply a QC "
    "verdict, a confidence, or any pass/fail decision — those are fixed elsewhere.\n"
    "- Ground every statement in the provided counts; do not invent runs, samples, metric values, "
    "IDs, thresholds, or artifacts.\n"
    "- Preserve each run's origin label exactly as given; never relabel a synthetic or contrived "
    "run as real.\n"
    "- Make no diagnostic, therapeutic, or pathogenicity claims.\n"
    "- Use conservative, hedged language; be concise, no preamble."
)


class ClaudeArchivist:
    """Opt-in live librarian — OFF by default. The deterministic index/manifest/citations stay
    (grounding); Claude is asked ONLY to re-phrase the `summary`, and is sent ONLY the de-identified
    aggregate rollup (never a raw card, id, or intake field). Any API error / refusal / empty
    response falls back to the stub, so flipping it on can never break the advisory path.
    """

    name = "claude"

    def __init__(self, model: str | None = None, max_tokens: int = 512) -> None:
        self.model = model or os.environ.get("BAYLEAF_ARCHIVIST_MODEL", _DEFAULT_ARCHIVIST_MODEL)
        self.max_tokens = max_tokens
        self._fallback = StubArchivist()
        self._client: Any = None  # anthropic client, created lazily on first use

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic  # lazy: package works (and tests/install run) without anthropic

            # Best-effort local .env load (python-dotenv ships with the [claude] extra; plain
            # environment variables still work without it).
            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:
                pass
            self._client = anthropic.Anthropic()  # resolves credentials from env
        return self._client

    def digest(self, runs: list[RunArchiveInput]) -> ArchiveDigest:
        # Compute the deterministic base FIRST so the manifest/citations/counts survive even if the
        # model output is discarded (grounding). Nothing to summarize for an empty set → base.
        base = self._fallback.digest(runs)
        if not runs:
            return base
        try:
            # PII-safe payload: only the aggregate counts + the signature labels — never a raw card,
            # an artifact path, or an intake field (none of which the input even carries).
            payload = {
                "scope": base.scope,
                "run_ids": base.run_ids,
                "n_runs": base.n_runs,
                "n_samples": base.n_samples,
                "n_attention": base.n_attention,
                "verdict_counts": base.verdict_counts,
                "by_origin": base.by_origin,
                "by_status": base.by_status,
                "n_archive_ready": base.n_archive_ready,
                "date_range": _date_range(runs),
                "recurring_signatures": [
                    {"title": s.title, "gate": s.gate, "count": s.count}
                    for s in base.recurring_signatures
                ],
                "proposed_action": base.proposed_action,
            }
            client = self._get_client()
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM,
                messages=[{"role": "user", "content": json.dumps(payload, indent=2)}],
                output_config={"format": {"type": "json_schema", "schema": _SUMMARY_SCHEMA}},
            )
            # Guard the refusal path before reading content (life-sciences work can trip safety
            # classifiers; fall back rather than break the demo).
            if response.stop_reason == "refusal":
                return base
            text = next((b.text for b in response.content if b.type == "text"), None)
            if not text:
                return base
            summary = json.loads(text).get("summary") or base.summary
            return base.model_copy(
                update={"generated_by": self.name, "model": self.model, "summary": summary}
            )
        except Exception:
            return base  # never let a live-API problem break the advisory path


def get_archivist_agent() -> ArchivistAgent:
    """Select the archivist agent from the environment (default: the zero-cost stub)."""
    choice = os.environ.get("BAYLEAF_ARCHIVIST_AGENT", "stub").strip().lower()
    if choice == "claude":
        return ClaudeArchivist()
    return StubArchivist()


def archive_digest(
    runs: list[RunArchiveInput], agent: ArchivistAgent | None = None
) -> ArchiveDigest:
    """Advisory organizational digest / index over a set of already-decided runs (mirrors
    `triage_card` / `assess_feedback`): picks the env-selected agent unless one is injected. The
    digest never sets or overrides a verdict (ADR-0001).
    """
    return (agent or get_archivist_agent()).digest(runs)


# --- Convenience: build the archivist's input from a run directory (CLI + tests) --------------
# The API endpoint builds `RunArchiveInput` from the in-memory `_evaluate` cards + the artifacts
# listing (no re-run); this helper is the self-contained path for the out-of-band CLI and the tests.


def _read_origin(run_dir: Path) -> str:
    """The run's origin label from its single-line `origin` marker; default `unknown`."""
    marker = run_dir / "origin"
    if marker.exists():
        text = marker.read_text(encoding="utf-8").strip()
        if text:
            return text
    return "unknown"


def _sha256_of(path: Path) -> str | None:
    """Streamed content hash; None above the cap so a raw-reads file is never slurped into RAM."""
    if path.stat().st_size > _HASH_CAP_BYTES:
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan_artifacts(run_dir: Path, origin: str) -> list[ArtifactRef]:
    """Register a pointer + checksum for each data artifact in the run dir (never opens the payload
    for anything but hashing a small file; large files are pointer-only with `sha256=None`)."""
    refs: list[ArtifactRef] = []
    for p in sorted(run_dir.iterdir()):
        if not p.is_file() or p.name in _SKIP_NAMES or p.suffix in _SKIP_SUFFIXES:
            continue
        refs.append(
            ArtifactRef(
                name=p.name,
                kind=_classify_kind(p.name),
                sha256=_sha256_of(p),
                size_bytes=p.stat().st_size,
                origin=origin,
            )
        )
    return refs


def build_run_input_from_dir(run_dir: str | Path, run_id: str | None = None) -> RunArchiveInput:
    """Assemble a `RunArchiveInput` from a run directory (off-gate, read-only).

    Re-derives the cards via the deterministic gate and registers artifact pointers. Used by the CLI
    and the offline tests; the API endpoint should pass its cached `_evaluate` cards instead of
    re-running the gate here.
    """
    path = Path(run_dir)
    rid = run_id or path.name
    ledger = EventLedger()
    artifacts = load_run(path, run_id=rid)
    cards = run_gate(artifacts, ledger=ledger)
    n_attention = sum(1 for c in cards if c.is_actionable)
    # Honest lifecycle status from the event trail (mirrors the API's `_run_status`): a run is
    # 'running' until its ANALYSIS_RUN_COMPLETED event lands, so a still-executing clean run is
    # never mislabeled 'released'.
    completed = any(e.event_type is EventType.ANALYSIS_RUN_COMPLETED for e in ledger.events)
    status = "running" if not completed else ("needs_review" if n_attention else "released")
    origin = _read_origin(path)
    return RunArchiveInput(
        run_id=rid,
        status=status,
        run_date=artifacts.run_date,
        platform=artifacts.platform,
        origin=origin,
        cards=cards,
        artifacts=_scan_artifacts(path, origin),
    )


def main(argv: list[str] | None = None) -> int:
    """Read one or more run dirs + print the advisory digest (out-of-band; no HTTP surface)."""
    parser = argparse.ArgumentParser(
        prog="python -m api.archivist",
        description="Advisory organizational digest / index over already-decided runs (off-gate).",
    )
    parser.add_argument(
        "run_dirs", nargs="+", help="One or more run directories (e.g. data/mock_run_01)."
    )
    parser.add_argument("--json", action="store_true", help="emit the full digest as JSON.")
    args = parser.parse_args(argv)

    runs = [build_run_input_from_dir(d) for d in args.run_dirs]
    digest = archive_digest(runs)
    if args.json:
        print(digest.model_dump_json(indent=2))
        return 0
    print(f"Archive digest ({digest.generated_by}) — scope={digest.scope}, {digest.n_runs} run(s)")
    print(f"  {digest.summary}")
    print(f"  proposal    : {digest.proposed_action}")
    print(f"  verdicts    : {digest.verdict_counts}")
    print(f"  by origin   : {digest.by_origin}")
    print(f"  by status   : {digest.by_status}")
    if digest.recurring_signatures:
        print("  signatures  :")
        for s in digest.recurring_signatures:
            print(f"    - {s.title} [{s.gate}] ({s.count}x)")
    if digest.manifest:
        print(f"  manifest    : {len(digest.manifest)} artifact(s)")
    print(f"  ({digest.disclaimer})")
    return 0


# Static type check: both agents satisfy the ArchivistAgent protocol.
_STUB: ArchivistAgent = StubArchivist()
_CLAUDE: ArchivistAgent = ClaudeArchivist()


if __name__ == "__main__":
    raise SystemExit(main())
