# CLAUDE.md — bayleaf

AI-assisted provenance & QC decision gate for genomics runs (Built with Claude:
Life Sciences hackathon). This file is the self-contained operating contract for
this repo — do not assume any global rules apply here.

**Naming:** the product and the Python package are now both **bayleaf** — the
breaking package rename landed 2026-07-13 (`src/bayleaf/`, `from bayleaf import …`,
all `BAYLEAF_*` env vars, `X-Bayleaf-*` wire headers). The historical name was
"PipeGuard"; some git history and archived journals predate the rename.

## Start here (every session)

1. **Two top-layer inputs — read both at session start:**
   a. [docs/TABLE_OF_CONTENTS.md](docs/TABLE_OF_CONTENTS.md) — the map of what exists,
      and (its **Doc-update map**) the authority on which docs a given change obligates.
   b. [docs/planning/tasks.md](docs/planning/tasks.md) — development state, timeline,
      and which work is parallel-safe (fan out subagents for non-blocking tasks).
2. **Read lean, write complete.** Load only the files the task needs (bulk-load only when it
   genuinely needs broad context). Reading and owing are separate: before you finish, sweep the
   [Doc-update map](docs/TABLE_OF_CONTENTS.md#doc-update-map) and update every doc your change made
   stale — a doc you never opened can still be one you now owe (see *Documentation rules* below).
   Every working session also owes a `docs/journal/YYYY-MM-DD-<topic>.md` entry.
3. Follow [docs/DOCUMENTATION_HABITS.md](docs/DOCUMENTATION_HABITS.md) for anything
   documentation-related.
4. The `why` behind the architecture lives in the ADRs at [docs/adr/](docs/adr/).

## Commands

```bash
# Setup (uv is the single dependency source: pyproject.toml + uv.lock)
uv sync --all-extras                        # .venv + deps + dev tools, editable install
uv run pre-commit install --install-hooks   # ruff/mypy/secret-scan (commit) + pytest (push)

# Run the full stack (FastAPI read-API + React; Vite proxies /api -> :8010).
# Offline + no API key needed by default (agents are stub-first); this IS the demo.
uv run uvicorn api.main:app --port 8010     # backend
npm --prefix frontend run dev               # frontend (Vite dev server)
npm --prefix frontend run build             # tsc -b + vite build (the pre-push tsc gate)
npm --prefix frontend run lint              # oxlint

# Tests (offline — pins the demo scenario)
uv run pytest                               # editable install; no PYTHONPATH shim
uv run pytest tests/test_ingest.py -k name  # a single file / -k a single test
make check                                  # one-shot gate: ruff + mypy + pytest

# Lint + strict type-check (Python)
uv run ruff check && uv run mypy

# Ad-hoc run of the core (no UI)
uv run python -c "from bayleaf import run_gate_from_dir; \
  _, cards = run_gate_from_dir('data/mock_run_01'); \
  print([(c.sample_id, c.verdict.value) for c in cards])"
```

## Working agreement

**Workflow**
1. Before non-trivial changes, inspect the relevant files and propose a short plan.
2. No broad refactors unless explicitly asked. Prefer small, reviewable diffs.
3. If requirements are ambiguous, make a reasonable assumption, state it, continue.
4. **Parallelize by default.** Batch independent work into as many concurrent processes as
   safely possible: issue independent tool calls in one message, and fan out subagents/
   workflows for non-blocking tasks (audits, per-file/-screen sweeps, research, multi-angle
   design, verification). Scout inline to discover the work-list, then fan out over it.
   Caveats: keep tightly-coupled edits to the *same* file single-author (parallel writers
   collide); serialize steps with a real data dependency; use read-only agents (Explore) for
   audits/reviews. When unsure whether two tasks are independent, they usually are — split them.
   **Prioritize background execution:** default to pushing non-blocking work to background agents
   (`run_in_background`) / Workflows so the main interaction surface stays free for decisions and
   synthesis rather than being consumed by long inline processing — report results when they land.

**Architecture guardrails**
1. `src/bayleaf/` stays framework-agnostic — no FastAPI/React imports in the core.
2. Reuse existing utilities, models, and patterns before adding new ones; no duplicate abstractions.
3. Don't move files across `src/`, `app/`, `data/`, `docs/`, `tests/` without explaining why.

**Dependencies**
1. Don't add a dependency unless the stdlib or an existing dep can't do it; justify additions.
2. `pyproject.toml` is the single source of truth (uv). Pin for a reproducible demo.

**Security**
1. Never hardcode keys, tokens, credentials, private URLs, or personal data — use env vars.
2. Update `.env.example` when adding a required env variable.
3. Never print secrets in logs, test output, or errors.

**Life-science / biomedical guardrails**
1. Research/demo tool with production intent — **not** a clinical decision system.
   Make no diagnostic, therapeutic, or safety claims.
2. Confidence values are heuristics, not calibrated probabilities — label them as such.
3. Runbook thresholds are illustrative/configurable, not clinical thresholds.
4. Keep evidence, assumptions, and generated suggestions separate; preserve citations,
   provenance, and confidence. Prefer conservative language; flag uncertainty.
5. Clinical variant claims stay grounded in ClinVar/GIAB truth; never invent pathogenicity.

**Data handling**
1. Never commit raw reads, PHI, credentials, or large artifacts. Commit accessions +
   a fetch script instead. Tag every artifact's origin (`real-giab` / `synthetic` / `contrived`).
2. Parse artifacts tolerantly at boundaries — a missing field is a signal, not a crash.

**Testing & verification**
1. Changes to parsers or rules must keep the offline test suite green and the demo intact.
2. Verification is batch-default (heavy checks on batch pushes); ask when a single change warrants one.

**Delivery posture**
1. MVP-first with production-ready seams. Optimize for a working, understandable core
   flow — but run major tradeoff decisions by the maintainer first. Prefer boring, robust choices.
2. **Do not foreground time/deadline pressure.** Budget is ample (weekly + 5-hour caps well
   under limit); build steadily, pursue the maintainer's wishlist features, drop deadline hedging,
   and reassess scope at checkpoints. This governs framing only — the *guardrails above still hold*.

**Communication**
1. Summarize what changed, list files modified, state how it was verified, and note
   remaining risks/TODOs/assumptions. Be concise. Reference files as clickable paths.
2. Use **numbered or lettered lists**, not plain bullets, for anything referenceable —
   in docs, commit bodies, and chat responses — so items get short stable IDs
   (e.g. "Security 2") for feedback without quoting long text.

## Coding standards

1. **Type hints across the board**, enforced by mypy.
2. **Meaningful docstrings** on public functions and classes.
3. **Comments explain *why*** a method or approach was chosen, not what the line does.
4. **Configuration via env / typed settings** (pydantic-settings); never hardcode config.
   Two toolchains kept separate: `uv` for the app, bioconda/containers for genomics tools.

## Documentation rules

1. Before creating a doc, check [docs/_templates/](docs/_templates/) and follow the
   matching template. If none fits, **create the template first**, then the doc.
2. Update every doc your change obligates, in the **same change**; the [Doc-update map](docs/TABLE_OF_CONTENTS.md#doc-update-map) is the routing authority (touch X → owe doc Y), not the set of files you opened.
3. Date entries ISO-8601 with **MST**. Keep a session journal and distill it into
   canonical docs at session end (journal is the archive, not the source of truth).
4. **Crosslink related sources** — fill each doc's Related field and link inline
   references (docs, ADRs, code) so navigation is one click.
5. Before declaring a **substantive** session/PR done, run the **Session-end doc checklist**
   ([DOCUMENTATION_HABITS.md](docs/DOCUMENTATION_HABITS.md#session-end-doc-checklist))
   and include its CHK-1/CHK-2/CHK-3 results in the wrap-up summary.

## Design invariants (details in docs/design/)

1. **Rules decide; AI narrates/advises** — never let a synthesizer or agent set or
   override a verdict or confidence (ADR-0001).
2. **Agents are advisory and OFF the deterministic critical path** (ADR-0001).
3. **AI is OFF by default** with a deterministic fallback (ADR-0006).
4. **Event-driven core**; every I/O is recorded in the provenance ledger (ADR-0002).
5. **Deployment-agnostic ports & adapters**; Nextflow carries compute portability (ADR-0003).
6. **Config layer + profiles** serve research (lean) and biotech (granular) from one codebase (ADR-0005).

## Current code map (current state; updated 2026-07-13)

> Dated wave/batch narrative, superseded detail, and per-commit history →
> [docs/HISTORY.md](docs/HISTORY.md) (git-archived, **not** loaded each session). This is
> current-state only (what exists NOW, per subsystem); the *why* is in the ADRs ([docs/adr/](docs/adr/)).

1. **Core (`src/bayleaf/`) — framework-agnostic (no FastAPI/React imports).**
   a. `rules` emits cited, immutable `Finding`s (each derives its gate + a rule-version-independent
      signature + `content_hash`); `synthesis/base.py` aggregates the verdict (**never** the LLM,
      ADR-0001); confidence omitted until grounded (T-019). Fraction QC metrics render as percent
      via a registry-backed display conversion (no verdict/hash change). **Fail-closed additions
      (gap-analysis WS-01, 2026-07-12):** `QC-MISSING` (a sheet-declared sample with no QC row →
      WARN/HOLD, LIVE end-to-end — `aggregate_verdict([])` no longer PROCEEDs on unexamined data)
      and `_check_expected_metrics` (a `Runbook.expected_metrics` key absent from the sample's
      metrics → `QC-EXPECTED-<key>` WARN/HOLD, validated at construction against the producible-key
      set so a typo can't HOLD forever). `rules.compute_check_coverage` → `models.CheckCoverage`
      (deterministic "N ran / M not examined" over a fixed provenance/metadata/qc/contamination/
      identity/pipeline catalog, carried un-hashed on `DecisionCard.check_coverage`, never a verdict)
      replaces the old "all checks passed" stub prose and the RunDetail clean-card panel — both now
      state plainly when contamination/identity were never examined. **Honesty fix (2026-07-13,
      `b03d1fa`):** contamination/identity now genuinely flip to "ran" when the sample actually
      carries a metric in that category — `_examined_metric_categories` treats present = examined
      = ran (pass or fail), closing a sub-gap where an examined-and-passed FREEMIX still read
      "contamination not examined" (the finding-based flip the original design intended never fired,
      since every `QCThreshold` finding is tagged `Category.QC`, not `Category.CONTAMINATION`).
      Identity stays honestly not-examined — no NGSCheckMate parser exists to ever populate it.
   b. `models` (pydantic data contract), `identifiers` (UUIDv7 ids + content hashing; `PLATFORM_VERSION`
      from `pyproject.toml`), `runbook` (QC policy). **Ingestion contract (WS-06·PR1/PR2, 2026-07-12):**
      `models.RawObservation`/`models.SampleMetrics` (a registry-keyed `sample_id + raw: dict[our_key
      -> RawObservation]` map, additive to the flat `QCMetrics`) is the shape a real-run adapter emits;
      `RunArtifacts.qc: list[QCMetrics | SampleMetrics]` (a transition Union, not a hard flip) means the
      gate consumes EITHER shape byte-identically (`metrics.mapping.metric_values_for` accepts both).
   c. `runbook.QCThreshold.required` (default `True`, T-082): the richer QC report (13 metrics: the
      frozen five + 8 registered) gates 5 **optional** thresholds (score a present value, never
      NA-flag an absent one) without penalizing a lean real run. `QCThreshold.kind` (WS-06 Gap 2,
      2026-07-12) adds a **`target_band`** shape (both-tails PASS/WARN/CRITICAL band, e.g. Ts/Tv) beside
      the default `one_sided`; `variant.titv` is the first threshold to use it. Metric catalog = **13
      gated / 8 ungated** of 21 registered `our_key`s (`data/metric_registry.md`; was 11/9 of 20 before
      WS-02/WS-04, 2026-07-12, gated `contamination.freemix` (VerifyBamID2) + new key
      `concordance.snp_f1` (hap.py) — real ingest-adapter parsers, but **gated + parser-wired, not
      pipeline-produced by default**: `happy.nf` is still a standalone Nextflow module
      (`pipelines/optional_modules/`) not wired into any pipeline; `verifybamid2.nf` is now wired
      into the drift-locked `pipelines/germline/` reference as a **dormant** stage (T-071a, item 1e)
      — still not pipeline-produced *by default* (armed only if an operator supplies the SVD panel).
      **Proven on real, calibrated tool output (2026-07-13, `478d579`):** both parsers
      now additionally read GENUINE tool output (a genome-wide-calibrated VerifyBamID2 `.selfSM`,
      FREEMIX 0.000220096; a real hap.py `summary.csv` vs GIAB v4.2.1 truth, SNP-F1 0.989276) —
      committed as tiny fixtures (`tests/fixtures/giab_real/`) and proven through the public
      `ingest_results_dir → run_gate` path (`tests/test_real_giab_calibrated.py`), upgrading WS-02/
      WS-04 from "parser-wired, fixture-tested" to "proven on real calibrated tool output." The
      "not pipeline-produced" caveat is unchanged — no pipeline in this repo runs either tool. **`runbook.RunbookSet`/`RunbookKey`** (WS-05, 2026-07-12): a per-`(assay,
      sample_type, platform)` runbook resolver (binary-weight precedence, fail-closed to the full
      `default` runbook, never `None`) — `rules.evaluate_run` widened to `Runbook | RunbookSet`;
      `evaluate_sample`/`aggregate_verdict` are UNCHANGED (ADR-0001 preserved). `GERMLINE_PANEL_RUNBOOK`
      (keyed on `assay="germline-panel"`) is the first production consumer of WS-01's
      `expected_metrics` — verified end-to-end (a sample PROCEEDs under the plain `DEFAULT_RUNBOOK`,
      HOLDs under `DEFAULT_RUNBOOK_SET`, driven by `QC-EXPECTED-QC.BREADTH_20X`/`_30X`). **Deferred,
      labelled:** the Settings→runbook config-apply loop (`api/main.py::_active_runbook` still returns
      one run-level `Runbook`) and the assay×tissue frontend UI.
   d. `runbook.FlagForReviewPolicy` + `rules._check_flag_for_review` (**VAR-FFR-001**, ADR-0018 D2): a
      distinct, off-by-default variant-gate rule — never gates call quality; routes a sample to
      mandatory human review when an operator-armed ClinVar significance is present on an
      externally-annotated `VariantCall` (read from `variants.csv`, never authored — quotes ClinVar
      verbatim, ADR-0004). Empty `significances` ⇒ disarmed (shipped default); the API arms it per
      run (item 4). Fires end-to-end via the `data/RUN-2026-07-11-CLINVAR-RTH/` (`contrived`) fixture
      through the API only — the core default + pinned demo untouched.
   e. `nextflow/` — a pure-text **card-graph → Nextflow (DSL2) compiler** (T-123): `catalog.py`
      (curated tool→`ProcessSpec`: bioconda/biocontainer, typed ports, real `script:` + `stub:`,
      per-sample `[meta,files]` fan-out, MultiQC the one aggregator), `compiler.py` (`compile_graph()`:
      Kahn topo-sort, channel wiring from typed edges, robustness guards — injection escaping,
      proc-name collision, fan-in, dup-emit, catalog-port-drift; an uncatalogued tool → a labelled
      placeholder, never a fabricated command), `germline.py` (the seeded chain). Operator
      custom-script processes render **VERBATIM** via `_render_custom` (`NfNode.script/container/conda`,
      ADR-0020; a blank script → `CompileError`). Emits text only — **never runs a tool (compose ≠
      execute, ADR-0001/0003)**; see [design/nextflow-codegen.md](docs/design/nextflow-codegen.md).
      **Optional external input + a dormant contamination stage (T-071a, PR #12, 2026-07-13):** a
      new general compiler concept, `catalog.OPTIONAL_INPUT_PARAMS` (kind → params key), lets an
      input be operator-suppliable but **not required** — it compiles to a param-gated source
      channel (`params.x ? Channel.fromPath(params.x) : Channel.empty()`), deliberately kept OUT of
      `required_inputs()`; unset → the consuming process gets an empty channel and runs **zero
      tasks** (dormant, standard DSL2 semantics, not an error). `germline_graph()` (the canonical
      reference) now wires a verifybamid2 contamination stage this way — its `svd_panel` is the
      concept's first user — so the committed `pipelines/germline/` (regenerated, drift-lock still
      green, `tests/test_nextflow_compile.py`) carries a real `VERIFYBAMID2` process that is
      **dormant on the pinned/offline demo** (no `params.verifybamid_svd` supplied) and would emit
      the `.selfSM` `ingest.nfcore._extract_verifybamid` (item 1g below) already parses, once armed.
      **Contamination is now pipeline-*producible*, not yet pipeline-*live*: three follow-ups
      remain** — `scripts/run_giab_pipeline.py` (the live intake driver) still doesn't parse
      `.selfSM` (only the still-not-gate-called `ingest.nfcore` adapter does, item 1g); a live
      *multi-sample* run needs the SVD panel staged as a broadcast value channel + a `--SVDPrefix`
      sibling-file convention; the frontend Builder's seeded template has no verifybamid2 card yet.
      Detail: [design/nextflow-codegen.md](docs/design/nextflow-codegen.md) rule 9.
   f. `synthetic/` — the failure-mode data generator incl. `scale.py` (`demo/scale/bulk` CLI, T-050).
   g. `ingest/nfcore.py` (WS-03, 2026-07-12): `ingest_results_dir()` turns a **real, published**
      nf-core/MultiQC `results/` dir into registry-keyed `SampleMetrics` — parses `fastp.json` +
      `mosdepth` summary/thresholds (authoritative, structured) and `multiqc_data.json` general-stats
      (secondary, alias-fed); a drifted MultiQC key still folds to its `our_key`; an unknown key /
      absent structured file surfaces honestly in `IngestResult.unmapped`, never fabricated.
      **Proven end-to-end on genuine output** (env-gated real-path test, `tests/test_ingest.py`):
      real HG002 `results/` → `ingest_results_dir` → `SampleMetrics` → the `RunArtifacts.qc` Union
      (item 1b) → `run_gate` → the SAME HOLD the production driver's own parse produces. **Honest
      gap:** this adapter is gate-**wired** (the type is accepted) and gate-**proven** (the real-path
      test), but it is **not gate-called** by any running code path — `POST /api/runs` (item 4b.i)
      still drives `scripts/run_giab_pipeline.py`'s own bespoke parser into the frozen-five
      `qc_metrics.csv` → `QCMetrics`, a separate, unrelated-by-name `SampleMetrics` dataclass local to
      that script. A `POST /api/runs/ingest` endpoint to call `ingest_results_dir` from outside stays
      **deferred** — the two ingestion paths are proven equivalent, not yet unified. **WS-02/WS-04
      (2026-07-12):** `_extract_verifybamid`/`_extract_happy` added to this same adapter, parsing a
      present VerifyBamID2 `.selfSM` (FREEMIX) / hap.py `summary.csv` (SNP-F1 vs GIAB truth) into
      `contamination.freemix`/`concordance.snp_f1` — real, tested parsers, each gated by an optional
      (`required=False`) `runbook.QCThreshold` (item 1c). **Was the same honest gap as above, one
      layer earlier; half-closed 2026-07-13 (T-071a, PR #12):** `happy.nf` (real `script:` + `stub:`)
      still lives unwired in `pipelines/optional_modules/` — **not wired into any runnable
      pipeline**, a live SNP-F1 number still needs an operator to run it by hand (needs the GIAB
      truth VCF + confident BED, labelled input, never fabricated, ADR-0004). `verifybamid2.nf`,
      however, is **no longer unwired** — item 1e's new `catalog.OPTIONAL_INPUT_PARAMS` concept
      wires it into the drift-locked `pipelines/germline/` reference as a dormant stage (the
      "compiler has no input-gated-conditional concept" limitation this paragraph used to note is
      resolved for THIS one input kind); a live FREEMIX number still needs an operator to arm
      `params.verifybamid_svd` (an SVD/UD ancestry panel, labelled input, never fabricated,
      ADR-0004) — see item 1e for the three follow-ups that remain before it is genuinely live.

2. **Provenance seam (`provenance.py`, ADR-0002).** `run_gate` emits an append-only event trail
   (`analysis_run.started` → per-sample findings/verdict → `completed`) into an `EventLedger`
   (in-memory + JSONL) — the event log is authoritative, the DB a rebuildable projection via
   `persistence/` `get_repository()` (`BAYLEAF_REPOSITORY=sqlite|postgres`, default SQLite,
   degrade-to-SQLite; SqliteRepository + guarded off-by-default PostgresRepository, ADR-0016);
   `rebuild-db` targets either (ADR-0003). A tenth `EventType` `DATA_EXPORTED` (ADR-0018 D3) is
   emitted by the read-API (not `run_gate`) into a **separate** sink `api/share_store.py` (a
   `ShareStore` Protocol, jsonl/sqlite/postgres via `BAYLEAF_SHARE_STORE`, degrade-to-JSONL) —
   kept off the gate's `@lru_cache`'d re-derivation because a share is a live side effect that must
   survive a restart; `GET /api/runs/{id}` merges the two at read. Other ports: notify
   (stub/Slack/Teams/Discord, ADR-0010); artifact store (`LocalArtifactStore` + off-by-default
   `S3ArtifactStore`, `BAYLEAF_S3_LIVE`). Multi-worker locking on the off-gate stores is a
   documented seam, not built (ADR-0016).

3. **Swappable AI, OFF by default (ADR-0006 deterministic fallback; ADR-0009/0012 scoping/tiering).**
   Six `stub|claude` seams, all stub-first ($0), lazy `anthropic` import, fall back to the stub on
   any error (incl. a safety refusal); models via `BAYLEAF_*_MODEL`. Five are one-liners:
   a. synthesizer (`BAYLEAF_SYNTHESIZER`) — **honesty fix (WS-07 Q1, 2026-07-12):** the stub no
      longer emits hardcoded per-verdict `next_steps` boilerplate (dropped `_NEXT_STEPS`; stub
      `next_steps=[]`, dishonest filler on a $0 default path a stub cannot ground); the live Claude
      path is unchanged. `api/card_readout.py` now surfaces `qc_reports` (real `fastp.html`/
      `multiqc_report.html` links off the run dir, sibling-scoped) as the AI-off fallback so the
      suggestion box degrades to real artifacts, not silence.
   b. QC-triage (`triage/`, `BAYLEAF_TRIAGE_AGENT`) — **`ask` (WS-07 Q2, 2026-07-12):**
      `TriageAgent.ask` + `POST /api/runs/{run_id}/cards/{sample_id}/ask` (`AskRequest`→`AgentReply`,
      `advisory: Literal[True]`, no verdict/confidence) answers a free-text question about a card,
      even a clean PROCEED one; the stub retrieves + cites corpus knowledge explicitly framed as
      retrieval, never fabricated prose; Claude writes only the answer, citations stay deterministic.
      **Still open (design-only):** richer per-agent artifact/cross-sample context and real semantic
      retrieval (`design/agents.md`'s `EmbeddingRetriever` seam) — the corpus + `KeywordRetriever`
      are unchanged; see [audit/gap_analysis/ws-07-ai-earning-its-place.md](audit/gap_analysis/ws-07-ai-earning-its-place.md)
      Design items 1/2/4.
   c. pipeline-repair (`pipeline_repair/`, `BAYLEAF_PIPELINE_REPAIR_AGENT`, Opus-high; recurring
   signature → cited `RepairProposal`); d. feedback-categorization (`api/feedback_agent.py`,
   off-gate); e. archivist (`api/archivist.py`, off-gate, Haiku; released runs → `ArchiveDigest`).
   The sixth:
   f. node-authoring (`src/bayleaf/node_author/`, `BAYLEAF_NODE_AUTHOR_AGENT`, Sonnet default): a
      NL request / bare tool name → a cited `NodeProposal` retrieved over a **fixed curated 9-card
      corpus** (7 germline tools + Reference FASTA + Panel BED; NGSCheckMate is retired-but-pinned
      and Truth VCF removed — both KINDS stay in the vocabulary). `advisory: Literal[True]`, no
      verdict/confidence (ADR-0001); a port kind outside `ARTIFACT_KINDS` is `reserved`, never wired
      (`PortSpec.known` structurally computed). Read + accept API: `GET /api/builder/node-proposal`,
      `POST .../node-proposal/accept` (reviewer/approver — the server *re-derives* via `propose_node`
      so a client can't smuggle metadata, guards `matched` + `check_conformance`, persists a **draft
      metadata-only `LibraryEntry`** into `api/library_store.py`), `GET /api/builder/library`;
      `conformance.py` (a boundaries-contract validator) + `importer.py` (a `nextflow_schema.json`
      doc-drop importer, unknown kinds→reserved-never-invented). **Deferred:** the `--help`/README
      importer half, the draft→approve transition, the Builder "Accept to library" button; the
      corpus stays fixed (no genuine new-tool onboarding). Boundaries:
      [design/agent-authoring-contract.md](docs/design/agent-authoring-contract.md).

4. **Delivery layers (thin, over the core).** The FastAPI read-API + React frontend are the
   product surface (the Streamlit MVP was removed 2026-07-13 — the offline, stub-first full stack
   is the demo).
   a. `api/` = FastAPI read-API + **off-gate writes**. Authz: the dev-shim `api/auth.py` (Role
      viewer|reviewer|approver + `Actor` + `current_actor()` from `X-Bayleaf-Actor/-Role` headers,
      permissive dev-default, `require_role`) — the shared authz source and the single swap point for
      real auth. Off-gate stores are all pluggable (jsonl/sqlite/postgres, degrade-to-jsonl):
      feedback, pipeline-graph, settings, review, share; plus a node-local **durable job store**
      (`api/job_store.py`, jsonl/sqlite under gitignored `.nf-runs/`, T-131 — a job survives a
      restart, reconciling `running`→`complete`/`lost`, never an eternal spinner) and library store.
      `api/card_readout.py` projects card `metric_values` ⋈ runbook → Metric·Observed·Threshold·Status
      + `blocked_by` (the maintainer's two-tier gate-dependency model); core card/gate untouched.
      Read endpoints: runs (pagination/search, Tier-0 params, facet-count header), artifacts + a
      traversal-hardened download (inline default, `?download=1` attaches, T-077), `/variants`
      (T-133, ClinVar quoted verbatim), `/monitoring` (server-side `page`/`limit`, T-072 closed),
      advisory-agent reads (repair / archive-digest / archive-index), `/runbook` (three-gate
      readout), and a **sandboxed `GET /api/files`** (`api/routers/files.py`: allowlisted
      `BAYLEAF_BROWSE_ROOTS` default `data/`, `resolve()`+`is_relative_to()`, read-only, ADR-0020).
      **Execution boundaries (out-of-core — the API triggers an external driver; the core still never
      runs a tool):**
      i. **Intake `POST /api/runs`** (`api/routers/intake.py`, T-057) registers a samplesheet and
         drives Nextflow via `scripts/run_giab_pipeline.py` (`nextflow run pipelines/germline/main.nf`,
         parses published QC into the frozen-five run dir; needs `nextflow` + JRE + bioconda on PATH
         via `BAYLEAF_BIOCONDA_BIN`). **Verified live on HG002 (local-serial); the multi-sample
         parse is offline-proven vs fixture publish dirs but a live multi-sample run is
         env-gated/unverified (only HG002 has reads); the Slurm profile is config-verified NOT
         cluster-verified.** **Verification milestone (2026-07-12):** the toolchain (`nextflow`
         26.04 + a JRE) was installed into the machine-local `hackathon` conda env and the REAL
         germline pipeline was run end-to-end on real GIAB HG002 (`completed=7 failed=0`, Q30 88.2%,
         coverage 54.2×, 553 variants) — proving both the driver's own parse path (unchanged) AND,
         separately, the full alternate ingestion spine (item 1g) against that SAME genuine output.
         Two HIGH gaps in running a **non-germline** authored pipeline through this endpoint are now
         closed (WS-09, 2026-07-12) by rejecting rather than by generalizing the parser: `SubmitRunIn`
         **422s at submit** — before any compute — when the named pipeline can't produce the
         frozen-five outputs (`authored_pipeline.check_parse_contract`) or needs an input intake can't
         supply (`check_inputs_suppliable`, parity with Builder-Run's `required_inputs` check) —
         so a pipeline that used to run to completion in Nextflow then die at parse now fails fast
         instead. **This does not make intake gate an arbitrary non-germline pipeline** — it still
         only accepts one whose declared outputs are germline-shaped; it stops the wrong-but-runs and
         runs-then-dies failure modes, honestly, rather than solving general parsing. Runs an
         operator-**authored, approved** pipeline when `SubmitRunIn.pipeline`
         names one (else the committed reference, byte-preserved), via the shared
         `api/authored_pipeline.py` approval gate (ADR-0021). Processing gate `SubmitRunIn.mode`:
         `immediate`/`hold`/`schedule` + `POST /api/runs/{id}/release` (reviewer/approver) — **a
         time-based auto-release scheduler is a DEFERRED seam; release is manual only** (frozen by a
         regression test, WS-09).
         `GET /api/runs/{id}/intake-status` polls `queued|running|held|scheduled|complete|failed|lost`.
      ii. **Builder-Run `POST /api/pipelines/run`** (`api/routers/pipeline_run.py`, reviewer/approver)
         is **approval-gated (W1)**: it NAMES a saved pipeline (never a raw posted graph —
         `extra="forbid"`), resolves + compiles that pipeline's approver-blessed (`emitted`) snapshot
         (no approved version → **409**, not a silent bypass), then runs it via the same driver. Both
         execution paths share ONE approval gate + ONE compile path (`api/authored_pipeline.py`,
         ADR-0014/0021), distinct from `pipelines_lifecycle.py`'s save→submit→approve flow that mints
         the approval. **Parse-contract parity with intake (2026-07-13, `7cef743`, audit G8/WS-09
         #1):** right after `compile_record`, before the driver launches, this endpoint now also calls
         `check_parse_contract(graph, name)` — the same structural, tool-free frozen-five check item
         4b.i's intake uses — so an approved pipeline whose catalogued nodes can't collectively
         produce the frozen five now 422s at submit instead of running to completion in Nextflow and
         only then dying at parse (a full compute burn for a `failed` run). Test-first, proven
         red-before-impl (a stashed-endpoint rerun: 202 without the check, 422 with it).
      iii. `POST /api/pipelines/compile` (`api/routers/nextflow.py`, stateless): the Builder graph →
         the same bundle as JSON or a `.zip`. `scripts/seed_approved_germline.py` seeds the runnable
         `germline-panel` baseline. Feature routers (settings / review-queue / pipelines-lifecycle:
         save→submit→approve / dry-run / diff) fold into `main.py`.
   b. `frontend/` = React + Vite + Tailwind: 13 operator screens in a three-group nav (Operate —
      incl. Inbox + Accession / Analyze / Configure) + Admin, behind a demo login (T-081, every production
      auth seam labelled NOT implemented). Two **frontend-only** governance capabilities over the wire
      roles — `isAdmin` and page-access (`access.ts`/`AccessContext`) — gate **VIEWS, not the API**:
      **NOT authorization; `require_role` still checks every real write server-side.** Charts via
      recharts 3.9.2 (MIT). Operator custom-script authoring (`CustomScriptInspector`) + a server-side
      `FileBrowser` (over `GET /api/files`). Every off-gate write toasts its real backend outcome and
      routes stakes-y writes through `useConfirm` (no accidental single click fires a cascade).
      Accession/Submit carry subject/tissue **client-side only** — nothing PII-bearing is transmitted
      (`SubmitRunIn`/`SampleIn` are `extra="forbid"`, no subject field; a labelled data-platform seam).
      Design: [design/frontend/](docs/design/frontend/), [design/ui-conventions.md](docs/design/ui-conventions.md).

      **Builder-agent hardening (2026-07-12, ADR-0022).** Agent attachment is now a persisted,
      read-only **observation binding** (`AgentBinding {agent,node,grants}` in a `graph.agent_bindings`
      envelope the compiler NEVER dereferences — byte-identical compile proven) + a scoped,
      **de-identified** node-read endpoint (`GET /api/runs/{id}/nodes/{node}/observations`, `outputs`
      default / `logs` opt-in via `api.deid.scrub_text`; agent-consumption + UI display are labelled
      deferrals). **Access-control honesty (WS-08 interim, 2026-07-12):** the `AgentBinding` is a
      **client-side-only advisory hint — the server does not persist or enforce it** (no server-side
      binding model, no run→executed-graph linkage); real, server-enforced access is by node scope
      (real) plus **wire role**, not the binding (`outputs` stays viewer+, the PII-adjacent `logs`
      grant now requires **reviewer+**, closing a hole where any viewer could read any node's log
      tail). System agents (pipeline-repair, archivist) moved off the Builder palette →
      Agent-triage; the Builder keeps node-attachable QC-triage + node-authoring. Every Builder port
      now maps to a **real Nextflow channel or is removed** (reserved-port honesty; `fastp adapter_fasta`
      the sole left-reserved). Plus compiler hardening (injection escaping + validators, `is_source`
      data-kind fix, collision/fan-in/dup-emit/port-drift `CompileError`s), the mosdepth Export-422 fix,
      and **`tsc -b` in pre-push**. Details: [ADR-0022](docs/adr/ADR-0022-agent-observation-binding.md),
      [design/agents.md](docs/design/agents.md); narrative in [HISTORY.md](docs/HISTORY.md).

      **Scope-by-wiring, server-enforced (ADR-0024, built 2026-07-13, superseding the "documented
      deferral" line above).** `api/agent_binding_store.py` (jsonl/sqlite) snapshots a run's
      **executed-graph** agent bindings at launch, so `GET .../nodes/{node}/observations?agent=X`
      really 403s an agent not wired to `node` and caps its grants to the binding — enforcement, not
      just an advisory hint. Shipped first for Builder-Run (`api/routers/pipeline_run.py`).
      **T-148 (PR #10, 2026-07-13) closes the intake half of ADR-0024's own deferred list:**
      `api/routers/intake.py::submit_run` now also calls `agent_binding_store.record()` at submit —
      an authored-pipeline intake run snapshots its real bindings, and the default germline
      reference (which carries none) still snapshots an EMPTY set, so even an unbound intake run
      403s an unwired `?agent=` request rather than going silently unenforced (previously: zero
      enforcement on every intake-launched run). **Still deferred:** a real triage consumer
      (`gather_node_observations` → `triage/agent.py` never calls it today) and the automatic
      `?agent=` pass (nothing populates the query param from a caller's identity yet).
      [ADR-0024](docs/adr/ADR-0024-scope-by-wiring.md).
   c. `deploy/` — a containerized read-API + built frontend (T-041, PR #13, 2026-07-13, **Docker
      only** — Terraform/IaC dropped per the maintainer, no cloud target shipped). `Dockerfile.api`:
      a multi-stage build (stage 1 `node:22-bookworm-slim` builds the Vite SPA; stage 2
      `python:3.14-slim-bookworm` runs `uv sync --frozen --no-dev --extra api` off the committed
      lock, then `uvicorn api.main:app`), serving the read-API and the compiled SPA same-origin from
      ONE container. `api/main.py` is container-ready with defaults that preserve today's offline
      behavior: `DATA_ROOT` resolves via the existing `bayleaf.settings.run_store_root()`
      (`BAYLEAF_DATA_ROOT`, else the repo's committed `data/`), CORS reads `BAYLEAF_CORS_ORIGINS`
      (comma-separated, defaults to the two `:5173` dev hosts), and a guarded
      `StaticFiles(html=True)` mount serves `frontend/dist` at `/` only when that dir exists
      (present in the image, absent in dev/tests). `docker-compose.yml` adds a standalone `app`
      service alongside the pre-existing `deploy/postgres/`/`deploy/telemetry/` bundles. Verified: a
      `docker build` + a running container served `/api/health` (200), `/api/runs` (from the
      mounted `data/`), and `/` (SPA index, 200) with CORS honoring the env override.

## Git conventions

Incremental, self-contained commits; short title + descriptive body. End commit
messages made with Claude Code with a `Co-Authored-By: Claude Opus 4.8
<noreply@anthropic.com>` trailer.
