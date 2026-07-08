# ADR-0007 — ML-ready structured outputs

| Field | Value |
|---|---|
| **Status** | Accepted · Realized (`MetricValue` is the concrete ML-ready QC record; schema-versioned, origin-tagged JSONL) |
| **Date** | 2026-07-07 (MST) · updated 2026-07-08 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0004](ADR-0004-vcf-first-giab-substrate.md), [ADR-0013](ADR-0013-gate-architecture-verdict-policy.md), [ADR-0015](ADR-0015-layered-data-contract.md), [data/schemas.md](../data/schemas.md), [data/metric_registry.md](../data/metric_registry.md) |

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

## Realized (2026-07-08)

1. **`MetricValue` (`models.py`) is the concrete ML-ready QC record.** It is frozen, carries a
   `content_hash` identity + `schema_version`, and — the load-bearing choice — **snapshots**
   `canonical_unit` + `metric_registry_version` onto the record rather than dereferencing the
   registry at read time, so one ledger row is standalone-interpretable for offline ML/audit.
   The registry (`metrics/registry.py::observe`) computes the normalized value; the model only
   stores it, so a row round-trips through `model_dump(mode="json")` with no registry present.
2. **The structural discipline landed everywhere:** every persisted shape carries
   `identifiers.SCHEMA_VERSION`; the provenance ledger is one-JSON-per-line JSONL
   (`EventLedger`); artifacts are origin-tagged `real-giab | synthetic | contrived`
   ([ADR-0004](ADR-0004-vcf-first-giab-substrate.md)); free-text narration always sits
   *alongside* typed fields, never as the only representation.
3. The full "why each shape" rationale — immutability, hashing, computed fields, the units
   contract, confidence-omitted-until-grounded — is consolidated in
   [ADR-0015](ADR-0015-layered-data-contract.md).

## Revisit when

- We start an ML task that needs a feature store, or a schema needs a breaking change.
