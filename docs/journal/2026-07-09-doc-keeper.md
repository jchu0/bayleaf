# Journal — 2026-07-09 (MST) — The doc-keeper subagent

| Field | Value |
|---|---|
| **Focus** | Codify this repo's documentation discipline into a reusable Claude Code subagent, so doc work is consistent instead of ad-hoc. |
| **Outcome** | New `.claude/agents/doc-keeper.md` (a custom subagent embodying the doc contract); noted in [DOCUMENTATION_HABITS.md](../DOCUMENTATION_HABITS.md); tracked as T-060. Loads at next session start. |

## Discussion

**Why.** This session repeatedly fanned out ad-hoc doc-writers and read-only freshness auditors
(the Doc-update-map sweeps, the CHK-1/2/3 close-outs, the "built-feature-still-marked-deferred"
drift fixes). Codifying that into one **`doc-keeper`** subagent makes the discipline reusable and
consistent across sessions rather than re-improvised each time.

**The load-bearing design choice: point at the living sources, don't hardcode them.** A doc agent
that embedded the Doc-update map / templates / house rules as a static snapshot would *itself go
stale* the moment those evolve — the exact failure it exists to prevent. So its system prompt
tells it to **read the contract fresh every task** (`CLAUDE.md`, `DOCUMENTATION_HABITS.md`, the ToC
+ its Doc-update map, `_templates/`, `tasks.md`) and carries only the **durable invariants**
(explain-why→ADR, map-is-routing-authority, ground-every-claim-in-code, journal-is-archive /
canonical-is-truth, numbered-lists + crosslinks + ISO-MST, templates + no-duplication, life-science
honesty, tie-claims-to-verification). Four modes: SWEEP / AUDIT / AUTHOR / CHK.

**What it is not.** Dev tooling (a Claude Code subagent under `.claude/agents/`), **not** a
bayleaf product/roster agent. The roster ([agents.md](../design/agents.md)) is advisory agents
over genomics *run* data governed by ADR-0001 (rules decide, AI advises); the repo's own docs are
not a product feature, so this doesn't belong in that roster or its intake checklist.

**Dogfood note.** Custom agents register at session start, so the freshly-written definition
wasn't invocable this session (confirmed: `subagent_type: doc-keeper` → "not found"). Its own
creation was therefore documented by the top-level session — which is also the *correct* owner of
the journal under the contract's own fan-out rule. It's ready to invoke next session.

## Decisions

| Decision | Distilled to |
|---|---|
| Codify the doc discipline as a reusable `doc-keeper` Claude Code subagent (dev tooling, not a product/roster agent) | `.claude/agents/doc-keeper.md`; [DOCUMENTATION_HABITS.md](../DOCUMENTATION_HABITS.md); [tasks.md](../planning/tasks.md) T-060 |
| The agent points at the living contract sources rather than a hardcoded snapshot (else it goes stale) | the agent's system prompt; this journal |

## Open questions & TODO

1. First real use next session — invoke `doc-keeper` (SWEEP/AUDIT) on the next substantive change
   and refine its prompt if it over/under-reaches.
2. If a doc-freshness *report* is wanted with no edits, use a read-only Explore agent (the doc-keeper
   is write-enabled by design).

## Distilled into

- `.claude/agents/doc-keeper.md` — the agent (canonical)
- [docs/DOCUMENTATION_HABITS.md](../DOCUMENTATION_HABITS.md) — the "doc-keeper subagent" note
- [docs/planning/tasks.md](../planning/tasks.md) — T-060
