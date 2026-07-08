# ADR-0009 — Knowledge + experience corpora, retrieval-based upskilling

| Field | Value |
|---|---|
| **Status** | Accepted · Partially realized (knowledge corpus + one keyword-retrieval interface built; experience ledger deferred) |
| **Date** | 2026-07-07 (MST) · updated 2026-07-08 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0007](ADR-0007-ml-ready-structured-outputs.md), [ADR-0008](ADR-0008-issue-taxonomy-suppression-escalation.md), [ADR-0012](ADR-0012-agent-scoping-model-tiering.md), [data/schemas.md](../data/schemas.md) |

## Context

The triage agent needs two kinds of grounding to cut diagnosis time: static tool
knowledge, and the lab's own history of what fixed what. It should also improve
over time without the cost and evaluation burden of model training.

## Decision

1. Two corpora behind **one retrieval interface**:
   a. **Knowledge** (static, curated): tool docs, QC-metric definitions, failure
      signatures, the runbook.
   b. **Experience** (append-only ledger): `issue → diagnosis → action → outcome`,
      seeded from synthetic failure cases.
2. Stored as **JSON/JSONL**, pydantic-validated, ML-ready per ADR-0007.
3. **"Upskilling" = retrieval** over the experience ledger, **not** fine-tuning.
4. Retrieval starts simple (BM25 / small embedding index); pgvector later.

## Assumptions

- Retrieval delivers the "learns from history" value without training.
- JSONL scales for the MVP's corpus size.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Fine-tune a model now | Cost, complexity, and no way to evaluate it in the sprint |
| One combined corpus | Conflates stable knowledge with dynamic, lab-specific experience |

## Consequences

| | |
|---|---|
| **Gains** | Grounded, improving triage; the corpora double as ML-ready data |
| **Costs** | A retrieval interface and ongoing corpus curation |
| **Follow-ups** | Record schemas finalized in the schema discussion; fine-tuning (LoRA on an open-weight model) is a documented future option |

## Realized (2026-07-08)

1. **Knowledge corpus + the "one retrieval interface" built.** `triage/retrieval.py` ships a
   narrow `Retriever` protocol (`retrieve(query, top_k)`) plus a dependency-free
   `KeywordRetriever` over a curated knowledge JSONL (`triage/knowledge/qc_triage.jsonl`),
   validated by pydantic and consumed by the QC-triage agent
   ([ADR-0012](ADR-0012-agent-scoping-model-tiering.md)). The narrow protocol is exactly the seam
   a BM25 / embedding / pgvector backend swaps into later.
2. **Deferred (unchanged):** the append-only *experience* ledger
   (`issue → diagnosis → action → outcome`) and its retrieval — "upskilling = retrieval, not
   fine-tuning" still holds; the experience corpus lands with the ticket/resolution loop
   ([ADR-0008](ADR-0008-issue-taxonomy-suppression-escalation.md), schemas.md §14).

## Revisit when

- Retrieval quality plateaus and fine-tuning is justified, or corpus size needs a vector DB.
