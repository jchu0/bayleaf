# 2026-07-13 (MST) — P3 §3: node-author "Accept to library" button (QoL)

**Topic:** First slice of P3 §3 (node-author QoL, design/agent-capabilities.md §3) — wired the
Builder's **Accept-to-library** button, closing a CLAUDE.md-listed deferral. The node-author
backend (proposal + accept + conformance + library store) was already solid + live; the gap was the
frontend surface, which promised "you review & accept" but only offered Copy.

## Shipped (`96b363b`)

- `AuthorToolNodeModal` (`frontend/src/components/BuilderModals.tsx`): the footer now has a real
  **Accept to library** action alongside a demoted **Copy**. Accepting:
  - is **confirm-gated** (`useConfirm`) with honest copy — it saves a **metadata-only DRAFT** (typed
    ports, pinned version, citations), never a canvas node / edge / runnable command; a human still
    authors the `ProcessSpec` (compose ≠ execute, ADR-0001/0003);
  - is **role-gated** in the UI (`useRole.isReviewer`) purely for UX — the server RE-CHECKS
    (`require_role("reviewer","approver")`, viewer→403 verified live);
  - posts to the existing `POST /api/builder/node-proposal/accept`, which **re-derives** the
    proposal from the request + runs `check_conformance` (a client can't smuggle library metadata).
- `api.ts`: `acceptNodeProposal` / `builderLibrary` + the `LibraryEntry` type. Stale "11-card"
  corpus text → "curated corpus".

## Verification

`tsc -b` + vite + lint clean. **Live** (backend running): reviewer accept of "mosdepth coverage" →
`draft` `LibraryEntry` stamped `a.rivera`; a **viewer** accept → **403** (server-enforced, not just
the hidden button); `GET /api/builder/library` then lists the entry. The pre-existing backend accept
tests (`tests/test_node_author_accept_api.py`) remain green (full suite unaffected — frontend-only
change).

## P3 §3 remaining (still design, honest)

1. **Inline edit** of the proposal before accept + the `draft→approved` transition.
2. **Doc-upload → schema-delta-as-proposal** — the `nextflow_schema.json` importer exists
   backend-only; wiring an upload that drafts the card + Nextflow wiring + a **human-approved**
   data-schema delta (never auto-mutating the contract) is the next meaty piece.
3. **Scaffolds-as-assets** — reusable versioned templates (tool-card / Nextflow process /
   metric-registry-entry) the agent fills so output conforms by construction; generalizes to all
   agents. Not started.

**Related:** [design/agent-capabilities.md](../design/agent-capabilities.md) §3 ·
[design/agent-authoring-contract.md](../design/agent-authoring-contract.md) ·
[ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) · [TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md)
