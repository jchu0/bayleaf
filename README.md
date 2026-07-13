# bayleaf 🌿

**An AI-assisted provenance & QC decision gate for genomics sequencing runs.**

Built with Claude · Life Sciences hackathon.

Bioinformatics pipelines are good at *executing* workflow steps, but *operating* them — intake,
provenance review, QC interpretation, failure triage — is still manual, spread across scattered
tools, logs, and human memory. bayleaf is the **decision gate** for a sequencing run: it ingests
the run's artifacts, checks them, and produces a **decision card per sample** answering the one
question the operator cares about:

> Should this sample **proceed**, **hold**, **rerun**, or **escalate** — and what's the evidence?

The human still makes the call; they just no longer reconstruct the context by hand.

> ⚠️ **Not a clinical decision system.** A research/demo tool with production intent. It makes **no
> diagnostic, therapeutic, or pathogenicity claims**; thresholds are illustrative and configurable,
> not clinical; confidence values are heuristics, not calibrated probabilities. See
> [Guardrails](#guardrails).

---

## Features

- **Deterministic decision gate** — a rule engine emits cited, immutable, content-hashed findings
  (barcode/index swaps, sample identity, missing metadata, QC-vs-runbook thresholds, pipeline
  failures) and computes a per-sample verdict across three gates (preflight · qc · variant).
- **Rules decide; AI narrates & advises** — the LLM writes the card's prose and answers questions,
  but never sets or overrides a verdict. AI is **off by default** ($0, stub-first) and flips on per
  env var, degrading back to a deterministic stub on any API error or refusal.
- **Advisory agents** — QC-triage (per-card cause + next action), a System-agents **chat** over the
  org-wide agents (pipeline-repair, archivist), and a Builder **node-authoring** assistant — all
  cited, all off the deterministic path.
- **Append-only provenance** — every I/O is recorded in an event ledger; the SQL projection is a
  rebuildable view of it (the log is truth).
- **Pipeline Builder** — compose a card graph and compile it to runnable Nextflow (DSL2); bayleaf
  *composes*, it never executes a tool itself.
- **Deployment-agnostic seams** — swappable synthesizer/agents (stub | Claude), persistence
  (SQLite | Postgres), and notify (stub | Slack), all off by default.

---

## Quickstart

**Prerequisites:** [`uv`](https://docs.astral.sh/uv/) (Python) and Node 20+ (frontend). No API key
needed — the app runs fully offline with stub agents by default.

```bash
uv sync --all-extras                          # .venv + deps + dev tools (editable install)

# Run the full stack (two terminals):
uv run uvicorn api.main:app --port 8010        # backend  (FastAPI read-API)
npm --prefix frontend install                  # first run only
npm --prefix frontend run dev                  # frontend (Vite; proxies /api → :8010)
```

Open **http://localhost:5173** and sign in with the demo login — any of the seeded accounts with
password `bayleaf` (use `admin@lab.org` to see every screen). It opens on the pinned mock run
(`data/mock_run_01`).

Prefer no UI? Drive the core headless:

```bash
uv run python -c "from bayleaf import run_gate_from_dir; \
  _, cards = run_gate_from_dir('data/mock_run_01'); \
  print([(c.sample_id, c.verdict.value) for c in cards])"
# -> [('S4','escalate'), ('S5','hold'), ('S1','proceed'), ('S2','proceed'), ('S3','proceed')]
```

### The pinned demo scenario

`data/mock_run_01` is test-pinned so the demo is deterministic:

| Sample | Verdict | Gate | Why |
|---|---|---|---|
| S1, S2, S3 | **Proceed** | — | Clean across all artifacts |
| S4 | **Escalate** | preflight | Demux index2 `AGGCGAAG` ≠ declared `GGCTCTGA` (index swap) + missing `subject_id` |
| S5 | **Hold** | qc | Q30 84.1% (gate 85%) and coverage 29.2× (gate 30×) — both borderline |

### Enabling live Claude (optional)

Both AI seams are stub-first ($0). The live path is fully written but flips on only via an env var
and **degrades back to the stub on any API error or safety refusal**:

```bash
cp .env.example .env                           # add ANTHROPIC_API_KEY
export BAYLEAF_SYNTHESIZER=claude              # and/or BAYLEAF_TRIAGE_AGENT / _PIPELINE_REPAIR_AGENT / …
```

See [`.env.example`](.env.example) for every knob (model tiers, stores, notify).

---

## Development

```bash
make check                    # ruff + mypy (strict) + pytest — the one-shot gate
uv run pytest                 # offline test suite (pins the demo scenario)
npm --prefix frontend run build   # tsc -b + vite build (the frontend type-check gate)
uv run pre-commit install --install-hooks   # ruff/mypy/secret-scan (commit) + pytest/tsc (push)
```

Two toolchains are kept separate: **`uv`** for the app, and **bioconda/Nextflow** for the optional
genomics-tool execution (only needed to run a real pipeline, not for the demo).

---

## Project layout

```
src/bayleaf/     framework-agnostic core: parsers · rules · models · runbook · engine ·
                 synthesis · triage · provenance · persistence · metrics · notify · nextflow
api/             FastAPI read-API + off-gate writes (agents, chat, pipeline builder/run)
frontend/        React + Vite + Tailwind operator UI (consumes the API)
data/            pinned + generated demo runs (real GIAB data is fetched, never committed)
docs/            architecture, ADRs, design, requirements, demo scripts
tests/           offline test suite
```

---

## Architecture & docs

The core invariant — **rules decide; AI narrates and advises, never sets a verdict**
([ADR-0001](docs/adr/ADR-0001-deterministic-gate-advisory-ai.md)) — plus an event-driven provenance
core (ADR-0002), AI off by default (ADR-0006), and Nextflow for compute portability (ADR-0003).

- [docs/TABLE_OF_CONTENTS.md](docs/TABLE_OF_CONTENTS.md) — the map of every doc
- [docs/design/architecture.md](docs/design/architecture.md) — system shape & invariants
- [docs/adr/](docs/adr/) — one architectural decision per file (the *why*)
- [docs/demo/demo_plan.md](docs/demo/demo_plan.md) — the walkthrough

---

## Guardrails

1. **Not a clinical decision system** — no diagnostic, therapeutic, or safety claims. It sits *on
   top of* a pipeline; it does not build or modify a clinical pipeline.
2. **Rules decide; AI is advisory** and off the deterministic critical path, off by default.
3. **Thresholds are illustrative and configurable**, not clinical; confidence is a heuristic, not a
   calibrated probability, and is omitted until grounded.
4. **Conservative by construction** — evidence, assumptions, and generated suggestions stay
   separate; citations, provenance, and uncertainty are preserved. Variant claims stay grounded in
   ClinVar/GIAB truth; the tool never invents pathogenicity.
5. **No PHI** — public/synthetic data only.
