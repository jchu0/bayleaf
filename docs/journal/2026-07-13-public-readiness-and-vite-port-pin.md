# Journal — 2026-07-13 (MST) — Public-readiness doc framing + Vite dev-port pin

| Field | Value |
|---|---|
| **Focus** | Prep the repo to go public for the hackathon demo: decide whether to cut "non-essential" docs, then apply light front-door curation instead. Separately, resolve a flagged oddity — the README hardcodes `http://localhost:5173` though no port is set in config. |
| **Participants** | Claude (Opus 4.8), maintainer (James Hu) |
| **Outcome** | Recommendation: **keep the docs, curate the front door** (nothing sensitive is tracked; the docs are a differentiator; deletion would break the crosslink web). Applied: an `audit/` framing README, a README "engineering archive" pointer, and a **pinned Vite dev port** (`:5173` + `strictPort`) that closes a real latent break, not just a README cosmetic. |

## Discussion

### Should we cut non-essential docs before going public?

Grounded the question in the actual tracked state rather than filename counts:

1. **Nothing sensitive/junky is tracked.** `.env`, the root runtime event logs
   (`feedback.events.jsonl`, `review_tickets.jsonl`, `share.events.jsonl`, …), the 9 MB
   `HG002…bam.bai`, and `.DS_Store` are all gitignored. Going public leaks nothing — hygiene was
   already done. That narrows the question to purely editorial: are the 153 tracked `docs/` files +
   28 `audit/` files (34% of the repo) a liability?
2. **Conclusion: keep them.** (a) For a "Built with Claude" entry the doc depth (25 ADRs, the
   Doc-update-map contract, grounded data/QC docs, a real audit trail) is a rigor signal most
   hackathon repos lack. (b) The IA already shields a casual visitor: the README routes to ~4
   must-reads, and the ToC labels `journal/` as distilled archive. (c) Bulk deletion right before
   going public is the *riskier* move — the doc system is built on crosslinks + the Doc-update map,
   so deletion orphans references and can make surviving docs look broken.
3. **The one nuance — frame, don't cut — is `audit/gap_analysis/`.** It candidly enumerates
   "confident surface vs. thin wiring" (e.g. WS-07's "the live agents add phrasing, not knowledge,"
   a "dead mock"). That candor reads as maturity to an engineer but a *problem statement* skimmed out
   of context could misread as a weakness. Resolution: a framing banner so the honesty reads as
   discipline (findings were acted on), and — importantly — **not** deletion, since the ToC
   references the dir and its absence would be conspicuous.

### The `:5173` oddity — cosmetic README bug or real?

The maintainer flagged that the README says "Open http://localhost:5173" though no port is set. It
is **more than cosmetic**:

1. `frontend/vite.config.ts` set no `server.port`, so `npm run dev` took **Vite's default 5173** —
   but Vite's default is **not strict**: a busy 5173 silently drifts to 5174/5175.
2. The app **hardcodes 5173** in two real places: the API CORS allowlist (`api/main.py:92`,
   `allow_origins=["http://localhost:5173", …]`) and the Admin `/metrics` origin swap
   (`frontend/src/screens/Admin.tsx:698`, swaps `:5173→:8010`). So a drift off 5173 silently breaks
   `/metrics` and cross-origin calls.
3. Robust fix = **pin the port** (`port: 5173, strictPort: true`), not soften the README. Pinning
   makes the README, run-of-show, CORS allowlist, and Admin swap mutually consistent, and
   `strictPort` fails loudly on a taken port instead of drifting into a broken state.

Left out of scope (noted for the maintainer): `.claude/launch.json` has a duplicate `frontend` entry
and a stale `pipeguard-dashboard` Streamlit entry (points at the removed `app/streamlit_app.py`,
uses the pre-rename `PIPEGUARD_BIOCONDA_BIN`). It's a local harness file, not the public-facing
concern here.

### Streamlit purge — code already done, docs were stale

The maintainer asked to "get rid of the Streamlit stuff." Investigation showed the **code side was
already complete and merged**: commit `7dab033` ("remove the Streamlit MVP") landed via PR #7, and
the working checkout is now on `main` (the session-start branch snapshot was stale). `app/` is gone;
`pyproject.toml` and `uv.lock` have zero Streamlit references.

What remained was **stale doc references**. Split them two ways:

1. **Canonical, current-state docs → updated.** Two kinds: (a) the *guardrail* phrasing "no
   Streamlit/FastAPI imports in the core" — the invariant (framework-agnostic core) still holds, so
   it becomes "no FastAPI/React imports" (CLAUDE.md, `architecture.md`, `nonfunctional.md` REQ-NF-050,
   `pipeline-builder-brief.md`); (b) Streamlit as a *live delivery layer / fallback* — removed from
   `architecture.md` (prose + the component-map ASCII diagram), `one-pager.md`, `run-of-show.md`,
   `nf-core-conventions.md`, the telemetry docs, and rewrote the offline-demo requirements
   (REQ-F-043, REQ-NF-042, REQ-C-003, `scope-and-wishlist.md`) around "the full React/API stack runs
   offline, stub-first" — which is what actually replaced Streamlit as the always-green demo.
2. **ADR-0014 (the decision that *chose* Streamlit) → amended, not rewritten.** Added a dated
   Amendment note recording that Decision 3 was reversed + why (React/FastAPI runs offline, so a
   second parallel UI was redundant), preserving the original decision text as the historical record.
3. **Dated archives (`journal/`, `audit/`) → left untouched.** They accurately describe what was
   true when written; editing them would falsify the snapshot — consistent with the `audit/README.md`
   framing added earlier this session.

### Doc-freshness audit → fixes (fanned out to background agents)

Per the new prefer-background-agents posture, ran the freshness pass as **two background Workflows**.
**Audit** — 7 read-only `Explore` agents, one per doc cluster, cross-checking docs against current
code — returned **25 code-proven findings** (6 high / 16 med / 3 low), collapsing to 10 root issues.
Most were docs *under*-selling shipped work (Accept-to-library marked deferred but built; the
author-tool-node modal called a static preview but actually wired; ADR-0019 "not built" but Slice 1
shipped) plus two genuinely wrong facts: the **test census** (doc said 727/55, judge one-pager said
320/19; actual **789 collected / 65 files**) and the **CLAUDE.md code map** still citing the
pre-rename `RouteToHumanPolicy`/`_check_route_to_human`/`VAR-RTH-001`. **Apply** — 6 write-agents
partitioned by *file* (no two touch the same doc) — applied all 25, **0 skipped**, across 15
current-state docs; verified centrally (git diff + re-grep: 0 `NODE_W = 232`, 0 "tenth EventType",
0 "12 operator screens", 0 "320 tests"; census now 789/65; **no source files touched**). Dated
`journal/`/`audit/`/`HISTORY.md` archives left untouched, as were two dated `NODE_W = 232` milestone
records (tasks.md T-121, functional.md REQ-F-083i — history, not current-value claims). Also fixed a
residual self-inconsistency in `agent-triage-redesign-spec.md` (WS-1c/Slices still said
`'system-agents'`/`/agents`).

## Decisions

| Decision | Distilled to |
|---|---|
| Freshness pass run as two background Workflows (7 read-only auditors → 6 file-partitioned appliers); fix current-state docs, leave dated milestone records | 25 fixes across 15 docs; verified by re-grep |
| Delete `docs/demo/` (all 3, incl. the judge one-pager) at maintainer request; clean the 19-file inbound cascade (§Fallbacks traces repointed to REQ-NF-042), leave `journal/`+`audit/`+`tasks.md` archive links as history | demo/ removed; README/requirements/quality/DOCUMENTATION_HABITS links repointed or dropped |
| Keep the doc/audit corpus for public release; curate the front door rather than cut | This journal + the README/ToC/`audit/README.md` edits |
| Frame `audit/` candor as acted-on discipline (banner), never delete | [audit/README.md](../../audit/README.md) |
| Pin the Vite dev port to `:5173` (`strictPort`) rather than soften the README | `frontend/vite.config.ts` |
| Purge stale Streamlit refs from *current-state* docs; amend (not rewrite) ADR-0014; leave dated archives as-is | [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md) + the requirements/design/demo docs |
| Reverse the agent-usage posture: **prefer background/parallel agents over inline**, keep the main surface free (reverts the earlier same-day don't-fan-out rule) | `CLAUDE.md` Working agreement §4 + the `feedback-prefer-background-agents` memory (old `feedback-restrict-costly-subagents` deleted); read-only-review + same-file-single-author caveats kept |

## Open questions & TODO

- Optional (not done): trim repo weight by relocating the two ~1 MB design-mockup HTML files
  (`docs/design/frontend/bayleaf.html`, `…/source/bayleaf.dc.html`) — the heaviest tracked blobs;
  harmless to leave.
- Optional (not done): clean the stale/duplicate entries in `.claude/launch.json`.

## Distilled into

- [README.md](../../README.md) — "engineering archive" pointer in *Architecture & docs*
- [audit/README.md](../../audit/README.md) — new audit landing/framing page
- [docs/TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md) — audit row + ADR-0014 title + `Last updated`
- `frontend/vite.config.ts` — pinned dev port (`port: 5173, strictPort: true`)
- [docs/adr/ADR-0014-productionization-fastapi-react.md](../adr/ADR-0014-productionization-fastapi-react.md) — Streamlit-removal amendment
- Streamlit purge across current-state docs: `architecture.md`, `one-pager.md`, `run-of-show.md`,
  `nf-core-conventions.md`, `ops/telemetry-connectors.md`, `deploy/telemetry/docker-compose.yml`,
  `requirements/{functional,nonfunctional,constraints,scope-and-wishlist}.md`, `CLAUDE.md`,
  `design/frontend/pipeline-builder-brief.md`
- Doc-freshness pass — 25 fixes across 15 current-state docs: census 789/65 (`evaluation.md`,
  `one-pager.md`); `12→13` screens/PageId (`functional.md`, `ui-conventions.md`, `demo_plan.md`,
  `frontend/README.md`, `CLAUDE.md`, `agent-triage-redesign-spec.md`); `NODE_W 232→320`
  (`ui-conventions.md`, `builder-cards/README.md`, `frontend/README.md`); Accept-to-library built
  (`architecture.md`, `agents.md`, `node-authoring-agent.md`, `agent-authoring-contract.md`);
  `flag-for-review` rename (`CLAUDE.md`); EventType 10→12 + router list (`architecture.md`);
  ADR-0019 Slice-1 (`ADR-0019`); QC gating + registry source-honesty (`schemas.md`,
  `metric_registry.md`). Dated archives + milestone records left as history.
- **Residual (out of audit scope, not fixed):** `docs/planning/tasks.md` T-163 row now reads
  stale (dedicated `systemAgents` PageId was added after it); a task-board record, flagged not edited.
