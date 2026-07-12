# CLAUDE.md — bayleaf (PipeGuard)

AI-assisted provenance & QC decision gate for genomics runs (Built with Claude:
Life Sciences hackathon). This file is the self-contained operating contract for
this repo — do not assume any global rules apply here.

**Naming:** the *product* was renamed **bayleaf** (user-facing surface only,
2026-07-11); the Python *package* stays `pipeguard` (`src/pipeguard/`, all
`PIPEGUARD_*` env vars, `X-PipeGuard-*` wire headers) — a package rename is a
separate, breaking, deferred pass. Commands below work verbatim.

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

# Run the dashboard (offline; no API key needed)
uv run streamlit run app/streamlit_app.py   # http://localhost:8501

# Tests (offline — pins the demo scenario)
uv run pytest                               # editable install; no PYTHONPATH shim

# Lint + strict type-check
uv run ruff check && uv run mypy

# Ad-hoc run of the core (no UI)
uv run python -c "from pipeguard import run_gate_from_dir; \
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

**Architecture guardrails**
1. `src/pipeguard/` stays framework-agnostic — no Streamlit/FastAPI imports in the core.
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

## Current code map (current state; updated 2026-07-12)

> Dated wave/batch narrative, superseded detail, and per-commit history →
> [docs/HISTORY.md](docs/HISTORY.md) (git-archived, **not** loaded each session). This is
> current-state only (what exists NOW, per subsystem); the *why* is in the ADRs ([docs/adr/](docs/adr/)).

1. **Core (`src/pipeguard/`) — framework-agnostic (no Streamlit/FastAPI imports).**
   a. `rules` emits cited, immutable `Finding`s (each derives its gate + a rule-version-independent
      signature + `content_hash`); `synthesis/base.py` aggregates the verdict (**never** the LLM,
      ADR-0001); confidence omitted until grounded (T-019). Fraction QC metrics render as percent
      via a registry-backed display conversion (no verdict/hash change).
   b. `models` (pydantic data contract), `identifiers` (UUIDv7 ids + content hashing; `PLATFORM_VERSION`
      from `pyproject.toml`), `runbook` (QC policy).
   c. `runbook.QCThreshold.required` (default `True`, T-082): the richer QC report (13 metrics: the
      frozen five + 8 registered) gates 5 **optional** thresholds (score a present value, never
      NA-flag an absent one) without penalizing a lean real run. Metric catalog = 10 gated / 10
      ungated of 20 registered `our_key`s (`data/metric_registry.md`).
   d. `runbook.RouteToHumanPolicy` + `rules._check_route_to_human` (**VAR-RTH-001**, ADR-0018 D2): a
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
   f. `synthetic/` — the failure-mode data generator incl. `scale.py` (`demo/scale/bulk` CLI, T-050).

2. **Provenance seam (`provenance.py`, ADR-0002).** `run_gate` emits an append-only event trail
   (`analysis_run.started` → per-sample findings/verdict → `completed`) into an `EventLedger`
   (in-memory + JSONL) — the event log is authoritative, the DB a rebuildable projection via
   `persistence/` `get_repository()` (`PIPEGUARD_REPOSITORY=sqlite|postgres`, default SQLite,
   degrade-to-SQLite; SqliteRepository + guarded off-by-default PostgresRepository, ADR-0016);
   `rebuild-db` targets either (ADR-0003). A tenth `EventType` `DATA_EXPORTED` (ADR-0018 D3) is
   emitted by the read-API (not `run_gate`) into a **separate** sink `api/share_store.py` (a
   `ShareStore` Protocol, jsonl/sqlite/postgres via `PIPEGUARD_SHARE_STORE`, degrade-to-JSONL) —
   kept off the gate's `@lru_cache`'d re-derivation because a share is a live side effect that must
   survive a restart; `GET /api/runs/{id}` merges the two at read. Other ports: notify
   (stub/Slack/Teams/Discord, ADR-0010); artifact store (`LocalArtifactStore` + off-by-default
   `S3ArtifactStore`, `PIPEGUARD_S3_LIVE`). Multi-worker locking on the off-gate stores is a
   documented seam, not built (ADR-0016).

3. **Swappable AI, OFF by default (ADR-0006 deterministic fallback; ADR-0009/0012 scoping/tiering).**
   Six `stub|claude` seams, all stub-first ($0), lazy `anthropic` import, fall back to the stub on
   any error (incl. a safety refusal); models via `PIPEGUARD_*_MODEL`. Five are one-liners:
   a. synthesizer (`PIPEGUARD_SYNTHESIZER`); b. QC-triage (`triage/`, `PIPEGUARD_TRIAGE_AGENT`);
   c. pipeline-repair (`pipeline_repair/`, `PIPEGUARD_PIPELINE_REPAIR_AGENT`, Opus-high; recurring
   signature → cited `RepairProposal`); d. feedback-categorization (`api/feedback_agent.py`,
   off-gate); e. archivist (`api/archivist.py`, off-gate, Haiku; released runs → `ArchiveDigest`).
   The sixth:
   f. node-authoring (`src/pipeguard/node_author/`, `PIPEGUARD_NODE_AUTHOR_AGENT`, Sonnet default): a
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

4. **Delivery layers (thin, over the core).**
   a. `app/` = Streamlit demo (kept as the guaranteed-working fallback).
   b. `api/` = FastAPI read-API + **off-gate writes**. Authz: the dev-shim `api/auth.py` (Role
      viewer|reviewer|approver + `Actor` + `current_actor()` from `X-PipeGuard-Actor/-Role` headers,
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
      `PIPEGUARD_BROWSE_ROOTS` default `data/`, `resolve()`+`is_relative_to()`, read-only, ADR-0020).
      **Execution boundaries (out-of-core — the API triggers an external driver; the core still never
      runs a tool):**
      i. **Intake `POST /api/runs`** (`api/routers/intake.py`, T-057) registers a samplesheet and
         drives Nextflow via `scripts/run_giab_pipeline.py` (`nextflow run pipelines/germline/main.nf`,
         parses published QC into the frozen-five run dir; needs `nextflow` + JRE + bioconda on PATH
         via `PIPEGUARD_BIOCONDA_BIN`). **Verified live on HG002 (local-serial); the multi-sample
         parse is offline-proven vs fixture publish dirs but a live multi-sample run is
         env-gated/unverified (only HG002 has reads); the Slurm profile is config-verified NOT
         cluster-verified.** Runs an operator-**authored, approved** pipeline when `SubmitRunIn.pipeline`
         names one (else the committed reference, byte-preserved), via the shared
         `api/authored_pipeline.py` approval gate (ADR-0021). Processing gate `SubmitRunIn.mode`:
         `immediate`/`hold`/`schedule` + `POST /api/runs/{id}/release` (reviewer/approver) — **a
         time-based auto-release scheduler is a DEFERRED seam; release is manual only**.
         `GET /api/runs/{id}/intake-status` polls `queued|running|held|scheduled|complete|failed|lost`.
      ii. **Builder-Run `POST /api/pipelines/run`** (`api/routers/pipeline_run.py`, reviewer/approver)
         is **approval-gated (W1)**: it NAMES a saved pipeline (never a raw posted graph —
         `extra="forbid"`), resolves + compiles that pipeline's approver-blessed (`emitted`) snapshot
         (no approved version → **409**, not a silent bypass), then runs it via the same driver. Both
         execution paths share ONE approval gate + ONE compile path (`api/authored_pipeline.py`,
         ADR-0014/0021), distinct from `pipelines_lifecycle.py`'s save→submit→approve flow that mints
         the approval.
      iii. `POST /api/pipelines/compile` (`api/routers/nextflow.py`, stateless): the Builder graph →
         the same bundle as JSON or a `.zip`. `scripts/seed_approved_germline.py` seeds the runnable
         `germline-panel` baseline. Feature routers (settings / review-queue / pipelines-lifecycle:
         save→submit→approve / dry-run / diff) fold into `main.py`.
   c. `frontend/` = React + Vite + Tailwind: 12 operator screens in a three-group nav (Operate /
      Analyze / Configure) + Admin + Inbox + Accession, behind a demo login (T-081, every production
      auth seam labelled NOT implemented). Two **frontend-only** governance capabilities over the wire
      roles — `isAdmin` and page-access (`access.ts`/`AccessContext`) — gate **VIEWS, not the API**:
      **NOT authorization; `require_role` still checks every real write server-side.** Charts via
      recharts 3.9.2 (MIT). Operator custom-script authoring (`CustomScriptInspector`) + a server-side
      `FileBrowser` (over `GET /api/files`). Every off-gate write toasts its real backend outcome and
      routes stakes-y writes through `useConfirm` (no accidental single click fires a cascade).
      Accession/Submit carry subject/tissue **client-side only** — nothing PII-bearing is transmitted
      (`SubmitRunIn`/`SampleIn` are `extra="forbid"`, no subject field; a labelled data-platform seam).
      Design: [design/frontend/](docs/design/frontend/), [design/ui-conventions.md](docs/design/ui-conventions.md).

## Git conventions

Incremental, self-contained commits; short title + descriptive body. End commit
messages made with Claude Code with a `Co-Authored-By: Claude Opus 4.8
<noreply@anthropic.com>` trailer.
