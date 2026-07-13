# 2026-07-13 (MST) — Live agent smoke-test over the API + `ask` truncation fix

**Topic:** First end-to-end exercise of the Claude agent seams against a real
`ANTHROPIC_API_KEY`, driven through the FastAPI read/advisory surface — and a
"confident surface vs thin wiring" bug it surfaced in the interactive `ask` path.

## What was done

1. **Connectivity confirmed** — a minimal live `messages.create` on
   `claude-haiku-4-5-20251001` returned `end_turn` (16 in / 8 out), proving the key +
   SDK (`anthropic 0.116.0`) resolve.
2. **Triage `triage_card`** exercised live via `GET /api/runs/{id}/cards/{sample_id}/triage`
   on the pinned `data/mock_run_01` (S4 escalate, S5 hold). Model `claude-sonnet-5`
   wrote grounded, cited notes; citations/addressed-findings stayed deterministic (ADR-0001).
   Verified both directly through the core AND through the API.
3. **Synthesizer** (`BAYLEAF_SYNTHESIZER=claude`) exercised over the same run — Opus
   narration respected the rules' verdict on every card (never set/overrode it, ADR-0001).
4. **The remaining four seams, all exercised live (all six now proven live):**
   a. **Pipeline-repair** (`claude-opus-4-8`) via `GET /api/monitoring/signatures/{sig}/repair`
      on the recurring `PROV-001` barcode signature — a grounded index-distance-guard proposal,
      cited, `advisory`, no verdict.
   b. **Node-author** (`claude-sonnet-5`) via `GET /api/builder/node-proposal` — matched `fastp`
      v0.23.4 with typed live ports + citations; authored metadata only.
   c. **Archivist** (`claude-haiku-4-5`) via `GET /api/runs/{id}/archive-digest` and
      `/api/archive/index` — per-run + cross-run (31-run) organizational digests.
   d. **Feedback-categorization** (`claude-haiku-4-5`) out-of-band (no endpoint) over 3 seeded
      records via `assess_feedback(get_feedback_store().read_all())` — 3 items categorized +
      deterministic themes.
5. **A stale server gotcha:** a pre-existing uvicorn on :8010 (started WITHOUT the env
   flag) served `generated_by: stub` while the newly-launched live one silently failed
   to bind (`address already in use`). Killed the stale PID and rebound. Lesson: confirm
   `generated_by`/`model` on the response, not just a 200.

## The bug (and fix)

`POST /api/runs/{id}/cards/{sample_id}/ask` **silently degraded to the stub on flagged
cards** while working on clean ones. Root cause: `ClaudeTriageAgent.ask` reused the
`triage_card` budget (`max_tokens=1024`, tuned for two short fields). A grounded answer
to an operator question on a flagged card runs long, hit the cap
(`stop_reason=max_tokens`), and the truncated JSON tripped `json.loads` — an
`Unterminated string` that the broad `except` swallowed as if the API were off. The
answer degraded to the stub on exactly the cards where a written answer matters most.

**Fix** (`src/bayleaf/triage/agent.py`):
1. New `_ASK_MAX_TOKENS = 2048` for the free-text `ask` call (kept `triage_card`'s
   two-field note at the smaller default).
2. An explicit `stop_reason in ("refusal", "max_tokens")` guard on **both** `ask` and
   `triage_card`, so a truncation degrades cleanly instead of reading as an opaque
   parse error.

**Tests** (`tests/test_triage.py`, offline, mocked client — no credits):
1. `test_claude_ask_requests_a_larger_budget_than_the_two_field_triage_note` — the
   real anti-regression guard: asserts the `ask` create call requests `_ASK_MAX_TOKENS`
   and that it exceeds `triage_card`'s budget (fails if reverted to the shared 1024).
2. `test_claude_ask_falls_back_to_stub_on_truncation` /
   `test_claude_triage_falls_back_to_stub_on_truncation` — document the clean degrade.

## Second bug (archivist 500 on a clean run)

Exercising the archivist live surfaced a bug in the **deterministic** path (not the LLM):
`api/archivist.py::_summary_prose` evaluated `top_sig = signatures[0]` eagerly even though
the next line already guarded `if signatures`. A released, all-PROCEED run has runs present
but **no recurring signatures**, so `GET /api/runs/{id}/archive-digest` **500'd for every
clean run** (`IndexError`). The Claude path hit it too — `ClaudeArchivist.digest` builds its
grounded base via `self._fallback.digest(runs)` first.

**Fix:** fold the access into the guarded expression (`signatures[0].title` only inside the
`if signatures` branch). **Regression test:**
`test_digest_over_a_clean_run_with_no_recurring_signatures` (real all-clean GIAB run dir) —
verified RED on the old code (`IndexError` at `archivist.py:330`), green with the fix.

## Verification

`uv run ruff check` ✅ · **`uv run mypy` (project gate) ✅ 95 files** · `uv run pytest`
**734 passed / 8 skipped** · `make check` green. Live re-tests after the fixes: flagged S4
`ask` returned a full `claude-sonnet-5` answer that explicitly deferred the verdict
("determined elsewhere", ADR-0001); the clean-run archive-digest returned **200** (was 500).

## Notes / follow-ups

1. **`max_tokens` budgets — pipeline-repair + node-author bumped to 2048 (2026-07-13).**
   synthesizer 8192 (safe); feedback/archivist 512 (bounded tasks). Pipeline-repair and
   node-author were on the same 1024 tier the `ask` path truncated at; both emit two
   free-text fields (summary + rationale), so a long signature/request could clip a proposal
   mid-JSON (same silent-degrade class). Proactively raised to 2048 + given the same
   `stop_reason in (refusal, max_tokens)` guard, with budget + truncation regression tests
   in `tests/test_pipeline_repair.py` / `tests/test_node_author.py` (budget tests verified
   RED on the old 1024 default).
2. Left the demo default OFF (stub) per the conserve-credits posture; the live flip is
   one env var per seam.

**Related:** [design/agents.md](../design/agents.md) ·
[ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) ·
[ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md) ·
[ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md)
