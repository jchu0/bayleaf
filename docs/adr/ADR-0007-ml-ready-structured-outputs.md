# ADR-0007 — ML-ready structured outputs

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-07 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | ADR-0002, ADR-0004 |

## Context

Provenance and logging in this project are not only for audit and human review.
Clean, correctly structured, labeled data is the substrate for downstream ML: the
experience ledger is training data for triage; QC records are features for a
future confidence model; read/QC profiles feed the wishlisted vector-QC work.
Structured output here has a purpose, not just an aesthetic.

## Decision

Design all machine outputs to be **ML-ready** from the start: the provenance
ledger, experience ledger, decision cards, and QC records are emitted as typed,
**schema-versioned**, consistently **labeled** JSON/JSONL (origin `real-giab` vs
`synthetic`, verdict, findings, resolution outcomes), validated by pydantic.
Free-text is allowed alongside structured fields, never as the only
representation. Append-only logs are one record per line (JSONL) so they stream
and grow cleanly.

## Assumptions

- Downstream ML (confidence models, vector-QC, agent upskilling) is a real
  direction, even if built later.
- JSONL + pydantic schemas are sufficient now; a feature store is not yet needed.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Human-readable logs only | Not ML-consumable; loses the data's downstream value |
| Build a feature store / ML pipeline now | Scope; premature before the core flow exists |

## Consequences

| | |
|---|---|
| **Gains** | Outputs do double duty (operations + an ML-ready corpus); the wishlisted ML work has clean inputs waiting |
| **Costs** | Upfront discipline: schema versioning, origin/label tagging, avoiding lossy free-text-only logs |
| **Follow-ups** | Record schemas + versions in `data/schemas.md` and `data/provenance.md` |

## Revisit when

- We start an ML task that needs a feature store, or a schema needs a breaking change.
