# Node-Authoring Agent — build Pipeline Builder tool cards from dropped tool docs

| Field | Value |
|---|---|
| **Status** | **Built, narrower than proposed (2026-07-10, T-046, commit `71d4ff9`)** — roster agent #5. The core Python agent (`src/pipeguard/node_author/`) is built and tested; the flow this doc originally proposed (drop a tool's docs → parse → propose) was **not** what shipped — see "What actually shipped" below. **Updated 2026-07-11 (W2, T-127): a read-only `api/` endpoint + Pipeline-Builder wiring now exist** — the builder's "Author a tool node" modal renders the real proposal instead of a static `phase-2` preview. **Updated again 2026-07-11 (W2 backend, T-135): accept→library, a conformance harness, and a structured doc-drop importer are now built (backend-only)** — `POST /api/builder/node-proposal/accept` + `api/library_store.py` + `src/pipeguard/node_author/conformance.py` + `src/pipeguard/node_author/importer.py`. **Still deferred:** the Builder's own "Accept to library" button (no frontend caller yet), the `draft→approved` transition, and the free-text `--help`/README half of the importer — see item 5 below + [agent-authoring-contract.md](agent-authoring-contract.md). |
| **Last updated** | 2026-07-11 (MST) |
| **Audience** | all (contributors and Claude Code) |
| **Related** | [design/agents.md](agents.md) (roster #5) · [design/agent-authoring-contract.md](agent-authoring-contract.md) (the boundaries MD this agent's endpoint + UI must satisfy) · [design/frontend/pipeline-builder-brief.md](frontend/pipeline-builder-brief.md) · [design/frontend/README.md](frontend/README.md) (§4 node model) · [design/frontend/handoffs/2026-07-09-review-to-design.md](frontend/handoffs/2026-07-09-review-to-design.md) (§4h, §6) · [design/builder-cards/](builder-cards/) (the tool-card corpus this agent retrieves over) · [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) · [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md) · [ADR-0009](../adr/ADR-0009-corpora-retrieval-upskilling.md) · [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) · [ADR-0016](../adr/ADR-0016-postgres-port.md) (item 9, the library store) · [scope-and-wishlist.md](../requirements/scope-and-wishlist.md) (#9, #11) · [planning/tasks.md](../planning/tasks.md) (T-044, T-046, T-127, T-135) · [functional.md](../requirements/functional.md) (REQ-F-025, REQ-F-089, REQ-F-096) · [journal 2026-07-11 fleet](../journal/2026-07-11-fleet.md) |

> **Built, narrower than proposed.** Originated as maintainer review point #11 and was scoped in the
> review→design brief (§4h). It is **advisory and off the gate** (ADR-0001); it authors a *proposal*,
> never a run. **The rest of this doc is the original design note, preserved as-written** — read the
> box below first for what actually shipped, since it is a different (simpler, narrower) mechanism
> than "drop a tool's docs."

## What actually shipped (2026-07-10, T-046) — read this first

The built agent (`src/pipeguard/node_author/`, verified by reading `agent.py`/`models.py`/
`retrieval.py` + `tests/test_node_author.py`, 19 tests) is **retrieval over a small curated
tool-card corpus**, mirroring the `pipeline_repair/` agent's shape almost exactly — **not** the
doc-drop pipeline this note originally proposed:

1. **Input is a natural-language request** ("add a tool that trims adapters", or a bare tool name)
   — not a dropped `nextflow_schema.json` / `--help` dump / module / README. No document parser of
   any kind exists in the shipped code.
2. **The corpus is fixed and small: 11 curated cards** (`knowledge/tool_cards.jsonl`) — the
   pipeline's own 7 germline tools (fastp, bwa-mem2, samtools markdup, mosdepth, bcftools call/norm,
   MultiQC) plus NGSCheckMate and 3 reference-node cards (FASTA/BED/truth VCF), hand-authored from
   `docs/design/builder-cards/` + the frontend `BTOOLSPEC`. It can only propose a tool **already
   known to the corpus** — it does not onboard a genuinely new/arbitrary tool. This is the opposite
   of "bring your own tools" (#11's original unlock); it is closer to "help an operator rediscover
   or re-propose one of this pipeline's own tools."
3. **No `ArtifactKind`-mapping LLM layer exists.** The design's "hard part" (§ below, mapping a
   tool's raw I/O to `ArtifactKind`s via Claude with a confidence signal) is moot — ports come
   straight from the curated card, deterministically, on both the stub and Claude paths. Claude
   phrases only the `summary`/`rationale` prose (mirrors `pipeline_repair`'s split).
4. **Wishlist #9's deterministic nf-core-schema importer was NOT built as part of this agent** —
   see the correction in [scope-and-wishlist.md](../requirements/scope-and-wishlist.md) #9. The two
   were previously described as sharing a stub core; they do not.
5. **`api/` route + frontend wiring added 2026-07-11 (W2, T-127) — this item is CLOSED for the
   read path.** A new read-only `GET /api/builder/node-proposal?request=…`
   (`api/routers/node_author.py`, mirrors the other advisory-agent read shapes, off-gate, no RBAC
   write) makes `propose_node()` reachable; the Builder's `AuthorToolNodeModal`
   (`BuilderModals.tsx`) now fetches and renders the REAL proposal (typed live/reserved port
   chips, a `platform_version` stamp, heuristic-labelled citation scores) instead of the old
   static mock. **What is still deferred, not silently dropped:** the modal's primary action stays
   "Copy proposal" — it never auto-adds a card.
6. **Accept→library, a conformance harness, and a structured doc-drop importer, ALL BACKEND-ONLY
   (2026-07-11, W2 backend, T-135, commit `5a3dd6a`).** `POST /api/builder/node-proposal/accept`
   (`reviewer`/`approver`) re-derives the proposal server-side (never trusts a client-supplied
   one), runs it through a new `src/pipeguard/node_author/conformance.py` `check_conformance()`
   (mechanically enforces the [agent-authoring-contract.md](agent-authoring-contract.md)
   capability pins: advisory-True, no verdict/confidence anywhere, no `script`/`stub` command-body
   key, closed port vocabulary with unknown→reserved, versioned four ways), and stores a `draft`
   `LibraryEntry` in the new `api/library_store.py` (`PIPEGUARD_LIBRARY_STORE=jsonl|sqlite`, no
   Postgres by design — [ADR-0016 item 9](../adr/ADR-0016-postgres-port.md)); `GET
   /api/builder/library` lists accepted entries. A companion
   `src/pipeguard/node_author/importer.py` (`import_from_nextflow_schema`) deterministically parses
   an nf-core `nextflow_schema.json` into a `NodeProposal` for a tool **not** in the curated
   corpus — the structured, lowest-injection-risk half of the "bring your own tools" gap item 4
   above names; a param maps to a real `ARTIFACT_KINDS` kind only on a confident match, else a
   `reserved` slot (never invented). **Deferred, not silently dropped:** the Builder's "Accept to
   library" button (no frontend caller of either new endpoint exists —
   `grep -rn "node-proposal/accept\|builder/library" frontend/src` returns nothing); the
   `draft→approved` transition; the free-text `--help`/README half of the importer (its own
   spike, per the module docstring). +34 tests (`test_library_store.py`,
   `test_node_author_accept_api.py`, `test_node_author_conformance.py`,
   `test_node_author_importer.py`).

What DID carry over faithfully from the design: **advisory-only, off the gate** (`advisory: True`,
no verdict/confidence field), **never invents a port kind** (`PortSpec.known` computed against the
real `ARTIFACT_KINDS` vocabulary; an unknown kind is `reserved`, never wired), **stub-first / off by
default with a deterministic fallback** (`PIPEGUARD_NODE_AUTHOR_AGENT=stub|claude`, degrade-to-stub
on any error including a safety refusal), and a **conservative "defer to a human" proposal** when no
request/no match (fabricates no tool or ports). Model tier is **mid (Sonnet)**, not the design's
"low–mid" framing — moderate composition, matching the QC-triage default, not the cheap
categorization tier.

---

## The one job

Given a tool's documentation dropped by the operator (an nf-core `nextflow_schema.json`, a
`--help` dump, a Nextflow module, or a README), **propose a typed `ToolNode` card** for the
Pipeline Builder palette — tool name + version, typed input/output ports mapped to the
`ArtifactKind` vocabulary, a schema-driven param form, and candidate output locators — for the
operator to **review, edit, and accept**. This flips the builder from *configure the seeded
tools* to *bring your own tools*, the real unlock behind custom profiles (#4), typed ordering
(#7), and pipeline versioning (#8).

## Why it is tractable and safe (unusually so for a generative feature)

The Pipeline Builder already supplies the two properties that make agent-authored components safe:

1. **A rigid, typed target.** The agent fills a validated `ToolNode` shape (see README §4 data
   contract), not free-form UI. Constrained, schema-bounded generation.
2. **A validation backstop.** A wrong proposal cannot corrupt a pipeline: the typed-wiring
   invariant rejects an incompatible edge at compose time (it springs back), and the gate is a
   terminal node with no data-edge input. The worst case is the operator edits or rejects the
   proposed card — blast radius zero.

## The flow

1. **Drop docs** → the agent extracts: tool name + version; the param set; the candidate input
   and output artifacts.
2. **Propose** a `ToolNode` as a **review card** in the builder (ports, params, candidate
   locators) — flagged clearly as an AI proposal.
3. **Human ratifies**: edit ports/params/locators, accept → it joins the palette (and, with #8,
   a saved custom pipeline version). Reject → nothing changes.

## The hard part: mapping tool I/O → the `ArtifactKind` vocabulary

Mapping a tool's outputs to `fastq / bam / vcf / mosdepth_summary / …` is the one fuzzy step.
Rules:
- The agent **suggests** kinds with a short rationale + a confidence signal.
- **Unknown or ambiguous kinds are flagged for the human, never invented** (the same
  data-honesty guardrail as everywhere — never fabricate; label uncertainty).
- The type system is the backstop: even a ratified-but-wrong kind is caught when the operator
  tries to wire it.

## Layered build — stub-first, then Claude (mirrors the other agents)

A surprising amount needs **no LLM**, so this is the same stub|claude split as triage/feedback
(ADR-0006/0012), and it reuses wishlist **#9** (the nf-core schema-driven form):

1. **Deterministic importer (the stub, $0):** an `nextflow_schema.json` → a param form is a
   pure parse — that is exactly what nf-core schemas are for (wishlist #9). This alone delivers
   most of the value with zero API cost and no fabrication risk.
2. **LLM layer (opt-in Claude):** adds value only for the fuzzy parts — the `ArtifactKind`
   mapping, and parsing unstructured `--help`/README when no schema exists. Lazy `anthropic`,
   degrade to the deterministic path on any error, off by default (`PIPEGUARD_*_AGENT=stub|claude`).

So this is not net-new scope — it is **#9 (schema form) + an ArtifactKind-mapping layer,
surfaced inside the builder**.

## Guardrails (advisory, off the critical path — ADR-0001)

- **Authors a card, never a run.** It proposes a `ToolNode`; it never draws an edge, never
  places a node on the gate, never sets/routes/restates a verdict. Compose ≠ execute holds.
- **Human-in-the-loop by construction** — the proposal is inert until the operator accepts it.
- **Stub-first / off by default** with a deterministic fallback (ADR-0006); the LLM path degrades
  to the deterministic importer on any error (incl. a safety refusal).
- **No fabricated kinds/params** — unknowns are surfaced, not guessed (data-handling guardrail).
- No clinical/diagnostic claims; a tool card is metadata, not a recommendation.

## Build order (when it graduates)

1. The **review-card UX + palette-injection seam** in the Pipeline Builder (needed either way,
   independent of the agent).
2. The **deterministic nf-core schema importer** (#9) — real value, $0.
3. The **LLM ArtifactKind-mapping + unstructured-docs layer** (opt-in Claude).

## Status / next

**Built (narrower scope), roster agent #5** in [agents.md](agents.md) — see "What actually
shipped" above for the concrete divergence from this note's original proposal. Passes the
agent-intake checklist (one job; advisory-only; grounded in a curated corpus; stub-first with a
deterministic fallback). Tracked as **T-046** (done). Covered by the existing agent ADRs
(0001/0006/0009/0012) — no new ADR was needed; no load-bearing decision emerged during the build
that isn't already captured by those.

**Next slices**, in rough order (items 1–2 done, T-127; item 3 partially done, T-135):
1. ~~An `api/` read-only endpoint~~ **DONE** — `GET /api/builder/node-proposal` (T-127).
2. ~~Wire the Pipeline Builder's `AuthorToolNodeModal` to that endpoint~~ **DONE** (T-127).
3. **The doc-drop parsing this note originally proposed — PARTIALLY DONE (T-135).** The structured
   half (`nextflow_schema.json` → a `NodeProposal` for a tool NOT already in the curated corpus,
   `src/pipeguard/node_author/importer.py`) is built, backend-only, no `api/` exposure. **Still
   unbuilt:** the free-text `--help`/README half (the unbounded-input, higher injection-risk
   parse, wants its own spike + safety tests) and any `api/` endpoint for either importer path.
4. The Builder's own "Accept to library" button — `POST /api/builder/node-proposal/accept` +
   `GET /api/builder/library` exist (T-135) but have no frontend caller yet.
5. The `draft→approved` library-entry transition (riding the `pipelines_lifecycle` RBAC pattern).
