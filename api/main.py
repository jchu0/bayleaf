"""FastAPI read-API over the pipeguard core — the production seam (ADR-0010).

Framework boundary: this wraps `pipeguard`; the core has no FastAPI import (CLAUDE.md
architecture guardrail 1). The React frontend consumes these endpoints. Read-only for
now — write actions (ticket transitions, notify) arrive with the ticketing phase.

Run:  uv run uvicorn api.main:app --reload --port 8010
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from pipeguard import DEFAULT_RUNBOOK, EventLedger, load_run, run_gate, triage_card
from pipeguard.models import DecisionCard, Gate, Verdict
from pipeguard.provenance import ProvenanceEvent
from pipeguard.triage import TriageNote

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="PipeGuard API", version="0.1.0")

# The React dev server (Vite) runs on 5173; allow it in dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


class RunSummary(BaseModel):
    """The run-overview row: per-run verdict counts and attention flag."""

    run_id: str
    n_samples: int
    n_attention: int
    counts: dict[str, int]


class RunDetail(BaseModel):
    """A run's full payload: summary + decision cards + the provenance trail."""

    run_id: str
    summary: RunSummary
    cards: list[DecisionCard]
    events: list[ProvenanceEvent]


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

    `gate`/`hard_fail` are in the metric's canonical unit (fractions for rates, x for
    coverage — the same scale the rules gate on); `unit` is the display symbol. `direction`
    reports the comparison sense so an integrator reads a one-sided gate correctly.
    """

    metric: str
    our_key: str
    label: str
    gate: float
    hard_fail: float
    unit: str
    direction: str  # "higher_is_better" | "lower_is_better"


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


@lru_cache(maxsize=32)
def _evaluate(run_id: str) -> RunDetail:
    """Run the gate once per run (cached); captures cards + the event trail."""
    ledger = EventLedger()
    cards = run_gate(load_run(_run_dir(run_id)), ledger=ledger)
    counts = Counter(c.verdict.value for c in cards)
    summary = RunSummary(
        run_id=run_id,
        n_samples=len(cards),
        n_attention=sum(1 for c in cards if c.is_actionable),
        counts={v: counts.get(v, 0) for v in ("proceed", "hold", "rerun", "escalate")},
    )
    return RunDetail(run_id=run_id, summary=summary, cards=cards, events=ledger.events)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/runs")
def list_runs() -> list[RunSummary]:
    """All discoverable runs with their verdict counts (the run-overview screen)."""
    return [_evaluate(rid).summary for rid in _run_ids()]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> RunDetail:
    """One run: summary + every decision card + the full provenance trail."""
    return _evaluate(run_id)


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


def _decision_rows(run_ids: list[str], verdict: str | None) -> Iterator[dict[str, Any]]:
    """One row per (run, sample): verdict + full narration + a findings summary."""
    for rid in run_ids:
        detail = _evaluate(rid)
        origin = _run_origin(rid)
        for card in detail.cards:
            if verdict is not None and card.verdict.value != verdict:
                continue
            yield {
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


def _feature_rows(run_ids: list[str], verdict: str | None) -> Iterator[dict[str, Any]]:
    """One row per `MetricValue` (long format = the ML corpus); `normalized_value` is the number.

    `canonical_unit` + `metric_registry_version` ride each row (ADR-0007 self-containment), so a
    downstream consumer can interpret the value without the registry in hand.
    """
    for rid in run_ids:
        detail = _evaluate(rid)
        origin = _run_origin(rid)
        for card in detail.cards:
            if verdict is not None and card.verdict.value != verdict:
                continue
            for mv in card.metric_values:
                yield {
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
    """
    if fmt not in ("csv", "jsonl", "parquet"):
        raise HTTPException(status_code=400, detail="format must be 'csv', 'jsonl', or 'parquet'")
    if grain not in ("decision", "feature"):
        raise HTTPException(status_code=400, detail="grain must be 'decision' or 'feature'")
    if verdict is not None and verdict not in _VERDICT_ORDER:
        raise HTTPException(status_code=400, detail=f"verdict must be one of {_VERDICT_ORDER}")

    if run_id is not None:
        _run_dir(run_id)  # 404 if unknown
        run_ids = [run_id]
    else:
        run_ids = [r for r in _run_ids() if q is None or q in r]

    fields = _DECISION_FIELDS if grain == "decision" else _FEATURE_FIELDS
    builder = _decision_rows if grain == "decision" else _feature_rows
    rows = list(builder(run_ids, verdict))
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
        },
    )


@app.get("/api/runbook")
def get_runbook() -> RunbookPolicy:
    """The active runbook's QC gate policy, flattened for operators/integrators.

    Each threshold becomes `{metric, our_key, label, gate, hard_fail, unit, direction}`;
    the response also lists the required intake-metadata fields. Thresholds are
    ILLUSTRATIVE / configurable demo policy — not clinical cutoffs (see `disclaimer`;
    CLAUDE.md life-science guardrail 3). Complements the raw dump at `GET /api/config`.
    """
    thresholds = [
        RunbookThreshold(
            metric=t.metric,
            our_key=t.our_key,
            label=t.label,
            gate=t.gate,
            hard_fail=t.hard_fail,
            unit=t.unit,
            direction="higher_is_better" if t.higher_is_better else "lower_is_better",
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


# Fixed series order so the exposition is byte-stable across scrapes (Prometheus itself is
# order-insensitive, but a deterministic dump keeps the pinned test and diffs clean).
_VERDICT_ORDER: tuple[str, ...] = ("proceed", "hold", "rerun", "escalate")
_GATE_ORDER: tuple[Gate, ...] = (Gate.PREFLIGHT, Gate.QC, Gate.VARIANT)


def _aggregate_metrics() -> tuple[int, int, dict[str, int], dict[str, int]]:
    """Roll up run / sample / verdict / per-gate counts across every served run.

    Pure aggregation over the gate's own outputs (the `_evaluate` cards) — no metrics code
    leaks into `src/pipeguard/` (CLAUDE.md architecture guardrail 1). A sample counts as
    "flagged" at a gate when that gate's rollup verdict is actionable (non-proceed).
    """
    run_ids = _run_ids()
    verdict_counts = dict.fromkeys(_VERDICT_ORDER, 0)
    gate_flagged = {g.value: 0 for g in _GATE_ORDER}
    total_cards = 0
    for rid in run_ids:
        detail = _evaluate(rid)
        total_cards += detail.summary.n_samples
        for verdict, n in detail.summary.counts.items():
            verdict_counts[verdict] += n
        for card in detail.cards:
            for gr in card.gate_results:
                if gr.verdict is not Verdict.PROCEED:
                    gate_flagged[gr.gate.value] += 1
    return len(run_ids), total_cards, verdict_counts, gate_flagged


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
