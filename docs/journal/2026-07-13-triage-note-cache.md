# 2026-07-13 (MST) — Persistent cache for rule-derived triage notes

**Topic:** Cache generated QC-triage notes in the backend so navigating away and back doesn't
regenerate them (no repeat Claude call on the live path), with every note saved + logged.

## Why

`GET /api/runs/{id}/cards/{sid}/triage` generated the note per request. The note is DERIVED from
the card's rule findings + the retrieval corpus + the agent; on the live path each generation is a
Claude call. Re-fetching on navigation regenerated an identical result — wasted cost + latency, and
the note wasn't persisted.

## What shipped (`7eefe91`, branch `feat/triage-cache`)

1. **`api/triage_cache_store.py`** — a persistent cache over the shared `api.base_store` generic
   (jsonl default / sqlite / postgres, degrade-to-JSONL). `get(cache_key)` / `put` (upsert).
   `triage_cache_key(...)` hashes the card's finding **signatures** (rule-version-independent,
   stable across restarts — not the per-run gate id) + agent identity (name/model) + corpus
   version, so a changed card / flipped agent / bumped corpus regenerates while an unchanged one
   reuses.
2. **`api/triage_cache.py`** — `get_or_create_triage(run_id, card)` cache-through: hit → served
   from the store; miss → generate, save, log. **Honest cache policy:** a note is cached only when
   `generated_by == the SELECTED agent`, so a transient live-API degrade-to-stub is NOT pinned under
   the live key — it retries next request instead of caching a fallback forever.
3. **Endpoint** now serves via the cache. Off the gate (ADR-0001): caching never re-enters the
   deterministic gate or sets a verdict.
4. **"Saved + logged":** each cache record is a structured, ML-minable row — `{cache_key, run_id,
   sample_id, generated_by, model, corpus_version, addresses_signatures, created_at, note}` — the
   durable backend log of every generated note (plus best-effort `_log.info` HIT/MISS lines).
5. `.env.example` — the new `BAYLEAF_TRIAGE_CACHE_*` vars (+ backfilled the chat / agent-binding
   store vars added earlier this session).

## Verification

`make check` green (full suite **776 passed / 8 skipped**, mypy 104 files, ruff clean). 4 offline
tests (key stability, generate-once-then-serve — asserts the agent is invoked exactly once across
two calls, endpoint returns the SAME note id twice, degraded-note-not-cached). **Live-verified**
with `BAYLEAF_TRIAGE_AGENT=claude`: two GETs of S4's triage → the same `note_…` id, one persisted
cache record (`generated_by=claude`, `model=claude-sonnet-5`).

## Process note

The commit was initially made on `main` by mistake (right after merging PR #5 the worktree was on
`main`); recovered by moving it to `feat/triage-cache` and resetting local `main` to `origin/main`
(the commit was never pushed to `main`). This change ships via its own PR.

## Follow-ups (not built)

- Cache **eviction/TTL** — entries are keyed by content so they self-supersede, but old keys
  accumulate; a size/age bound is a future concern.
- Serving the cached note could also carry a `served_from_cache` hint to the UI (cosmetic).

**Related:** [design/agents.md](../design/agents.md) (QC-triage) ·
[ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) ·
[ADR-0016](../adr/ADR-0016-postgres-port.md) (the store seam) · [structure-for-ML memory]
