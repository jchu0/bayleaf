"""Synthesis layer: the swappable seam between deterministic rules and narration."""

from .base import Synthesizer, aggregate_verdict
from .claude import ClaudeSynthesizer
from .stub import StubSynthesizer

__all__ = [
    "ClaudeSynthesizer",
    "StubSynthesizer",
    "Synthesizer",
    "aggregate_verdict",
]
