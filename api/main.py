"""FastAPI read-API over the pipeguard core — the production seam (ADR-0010).

Framework boundary: this wraps `pipeguard`; the core has no FastAPI import (CLAUDE.md
architecture guardrail 1). The React frontend consumes these endpoints.

Read-only over the DECISION domain: no endpoint mutates a verdict, finding, provenance
event, or the EventLedger, and rules still decide (ADR-0001). The one write is
`POST /api/feedback` — append-only PRODUCT TELEMETRY that is OFF the deterministic gate
(`api/feedback.py`): it records operator reactions/notes to a separate, gitignored JSONL,
never calls `run_gate`, never touches provenance, and can never set or influence a verdict.
Other off-gate PRODUCT writes now live in dedicated auth-gated routers (`api/routers/`): the
Pipeline save/approve lifecycle, Settings/config-authoring drafts, and Review-queue tickets —
each append-only, RBAC-gated (`api/auth.py`), and equally incapable of touching a verdict.

Run:  uv run uvicorn api.main:app --reload --port 8010
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from pipeguard import DEFAULT_RUNBOOK, EventLedger, load_run, run_gate, triage_card
from pipeguard.metrics import default_registry
from pipeguard.models import DecisionCard, Gate, Sample, Verdict
from pipeguard.pipeline_repair import RepairProposal, propose_repair, recurring_signature
from pipeguard.provenance import EntityRef, EventType, ProvenanceEvent
from pipeguard.runbook import RouteToHumanPolicy, Runbook
from pipeguard.triage import TriageNote

from .archivist import ArchiveDigest, ArtifactRef, RunArchiveInput, _classify_kind, archive_digest
from .auth import Actor, require_role
from .card_readout import router as card_readout_router
from .deid import IDENTITY_FIELDS, DeidPolicy, default_policy, export_fields, redact
from .feedback import FEEDBACK_SCHEMA_VERSION, FeedbackAck, FeedbackIn
from .feedback_store import get_feedback_store
from .pipeline import PipelineGraph, PipelineGraphAck, PipelineGraphIn
from .pipeline_store import get_pipeline_store
from .routers.intake import router as intake_router
from .routers.nextflow import router as nextflow_router
from .routers.node_author import router as node_author_router
from .routers.pipeline_run import router as pipeline_run_router
from .routers.pipelines_lifecycle import router as pipelines_lifecycle_router
from .routers.review_queue import router as review_router
from .routers.settings import router as settings_router
from .safe_harbor import HIPAA_SAFE_HARBOR_CLASSES, SAFE_HARBOR_POLICY_ID, redact_record
from .share_store import get_share_store

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="PipeGuard API", version="0.1.0")

# The React dev server (Vite) runs on 5173; allow it in dev. GET for the read-API + exactly
# one write verb (POST) for the off-gate feedback telemetry — no PUT/DELETE/PATCH. Origins
# stay pinned to the two dev hosts (not "*"); tightening them is the production-seam knob.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    # The run-list keeps its JSON body a plain list (backward-compat) and carries pagination
    # metadata on headers; a browser fetch can only read those cross-origin if they're exposed.
    expose_headers=[
        "X-PipeGuard-Total-Count",
        "X-PipeGuard-Page",
        "X-PipeGuard-Limit",
        "X-PipeGuard-Status-Counts",
        # Review-queue total (resolved count while only a recent window is loaded) — a browser fetch
        # can only read it cross-origin if it's exposed (same reason as the run-list headers above).
        "X-PipeGuard-Ticket-Total",
    ],
)

# Additive product-domain surfaces, each its own auth-gated router OFF the deterministic gate
# (ADR-0001): Settings/config authoring drafts, the Review-queue/ticket domain, the Pipeline
# approve/dry-run/diff lifecycle, and the per-card QC-readout projection. They live in
# api/routers/ (+ api/card_readout.py) so feature areas evolve independently of this file; none
# mutates a verdict, finding, provenance event, or the ledger.
app.include_router(settings_router)
app.include_router(review_router)
app.include_router(pipelines_lifecycle_router)
app.include_router(card_readout_router)
app.include_router(intake_router)
app.include_router(nextflow_router)
app.include_router(pipeline_run_router)
app.include_router(node_author_router)


class RunSummary(BaseModel):
    """The run-overview row: per-run verdict counts, attention flag, and lifecycle state.

    `platform`/`run_date` come from the sample sheet's [Header] block (Illumina v2);
    both are optional because a sheet may omit them, and `run_date` is the raw ISO
    string, never a fabricated datetime. `status` is a run-LIFECYCLE label derived
    honestly from provenance (see `_run_status`) — NOT a per-sample verdict.
    """

    run_id: str
    n_samples: int
    n_attention: int
    counts: dict[str, int]
    platform: str | None = None
    run_date: str | None = None
    status: str  # "running" | "needs_review" | "released"


class RunDetail(BaseModel):
    """A run's full payload: summary + decision cards + the provenance trail."""

    run_id: str
    summary: RunSummary
    cards: list[DecisionCard]
    events: list[ProvenanceEvent]


class RunArtifact(BaseModel):
    """One data artifact in a run's lineage, mapped to a pipeline stage (the provenance
    canvas's data-I/O drill-in, §5).

    `sha256` + `size_bytes` are read from the actual file on disk; `origin` carries the run's
    provenance tag so a consumer never mistakes a contrived/synthetic artifact for real
    (CLAUDE.md data-handling). Large raw reads (BAM/VCF) are size-listed but not hashed
    (`sha256` is null) so the endpoint never slurps a multi-GB file to compute a hash.
    """

    name: str
    stage: str  # intake | demux | qc | align | variant | gate
    role: str  # "input" | "output"
    sha256: str | None
    size_bytes: int
    origin: str
    url: str  # same-origin download link (GET /api/runs/{id}/artifacts/{name}); read-only


# Life-science guardrail (CLAUDE.md, "Runbook thresholds are illustrative/configurable, not
# clinical thresholds"): surfaced verbatim in the runbook response so an integrator can never
# mistake the gate policy for a validated clinical cutoff.
_RUNBOOK_DISCLAIMER = (
    "Illustrative / operator-configurable QC thresholds — NOT clinical thresholds. "
    "These gate values are demo policy, not calibrated or validated clinical cutoffs."
)

# Make the units contract explicit at the API boundary so an integrator never renders a
# canonical 0.85 fraction as "0.85%": gate/hard_fail are in canonical units, `unit` is display.
_RUNBOOK_UNITS_NOTE = (
    "gate/hard_fail are in each metric's canonical unit (fraction for %-unit metrics, x for "
    "coverage); 'unit' is the display symbol — multiply %-unit gates by 100 to display them."
)


class RunbookThreshold(BaseModel):
    """One QC gate's policy, flattened for operators/integrators (the settings screen).

    `gate`/`hard_fail` are the numeric threshold VALUES in the metric's canonical unit
    (fractions for rates, x for coverage — the same scale the rules gate on); `unit` is the
    display symbol. `direction` reports the comparison sense so an integrator reads a one-sided
    gate correctly. `pipeline_gate` is the metric's PIPELINE gate (preflight|qc|variant), from
    the registry — distinct from the numeric `gate` value, so a consumer can group policy by gate
    without conflating the two (the old shape only carried the value, forcing the frontend to
    mistype it as the gate).
    """

    metric: str
    our_key: str
    label: str
    gate: float
    hard_fail: float
    unit: str
    direction: str  # "higher_is_better" | "lower_is_better"
    pipeline_gate: Gate  # preflight | qc | variant — the metric's gate (registry), not the value


class RunbookPolicy(BaseModel):
    """The active runbook's gate policy: QC thresholds + required intake metadata.

    `disclaimer` is load-bearing, not decoration: the thresholds are illustrative and
    configurable, never clinical cutoffs (CLAUDE.md life-science guardrail 3).
    """

    disclaimer: str
    units_note: str
    run_id_field: str
    required_metadata_fields: list[str]
    thresholds: list[RunbookThreshold]


def _run_dir(run_id: str) -> Path:
    run_dir = DATA_ROOT / run_id
    if not (run_dir / "SampleSheet.csv").exists():
        raise HTTPException(status_code=404, detail=f"Unknown run '{run_id}'")
    return run_dir


def _run_ids() -> list[str]:
    if not DATA_ROOT.exists():
        return []
    return sorted(
        p.name for p in DATA_ROOT.iterdir() if p.is_dir() and (p / "SampleSheet.csv").exists()
    )


def _run_status(*, completed: bool, n_attention: int) -> str:
    """Derive a run's LIFECYCLE label from provenance + the attention count.

    This is a run-lifecycle status, NOT a per-sample verdict (ADR-0001, rules decide):
    a run is 'running' until its ANALYSIS_RUN_COMPLETED event lands, so a still-executing
    run with zero flags is never mislabeled 'released' (the bug this fixes). Once the gate
    completes it is 'needs_review' if any sample is actionable, else 'released'. Kept a pure
    function of (completed, n_attention) so the tri-state is unit-testable without a ledger.
    """
    if not completed:
        return "running"
    return "needs_review" if n_attention > 0 else "released"


def _active_runbook(run_id: str) -> Runbook:
    """The runbook the gate uses for THIS run — the stock DEFAULT_RUNBOOK unless the run dir carries
    a `route_to_human` marker (comma-separated ClinVar significances) that arms VAR-RTH-001 for it.

    Route-to-human is off by default in the core (ADR-0018 D2); this is the deployment-config seam
    that arms it, scoped PER RUN via a marker so a single contrived fixture can demonstrate the
    human-review escalation while every real/other run stays disarmed. Empty/absent → disarmed.
    """
    marker = _run_dir(run_id) / "route_to_human"
    if not marker.exists():
        return DEFAULT_RUNBOOK
    sigs = tuple(s.strip() for s in marker.read_text(encoding="utf-8").split(",") if s.strip())
    if not sigs:
        return DEFAULT_RUNBOOK
    policy = RouteToHumanPolicy(significances=sigs)
    return DEFAULT_RUNBOOK.model_copy(update={"route_to_human": policy})


@lru_cache(maxsize=32)
def _evaluate(run_id: str) -> RunDetail:
    """Run the gate once per run (cached); captures cards + the event trail."""
    ledger = EventLedger()
    artifacts = load_run(_run_dir(run_id))
    cards = run_gate(artifacts, runbook=_active_runbook(run_id), ledger=ledger)
    counts = Counter(c.verdict.value for c in cards)
    n_attention = sum(1 for c in cards if c.is_actionable)
    # Honest lifecycle state from the authoritative event trail (ADR-0002): a run counts as
    # finished only once its ANALYSIS_RUN_COMPLETED event is on the ledger — not inferred from
    # a zero attention count, which conflates "still running" with "released clean".
    completed = any(e.event_type is EventType.ANALYSIS_RUN_COMPLETED for e in ledger.events)
    summary = RunSummary(
        run_id=run_id,
        n_samples=len(cards),
        n_attention=n_attention,
        counts={v: counts.get(v, 0) for v in ("proceed", "hold", "rerun", "escalate")},
        platform=artifacts.platform,
        run_date=artifacts.run_date,
        status=_run_status(completed=completed, n_attention=n_attention),
    )
    return RunDetail(run_id=run_id, summary=summary, cards=cards, events=ledger.events)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/feedback", status_code=201)
def submit_feedback(body: FeedbackIn) -> FeedbackAck:
    """Record in-app feedback — the app's only write, and it is OFF the deterministic gate.

    Product telemetry (ADR-0001): this appends an operator reaction/note to a separate,
    gitignored JSONL and returns an ack. It NEVER calls `run_gate`, touches the EventLedger
    or SQLite projection, or mutates a verdict/finding/card. The client cannot set the
    server-authored fields (`FeedbackIn` is `extra="forbid"`); `origin` is resolved
    server-side via `_run_origin` (the trust anchor), never trusted from the request.
    """
    ctx = body.context
    feedback_id = uuid.uuid4().hex  # stdlib uuid on purpose — no coupling to the core's ids
    received_at = datetime.now(timezone.utc).isoformat()
    record: dict[str, Any] = {
        **body.model_dump(),
        "id": feedback_id,
        "schema_version": FEEDBACK_SCHEMA_VERSION,
        "received_at": received_at,
        "app_version": app.version,
        "origin": _run_origin(ctx.run_id) if ctx.run_id else "unknown",
    }
    try:
        # The sink is env-selected (JSONL / SQLite / Postgres) and degrades to JSONL if a DB is
        # misconfigured; a write that still fails (disk full, DB down mid-flight) maps to a
        # generic 503 — never leaking the path, DSN, or the message body.
        get_feedback_store().append(record)
    except Exception:
        raise HTTPException(status_code=503, detail="feedback store unavailable") from None
    return FeedbackAck(
        id=feedback_id, received_at=received_at, schema_version=FEEDBACK_SCHEMA_VERSION
    )


# --- Pipeline Builder save/version (ADR-0014): PRODUCT state, OFF the deterministic gate ------
# A saved builder graph is product state, NOT a decision: these three endpoints never call
# `run_gate`, touch the EventLedger/projection, or set a verdict (ADR-0001). The graph payload is
# a tolerant, versioned envelope (`api/pipeline.py`) stored as-is via a pluggable, env-selected
# sink (`api/pipeline_store.py`) — distinct from the decision Repository port. Additive: no
# existing endpoint's response changes.


@app.post("/api/pipelines", status_code=201)
def save_pipeline(
    body: PipelineGraphIn,
    actor: Actor = Depends(require_role("reviewer", "approver")),
) -> PipelineGraphAck:
    """Save a Pipeline Builder graph under a name — a PRODUCT write, OFF the deterministic gate.

    Mints a server-authored `id` + `created_at`; the store authors the monotonic per-name
    `version` (max existing + 1) atomically under its write lock, so re-saving a name yields
    2, 3, …. The client cannot set the server-authored fields (`PipelineGraphIn` is
    `extra="forbid"`), and the `graph` payload is stored AS-IS — never validated node-by-node
    or fed to a rule/verdict. A write that fails (disk full, DB down mid-flight) maps to a
    generic 503 — never leaking the path, DSN, or the payload (mirrors POST /api/feedback).
    """
    pipeline_id = uuid.uuid4().hex  # stdlib uuid on purpose — no coupling to the core's ids
    created_at = datetime.now(timezone.utc).isoformat()
    # Everything but `version`, which the store authors atomically under its lock. A save mints a
    # `draft`; the reviewer/approver fields are reserved-null now (server-authored once auth lands,
    # never client-set — the draft→save→approve flow the builder-versioning decision reserves).
    record: dict[str, Any] = {
        **body.model_dump(),
        "id": pipeline_id,
        "created_at": created_at,
        "status": "draft",
        "submitted_by": actor.id,
        "reviewed_by": None,
        "approved_by": None,
    }
    try:
        stored = get_pipeline_store().append(record)
    except Exception:
        raise HTTPException(status_code=503, detail="pipeline store unavailable") from None
    return PipelineGraphAck(
        id=stored["id"],
        name=stored["name"],
        version=stored["version"],
        schema_version=stored["schema_version"],
        created_at=stored["created_at"],
        status=stored["status"],
    )


@app.get("/api/pipelines")
def list_pipelines() -> list[PipelineGraph]:
    """The saved-pipeline catalog: the LATEST version of each distinct name, sorted by name.

    Read-only over product state (never the decision domain). The store keeps every revision;
    collapsing to the latest per name is a presentation concern kept in the API layer (CLAUDE.md
    architecture guardrail 1) so the catalog shows each pipeline once — use
    `GET /api/pipelines/{name}` for a name's full version history.
    """
    try:
        records = get_pipeline_store().list()
    except Exception:
        raise HTTPException(status_code=503, detail="pipeline store unavailable") from None
    latest: dict[str, dict[str, Any]] = {}
    for r in records:
        name = str(r["name"])
        if name not in latest or int(r["version"]) > int(latest[name]["version"]):
            latest[name] = r
    return [PipelineGraph.model_validate(latest[name]) for name in sorted(latest)]


@app.get("/api/pipelines/{name}")
def get_pipeline_versions(name: str) -> list[PipelineGraph]:
    """One pipeline's full version history, ascending by `version` (the save/version timeline).

    Read-only over product state. 404 if the name has no saved revisions (mirrors the run
    endpoints' unknown-id 404). The store-read is wrapped so a backend failure maps to a
    generic 503 without leaking the path/DSN; the 404 is raised outside that guard so it is
    never masked as a 503.
    """
    try:
        records = get_pipeline_store().get_versions(name)
    except Exception:
        raise HTTPException(status_code=503, detail="pipeline store unavailable") from None
    if not records:
        raise HTTPException(status_code=404, detail=f"Unknown pipeline '{name}'")
    return [PipelineGraph.model_validate(r) for r in records]


# --- Run-list filtering / ordering / paging (the run-overview + monitoring screens) ----------
# Presentation concerns kept in the API layer, never the framework-agnostic core (CLAUDE.md
# architecture guardrail 1): the core emits runs; sorting/paging shape them for a screen.


def _run_order_key(summary: RunSummary) -> tuple[str, str]:
    """Chronological sort key for a run: its [Header] date when present, else the run_id as a
    stable fallback (per the schema, run_date is a real ISO date or None, never empty). run_id
    is the tiebreaker so same-date runs (e.g. two 2026-07-08 runs) keep a deterministic order.
    """
    return (summary.run_date or summary.run_id, summary.run_id)


# Closed `sort` vocabulary → (key, reverse). Mirrors the export endpoint's closed-enum + 400
# idiom for `verdict`: an unknown token is a 400, never a silent fallback to the default order.
_RUN_SORTS: dict[str, tuple[Callable[[RunSummary], Any], bool]] = {
    "run_id": (lambda s: s.run_id, False),
    "-run_id": (lambda s: s.run_id, True),
    "run_date": (_run_order_key, False),
    "-run_date": (_run_order_key, True),
    "n_samples": (lambda s: s.n_samples, False),
    "-n_samples": (lambda s: s.n_samples, True),
    "n_attention": (lambda s: s.n_attention, False),
    "-n_attention": (lambda s: s.n_attention, True),
}

# Friendly sort aliases the design UI uses ("recent"/"urgent"/"date") mapped onto the canonical
# vocabulary above, so the frontend can bind its labels without knowing the -field spelling.
_RUN_SORT_ALIASES = {"recent": "-run_date", "urgent": "-n_attention", "date": "run_date"}

# The run-lifecycle vocabulary `status` filters on (mirrors RunSummary.status / _run_status).
_RUN_STATUSES = frozenset({"running", "needs_review", "released"})


@app.get("/api/runs")
def list_runs(
    response: Response,
    verdict: str | None = None,
    status: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    page: int = Query(1, ge=1),
    limit: int | None = Query(None, ge=1),
) -> list[RunSummary]:
    """All discoverable runs with their verdict counts (the run-overview + monitoring screens).

    Backward-compatible: with NO params the JSON body is byte-identical to before — every run
    in run_id order, unpaginated. Optional filters: `verdict` keeps runs with ≥1 sample of that
    verdict (unknown → 400); `status` filters on the run-lifecycle label
    (running|needs_review|released, unknown → 400); `q` is a case-insensitive substring match on
    run_id OR platform (the design's "search run id or platform" box). `sort` is a closed
    vocabulary ({run_id,run_date,n_samples,n_attention}, each with a `-` desc variant) plus the
    friendly aliases recent/urgent/date; unknown → 400. Pagination applies ONLY when `limit` is
    given (`page` is 1-based); the pre-pagination total + the per-status facet counts + the active
    page/limit ride response headers so the body stays a plain list.
    """
    if verdict is not None and verdict not in _VERDICT_ORDER:
        raise HTTPException(status_code=400, detail=f"verdict must be one of {_VERDICT_ORDER}")
    if status is not None and status not in _RUN_STATUSES:
        allowed = sorted(_RUN_STATUSES)
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    if sort is not None:
        sort = _RUN_SORT_ALIASES.get(sort, sort)  # normalize the design's friendly tokens
        if sort not in _RUN_SORTS:
            aliases = sorted(_RUN_SORTS) + sorted(_RUN_SORT_ALIASES)
            raise HTTPException(status_code=400, detail=f"sort must be one of {aliases}")

    summaries = [_evaluate(rid).summary for rid in _run_ids()]
    # Per-status facet counts over the FULL set (before any filter) so the UI's All/Needs
    # review/Sequencing/Released chips can show totals independent of the active filter + page.
    facets = Counter(s.status for s in summaries)
    response.headers["X-PipeGuard-Status-Counts"] = json.dumps(
        {st: facets.get(st, 0) for st in sorted(_RUN_STATUSES)}
    )

    if q is not None:
        ql = q.lower()  # case-insensitive so "novaseq" matches a "NovaSeq" platform
        summaries = [
            s
            for s in summaries
            if ql in s.run_id.lower() or (s.platform is not None and ql in s.platform.lower())
        ]
    if verdict is not None:
        # A run "has" a verdict when at least one of its samples landed there.
        summaries = [s for s in summaries if s.counts.get(verdict, 0) > 0]
    if status is not None:
        summaries = [s for s in summaries if s.status == status]
    if sort is not None:
        key, reverse = _RUN_SORTS[sort]
        summaries = sorted(summaries, key=key, reverse=reverse)

    # Total is the filtered count BEFORE the page slice, so a client can size its pager.
    response.headers["X-PipeGuard-Total-Count"] = str(len(summaries))
    if limit is not None:
        start = (page - 1) * limit
        summaries = summaries[start : start + limit]
        response.headers["X-PipeGuard-Page"] = str(page)
        response.headers["X-PipeGuard-Limit"] = str(limit)
    return summaries


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> RunDetail:
    """One run: summary + every decision card + the full provenance trail.

    The gate events come from the cached, deterministic `_evaluate`; the append-only
    `DATA_EXPORTED` share events (ADR-0018 D3) are merged in live from the pluggable share store
    so a just-recorded egress shows in the trail without invalidating the gate cache. Merged by
    `created_at`, so the share (always newer) lands after the run's decision events.
    """
    base = _evaluate(run_id)
    shares = get_share_store().for_run(run_id)
    if not shares:
        return base
    merged = sorted([*base.events, *shares], key=lambda e: e.created_at)
    return base.model_copy(update={"events": merged})


@app.get("/api/runs/{run_id}/cards/{sample_id}")
def get_card(run_id: str, sample_id: str) -> DecisionCard:
    """One sample's decision card (verdict, evidence, gate results)."""
    card = next((c for c in _evaluate(run_id).cards if c.sample_id == sample_id), None)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Unknown sample '{sample_id}'")
    return card


@app.get("/api/runs/{run_id}/cards/{sample_id}/triage")
def get_card_triage(run_id: str, sample_id: str) -> TriageNote:
    """Advisory QC-triage note for a flagged sample (ADR-0009); 404 if clean/unknown.

    Read-only and OFF the deterministic critical path (ADR-0001): the note suggests a
    likely cause + next action and cites the corpus, but never sets a verdict. Uses the
    offline stub agent by default (set PIPEGUARD_TRIAGE_AGENT=claude to go live).
    """
    card = next((c for c in _evaluate(run_id).cards if c.sample_id == sample_id), None)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Unknown sample '{sample_id}'")
    note = triage_card(card)
    if note is None:
        raise HTTPException(
            status_code=404, detail=f"Sample '{sample_id}' is clean; no triage note"
        )
    return note


# --- Provenance data-I/O (the §5 canvas drill-in) --------------------------------------------

# Never read a raw-reads artifact (BAM/VCF, potentially GB) into memory just to hash it: above
# this cap, `sha256` is null and only the on-disk size is reported.
_HASH_MAX_BYTES = 8 * 1024 * 1024

# Filename → (pipeline stage, I/O role). The small committed metadata artifacts map explicitly;
# raw-read extensions fall through to the suffix rules below so a future real-reads run still
# lands each file on the right stage instead of vanishing.
# A file can sit on more than one edge — one stage's OUTPUT is often the next stage's INPUT — so
# each name maps to a LIST of (stage, role) pairs. That is what gives QC a real input edge: the
# demultiplexed result (demux_stats / reads) is demux's output AND the data QC operates on, the
# same bytes on two edges (no file fabricated). Without it the QC node rendered orphaned ("how are
# there no inputs for QC?"). qc_metrics.csv stays QC's OUTPUT — it is the flattened QC report, not
# an input.
_ARTIFACT_STAGE: dict[str, list[tuple[str, str]]] = {
    # SampleSheet is the barcode manifest demux consumes — the preflight (demux) gate compares
    # it against demux_stats for index integrity — so it lands on demux, not intake.
    "sample_metadata.csv": [("intake", "input")],
    "samplesheet.csv": [("demux", "input")],
    "demux_stats.csv": [("demux", "output"), ("qc", "input")],
    "qc_metrics.csv": [("qc", "output")],
    "pipeline.log": [("gate", "input")],
    # Post-variant lineage seams (W3). No committed fixture emits these, so the downstream
    # provenance stages honestly read "not run in this build" — but when a build DOES publish a
    # route-to-human routing record or a de-identified share manifest, it lands on the right stage
    # instead of vanishing (the route_to_human ARMING marker stays config, never a data artifact).
    "route_to_human.json": [("review", "output")],
    "share_manifest.json": [("share", "output")],
}
_SKIP_ARTIFACTS = {"origin"}  # provenance marker, not a data artifact
_SKIP_SUFFIXES = {".bai", ".tbi", ".csi", ".pyc"}  # index/sidecar files


def _artifact_stage_roles(name: str) -> list[tuple[str, str]]:
    lower = name.lower()
    if lower in _ARTIFACT_STAGE:
        return _ARTIFACT_STAGE[lower]
    if lower.endswith((".bam", ".cram")):
        return [("align", "output")]
    # A filtered/normalized VCF is the OUTPUT of the post-call filter stage (W3) — matched before
    # the generic .vcf rule so it lands on 'filter', not 'variant' (the raw-caller output).
    if lower.endswith((".filtered.vcf", ".filtered.vcf.gz", ".norm.vcf", ".norm.vcf.gz")):
        return [("filter", "output")]
    if lower.endswith((".vcf", ".vcf.gz")):
        return [("variant", "output")]
    if lower.endswith((".fastq", ".fastq.gz", ".fq", ".fq.gz")):
        # Reads are demux's output and the QC stage's real input (the two-edge case).
        return [("demux", "output"), ("qc", "input")]
    return []


def _sha256_of(path: Path) -> str | None:
    """Streamed content hash for the integrity column; None above the size cap so we never
    slurp a raw-reads file into memory."""
    if path.stat().st_size > _HASH_MAX_BYTES:
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@app.get("/api/runs/{run_id}/artifacts")
def list_run_artifacts(run_id: str) -> list[RunArtifact]:
    """A run's data artifacts mapped to pipeline stages, each with a real integrity hash,
    byte size, and origin tag (the provenance canvas's data-I/O drill-in, §5).

    Every row carries the run's `origin` (real-giab / synthetic / contrived) so a consumer
    never mistakes a contrived artifact for real data (CLAUDE.md data-handling). Raw reads
    above `_HASH_MAX_BYTES` are size-listed with `sha256: null` rather than hashed.
    """
    run_dir = DATA_ROOT / run_id
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Unknown run '{run_id}'")
    origin = _run_origin(run_id)
    out: list[RunArtifact] = []
    for p in sorted(run_dir.iterdir()):
        if not p.is_file() or p.name in _SKIP_ARTIFACTS or p.suffix in _SKIP_SUFFIXES:
            continue
        pairs = _artifact_stage_roles(p.name)
        if not pairs:
            continue
        # Hash + stat once, then emit one row per (stage, role) edge the file sits on.
        sha = _sha256_of(p)
        size = p.stat().st_size
        url = f"/api/runs/{run_id}/artifacts/{p.name}"
        for stage, role in pairs:
            out.append(
                RunArtifact(
                    name=p.name,
                    stage=stage,
                    role=role,
                    sha256=sha,
                    size_bytes=size,
                    origin=origin,
                    url=url,
                )
            )
    return out


@app.get("/api/runs/{run_id}/artifacts/{name}")
def get_run_artifact(run_id: str, name: str, download: bool = False) -> FileResponse:
    """Serve one run artifact — inline to VIEW it (open-in-store), or as an attachment to download.

    ``download=1`` forces a save (Content-Disposition: attachment); the default serves it inline so
    clicking the artifact name opens the file at its location rather than downloading it. Read-only
    and traversal-hardened: ``name`` must be a bare filename (no path segments, no ``..``) and the
    resolved path must be a real direct child file of the run dir — a crafted name can never aim
    this outside ``data/<run_id>/``. Skips the same non-data markers/sidecars the listing does.
    """
    run_dir = DATA_ROOT / run_id
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Unknown run '{run_id}'")
    # Reject anything but a bare filename BEFORE touching the filesystem.
    if name != Path(name).name or name in _SKIP_ARTIFACTS:
        raise HTTPException(status_code=404, detail="Unknown artifact")
    target = (run_dir / name).resolve()
    if not target.is_relative_to(run_dir.resolve()) or not target.is_file():
        raise HTTPException(status_code=404, detail="Unknown artifact")
    disposition = "attachment" if download else "inline"
    return FileResponse(target, filename=name, content_disposition_type=disposition)


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    """The active runbook (thresholds + gate policy) for the settings screen."""
    return DEFAULT_RUNBOOK.model_dump()


# --- Data export (the BUILD-NOW query + export + ML-ready slice; design doc §2.1, T-030) -----

# Honesty label (design doc G-EXPORT-SOURCE): the export is a LIVE deterministic re-derivation
# of the gate over each run's artifacts at request time — reproducible and version-stamped, but
# NOT a read of a recorded/ledger-anchored decision. Audit-grade (projection-read) export is
# target-state. Surfaced in the `X-PipeGuard-Export-Source` header so a consumer can't mistake
# the demo export for audit provenance.
_EXPORT_SOURCE = "live-recompute"

# Explicit, stable column orders. Operator PII (`submitted_by`) is deliberately never a column
# (D10) — it is not an ML feature and never leaves the machine via export.
_DECISION_FIELDS = [
    "run_id", "sample_id", "verdict", "is_actionable", "headline", "rationale",
    "next_steps", "n_findings", "findings", "generated_by", "origin",
]  # fmt: skip
_FEATURE_FIELDS = [
    "run_id", "sample_id", "metric_key", "gate", "raw_value", "raw_unit",
    "normalized_value", "canonical_unit", "metric_registry_version", "verdict", "origin",
]  # fmt: skip


def _run_origin(run_id: str) -> str:
    """Origin label (`real-giab` | `synthetic` | `contrived`) for a run, from a per-run marker.

    Data-handling guardrail (D11): every exported row is tagged with where its data came from,
    so a consumer never mistakes synthetic/contrived rows for real ones and identity fields stay
    gated to non-real origins. Read from an optional single-line `origin` marker in the run dir;
    default `unknown` (treated conservatively) until runs are tagged.
    """
    marker = DATA_ROOT / run_id / "origin"
    if marker.exists():
        text = marker.read_text(encoding="utf-8").strip()
        if text:
            return text
    return "unknown"


@lru_cache(maxsize=32)
def _sample_index(run_id: str) -> dict[str, Sample]:
    """`sample_id` → intake `Sample` metadata, for the opt-in identity export join.

    A read-only re-read of the run's `sample_metadata.csv` via `load_run` (cached per run).
    Off the gate path entirely: identity fields never reach a rule or verdict — they only
    ride the export row through the de-id policy (`api/deid.py`, ADR-0001).
    """
    return {s.sample_id: s for s in load_run(_run_dir(run_id)).samples}


def _identity_fields(run_id: str, sample_id: str) -> dict[str, Any]:
    """The intake-identity columns for one sample (pre-de-id); missing metadata → `None`s."""
    sample = _sample_index(run_id).get(sample_id)
    return {
        "subject_id": sample.subject_id if sample else None,
        "tissue": sample.tissue if sample else None,
        "submitted_by": sample.submitted_by if sample else None,
    }


def _decision_rows(
    run_ids: list[str],
    verdict: str | None,
    *,
    include_identity: bool,
    policy: DeidPolicy,
) -> Iterator[dict[str, Any]]:
    """One row per (run, sample): verdict + full narration + a findings summary.

    Every row is routed through the de-id policy (`redact`), which makes the export's
    field allow-list explicit and unit-testable: operator PII is dropped, and (only with
    `include_identity`) intake cohort keys are origin-gated + pseudonymized. Without
    `include_identity` no identity field is joined, so the output is unchanged from before.
    """
    for rid in run_ids:
        detail = _evaluate(rid)
        origin = _run_origin(rid)
        for card in detail.cards:
            if verdict is not None and card.verdict.value != verdict:
                continue
            row: dict[str, Any] = {
                "run_id": rid,
                "sample_id": card.sample_id,
                "verdict": card.verdict.value,
                "is_actionable": card.is_actionable,
                "headline": card.headline,
                "rationale": card.rationale,
                "next_steps": " | ".join(card.next_steps),
                "n_findings": len(card.findings),
                "findings": " | ".join(f"{f.rule_id}:{f.title}" for f in card.findings),
                "generated_by": card.generated_by,
                "origin": origin,
            }
            if include_identity:
                row.update(_identity_fields(rid, card.sample_id))
            yield redact(row, origin, policy)


def _feature_rows(
    run_ids: list[str],
    verdict: str | None,
    *,
    include_identity: bool,
    policy: DeidPolicy,
) -> Iterator[dict[str, Any]]:
    """One row per `MetricValue` (long format = the ML corpus); `normalized_value` is the number.

    `canonical_unit` + `metric_registry_version` ride each row (ADR-0007 self-containment), so a
    downstream consumer can interpret the value without the registry in hand. Rows pass through
    the same de-id policy as the decision grain (see `_decision_rows`).
    """
    for rid in run_ids:
        detail = _evaluate(rid)
        origin = _run_origin(rid)
        for card in detail.cards:
            if verdict is not None and card.verdict.value != verdict:
                continue
            identity = _identity_fields(rid, card.sample_id) if include_identity else {}
            for mv in card.metric_values:
                row: dict[str, Any] = {
                    "run_id": rid,
                    "sample_id": mv.sample_id,
                    "metric_key": mv.metric_key,
                    "gate": mv.gate.value,
                    "raw_value": mv.raw_value,
                    "raw_unit": mv.raw_unit,
                    "normalized_value": mv.normalized_value,
                    "canonical_unit": mv.canonical_unit.value,
                    "metric_registry_version": mv.metric_registry_version,
                    "verdict": card.verdict.value,
                    "origin": origin,
                }
                if include_identity:
                    row.update(identity)
                yield redact(row, origin, policy)


def _to_csv(fields: list[str], rows: Iterable[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def _to_jsonl(rows: Iterable[dict[str, Any]]) -> str:
    return "".join(json.dumps(row) + "\n" for row in rows)


def _to_parquet(fields: list[str], rows: list[dict[str, Any]]) -> bytes:
    """Serialize to a single columnar Parquet file (D3) so a consumer reads it with any tool.

    `pyarrow` is an optional extra, imported lazily (mirroring the claude/slack seams) so the
    base install stays lean — absent, a clear 501 points at the extra, and CSV/JSONL still work.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - only without the parquet extra
        raise HTTPException(
            status_code=501,
            detail="parquet export needs the 'parquet' extra: uv sync --extra parquet",
        ) from exc
    # Column-major with the explicit field order; an empty result still carries the schema.
    table = pa.table({f: [row.get(f) for row in rows] for f in fields})
    buf = pa.BufferOutputStream()
    pq.write_table(table, buf)  # type: ignore[no-untyped-call]
    return bytes(buf.getvalue().to_pybytes())


def _serialize(
    fmt: str, fields: list[str], rows: list[dict[str, Any]]
) -> tuple[str | bytes, str, str]:
    """Return (body, extension, media_type) for the requested format."""
    if fmt == "csv":
        return _to_csv(fields, rows), "csv", "text/csv"
    if fmt == "jsonl":
        return _to_jsonl(rows), "jsonl", "application/x-ndjson"
    return _to_parquet(fields, rows), "parquet", "application/vnd.apache.parquet"


@app.get("/api/export")
def export(
    fmt: str = Query("csv", alias="format"),
    grain: str = "decision",
    run_id: str | None = None,
    verdict: str | None = None,
    q: str | None = None,
    include: str | None = None,
) -> Response:
    """Export the gate's decisions/metrics as one downloadable file (design doc §2.1, T-030).

    A read-only, deterministic re-derivation over the served runs — the whole *query + export +
    ML-ready* story from data the API already computes, no persistence wiring. `grain=decision`
    is one row per (run, sample) with verdict + narration + findings; `grain=feature` is one
    registry-normalized `MetricValue` per row (long format = the ML corpus).
    `format=csv|jsonl|parquet` (Parquet needs the optional `parquet` extra; pandas/polars/DuckDB
    read it). Filter by `run_id`, `verdict`, or `q` (run-id substring). Every row carries its
    `origin`; operator PII is never emitted (D10). This is a LIVE recompute, not audit
    provenance (`X-PipeGuard-Export-Source`).

    Every row is shaped by the config-driven de-id policy (`api/deid.py`, T-040) — a **demo
    de-id seam, NOT HIPAA de-identification**: operator PII (`submitted_by`) is dropped, and
    the opt-in `include=identity` mode joins intake cohort keys (`subject_id`/`tissue`) that
    are **origin-gated** (withheld for `real-giab` / untagged `unknown`) and **pseudonymized**
    (salted, non-reversible) for non-real origins. The active policy id rides
    `X-PipeGuard-Deid-Policy` (no compliance claim).
    """
    if fmt not in ("csv", "jsonl", "parquet"):
        raise HTTPException(status_code=400, detail="format must be 'csv', 'jsonl', or 'parquet'")
    if grain not in ("decision", "feature"):
        raise HTTPException(status_code=400, detail="grain must be 'decision' or 'feature'")
    if verdict is not None and verdict not in _VERDICT_ORDER:
        raise HTTPException(status_code=400, detail=f"verdict must be one of {_VERDICT_ORDER}")
    if include is not None and include != "identity":
        raise HTTPException(status_code=400, detail="include must be 'identity'")

    if run_id is not None:
        _run_dir(run_id)  # 404 if unknown
        run_ids = [run_id]
    else:
        run_ids = [r for r in _run_ids() if q is None or q in r]

    include_identity = include == "identity"
    policy = default_policy()
    base_fields = _DECISION_FIELDS if grain == "decision" else _FEATURE_FIELDS
    fields = export_fields(base_fields, IDENTITY_FIELDS if include_identity else [], policy)
    builder = _decision_rows if grain == "decision" else _feature_rows
    rows = list(builder(run_ids, verdict, include_identity=include_identity, policy=policy))
    body, ext, media = _serialize(fmt, fields, rows)

    scope = run_id or (f"q-{q}" if q else "all")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"pipeguard-{scope}-{grain}-{stamp}.{ext}"
    return Response(
        content=body,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-PipeGuard-Export-Source": _EXPORT_SOURCE,
            "X-PipeGuard-Exported-At": stamp,
            "X-PipeGuard-Row-Count": str(len(rows)),
            "X-PipeGuard-Deid-Policy": policy.policy_id,
        },
    )


# --- De-identified share/report egress (ADR-0018 D3) ------------------------------------------

# The maintainer's conservative default ("HIPAA compliance is so key here"): a share is scrubbed
# by the Safe-Harbor-STYLE transform in `api/safe_harbor.py` — the strictest scrub we can honestly
# offer, explicitly NOT a certified/attested de-identification and NOT a compliance claim. Every
# share is recorded as a DATA_EXPORTED provenance event so data-out is auditable next to decisions.
_SHARE_DISCLAIMER = (
    "Conservative HIPAA Safe-Harbor-STYLE scrub (mechanical 45 CFR §164.514(b)(2) identifier "
    "removal) — NOT certified/attested de-identification and NOT a compliance claim. Free-text "
    "redaction is regex-mechanical and will miss prose identifiers; real patient data needs an "
    "audited de-identification program before any external share."
)


class ShareManifest(BaseModel):
    """The provenance + honesty manifest returned with (and recorded for) a de-identified share."""

    run_id: str
    policy_id: str  # safe-harbor-style-v1 — a scrub version, NOT a compliance attestation
    grain: str
    n_rows: int
    origin: str  # the run's data origin (real-giab | synthetic | contrived | unknown)
    exported_at: str  # ISO-8601 Z
    exported_by: str  # the approver actor id
    content_hash: str  # sha256 of the emitted rows — ties the recorded event to these exact bytes
    event_id: str  # the DATA_EXPORTED provenance event this share recorded
    safe_harbor_classes: list[str]  # the §164.514(b)(2) identifier classes the scrub covers
    disclaimer: str


class ShareBundle(BaseModel):
    """A de-identified share/report egress: the scrubbed rows + the honesty/provenance manifest."""

    manifest: ShareManifest
    rows: list[dict[str, Any]]


@app.post("/api/runs/{run_id}/share")
def share_run(
    run_id: str,
    actor: Actor = Depends(require_role("approver")),
) -> ShareBundle:
    """De-identify one run's decision report for egress AND record it as a DATA_EXPORTED event.

    The conservative default the maintainer asked for: every row is run through
    `api.safe_harbor.redact_record` (Safe-Harbor-STYLE identifier removal) — the strictest scrub
    we can honestly offer, NOT an attestation (see `manifest.disclaimer`). Approver-gated (the
    frontend also confirms before firing). This is an **egress transform only**: it reads the
    gate's already-computed decision cards + intake identity join, never a rule/verdict/gate input
    (ADR-0001). The share is written to the append-only share ledger so every data-out is auditable
    in the same provenance trail as the decisions — the recorded event carries a content hash of the
    exact bytes emitted, so the trail entry can't drift from what actually left.
    """
    _run_dir(run_id)  # 404 if unknown
    origin = _run_origin(run_id)
    detail = _evaluate(run_id)
    # Build the pre-scrub decision report joined with intake identity (subject_id/tissue/
    # submitted_by) — i.e. the very columns the Safe-Harbor scrub then removes/generalizes, so the
    # de-id is demonstrably doing work rather than passing an already-clean row through.
    rows: list[dict[str, Any]] = []
    for card in detail.cards:
        raw: dict[str, Any] = {
            "run_id": run_id,
            "sample_id": card.sample_id,
            "verdict": card.verdict.value,
            "headline": card.headline,
            "rationale": card.rationale,
            "n_findings": len(card.findings),
            **_identity_fields(run_id, card.sample_id),
        }
        rows.append(redact_record(raw, origin))

    # Hash the exact emitted bytes so the recorded event is tamper-evident and pins the egress.
    payload = json.dumps(rows, sort_keys=True)
    content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    event = ProvenanceEvent(
        event_type=EventType.DATA_EXPORTED,
        run_id=run_id,
        actor=f"human:{actor.id}",
        outputs=[EntityRef(entity_type="share_bundle", id=content_hash, content_hash=content_hash)],
        payload={
            "policy_id": SAFE_HARBOR_POLICY_ID,
            "grain": "decision",
            "n_rows": len(rows),
            "origin": origin,
            "content_hash": content_hash,
            "exported_at": stamp,
            "disclaimer": _SHARE_DISCLAIMER,
        },
    )
    get_share_store().append(event)  # append-only; get_run merges it into the trail (cache pure)
    manifest = ShareManifest(
        run_id=run_id,
        policy_id=SAFE_HARBOR_POLICY_ID,
        grain="decision",
        n_rows=len(rows),
        origin=origin,
        exported_at=stamp,
        exported_by=actor.id,
        content_hash=content_hash,
        event_id=event.id,
        safe_harbor_classes=[label for label, _ in HIPAA_SAFE_HARBOR_CLASSES],
        disclaimer=_SHARE_DISCLAIMER,
    )
    return ShareBundle(manifest=manifest, rows=rows)


@app.get("/api/runbook")
def get_runbook() -> RunbookPolicy:
    """The active runbook's QC gate policy, flattened for operators/integrators.

    Each threshold becomes `{metric, our_key, label, gate, hard_fail, unit, direction}`;
    the response also lists the required intake-metadata fields. Thresholds are
    ILLUSTRATIVE / configurable demo policy — not clinical cutoffs (see `disclaimer`;
    CLAUDE.md life-science guardrail 3). Complements the raw dump at `GET /api/config`.
    """
    registry = default_registry()
    thresholds = [
        RunbookThreshold(
            metric=t.metric,
            our_key=t.our_key,
            label=t.label,
            gate=t.gate,
            hard_fail=t.hard_fail,
            unit=t.unit,
            direction="higher_is_better" if t.higher_is_better else "lower_is_better",
            # Pipeline gate from the registry — the authoritative gate for this our_key, so the
            # frontend can group policy by gate (and build the not-measured placeholders) honestly.
            pipeline_gate=registry.entry(t.our_key).gate,
        )
        for t in DEFAULT_RUNBOOK.qc_thresholds
    ]
    return RunbookPolicy(
        disclaimer=_RUNBOOK_DISCLAIMER,
        units_note=_RUNBOOK_UNITS_NOTE,
        run_id_field=DEFAULT_RUNBOOK.run_id_field,
        required_metadata_fields=DEFAULT_RUNBOOK.require_metadata_fields,
        thresholds=thresholds,
    )


# --- Metric catalog (read-only registry view; W16/T-038) -------------------------------------

# Life-science guardrail (CLAUDE.md 2/3): the registry is a versioned, operator-configurable
# metric VOCABULARY — not a calibrated or validated clinical panel. Kept parallel to
# `_RUNBOOK_DISCLAIMER` (both carry the verbatim "NOT clinical" phrase) so an integrator reading
# either surface can't mistake tool metadata for a medical claim.
_CATALOG_DISCLAIMER = (
    "Illustrative / operator-configurable metric vocabulary — NOT clinical. Registry entries are "
    "versioned tool metadata (metric_registry_version); the registered set is not a calibrated or "
    "validated clinical panel, and a 'registered' metric is not a gate until the runbook adds it."
)


class MetricCatalogEntry(BaseModel):
    """One registered metric type, flattened from the registry for the settings catalog.

    A read-only projection of a `MetricEntry`. `gated` reports whether the ACTIVE runbook
    currently gates on this `our_key`; registered-but-ungated entries are the extensibility
    surface (a metric can be described in the vocabulary before any threshold gates on it).
    """

    our_key: str
    display_name: str
    category: str
    canonical_unit: str  # registry CanonicalUnit value (e.g. "fraction", "x")
    direction: str  # "higher_is_better" | "lower_is_better" | "target_band"
    gate: str  # which gate this metric belongs to ("preflight" | "qc" | "variant")
    source_module: str  # tool/MultiQC module the value is parsed from
    aliases: list[str]
    gated: bool


class MetricCatalog(BaseModel):
    """The registered metric vocabulary plus which entries the live runbook gates on.

    `disclaimer` is load-bearing, not decoration: this is versioned, configurable vocabulary,
    never a calibrated or clinical panel (CLAUDE.md life-science guardrails 2/3). `n_gated`
    (< `n_registered`) makes the extensibility story explicit at the API boundary.
    """

    disclaimer: str
    metric_registry_version: int
    n_registered: int
    n_gated: int
    entries: list[MetricCatalogEntry]


@app.get("/api/metrics/registry")
def get_metric_catalog() -> MetricCatalog:
    """The registered metric vocabulary + which entries the live runbook gates on (read-only).

    Reads `default_registry()` and `DEFAULT_RUNBOOK` and flattens each registered `MetricEntry`
    to `{our_key, display_name, category, canonical_unit, direction, gate, source_module,
    aliases, gated}`. `gated` is true when the active runbook has a QC threshold on that
    `our_key` — the registered-but-ungated entries are the extensibility surface. This is a pure
    READ over the versioned registry: it never authors or edits a metric type or a gate (ADR-0001,
    rules decide). Entries are illustrative, configurable vocabulary — never calibrated or
    clinical (see `disclaimer`). Complements `GET /api/runbook` (the gated thresholds' policy).
    """
    registry = default_registry()
    gated_keys = {t.our_key for t in DEFAULT_RUNBOOK.qc_thresholds}
    entries = [
        MetricCatalogEntry(
            our_key=entry.our_key,
            display_name=entry.display_name,
            category=entry.category,
            canonical_unit=entry.canonical_unit.value,
            direction=entry.direction.value,
            gate=entry.gate.value,
            source_module=entry.source.module,
            aliases=list(entry.aliases),
            gated=entry.our_key in gated_keys,
        )
        for entry in registry.entries.values()
    ]
    return MetricCatalog(
        disclaimer=_CATALOG_DISCLAIMER,
        metric_registry_version=registry.version,
        n_registered=len(entries),
        n_gated=sum(1 for e in entries if e.gated),
        entries=entries,
    )


# Fixed series order so the exposition is byte-stable across scrapes (Prometheus itself is
# order-insensitive, but a deterministic dump keeps the pinned test and diffs clean).
_VERDICT_ORDER: tuple[str, ...] = ("proceed", "hold", "rerun", "escalate")
_GATE_ORDER: tuple[Gate, ...] = (Gate.PREFLIGHT, Gate.QC, Gate.VARIANT)


def _aggregate_metrics(
    run_ids: list[str] | None = None,
) -> tuple[int, int, dict[str, int], dict[str, int]]:
    """Roll up run / sample / verdict / per-gate counts across a set of runs.

    Pure aggregation over the gate's own outputs (the `_evaluate` cards) — no metrics code
    leaks into `src/pipeguard/` (CLAUDE.md architecture guardrail 1). A sample counts as
    "flagged" at a gate when that gate's rollup verdict is actionable (non-proceed).

    `run_ids` defaults to every served run (the Prometheus `/metrics` seam's fleet-wide view);
    the monitoring endpoint passes a windowed subset so the SAME roll-up powers both. The
    return tuple shape is unchanged, keeping the `/metrics` caller byte-stable.
    """
    ids = _run_ids() if run_ids is None else run_ids
    verdict_counts = dict.fromkeys(_VERDICT_ORDER, 0)
    gate_flagged = {g.value: 0 for g in _GATE_ORDER}
    total_cards = 0
    for rid in ids:
        detail = _evaluate(rid)
        total_cards += detail.summary.n_samples
        for verdict, n in detail.summary.counts.items():
            verdict_counts[verdict] += n
        for card in detail.cards:
            for gr in card.gate_results:
                if gr.verdict is not Verdict.PROCEED:
                    gate_flagged[gr.gate.value] += 1
    return len(ids), total_cards, verdict_counts, gate_flagged


# --- Monitoring dashboard (pre-aggregated; the §7 screen) ------------------------------------
# One response replaces the frontend's N-fan-out (a detail fetch per run). Aggregation stays in
# the API layer, never the framework-agnostic core (CLAUDE.md architecture guardrail 1).

# Supported time windows. A dated window keeps runs whose [Header] date is within the last N
# days of "now"; "all" applies no date filter (and admits undated runs).
_WINDOW_DAYS: dict[str, int] = {"7d": 7, "14d": 14, "30d": 30}
_WINDOWS: tuple[str, ...] = ("7d", "14d", "30d", "all")


def _in_window(run_date: str | None, window: str, *, now: date) -> bool | None:
    """Tri-state window membership for a run's [Header] date.

    Returns True (inside the window, or any run under "all"), False (dated but older than the
    window), or None (no / unparseable date → the run can't be placed on the time axis). A dated
    window is inclusive of its `now - Nd` cutoff. Pure and `now`-injected so the boundary is
    unit-testable without leaning on the wall clock (mirrors `_run_status`'s pure-function style).
    """
    if window == "all":
        return True
    if run_date is None:
        return None
    try:
        parsed = date.fromisoformat(run_date)
    except ValueError:
        # Tolerant boundary (CLAUDE.md data-handling 2): a malformed date is a signal the run
        # can't be windowed, not a crash — treat it exactly like a missing date.
        return None
    return parsed >= now - timedelta(days=_WINDOW_DAYS[window])


class MonitoringOverall(BaseModel):
    """Fleet-wide KPI roll-up for the in-window run set (the monitoring header tiles).

    `auto_proceed_pct` is a throughput ratio (share of samples the gate cleared with no human
    touch), a heuristic display number — not a calibrated rate or a confidence (CLAUDE.md
    life-science guardrail 2); None when the window has no samples.
    """

    n_runs: int
    n_samples: int
    n_attention: int
    verdict_counts: dict[str, int]
    auto_proceed_pct: float | None


class MonitoringRunRow(BaseModel):
    """One run's throughput + verdict split (the verdicts-over-time bars)."""

    run_id: str
    run_date: str | None
    n_samples: int
    counts: dict[str, int]


class MonitoringGate(BaseModel):
    """Per-gate flagged / total for the pass-rate bars (pass% = (total - flagged) / total)."""

    gate: str
    flagged: int
    total: int


class MonitoringSignature(BaseModel):
    """One recurring issue signature, ranked by its count within the window.

    Identity (`signature`/`rule_id`/`title`/`gate`) and `count` are the historic core; the four
    fields below are ADDITIVE fidelity for the §7 signature row and default so the payload stays
    backward-compatible:

    - `first_seen` / `last_seen` — earliest / latest [Header] date (ISO 8601) of a run carrying
      the signature; None when only undated runs carry it (never fabricated — honest omission).
    - `trend` — a coarse up/down/flat glyph comparing the recent vs older half of the window by
      occurrence count. A display heuristic, NOT a calibrated rate (life-science guardrail 2).
    - `affected_run_ids` — the distinct run ids the signature appears in, chronological, for the
      affected-run deep-links on the detail panel.
    """

    signature: str
    rule_id: str
    title: str
    gate: str
    count: int
    first_seen: str | None = None
    last_seen: str | None = None
    trend: Literal["up", "down", "flat"] = "flat"
    affected_run_ids: list[str] = Field(default_factory=list)


class MonitoringMetrics(BaseModel):
    """Pre-aggregated monitoring payload (the §7 screen) so the frontend renders from ONE
    response instead of fanning out a detail fetch per run.

    `window` echoes the requested view. `n_runs_excluded_no_date` is honest bookkeeping: under
    a dated window, runs with no [Header] date can't be placed on the time axis and are dropped
    from the aggregate, so a consumer can surface how many were set aside. `n_signatures_total`
    is the full distinct-signature count before `signatures_limit` caps the list, so a
    "show all (N)" affordance stays honest. Counts are lifetime tallies over the in-window runs,
    not calibrated rates (CLAUDE.md life-science guardrail 2).
    """

    window: str
    n_runs_excluded_no_date: int
    n_signatures_total: int
    overall: MonitoringOverall
    runs: list[MonitoringRunRow]
    gates: list[MonitoringGate]
    signatures: list[MonitoringSignature]


@app.get("/api/monitoring")
def get_monitoring(
    window: str = "all",
    sig_limit: int | None = Query(None, ge=1, alias="signatures_limit"),
) -> MonitoringMetrics:
    """Pre-aggregated monitoring dashboard metrics (the §7 screen).

    Rolls up throughput, verdict distribution, per-gate pass rate, and recurring issue
    signatures across the served runs so the frontend renders from ONE response instead of
    N-fanning-out a detail fetch per run. Reuses `_aggregate_metrics` (the same roll-up the
    Prometheus `/metrics` seam uses) for the KPI + per-gate group; the aggregation lives in the
    API layer, never the framework-agnostic core (CLAUDE.md architecture guardrail 1).

    `window` ∈ {7d,14d,30d,all} filters runs by their [Header] date relative to today; an
    unknown value is a 400. Under a dated window a run with no date can't be placed on the time
    axis, so it is excluded and counted in `n_runs_excluded_no_date`. `signatures_limit` caps
    the ranked signature list (uncapped by default); `n_signatures_total` always reports the
    full distinct count. Counts are lifetime tallies, not calibrated rates (life-science
    guardrail 2).
    """
    if window not in _WINDOWS:
        raise HTTPException(status_code=400, detail=f"window must be one of {list(_WINDOWS)}")

    today = datetime.now(timezone.utc).date()
    kept: list[str] = []
    excluded = 0
    for rid in _run_ids():
        member = _in_window(_evaluate(rid).summary.run_date, window, now=today)
        if member is None:
            excluded += 1  # dated window + undated run → set aside, counted honestly
            continue
        if member:
            kept.append(rid)
    # Chronological order for the time-series bars (fallback to run_id when a run has no date).
    kept.sort(key=lambda rid: _run_order_key(_evaluate(rid).summary))

    n_runs, n_cards, verdict_counts, gate_flagged = _aggregate_metrics(kept)
    proceed = verdict_counts.get("proceed", 0)
    overall = MonitoringOverall(
        n_runs=n_runs,
        n_samples=n_cards,
        # Attention == every non-proceed sample; equals the sum of the per-run n_attention.
        n_attention=sum(n for v, n in verdict_counts.items() if v != "proceed"),
        verdict_counts=verdict_counts,
        auto_proceed_pct=(100.0 * proceed / n_cards) if n_cards else None,
    )

    rows: list[MonitoringRunRow] = []
    sig_counts: dict[str, int] = {}
    sig_meta: dict[str, tuple[str, str, str]] = {}  # signature -> (rule_id, title, gate)
    # Additive fidelity accumulators for the §7 signature row: the distinct run ids a signature
    # appears in (chronological — the `kept` loop is already date-sorted; deduped via `sig_seen`)
    # for the affected-run deep-links, and the parsed [Header] date of each dated occurrence for
    # the first/last-seen range and the recent-vs-older trend.
    sig_runs: dict[str, list[str]] = {}
    sig_seen: dict[str, set[str]] = {}
    sig_dates: dict[str, list[date]] = {}
    kept_dates: list[date] = []  # dated runs in the window, for the "all"-window trend split
    for rid in kept:
        detail = _evaluate(rid)
        summary = detail.summary
        rows.append(
            MonitoringRunRow(
                run_id=summary.run_id,
                run_date=summary.run_date,
                n_samples=summary.n_samples,
                counts=summary.counts,
            )
        )
        # Parse the run's [Header] date once; an undated/unparseable run can't be placed on the
        # time axis, so it still contributes to count/affected-runs but not to dates or the trend.
        try:
            run_d: date | None = date.fromisoformat(summary.run_date) if summary.run_date else None
        except ValueError:
            run_d = None
        if run_d is not None:
            kept_dates.append(run_d)
        for card in detail.cards:
            for finding in card.findings:
                sig = finding.signature
                sig_counts[sig] = sig_counts.get(sig, 0) + 1
                # First sighting fixes the display metadata; the signature key is stable across
                # rule versions (models.Finding.signature), so any occurrence carries the same.
                sig_meta.setdefault(sig, (finding.rule_id, finding.title, finding.gate.value))
                seen = sig_seen.setdefault(sig, set())
                if summary.run_id not in seen:
                    seen.add(summary.run_id)
                    sig_runs.setdefault(sig, []).append(summary.run_id)
                if run_d is not None:
                    sig_dates.setdefault(sig, []).append(run_d)

    # Trend split point: occurrences in the recent half of the window vs the older half. A dated
    # window (7/14/30d) splits at today - N/2; "all" has no fixed span, so split at the midpoint
    # of the observed run-date range. None → nothing to split on, so every trend reads flat.
    if window in _WINDOW_DAYS:
        midpoint: date | None = today - timedelta(days=_WINDOW_DAYS[window] // 2)
    elif kept_dates:
        lo, hi = min(kept_dates), max(kept_dates)
        midpoint = date.fromordinal((lo.toordinal() + hi.toordinal()) // 2)
    else:
        midpoint = None

    def _sig_trend(dates: list[date]) -> Literal["up", "down", "flat"]:
        # Rising (more occurrences in the recent half) → "up"; falling → "down"; else "flat". A
        # coarse display heuristic, not a calibrated rate (life-science guardrail 2).
        if midpoint is None or not dates:
            return "flat"
        older = sum(1 for d in dates if d <= midpoint)
        recent = len(dates) - older
        if recent > older:
            return "up"
        if recent < older:
            return "down"
        return "flat"

    # Rank by count desc, then rule_id / title / signature so ties order deterministically.
    ranked = sorted(
        sig_counts, key=lambda sig: (-sig_counts[sig], sig_meta[sig][0], sig_meta[sig][1], sig)
    )
    if sig_limit is not None:
        ranked = ranked[:sig_limit]
    signatures = [
        MonitoringSignature(
            signature=sig,
            rule_id=sig_meta[sig][0],
            title=sig_meta[sig][1],
            gate=sig_meta[sig][2],
            count=sig_counts[sig],
            first_seen=min(sig_dates[sig]).isoformat() if sig_dates.get(sig) else None,
            last_seen=max(sig_dates[sig]).isoformat() if sig_dates.get(sig) else None,
            trend=_sig_trend(sig_dates.get(sig, [])),
            affected_run_ids=sig_runs.get(sig, []),
        )
        for sig in ranked
    ]

    gates = [
        MonitoringGate(gate=g.value, flagged=gate_flagged[g.value], total=n_cards)
        for g in _GATE_ORDER
    ]
    return MonitoringMetrics(
        window=window,
        n_runs_excluded_no_date=excluded,
        n_signatures_total=len(sig_counts),
        overall=overall,
        runs=rows,
        gates=gates,
        signatures=signatures,
    )


# --- Advisory agents over the read-API (roster #2 pipeline-repair, #3 archivist) -------------
# On-demand, read-only, OFF the deterministic gate (ADR-0001): each invokes an advisory agent
# that narrates/organizes over already-decided artifacts; neither sets/routes a verdict, and both
# use the offline stub by default (PIPEGUARD_PIPELINE_REPAIR_AGENT / PIPEGUARD_ARCHIVIST_AGENT
# = claude to go live). They mirror the GET .../triage surface.


@app.get("/api/monitoring/signatures/{signature}/repair")
def get_signature_repair(signature: str, window: str = "all") -> RepairProposal:
    """Advisory pipeline-repair proposal for a recurring issue signature (agent #2; ADR-0008/0012).

    Assembles the recurring signature from the served runs (the same rollup `/api/monitoring`
    shows, windowed the same way) and returns a proposed, HUMAN-REVIEWED remediation. On-demand
    and off the gate — it never edits a pipeline or sets a verdict; the ~3x auto-escalation is a
    separate, not-yet-built trigger. 404 if the signature does not recur in the window.
    """
    if window not in _WINDOWS:
        raise HTTPException(status_code=400, detail=f"window must be one of {list(_WINDOWS)}")
    today = datetime.now(timezone.utc).date()
    runs = {
        rid: _evaluate(rid).cards
        for rid in _run_ids()
        if _in_window(_evaluate(rid).summary.run_date, window, now=today)
    }
    sig = recurring_signature(runs, signature)
    if sig is None:
        raise HTTPException(
            status_code=404, detail=f"Signature not recurring in window: '{signature}'"
        )
    return propose_repair(sig)


def _archive_input(run_id: str) -> RunArchiveInput:
    """Build the archivist's least-privilege input from the cached projection (no gate re-run)."""
    detail = _evaluate(run_id)
    artifacts = [
        ArtifactRef(
            name=a.name,
            kind=_classify_kind(a.name),
            sha256=a.sha256,
            size_bytes=a.size_bytes,
            origin=a.origin,
        )
        for a in list_run_artifacts(run_id)
    ]
    return RunArchiveInput(
        run_id=run_id,
        status=detail.summary.status,
        run_date=detail.summary.run_date,
        platform=detail.summary.platform,
        origin=_run_origin(run_id),
        cards=detail.cards,
        artifacts=artifacts,
    )


@app.get("/api/runs/{run_id}/archive-digest")
def get_archive_digest(run_id: str) -> ArchiveDigest:
    """Advisory organizational digest + export manifest for one run (agent #3, off the gate).

    Indexes/summarizes an already-decided run and PROPOSES an archival/organization action; it
    never opens/moves/deletes a file or relabels an origin, and carries no verdict (ADR-0001).
    """
    return archive_digest([_archive_input(run_id)])


@app.get("/api/archive/index")
def get_archive_index() -> ArchiveDigest:
    """Advisory cross-run organizational index over every served run (agent #3, off the gate)."""
    return archive_digest([_archive_input(rid) for rid in _run_ids()])


def _render_prometheus() -> str:
    """Hand-roll the Prometheus text-exposition format (stdlib f-strings, wishlist #17).

    The format is trivial enough that `prometheus-client` would be an unjustified dependency
    (CLAUDE.md dependency guardrail 1): `# HELP`/`# TYPE` headers plus one
    `name{label="v"} value` line per series. `_total`-suffixed names are counters by
    Prometheus convention. Label values come from closed enums, so no escaping is needed.
    """
    n_runs, n_cards, verdict_counts, gate_flagged = _aggregate_metrics()
    lines = [
        "# HELP pipeguard_runs_total Analysis runs discoverable by the API.",
        "# TYPE pipeguard_runs_total counter",
        f"pipeguard_runs_total {n_runs}",
        "# HELP pipeguard_samples_total Decision cards (samples) across all served runs.",
        "# TYPE pipeguard_samples_total counter",
        f"pipeguard_samples_total {n_cards}",
        "# HELP pipeguard_cards_total Decision cards by final gate verdict.",
        "# TYPE pipeguard_cards_total counter",
    ]
    lines += [f'pipeguard_cards_total{{verdict="{v}"}} {verdict_counts[v]}' for v in _VERDICT_ORDER]
    lines += [
        "# HELP pipeguard_gate_flagged_samples_total Samples with an actionable "
        "(non-proceed) verdict at each gate.",
        "# TYPE pipeguard_gate_flagged_samples_total counter",
    ]
    lines += [
        f'pipeguard_gate_flagged_samples_total{{gate="{g.value}"}} {gate_flagged[g.value]}'
        for g in _GATE_ORDER
    ]
    return "\n".join(lines) + "\n"


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> PlainTextResponse:
    """Prometheus text-exposition metrics — the telemetry seam (ADR-0010, wishlist #17).

    Read-only aggregation over the served mock runs; deterministic for the pinned data.
    Emits the Prometheus canonical content type `text/plain; version=0.0.4`.
    """
    return PlainTextResponse(_render_prometheus(), media_type="text/plain; version=0.0.4")
