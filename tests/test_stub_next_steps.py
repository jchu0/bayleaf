"""The stub synthesizer must emit NO fabricated per-verdict advice (WS-07 Q1).

Decision-card ``next_steps`` used to be hardcoded per-verdict boilerplate in
``synthesis/stub.py`` (``_NEXT_STEPS[verdict]``) — the $0 default. That is dishonest
filler: the stub cannot know a run's real remediation, so it invented one. The honest
deterministic fallback (ADR-0006) is to emit NO next_steps at all; the operator is pointed
at the REAL artifacts instead — the QC HTML reports + the Metric·Observed·Threshold·Status
readout the API surfaces (``api/card_readout.py``). The live Claude path still authors real,
grounded next_steps (``synthesis/claude.py``); only the stub stops fabricating them.

These tests freeze that gap so it can't silently reopen (anti-scaffold), and pin the
ADR-0001 invariant: narration never moves the verdict.
"""

from __future__ import annotations

from pipeguard.models import Category, Finding, RunArtifacts, Severity, Verdict
from pipeguard.synthesis.base import aggregate_verdict
from pipeguard.synthesis.stub import StubSynthesizer

# The exact boilerplate strings the retired ``_NEXT_STEPS`` table emitted. If ANY of these
# reappears on a stub card, the fabricated-advice regression has reopened.
_BANNED = (
    "Release sample to downstream analysis.",
    "Have a reviewer confirm the borderline",
    "Release or rerun once a human signs off.",
    "Requeue the sample for resequencing",
    "Confirm the upstream failure is resolved",
    "Do not release. Notify the lab lead",
    "Reconcile the sample sheet, barcode manifest",
)


def _finding(verdict: Verdict) -> Finding:
    """A minimal finding whose suggested verdict drives the card's aggregated verdict."""
    return Finding(
        rule_id="TEST-001",
        sample_id="SX",
        category=Category.QC,
        severity=Severity.WARN,
        title="test finding",
        detail="synthetic finding to drive the verdict",
        suggested_verdict=verdict,
    )


def _findings_for(verdict: Verdict) -> list[Finding]:
    # PROCEED is the empty-findings case (aggregate_verdict([]) == PROCEED); the others each
    # carry one finding suggesting that verdict.
    return [] if verdict is Verdict.PROCEED else [_finding(verdict)]


def test_stub_emits_no_boilerplate_next_steps() -> None:
    """For EVERY verdict, the stub card carries an empty ``next_steps`` and none of the retired
    boilerplate anywhere on the card (headline / rationale / next_steps)."""
    stub = StubSynthesizer()
    artifacts = RunArtifacts(run_id="R")
    for verdict in Verdict:
        card = stub.synthesize("SX", _findings_for(verdict), artifacts)
        assert card.generated_by == "stub"
        # No fabricated advice — the honest deterministic fallback emits nothing.
        assert card.next_steps == [], f"{verdict}: stub must not fabricate next_steps"
        blob = " ".join([card.headline, card.rationale, *card.next_steps])
        for banned in _BANNED:
            assert banned not in blob, f"{verdict}: banned boilerplate resurfaced: {banned!r}"


def test_stub_verdict_is_narration_independent() -> None:
    """ADR-0001: the verdict is a deterministic function of the findings, unchanged by the
    narration edit — the stub card's verdict always equals ``aggregate_verdict(findings)``."""
    stub = StubSynthesizer()
    artifacts = RunArtifacts(run_id="R")
    for verdict in Verdict:
        findings = _findings_for(verdict)
        card = stub.synthesize("SX", findings, artifacts)
        assert card.verdict is aggregate_verdict(findings) is verdict
