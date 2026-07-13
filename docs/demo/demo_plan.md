# Demo Plan

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-11 (MST) |
| **Audience** | presenter / judges |
| **Related** | [run-of-show.md](run-of-show.md) (timed live script), [one-pager.md](one-pager.md) (judge summary), [architecture.md](../design/architecture.md), [provenance.md](../data/provenance.md), [qc_metrics.md](../data/qc_metrics.md), [quality/evaluation.md](../quality/evaluation.md), [quality/risks.md](../quality/risks.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md) |

## The narrative (60 seconds)

A sequencing run finishes; an operator must decide, per sample, **proceed / hold /
rerun / escalate** — today that means combing logs and QC reports by hand. bayleaf is
the **operations layer**: deterministic rules make the call with **cited evidence**, an
advisory **Claude agent** accelerates triage, and every decision is recorded in an
**append-only provenance ledger** the database is a rebuildable projection of. **Rules
decide; AI advises** — the load-bearing safety property for a clinical-adjacent tool.

## Setup

```bash
uv sync --all-extras
uv run uvicorn api.main:app --port 8010        # backend
npm --prefix frontend run dev                  # React UI (proxies /api -> :8010)
# Offline + stub-first by default (no API key needed) — this full stack IS the demo.
```

## Walkthrough (the happy path)

1. **Run overview** — runs with per-verdict counts and an "N need attention" flag.
   Click `mock_run_01`.
2. **Decision cards (the hero)** — for the escalated sample **S4**: the verdict badge,
   the **per-gate result strip** (preflight → escalate), and the **cited evidence table**
   — barcode `SampleSheet.csv` vs `demux_stats.csv` with the **mismatched i5 highlighted
   in red** (`AGGCGAAG` ≠ declared `GGCTCTGA`), `source_kind` chips, observed vs expected.
   Point out: every number traces to a source file + a rule.
3. **Ask the triage agent** — click **"Ask the triage agent"** on S4. The advisory
   `TriageNote` appears (likely cause, suggested action, **corpus citations**). Note the
   **Advisory** badge and the **Rule-derived triage (offline)** source label — it never
   sets the verdict.
4. **Provenance** — the append-only event trail (analysis_run.started → per-sample
   findings/verdict → completed) with content-hashed card refs. "The event log is
   authoritative."
5. **Review queue** — the cross-run "needs attention" worklist, most-urgent first.
6. **Monitoring** — verdict distribution + per-gate flag rate. **Settings** — the runbook
   thresholds (labelled illustrative, not clinical).

> **The walkthrough above is a curated 6-beat happy path, not the full app.** The shipped UI
> is **13 operator screens across three nav groups + an approver-only Admin group + a demo
> Login** (16 routes total), all behind `/login`:
> - **Operate** — Inbox (`/inbox`), Review queue (`/queue`), Sample accessioning
>   (`/accession`), Submit samplesheet (`/submit`), Intake gate (`/runs/:id/intake`),
>   Decision cards (`/runs/:id`), Runs (`/`).
> - **Analyze** — Provenance (`/runs/:id/provenance`), Agent triage (`/runs/:id/agent`),
>   Monitoring (`/monitoring`), System agents (`/system-agents`).
> - **Configure** — Pipeline builder (`/builder`), Settings (`/settings`).
> - **Admin** (`/admin`, off the deterministic gate — governance/audit only) and **Login**
>   (`/login`, a demo auth screen; production auth seams are labelled not-implemented).
>
> The demo drives the hero path (Runs → Decision cards → triage → Provenance, glancing the
> Review queue); the remaining screens are available if a judge explores or asks.

## The "wow" moments

1. **Flip the AI on, live.** `BAYLEAF_TRIAGE_AGENT=claude` (and/or
   `BAYLEAF_SYNTHESIZER=claude`) → the same triage panel now shows Claude-written prose,
   with citations + addressed findings still **deterministic**. If the API errors or the
   safety classifier refuses, it **degrades to the stub** — the demo cannot break.
2. **Reproducibility from the log.** `make emit-ledger && make rebuild-db` writes a fresh
   16-event ledger from the demo run, then rebuilds the entire relational projection from that
   authoritative log — `16 event(s) → 1 run, 5 decision cards`, byte-stable. The DB is
   disposable; the log is truth.
3. **An escalation lands in Slack, live.**
   `BAYLEAF_NOTIFIER=slack BAYLEAF_SLACK_LIVE=1 uv run python -m bayleaf.notify data/mock_run_01`
   → the gate runs and the S4 escalation (+ S5 hold) post to a real Slack channel as cited
   cards. Off by default (stub, $0); the live post is armed **only** by the explicit
   `BAYLEAF_SLACK_LIVE` flag (needs `uv sync --extra slack` + a bot token/channel in `.env`),
   and any Slack error degrades to the stub. Shows the ops-integration seam (ADR-0010) as a
   real, controlled side effect — verified end-to-end against a live workspace.

## Expected I/O (the pinned scenario)

`mock_run_01`: **S1–S3 proceed** (clean), **S4 escalate** (barcode/index swap — declared i5
`GGCTCTGA` vs observed `AGGCGAAG` — plus missing `subject_id`, both at the preflight gate),
**S5 hold** (borderline Q30 84.1% and coverage 29.2×). **16 provenance events** on the default
(no-notifier) run; wiring the notify port for wow-moment 3 adds **two** `notification.emitted`
events — one per actionable card (S4, S5). These are test-pinned, so the demo is deterministic.

## Fallbacks (in order)

1. Live Claude flaky/rate-limited → keep the **stub** (default, $0) — identical structure,
   templated prose.
2. React/API issue → drive the **deterministic core headless** (`uv run python -c "from bayleaf
   import run_gate_from_dir; ..."`) — same verdicts, no UI, always green.
3. Everything else → the recorded walkthrough / screenshots.

## Talking points if asked

- **Safety:** advisory AI, off the critical path, off by default; confidence omitted until
  grounded; conservative language; no diagnostic/pathogenicity claims.
- **Rigor:** immutable content-hashed findings, three-gate model, per-assay configurable
  runbook, event-sourced provenance.
- **Production intent:** framework-agnostic core; FastAPI seam; SQLite→Postgres via a
  repository port; Nextflow for compute portability.
- **Pipeline authoring + approval gate:** the Builder composes a typed-port DAG → **draft →
  submit → approve** (ADR-0017); `POST /api/pipelines/run` executes only the approver-blessed
  baseline (an unapproved draft is a 409, a posted graph is refused). `scripts/seed_approved_germline.py`
  seeds an approved `germline-panel` for the optional Builder Run beat; see the run-of-show.
