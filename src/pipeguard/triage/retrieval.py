"""Retrieval over the triage knowledge corpus — ADR-0009's "one interface".

Two corpora (static *knowledge* + append-only *experience*) are meant to sit behind
ONE retrieval interface. This module ships that interface plus a **dependency-free**
keyword / token-overlap backend over the curated knowledge JSONL. The `Retriever`
protocol is deliberately narrow — ``retrieve(query, top_k)`` over free text — so an
embedding / pgvector backend can replace :class:`KeywordRetriever` later without the
agent changing. The scorer stays simple and explainable on purpose: it is a
heuristic, not a ranking model.
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib.resources import files
from typing import Protocol

from pydantic import BaseModel

from .models import KnowledgeEntry

# The JSONL ships as package data next to this module (see pyproject package-data).
_KNOWLEDGE_PACKAGE = "pipeguard.triage"
_KNOWLEDGE_RESOURCE = ("knowledge", "qc_triage.jsonl")

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

    Short technical tokens are kept deliberately (``q30``, ``20x``, ``pf``) — they
    carry the signal for QC retrieval.
    """
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2 and t not in _STOPWORDS]


class RetrievalHit(BaseModel):
    """A corpus entry with its heuristic relevance score for a query."""

    entry: KnowledgeEntry
    score: float


class Retriever(Protocol):
    """The single retrieval seam (ADR-0009). Swap the backend, keep this shape."""

    def retrieve(self, query: str, *, top_k: int = 3) -> list[RetrievalHit]: ...


@lru_cache(maxsize=1)
def load_knowledge_corpus() -> tuple[KnowledgeEntry, ...]:
    """Parse the curated knowledge JSONL into validated entries (cached once).

    Parsed tolerantly at the boundary (CLAUDE.md data-handling 2): blank lines and
    ``#`` comment lines are skipped so the corpus file can carry section headers.
    """
    resource = files(_KNOWLEDGE_PACKAGE)
    for part in _KNOWLEDGE_RESOURCE:
        resource = resource.joinpath(part)
    entries: list[KnowledgeEntry] = []
    for line in resource.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.append(KnowledgeEntry.model_validate_json(stripped))
    return tuple(entries)


class KeywordRetriever:
    """Token-overlap retrieval over the knowledge corpus (no external dependency).

    Scoring is a weighted overlap of query tokens against each entry: a match on the
    entry's `keywords` (the curated signature terms) counts full weight, a match on
    title/tag/category counts half. The score is normalized by query length into
    [0, 1] so it reads as a heuristic relevance, and ties break on `id` for stable,
    deterministic ordering.
    """

    def __init__(self, entries: tuple[KnowledgeEntry, ...] | list[KnowledgeEntry]) -> None:
        self._index: list[tuple[KnowledgeEntry, set[str], set[str]]] = [
            (entry, *self._entry_tokens(entry)) for entry in entries
        ]

    @classmethod
    def from_default_corpus(cls) -> KeywordRetriever:
        """Build a retriever over the shipped ``qc_triage.jsonl`` corpus."""
        return cls(load_knowledge_corpus())

    @staticmethod
    def _entry_tokens(entry: KnowledgeEntry) -> tuple[set[str], set[str]]:
        """(primary, secondary) token sets for an entry; secondary excludes primary."""
        primary: set[str] = set()
        for keyword in entry.keywords:
            primary.update(_tokenize(keyword))
        secondary: set[str] = set(_tokenize(entry.title))
        for tag in entry.tags:
            secondary.update(_tokenize(tag))
        if entry.category:
            secondary.update(_tokenize(entry.category))
        return primary, secondary - primary

    def retrieve(self, query: str, *, top_k: int = 3) -> list[RetrievalHit]:
        """Return up to `top_k` entries whose tokens overlap the query, best first."""
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


# Static type check: KeywordRetriever satisfies the Retriever protocol (empty index
# so this line performs no file I/O at import time).
_: Retriever = KeywordRetriever(())
