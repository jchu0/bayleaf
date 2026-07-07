"""Live Claude synthesizer — the integration point, OFF by default.

Nothing here runs unless `PIPEGUARD_SYNTHESIZER=claude` is set (see
`pipeguard.engine.get_synthesizer`), so it consumes zero API credits during
normal development. When enabled, it sends the rule engine's findings plus a
compact artifact context to Claude and gets back operator-readable narration.

Design guarantees that keep it safe and cheap to flip on:
  * The verdict and confidence are STILL computed deterministically from the
    findings (via the shared grounding helpers) — Claude only writes prose.
    The model cannot override the gate.
  * `anthropic` is imported lazily, so the package installs and runs without it.
  * Any API error (including a safety `refusal`) falls back to StubSynthesizer,
    so a flaky conference network can never break the demo.

Model + cost knobs (env):
  PIPEGUARD_CLAUDE_MODEL   default "claude-opus-4-8". For a hackathon on limited
                           credits, "claude-sonnet-5" or "claude-haiku-4-5" cut
                           cost substantially — see README for the price table.
"""

from __future__ import annotations

import json
import os

from ..models import DecisionCard, Finding, RunArtifacts
from .base import Synthesizer, aggregate_verdict, derive_confidence
from .stub import StubSynthesizer

# JSON schema for the *narration only*. Verdict/confidence/findings are not the
# model's to decide, so they are deliberately absent here.
_NARRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "rationale": {"type": "string"},
        "next_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "rationale", "next_steps"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are the analyst behind an AI-assisted provenance and QC decision gate for a "
    "genomics sequencing run. A deterministic rule engine has already evaluated one "
    "sample and produced a verdict plus a list of cited findings. Your job is to write "
    "the operator-facing decision card: a one-line headline, a short rationale, and "
    "concrete next steps.\n\n"
    "Rules you must follow:\n"
    "- The verdict is fixed; explain it, never contradict or re-decide it.\n"
    "- Ground every statement in the findings and artifact context provided. Do not "
    "invent metric values, IDs, or thresholds that are not present.\n"
    "- Write for a lab operator who must act: be specific and concise, no preamble.\n"
    "- If a barcode/ID or provenance issue is present, treat chain of custody as the "
    "priority concern."
)


class ClaudeSynthesizer:
    name = "claude"

    def __init__(self, model: str | None = None, max_tokens: int = 8192) -> None:
        self.model = model or os.environ.get("PIPEGUARD_CLAUDE_MODEL", "claude-opus-4-8")
        self.max_tokens = max_tokens
        self._fallback = StubSynthesizer()
        self._client = None  # created lazily on first use

    def _get_client(self):
        if self._client is None:
            import anthropic  # lazy: package works without anthropic installed

            self._client = anthropic.Anthropic()  # resolves credentials from env
        return self._client

    def _sample_context(self, sample_id: str, artifacts: RunArtifacts) -> dict:
        """A compact, model-friendly snapshot of one sample's raw artifacts."""
        meta = next((s for s in artifacts.samples if s.sample_id == sample_id), None)
        sheet = next((e for e in artifacts.sample_sheet if e.sample_id == sample_id), None)
        demux = next((d for d in artifacts.demux if d.sample_id == sample_id), None)
        qc = next((q for q in artifacts.qc if q.sample_id == sample_id), None)
        log_hits = [ln for ln in artifacts.log_lines if sample_id in ln][:8]
        return {
            "run_id": artifacts.run_id,
            "sample_id": sample_id,
            "metadata": meta.model_dump(exclude_none=True) if meta else None,
            "sample_sheet": sheet.model_dump(exclude_none=True) if sheet else None,
            "demux": demux.model_dump(exclude_none=True) if demux else None,
            "qc": qc.model_dump(exclude_none=True) if qc else None,
            "log_excerpts": log_hits,
        }

    def synthesize(
        self, sample_id: str, findings: list[Finding], artifacts: RunArtifacts
    ) -> DecisionCard:
        # Verdict + confidence stay deterministic — Claude never touches them.
        verdict = aggregate_verdict(findings)
        confidence = derive_confidence(findings, verdict)

        payload = {
            "verdict": verdict.value,
            "findings": [f.model_dump() for f in findings],
            "artifact_context": self._sample_context(sample_id, artifacts),
        }
        user_content = (
            f"Sample {sample_id} — the rule engine returned verdict '{verdict.value}'.\n\n"
            f"Findings and artifact context (JSON):\n{json.dumps(payload, indent=2)}\n\n"
            "Write the decision card narration as JSON matching the required schema."
        )

        try:
            client = self._get_client()
            # No `thinking` param: safe across opus-4-8 (off), sonnet-5 (adaptive),
            # and fable-5 (always on). output_config.format guarantees JSON text.
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
                output_config={"format": {"type": "json_schema", "schema": _NARRATION_SCHEMA}},
            )
            # Guard the refusal path before reading content (Fable 5 classifiers can
            # false-positive on life-sciences work; other models can refuse too).
            if response.stop_reason == "refusal":
                return self._fallback.synthesize(sample_id, findings, artifacts)

            text = next((b.text for b in response.content if b.type == "text"), None)
            if not text:
                return self._fallback.synthesize(sample_id, findings, artifacts)
            narration = json.loads(text)

            return DecisionCard(
                sample_id=sample_id,
                verdict=verdict,
                confidence=confidence,
                headline=narration["headline"],
                rationale=narration["rationale"],
                next_steps=list(narration.get("next_steps", [])),
                findings=findings,
                generated_by=self.name,
            )
        except Exception:
            # Never let a live-API problem break the gate mid-demo.
            return self._fallback.synthesize(sample_id, findings, artifacts)


# Static type check: ClaudeSynthesizer satisfies the Synthesizer protocol.
_: Synthesizer = ClaudeSynthesizer()
