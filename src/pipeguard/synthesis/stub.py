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

from ..models import Category, DecisionCard, Finding, RunArtifacts, Verdict
from .base import Synthesizer, aggregate_verdict, top_finding

_VERDICT_HEADLINE = {
    Verdict.PROCEED: "Clear to proceed",
    Verdict.HOLD: "Hold for operator review",
    Verdict.RERUN: "Recommend rerun",
    Verdict.ESCALATE: "Escalate — provenance risk",
}


class StubSynthesizer:
    name = "stub"

    def synthesize(
        self, sample_id: str, findings: list[Finding], artifacts: RunArtifacts
    ) -> DecisionCard:
        verdict = aggregate_verdict(findings)
        lead = top_finding(findings)

        if lead is None:
            headline = f"{_VERDICT_HEADLINE[verdict]} — all checks passed"
            rationale = (
                f"{sample_id} cleared every provenance, metadata, and QC check in the "
                f"runbook. No inconsistencies were found across the intake sheet, sample "
                f"sheet, demultiplexing stats, QC metrics, or run log."
            )
        else:
            headline = f"{_VERDICT_HEADLINE[verdict]} — {lead.title.lower()}"
            crit = [f for f in findings if f.severity.value == "critical"]
            warn = [f for f in findings if f.severity.value == "warn"]
            parts = [
                f"{sample_id}: {lead.detail}",
            ]
            if len(crit) + len(warn) > 1:
                others = [f for f in findings if f is not lead]
                by_cat: dict[Category, int] = {}
                for f in others:
                    by_cat[f.category] = by_cat.get(f.category, 0) + 1
                summary = ", ".join(f"{n} {c.value}" for c, n in by_cat.items())
                parts.append(f"Additional signals: {summary}.")
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
