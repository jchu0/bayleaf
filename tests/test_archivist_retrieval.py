"""Archivist read-only historic retrieval (ADR-0024 / P3, design/agent-capabilities.md §1), offline.

Pins the guarantees: the aggregate has the expected shape, it derives real cross-run history from
the served run dirs when the projection is empty (the demo default), grounding is non-empty + cited,
and the archivist chat grounds a run-independent question in that history. Read-only, no PII.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from api.agent_chat import ask_system_agent
from api.archivist_retrieval import _aggregate, historic_aggregate, historic_grounding


def test_aggregate_shape() -> None:
    agg = _aggregate(
        verdicts=["proceed", "proceed", "hold"],
        run_ids={"RUN-A", "RUN-B"},
        sigs=Counter({"Low coverage": 3, "Barcode mismatch": 1}),
    )
    assert agg["n_runs"] == 2 and agg["n_cards"] == 3
    assert agg["verdict_counts"] == {"proceed": 2, "hold": 1}
    assert agg["top_signatures"][0] == ("Low coverage", 3)  # most common first
    assert agg["run_ids"] == ["RUN-A", "RUN-B"]


def test_historic_aggregate_derives_real_cross_run_history() -> None:
    """With an empty projection (default :memory:), it derives from the committed run dirs."""
    agg = historic_aggregate()
    assert agg["source"] in ("projection", "derived")
    assert agg["n_runs"] >= 1  # the repo ships many committed run fixtures
    assert agg["verdict_counts"]  # at least one verdict tallied
    assert sum(agg["verdict_counts"].values()) == agg["n_cards"]


def test_historic_grounding_is_nonempty_and_cited() -> None:
    context, citations = historic_grounding("how many runs have findings?")
    assert "run(s)" in context and "Verdict distribution" in context
    assert citations and any(c.kind == "run" for c in citations)


def test_archivist_chat_grounds_in_history_without_a_run(monkeypatch: Any) -> None:
    """A run-independent archivist question grounds in the cross-run aggregate (stub path, no live
    API): the reply is advisory, stub-generated, and cited."""
    monkeypatch.delenv("BAYLEAF_ARCHIVIST_AGENT", raising=False)  # force the offline stub
    reply = ask_system_agent("archivist", "which recurring issues show up most often?", {})
    assert reply.role == "agent" and reply.generated_by == "stub" and reply.model is None
    assert reply.citations  # grounded in the historic aggregate
    assert "verdict" not in reply.model_dump()  # advisory only (ADR-0001)
