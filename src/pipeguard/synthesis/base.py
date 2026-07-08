"""Synthesizer interface + grounding helpers shared by every implementation.

The `Synthesizer` protocol is the single seam between the deterministic core and
the narration layer. Today `StubSynthesizer` fills it (no API cost); flip
`PIPEGUARD_SYNTHESIZER=claude` to use `ClaudeSynthesizer` for demo/testing.

`aggregate_verdict` and `derive_confidence` live here — NOT inside any one
synthesizer — because the verdict must be a deterministic function of the rule
findings even when Claude writes the prose. The live path uses these as a
guardrail so the model can phrase the rationale but cannot override the gate.
"""

from __future__ import annotations

from typing import Protocol

from ..models import DecisionCard, Finding, RunArtifacts, Severity, Verdict

# Higher rank wins when a sample trips multiple rules.
_VERDICT_RANK = {
    Verdict.PROCEED: 0,
    Verdict.HOLD: 1,
    Verdict.RERUN: 2,
    Verdict.ESCALATE: 3,
}


def aggregate_verdict(findings: list[Finding]) -> Verdict:
    """The run's verdict is the most severe verdict any finding suggests."""
    if not findings:
        return Verdict.PROCEED
    return max((f.suggested_verdict for f in findings), key=lambda v: _VERDICT_RANK[v])


def top_finding(findings: list[Finding]) -> Finding | None:
    """The single most decision-relevant finding, for headline generation."""
    if not findings:
        return None
    sev_rank = {Severity.CRITICAL: 2, Severity.WARN: 1, Severity.INFO: 0}
    return max(
        findings,
        key=lambda f: (_VERDICT_RANK[f.suggested_verdict], sev_rank[f.severity]),
    )


class Synthesizer(Protocol):
    """Turns rule findings + raw artifacts into an operator-facing DecisionCard."""

    name: str

    def synthesize(
        self, sample_id: str, findings: list[Finding], artifacts: RunArtifacts
    ) -> DecisionCard: ...
