# Authoring-agent scaffold + constraints contract

| Field | Value |
|---|---|
| **Status** | **Active** (2026-07-11, W2 + W2 backend) — the governing contract for how an *authoring* agent is built and what it may do. Wired end-to-end: a read-only endpoint + the Builder modal render + a platform-version stamp (W2), and — backend-only, T-135 — accept→a draft library entry, the `check_conformance()` harness, and a structured (`nextflow_schema.json`) doc-drop importer. Later slices (the Builder's own accept button, `draft→approved`, the free-text `--help`/README importer half, a roster-wide CI conformance sweep) are labelled deferred below. |
| **Last updated** | 2026-07-12 (MST) |
| **Audience** | all (contributors and Claude Code) |
| **Related** | [design/agents.md](agents.md) (the six-agent roster + shared invariants + intake a–g + the observation-binding model + taxonomy) · [design/node-authoring-agent.md](node-authoring-agent.md) (agent #6, what shipped) · [design/nextflow-codegen.md](nextflow-codegen.md) (the compiler + catalog this contract binds to) · [design/builder-cards/README.md](builder-cards/README.md) (the tool-card corpus + reserved kinds) · [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) (rules decide / AI advises) · [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md) (compose ≠ execute) · [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md) (off by default) · [ADR-0009](../adr/ADR-0009-corpora-retrieval-upskilling.md) (corpora/retrieval) · [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) (scoping/tiering) · [ADR-0016](../adr/ADR-0016-postgres-port.md) (item 9, the library store) · [ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md) (the operator custom-script card — the human-authoring surface this contract presupposes) · [ADR-0022](../adr/ADR-0022-agent-observation-binding.md) (attach-as-observation, off the compiled graph) · [requirements/scope-and-wishlist.md](../requirements/scope-and-wishlist.md) (#5/#9/#11) · [planning/tasks.md](../planning/tasks.md) (T-046, T-135) · [journal 2026-07-11 fleet](../journal/2026-07-11-fleet.md) |

## Overview

An **authoring agent** proposes something a human then reviews and incorporates: a Pipeline-Builder
**tool card** (the node-author agent, #6), or — one level up — a **new advisory agent** added to the
roster. This document is the **scaffold + constraint contract** that makes such an agent safe and
repeatable. It is *honest transcription*: every rule below is already enforced in code and cited to
a real `file:line`, so the contract cannot drift into aspiration.

**Two things it governs, one library.**
1. **Card / tool authoring** — an agent that proposes a typed builder node (`node_author/`, agent #6).
2. **Agent authoring** — the general convention for how *any* advisory agent is made and incorporated.
3. **The "accessible agent library" is the existing six-agent roster** — card-synthesizer, QC-triage,
   pipeline-repair, feedback-categorizer, archivist, node-author — surfaced in Settings
   ([`SettingsModelTier.tsx`](../../frontend/src/components/SettingsModelTier.tsx) `AGENTS`), which we
   keep **cleanly expandable** to a 7th/8th agent. There is no greenfield registry; the roster + its
   `BAYLEAF_*_AGENT` env seams + the Settings roster UI *are* the library, governed by this contract.

**The one load-bearing invariant** (everything else serves it): an authoring agent emits
**metadata, never a runnable command**. It fills typed shapes (`ToolCardEntry` / `NodeProposal` /
`PortSpec`); the runnable `script:` / `stub:` body is authored **only by a human** — either curated
into the `ProcessSpec` catalog, or supplied verbatim on an **operator-authored custom-script Builder
card** ([ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md), the human-authoring
surface this contract presupposes). A **human authors the runnable body** before anything compiles.
This is the **compose ≠ execute** trust seam (ADR-0003) — if it ever softened, agent-authored
metadata would become a route to arbitrary command execution. The custom-script card does not soften
it: an *agent* still cannot emit a command (the shapes it writes have no command field), and an
operator's custom command reaches a compute host only inside a SAVED, APPROVED pipeline via the W1
run gate (ADR-0020 safety [i]).

---

## A. The templates it authors *into* (never around)

An authoring agent fills these shapes and only these shapes. It never emits a free-form command,
a file path it invented, or a verdict.

| Template | Where | What the agent may fill | What it must NEVER touch |
|---|---|---|---|
| **`ToolCardEntry`** — one curated corpus card | [`node_author/models.py:156`](../../src/bayleaf/node_author/models.py) + [`node_author/knowledge/tool_cards.jsonl`](../../src/bayleaf/node_author/knowledge/tool_cards.jsonl) (9 proposable entries; NGSCheckMate retired-but-pinned as a commented-out line the loader skips) | tool name, keywords, pinned version, typed `inputs`/`outputs`, suggested `locators`, summary/rationale, `source` citation | any verdict/threshold value (the corpus test asserts none leak: [`tests/test_node_author.py`](../../tests/test_node_author.py)) |
| **`NodeProposal`** — the advisory output | [`node_author/models.py:187`](../../src/bayleaf/node_author/models.py) | (via the corpus, deterministically) tool/version/stage/ports/locators/citations; **only** `summary`/`rationale` prose is the model's | `advisory` is pinned `Literal[True]` ([`:200`](../../src/bayleaf/node_author/models.py)); there is **no verdict and no confidence field anywhere** (G1) |
| **`PortSpec`** — one typed port | [`node_author/models.py:88`](../../src/bayleaf/node_author/models.py) | `kind` (from the real vocabulary), `required`, `role`, `note` | `known` is **computed**, not authored: `known = kind in ARTIFACT_KINDS` ([`:105-109`](../../src/bayleaf/node_author/models.py)) — a port outside the vocabulary is structurally **reserved**, never a live wire |
| **target `ProcessSpec` / `Port`** — the *runnable* card | [`nextflow/catalog.py:41`](../../src/bayleaf/nextflow/catalog.py) (`ProcessSpec`), [`:23`](../../src/bayleaf/nextflow/catalog.py) (`Port`) | **nothing** — the agent proposes metadata that *maps toward* a `ProcessSpec`; a **human** authors the entry | the `script:` ([`catalog.py:50`](../../src/bayleaf/nextflow/catalog.py)) and `stub:` ([`:51`](../../src/bayleaf/nextflow/catalog.py)) command bodies — **authored by a human only** |
| **`LibraryEntry`** — an *accepted* proposal, API-layer, not agent-authored | [`api/routers/node_author.py`](../../api/routers/node_author.py) (the pydantic shape), [`api/library_store.py`](../../api/library_store.py) (the sink) | the API layer wraps a server-re-derived `NodeProposal` with `id`/`status`/`submitted_by`/timestamps — the agent itself fills none of these fields | `status` starts and stays `"draft"` here (no code path sets `"approved"` yet); the embedded `proposal` carries the same never-touch list as the `NodeProposal` row above (enforced again by `check_conformance()` at accept time, §D below) |

**The hard rule, restated:** the agent's output vocabulary is *ports, versions, locators, citations,
and prose*. It cannot express a `script:` / `stub:` body — those fields do not exist on any shape it
writes to. The runnable command is a separate, human-curated artifact.

---

## B. Rules for interacting with the Nextflow integration

How a proposal relates to real execution — `NodeProposal → (human authors) ProcessSpec →
compile_graph → nextflow run`:

1. **Metadata only.** A `NodeProposal` carries ports/version/locators; it is not runnable. Compiling
   and running is the [`nextflow/`](../../src/bayleaf/nextflow/) codegen path, driven by the
   human-curated catalog — see [nextflow-codegen.md](nextflow-codegen.md).
2. **A human authors the runnable body — two human paths, never an agent one.** A tool becomes
   runnable when a **human** either (a) adds its `ProcessSpec` (with a real `script:` and a `stub:`)
   to [`catalog.py`](../../src/bayleaf/nextflow/catalog.py), or (b) authors a verbatim Nextflow
   process body on an **operator-authored custom-script Builder card**
   ([ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md); a non-empty `NfNode.script`
   renders a real process wired from its typed ports, the catalog never consulted for it — a
   blank body is a `CompileError`, never a fabricated command). The **agent never does either** —
   the shapes it writes to (`NodeProposal`/`PortSpec`) have no command field. Path (b) is the
   human-authoring surface this whole contract presupposes; it executes only behind the W1 approval
   gate ([`api/routers/pipeline_run.py`](../../api/routers/pipeline_run.py)), so an un-reviewed
   custom command never reaches a compute host.
3. **Uncatalogued → a loud placeholder, never a fabricated command.** If a tool has no `ProcessSpec`,
   the compiler emits a labelled placeholder process whose `script:` is `exit 1`
   ([`compiler.py:227` `_render_placeholder`](../../src/bayleaf/nextflow/compiler.py), the
   `exit 1` at [`:245`](../../src/bayleaf/nextflow/compiler.py)). `-stub-run` still validates the
   wiring; a real run fails loudly there until a human fills it in. "Any proposed card runs" is **not**
   the claim.
4. **Closed `ArtifactKind` vocabulary; unknown → reserved.** Ports speak the closed
   `ARTIFACT_KINDS` set ([`node_author/models.py:47`](../../src/bayleaf/node_author/models.py)). A
   kind outside it is `reserved` via the structural `PortSpec.known` flag — surfaced as an honest,
   labelled, unwired slot (e.g. `fastp_html`, `adapter_fasta`), never a fabricated live edge.
5. **The drift-guard + live `-stub-run` gate.** A new tool card is only "runnable" once (a) its
   human-authored `ProcessSpec` passes the byte-for-byte reference-pipeline drift test and (b)
   `nextflow run … -stub-run` exercises the DAG — the same gates the seeded germline chain passes
   ([nextflow-codegen.md](nextflow-codegen.md); [`tests/test_nextflow_compile.py`](../../tests/test_nextflow_compile.py)).
6. **Registering a reserved kind is a governed change, never a fabrication.** Adding a new
   `ArtifactKind` widens the closed vocabulary + wires a real port — a human, reviewed change to the
   registry, not something an agent proposal performs.
7. **An agent ATTACHES to a node as a read-only observation, never as a graph edge**
   ([ADR-0022](../adr/ADR-0022-agent-observation-binding.md)). Where an *observing* agent (QC-triage
   today) is bound to a Pipeline-Builder node, the attachment is a persisted
   `AgentBinding {agent, node, grants:('outputs'|'logs')[]}` (`frontend/src/types.ts`) stored in a
   **sibling `graph.agent_bindings` save-envelope key the compiler never dereferences** — the
   compile/run payload stays a pure function of `{nodes, edges}`, so a binding is byte-identical-compile
   safe (compose ≠ execute by construction). A binding grants a **scoped, node-only read**
   (`GET /api/runs/{id}/nodes/{node}/observations`; `outputs` default, `logs` opt-in + de-identified),
   never a data edge, a card, or a verdict. This is the *observing* dual of §A's *authoring* rule: an
   authoring agent emits metadata never a command; an observing agent reads outputs never the graph.
   Only node-scoped agents are attachable; run-/org-scoped system agents (pipeline-repair, archivist)
   launch from Agent-triage, not the Builder palette (the taxonomy in [agents.md](agents.md)).

---

## C. UI do's and don'ts

The Builder's "Author a tool node" modal
([`BuilderModals.tsx` `AuthorToolNodeModal`](../../frontend/src/components/BuilderModals.tsx)) is the
reference surface. It reads the live proposal from `GET /api/builder/node-proposal` and renders it
verbatim.

**Do:**
1. **Surface proposals as advisory** — labelled "advisory," the agent "never wires an edge or touches
   a verdict," stub-first ($0). The roster row reads `roster #6 · advisory`.
2. **Show reserved kinds, do not wire them.** Render reserved ports in a distinct (amber) tone with an
   explicit "reserved — surfaced, never wired; registering one is a governed change" note.
3. **Keep the accept action human, confirm-gated, and audited** — when accept→card lands (deferred
   slice), it rides the explicit-edit + `useConfirm` + client-audit house rules, exactly like every
   other stakes-y off-gate write ([ConfirmDialog](../../frontend/src/components/ConfirmDialog.tsx)).
4. **Label heuristic scores honestly** — a `NodeCitation.score` renders as `…% (heuristic)`, never
   "confidence."
5. **Be scale-aware** — the corpus is small today, but any list/table follows the app's
   pagination/search conventions (no infinite rows).

**Don't:**
1. **Never auto-add.** A proposal never places a node on the canvas or the gate; a human accepts. The
   modal's primary action is "Copy proposal" — a harmless utility — not a silent mutation.
2. **No false "Live" labels.** An agent shows `Live` only when its `BAYLEAF_*_AGENT=claude` seam is
   actually on; otherwise `Stub · $0`. A phase-2 seam is labelled `phase-2`, never dressed up as wired
   (the Settings roster's honest `wired` / `phase2` flags).
3. **Never render a verdict or confidence** — the shape has no such field to render.

---

## D. Conventions for how any advisory agent is made + incorporated

The six-agent `stub|claude` seam is the mould. Adding a 7th/8th agent means reproducing it — run the
idea through the [`agents.md:66` intake checklist a–g](agents.md) first, then build to this shape:

1. **One job.** State it in a sentence (intake a). If it needs two, it is two agents.
2. **Advisory + off the critical path.** It narrates/proposes/organizes; the gate's verdict is
   identical whether the agent runs or not (ADR-0001; [agents.md](agents.md) invariants 1–2). Its
   output model pins `advisory: Literal[True]` and carries **no verdict/confidence field**.
3. **Env selector + model knob.** `BAYLEAF_<AGENT>_AGENT=stub|claude` selects the agent
   ([`node_author/agent.py:321` `get_node_author_agent`](../../src/bayleaf/node_author/agent.py));
   `BAYLEAF_<AGENT>_MODEL` picks the tier (ADR-0012). Both go in
   [`.env.example`](../../.env.example).
4. **Stub-first ($0), lazy SDK, degrade-to-stub on any error incl. refusal.** The stub is the default
   and the fallback; `anthropic` is imported lazily; a refusal
   ([`agent.py:300`](../../src/bayleaf/node_author/agent.py)) and any exception
   ([`:316`](../../src/bayleaf/node_author/agent.py)) both fall back to the deterministic stub. AI is
   off by default (ADR-0006).
5. **Prose-only LLM schema.** The model phrases prose *only*; everything structured (ports, versions,
   ids, scores, citations) stays deterministic. The JSON schema handed to the model exposes just the
   prose fields (`node_author`'s `_PROSE_SCHEMA` = `{summary, rationale}`, `additionalProperties:False`,
   [`agent.py:176`](../../src/bayleaf/node_author/agent.py)).
6. **Grounded + cited + structured output.** Claims retrieve over a curated corpus (ADR-0009) and carry
   citations; the output is a typed record with provenance (ADR-0007), so it feeds the ledger/ML.
7. **Tests + registration.** Add a conformance test mirroring
   [`tests/test_node_author.py`](../../tests/test_node_author.py) (advisory-true, no verdict/confidence,
   `PortSpec.known == kind in ARTIFACT_KINDS`, degrade-to-stub); register a roster row in
   [`agents.md`](agents.md) and in the Settings roster
   ([`SettingsModelTier.tsx`](../../frontend/src/components/SettingsModelTier.tsx) `AGENTS`), with a
   design doc/ADR for anything non-trivial.

**Where it registers in the library:** a roster row (Settings, `AGENTS`) + a `BAYLEAF_*_AGENT` seam
+ a design/agents.md entry. That trio *is* the library membership.

---

## Capability pins (the non-negotiables)

| Pin | Rule | Enforced by |
|---|---|---|
| **Metadata, not commands** | authors ports/version/locators/prose; never a `script:`/`stub:` body | the shapes it writes to have no command field; `script:`/`stub:` live in [`catalog.py:50-51`](../../src/bayleaf/nextflow/catalog.py) |
| **Closed vocabulary** | ports only from `ARTIFACT_KINDS`; unknown → reserved | `PortSpec.known` computed ([`models.py:105-109`](../../src/bayleaf/node_author/models.py)) |
| **No verdict / no confidence (G1)** | an authored artifact can never carry or move a gate value | `advisory: Literal[True]` + no such field ([`models.py:200`](../../src/bayleaf/node_author/models.py)); asserted by [`test_node_author.py`](../../tests/test_node_author.py) |
| **Versioned four ways** | a proposal pins **tool version + corpus + schema + platform** | `version` + `corpus_version` + `schema_version` + `platform_version` ([`models.py:207,233-239`](../../src/bayleaf/node_author/models.py)); `platform_version` sourced from `pyproject.toml` via [`identifiers.PLATFORM_VERSION:47`](../../src/bayleaf/identifiers.py) |
| **Reserved-vs-known = governed change** | widening the vocabulary is a human, reviewed registry change | reserved ports are surfaced-not-wired; no agent path mutates `ARTIFACT_KINDS` |
| **Off by default ($0)** | stub-default + degrade-to-stub | [`agent.py:321,300,316`](../../src/bayleaf/node_author/agent.py) |
| **Human review + approval** | inert until a human accepts *and* authors the `ProcessSpec` | `POST /api/builder/node-proposal/accept` requires `reviewer`/`approver` RBAC + re-derives + conformance-checks server-side (T-135, [`api/routers/node_author.py`](../../api/routers/node_author.py)); the **UI's own confirm-gated accept button is now built** (2026-07-13, [`BuilderModals.tsx`](../../frontend/src/components/BuilderModals.tsx) → `api.acceptNodeProposal`, viewer→403), so "human review" is enforced by both an in-app confirmation step and the endpoint's RBAC |

---

## Versioning — "versioned to the platform version"

Before W2 a `NodeProposal` pinned only `corpus_version` + `schema_version`; the platform version was
`pyproject.toml`'s `version` (`0.1.0`), **unreferenced by code**. W2 closes that: a single
`PLATFORM_VERSION` constant reads the installed package version
([`identifiers.py:47`](../../src/bayleaf/identifiers.py); `pyproject.toml` is the one source of
truth, with a literal fallback so a version stamp can never break the record layer) and is stamped
onto every proposal ([`models.py:239`](../../src/bayleaf/node_author/models.py)) and folded into its
`content_hash`. A proposal now pins all four coordinates — **tool version + corpus + schema +
platform** — so a scoped, human-approved library entry stays traceable to exactly what produced it.
It is placed beside `SCHEMA_VERSION` (the module that already stamps `schema_version`) rather than a
second hand-maintained constant.

---

## Status — what is wired vs deferred (honest)

**Wired end-to-end (W2 MVP, 2026-07-11):**
1. **This contract MD** — the headline deliverable.
2. **Read-only endpoint** `GET /api/builder/node-proposal?request=…` →
   [`api/routers/node_author.py`](../../api/routers/node_author.py), mounted in
   [`api/main.py:100`](../../api/main.py); mirrors the read-only
   `GET /api/monitoring/signatures/{sig}/repair` shape ([`main.py:1442`](../../api/main.py)).
   Off-gate, advisory, no RBAC write.
3. **Modal read-path** — `AuthorToolNodeModal`
   ([`BuilderModals.tsx`](../../frontend/src/components/BuilderModals.tsx)) fetches the real proposal
   (`api.nodeProposal`, [`api.ts`](../../frontend/src/api.ts)) and renders it verbatim; the old static
   STAR mock is gone.
4. **Roster honesty** — the Settings node-author row now reads `wired`, with the corrected env var
   `BAYLEAF_NODE_AUTHOR_AGENT` ([`SettingsModelTier.tsx`](../../frontend/src/components/SettingsModelTier.tsx)).
5. **Platform-version stamp** — above.

**Wired, backend-only (W2 backend, 2026-07-11, T-135, commit `5a3dd6a`):**
1. **Accept → draft library entry** — `POST /api/builder/node-proposal/accept`
   (`reviewer`/`approver`, [`api/routers/node_author.py`](../../api/routers/node_author.py))
   re-derives the proposal server-side from the request (never trusts a client-supplied proposal),
   guards `matched`, runs it through item 4's conformance harness, and stores a `status="draft"`
   `LibraryEntry`. **Narrower than this row's original framing above:** it does NOT (yet) ride the
   `PipelineGraph` draft→approve envelope or `pipelines_lifecycle`'s RBAC transitions — it is its
   own store with its own `status` field, not a reuse of the pipeline lifecycle machinery. The
   human still authors the `ProcessSpec` before anything is runnable (unchanged).
2. **Governed library store** — [`api/library_store.py`](../../api/library_store.py): `LibraryStore`
   Protocol + `JsonlLibraryStore`/`SqliteLibraryStore`, `BAYLEAF_LIBRARY_STORE=jsonl|sqlite`
   (**no `postgres` adapter, by design** — a small node-local corpus of accepted drafts, not shared
   product state, [ADR-0016 item 9](../adr/ADR-0016-postgres-port.md)). `GET /api/builder/library`
   lists entries. A roster-expansion UI over it is still unbuilt.
3. **Doc-drop importer — structured half only.**
   [`node_author/importer.py`](../../src/bayleaf/node_author/importer.py)
   `import_from_nextflow_schema()` deterministically parses an nf-core `nextflow_schema.json` →
   a `NodeProposal` for a tool NOT already in the curated corpus, mapping `format: file-path`
   params → typed ports on a confident, conservative match, else a `reserved` slot (never
   invented) — designed to pass item 4's conformance harness by construction. **The free-text
   `--help`/README half stays its own deferred spike** (unbounded input, higher injection risk;
   the module docstring says so explicitly).
4. **A conformance harness — narrower than "Agent-manifest" framing below.**
   [`node_author/conformance.py`](../../src/bayleaf/node_author/conformance.py)
   `check_conformance()` is a **pure, deterministic function** mechanically asserting the five
   capability pins (advisory-True; no `verdict`/`confidence` key anywhere; no `script`/`stub`
   command-body key anywhere; closed port vocabulary with unknown→`reserved`; versioned four ways)
   against a single candidate `NodeProposal` or raw mapping — invoked at accept time (item 1
   above) so a violation 422s before an entry is stored. It is **not yet** the roster-wide,
   CI-enforced `test_agent_conformance.py` deferred item 4 below still describes: today it checks
   one node-authoring candidate on demand, not every advisory agent's output on every CI run.

**Still deferred, labelled (not silently dropped):**
1. ~~The Builder's own "Accept to library" UI action.~~ **BUILT (2026-07-13).**
   [`BuilderModals.tsx`](../../frontend/src/components/BuilderModals.tsx) calls
   `api.acceptNodeProposal` (`POST /api/builder/node-proposal/accept`), confirm-gated +
   reviewer/approver-gated (viewer→403); it persists a metadata-only draft `LibraryEntry` and does
   **not** add a canvas node.
2. **The `draft→approved` library-entry transition** — the store already carries `status`, so no
   migration is needed when this lands; it should ride the same confirm-gated, audited RBAC pattern
   `pipelines_lifecycle` uses, per item 1 above's honest correction.
3. **The free-text `--help`/README half of the doc-drop importer** — its own spike with its own
   safety tests, per item 3 above.
4. **A roster-wide `AgentManifest` + `test_agent_conformance.py` CI sweep.** Item 4 above's
   `check_conformance()` proves the *mechanism* works for node-authoring; generalizing it to a
   per-agent manifest asserted across the whole six-agent roster on every CI run (making this MD
   self-enforcing everywhere, not just at one accept endpoint) is the natural next step.

---

*Marker legend — distinguish claim types where confusion is likely:*
**Fact** · **Assumption** · **Decision** · **TODO**.
