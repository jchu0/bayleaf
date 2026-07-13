# Journal — 2026-07-13 (MST) — Builder loaded-pipeline agent render fix + conda-env setup docs

| Field | Value |
|---|---|
| **Focus** | Fix a Pipeline-Builder bug where a loaded saved pipeline hid its advisory QC-triage agent; then document the conda/mamba env setup path so `uv run` doesn't create a stray `.venv`. |
| **Participants** | James Hu (maintainer); Claude Code (Opus 4.8) |
| **Outcome** | [PR #17](https://github.com/jchu0/claude_life_science_hackathon/pull/17) merged (`showAgent` render gate + load re-fit); README + CLAUDE.md now document `UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX"`. |

## Discussion

### Builder — a loaded pipeline hid its advisory agent (PR #17)

1. **Symptom.** Opening a saved pipeline via "Open saved" rehydrated its persisted `agent_bindings`
   but showed **no** QC-triage card, connectors, node badges, grant popover, or minimap dot. A page
   refresh appeared to "fix" it.
2. **Root cause (render).** Every agent visual was gated on `showTerminals`, which `PipelineBuilder`
   derives as `isLinked` (`docKind === 'germline' && docName === GRAPH_ID` — ADR-0019 slice 1a
   run-linkage). `loadSavedPipeline` sets `docKind='blank'`, so `isLinked` is false and the agent
   never rendered — even though `reconcileBindings(...)` had populated `agentBindings` correctly. The
   seeded template only showed the agent because *it* is the linked doc. "Refresh fixes it" was a red
   herring: a refresh drops back to the default germline canvas (linked → agent via `showTerminals`),
   not the loaded pipeline. Fix: `showAgent = showTerminals || boundNodeIds.size > 0`, gating the five
   agent visuals.
3. **Root cause (viewport).** A quieter second gap: an in-app `loadSavedPipeline` set the graph but
   never re-fit the viewport (only a page reload's once-on-mount fit did), leaving the loaded graph's
   off-centre cards — notably the advisory-agent landmark below the QC nodes — off-screen. Fix:
   `loadSavedPipeline` bumps `fitNonce`, reproducing the mount fit.
4. **Process lesson (worth keeping).** The `showAgent` fix *looked* broken after it was written,
   because it had been committed to the PR branch and a `git checkout main` silently reverted the
   working tree; Vite HMR reloaded the fix-less file and the dev server served the old behavior. When
   a fix seems to "regress," verify against the branch the dev server is actually serving — not just
   "the fix is written somewhere."

### Setup docs — conda/mamba env vs uv's `.venv`

5. The docs assume `uv run …`, which manages a project-local `.venv`. When the app's Python deps live
   in a conda/mamba env instead, `uv run` would spawn a stray `.venv`. Documented the fix **without
   rewriting every command**: `uv` stays the dependency *source* (`pyproject.toml` + `uv.lock`);
   `export UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX"` points it at the active env, so
   `uv sync`/`uv run`/`make check` all target it — or activate the env and drop the `uv run` prefix
   (`pytest`, `uvicorn …`, `ruff`, `mypy`). Kept portable (`$CONDA_PREFIX`, not a hardcoded path) and
   warned that `uv sync` prunes the target env to the lockfile → keep the app env separate from the
   bioconda genomics env.

## Decisions

| Decision | Distilled to |
|---|---|
| Advisory agent renders when run-linked **OR** carrying a binding (not run-linked only) | [PR #17](https://github.com/jchu0/claude_life_science_hackathon/pull/17) — `frontend/src/components/BuilderCanvas.tsx` |
| Document conda-env setup via `UV_PROJECT_ENVIRONMENT`; don't rewrite every `uv run` | [README.md](../../README.md) Quickstart + Development; [CLAUDE.md](../../CLAUDE.md) Commands |

## Open questions & TODO

- None outstanding for these changes. Standing (unrelated) cleanup still open: prune merged
  `harden/*` / `docs/*` branches, `docker rmi bayleaf-api`, remove the `hackathon_demo` clone.

## Distilled into

- [README.md](../../README.md) — Quickstart conda-env callout + Development pointer
- [CLAUDE.md](../../CLAUDE.md) — Commands env note
- `frontend/src/components/BuilderCanvas.tsx` + `frontend/src/screens/PipelineBuilder.tsx` (PR #17, merged `cc4a5a7`)
