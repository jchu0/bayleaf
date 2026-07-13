# System agents — chat surface & structured chat history

| Field | Value |
|---|---|
| **Status** | Proposed (design) |
| **Last updated** | 2026-07-13 (MST) — initial design |
| **Audience** | software / design / reviewers |
| **Related** | [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) (advisory only), [ADR-0022](../adr/ADR-0022-agent-observation-binding.md) (System-agents taxonomy), [ADR-0024](../adr/ADR-0024-scope-by-wiring.md) (agent file access), [agents.md](agents.md), [structure-for-ML memory], [restrict-costly-subagents memory] |

## Why

The **System agents** page is currently a minimal read-only panel. Redesign it into a **chat
surface**: a left panel to select a system agent, a chat window to converse, and a per-user history
of past chats. All history is persisted as **structured, ML-minable records** (per the
structure-for-ML principle) — even when a user archives/deletes from their own view.

**Scope of "system agents" here** (ADR-0022 taxonomy): the **cross-run / org-wide advisory** agents
— **pipeline-repair** and **archivist**. QC-triage stays per-run (its own Triage page); node-author
stays in the Builder; the monitoring agent is a *tool-agent* on the graph (ADR-0023), not here.

## Surface

1. **Left panel** — selectable system agents (pipeline-repair, archivist), each with a one-line
   scope note. Selecting one opens or resumes a chat with it.
2. **Chat window** — reuses the existing `ask` plumbing (`ask_agent` → `AgentReply`), generalized
   from per-card to a free-standing, run-independent session. Every agent turn stays **advisory**:
   cited, no verdict/confidence (ADR-0001); citations stay deterministic, the model writes prose.
3. **My chats** — the acting user's session list with **archive** and **delete** that are
   **view-scoped soft-deletes**: the record is retained in the store for ML; the user's view hides
   it. (Distinct from a hard delete, which we do not offer here.)

## Data model (`chat_store`, off-gate)

Follows the existing store abstraction (`base_store.py` → jsonl / sqlite / postgres,
degrade-to-jsonl; env-selected). Two typed records:

1. `ChatSession` — `{session_id, created_at, actor{id,role}, agent_id, title, context_refs,
   status: active|archived|deleted, updated_at}`. `context_refs` optionally ties a session to a
   run/graph so the agent can ground its answers (and, for scope-by-wiring, know its file access).
2. `ChatMessage` — `{message_id, session_id, ts, role: user|agent, content, agent_id, model,
   citations[]}`. Append-only.

`status` drives the per-user view; **archive/delete flip `status`, never remove rows** — retention
for downstream ML is the whole point.

## API (off the gate)

- `POST /api/agents/{agent}/chat` — send a message in a session (creates one if absent); persists
  the user turn + the agent turn; returns the `AgentReply`. Auth: viewer+ (advisory read-family
  floor, mirrors the `ask` endpoint); a live-API call is still env-gated + stub-first (ADR-0006).
- `GET /api/agents/chats` — the acting user's sessions (paginated; excludes `deleted`/`archived`
  per a filter). `GET /api/agents/chats/{session_id}` — its messages.
- `POST /api/agents/chats/{session_id}/archive` / `DELETE /api/agents/chats/{session_id}` —
  view-scoped soft-deletes (set `status`). Reviewer+ not required (a user manages their own view);
  the record persists regardless.

## Invariants

1. **Advisory only** — no verdict/confidence anywhere in the chat surface (ADR-0001).
2. **Retain-for-ML** — user-facing archive/delete never destroy the stored record.
3. **Stub-first** — the page works AI-off (grounded retrieval answer), live only when the agent's
   env flag is set (ADR-0006).
4. **Least-privilege grounding** — an agent's file grounding in a chat obeys scope-by-wiring
   (ADR-0024) + de-id; a run-independent chat has no file access beyond its `context_refs`.

## Open questions

- Session titling: auto-derive from the first message vs let the user name it.
- Whether archivist chats should expose its DB-retrieval tool inline (see [agent-capabilities.md](agent-capabilities.md)).
