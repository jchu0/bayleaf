# Journal — 2026-07-09 (MST) — Doc-keeper trial + the drift it caught

| Field | Value |
|---|---|
| **Focus** | Trial the newly-built `doc-keeper` subagent on real doc tasks, adversarially verify its work, and fix the drift it surfaced. |
| **Outcome** | The agent held up: it caught a planted bait + **4 misses in my own recent sweeps** + a pre-existing gap + a meta-staleness — all grounded in code, zero hallucinations on verification. Fixed across 5 docs. |

## Discussion

**How it was trialed.** `subagent_type: doc-keeper` doesn't register until session start, so the
contract was exercised by having 3 general-purpose instances **read `.claude/agents/doc-keeper.md`
and operate as that agent**, report-only (no edits). I then verified every top finding against
code myself before applying anything.

**What it caught (all CONFIRMED against code):**
1. The **planted bait** — `nf-core-conventions.md` framing execution-trace ingestion as
   aspirational when EXEC-001 now ships it (caught by *both* the data-audit and the sweep-check).
2. **Four misses in my own sweeps** — `data-platform-and-archivist.md` (agent #2 "planned/deferred"
   + "execution_trace capture that doesn't exist" + "load_run opens exactly five run/ files" +
   "GET-only CORS", plus the stale open-question at line 803) and the `agents.md` T-026 folder-plan
   narrative. Owed by the EXEC-001 + writes batches; I hit the obvious 🔴/🟠 targets and
   **under-swept the design docs**.
3. A **pre-existing gap** — the built+tested S3 artifact-store seam (T-039) absent from
   architecture.md's swappable-seams table.
4. A **meta-staleness** via grep — `metric_registry.md` claimed the metrics module docstrings
   "still read 'additive only'"; `grep additive src/bayleaf/metrics/` = 0, so the caveat was
   itself stale.

**The lesson (aimed at me, not the agent).** My per-change doc sweeps route off *the files I
opened* rather than *the Doc-update map*, so cross-cutting design docs (`data-platform-and-archivist.md`
especially) get skipped — exactly the "a doc you never opened can still be owed" failure the map
exists to prevent. The fix: hand each change to `doc-keeper` (once it registers next session), which
routes off the map by construction.

**Verification discipline held.** Ran the agents report-only, spot-checked ~6 findings against
`file:line` before any edit, then applied the verified fixes via one write-agent (which also caught
two coupled clauses to avoid a fresh contradiction) — and a residual open-question the fix pass
missed was flagged in the agent's own finding, so I closed it by hand.

## Decisions

| Decision | Distilled to |
|---|---|
| The doc-keeper is trustworthy for AUDIT/SWEEP; route future per-change sweeps through it (next session, once registered) | this journal; [DOCUMENTATION_HABITS.md](../DOCUMENTATION_HABITS.md) doc-keeper note |
| Fix the 6 real drifts it surfaced (5 docs) rather than only assess | architecture.md · data-platform-and-archivist.md · agents.md · metric_registry.md · nf-core-conventions.md |

## Distilled into

- Fixed: [architecture.md](../design/architecture.md) (artifact-store seam) · [data-platform-and-archivist.md](../design/data-platform-and-archivist.md) (#2 built, six run/ files, CORS, open-question) · [agents.md](../design/agents.md) (T-026 narrative) · [metric_registry.md](../data/metric_registry.md) (additive caveat) · [nf-core-conventions.md](../data/nf-core-conventions.md) (replaces→complements)
