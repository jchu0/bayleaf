"""Deterministic, zero-cost synthesizer.

Produces a fully-formed DecisionCard from the rule findings without any API call.
It is the default synthesizer so the whole app runs (and demos) offline, and it
doubles as the ground truth the live ClaudeSynthesizer is checked against.

The prose here is templated and GROUNDED — `headline`/`rationale` restate the
cited findings, nothing more. The Claude path improves that prose *and* authors
real, grounded `next_steps`; the verdict and findings stay identical (from the
shared grounding helpers). Confidence is omitted (T-019).

WHY the stub emits NO `next_steps` (WS-07 Q1): the deterministic fallback cannot
know a run's real remediation, so any per-verdict advice it printed would be
fabricated boilerplate — dishonest filler that reads like a recommendation but
stands on nothing (ADR-0001 keeps AI/heuristics out of the decision; the same
honesty applies to advice). The honest AI-off default (ADR-0006) is to point the
operator at the REAL artifacts instead: the QC HTML reports (fastp.html /
multiqc_report.html) and the Metric·Observed·Threshold·Status readout the API
surfaces (`api/card_readout.py`). So the stub leaves `next_steps` empty; only the
live Claude path (`synthesis/claude.py`) fills it, with grounded, run-specific steps.
"""

from __future__ import annotations

from ..models import Category, CheckCoverage, DecisionCard, Finding, RunArtifacts, Verdict
from .base import Synthesizer, aggregate_verdict, top_finding

_VERDICT_HEADLINE = {
    Verdict.PROCEED: "Clear to proceed",
    Verdict.HOLD: "Hold for operator review",
    Verdict.RERUN: "Recommend rerun",
    Verdict.ESCALATE: "Escalate — provenance risk",
}


def _and_list(items: list[str]) -> str:
    """Join labels for prose: ['a']→'a'; ['a','b']→'a and b'; ['a','b','c']→'a, b, and c'."""
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


class StubSynthesizer:
    name = "stub"

    def synthesize(
        self,
        sample_id: str,
        findings: list[Finding],
        artifacts: RunArtifacts,
        coverage: CheckCoverage | None = None,
    ) -> DecisionCard:
        verdict = aggregate_verdict(findings)
        lead = top_finding(findings)

        if lead is None:
            # HONEST clean-card prose (WS-01 Gap B): a clean sample "raised no findings from the
            # checks that RAN" — never "all checks passed", because contamination/identity are not
            # examined today. The counts come from the deterministic CheckCoverage, not the prose.
            if coverage is not None:
                ran_labels = _and_list([c.value for c in coverage.categories_ran])
                headline = (
                    f"{_VERDICT_HEADLINE[verdict]} — "
                    f"{coverage.checks_ran}/{coverage.checks_expected} check categories ran"
                )
                rationale = (
                    f"{sample_id} raised no findings from the {coverage.checks_ran} check "
                    f"categories that ran ({ran_labels})."
                )
                if coverage.not_examined:
                    n = len(coverage.not_examined)
                    rationale += (
                        f" {_and_list(coverage.not_examined)} {'was' if n == 1 else 'were'} not "
                        f"examined — no check for {'it' if n == 1 else 'them'} exists yet, so this "
                        f"is not a blanket clearance."
                    )
            else:
                # Back-compat when a caller invokes synthesize without coverage: still honest.
                headline = f"{_VERDICT_HEADLINE[verdict]} — no rule objected"
                rationale = (
                    f"{sample_id} raised no findings from the checks that ran. This reflects the "
                    f"checks examined, not a verified clearance of every category."
                )
        else:
            headline = f"{_VERDICT_HEADLINE[verdict]} — {lead.title.lower()}"
            crit = [f for f in findings if f.severity.value == "critical"]
            warn = [f for f in findings if f.severity.value == "warn"]
            parts = [f"{sample_id}: {lead.detail}"]
            if len(crit) + len(warn) > 1:
                others = [f for f in findings if f is not lead]
                by_cat: dict[Category, int] = {}
                for f in others:
                    by_cat[f.category] = by_cat.get(f.category, 0) + 1
                summary = ", ".join(f"{n} {c.value}" for c, n in by_cat.items())
                parts.append(f"Additional signals: {summary}.")
            # A brief honest coverage tail so even a flagged card names what was NOT examined.
            if coverage is not None and coverage.not_examined:
                parts.append(
                    f"Coverage: {coverage.checks_ran}/{coverage.checks_expected} categories ran; "
                    f"{_and_list(coverage.not_examined)} not examined."
                )
            rationale = " ".join(parts)

        return DecisionCard(
            sample_id=sample_id,
            verdict=verdict,
            headline=headline,
            rationale=rationale,
            # No fabricated advice — the honest AI-off fallback (see module docstring). The API
            # surfaces the real QC reports + metric readout; the live Claude path fills this in.
            next_steps=[],
            findings=findings,
            generated_by=self.name,
        )


# Static type check: StubSynthesizer satisfies the Synthesizer protocol.
_: Synthesizer = StubSynthesizer()
