# Run-of-Show — live demo script

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | presenter |
| **Related** | [demo_plan.md](demo_plan.md) (narrative + wow moments this script drives), [one-pager.md](one-pager.md), [../design/architecture.md](../design/architecture.md), [../data/provenance.md](../data/provenance.md), [../quality/evaluation.md](../quality/evaluation.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md) |

## Overview

A timed, click-by-click script for a **~5-minute live demo**. It drives the story and
the three "wow" moments defined in [demo_plan.md](demo_plan.md) — this doc is the
*operational* companion (what to click, the exact command, the one line to say, and the
fallback if a step misfires). It does not restate the narrative; read demo_plan first,
present from this.

**Timing:** core script ≈ **4:20**, target slot **5:00** (≈0:40 spoken buffer). The three
wow beats are marked **★**.

## Pre-flight (before the clock starts)

Do this off-stage; none of it is on the demo clock. Each item has a checkbox so nothing
is skipped under pressure.

1. **[ ] Deps installed, Slack extra included:** `uv sync --all-extras --extra slack`.
2. **[ ] Backend up (Terminal A):** `uv run uvicorn api.main:app --port 8010`
   — leave the **default (stub) AI** on; the flip is a wow moment, not the baseline.
3. **[ ] Frontend up (Terminal B):** `npm --prefix frontend run dev` — open the URL Vite
   prints (default `http://localhost:5173`; Vite proxies `/api` → `:8010`).
4. **[ ] `.env` filled (Terminal C, a spare shell at repo root):** `ANTHROPIC_API_KEY`
   for the AI flip; `PIPEGUARD_SLACK_BOT_TOKEN` + `PIPEGUARD_SLACK_CHANNEL` for the Slack
   beat (see [`.env.example`](../../.env.example)). Never read these on screen.
5. **[ ] Pre-type (don't run) the two "armed" commands** so a wow beat is one Enter, not
   live typing — see the pre-typed commands below.
6. **[ ] Delete any stale ledger:** `rm -f run.events.jsonl pg.sqlite` at repo root.
   The ledger is **append-only** — a leftover file makes Step 5 print doubled event
   counts.
7. **[ ] Sanity-check the pinned scenario** (proves the room is green before you talk):
   `uv run python -c "from pipeguard import run_gate_from_dir; _, c = run_gate_from_dir('data/mock_run_01'); print([(x.sample_id, x.verdict.value) for x in c])"`
   → expect `[('S4','escalate'), ('S5','hold'), ('S1','proceed'), ('S2','proceed'), ('S3','proceed')]`.
8. **[ ] Streamlit fallback armed** in a 4th terminal, ready to launch if React/API dies:
   `uv run streamlit run app/streamlit_app.py` (see Fallback ladder).

## The script

Times are **cumulative** (end-of-step mark on a 5:00 slot). "Presenter" is the single
driver. Each step's **Fallback** is the local recovery; the global ladder is below.

| # | End | Screen / action | Command or click | Say (one line) | Fallback |
|---|---|---|---|---|---|
| 1 | 0:20 | **Hook** — Run Overview (`/`) | Browser already on the run list; point at `mock_run_01`'s "needs attention" flag | "A run just finished. Someone has to decide, per sample, proceed / hold / rerun / escalate — today that's combing logs by hand." | If list empty → reload; if still empty → Streamlit fallback |
| 2 | 1:15 | **Decision card (the hero)** | Click `mock_run_01` → open **S4** | "S4 escalates: the demux i5 `AGGCGAAG` doesn't match the declared `GGCTCTGA` — an index swap — plus a missing `subject_id`. Every number links to a source file and a rule." Point at the **red-highlighted mismatched i5** and the `source_kind` chips. | If S4 card errors → open **S5** (borderline QC) and tell the same "cited evidence" story |
| 3 | 1:50 | **Ask the triage agent** | On S4, click **"Ask the triage agent"** | "An advisory agent suggests a likely cause and next action, with **corpus citations** — note the `ADVISORY · STUB` badge. It never sets the verdict." | If panel errors → say the note is advisory-only and move on; the verdict is untouched either way |
| 4 ★ | 2:40 | **★ Flip the AI on, live** | In **Terminal A**, `Ctrl-C`, then run the pre-typed armed command (below); wait for "Uvicorn running"; **refresh browser**, re-open S4, click triage again | "Same panel — now the prose is **Claude-written**, while the citations and the verdict stay deterministic. If the API errors or the safety classifier refuses, it silently degrades to the stub." | If live Claude is flaky/slow → **don't flip** (or re-launch backend with the stub); the stub is the default and identical in structure. The demo cannot break here. |
| 5 ★ | 3:30 | **★ Reproduce from the log** | In **Terminal C**, run the pre-typed one-liner (below) | "The database is disposable. This rebuilds the entire relational projection from the **authoritative event log** — same run, samples, findings, cards. `16 event(s) → 1 run, 5 decision cards`. The log is truth." | If the emit/rebuild errors → show the committed provenance screen instead (Step 7 target) and narrate the same "event log is authoritative" point |
| 6 ★ | 4:15 | **★ An escalation lands in Slack, live** | In **Terminal C**, run the pre-typed Slack command (below); cut to the Slack channel | "Same gate, wired to a real outbound port: the S4 escalation and S5 hold post to Slack as **cited cards** — one `notification.emitted` provenance event per send. Off by default; the live post is armed only by an explicit flag." | If Slack is down / not armed → run it **without** `PIPEGUARD_SLACK_LIVE`; it builds and records the payload with **$0, nothing sent**, and prints the actionable set. Same seam, no network. |
| 7 | 4:40 | **Close** — Provenance + guardrails | Click into S4's **Provenance** trail (`/runs/:runId/provenance`); glance the **Review queue** | "Every I/O is on an append-only trail. And the honest part: this is a **research/demo tool, not a clinical system** — rules decide, AI is advisory and off by default, thresholds are illustrative, confidence is a heuristic omitted until grounded." | Skip the click, deliver the guardrail line verbatim — it's the most important sentence in the demo |

Buffer to 5:00 for one judge question or a slow step.

### Pre-typed commands (for Pre-flight item 5)

**Step 4 — armed AI backend** (paste into Terminal A after `Ctrl-C`):

```bash
PIPEGUARD_TRIAGE_AGENT=claude PIPEGUARD_SYNTHESIZER=claude \
  uv run uvicorn api.main:app --port 8010
```

> The seam reads its env from the **running** process, so flipping = **restart the
> backend** with the prefix (an `export` in another shell won't reach the live server).
> `_evaluate` is cached per run, so a fresh process also re-narrates the cards.

**Step 5 — reproduce from the log** (one paste in Terminal C; `rm` guards the append-only
gotcha):

```bash
make emit-ledger && make rebuild-db
```

(`emit-ledger` deletes any stale `run.events.jsonl` and writes a fresh 16-event ledger from
`mock_run_01`; `rebuild-db` replays it into `pipeguard.sqlite`. Both artifacts are gitignored.)

Expected tail: `... 16 event(s) -> 1 run(s), 5 decision card(s).`

**Step 6 — live Slack escalation** (paste in Terminal C):

```bash
PIPEGUARD_NOTIFIER=slack PIPEGUARD_SLACK_LIVE=1 \
  uv run python -m pipeguard.notify data/mock_run_01
```

Safe variant if Slack is unavailable (builds + records, **sends nothing, $0**):

```bash
uv run python -m pipeguard.notify data/mock_run_01
```

## Fallback ladder (global)

Layered so the presenter can always keep going — matches [demo_plan.md](demo_plan.md)
§Fallbacks:

1. **A single step misfires** → use that step's row-level Fallback above; keep the story
   moving, don't debug on stage.
2. **Live Claude flaky / rate-limited** → stay on the **stub** (the default, $0) — same
   structure, templated prose. Skip the flip or relaunch the backend without the claude env.
3. **React / API broken** → launch the **Streamlit** app
   (`uv run streamlit run app/streamlit_app.py`) — the same core, one offline process,
   always green. Re-tell Steps 1–3 there.
4. **Everything is uncooperative** → the recorded walkthrough / screenshots.

## Presenter notes

1. **Lead with the invariant, not the UI:** "rules decide; AI narrates and advises" is
   the load-bearing point for a clinical-adjacent tool — say it early and again at close.
2. **Don't read secrets on screen.** All keys/tokens live in `.env`; never `cat` it.
3. **The safe default is the strong default.** Every AI/notify beat degrades to a $0
   offline path — that resilience *is* part of the pitch, not an apology.
4. If time is short, the three **★** beats plus the guardrail close are the irreducible
   demo; Steps 3 and 7's provenance click are the first to cut.

---

*Marker legend — distinguish claim types where confusion is likely:*
**Fact** · **Assumption** · **Decision** · **TODO**.
