"""Synthesis layer: the swappable seam between deterministic rules and narration."""

from .base import Synthesizer, aggregate_verdict, derive_confidence
from .claude import ClaudeSynthesizer
from .stub import StubSynthesizer

__all__ = [
    "ClaudeSynthesizer",
    "StubSynthesizer",
    "Synthesizer",
    "aggregate_verdict",
    "derive_confidence",
]
