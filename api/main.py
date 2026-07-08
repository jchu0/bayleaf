"""FastAPI read-API over the pipeguard core — the production seam (ADR-0010).

Framework boundary: this wraps `pipeguard`; the core has no FastAPI import (CLAUDE.md
architecture guardrail 1). The React frontend consumes these endpoints. Read-only for
now — write actions (ticket transitions, notify) arrive with the ticketing phase.

Run:  uv run uvicorn api.main:app --reload --port 8010
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pipeguard import DEFAULT_RUNBOOK, EventLedger, load_run, run_gate, triage_card
from pipeguard.models import DecisionCard
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
