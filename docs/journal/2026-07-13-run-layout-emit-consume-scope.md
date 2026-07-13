# Journal — 2026-07-13 (MST) — Scoping the run_layout emit→consume loop

| Field | Value |
|---|---|
| **Focus** | Scope the full Pipeline-Builder `run_layout.yaml` **emit → consume** loop (maintainer request), grounded in a read-only 3-surface code audit rather than the design docs alone. |
| **Participants** | Claude (Opus 4.8) orchestrating 3 read-only `Explore` agents (emit / consume / design-gap maps); maintainer (James Hu). |
| **Outcome** | New design doc [design/run-layout-emit-consume.md](../design/run-layout-emit-consume.md) — current-state audit + the gap (G1–G7) + the invariants + a 4-phase build plan + 2 open decisions. ToC row + `Last updated` + this journal. **No code changed** (scoping only). |

## Discussion

### Why this doc exists
The maintainer asked to "scope out the pipeline build emit feature" — specifically the **full emit→consume loop**. The design intent already lives in [pipeline-builder-brief.md](../design/frontend/pipeline-builder-brief.md) + [data-platform-and-archivist.md](../design/data-platform-and-archivist.md) §5, but nowhere did a single doc state **what is built vs missing vs how to close it**. This doc is that roadmap; it deliberately does not duplicate the design intent.

### Key findings (code-grounded, 3-surface map)
1. **Emit is a UI shell decoupled from the graph, client-only.** The `Emit` verb, `run_layout.yaml` preview, profile switcher, Copy/Download all exist — but the YAML is a fixed `GIAB_LOC` template ⋈ inspector edits, **not** serialized from the composed nodes/ports; `Validate` is a static always-green pass-list (no V10 gate); nothing writes a `run_layout.yaml` (`approve` only stamps `emitted_at`).
2. **Consume does not exist.** `load_run` (`parsers.py:341`) hardcodes the frozen-five filenames; `settings.py` has no `BAYLEAF_RUN_LAYOUT` selector; there is no `src/bayleaf/layout/` package or loader.
3. **Two un-unified locate mechanisms.** `load_run` (literal filenames) vs `ingest_results_dir` (per-sample globs, gate-ready-but-not-gate-called) — the loop needs them unified (implies the deferred `RunArtifacts.qc → SampleMetrics` flip, WS-06 PR2).
4. The consume half was **deliberately deferred** (data-platform §5f) — it refactors the one offline-suite-pinned path (`load_run`) for zero demo gain and would be `pydantic-settings`' first `src/` use.

### The two decisions to resolve before Phase 1
- **`pydantic-settings` vs `os.getenv`** for the `BAYLEAF_RUN_LAYOUT` selector (recommend mirroring the existing `run_store_root()`/`os.getenv` pattern — no new dep during the hackathon).
- **Unify the two locators now (G5) or keep them parallel** through Phase 2 (recommend parallel, unify in a follow-up with WS-06 PR2).

## Decisions

| Decision | Distilled to |
|---|---|
| Capture the loop as a **design doc**, not an ADR — no load-bearing decision is *made* yet; the 2 open decisions become ADRs when resolved | [design/run-layout-emit-consume.md](../design/run-layout-emit-consume.md) |
| Phase the build: Phase 1 foundation (schema+selector+dispatch, no behavior change) → Phase 2 `load_run` refactor (`default` byte-identical) → Phase 3 graph-derived emit + validator → Phase 4 loop closers | the design doc §Suggested phasing |

## Open questions & TODO
- Resolve Decision 1 + Decision 2 (maintainer input) before Phase 1.
- The loop is post-hackathon / production-hardening, not a demo blocker.

## Distilled into
- [design/run-layout-emit-consume.md](../design/run-layout-emit-consume.md) — the scoping doc (new)
- [docs/TABLE_OF_CONTENTS.md](../TABLE_OF_CONTENTS.md) — design-section row + `Last updated`
