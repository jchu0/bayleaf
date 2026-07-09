# ADR-0008 — Issue taxonomy, suppression, and escalation

| Field | Value |
|---|---|
| **Status** | Accepted · Partially realized (finding category + rule-version-independent signature built; reviewer/approver RBAC tiers BUILT — `api/auth.py`, [ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md); suppression-muting + ~3× recurrence escalation deferred) |
| **Date** | 2026-07-07 (MST) · updated 2026-07-08 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0009](ADR-0009-corpora-retrieval-upskilling.md), [ADR-0015](ADR-0015-layered-data-contract.md), [ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md), [data/schemas.md](../data/schemas.md) |

## Context

Recurring issues create re-approval fatigue: an operator re-triages the same
known condition every run, and teams "throw a person at it as glue" instead of
fixing the cause. But blindly auto-applying fixes is unacceptable in this domain.

## Decision

1. Every finding carries a **category** and a **stable signature** (a hash of its
   type plus salient parameters).
2. An operator can **acknowledge/suppress a signature or class** (with an expiry
   and periodic review) so it stops re-prompting once knowingly accepted.
3. A signature recurring **~3 times** (configurable) **escalates to the
   pipeline-repair agent** (agent #2, ADR-0012).
4. Escalation and any fix are **human-gated**, likely behind **tiered dashboard
   access (RBAC)**. Support both **class-level fixes** and per-instance
   **"see-one/fix-one"** approvals — never blind auto-apply.
5. Signatures and resolutions feed the **experience ledger** (ADR-0009).

## Assumptions

- ~3× is a sensible default recurrence threshold; it will be tunable.
- Approval authority needs role tiers (reviewer vs. approver).

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Re-prompt on every occurrence | The fatigue this is meant to eliminate |
| Auto-apply fixes on recurrence | Unsafe without a human in a clinical-adjacent domain |

## Consequences

| | |
|---|---|
| **Gains** | No re-approval loop; systemic issues surface and route to the repair agent |
| **Costs** | Signature scheme, suppression lifecycle, and RBAC to build |
| **Follow-ups** | Signature fields finalized in the schema-design discussion |

## Realized (2026-07-08)

1. **Realized:** every `Finding` (`models.py`) carries a `category` and a semantic,
   rule-version-independent `signature` (a hash of category + rule_id + sample + sorted evidence
   loci, **excluding** `rule_version` so recurrence survives rule-pack bumps) alongside an
   exact-identity `content_hash`. Findings are immutable (`frozen`); the signature is emitted on
   each `finding.emitted` event.
2. **RBAC tiers BUILT:** the reviewer/approver role tiers this ADR anticipated (item 4,
   assumption 2) now exist as the shared identity/RBAC primitive (`api/auth.py` — `Role`
   `viewer|reviewer|approver` + `require_role`), applied to the suppression/escalation approvals
   in `api/routers/review_queue.py` ([ADR-0017](ADR-0017-identity-rbac-authoring-lifecycle.md)).
   **Still deferred (unchanged):** the suppression-muting lifecycle, the ~3× recurrence escalation
   to the pipeline-repair agent, and the `IssueSignature` / `ExperienceRecord` corpora
   (schemas.md §16 / §14 — MVP-deferred). Suppression/resolution will live on those records,
   never by mutating a `Finding` (schemas.md invariant 1).

## Revisit when

- Signatures prove too coarse or too fine, or the recurrence threshold needs tuning.
