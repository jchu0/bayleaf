# ADR-0008 — Issue taxonomy, suppression, and escalation

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-07 (MST) |
| **Deciders** | James Hu, Claude Code |
| **Related** | [ADR-0001](ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0009](ADR-0009-corpora-retrieval-upskilling.md) |

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

## Revisit when

- Signatures prove too coarse or too fine, or the recurrence threshold needs tuning.
