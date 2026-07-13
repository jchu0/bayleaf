"""Retrieval over the node-author tool-card corpus — ADR-0009's "one interface".

Mirrors ``bayleaf.pipeline_repair.retrieval``: the same narrow :class:`Retriever` protocol
(``retrieve(query, top_k)`` over free text) plus a **dependency-free** keyword / token-overlap
backend, here over the curated *tool-card* JSONL. The tokenizer and scorer are intentionally
re-implemented rather than imported from a sibling agent so the agent packages stay independent
(the T-026 ``agents/`` consolidation is deferred); the duplication is a small, deliberate mirror of
a shipped pattern. An embedding / pgvector backend can replace :class:`ToolCardRetriever` later
without the agent changing.
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib.resources import files

from pydantic import BaseModel

from .models import ToolCardEntry

# The JSONL ships as package data next to this module (see pyproject package-data).
_KNOWLEDGE_PACKAGE = "bayleaf.node_author"
_KNOWLEDGE_RESOURCE = ("knowledge", "tool_cards.jsonl")

# A tiny stopword set — just enough to stop generic glue words (and the ubiquitous request verbs
# "add"/"tool"/"node") from inflating overlap. Kept local (no nltk dependency) since the corpus and
# queries are short and technical.
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "was",
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
        # Request boilerplate — nearly every NL request says "add a tool/node that does …".
        "add",
        "tool",
        "node",
        "does",
        "do",
        "make",
        "create",
        "new",
        "step",
        "stage",
        "use",
        "want",
        "need",
        "please",
    }
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords and 1-char tokens.

    Short technical tokens are kept deliberately (``bwa``, ``q30``, ``bam``, ``vcf``) — they carry
    the signal for tool retrieval; a compound name like ``bwa-mem2`` becomes the tokens ``bwa`` +
    ``mem2`` so a direct tool-name hit scores against the corpus.
    """
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2 and t not in _STOPWORDS]


class RetrievalHit(BaseModel):
    """A tool-card entry with its heuristic relevance score for a query."""

    entry: ToolCardEntry
    score: float


class Retriever:
    """The single retrieval seam (ADR-0009). Swap the backend, keep this shape.

    A structural Protocol would work, but a plain base is enough here — the agent depends only on
    the ``retrieve`` shape, which :class:`ToolCardRetriever` provides.
    """

    def retrieve(self, query: str, *, top_k: int = 3) -> list[RetrievalHit]:  # pragma: no cover
        raise NotImplementedError


@lru_cache(maxsize=1)
def load_tool_card_corpus() -> tuple[ToolCardEntry, ...]:
    """Parse the curated tool-card JSONL into validated entries (cached once).

    Parsed tolerantly at the boundary (CLAUDE.md data-handling 2): blank lines and ``#`` comment
    lines are skipped so the corpus file can carry section headers.
    """
    resource = files(_KNOWLEDGE_PACKAGE)
    for part in _KNOWLEDGE_RESOURCE:
        resource = resource.joinpath(part)
    entries: list[ToolCardEntry] = []
    for line in resource.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.append(ToolCardEntry.model_validate_json(stripped))
    return tuple(entries)


class ToolCardRetriever(Retriever):
    """Token-overlap retrieval over the tool-card corpus (no external dependency).

    Scoring is a weighted overlap of query tokens against each entry: a match on the entry's
    ``keywords`` **or** its tokenized ``tool`` name (the curated tool terms) counts full weight, a
    match on title/tags/category/stage counts half. The score is normalized by query length into
    [0, 1] so it reads as a heuristic relevance, and ties break on ``id`` for stable, deterministic
    ordering. Mirrors ``pipeline_repair.retrieval.RemediationRetriever`` — kept as a separate class
    only because it indexes the different :class:`ToolCardEntry` shape.
    """

    def __init__(self, entries: tuple[ToolCardEntry, ...] | list[ToolCardEntry]) -> None:
        self._index: list[tuple[ToolCardEntry, set[str], set[str]]] = [
            (entry, *self._entry_tokens(entry)) for entry in entries
        ]

    @classmethod
    def from_default_corpus(cls) -> ToolCardRetriever:
        """Build a retriever over the shipped ``tool_cards.jsonl`` corpus."""
        return cls(load_tool_card_corpus())

    @staticmethod
    def _entry_tokens(entry: ToolCardEntry) -> tuple[set[str], set[str]]:
        """(primary, secondary) token sets for an entry; secondary excludes primary.

        The tokenized ``tool`` name joins the *primary* (full-weight) set so a request naming the
        tool (``fastp``, ``bwa-mem2``) retrieves its card directly, independent of the keyword list.
        """
        primary: set[str] = set()
        for keyword in entry.keywords:
            primary.update(_tokenize(keyword))
        primary.update(_tokenize(entry.tool))
        secondary: set[str] = set(_tokenize(entry.title))
        for tag in entry.tags:
            secondary.update(_tokenize(tag))
        if entry.category:
            secondary.update(_tokenize(entry.category))
        if entry.stage:
            secondary.update(_tokenize(entry.stage))
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


# Static type check: ToolCardRetriever satisfies the Retriever interface (empty index so this line
# performs no file I/O at import time).
_: Retriever = ToolCardRetriever(())
