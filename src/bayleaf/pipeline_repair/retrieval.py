"""Retrieval over the pipeline-repair remediation corpus — ADR-0009's "one interface".

Mirrors ``bayleaf.triage.retrieval``: the same narrow :class:`Retriever` protocol
(``retrieve(query, top_k)`` over free text) plus a **dependency-free** keyword /
token-overlap backend, here over the curated *remediation* JSONL. The tokenizer and scorer
are intentionally re-implemented rather than imported from ``triage`` so the two agent
packages stay independent siblings (the T-026 ``agents/`` consolidation is deferred); the
duplication is a small, deliberate mirror of a shipped pattern. An embedding / pgvector
backend can replace :class:`RemediationRetriever` later without the agent changing.
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib.resources import files
from typing import Protocol

from pydantic import BaseModel

from .models import RemediationEntry

# The JSONL ships as package data next to this module (see pyproject package-data).
_KNOWLEDGE_PACKAGE = "bayleaf.pipeline_repair"
_KNOWLEDGE_RESOURCE = ("knowledge", "pipeline_repair.jsonl")

# A tiny stopword set — just enough to stop generic glue words from inflating overlap.
# Kept local (no nltk dependency) since the corpus and queries are short and technical.
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "was",
        "were",
        "are",
        "its",
        "it",
        "this",
        "that",
        "not",
        "but",
        "with",
        "from",
        "may",
        "can",
        "has",
        "have",
        "than",
        "into",
        "per",
        "any",
        "all",
        "which",
        "when",
        "been",
        "being",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "or",
        "is",
        "be",
        "as",
        "at",
        "by",
        "no",
        "so",
    }
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords and 1-char tokens.

    Short technical tokens are kept deliberately (``q30``, ``i7``, ``pf``, ``prov``) — they
    carry the signal for signature retrieval; a ``rule_id`` like ``PROV-001`` becomes the
    tokens ``prov`` + ``001`` so a direct rule_id hit scores against the corpus.
    """
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2 and t not in _STOPWORDS]


class RetrievalHit(BaseModel):
    """A remediation entry with its heuristic relevance score for a query."""

    entry: RemediationEntry
    score: float


class Retriever(Protocol):
    """The single retrieval seam (ADR-0009). Swap the backend, keep this shape."""

    def retrieve(self, query: str, *, top_k: int = 3) -> list[RetrievalHit]: ...


@lru_cache(maxsize=1)
def load_remediation_corpus() -> tuple[RemediationEntry, ...]:
    """Parse the curated remediation JSONL into validated entries (cached once).

    Parsed tolerantly at the boundary (CLAUDE.md data-handling 2): blank lines and ``#``
    comment lines are skipped so the corpus file can carry section headers.
    """
    resource = files(_KNOWLEDGE_PACKAGE)
    for part in _KNOWLEDGE_RESOURCE:
        resource = resource.joinpath(part)
    entries: list[RemediationEntry] = []
    for line in resource.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.append(RemediationEntry.model_validate_json(stripped))
    return tuple(entries)


class RemediationRetriever:
    """Token-overlap retrieval over the remediation corpus (no external dependency).

    Scoring is a weighted overlap of query tokens against each entry: a match on the entry's
    ``keywords`` **or** its ``rule_ids`` (the curated signature terms) counts full weight, a
    match on title/tag/category counts half. The score is normalized by query length into
    [0, 1] so it reads as a heuristic relevance, and ties break on ``id`` for stable,
    deterministic ordering. Mirrors ``triage.retrieval.KeywordRetriever`` — kept as a separate
    class only because it indexes the different :class:`RemediationEntry` shape.
    """

    def __init__(self, entries: tuple[RemediationEntry, ...] | list[RemediationEntry]) -> None:
        self._index: list[tuple[RemediationEntry, set[str], set[str]]] = [
            (entry, *self._entry_tokens(entry)) for entry in entries
        ]

    @classmethod
    def from_default_corpus(cls) -> RemediationRetriever:
        """Build a retriever over the shipped ``pipeline_repair.jsonl`` corpus."""
        return cls(load_remediation_corpus())

    @staticmethod
    def _entry_tokens(entry: RemediationEntry) -> tuple[set[str], set[str]]:
        """(primary, secondary) token sets for an entry; secondary excludes primary.

        rule_ids join the *primary* (full-weight) set so a signature carrying the addressed
        rule_id retrieves its remediation directly, independent of the title wording.
        """
        primary: set[str] = set()
        for keyword in entry.keywords:
            primary.update(_tokenize(keyword))
        for rule_id in entry.rule_ids:
            primary.update(_tokenize(rule_id))
        secondary: set[str] = set(_tokenize(entry.title))
        for tag in entry.tags:
            secondary.update(_tokenize(tag))
        if entry.category:
            secondary.update(_tokenize(entry.category))
        return primary, secondary - primary

    def retrieve(self, query: str, *, top_k: int = 3) -> list[RetrievalHit]:
        """Return up to ``top_k`` entries whose tokens overlap the query, best first."""
        q_tokens = set(_tokenize(query))
        if not q_tokens:
            return []
        hits: list[RetrievalHit] = []
        for entry, primary, secondary in self._index:
            matched = sum(1.0 for t in q_tokens if t in primary)
            matched += sum(0.5 for t in q_tokens if t in secondary)
            if matched <= 0.0:
                continue
            score = round(matched / len(q_tokens), 4)
            hits.append(RetrievalHit(entry=entry, score=score))
        hits.sort(key=lambda h: (-h.score, h.entry.id))
        return hits[:top_k]


# Static type check: RemediationRetriever satisfies the Retriever protocol (empty index so
# this line performs no file I/O at import time).
_: Retriever = RemediationRetriever(())
