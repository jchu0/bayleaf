"""Advisory feedback-categorization agent (W12 / #3b) — OFF the deterministic gate.

Mirrors the QC-triage agent (ADR-0009/0012): stub-first ($0, offline, deterministic) with an
opt-in Claude path that falls back to the stub on ANY error. It reads the feedback corpus (the
:class:`~api.feedback_store.FeedbackStore`) and emits a STRUCTURED assessment — per-item
category / area / sentiment / priority + an aggregate rollup + recurring themes — to guide
product iteration. Advisory only: it never touches a verdict, a finding, or the decision
projection (feedback is off-gate telemetry, ADR-0001).

Env: ``PIPEGUARD_FEEDBACK_AGENT`` = "stub" (default) | "claude"; ``PIPEGUARD_FEEDBACK_MODEL``
default ``claude-haiku-4-5-20251001`` (categorization is a cheap, high-volume task, ADR-0012).

PII posture: the deterministic categorization uses only the structured fields; the Claude path
is sent ONLY the aggregate rollup (counts + category/area pairs) — never the raw free-text
messages — so an operator-typed note is never egressed to the API. There is no HTTP surface:
run out-of-band via ``python -m api.feedback_agent`` (telemetry never re-enters a view).
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from .feedback_store import get_feedback_store

FEEDBACK_TRIAGE_AGENT = "feedback_triage"
_DEFAULT_FEEDBACK_MODEL = "claude-haiku-4-5-20251001"  # cheap tier — high-volume categorization

# reason_code / kind → structural category. Decision signals with no reason_code fall through
# to the signal-based default in `_categorize_one`.
_REASON_CATEGORY = {
    "threshold_too_strict": "threshold_tuning",
    "threshold_too_loose": "threshold_tuning",
    "wrong_root_cause": "root_cause",
    "missing_context": "missing_context",
    "other": "other",
}
_KIND_CATEGORY = {
    "confusing": "usability",
    "problem": "bug",
    "idea": "feature_request",
    "praise": "praise",
}
_KIND_SENTIMENT = {
    "confusing": "negative",
    "problem": "negative",
    "idea": "neutral",
    "praise": "positive",
}


class FeedbackAssessmentItem(BaseModel):
    """One categorized feedback record (advisory)."""

    feedback_id: str
    source: str | None = None
    category: str
    area: str
    sentiment: Literal["positive", "negative", "neutral"]
    priority: Literal["low", "medium", "high"]
    summary: str


class FeedbackAssessment(BaseModel):
    """The agent's advisory rollup over the feedback corpus. `advisory` is pinned True and
    there is deliberately no verdict/priority-override that feeds a decision — this guides
    product iteration, nothing on the gate."""

    advisory: bool = True
    agent: str = FEEDBACK_TRIAGE_AGENT
    generated_by: str = "stub"
    model: str | None = None
    n_total: int = 0
    items: list[FeedbackAssessmentItem] = []
    by_category: dict[str, int] = {}
    by_area: dict[str, int] = {}
    by_sentiment: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    themes: list[str] = []
    disclaimer: str = "Advisory heuristics for product iteration — not calibrated, not clinical."


def _area_of(ctx: dict[str, Any], target: str | None) -> str:
    """The surface a reaction pertains to: the flagged gate for decision feedback, else the
    screen it came from (falling back to the route or 'general')."""
    if target == "decision" and ctx.get("gate"):
        return f"{ctx['gate']} gate"
    return str(ctx.get("screen") or ctx.get("route") or "general")


def _categorize_one(record: dict[str, Any]) -> FeedbackAssessmentItem:
    """Deterministic categorization from the structured fields only (no message parsing)."""
    ctx = record.get("context") or {}
    target = record.get("target")
    if target == "product":
        kind = record.get("kind") or "other"
        category = _KIND_CATEGORY.get(kind, "other")
        sentiment: Literal["positive", "negative", "neutral"] = _KIND_SENTIMENT.get(kind, "neutral")  # type: ignore[assignment]
        priority = "high" if kind == "problem" else ("medium" if kind == "confusing" else "low")
    else:  # decision
        reason = record.get("reason_code")
        signal = record.get("signal")
        category = _REASON_CATEGORY.get(reason or "", "praise" if signal == "agree" else "other")
        sentiment = (
            "positive" if signal == "agree" else "negative" if signal == "disagree" else "neutral"
        )
        # A downvote on a blocking verdict (escalate/rerun) is the most actionable signal.
        verdict = ctx.get("verdict")
        if signal == "disagree" and verdict in ("escalate", "rerun"):
            priority = "high"
        elif signal == "disagree":
            priority = "medium"
        else:
            priority = "low"
    area = _area_of(ctx, target)
    rated = record.get("signal") or record.get("kind")
    summary = f"{category} · {area}" + (f" · {rated}" if rated else "")
    return FeedbackAssessmentItem(
        feedback_id=str(record.get("id") or "unknown"),
        source=record.get("source"),
        category=category,
        area=area,
        sentiment=sentiment,
        priority=priority,
        summary=summary,
    )


def _rollup(items: list[FeedbackAssessmentItem]) -> dict[str, dict[str, int]]:
    return {
        "by_category": dict(Counter(i.category for i in items)),
        "by_area": dict(Counter(i.area for i in items)),
        "by_sentiment": dict(Counter(i.sentiment for i in items)),
        "by_priority": dict(Counter(i.priority for i in items)),
    }


def _deterministic_themes(items: list[FeedbackAssessmentItem]) -> list[str]:
    """Recurring (category, area) pairs, most-frequent first — the offline theme list."""
    pairs = Counter((i.category, i.area) for i in items)
    return [f"{cat} on {area} ({n}x)" for (cat, area), n in pairs.most_common(6) if n >= 2]


class FeedbackAgent(Protocol):
    name: str

    def assess(self, records: list[dict[str, Any]]) -> FeedbackAssessment: ...


class StubFeedbackAgent:
    """Deterministic, zero-cost categorization — the default and the fallback."""

    name = "stub"

    def assess(self, records: list[dict[str, Any]]) -> FeedbackAssessment:
        items = [_categorize_one(r) for r in records]
        roll = _rollup(items)
        return FeedbackAssessment(
            generated_by=self.name,
            model=None,
            n_total=len(items),
            items=items,
            themes=_deterministic_themes(items),
            **roll,
        )


_SYSTEM = (
    "You are a product analyst for an internal genomics-QC decision-gate tool. You are given an "
    "ANONYMOUS, AGGREGATED rollup of in-app feedback (counts by category/area/sentiment/priority "
    "— no user text, no identities). Produce a short, prioritized list of the concrete product "
    "themes to act on next. Rules: ground every theme in the provided counts; do not invent "
    "numbers or specifics; be concise; make no clinical claims."
)
_THEMES_SCHEMA = {
    "type": "object",
    "properties": {"themes": {"type": "array", "items": {"type": "string"}}},
    "required": ["themes"],
    "additionalProperties": False,
}


class ClaudeFeedbackAgent:
    """Opt-in live categorization — OFF by default. The deterministic categorization stays
    (grounding); Claude is asked ONLY for a prioritized `themes` narrative, and is sent ONLY the
    aggregate rollup (never raw messages). Any API error falls back to the stub."""

    name = "claude"

    def __init__(self, model: str | None = None, max_tokens: int = 512) -> None:
        self.model = model or os.environ.get("PIPEGUARD_FEEDBACK_MODEL", _DEFAULT_FEEDBACK_MODEL)
        self.max_tokens = max_tokens
        self._fallback = StubFeedbackAgent()
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic  # lazy: package works without anthropic installed

            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:
                pass
            self._client = anthropic.Anthropic()
        return self._client

    def assess(self, records: list[dict[str, Any]]) -> FeedbackAssessment:
        base = self._fallback.assess(records)
        if base.n_total == 0:
            return base
        try:
            # PII-safe payload: only the aggregate counts + the (category, area, priority)
            # triples — never a raw message or an id.
            payload = {
                "by_category": base.by_category,
                "by_area": base.by_area,
                "by_sentiment": base.by_sentiment,
                "by_priority": base.by_priority,
                "items": [
                    {"category": i.category, "area": i.area, "priority": i.priority}
                    for i in base.items
                ],
            }
            client = self._get_client()
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM,
                messages=[{"role": "user", "content": json.dumps(payload, indent=2)}],
                output_config={"format": {"type": "json_schema", "schema": _THEMES_SCHEMA}},
            )
            if response.stop_reason == "refusal":
                return base
            text = next((b.text for b in response.content if b.type == "text"), None)
            if not text:
                return base
            themes = json.loads(text).get("themes") or base.themes
            return base.model_copy(
                update={"generated_by": self.name, "model": self.model, "themes": themes}
            )
        except Exception:
            return base  # never let a live-API problem break the advisory path


def get_feedback_agent() -> FeedbackAgent:
    """Select the feedback agent from the environment (default: the zero-cost stub)."""
    choice = os.environ.get("PIPEGUARD_FEEDBACK_AGENT", "stub").strip().lower()
    if choice == "claude":
        return ClaudeFeedbackAgent()
    return StubFeedbackAgent()


def assess_feedback(
    records: list[dict[str, Any]], agent: FeedbackAgent | None = None
) -> FeedbackAssessment:
    """Advisory structural assessment of the feedback corpus (mirrors `triage_card`)."""
    return (agent or get_feedback_agent()).assess(records)


def main(argv: list[str] | None = None) -> int:
    """Read the feedback store + print the advisory assessment (out-of-band; no HTTP surface)."""
    parser = argparse.ArgumentParser(
        prog="python -m api.feedback_agent",
        description="Advisory structural categorization of the in-app feedback corpus (off-gate).",
    )
    parser.add_argument("--json", action="store_true", help="emit the full assessment as JSON.")
    args = parser.parse_args(argv)

    assessment = assess_feedback(get_feedback_store().read_all())
    if args.json:
        print(assessment.model_dump_json(indent=2))
        return 0
    print(f"Feedback assessment ({assessment.generated_by}) — {assessment.n_total} item(s)")
    if assessment.n_total:
        print(f"  by category : {assessment.by_category}")
        print(f"  by priority : {assessment.by_priority}")
        print(f"  by sentiment: {assessment.by_sentiment}")
        if assessment.themes:
            print("  themes:")
            for t in assessment.themes:
                print(f"    - {t}")
    print(f"  ({assessment.disclaimer})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
