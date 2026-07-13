# Agent capability upgrades — grounding, corpora & authoring QoL

| Field | Value |
|---|---|
| **Status** | 🚧 §1 archivist DB retrieval **built** (P3, wired into the chat, live-verified); §2 pipeline-repair corpora + §3 node-author QoL still design |
| **Last updated** | 2026-07-13 (MST) — §1 built: `api/archivist_retrieval.py` (read-only cross-run aggregate, projection-first with run-dir-derivation fallback) grounds the archivist chat for run-independent questions. Prior: initial design |
| **Audience** | software / design / reviewers |
| **Related** | [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0009](../adr/ADR-0009-corpora-retrieval-upskilling.md) (corpora/retrieval), [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md), [ADR-0023](../adr/ADR-0023-agent-taxonomy-and-action-boundary.md), [ADR-0024](../adr/ADR-0024-scope-by-wiring.md), [ADR-0025](../adr/ADR-0025-versioned-reversible-agent-config.md), [agents.md](agents.md), [agent-authoring-contract.md](agent-authoring-contract.md) |

## Why

Each advisory agent is real but thinly grounded — retrieval over small fixed corpora. This doc
specs the per-agent capability upgrades the maintainer asked for. All stay **advisory** (ADR-0001):
richer *inputs* and *authoring aids*, never verdict/authority. All persisted data is **structured
for ML** (timestamps, actor, ids), and any editable asset is **versioned/reversible** (ADR-0025).

## 1. Archivist — read-only DB retrieval

**Built (P3, 2026-07-13):** `api/archivist_retrieval.py` gives the archivist a read-only cross-run
aggregate (verdict distribution, recurring signatures, run inventory), tried projection-first
(`get_repository`) with a run-dir-derivation fallback for the offline demo (the `:memory:` projection
is empty until `rebuild-db`). It grounds the System-agents chat when the operator asks a historical
question without naming a run — live-verified (Haiku narrated 31 runs / 184 cards with real counts,
cited by run id). Bounds (all met):

1. **Read-only** — never writes the ledger/projection; the event log stays authoritative (ADR-0002).
2. **De-identified** — results pass `api.deid.scrub_text`; no PII surfaces.
3. **Cited** — every historical claim references the run/record it came from.
4. **Structured out** — returns typed rows, not free prose, so the chat can render + the answer is
   grounded. The archivist narrates over those rows; it never invents a number.

## 2. Pipeline-repair — issues+resolutions store + docs corpora

Two grounding sources beyond today's remediation corpus:

1. **Recurring issues + resolutions**, as **structured records**, fed by the monitoring tool-agent's
   issue store (ADR-0023 §4) and by past `RepairProposal`s marked resolved. Shape:
   `{signature, class, first_seen, count, run_ids, resolution?, resolved_by?, resolved_at?}`. This
   is the live, minable memory that makes repair proposals better over time.
2. **A documentation corpus** covering (a) each tool card's tool docs and (b) **bayleaf's own
   system docs** (architecture, ADRs, limitations) so the agent understands the systems involved,
   their seams and limits — not just the tool in isolation. Retrieval over this corpus uses the
   existing seam (`KeywordRetriever` now; the `EmbeddingRetriever` seam later, ADR-0009).

Repair stays **advisory**: it proposes cited remediations; it never edits a pipeline or sets a
verdict (unchanged from today).

## 3. Node-author — authoring QoL, doc-upload, schema-delta, scaffolds

The backend is wired + live (`GET /api/builder/node-proposal` → live `claude-sonnet-5`); the gap is
the **authoring surface** and the **onboarding inputs**.

1. **Tool-node authoring popup (QoL).** Replace the minimal surface with a proper popup/page: enter
   a request or tool name → see the proposed node (typed ports, pinned version, locators, cited
   rationale) rendered clearly, with inline edit + "accept to library" (the accept path + conformance
   harness already exist backend-side).
2. **Doc-upload.** Let the operator attach relevant documentation (a `nextflow_schema.json`, a
   README, `--help` text) so onboarding a *new* tool updates the necessary parts **from that input**
   rather than searching: the card metadata, the Nextflow process wiring, and the **data-schema
   delta**. Extends the existing doc-drop importer + `check_conformance`.
3. **Schema delta stays a PROPOSAL.** "Update the data schema to accommodate the new card" is
   consequential — the agent drafts the card + the schema/registry delta + the nextflow wiring as a
   **human-approved proposal**; it never auto-mutates the core data contract. (ADR-0001 + the
   authoring-contract boundary.)
4. **Scaffolds-as-assets** (generalizes to **all** agents). Ship reusable, versioned templates —
   a tool-card scaffold, a Nextflow process scaffold (`script:`+`stub:`), a metric-registry-entry
   scaffold — as agent assets. The agent fills a scaffold rather than free-composing, making card
   creation **quicker and more reproducible**, and the output conforms by construction. Scaffolds
   are versioned/reversible like other editable assets (ADR-0025).

## Cross-cutting invariants

1. Advisory only (ADR-0001); richer inputs, never authority.
2. Read paths de-identified + sandboxed (ADR-0024 for files; deid for DB/logs).
3. All new persisted data typed + retained for ML; editable assets versioned (ADR-0025).
4. Stub-first, live only when the agent's env flag is set (ADR-0006).

## Open questions

- Archivist DB tool: expose as a constrained query DSL vs a fixed set of parameterized queries
  (safer, less flexible).
- Which bayleaf system docs to include in the repair corpus (all ADRs? a curated subset?).
- Scaffold format: templated files vs a structured schema the agent fills.
