# PipeGuard 🧬

**An AI-assisted provenance & QC decision gate for genomics runs.**

Built with Claude · Life Sciences hackathon.

Most bioinformatics pipelines are good at *executing* predefined workflow steps, but
*operating* those pipelines is still manual: intake, provenance review, QC
interpretation, failure triage, and run monitoring happen across scattered tools,
dashboards, logs, spreadsheets, and human memory. When something looks off, teams
have to manually reconstruct what happened, why it matters, and what to do next.

PipeGuard is a vertical slice of that operations layer: **the decision gate for a
sequencing run.** It ingests the run's artifacts, checks them for provenance risks,
missing metadata, and borderline QC, and produces a **decision card per sample**
answering the only question the operator cares about:

> Should this sample **proceed**, **hold**, **rerun**, or **escalate** — and what's the evidence?

The human still makes the call. They just no longer reconstruct the context by hand.

---

## The core idea: deterministic rules, AI narration

The credibility of a decision gate depends on its recommendations being **grounded**.
So PipeGuard splits the work:

| Layer | Owns | Guarantees |
|---|---|---|
| **Rule engine** (`pipeguard.rules`) | The facts: barcode/ID mismatches, missing fields, QC vs. runbook thresholds, log failures — each a cited `Finding`. | Deterministic. Every number traces to a rule and a source file. |
| **Synthesizer** (`pipeguard.synthesis`) | The narration: the verdict's headline, rationale, and next steps in operator language. | The verdict is computed from the findings — the model phrases, it does not decide. |

An LLM eyeballing whether `Q30 = 84.1%` clears an 85% gate is unreliable and
unconvincing to a bioinformatician. A rule computing it, with Claude explaining the
*consequence*, is both correct and readable.

```
 run artifacts ─▶ parsers ─▶ rule engine ─▶ findings ─▶ synthesizer ─▶ decision cards ─▶ dashboard
 (sample sheet,              (deterministic,           (stub today,
  QC, demux, logs)            cited findings)           Claude when enabled)
```

---

## Quick start

```bash
uv sync --all-extras     # creates .venv, installs deps + dev tools (editable)

# Run the dashboard (offline — no API key, no cost)
uv run streamlit run app/streamlit_app.py

# Run the tests
uv run pytest
```

The dashboard opens on the bundled mock run (`data/mock_run_01`), a small NovaSeq run
where **3 samples pass, 1 has a barcode/sample-ID mismatch (escalate), and 1 has
borderline QC (hold).**

---

## Enabling live Claude synthesis

Synthesis is offline by default (the `stub` — rule-derived narration, **$0**). The
live path is fully written but selected only via an environment flag, so it costs
nothing until you turn it on:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export PIPEGUARD_SYNTHESIZER=claude          # flip the switch
export PIPEGUARD_CLAUDE_MODEL=claude-sonnet-5 # optional; see cost note below
streamlit run app/streamlit_app.py
```

When live, Claude receives the rule engine's findings plus a compact artifact context
and writes the operator-facing card. The verdict is still the rules' verdict; any API
error (or a safety refusal) transparently falls back to the stub, so a flaky
conference network can't break a demo.

**Model / cost knob** — `PIPEGUARD_CLAUDE_MODEL` (default `claude-opus-4-8`):

| Model | Input / Output per 1M tok | Use for |
|---|---|---|
| `claude-opus-4-8` | $5 / $25 | Highest-quality narration |
| `claude-sonnet-5` | $3 / $15 | Recommended balance for the demo |
| `claude-haiku-4-5` | $1 / $5 | Cheapest; fine for short cards |

Each card is a small structured output (a few hundred tokens), so even Opus is cents
per run — but the knob is there to conserve credits.

---

## Project layout

```
src/pipeguard/            # framework-agnostic core (no UI dependency)
  models.py               # Verdict / Finding / DecisionCard / RunArtifacts (pydantic)
  runbook.py              # operator-configurable QC thresholds & gate policy
  parsers.py              # Illumina-style artifact parsers (sample sheet, demux, QC, log)
  rules.py                # deterministic rule engine -> cited Findings
  synthesis/
    base.py               # Synthesizer protocol + grounding helpers (verdict aggregation)
    stub.py               # zero-cost deterministic narration (default)
    claude.py             # live Claude integration point (off by default)
  engine.py               # orchestration: load -> evaluate -> synthesize -> cards
app/streamlit_app.py      # thin dashboard view over the core
data/mock_run_01/         # realistic mock NovaSeq run for the demo
tests/test_gate.py        # offline tests pinning the demo scenario
```

The Streamlit app is intentionally a thin rendering layer. Porting to a FastAPI +
React frontend later means importing `pipeguard` unchanged and rewriting only the view.

---

## The mock run (`data/mock_run_01`)

| Sample | Verdict | Why |
|---|---|---|
| S1, S2, S3 | ✅ Proceed | Clean across all artifacts |
| **S4** | 🚨 Escalate | Demux index2 `AGGCGAAG` ≠ declared `GGCTCTGA` (it's S5's i5 — an index swap), plus missing `subject_id` |
| **S5** | 🟡 Hold | Q30 84.1% (gate 85%) and coverage 29.2× (gate 30×) — both borderline, a judgment call |

---

## Roadmap (beyond the MVP slice)

PipeGuard is one component of a larger vision — an AI-governed pipeline operations
layer. Natural next slices: run monitoring, failure triage, sample status tracking
across runs, and a final-report generator — each with the same rules-ground-the-AI
architecture.
