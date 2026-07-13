# 2026-07-13 (MST) — P3 §1: Archivist read-only cross-run historic retrieval

**Topic:** Built the first P3 agent-capability upgrade (design/agent-capabilities.md §1) — the
archivist can now "pull historic data," grounding the System-agents chat for run-independent
organizational/historical questions. Closes P1's deferred archivist grounding.

## What shipped (`8838142`)

- `api/archivist_retrieval.py` — a read-only cross-run aggregate (verdict distribution, top
  recurring signatures, run inventory), tried in two sources: **(1) the persistence projection**
  (`get_repository` — the production form ADR-0024 names), **(2) fallback: re-derive from the served
  run dirs** via the archivist's own `build_run_input_from_dir` (the offline demo default — the
  `:memory:` projection is empty until `rebuild-db`). Same historic runs, cached for the process
  lifetime (deriving re-runs the gate per run dir).
- `agent_chat._archive_grounding` — no run named → `historic_grounding()`; a named run still grounds
  in that run's digest.

## Guardrails (all met)

1. **Read-only** — only `Repository` read methods / a read-only re-derivation; never writes.
2. **De-identified by construction** — the aggregate is counts + run ids + rule ids + signature
   titles; the projection rows carry no subject/PII, so nothing sensitive flows through.
3. **Cited** — run ids + recurring-signature titles as `ChatCitation`s.
4. **Advisory, off the gate (ADR-0001)** — grounds a chat answer; sets no verdict.

## Verification

`make check` green (full suite **765 passed / 8 skipped**, mypy 101 files, ruff clean). 4 offline
tests (aggregate shape, real derivation over the committed run fixtures, cited grounding, chat
grounds a run-independent question via the stub). **Live-verified:** an archivist chat question
"across all our runs, what recurs + how do verdicts break down?" → Haiku narrated the REAL aggregate
(31 runs, 184 cards; proceed 88 / hold 56 / escalate 27 / rerun 13; top issues with real counts),
cited by run id.

## P3 status + honest dependencies (remaining)

- **§2 pipeline-repair** — the **issues+resolutions store** half genuinely depends on the
  **monitoring tool-agent** (ADR-0023) as its producer, which isn't built. The **tool/bayleaf docs
  corpus** half (repair understands the systems + limits) is buildable independently.
- **§3 node-author** — QoL authoring popup + doc-upload + schema-delta-as-proposal +
  scaffolds-as-assets; largely a frontend build over the already-live node-proposal endpoint.

**Related:** [design/agent-capabilities.md](../design/agent-capabilities.md) ·
[ADR-0024](../adr/ADR-0024-scope-by-wiring.md) · [system-agents-chat.md](../design/system-agents-chat.md) ·
[ADR-0023](../adr/ADR-0023-agent-taxonomy-and-action-boundary.md) (the §2 producer) ·
[TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md)
