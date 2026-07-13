"""Read-only, de-identified historical retrieval for the Archivist agent (ADR-0024 / P3).

design/agent-capabilities.md §1: give the archivist a way to "pull historic data if the user asks" —
a cross-run aggregate (verdict distribution, recurring signatures, run inventory) that grounds the
System-agents chat when the operator asks an organizational/historical question without a run named.

Two sources, tried in order, both READ-ONLY:
  1. the persistence projection (:func:`bayleaf.persistence.get_repository` — the SQLite/Postgres
     rebuildable projection of the event ledger). This is the production form the ADR names.
  2. **fallback:** re-derive from the served run dirs (``data/<run_id>/`` via the archivist's own
     ``build_run_input_from_dir``) when the projection is empty (the offline demo default — the
     ``:memory:`` DB has no rows until ``rebuild-db`` runs). Same historic runs, just recomputed.

De-identified by construction: the aggregate is counts + run ids + rule ids + signature titles — no
subject id / free-text PII flows through. Advisory + off the gate (ADR-0001): it grounds a chat
answer; it never sets a verdict. The archivist NARRATES over these numbers; it never invents one.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from api.chat import ChatCitation

_DATA = Path(__file__).resolve().parent.parent / "data"


def _aggregate(verdicts: list[str], run_ids: set[str], sigs: Counter[str]) -> dict[str, Any]:
    """The unified historic aggregate — same shape whichever source produced the inputs."""
    return {
        "n_runs": len(run_ids),
        "n_cards": len(verdicts),
        "verdict_counts": dict(Counter(verdicts)),
        "top_signatures": sigs.most_common(6),  # [(title, count), …]
        "run_ids": sorted(run_ids),
    }


def _from_repository() -> dict[str, Any] | None:
    """Aggregate from the persistence projection, or ``None`` if it has no runs (demo default)."""
    from bayleaf.persistence import get_repository

    repo = get_repository()
    cards = repo.list_decision_cards()
    if not cards:
        return None
    findings = repo.list_findings()
    verdicts = [str(c.verdict) for c in cards]
    run_ids = {c.run_id for c in cards if c.run_id}
    sigs: Counter[str] = Counter(
        str(f.rule_id)
        for f in findings
        if f.rule_id  # rule_id is the stable signature key
    )
    return _aggregate(verdicts, run_ids, sigs)


@lru_cache(maxsize=1)
def _from_run_dirs() -> dict[str, Any]:
    """Aggregate by re-deriving every served run's cards from disk (the offline fallback).

    Cached for the process lifetime: deriving re-runs the deterministic gate over every run dir, so
    a new run added after first call won't show until restart — an accepted demo limitation (the
    production path reads the always-current projection instead).
    """
    from api.archivist import build_run_input_from_dir

    verdicts: list[str] = []
    run_ids: set[str] = set()
    sigs: Counter[str] = Counter()
    if _DATA.is_dir():
        for d in sorted(_DATA.iterdir()):
            if not (d.is_dir() and (d / "SampleSheet.csv").exists()):
                continue
            try:
                inp = build_run_input_from_dir(d)
            except Exception:
                continue  # a malformed run dir is skipped, never a crash (tolerant boundary)
            run_ids.add(inp.run_id)
            for card in inp.cards:
                verdicts.append(card.verdict.value)
                for f in card.findings:
                    sigs[f.title or f.rule_id] += 1
    return _aggregate(verdicts, run_ids, sigs)


def historic_aggregate() -> dict[str, Any]:
    """The cross-run historic aggregate — repository first (production), run-dir derivation as the
    offline fallback. Read-only; the ``source`` field says which path answered."""
    from_repo = _from_repository()
    if from_repo is not None:
        return {**from_repo, "source": "projection"}
    return {**_from_run_dirs(), "source": "derived"}


def historic_grounding(question: str) -> tuple[str, list[ChatCitation]]:
    """Ground an archivist chat question in the cross-run history: a context string + deterministic
    citations (run ids + recurring-signature titles). Empty history → honest empty grounding."""
    agg = historic_aggregate()
    if not agg["n_runs"]:
        return "", []
    verdicts = ", ".join(f"{v}={n}" for v, n in sorted(agg["verdict_counts"].items()))
    sig_lines = "\n".join(f"- {title} ({count}x)" for title, count in agg["top_signatures"])
    context = (
        f"Historic aggregate over {agg['n_runs']} run(s), {agg['n_cards']} decision card(s) "
        f"[source: {agg['source']}].\nVerdict distribution: {verdicts}.\n"
        f"Top recurring signatures:\n{sig_lines}"
    )
    citations = [ChatCitation(kind="run", ref=rid, title=None) for rid in agg["run_ids"][:8]]
    citations += [
        ChatCitation(kind="signature", ref=title, title=title)
        for title, _ in agg["top_signatures"][:4]
    ]
    return context, citations
