# PipeGuard 🧬

**An AI-assisted provenance & QC decision gate for genomics runs.**

Built with Claude · Life Sciences hackathon.

Bioinformatics pipelines are good at *executing* workflow steps, but *operating* them
is still manual: intake, provenance review, QC interpretation, and failure triage
happen across scattered tools, dashboards, logs, and human memory. When something
looks off, teams reconstruct by hand what happened, why it matters, and what to do next.

PipeGuard is a vertical slice of that operations layer: **the decision gate for a
sequencing run.** It ingests the run's artifacts, checks them for provenance risks,
missing metadata, and borderline QC, and produces a **decision card per sample**
answering the only question the operator cares about:

> Should this sample **proceed**, **hold**, **rerun**, or **escalate** — and what's the evidence?

The human still makes the call. They just no longer reconstruct the context by hand.

> **Not a clinical decision system.** PipeGuard is a research/demo tool with production
> intent. It makes **no diagnostic, therapeutic, or pathogenicity claims**. Runbook
> thresholds are illustrative and configurable, not clinical thresholds; any confidence
> value is a heuristic, not a calibrated probability, and is omitted until grounded. See
> [Guardrails & disclaimer](#guardrails--disclaimer).

---

## The core idea: rules decide, AI narrates & advises

The credibility of a decision gate depends on its recommendations being **grounded**, so
PipeGuard splits the work along one load-bearing invariant — **rules decide; AI narrates
and advises, and never sets or overrides a verdict** ([ADR-0001](docs/adr/ADR-0001-deterministic-gate-advisory-ai.md)):

1. **Rule engine** (`pipeguard.rules`) owns the *facts*: barcode/index-swap and
   sample-identity checks, missing metadata, QC vs. runbook thresholds, pipeline
   failures. Each is emitted as a cited, immutable, content-hashed `Finding` that traces
   to a source file and a rule. The **verdict is computed from the findings.**
2. **Synthesizer** (`pipeguard.synthesis`) owns the *narration*: the verdict's headline,
   rationale, and next steps in operator language. The model phrases the card; it does
   not decide it.
3. **Triage agent** (`pipeguard.triage`) is *advisory*: on a flagged card it suggests a
   likely cause and next action, grounded in a curated knowledge corpus with citations —
   **off the deterministic critical path**, and it never touches the verdict
   ([ADR-0009](docs/adr/ADR-0009-corpora-retrieval-upskilling.md)).

An LLM eyeballing whether `Q30 = 84.1%` clears an 85% gate is unreliable and
unconvincing to a bioinformatician. A rule computing it, with Claude explaining the
*consequence*, is both correct and readable.

### The three-gate model

Every finding and verdict is labelled with the gate it came from
([ADR-0013](docs/adr/ADR-0013-gate-architecture-verdict-policy.md)):

1. **preflight** — intake: barcode/index integrity, sample identity, required metadata,
   pipeline/operational failures ("did we produce usable data at all?").
2. **qc** — per-sample QC: yield/Q30, coverage depth and breadth, duplication,
   contamination, sample-swap signals.
3. **variant** — variant-level checks (DP/GQ/allele balance, gnomAD/ClinVar) — **Phase 2,
   not yet built.**

`RERUN` is reserved for operational/file-system failures; a data-quality problem is a
`HOLD` (surface-and-decide, not prescribe).

---

## Architecture at a glance

Full detail in [docs/design/architecture.md](docs/design/architecture.md); the *why*
lives in the [ADRs](docs/adr/).

```
 run dir ─▶ parsers ─▶ RunArtifacts ─▶ rules ─▶ Finding[] ─▶ synthesis ─▶ DecisionCard[]
                                          │                                   │
                                          ├────────▶ provenance: EventLedger ◀┘  (append-only,
                                          │            (analysis_run/finding/       ADR-0002)
                                          │             verdict events)
                            triage agent ─┘  (advisory, off the critical path, ADR-0009)
                                                          │
      ┌───────────────────────────────────────────────────┤
      ▼                          ▼                         ▼
 app/ Streamlit           api/ FastAPI  ───────────▶  frontend/ React
 (offline fallback)       (read-API seam)             (Vite + Tailwind)
```

1. **Core (`src/pipeguard/`), framework-agnostic** — no UI framework imports. `parsers`
   build a tolerant, typed `RunArtifacts` bundle (a missing field is a *signal*, not a
   crash); `rules` is the trust anchor (cited, immutable `Finding`s); `models` is the
   pydantic data contract; `runbook` holds operator-configurable QC policy; `metrics/`
   is a versioned, canonical metric vocabulary over MultiQC-style keys.
2. **Provenance seam (`provenance.py`, [ADR-0002](docs/adr/ADR-0002-event-driven-core-provenance-ledger.md))** —
   `run_gate` emits an append-only event trail (analysis_run.started → per-sample
   findings/verdict → completed) into an `EventLedger` (in-memory + JSONL). The **event
   log is authoritative**; the relational DB is a rebuildable projection via a
   `Repository` port (`persistence/`: `SqliteRepository` + `rebuild-db`).
3. **Swappable AI, OFF by default** ([ADR-0006](docs/adr/ADR-0006-ai-off-by-default-fallback.md)) —
   the synthesizer and the triage agent each flip via one env var, are stub-first ($0),
   import `anthropic` lazily, and **fall back to the stub on any error** (including a
   safety refusal).
4. **Delivery layers (thin, over the core)** — `app/` Streamlit (the guaranteed-working
   offline demo/fallback), `api/` FastAPI read-API (the production seam,
   [ADR-0010](docs/adr/ADR-0010-ticketing-notify-read-api.md)), `frontend/` React
   consuming the API ([ADR-0014](docs/adr/ADR-0014-productionization-fastapi-react.md)).
   An outbound `notify/` port turns each *actionable* card into a per-verdict, evidence-cited
   notification — stub-first ($0); the Slack adapter's live post is opt-in via
   `PIPEGUARD_SLACK_LIVE` and every send is recorded as a `notification.emitted` ledger event
   (`python -m pipeguard.notify <run_dir>`).

### Swappable seams (the flex points)

| Seam | Switch | Default |
|---|---|---|
| Synthesizer (narration) | `PIPEGUARD_SYNTHESIZER=stub\|claude` | `stub` ($0) |
| Triage agent (advice) | `PIPEGUARD_TRIAGE_AGENT=stub\|claude` | `stub` ($0) |
| Notify (outbound) | `PIPEGUARD_NOTIFIER=stub\|slack`; `PIPEGUARD_SLACK_LIVE=1` to arm live send | `stub` (no network) |
| Repository (persistence) | `Repository` port; SqliteRepository → Postgres later | SQLite + JSONL |

---

## Quickstart

```bash
uv sync --all-extras     # creates .venv, installs deps + dev tools (editable)

# Run the dashboard offline — no API key, no cost (http://localhost:8501)
uv run streamlit run app/streamlit_app.py
```

The dashboard opens on the bundled mock run (`data/mock_run_01`), a small contrived
NovaSeq run where **S1–S3 proceed, S4 escalates (barcode/index swap + missing metadata),
and S5 holds (borderline QC)** — see [the pinned scenario](#the-pinned-scenario).

### Full stack (FastAPI + React)

Matches [docs/demo/demo_plan.md](docs/demo/demo_plan.md):

```bash
uv run uvicorn api.main:app --port 8010     # read-API backend
npm --prefix frontend run dev               # React UI (Vite proxies /api → :8010)
```

### Developer commands

```bash
uv run pytest                # offline tests — pins the demo scenario
make check                   # lint + strict type-check + tests (ruff + mypy + pytest)
uv run pre-commit install --install-hooks   # ruff/mypy/secret-scan (commit) + pytest (push)

# Ad-hoc run of the core, no UI:
uv run python -c "from pipeguard import run_gate_from_dir; \
  _, cards = run_gate_from_dir('data/mock_run_01'); \
  print([(c.sample_id, c.verdict.value) for c in cards])"
# -> [('S4', 'escalate'), ('S5', 'hold'), ('S1', 'proceed'), ('S2', 'proceed'), ('S3', 'proceed')]
```

### Enabling live Claude (optional)

Both AI seams are offline by default (the `stub` — rule-derived narration/advice, **$0**).
The live path is fully written but selected only via an environment flag, so it costs
nothing until you turn it on and **degrades back to the stub on any API error or safety
refusal** — a flaky conference network can't break the demo:

```bash
cp .env.example .env                 # then fill in ANTHROPIC_API_KEY
export PIPEGUARD_SYNTHESIZER=claude  # and/or PIPEGUARD_TRIAGE_AGENT=claude
```

Model selection (and a cheaper tier to conserve credits) is env-configurable via
`PIPEGUARD_CLAUDE_MODEL` / `PIPEGUARD_TRIAGE_MODEL`; each card is a small structured
output, so cost per run is minimal. See [`.env.example`](.env.example) for every knob.

---

## Demo highlights

The two "wow" moments (full script in [docs/demo/demo_plan.md](docs/demo/demo_plan.md)):

1. **Flip the AI on, live.** Set `PIPEGUARD_TRIAGE_AGENT=claude` (and/or the synthesizer)
   and the same triage panel now shows Claude-written prose — while the **citations and
   the verdict stay deterministic.** If the API errors or the safety classifier refuses,
   it silently degrades to the stub.
2. **Reproduce from the log.** `make rebuild-db LEDGER=run.events.jsonl DB=pg.sqlite`
   rebuilds the entire relational projection from the authoritative event ledger — same
   run, samples, findings, cards, and events. The DB is disposable; the log is truth
   ([ADR-0002](docs/adr/ADR-0002-event-driven-core-provenance-ledger.md)).

### The pinned scenario

`data/mock_run_01` is test-pinned so the demo is deterministic:

| Sample | Verdict | Gate | Why |
|---|---|---|---|
| S1, S2, S3 | **Proceed** | — | Clean across all artifacts |
| S4 | **Escalate** | preflight | Demux index2 `AGGCGAAG` ≠ declared `GGCTCTGA` (an index swap), plus missing `subject_id` |
| S5 | **Hold** | qc | Q30 84.1% (gate 85%) and coverage 29.2× (gate 30×) — both borderline, a judgment call |

---

## Project layout

```
src/pipeguard/            # framework-agnostic core (no UI dependency)
  models.py               # Verdict / Finding / DecisionCard / RunArtifacts (pydantic)
  parsers.py              # tolerant Illumina-style artifact parsers -> RunArtifacts
  rules.py                # deterministic rule engine -> cited Findings
  runbook.py              # operator-configurable QC thresholds & gate policy
  identifiers.py          # UUIDv7 ids, content hashing, UTC time
  engine.py               # orchestration: load -> evaluate -> synthesize -> cards
  synthesis/              # verdict aggregation (deterministic) + narration (stub | claude)
  triage/                 # advisory QC-triage agent + knowledge corpus + retrieval
  provenance.py           # append-only EventLedger (in-memory + JSONL)
  persistence/            # Repository port + event→row projector + SqliteRepository + rebuild-db
  metrics/                # versioned canonical metric vocabulary (registry.yaml + loader)
  notify/                 # outbound notify port (stub | Slack; per-verdict, evidence-cited; opt-in live send)
  synthetic/              # synthetic failure-mode run generator (mock_run_02/03)
app/streamlit_app.py      # thin offline dashboard over the core (the fallback demo)
api/main.py               # FastAPI read-API (health, runs, cards, triage, config)
frontend/                 # React + Vite + Tailwind UI consuming the API
scripts/fetch_giab_hg002.py   # idempotent, checksum-verifying GIAB HG002 fetcher (accessions only)
data/mock_run_0{1,2,3}/   # contrived demo runs (01 hand-authored & pinned; 02/03 generated)
tests/                    # offline tests pinning the demo scenario
```

**Data posture** — `mock_run_01` is hand-authored and pinned; `mock_run_02/03` are
reproducible from the synthetic generator (`uv run python -m pipeguard.synthetic`). Real
GIAB HG002 truth data is **fetched, never committed** — the repo carries the accession
manifest + fetch script, and the bytes land in a git-ignored `data/real-giab/`. See
[data/README.md](data/README.md) and [scripts/README.md](scripts/README.md).

---

## Where to read next

1. [docs/TABLE_OF_CONTENTS.md](docs/TABLE_OF_CONTENTS.md) — the map of every doc.
2. [docs/design/architecture.md](docs/design/architecture.md) — system shape, invariants, deployment.
3. [docs/adr/](docs/adr/) — one decision per file; the *why* behind the architecture.
4. [docs/demo/demo_plan.md](docs/demo/demo_plan.md) — the walkthrough and fallbacks.
5. [docs/requirements/scope-and-wishlist.md](docs/requirements/scope-and-wishlist.md) — in-scope, deferred, and out-of-scope.
6. [docs/data/qc_metrics.md](docs/data/qc_metrics.md) · [docs/data/provenance.md](docs/data/provenance.md) — the QC runbook and the event seam.
7. [docs/reference/domain-primer.md](docs/reference/domain-primer.md) · [docs/reference/glossary.md](docs/reference/glossary.md) — the domain, for non-specialists.
8. [docs/quality/evaluation.md](docs/quality/evaluation.md) · [docs/quality/risks.md](docs/quality/risks.md) — what "good" means and what could go wrong.

---

## Status

MVP-first with production-ready seams. The core gate, provenance ledger + SQLite
projection, advisory triage agent, and all three delivery layers (Streamlit / FastAPI /
React) run today; the **variant gate**, richer real-data evaluation, and cloud/IaC are
Phase-2+. Track progress in `docs/planning/tasks.md`.

## Guardrails & disclaimer

Per the [operating contract](CLAUDE.md) and
[docs/requirements/scope-and-wishlist.md](docs/requirements/scope-and-wishlist.md):

1. **Not a clinical decision system.** A research/demo tool with production intent —
   **no diagnostic, therapeutic, or safety claims.** It sits *on top of* a pipeline; it
   does not build or modify the clinical pipeline.
2. **Rules decide; AI is advisory** and off the deterministic critical path. The AI is
   **off by default** with a deterministic fallback.
3. **Thresholds are illustrative and configurable**, not clinical thresholds. Any
   confidence value is a heuristic, not a calibrated probability, and is omitted until
   grounded.
4. **Conservative by construction** — evidence, assumptions, and generated suggestions
   are kept separate; citations, provenance, and uncertainty are preserved. Clinical
   variant claims stay grounded in ClinVar/GIAB truth; the tool never invents pathogenicity.
5. **No real patient data (PHI)** during the hackathon — public/synthetic only.
