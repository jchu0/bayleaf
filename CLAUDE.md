# CLAUDE.md — PipeGuard

AI-assisted provenance & QC decision gate for genomics runs (Built with Claude:
Life Sciences hackathon). See [README.md](README.md) for the full overview.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the dashboard (offline; no API key needed)
streamlit run app/streamlit_app.py        # http://localhost:8501

# Tests (offline — pins the demo scenario)
pytest                                     # pythonpath=src is set in pyproject.toml
pytest tests/test_gate.py -q

# Ad-hoc run of the core (no UI)
PYTHONPATH=src python -c "from pipeguard import run_gate_from_dir; \
  _, cards = run_gate_from_dir('data/mock_run_01'); \
  print([(c.sample_id, c.verdict.value) for c in cards])"
```

There is no build step (pure Python) and no linter configured yet.

## Architecture (what to know before editing)

- **`src/pipeguard/` is framework-agnostic.** It must not import Streamlit/FastAPI.
  The UI is a thin view; all logic lives in the package so the Streamlit MVP can be
  swapped for FastAPI + React by reusing `pipeguard` unchanged.
- **Rules decide; the synthesizer narrates.** `pipeguard.rules` produces deterministic,
  cited `Finding`s. Verdict and confidence are computed in `synthesis/base.py`
  (`aggregate_verdict`, `derive_confidence`) from those findings — **never** by the LLM.
  When adding a check, add a rule that emits a `Finding` with `suggested_verdict`;
  don't push judgment into the synthesizer.
- **The synthesizer is swappable via env.** `PIPEGUARD_SYNTHESIZER=stub|claude`
  (default `stub`, offline, $0). `synthesis/claude.py` is the live integration point:
  `anthropic` is imported lazily and any error falls back to the stub, so the package
  runs and tests pass without `anthropic` installed or any API key.
- **Data contract** flows through `pipeguard.models` (pydantic):
  `RunArtifacts → Finding[] → DecisionCard`. Change models there, not per-layer.
- **Runbook** (`runbook.py`) holds QC thresholds and gate policy — the operator-owned
  config. Borderline band vs. hard-fail floor is what separates a HOLD from a RERUN.

## Claude integration specifics

- Uses structured outputs: `client.messages.create(..., output_config={"format":
  {"type": "json_schema", "schema": ...}})`, constraining only the narration fields.
- Model via `PIPEGUARD_CLAUDE_MODEL` (default `claude-opus-4-8`). No `thinking` param
  is passed, which is safe across opus-4-8 / sonnet-5 / fable-5.
- The `refusal` stop reason is handled (falls back to stub) — relevant because Fable 5
  safety classifiers can false-positive on life-sciences work.

## Git conventions

Incremental, self-contained commits; short title + descriptive body. No AI attribution
lines in commit messages.
