# ADR-0025 — Versioned, reversible agent / tool-card configuration

| Field | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-07-13 (MST) |
| **Deciders** | maintainer (James), Claude |
| **Related** | [ADR-0023](ADR-0023-agent-taxonomy-and-action-boundary.md), [ADR-0024](ADR-0024-scope-by-wiring.md), [ADR-0002](ADR-0002-event-driven-core-provenance-ledger.md) (event ledger), [ADR-0014](ADR-0014-productionization-fastapi-react.md) (pipeline save/version/approve), [design/monitoring-agent.md](../design/monitoring-agent.md) |

## Context

A tool-agent's behavior is **operator-editable at runtime**: the monitoring agent's tool card
carries a per-issue-class policy (auto-retry vs detect-and-report) plus free-text custom watch
specs, and "the agent gets updated dynamically from there" (ADR-0023 §5). Editable behavior that
can *act* on a run must be **auditable and reversible**: which policy was in force when an
auto-retry fired? Can we roll back a bad edit? The maintainer's ask is explicit — "this should
100% be versioned and reversible… use tags or something (git in the background)."

The repo already versions pipeline graphs through a save→submit→approve lifecycle (ADR-0014) and
records every I/O as an append-only event (ADR-0002). We want the same rigor for agent/tool-card
config, without inventing a bespoke history engine.

## Decision

1. **Every tool-card config change is an immutable, tagged revision.** A card's policy
   (issue-class selections, custom watch specs, wired scope) is content-addressed; saving an edit
   creates a new revision with a monotonic tag (e.g. `monitor@v3`), never mutating the prior one.

2. **Rollback = re-pin, not delete.** Reverting means pointing the active card at an earlier tag;
   the intervening revisions stay in history (reversible + auditable). Nothing is destroyed.

3. **A run pins the exact revision it used.** The run's provenance records the config tag in
   force, so any action (an auto-retry) is attributable to a specific, recoverable policy.

4. **Git-in-the-background is the storage mechanism, not the UX.** Revisions persist via a
   git-backed store (tags/refs over a config tree) behind the same off-gate store abstraction as
   the other stores (`base_store.py` pattern). The operator sees "version / revert," never git
   plumbing. This keeps history durable, diffable, and reversible with a boring, proven tool.

5. **Structured for ML + audit.** Each revision record is typed — `{card_id, tag, ts, actor,
   parent_tag, diff_summary, policy}` — so config evolution is minable (per the structure-for-ML
   principle) and shows in the audit trail.

## Assumptions

- Config volume is low enough that a git-backed history is cheap (it is — cards change rarely).
- Operators want "undo to a known-good version," not free-form history surgery.
- The existing store abstraction can host a git-backed adapter alongside jsonl/sqlite/postgres.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| A bespoke revision table in SQLite | Reimplements tag/branch/diff/rollback that git already does well; more code, less proven. |
| Overwrite-in-place with an audit log of changes | Not truly reversible — you can see *that* it changed but can't cleanly restore a prior working policy. |
| Reuse ADR-0014's pipeline save/approve verbatim | That flow is for *graphs* with an approver gate; card-policy edits are lighter and operator-owned — share the *spirit* (immutable revisions) not the approval ceremony. |

## Consequences

| | |
|---|---|
| **Gains** | Auditable, reversible agent behavior; every action attributable to a pinned policy; config history is ML-minable; leans on git rather than a custom engine. |
| **Costs** | A git-backed store adapter to build + guard; must pin the config tag into run provenance; UX for "version / revert" on the card. |
| **Follow-ups** | The git-backed config store adapter; run-provenance field for the active config tag; the tool-card "history / revert" affordance; extend the same versioning to other editable agent assets (scaffolds, corpora) if it proves useful. |

## Revisit when

- Config volume or edit frequency grows enough that a git-backed store becomes a bottleneck.
- An editable agent asset needs approval (not just versioning) — then borrow ADR-0014's gate.
