# ADR-0015 — Layered, immutable data contract across the gate

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-08 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0007](ADR-0007-ml-ready-structured-outputs.md), [ADR-0008](ADR-0008-issue-taxonomy-suppression-escalation.md), [ADR-0013](ADR-0013-gate-architecture-verdict-policy.md), [data/schemas.md](../data/schemas.md), [data/metric_registry.md](../data/metric_registry.md), [data/provenance.md](../data/provenance.md) |

## Context

The gate's whole value is a reviewer trusting an auditable chain from a raw artifact to a
verdict. That chain crosses several layers, each owned by a different module:

    parsers   ->  RunArtifacts        (tolerant intake)
    metrics   ->  MetricValue         (normalized QC observation)
    rules     ->  Finding[]           (cited, immutable facts)
    synthesis ->  DecisionCard        (aggregated verdict + narration)
    provenance -> ProvenanceEvent[]   (append-only ledger of every step)

Two forces shape how these structures must be built. First, a later consumer — an ML
model, an auditor, a fresh session — has to read one record *without replaying the
pipeline that produced it*. Second, in a clinical-adjacent domain a stored fact must be
provably unaltered, and a derived value must never silently drift from what it was derived
from.

We had already made the individual decisions — an event-sourced core
([ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md)), ML-ready outputs
([ADR-0007](ADR-0007-ml-ready-structured-outputs.md)), rule-version-independent signatures
([ADR-0008](ADR-0008-issue-taxonomy-suppression-escalation.md)), the three-gate model
([ADR-0013](ADR-0013-gate-architecture-verdict-policy.md)) — but never captured, in one
place, *how the core data structures fit together and why each shape is what it is*. This
ADR is that synthesis. It does not restate those ADRs; it explains the record layer they
all rest on. Ground truth: `src/bayleaf/models.py`, `identifiers.py`, `provenance.py`,
and [data/schemas.md](../data/schemas.md).

## Decision

Adopt one typed record-layer contract with the shapes and invariants below. Each is stated
with the *why*, because the reasoning is the point.

1. **One framework-agnostic contract.** Every shape is pydantic v2 in `models.py` (plus the
   event shapes in `provenance.py`), with no FastAPI/React imports. *Why:* the same
   records back the FastAPI read-API, the React UI, the DB projection, and the JSONL
   ledger — the contract is the seam, so a delivery layer is swappable
   ([ADR-0003](ADR-0003-deployment-agnostic-ports.md)) and the pydantic model is the single
   source of truth (schemas.md).

2. **Immutable, content-hashed facts — with one deliberate exception.** `Finding`,
   `MetricValue`, `Evidence`, and `NotifyPayload` are `frozen`;
   `Finding`/`MetricValue`/`NotifyPayload` each expose a `content_hash` — a sha256 over a
   canonical JSON view of their *semantic* fields, excluding `id`/`created_at`
   (`identifiers.content_hash`). `Evidence` is frozen but unhashed — it is hashed
   transitively inside its parent `Finding`. `DecisionCard` is intentionally **not** frozen:
   `run_gate` stamps `analysis_run_id`/`run_id` onto the card *after* synthesis, and those
   contextual anchors are deliberately excluded from the card's `content_hash` (which folds
   in its child finding hashes). *Why:* (a) **tamper-evidence** — a stored finding can be
   proven unaltered; (b) **dedup + idempotent projection** — the DB upserts on identity, so
   replaying the same event twice is a no-op ([ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md));
   (c) events reference immutable entities by `content_hash` via `EntityRef`, tying the
   ledger to exactly the bytes decided on. A card's identity is its *decision*, not its
   wiring, which is why the anchors are excluded.

3. **Type-prefixed UUIDv7 ids; `created_at` is the time source of truth.** `new_id("find")`,
   `new_id("metric")`, `new_id("arun")`, `new_id("evt")` — time-sortable ids with a
   human-greppable prefix (`identifiers.py`). But `created_at` (stored UTC) is authoritative;
   a timestamp is never parsed back out of an id. *Why:* ids stay stable and collision-free
   across hosts with no coordinator (good ordering for free), while time semantics stay
   explicit rather than smuggled inside an opaque id.

4. **Computed fields, never stored duplicates.** `Finding.gate`, `Finding.signature`,
   `Finding.content_hash`, and `DecisionCard.gate_results`/`content_hash` are pydantic
   `computed_field`s derived from the record's own data. *Why:* derived truth cannot drift
   from its source. The gate a finding belongs to ([ADR-0013](ADR-0013-gate-architecture-verdict-policy.md))
   is a function of its category; its recurrence signature
   ([ADR-0008](ADR-0008-issue-taxonomy-suppression-escalation.md)) is a function of its
   category + rule + loci — so both are computed, never hand-set. The signature deliberately
   **excludes** `rule_version` so it survives rule-pack bumps (recurrence tracking); the
   `content_hash` **includes** `rule_version` (exact identity). Two hashes, two jobs.

5. **One inter-component metric representation: the canonical `MetricValue` + units
   contract.** A metric crosses every component boundary as its `normalized_value` — a
   decimal in the registry's `canonical_unit` — while `raw_value`/`raw_unit` (what the tool
   reported) are snapshotted *alongside* it. Consumers read `normalized_value`, never
   `raw_value`; the metric registry (`bayleaf.metrics`) is the single unit authority.
   *Why:* this defeats the units-mismatch class of bug (a percent handed where a fraction is
   expected). Runbook thresholds are stored in the same `canonical_unit`, so
   `rules._evaluate_metric` compares a threshold and the value it gates on one scale by
   construction; the finding then renders back to the operator's raw unit via
   `registry.denormalize` (`0.841 < 0.85` internally, shown as `84.1% / ≥ 85%`).
   `MetricValue` additionally **snapshots** `canonical_unit` + `metric_registry_version` onto
   the record instead of dereferencing the registry at read time, so a ledger row is
   standalone-interpretable ([ADR-0007](ADR-0007-ml-ready-structured-outputs.md)). Full
   spec: schemas.md §6.

6. **Event-log-authoritative; the DB is a rebuildable projection.** Every meaningful step
   emits a `ProvenanceEvent` into an append-only `EventLedger` (JSONL when file-backed); the
   relational store is a pure projection reached only through the `Repository` port and
   rebuilt by replaying the log ([ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md) /
   [ADR-0003](ADR-0003-deployment-agnostic-ports.md)). *Why:* no dual-write truth — the
   ledger is the record, the DB is disposable and reconstructable, which is what makes the
   provenance defensible rather than merely present.

7. **Version + origin labels on every record.** `schema_version` (`identifiers.SCHEMA_VERSION`,
   currently `1`) sits on every persisted shape, bumped only on a breaking change; an
   `origin` label (`real-giab | synthetic | contrived`) tags each artifact's provenance.
   *Why:* schema evolution stays migratable (a reader knows which shape it holds), and the
   ML/eval consumers can separate real GIAB truth from planted failure modes
   ([ADR-0004](ADR-0004-vcf-first-giab-substrate.md) / [ADR-0007](ADR-0007-ml-ready-structured-outputs.md)).

8. **Confidence omitted until grounded.** `DecisionCard.confidence` is `Optional` and left
   `None` (T-019). *Why:* a heuristic bar would misrepresent certainty in a clinical-adjacent
   domain — the model's shape encodes the biomedical guardrail. Absence is honest; a
   fabricated number is not.

## Assumptions

- pydantic v2 + JSONL are a sufficient contract now; a feature store / columnar format is
  not needed yet ([ADR-0007](ADR-0007-ml-ready-structured-outputs.md)).
- sha256 over canonical JSON (`sort_keys=True`, `default=str`) is a stable identity across
  processes and hosts.
- The immutable/mutable split is settled: findings, metrics, evidence, and payloads are
  facts; suppression/ticket/resolution *state* lives on separate records (schemas.md
  invariant 1), not by mutating a fact.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Mutable records updated in place | Loses tamper-evidence; a status change would rewrite history. We keep facts immutable and put lifecycle state on separate records. |
| Store the derived fields (gate, signature) as data | They drift from their source the moment rule logic or category changes; a `computed_field` cannot. |
| Pass metrics in raw tool units | Reintroduces the units-mismatch bug with no single authority; the canonical `normalized_value` exists precisely to prevent it. |
| Make the DB the source of truth | Dual-write truth against the event log, and not rebuildable/replayable ([ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md)). |
| Dereference the registry at read time (thin `MetricValue`) | A ledger row would not be standalone-interpretable for offline ML/audit; we snapshot the unit + registry version instead. |

## Consequences

| | |
|---|---|
| **Gains** | An auditable, tamper-evident chain from artifact → metric → finding → verdict → event; records ML/audit can read standalone; a disposable, rebuildable DB; derived truth that cannot drift. |
| **Costs** | Upfront discipline — hashing, snapshotting, version/origin tagging, and keeping the immutable/mutable split honest. `content_hash` must exclude volatile fields (`id`/`created_at`, and the card's contextual anchors) or identity breaks. |
| **Follow-ups** | Byte-identical replay determinism ([ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md) Phase 2); wire the remaining record shapes (IssueSignature / Ticket / ExperienceRecord) when suppression/RBAC land ([ADR-0008](ADR-0008-issue-taxonomy-suppression-escalation.md) / [ADR-0009](ADR-0009-corpora-retrieval-upskilling.md)). |

## Revisit when

- A breaking schema change is needed (bump `SCHEMA_VERSION` + a migration path), a non-JSON
  field must enter a `content_hash`, or a feature store / columnar format replaces JSONL as
  the ML substrate.
