# run_layout emit → consume loop — scoping

| Field | Value |
|---|---|
| **Status** | Proposed (scoping) — the **emit UI shell** and the **hardcoded consume path** are current-state; the loop-closing work is phased and **not built**. The consume half was deliberately deferred ([data-platform-and-archivist.md](data-platform-and-archivist.md) §5f). This doc is the roadmap to close it. |
| **Last updated** | 2026-07-13 (MST) |
| **Audience** | software / bioinformatics |
| **Related** | [design/frontend/pipeline-builder-brief.md](frontend/pipeline-builder-brief.md) (the emit design + V1–V10 + the `run_layout.yaml` shape), [design/data-platform-and-archivist.md](data-platform-and-archivist.md) §5 (the typed `run_layout` schema + the explicit consume DEFER), [design/nextflow-codegen.md](nextflow-codegen.md) (the **separate** Export-to-Nextflow codegen path — not this), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md) (rules decide; config locates, never judges), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md) (deployment-agnostic ports; compose≠execute), [ADR-0005](../adr/ADR-0005-config-layer-and-profiles.md) (config layer + profiles), [requirements/functional.md](../requirements/functional.md) REQ-F-045, [planning/tasks.md](../planning/tasks.md) (T-032/T-033 config seams) |

## Overview

The Pipeline Builder's designed **sole grounded deliverable** is a `run_layout.yaml` — a *profiled artifact-kind → path/glob locator map*. The **full loop** is:

> compose → validate → **emit `run_layout.yaml`** → the running gate **locates** a run's artifacts from it → deterministic ingest flattens them to the frozen-five `run/` CSVs → `run_gate` gates + records the ledger → decision cards.

Today the **emit half exists as a UI shell** (client-only, graph-decoupled) and the **consume half does not exist** (`load_run` hardcodes filenames). This doc audits current-state against the designed contract, states the gap, phases the build, and surfaces two decisions to make **before** Phase 1. It does **not** duplicate the design intent (that lives in the brief + data-platform §5) — it is the *current-state-vs-gap-vs-roadmap* those docs lack in one place.

**This is distinct from "Export to Nextflow"** (`POST /api/pipelines/compile`, a stateless `{nodes,edges}→main.nf` codegen — [nextflow-codegen.md](nextflow-codegen.md)). That path is built; this one is not.

## Current state — a UI-complete emit shell, an un-refactored consume path, two un-unified locators

### Emit side — real UI, but graph-*decoupled* and client-only
1. **Fact.** The `Emit` verb, a live `run_layout.yaml` preview, Copy/Download, the profile switcher (`default·giab_panel·sarek`), and the `BAYLEAF_RUN_LAYOUT=<profile>` hint all exist — purely **client-side** (`frontend/src/components/BuilderShared.tsx`, `BuilderConsole.tsx`, `screens/PipelineBuilder.tsx`).
2. **Fact.** The YAML is a **fixed 9-entry `GIAB_LOC` template ⋈ inspector edits — NOT serialized from the composed nodes/output-ports** (`BuilderShared.tsx` `GIAB_LOC`/`buildYaml`/`yamlFor`). Adding/removing/retyping tool nodes changes the canvas but **cannot change what is emitted**.
3. **Fact.** `Validate` is a **static, always-green pass-list** (`VAL_ROWS`) — a *display* of the invariants, not a computed evaluator — and `onEmit` runs **unconditionally**. So the brief's **V10 "emit only on zero errors"** is *not enforced*.
4. **Fact.** There is **no backend emit endpoint**; `approve` only stamps `emitted_at` as a diff baseline (`api/pipeline_store.py record_emission`). **Nothing writes a `run_layout.yaml` file.** The backend's tolerant `_extract_locators` (`api/routers/pipelines_lifecycle.py`) reads a saved graph's locators only for the read-only **dry-run** + **diff** inspectors. The docs' "only `mosdepth_summary` is a real emitted locator today" is **verified** (the rest carry `parser: null`, pointer-only).

### Consume side — untouched, hardcoded
5. **Fact.** `load_run` (`src/bayleaf/parsers.py:341`) is the **sole** run-artifact locate mechanism and it **hardcodes the frozen-five (+extra) filenames** via a `_maybe(name)` literal-filename join — no layout, no dispatch table, no selector. `run_gate_from_dir` (`engine.py`) calls it with **no layout argument**.
6. **Fact.** `src/bayleaf/settings.py` exposes only `run_store_root()` (`BAYLEAF_DATA_ROOT` — where run *dirs* live). **`BAYLEAF_RUN_LAYOUT` exists nowhere in `src/`.** There is no `src/bayleaf/layout/` package, no `run_layout.yaml` on disk, no loader. `pydantic-settings` is deliberately **not** a dependency.
7. **Fact.** `ingest_results_dir` (`src/bayleaf/ingest/nfcore.py`) is a **second, different** locate mechanism (per-sample dot-globs) returning `SampleMetrics` — **gate-ready but not gate-called**, and not `load_run`-wired. Closing the loop needs these two mechanisms **unified** under one locator model (implies the deferred `RunArtifacts.qc → SampleMetrics` type flip, WS-06 PR2).

**Why deferred:** the consume half was **deliberately** deferred ([data-platform-and-archivist.md](data-platform-and-archivist.md) §5f) because it refactors the *one offline-suite-pinned working path* (`load_run`) for **zero demo-visible gain** and would be `pydantic-settings`' **first use in `src/`**.

## The gap — what closing the loop requires

| # | Piece | Where | Risk |
|---|---|---|---|
| **G1** | **Layout schema package** — frozen pydantic `RunLayoutConfig`/`LayoutLocator` (`path\|glob`, `parser`, `required`, `role: output\|reference`, `on_multiple: first\|all\|error`, `origin`) + a shipped, versioned `run_layout.yaml` (via `importlib.resources`, mirroring `metric_registry.yaml`) | new `src/bayleaf/layout/` | low |
| **G2** | **`BAYLEAF_RUN_LAYOUT` selector + loader** — resolve `default \| giab_panel \| /path/to/custom.yaml` (default `default`), mirroring `run_store_root()`'s call-time env pattern | `settings.py` | low–med (see Decision 1) |
| **G3** | **Parser-dispatch table** — `parser`-key → `parse_*`; wire only kinds with a real reader today (the 5 CSVs + `mosdepth_summary`); leave `vcf_stats`/`bam` as `parser: null` pointer-only | `parsers.py` | low |
| **G4** | **`load_run` refactor** — resolve artifacts *through* the selected layout's locators (glob, required-vs-optional, `on_multiple`, origin) instead of `_maybe(filename)`; **the `default` profile must reproduce today's five-file contract byte-for-byte** | `parsers.py` | **high** |
| **G5** | **Unify the two locators** (`load_run` literals + `nfcore.py` globs) under one model, so an emitted layout drives BOTH — implies the `RunArtifacts.qc → SampleMetrics` flip (WS-06 PR2) | `parsers.py`/`ingest/nfcore.py` | med–high |
| **G6** | **Graph-derived emit + a computed V1–V10 validator** with the V10 all-or-nothing gate on `Emit` (so what you *wire* is what you emit, and an invalid graph can't emit) | frontend + a shared serializer | med |
| **G7** | **Consume-time provenance** — each resolved absolute path → a ledger event **through `run_gate`**; guarded origin stamped at ingest from the run marker | the loader | med |

## Invariants the loop must not break

1. **compose ≠ execute** — emission is compose-time; writing `run_layout.yaml` triggers nothing; the primary verb is `Emit`, never `Run` (ADR-0001/0003). *Held today: `onEmit` is state-only; `approve` never runs.*
2. **The graph is non-authoritative** — `run_layout.yaml` is the *sole* grounded deliverable; no second bayleaf-owned pipeline-definition artifact (Nextflow owns the workflow definition).
3. **V10 emit-all-or-nothing** — emit only on zero errors, so a `run_layout.yaml` on disk is always the product of a fully valid graph. *(Not enforced today — G6.)*
4. **Config LOCATES, never judges** — locators map kind→path only; edges/agents/gate are excluded; the gate reads the **flattened frozen-five CSVs**, never raw tool outputs; `aggregate_verdict()` stays the sole verdict writer.
5. **Origin never relabels up** — every emitted locator's `origin` is `unknown`; guarded values (`real-giab`/`synthetic`/`contrived`) are stamped **only at ingest** from the run marker.
6. **Ledger integrity** — a run reaches the verdict **only through `run_gate`**; reuse the existing event vocab (`metric.parsed`/`artifact.ingested` — invent no new type); **never inject a file-backed `EventLedger` into the `@lru_cache`'d `_evaluate`** (it re-appends the whole trail per cache-miss and corrupts the append-only ledger).
7. **Agents advisory + off-path** — structurally port-less; routing a verdict is unrepresentable.

## Suggested phasing

1. **Phase 1 — Foundation (low-risk, no behavior change):** G1 + G2 + G3. Ship the schema package + the selector + the dispatch table. Nothing consumes it yet, so the running system is untouched. *Cleanest first cut; independently reviewable.*
2. **Phase 2 — The consume refactor (the load-bearing part):** G4 + G5 + G7. Route `load_run` through the layout with the **`default` profile byte-identical** (the full offline suite is the regression net); unify the glob mechanism; wire consume-time provenance.
3. **Phase 3 — Close the emit half:** G6 — graph-derived serialization + the real V1–V10 validator, so what an operator wires is what emits, and an invalid graph is blocked.
4. **Phase 4 — Loop closers (partly built):** dry-run (the lifecycle dry-run already resolves locators), round-trip import (reconstruct a graph from a `run_layout.yaml`), the in-app **Run** hand-off to Nextflow.

## Open decisions (resolve before Phase 1)

- **Decision 1 — `pydantic-settings` vs `os.getenv`.** `BAYLEAF_RUN_LAYOUT` would be `pydantic-settings`' first use in `src/` (a new dependency), or it can mirror the existing `os.getenv`/`run_store_root()` call-time pattern (no new dep). *Recommendation:* mirror the existing pattern for the selector to avoid the first-use dependency risk during the hackathon; revisit `pydantic-settings` if the config layer (T-032) grows.
- **Decision 2 — unify now (G5) or keep two mechanisms parallel.** The `load_run` literals and the `nfcore.py` globs can be unified in Phase 2, or the layout can drive `load_run` only and leave `ingest_results_dir` parallel for now. *Recommendation:* keep parallel through Phase 2 (smaller blast radius on the pinned path), unify in a dedicated follow-up alongside the WS-06 PR2 `RunArtifacts.qc` flip.

## Effort / risk read

Phase 2 (G4) is the whole ballgame — it touches the one path the offline suite pins, so **the `default`-profile-byte-identical rule + the full suite are the safety net**. Phase 1 is a clean, low-risk foundation with no behavior change. Because the docs deferred the consume half deliberately (no demo gain), this reads as **post-hackathon / production-hardening**, not a demo blocker — the payoff is a *real* "compose a pipeline, then the gate runs from your layout" story and the removal of the two hardcoded locate mechanisms.

---

*Marker legend — distinguish claim types where confusion is likely:*
**Fact** · **Assumption** · **Decision** · **TODO**.
