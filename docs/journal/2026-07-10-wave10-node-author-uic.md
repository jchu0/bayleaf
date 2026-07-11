# Journal — 2026-07-10 (MST) — Wave 10 doc sweep: node-authoring agent (T-046) + UIC-1..16

| Field | Value |
|---|---|
| **Focus** | Doc-keeper SWEEP for two already-committed batches: `71d4ff9` (T-046, node-authoring advisory agent, backend-only) and `6b571a4` (UIC-1..16, a 33-file frontend UI-convention implementation) — plus indexing three design-doc areas (`design/ui-conventions.md`, `design/builder-cards/`, `docs/usage/`) that had landed without ToC entries in earlier sessions. |
| **Participants** | doc-keeper subagent (Claude), orchestrator task |
| **Outcome** | Doc-update map swept; every owed doc updated in this change; a genuine, load-bearing scope drift found and corrected (node-authoring shipped narrower than designed) — no code touched. |

## Discussion

### Reading the commits before writing anything

Per the doc-keeper contract ("ground every claim in code"), I read both commits' full diffs
(`git show 71d4ff9`, `git show 6b571a4`) before touching any doc, plus the actual source:
`src/pipeguard/node_author/{__init__,agent,models,retrieval}.py`,
`knowledge/tool_cards.jsonl`, and `tests/test_node_author.py` for the agent; and
`docs/design/ui-conventions.md` (already committed, 6b99196) plus spot-checked diffs of
`Submit.tsx` and `Admin.tsx` for the two highest-stakes UIC items (UIC-11's identity join, UIC-13's
Act-as re-auth) before writing any safety-adjacent claim about them.

### The node-authoring agent shipped narrower than its own design doc — this is the load-bearing find

`docs/design/node-authoring-agent.md` (written 2026-07-09, before this build) describes the "one
job" as: given a tool's **dropped documentation** (`nextflow_schema.json` / `--help` dump / a
Nextflow module / a README), parse it and propose a typed `ToolNode` card — the real "bring your
own tools" unlock, with a deterministic nf-core-schema importer as its $0 core (explicitly
described as *sharing a stub core with wishlist #9*) and Claude only for the fuzzy
`ArtifactKind`-mapping step.

What actually shipped (`src/pipeguard/node_author/`) is a **different, simpler mechanism**:
retrieval over a small, fixed, hand-curated corpus of 11 tool cards (this pipeline's own 7
germline tools + NGSCheckMate + 3 reference nodes), triggered by a **natural-language request**,
not a dropped document. There is no `nextflow_schema.json` parser, no `--help` parser, no README
ingestion anywhere in the code (confirmed: `retrieval.py`'s only I/O is
`load_tool_card_corpus()` reading the shipped JSONL; nothing in `agent.py` accepts a file). This
means the agent **cannot onboard a genuinely new tool** — it can only help an operator rediscover
or re-propose a tool already in its fixed corpus. It also means wishlist #9 (the schema-driven
form importer) and this agent **do not share a stub core**, contradicting what
`scope-and-wishlist.md` #9 previously said.

I verified this is not a misreading by grepping the actual corpus tool names (`grep -o '"tool":
...'` → fastp, bwa-mem2, samtools markdup, mosdepth, bcftools call, bcftools norm, MultiQC,
NGSCheckMate, Reference FASTA, Panel BED, Truth VCF — exactly the germline chain +
`docs/design/builder-cards/`'s 7 tools + 3 references, 11 total, matching the commit message's
"11 curated cards") and by reading `agent.py`'s own docstring ("Given a NATURAL-LANGUAGE request
… it retrieves a matching curated tool-card").

I also confirmed there is **no `api/` endpoint and no frontend wiring**:
`grep -rn node_author api/` → empty; `grep -rn "propose_node\|NodeProposal" frontend/src` → empty
(only the string "node_author" appears, in `BuilderModals.tsx`/`SettingsModelTier.tsx`, as
label text, not a call). `AuthorToolNodeModal` in `BuilderModals.tsx` — the Pipeline Builder's
"Author a tool node" entry — is a pre-existing static mock (`badge "roster #5 · phase-2"`,
hardcoded `STAR --help` text) that predates this build and is unconnected to it.

This is exactly the class of drift the doc-keeper contract calls out as the #1 priority bug (a
claim contradicted by code), except here the drift ran the *other* direction — a **design doc's
claim about what would be built** no longer matched what was built. I corrected it in three
places: `design/node-authoring-agent.md` (added a "What actually shipped" section, kept the
original proposal below it for record), `design/agents.md` (roster row #5 rewritten to the real
scope), and `scope-and-wishlist.md` (#9's "shares a stub core" claim explicitly retracted with a
correction note, plus #11's row appended with the accurate current status).

### Numbering the agent roster — resolving a three-way inconsistency

I found three different "which number is this agent" framings and had to pick an authoritative
one: (a) `design/agents.md`'s roster table (excludes the synthesizer) numbers node-authoring **#5**
— pre-existing, reserved for it before this build; (b) the shipped code's own docstring
(`node_author/agent.py`, `node_author/__init__.py`) says "**Agent #6** in the roster," inconsistent
with (a) — a code comment I cannot fix (out of scope: no `src/pipeguard` edits) but can avoid
propagating; (c) the orchestrating task's framing called it "the 7th advisory agent." I grounded
this by grepping every `PIPEGUARD_*_AGENT` env var plus `PIPEGUARD_SYNTHESIZER` in the actual
code: exactly **six** stub|claude seams exist today (synthesizer, triage, feedback, pipeline-repair,
archivist, node-author). I used **design/agents.md's own numbering (#5, excluding the
synthesizer, its own stated convention)** as authoritative for the roster table, and "six" for
CLAUDE.md's broader "Swappable AI" list (which does include the synthesizer) — neither matches
"7th." I did not silently adopt an unverified count from the task framing; I derived and reported
the actual number.

### The two verified-safe UIC items

Before writing anything about UIC-11 (Submit's identity-join gate) and UIC-13 (Admin's Act-as
re-auth) — both touch data-safety / security posture, so I read the actual diff hunks rather than
trusting the commit message:

- **UIC-11**: confirmed `Submit.tsx`'s `canSubmit = count > 0 && join.metadataPresent &&
  joinApproved`, and `lib/accession.ts`'s `computeIdentityJoin()` corroborates on `Sample_ID` plus
  tissue (never single-column), with approval bound to a join **signature** so any later edit
  auto-invalidates it. This is real, not just a commit-message claim — added a REQ-NF (data-safety
  posture is a nonfunctional requirement, not just a feature).
- **UIC-13**: confirmed the re-auth gate is a demo password field (`type="password"`, compared
  client-side against a shared demo credential), but it is **honestly labelled in both the code
  comment and the UI copy** as a production seam — real re-auth is meant to be an IdP step-up or a
  credential-request tool. This matches the life-science/security honesty guardrail (label, don't
  fabricate) rather than violating it, so I recorded it as shipped-with-a-labelled-gap, not a
  violation.

### Filling a dangling-link gap found along the way

While indexing `docs/usage/` per the task, I found `docs/usage/README.md` (seeded in an earlier,
already-committed session, `83d304f`) links to `operator-guide.md` in ~14 places, but that file
did not exist on disk — a dangling link from a previous session, not something Wave 10 introduced.
Since I was already indexing this area in the ToC, I created a lightweight stub
(`docs/usage/operator-guide.md`, one section per operator screen, each a TODO placeholder) rather
than leave ~14 broken links or skip the gap silently.

## Decisions

| Decision | Distilled to |
|---|---|
| The node-authoring agent's roster number stays **#5** (agents.md's own convention, excluding the synthesizer); CLAUDE.md's broader "Swappable AI" list now says **six** seams (including the synthesizer) | [design/agents.md](../design/agents.md), `CLAUDE.md` §4 |
| Correct `scope-and-wishlist.md` #9's claim that the node-author stub shares a core with the nf-core schema importer — it does not; #9 stays fully unbuilt on its own | [scope-and-wishlist.md](../requirements/scope-and-wishlist.md) |
| Add REQ-NF-025 for the Submit identity-join approval gate (a genuine new data-safety requirement, not just a UI feature) | [nonfunctional.md](../requirements/nonfunctional.md) |
| Create a lightweight `docs/usage/operator-guide.md` stub rather than leave README's page-index links dangling | [usage/operator-guide.md](../usage/operator-guide.md) |
| No new ADR needed — nothing here is a load-bearing architectural decision; it's a scope-accuracy correction + a doc-routing sweep | n/a |

## Open questions & TODO

- The node-authoring agent still needs an `api/` endpoint + Pipeline-Builder wiring (`AuthorToolNodeModal` → `propose_node()`) before it is reachable outside tests — tracked in `design/node-authoring-agent.md`'s "Next slices."
- UIC-16's larger four-side-typed-port Builder cards remain unbuilt (deferred, tracked in `design/builder-cards/README.md` §5).
- UIC-14's cosmetic kanban-id-format gap (a review-queue-derived ticket shows its raw internal id, not `T-XXXX`) is a small follow-up.
- `docs/usage/operator-guide.md` is a stub — filling in real step-by-step content per screen is future work, explicitly not attempted this session (screens are still moving; a stale walkthrough is worse than a TODO).

## Distilled into

- [CLAUDE.md](../../CLAUDE.md) §4 code map (Wave 10 paragraph + agent-roster count)
- [docs/planning/tasks.md](../planning/tasks.md) (T-046 done + new T-118)
- [docs/requirements/functional.md](../requirements/functional.md) (REQ-F-025, REQ-F-083, REQ-F-050 update)
- [docs/requirements/nonfunctional.md](../requirements/nonfunctional.md) (new REQ-NF-025)
- [docs/requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) (#9 correction, #11 update, item 6 count)
- [docs/design/architecture.md](../design/architecture.md) (component map, invariant 2, swappable-seams table, Wave 10 narrative)
- [docs/design/agents.md](../design/agents.md) (roster row #5)
- [docs/design/node-authoring-agent.md](../design/node-authoring-agent.md) ("What actually shipped" + Status/next)
- [docs/design/ui-conventions.md](../design/ui-conventions.md) (all 16 UIC statuses updated + grounded)
- [docs/TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md) (new Usage section + builder-cards/ui-conventions rows + 2 new Doc-update map rows)
- [docs/usage/operator-guide.md](../usage/operator-guide.md) (new stub, closes a dangling-link gap)
