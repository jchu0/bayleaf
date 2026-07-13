# Architecture — System Shape

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-13 (MST) — the `POST .../ask` advisory endpoint named in the Advisory-agent-reads bullet, with its new `require_role` viewer+ floor |
| **Audience** | software / bioinformatics / reviewers |
| **Related** | [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md), [ADR-0016](../adr/ADR-0016-postgres-port.md), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), [ADR-0018](../adr/ADR-0018-variant-interpretation-advisory-evidence.md), [ADR-0020](../adr/ADR-0020-operator-authored-custom-processes.md), [ADR-0021](../adr/ADR-0021-operator-gated-scheduled-pipeline-processing.md), [schemas.md](../data/schemas.md), [metric_registry.md](../data/metric_registry.md), [qc_metrics.md](../data/qc_metrics.md), [provenance.md](../data/provenance.md), [design/ui-conventions.md](ui-conventions.md), [design/builder-cards/](builder-cards/), [design/node-authoring-agent.md](node-authoring-agent.md), [design/agent-authoring-contract.md](agent-authoring-contract.md), [design/variant-interpretation.md](variant-interpretation.md), [design/nextflow-codegen.md](nextflow-codegen.md), [HISTORY.md](../HISTORY.md) (the dated wave/batch build chronology relocated out of this doc) |

> **Naming.** The product surface is now branded **bayleaf**; the Python package, env vars
> (`PIPEGUARD_*`), and repository stay `pipeguard`. This doc uses "bayleaf" for the product and
> `pipeguard` for the code.

> **Chronology lives in [HISTORY.md](../HISTORY.md).** This doc describes the *current* system
> shape and its honest limits. For "when/why did screen X or seam Y land" (the former
> batch/wave narrative), read HISTORY.md + the linked `docs/journal/` entries.

## Overview

bayleaf is the **operations layer** on top of a bioinformatics pipeline. For each
sample in a sequencing run it recommends **proceed / hold / rerun / escalate** with
**cited evidence**, and an advisory AI agent accelerates triage ("comb the logs" → a
grounded suggestion). The load-bearing invariant: **rules decide; AI narrates and
advises** (ADR-0001). Domain: rare-disease germline DNA panel, Illumina short-read.

## The three-gate model (ADR-0013)

Every finding and verdict is labelled with the gate it came from:

1. **preflight** — intake: barcode/index integrity, sample identity, required metadata,
   pipeline/operational failures ("did we even sequence/produce usable data?").
2. **qc** — per-sample QC: yield/Q30, coverage depth *and* breadth, contamination,
   sample-swap (NGSCheckMate).
3. **variant** — variant-level (DP/GQ/allele balance, gnomAD/ClinVar) — Phase 2.

`RERUN` is reserved for operational/file-system failures; a data-quality problem is a
`HOLD` (surface-and-decide, not prescribe).

## Component map

```
 run dir ─▶ parsers ─▶ RunArtifacts ─▶ rules ─▶ Finding[] ─▶ synthesis ─▶ DecisionCard[]
                                        ▲ │                                   │  │
                    metric registry ────┘ │  (rules normalize each metric to  │  │
                    (canonical decimals,  │   a canonical decimal via the     │  │
                     ON the critical path)│   registry, then gate)            │  │
                                          ├────────▶ provenance: EventLedger ◀─┘  │ (append-only,
                                          │            (analysis_run/finding/       ADR-0002)
                                          │             verdict/notification events)
                            triage agent ─┘  (advisory, off the critical path, ADR-0009)
                                                          │           notify/ ◀────┘
      ┌───────────────────────────────────────────────────┤        (outbound, off by
      ▼                          ▼                         ▼         default, ADR-0010)
 app/ Streamlit           api/ FastAPI  ───────────▶  frontend/ React
 (offline fallback)       (read-API seam, ADR-0010)   (Vite+Tailwind, ADR-0014)
```

1. **Core (`src/pipeguard/`), framework-agnostic.**
   - `parsers` → a typed `RunArtifacts` bundle (tolerant: a missing field is a signal).
   - `metrics` — the **metric registry** (versioned `metric_registry.yaml` + `MetricValue`):
     resolves each source key to a canonical `our_key` and normalizes the value to a canonical
     unit. **ON the QC-gate critical path** (T-024/T-025): `rules` normalizes through it before
     thresholding, so drift in a source's raw unit can't silently move a verdict. See
     [metric_registry.md](../data/metric_registry.md) + [schemas.md](../data/schemas.md) §QC (units contract).
   - `rules` — the trust anchor: computes cited, immutable `Finding`s; never guesses. Gates each
     metric on its **canonical (normalized) value vs a canonical-decimal threshold** keyed on
     `our_key`; a missing field yields no `MetricValue` (a signal, not a crash).
   - `models` — the pydantic data contract; `Finding`/`Evidence` are frozen + content-hashed,
     each `Finding` derives its gate + a rule-version-independent signature.
   - `runbook` — operator-configurable QC thresholds (keyed on `our_key`, canonical decimals) + gate policy.
   - `synthesis` — verdict aggregation (deterministic) + narration (stub or Claude).
   - `identifiers` — UUIDv7 ids, content hashing, UTC time.
   - `nextflow` (T-123) — a pure-text **card-graph → Nextflow (DSL2) compiler**
     (`catalog.py`/`compiler.py`/`germline.py`): compiles a Builder graph into a runnable
     `main.nf`+`modules/*.nf`+`nextflow.config` bundle, never invoking a tool. Realizes
     [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md)'s "Nextflow carries compute
     portability" decision. Robustness-hardened (Groovy/identifier injection escaping, fan-in /
     proc-name-collision / duplicate-emit / catalog-port-drift guards) and extended for
     **operator-authored custom-script processes** (ADR-0020: a non-empty `NfNode.script` renders
     verbatim as a labelled `operator_authored` process, catalog never consulted; a blank script is
     a `CompileError`, never fabricated). See [design/nextflow-codegen.md](nextflow-codegen.md).
2. **Provenance seam (`provenance.py`, ADR-0002).** `run_gate` emits an append-only
   event trail into an `EventLedger` (in-memory + JSONL), anchored to one `AnalysisRun`.
   The event log is authoritative; the relational DB is a rebuildable projection via the
   `Repository` port + `rebuild-db`, selected by `get_repository()` — SqliteRepository *and* a
   guarded, off-by-default PostgresRepository (ADR-0002/0016). A tenth `EventType`,
   `DATA_EXPORTED`, is emitted by the read-API's de-identified share egress (not `run_gate`) into a
   **separate** sink (`api/share_store.py`), merged with the ledger at read time (ADR-0018 D3).
3. **Advisory agents (OFF the deterministic critical path).** Five agents + the narration
   synthesizer = **six AI seams**, each stub-first ($0), lazy `anthropic` import, degrade-to-stub on
   any error (ADR-0006). The full roster + shared invariants live in [agents.md](agents.md):
   1. **QC-triage** (`triage/`) — grounds a `TriageNote` on a flagged card in a curated corpus.
   2. **Pipeline-repair** (`src/pipeguard/pipeline_repair/`) — a recurring cross-run signature →
      a cited, human-reviewed `RepairProposal` (never edits a pipeline, never sets a verdict).
   3. **Archivist** (`api/archivist.py`, off-gate) — released runs → an organizational
      `ArchiveDigest` (no verdict/confidence field by construction).
   4. **Feedback-triage** (`api/feedback_agent.py`, off-gate) — categorizes the in-app feedback corpus.
   5. **Node-authoring** (`src/pipeguard/node_author/`, T-046) — retrieves over a curated
      **9-card** tool corpus (7 germline tools + Reference FASTA + Panel BED) to propose a typed
      `NodeProposal` for the Pipeline Builder palette. A **read-only** `GET /api/builder/node-proposal`
      (W2, T-127) backs the Builder's "Author a tool node" modal. **Accept path is backend-built**
      (T-135): `POST /api/builder/node-proposal/accept` (`reviewer`/`approver`) re-derives the
      proposal server-side, runs it through `node_author.conformance.check_conformance()`
      (mechanically enforces [agent-authoring-contract.md](agent-authoring-contract.md)'s capability
      pins), and stores a `draft` `LibraryEntry` — metadata only, never a runnable command — in
      `api/library_store.py` (`PIPEGUARD_LIBRARY_STORE=jsonl|sqlite`, ADR-0016 item 9). A companion
      `node_author/importer.py` deterministically parses an nf-core `nextflow_schema.json` into a
      proposal for a tool outside the curated corpus (unknown kinds → reserved, never invented).
      **Still deferred, labelled:** the Builder's own "Accept to library" button (no frontend caller
      of the accept/library endpoints yet), the `draft→approved` transition, and the free-text
      `--help`/README half of the importer.
4. **Delivery layers (thin, over the core).** `app/` = Streamlit demo (the guaranteed-working
   offline fallback); `api/` = FastAPI read-API + off-gate writes (ADR-0010/0014/0016); `frontend/`
   = React + Vite + Tailwind consuming the API. **12 operator screens** in a **three-group nav** —
   **Operate** (accession → submit → runs → intake/preflight → decision cards → review queue →
   inbox), **Analyze** (provenance → agent triage → monitoring), **Configure** (pipeline builder →
   settings) — plus an **`isAdmin`-gated Admin** group (`/admin`, off the deterministic gate).
   Everything in this layer is **additive over an untouched core** — sorting, paging, aggregation,
   product writes, the draft→approve authoring lifecycle, and auth all live in `api/`, never
   `src/pipeguard/`. Two frontend-only governance capabilities (`isAdmin`, and a page-access
   view-gate `access.ts`/`AccessContext`) layer over the wire roles; both gate **VIEWS, not API
   authorization** — server-side `require_role` (below) is the only real enforcement. The build
   chronology (batches 2–8, waves 7–12, the P3-backlog + audit + fleet + custom-script sessions) is
   in [HISTORY.md](../HISTORY.md). The current `api/` surface:
   - **Feature-area routers.** New product surfaces live in `api/routers/`
     (`settings`, `review_queue`, `pipelines_lifecycle`, `nextflow`,
     `node_author`, `intake`, `pipeline_run`, `files`) + `api/card_readout.py`, each an `APIRouter`
     mounted via `include_router` — kept out of `main.py` so feature areas evolve independently and
     none mutates a verdict, finding, or ledger event (ADR-0001/0014).
   - **Auth / RBAC primitive (`api/auth.py`).** One shared identity+authorization source for every
     draft→approve flow: `Role` = `viewer` < `reviewer` < `approver` (authorization is *set-
     membership*, not an ordinal compare), the frozen `Actor{id, role}`, `current_actor()` (reads
     `X-PipeGuard-Actor`/`-Role` headers), and `require_role(*roles)` (403s an under-privileged
     caller, else returns the `Actor` so a handler captures `actor.id` into `*_by` audit fields).
     **Honest posture: a documented DEV SHIM, not a production auth boundary** — header-trust is
     permissive (no headers → `Actor(id="dev", role="approver")`), so any client can name itself; a
     one-shot log warns, and `PIPEGUARD_AUTH_STRICT` opt-in defaults the header-less role to
     `viewer`. A real deployment swaps *only* `current_actor()` for a verified IdP returning the
     same `Actor`; every `require_role(...)` gate stays unchanged (a single chokepoint to harden).
     Wholly OFF the gate: gates who may *write* product state, never a verdict/finding/confidence.
   - **Runs read-API.** `GET /api/runs` (+ `/{id}`, `/{id}/cards/{sample}`, `/{id}/artifacts`,
     `/{id}/artifacts/{name}` traversal-hardened download, `/{id}/variants` read-only per-`VariantCall`
     list via the same `parse_variant_calls` the route-to-human rule uses). Each `RunSummary` carries
     `platform` + `run_date` (from the SampleSheet `[Header]`) and an honest run-lifecycle `status`
     (`running`|`needs_review`|`released`, derived from provenance — a run-lifecycle label, NOT a
     per-sample verdict). `GET /api/runs` also has backward-compatible **Tier-0 list params** (bare
     call = byte-identical body): a `status` filter, a platform-aware case-insensitive `q`, a closed
     `sort` vocabulary + aliases, a `verdict` filter, `page`/`limit` pagination, totals + a
     full-set per-status facet count on `X-PipeGuard-*` headers.
   - **Monitoring aggregate.** `GET /api/monitoring?window=&page=&limit=` returns one pre-aggregated
     dashboard payload (fleet KPIs, per-run rows, per-gate flagged/total, ranked recurring
     signatures). `auto_proceed_pct` and each signature's `trend` are **display heuristics**, not
     calibrated probabilities (life-science guardrail 2). `runs[]` is server-side paginated (mirrors
     `GET /api/runs`, closing T-072); the KPI roll-up/per-gate rates/signatures stay whole-window.
     A Median-review-time KPI is a documented, not-yet-built seam.
   - **Off-gate product writes + a draft→approve authoring lifecycle.** `POST /api/feedback` → a
     `FeedbackStore`, plus three product stores carrying an audited, append-only draft→approve
     lifecycle — each pluggable JSONL/SQLite/Postgres (degrade-to-JSONL, DSN never logged), distinct
     from the decision `Repository`, never touching a verdict:
     a. **Pipeline graphs** (`api/routers/pipelines_lifecycle.py`): `submit` → `approve` (records the
        emitted baseline), plus read-only `dry-run` (globs a run dir, `executed` hard-coded `False`,
        traversal-hardened — **compose ≠ execute**) and `diff` (working vs last-emitted baseline).
     b. **Settings / config overrides** (`api/routers/settings.py`): QC-threshold override drafts,
        approver-promotable. **Does NOT mutate the live runbook** — approving records *intent* into an
        override ledger; a lenient sanity envelope rejects only NaN/Inf/negative-gate/out-of-[0,1].
     c. **Review-queue tickets** (`api/routers/review_queue.py`, ADR-0010): a writable HITL worklist
        over already-decided samples — open/acknowledge/escalate/resolve/suppress/reopen ALL
        reviewer+approver; an illegal transition → 409. A ticket snapshots the sample's
        `gate`/`verdict`/`rule_id` at open-time as inert data — never re-enters a decision.
     Across all three, every `*_by` audit field is server-authored from the authenticated `Actor`
     (bodies `extra="forbid"`), and a store failure is a generic 503 that never leaks a path/DSN.
   - **Card QC-readout projection** (`api/card_readout.py`, `GET /api/runs/{id}/cards/{sid}/qc-readout`):
     an API-layer join over an already-decided card — the card's registry-normalized `metric_values`
     × the runbook `QCThreshold`s → a gate-grouped, flagged-first Metric·Observed·Threshold·Status
     table, labelled with the registry `display_name`. Per-metric `status` is derived to **mirror the
     QC rule exactly** so the readout can never contradict the gate; the core `DecisionCard` is
     untouched. `GateReadout.blocked_by` renders a gate blocked by a non-proceed **upstream** gate as
     "blocked · clear \<upstream\> first" (the maintainer's two-tier gate-dependency model) — pure
     re-presentation, `rules.py`/`synthesis/` untouched. (Part 2, user-clearable HOLD/ESCALATE, not yet built.)
   - **Advisory agent reads (off the gate).** Read-only endpoints surface the advisory agents without
     re-entering the core: `GET /api/monitoring/signatures/{signature}/repair` (pipeline-repair's
     cited `RepairProposal`), `GET /api/runs/{id}/archive-digest` + `GET /api/archive/index`
     (archivist's `ArchiveDigest`), `GET /api/builder/node-proposal` (node-authoring). Each formats
     an advisory suggestion over already-decided state — never sets/overrides a verdict. The one
     interactive (POST) advisory surface, `POST /api/runs/{id}/cards/{sample}/ask` (QC-triage's free-text
     sibling to `GET .../triage`, WS-07 Q2), is `require_role("viewer","reviewer","approver")`-gated
     as of 2026-07-13 — the read-family floor (not the write/exec reviewer+ floor, since a question is
     advisory, not a mutation) — closing the one advisory endpoint that had bypassed the auth shim
     entirely.
   - **Intake execution boundary** (`api/routers/intake.py`, T-057). `POST /api/runs` registers a
     submitted samplesheet and triggers the Nextflow-first driver (`scripts/run_giab_pipeline.py`) as
     a background subprocess (409 on a dup run id, reserved atomically under the lock);
     `GET /api/runs/{id}/intake-status` polls `queued|running|complete|failed|lost`. The job registry
     is a durable job store (`api/job_store.py`, `PIPEGUARD_JOB_STORE=jsonl|sqlite`) so a job survives
     a restart (a gone `running` process reconciles to `complete` if its dir is on disk, else `lost`,
     never an eternal spinner); the driver runs in its own process group, reaped with `killpg` on the
     shared `DRIVER_TIMEOUT_S`. **Operator-gated + authored-pipeline processing (ADR-0021):**
     `SubmitRunIn` gains an optional `pipeline` (+`pipeline_version`) — when present, intake resolves
     and compiles that operator-authored, approver-blessed pipeline via the **same approval gate** the
     Builder-Run path uses (factored into `api/authored_pipeline.py`; a name with no approved version
     → 409); absent, it runs the committed `germline-panel` reference (byte-preserved). And a
     processing `mode`: `immediate` (fires the driver now), `hold` (registers WITHOUT firing — an
     operator releases via `POST /api/runs/{id}/release`), or `schedule` (parks with `scheduled_at`;
     time-based auto-release is a DEFERRED seam — release is manual today).
   - **Pipeline-Builder Run (`api/routers/pipeline_run.py`, W1, ADR-0014).** `POST /api/pipelines/run`
     (`require_role("reviewer","approver")`) is **approval-gated**: the body NAMES a saved pipeline
     (never a raw posted graph — `extra="forbid"` 422s a smuggled `graph`), and the endpoint resolves
     + compiles that pipeline's approver-blessed (`emitted`) snapshot from `PipelineGraphStore` (a name
     with no approved version → 409, not a silent bypass), then runs it via the same Nextflow driver
     (202 + `GET /api/pipelines/run/{id}` poll). The Builder's `RunPipelineModal` is a picker over the
     APPROVED stored pipelines, defaulting to the seeded `germline-panel` baseline
     (`scripts/seed_approved_germline.py`).
   - **Nextflow compile (`api/routers/nextflow.py`, T-123).** `POST /api/pipelines/compile`
     (stateless/off-gate) compiles a Builder graph → the same bundle as JSON (preview) or a `.zip`,
     surfaced by the Builder's "Export to Nextflow" button; a cycle/bad/empty/blank-custom-script
     graph 422s with the compiler's reason. Never persists, never runs Nextflow.
   - **Sandboxed file browser (`api/routers/files.py`, ADR-0020's Branch B).** `GET /api/files?root=&path=`
     lists one directory level under an **allowlisted** root (`PIPEGUARD_BROWSE_ROOTS`, default
     `{"data": <repo>/data}`) — metadata only (name/size/ext-inferred kind), never file bytes;
     traversal-hardened (`..`/absolute → 400, an escaping symlink → 403, unknown root/missing dir →
     404), any authenticated role. Powers the Builder's custom-script `FileBrowser.tsx` "Browse…" picker.
5. **Outbound notify seam (`notify/`, ADR-0010).** An optional `run_gate(notifier=…)` hook turns each
   *actionable* card (HOLD/RERUN/ESCALATE; clean cards skipped) into a notification tailored per
   verdict category, with cited observed-vs-expected evidence. Like every other seam it **formats
   what the gate decided, never a verdict** (ADR-0001): stub-first ($0, in-memory), with Slack /
   Teams / Discord adapters all off by default — each armed only by its OWN live flag
   (`PIPEGUARD_SLACK_LIVE` / `PIPEGUARD_TEAMS_LIVE` / `PIPEGUARD_DISCORD_LIVE`, the webhook pair also
   needing `PIPEGUARD_{TEAMS,DISCORD}_WEBHOOK_URL`) — and every send recorded as a
   `notification.emitted` ledger event. `python -m pipeguard.notify <run_dir>` is the CLI.

## Data flow

`load_run` → `evaluate_run` (rules **normalize each metric through the registry**, then →
`Finding[]` per sample) → `run_gate` (synthesize each sample → `DecisionCard`; emit the event
trail; anchor cards to the `AnalysisRun`; optionally dispatch actionable cards through an injected
`notifier`) → the FastAPI read-API serves cards + events + config → the React frontend renders
them. The triage, pipeline-repair, and archivist agents are invoked on demand and never re-enter
the verdict path. The read-API shapes cards for screens without re-entering the core: it labels
each run with an honest lifecycle `status` from provenance, filters/sorts/paginates the run list,
and pre-aggregates the monitoring roll-up. The Pipeline Builder's save/version writes, the whole
draft→approve authoring lifecycle (pipeline graphs, config-threshold overrides, review-queue
tickets), the intake/Builder-run job bookkeeping, and the per-card QC-readout are all API-layer
joins/writes over already-decided state, RBAC-gated by the `api/auth.py` dev shim — none re-enters
the deterministic path, and an approved config override records intent without mutating the live runbook.

## Invariants

1. **Rules decide; AI is advisory** — never sets/overrides a verdict or confidence (ADR-0001).
2. **AI is OFF by default** with a deterministic fallback; all six AI seams (synthesizer, QC-triage,
   feedback-triage, pipeline-repair, archivist, node-authoring) flip via env, $0 by default (ADR-0006).
3. **Event log is authoritative**; the DB is a disposable, rebuildable projection (ADR-0002).
4. **Core stays framework-agnostic** — no Streamlit/FastAPI/React imports in `src/pipeguard/`; ports & adapters (ADR-0003).
5. **Findings are immutable + content-hashed**; confidence is omitted until grounded.
6. **Off-gate product state never re-enters the gate** — in-app feedback, saved Pipeline Builder
   graphs, config-threshold overrides, and review-queue tickets are written by dedicated `api/` seams
   to their own stores (each distinct from the decision `Repository`); no product write becomes a
   verdict, finding, or authoritative ledger event, and an approved config override never mutates the
   live runbook (ADR-0001).
7. **Auth is a swappable dev shim, off the gate** — `api/auth.py` is the one shared RBAC source
   (`viewer`/`reviewer`/`approver`) for every draft→approve flow, but its header-trust
   `current_actor()` is a permissive DEV SHIM, **not** a production auth boundary; it gates who may
   *write* product state and never touches a verdict/finding/confidence. Hardening = swapping that
   single function for a verified identity provider (ADR-0010/0017).
8. **Off-gate writes are explicit and audited** — no single accidental click may fire a
   cascading/state-changing write. A reusable confirm gate (`frontend/src/components/ConfirmDialog.tsx`,
   `ConfirmProvider`/`useConfirm()`) requires a named confirmation before a stakes-y off-gate write
   fires; low-stakes/non-destructive actions stay direct one-clicks. This is the frontend-UX
   realization of the audit guarantee ADR-0017 already requires server-side (ADR-0017 realized addendum).
9. **Compose ≠ execute** — the core (`src/pipeguard/`, incl. the Nextflow compiler) never runs a
   tool. Only out-of-core drivers (`scripts/run_giab_pipeline.py`) and the API layer (`intake.py`,
   `pipeline_run.py`) shell out to Nextflow, and only inside a saved+approved pipeline for an
   operator-authored custom script (ADR-0003/0020). PipeGuard transcribes an operator's custom
   command verbatim — it never authors or vets it.

## Swappable seams (the flex points)

| Seam | Switch | Default |
|---|---|---|
| Synthesizer (narration) | `PIPEGUARD_SYNTHESIZER=stub\|claude` | stub ($0) |
| Triage agent | `PIPEGUARD_TRIAGE_AGENT=stub\|claude` | stub ($0) |
| Feedback-triage agent (off-gate) | `PIPEGUARD_FEEDBACK_AGENT=stub\|claude` (`_MODEL`); advisory categorization of the in-app feedback corpus (`api/feedback_agent.py`) | stub ($0) |
| Pipeline-repair agent (advisory) | `PIPEGUARD_PIPELINE_REPAIR_AGENT=stub\|claude` (`_MODEL`, default Opus-high); cross-run remediation over a recurring signature (`src/pipeguard/pipeline_repair/`) | stub ($0) |
| Archivist agent (off-gate) | `PIPEGUARD_ARCHIVIST_AGENT=stub\|claude` (`_MODEL`, default Haiku); organizational digest over released runs (`api/archivist.py`) | stub ($0) |
| Node-authoring agent (advisory) | `PIPEGUARD_NODE_AUTHOR_AGENT=stub\|claude` (`_MODEL`, default Sonnet); retrieves a `NodeProposal` over a curated **9-card** tool corpus (`src/pipeguard/node_author/`, T-046). Read endpoint `GET /api/builder/node-proposal` + Builder wiring shipped (W2); `POST /api/builder/node-proposal/accept` → library store shipped (T-135, backend-only). See [agent-authoring-contract.md](agent-authoring-contract.md) | stub ($0) |
| Tool-card library store (off-gate product) | `PIPEGUARD_LIBRARY_STORE=jsonl\|sqlite` (`api/library_store.py`, T-135); accepted `NodeProposal`s as versioned `draft` `LibraryEntry` records, gated through `check_conformance()` at accept time. **No Postgres by design** — node-local corpus, not shared product state (ADR-0016 item 9) | JSONL |
| Sandboxed file browser (off-gate, read) | `GET /api/files?root=&path=` (`api/routers/files.py`, ADR-0020); one directory level under an ALLOWLISTED root (`PIPEGUARD_BROWSE_ROOTS`, default `{"data": <repo>/data}`) — metadata only, traversal-hardened; any authenticated role | allowlisted `data/` only |
| Notify (outbound) | `PIPEGUARD_NOTIFIER=stub\|slack\|teams\|discord`; each adapter armed by its OWN `PIPEGUARD_{SLACK,TEAMS,DISCORD}_LIVE=1` (Teams/Discord also need `_WEBHOOK_URL`) | stub ($0, no network) |
| Metric registry (normalization) | versioned `metric_registry.yaml` + `our_key` mapping — add/remap a source metric without touching rules | canonical decimals; ON the critical path |
| Repository (persistence) | `Repository` port; SqliteRepository **and** guarded PostgresRepository built (ADR-0016), `get_repository()` selects | SQLite + JSONL (Postgres off by default) |
| Artifact store (staging) | `PIPEGUARD_ARTIFACT_STORE=local\|s3` (`src/pipeguard/artifacts/`); S3 adapter OFF by default (lazy `boto3`, degrade-to-local), realized + tested; entry `run_gate_from_store` (ADR-0003) | `local` |
| Feedback sink (off-gate) | `FeedbackStore` port (`api/feedback_store.py`); jsonl/sqlite/postgres, degrade-to-JSONL (ADR-0016) | JSONL |
| Pipeline-graph store (off-gate product) | `PIPEGUARD_PIPELINE_STORE=jsonl\|sqlite\|postgres` (`api/pipeline_store.py`); degrade-to-JSONL, never logs the DSN (ADR-0016) | JSONL |
| Settings-override store (off-gate authoring) | `PIPEGUARD_SETTINGS_STORE=jsonl\|sqlite\|postgres` (`api/settings_store.py`); records intent, **never mutates the live runbook** (ADR-0001/0016) | JSONL |
| Review-queue store (off-gate product) | `PIPEGUARD_REVIEW_STORE=jsonl\|sqlite\|postgres` (`api/review_store.py`); ticket lifecycle over already-decided samples (ADR-0010/0016) | JSONL |
| Share sink (off-gate egress) | `PIPEGUARD_SHARE_STORE=jsonl\|sqlite\|postgres` (`api/share_store.py`, ADR-0018 D3); the de-identified share/`DATA_EXPORTED` ledger, separate from the gate's `EventLedger`; degrade-to-JSONL | JSONL |
| Durable job store (off-gate execution bookkeeping) | `PIPEGUARD_JOB_STORE=jsonl\|sqlite` (`api/job_store.py`, T-131); intake/Builder-run jobs survive a restart (`lost` if no result dir, else `complete`). **No Postgres by design** — node-local scratch (ADR-0016 item 8). Hosts the shared, `killpg`-reaped `run_driver()` + the atomic dup-run-id reservation | JSONL |
| Auth / identity (off-gate) | `api/auth.py` `current_actor()` header-shim (`X-PipeGuard-Actor`/`-Role`) → swap for a verified IdP (OIDC / signed JWT) returning the same `Actor`; downstream `require_role(...)` unchanged (ADR-0010/0017) | permissive dev shim (`id=dev`, `role=approver`) |
| Pipeline codegen (compose, never execute) | `pipeguard.nextflow.compile_graph()` — a card graph → Nextflow bundle; `POST /api/pipelines/compile` (JSON/`.zip`); curated catalog, uncatalogued tool → a labelled placeholder. **Operator-authored custom-script processes (ADR-0020)** are a third path: a non-empty `NfNode.script` renders verbatim (catalog never consulted); a blank script is a `CompileError`; reaches a compute host only behind the W1 `POST /api/pipelines/run` approval gate ([nextflow-codegen.md](nextflow-codegen.md), T-123) | pure text codegen, no execution |
| Intake execution driver | `scripts/run_giab_pipeline.py`, triggered by `POST /api/runs`; **Nextflow-first** — runs `pipelines/germline/main.nf` via `nextflow run`. Pre-flight-guarded (FASTQ pairing/format, reference↔panel-BED contig naming, reference-index sidecars — loud `sys.exit` before launch) + per-run `versions.txt` capture (T-131). Post-run parse is **N-sample capable** (offline-verified vs fixture publish dirs) but the driver still submits a single-row (HG002-only) samplesheet — a live multi-sample run stays unverified. Now optionally runs an **operator-authored approved pipeline** by name + supports hold/schedule/release (ADR-0021) | local `-profile conda`/`standard`, HG002-fixture-scoped |
| Deployment | ports & adapters; Nextflow now **executable** for local compute; a `slurm` executor profile exists (env-driven, auto-selected on `sbatch`) but is CONFIG-verified not CLUSTER-verified; AWS-Batch/HealthOmics executor config stays wishlist (ADR-0003) | local |

Unlike the AI/notify seams (off by default, adapter-swapped at the edge), the **metric registry is
on the critical path** — its "flex" is that new tool keys or unit changes are absorbed by the
versioned YAML/mapping, not by editing `rules`, keeping verdicts byte-identical across the change.

## Deployment

Local today: Streamlit (offline) + FastAPI (`uvicorn`) + React (Vite). The ports-&-adapters boundary
carries portability. **Nextflow (compute) is a realized seam for local execution** — `pipeguard.nextflow`
compiles a card graph into a runnable pipeline and the intake driver runs it for real via `nextflow
run -profile conda`/`standard`. Slurm / AWS Batch / HealthOmics **executor config** for that same
generated pipeline remains wishlist (a `slurm` profile exists but has never run on a real cluster) —
the compute-portability gap left is "point Nextflow at a cluster," not "get Nextflow running at all."
**Storage** portability is likewise realized: the S3 artifact-store adapter is built + tested
(`PIPEGUARD_ARTIFACT_STORE=s3`, off by default; lazy `boto3`, degrade-to-local). The core has no
cloud/DB coupling; **both** repository adapters are built — `SqliteRepository` (default) and a
guarded, off-by-default `PostgresRepository` (ADR-0016, with a `deploy/postgres/docker-compose.yml`
+ a compose-gated live test verified green). IaC remains a Phase-2+ concern.

---

*Marker legend — distinguish claim types where confusion is likely:*
**Fact** · **Assumption** · **Decision** · **TODO**.
