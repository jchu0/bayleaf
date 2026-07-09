# Journal — 2026-07-09 (MST) — Parallelize directive + fan-out doc-freshness sweep

| Field | Value |
|---|---|
| **Focus** | Codify "parallelize by default" in the operating contract + cascade it; then sanity-check doc freshness after the parallel burst via a fan-out audit, and apply the fixes. |
| **Participants** | James Hu, Claude Code (+ two read-only audit workflows). |
| **Outcome** | CLAUDE.md Workflow-4 added + cascaded to DOCUMENTATION_HABITS; a 6-agent doc-freshness audit ran, and its quick fixes + larger gaps were applied across the ADRs, ToC, CLAUDE.md, architecture.md, requirements, and the agent roster. |

## Discussion

**Parallelize by default (a working-agreement decision).** The parallel-task cadence of the
last stretch was worth codifying: added **CLAUDE.md → Working agreement / Workflow 4** —
batch independent work into as many concurrent processes as safely possible (independent tool
calls in one message; fan out subagents/workflows for non-blocking audits/sweeps/research/
verification; scout inline then fan out), with the caveats that matter (single-author for
same-file edits, serialize real data dependencies, read-only Explore agents for audits).

**Cascaded it** to the how-we-work companion, `DOCUMENTATION_HABITS.md` ("Claude documentation
behavior"): fan out read-only agents for a doc-freshness audit or many-doc sweep, then apply
the fixes — but keep same-doc edits single-author, and prefer single-author for tightly-coupled
canonical docs (cross-referencing ADRs). Per the Doc-update map, a CLAUDE.md working-agreement
change's only hard obligation is the journal (this entry); the DOCUMENTATION_HABITS cross-ref is
the genuine downstream sibling.

**Fan-out doc-freshness audit.** Ran a 6-agent read-only (Explore) workflow over the doc domains
(ADRs · tracker · requirements · ToC/doc-map · architecture+CLAUDE.md · journal distillation).
Dominant finding: the 07-09 burst (Postgres port/ADR-0016, W12 feedback, feedback agent,
artifacts endpoint, Pipeline Builder = 8th screen) shipped faster than the canonical docs
tracked it — code + tracker were current, but the design/decision docs still described
pre-burst reality.

**Applied the fixes** (single-author, since the ADRs cross-reference each other):
- **ADR-0016** — Status/Follow-ups still deferred a live-Postgres test that shipped + passed
  green; rewrote to BUILT + verified.
- **ToC** — the ADR index stopped at ADR-0015 (the anchor doc for the whole stretch was
  unindexed); added the ADR-0016 row, bumped Last-updated, and fixed a rotted Doc-update-map
  trigger so a *new advisory agent anywhere* (not just `synthesis/`/`triage/`) obliges the roster.
- **CLAUDE.md code map** + **architecture.md** — both still called the API read-only, listed
  SQLite as the only built repository, and counted 7 screens; updated to the Postgres adapter +
  `get_repository()`, the off-gate feedback write + pluggable `FeedbackStore`, the artifacts
  endpoint, the feedback agent, and the 8th screen (Pipeline Builder).
- **design/agents.md** — added the feedback-triage agent (roster row #4, off-gate) + ADR-0016.
- **ADR-0003 / ADR-0010** — Realized/item-2a updated (Postgres adapter; pluggable store +
  `source` field) with reciprocal ADR-0016 backlinks.
- **scope-and-wishlist.md** — resolved the self-contradiction (W11/W19 were listed as both BUILT
  and SCOPE-ONLY), marked wishlist #12 built, noted #19's Postgres adapter shipped, refreshed the
  "Built as of" snapshot (8 screens + Pipeline Builder + feedback/artifacts/Postgres).
- **functional.md** — corrected the notify-adapters note (Teams + Discord shipped T-035; only
  Jira remains). Bumped the four stale Last-updated stamps to 2026-07-09.

The frontend fidelity/scale audit (the second workflow) also landed; its findings feed the
separate claude-design brief, not this doc sweep.

## Decisions

| Decision | Distilled to |
|---|---|
| "Parallelize by default" is a standing working-agreement convention | [CLAUDE.md](../../CLAUDE.md) Working-agreement/Workflow 4; [DOCUMENTATION_HABITS.md](../DOCUMENTATION_HABITS.md) |
| Apply cross-referencing canonical-doc fixes single-author (not fanned-out write-agents) | this journal (per the new caveat) |

## Open questions & TODO

- The frontend fidelity/scale audit surfaced real gaps (Decision-cards fidelity regressions,
  Dense/Brief density non-functional, Settings display-only, no scale affordances) → folded into
  the **claude-design brief** (separate deliverable) + a fix-now backlog.
- architecture.md's data-flow diagram + a couple of narrative sections could take a deeper pass;
  the load-bearing claims (adapters, screens, api posture) are now correct.

## Distilled into

- [CLAUDE.md](../../CLAUDE.md), [DOCUMENTATION_HABITS.md](../DOCUMENTATION_HABITS.md) — the directive + cascade
- [ADR-0016](../adr/ADR-0016-postgres-port.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md) — freshness fixes
- [TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md), [architecture.md](../design/architecture.md), [agents.md](../design/agents.md), [functional.md](../requirements/functional.md), [scope-and-wishlist.md](../requirements/scope-and-wishlist.md)
