# 2026-07-13 (MST) — System-agents chat: P1 build (store → backend → UI)

**Topic:** Built the System-agents chat surface end-to-end (design/system-agents-chat.md),
following the ADR-0023 agent-hardening design set. Also fixed nav label casing (UIC-21) and
committed the design set earlier the same session.

## Increments (each its own commit, `make check` green)

1. **`ae14aa2` label casing** — sentence case (Sample metadata / System agents), UIC-21.
2. **`a8087a4` design set** — ADR-0023/0024/0025 + 3 design docs + ToC/journal.
3. **`871eba3` `chat_store` (P1.1)** — the ML-structured persistence backbone: a chat session is
   a mutable record with embedded `messages[]` + a user-driven `status`, over the shared
   `api.base_store` generic (jsonl/sqlite/postgres, degrade-to-JSONL). Archive/delete are
   **view-scoped soft-deletes — the record is retained for ML** (no hard delete). 6 offline tests.
4. **`b20c2a8` chat backend (P1.2 + P1.3)** — `api/chat.py` (typed contract, advisory-only, no
   verdict/confidence field), `api/agent_chat.py` (the one place an agent turn is produced: ground
   deterministically → stub-first → live Claude only per the agent's existing env flag, degrade on
   any error/refusal, 2048-token budget + refusal guard), `api/routers/agent_chat.py`
   (send / list-mine / get / archive / restore / delete; sessions scoped to the acting actor).
   7 offline endpoint tests.
5. **`652d014` chat UI (P1.4)** — `SystemAgents.tsx` rewritten from a 2-button launcher into a
   chat surface: left agent panel + "My chats" (archive/restore/delete) + chat window with an
   optimistic composer; agent turns show provenance (stub "retrieval (AI off)" vs "claude · model")
   + deterministic citations. `api.ts`/`types.ts` chat methods + types. `tsc -b` + vite clean.

## Grounding (honest scope)

- **pipeline-repair** chat grounds in its real remediation corpus (`RemediationRetriever`).
- **archivist** chat grounds in a **named run's** archive digest for P1 (`context_refs.run_id`);
  the **cross-run DB-retrieval** tool is the deferred P3 upgrade (design/agent-capabilities.md §1) —
  labelled, not faked.
- Reused the per-agent env flags (`BAYLEAF_PIPELINE_REPAIR_AGENT` / `BAYLEAF_ARCHIVIST_AGENT`) so
  `=claude` turns chat live too; stub-first + $0 by default (ADR-0006).

## Verification

`make check` green across increments (final full suite **751 passed / 8 skipped**, mypy 99 files,
ruff clean); `tsc -b` + vite clean. **Live-verified** over the API: `POST /api/agents/
pipeline_repair/chat` returned an Opus (`claude-opus-4-8`), grounded, cited answer with a persisted
2-message session. Advisory guarantee held (no verdict/confidence anywhere).

## Next (per the design set, deferred)

- P2 scope-by-wiring (ADR-0024) → gives agents real tool-folder file access + would extend chat
  grounding beyond a single named run.
- P3 archivist DB retrieval; pipeline-repair issues+resolutions corpus (fed by the monitoring
  tool-agent, ADR-0023); node-author QoL + scaffolds.
- Session titling currently = first message truncated (design open question); good enough for P1.

**Related:** [design/system-agents-chat.md](../design/system-agents-chat.md) ·
[ADR-0023](../adr/ADR-0023-agent-taxonomy-and-action-boundary.md) ·
[agent-capabilities.md](../design/agent-capabilities.md) · [TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md)
