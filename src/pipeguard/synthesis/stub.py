"""Deterministic, zero-cost synthesizer.

Produces a fully-formed DecisionCard from the rule findings without any API call.
It is the default synthesizer so the whole app runs (and demos) offline, and it
doubles as the ground truth the live ClaudeSynthesizer is checked against.

The prose here is templated. The *only* thing the Claude path changes is the
quality of `headline`, `rationale`, and `next_steps`; verdict/confidence/findings
stay identical because they come from the shared grounding helpers.
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

_NEXT_STEPS = {
    Verdict.PROCEED: ["Release sample to downstream analysis."],
    Verdict.HOLD: [
        "Have a reviewer confirm the borderline metric(s) below against project requirements.",
        "Release or rerun once a human signs off.",
    ],
    Verdict.RERUN: [
        "Requeue the sample for resequencing / reprocessing.",
        "Confirm the upstream failure is resolved before rerun.",
    ],
    Verdict.ESCALATE: [
        "Do not release. Notify the lab lead / provenance owner.",
        "Reconcile the sample sheet, barcode manifest, and LIMS record before any decision.",
    ],
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
            next_steps=list(_NEXT_STEPS[verdict]),
            findings=findings,
            generated_by=self.name,
        )


# Static type check: StubSynthesizer satisfies the Synthesizer protocol.
_: Synthesizer = StubSynthesizer()
