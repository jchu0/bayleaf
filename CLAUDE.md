# CLAUDE.md — PipeGuard

AI-assisted provenance & QC decision gate for genomics runs (Built with Claude:
Life Sciences hackathon). This file is the self-contained operating contract for
this repo — do not assume any global rules apply here.

## Start here (every session)

- Read [docs/TABLE_OF_CONTENTS.md](docs/TABLE_OF_CONTENTS.md) first to see what
  exists, then load **only** the files relevant to the task. Do not bulk-load the
  repo into context.
- Follow [docs/DOCUMENTATION_HABITS.md](docs/DOCUMENTATION_HABITS.md) for anything
  documentation-related.
- The `why` behind the architecture lives in [docs/design/decisions/](docs/design/decisions/).

## Commands

```bash
# Setup (migrating to uv + pyproject as the single dependency source — see ADR/journal)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the dashboard (offline; no API key needed)
streamlit run app/streamlit_app.py        # http://localhost:8501

# Tests (offline — pins the demo scenario)
pytest                                     # pythonpath=src is set in pyproject.toml

# Ad-hoc run of the core (no UI)
PYTHONPATH=src python -c "from pipeguard import run_gate_from_dir; \
  _, cards = run_gate_from_dir('data/mock_run_01'); \
  print([(c.sample_id, c.verdict.value) for c in cards])"
```

## Working agreement

**Workflow**
- Before non-trivial changes, inspect the relevant files and propose a short plan.
- No broad refactors unless explicitly asked. Prefer small, reviewable diffs.
- If requirements are ambiguous, make a reasonable assumption, state it, continue.

**Architecture guardrails**
- `src/pipeguard/` stays framework-agnostic — no Streamlit/FastAPI imports in the core.
- Reuse existing utilities, models, and patterns before adding new ones; no duplicate abstractions.
- Don't move files across `src/`, `app/`, `data/`, `docs/`, `tests/` without explaining why.

**Dependencies**
- Don't add a dependency unless the stdlib or an existing dep can't do it; justify additions.
- `pyproject.toml` is the single source of truth (uv). Pin for a reproducible demo.

**Security**
- Never hardcode keys, tokens, credentials, private URLs, or personal data — use env vars.
- Update `.env.example` when adding a required env variable.
- Never print secrets in logs, test output, or errors.

**Life-science / biomedical guardrails**
- Research/demo tool with production intent — **not** a clinical decision system.
  Make no diagnostic, therapeutic, or safety claims.
- Confidence values are heuristics, not calibrated probabilities — label them as such.
- Runbook thresholds are illustrative/configurable, not clinical thresholds.
- Keep evidence, assumptions, and generated suggestions separate; preserve citations,
  provenance, and confidence. Prefer conservative language; flag uncertainty.
- Clinical variant claims stay grounded in ClinVar/GIAB truth; never invent pathogenicity.

**Data handling**
- Never commit raw reads, PHI, credentials, or large artifacts. Commit accessions +
  a fetch script instead. Tag every artifact's origin (`real-giab` vs `synthetic`).
- Parse artifacts tolerantly at boundaries — a missing field is a signal, not a crash.

**Testing & verification**
- Changes to parsers or rules must keep the offline test suite green and the demo intact.
- Verification is batch-default (heavy checks on batch pushes); ask when a single change warrants one.

**Delivery posture**
- MVP-first with production-ready seams. Optimize for a working, understandable core
  flow — but run major tradeoff decisions by the maintainer first. Prefer boring, robust choices.

**Communication**
- Summarize what changed, list files modified, state how it was verified, and note
  remaining risks/TODOs/assumptions. Be concise. Reference files as clickable paths.

## Coding standards

- **Type hints across the board**, enforced by mypy.
- **Meaningful docstrings** on public functions and classes.
- **Comments explain *why*** a method or approach was chosen, not what the line does.
- **Configuration via env / typed settings** (pydantic-settings); never hardcode config.
  Two toolchains kept separate: `uv` for the app, bioconda/containers for genomics tools.

## Documentation rules

- Before creating a doc, check [docs/_templates/](docs/_templates/) and follow the
  matching template. If none fits, **create the template first**, then the doc.
- Update relevant docs in the **same change** as the code.
- Date entries ISO-8601 with **MST**. Keep a session journal and distill it into
  canonical docs at session end (journal is the archive, not the source of truth).

## Design invariants (details in docs/design/)

- **Rules decide; AI narrates/advises** — never let a synthesizer or agent set or
  override a verdict or confidence (ADR-0001).
- **Agents are advisory and OFF the deterministic critical path** (ADR-0001).
- **AI is OFF by default** with a deterministic fallback (ADR-0006).
- **Event-driven core**; every I/O is recorded in the provenance ledger (ADR-0002).
- **Deployment-agnostic ports & adapters**; Nextflow carries compute portability (ADR-0003).
- **Config layer + profiles** serve research (lean) and biotech (granular) from one codebase (ADR-0005).

## Current code map (session-1 baseline; evolving)

- `pipeguard.rules` emits cited `Finding`s; verdict/confidence computed in
  `synthesis/base.py` — never by the LLM.
- Synthesizer swappable via `PIPEGUARD_SYNTHESIZER=stub|claude` (default `stub`,
  offline, $0); `synthesis/claude.py` imports `anthropic` lazily and falls back to
  the stub on any error. Model via `PIPEGUARD_CLAUDE_MODEL` (default `claude-opus-4-8`).
- Data contract flows through `pipeguard.models` (pydantic); runbook holds QC policy.

## Git conventions

Incremental, self-contained commits; short title + descriptive body. No AI
attribution lines in commit messages.
