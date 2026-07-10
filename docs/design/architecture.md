# Architecture — System Shape

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-09 (MST) |
| **Audience** | software / bioinformatics / reviewers |
| **Related** | [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md), [ADR-0016](../adr/ADR-0016-postgres-port.md), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), [schemas.md](../data/schemas.md), [metric_registry.md](../data/metric_registry.md), [provenance.md](../data/provenance.md), [journal 2026-07-09 frontend-batch2](../journal/2026-07-09-frontend-batch2.md), [journal 2026-07-09 frontend-batch3](../journal/2026-07-09-frontend-batch3.md) |

## Overview

PipeGuard is the **operations layer** on top of a bioinformatics pipeline. For each
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
2. **Provenance seam (`provenance.py`, ADR-0002).** `run_gate` emits an append-only
   event trail into an `EventLedger` (in-memory + JSONL), anchored to one `AnalysisRun`.
   The event log is authoritative; the relational DB is a rebuildable projection via the
   `Repository` port + `rebuild-db`, selected by `get_repository()` — SqliteRepository *and* a
   guarded, off-by-default PostgresRepository (ADR-0002/0016).
3. **Advisory agents (OFF the deterministic critical path).** The QC-triage agent (`triage/`,
   ADR-0009/0012) grounds a `TriageNote` in a curated corpus; the pipeline-repair agent
   (`src/pipeguard/pipeline_repair/`, ADR-0009/0012) turns a recurring cross-run signature into a
   cited, human-reviewed `RepairProposal` (never edits a pipeline, never sets a verdict); the
   off-gate feedback-triage agent (`api/feedback_agent.py`, ADR-0016) categorizes the in-app
   feedback corpus; and the off-gate archivist (`api/archivist.py`) rolls up released runs into an
   advisory `ArchiveDigest` (an organizational index — no verdict/confidence field by construction).
   All are stub-first ($0), import `anthropic` lazily, and fall back to the stub on any error.
4. **Delivery layers (thin, over the core).** `app/` Streamlit (offline demo / fallback);
   `api/` FastAPI — the production read-API seam (ADR-0010/0014/0016); `frontend/` React —
   **rebuilt to the refreshed design prototype** (`docs/design/frontend/`, 2026-07-09, Waves 1–3),
   then extended the same day by a maintainer feedback batch (commits `e891e62`→`6371128`,
   [journal](../journal/2026-07-09-frontend-batch2.md)) that added an admin panel, wired the
   previously-broken product writes to their real endpoints, and closed several per-screen
   fidelity gaps. **10 operator screens** in a **three-group nav** — **Operate** (submit
   samplesheet → runs → intake/preflight → decision cards → review queue), **Analyze**
   (provenance → agent triage → monitoring), **Configure** (pipeline builder → settings) — plus
   an **approver-gated Admin** group (`/admin`, off the deterministic gate; see below). A shared
   `RoleContext` (reviewer|approver, a `DecisionCard` carries `run_id`) now also exposes a full
   **`setActor(actor)`** (id + role together, not just a role toggle) so Admin's "Act as" can
   preview any seeded actor's RBAC view. The **Pipeline Builder** also realizes free composition
   (palette-add/drag/delete user nodes), a typed-port **Connect mode** (kind-matched, INV-e), a
   minimap, and editable Locators with live `run_layout.yaml` regen.
   - **Frontend fixes batch 3 (2026-07-09, commits `e5d5043`→`01ba673`, [journal](../journal/2026-07-09-frontend-batch3.md)),
     four maintainer-reported gaps closed.** (1) **Submit is a real execution boundary, not
     registration-only** (T-057, `e77c2e6`): new `api/routers/intake.py` — `POST /api/runs`
     registers a submitted samplesheet and triggers `scripts/run_giab_pipeline.py` as a
     background subprocess (in-process job registry, `require_role(reviewer|approver)`, 409 on a
     dup run id, HG002-fixture-scoped with the rest honestly *skipped*, not fabricated), `GET
     /api/runs/{id}/intake-status` polls `queued|running|complete|failed`; `Submit.tsx` submits →
     polls → navigates to the new run's cards. **Compose ≠ execute still holds at the core** —
     `src/pipeguard/` never runs a tool; the API layer now triggers the external driver, exactly
     like the Builder's hand-off concept, but wired. (2) **Decision card: honest three-gate
     readout** (T-073, `12ffa30`): `GET /api/runbook`'s `RunbookThreshold` gains `pipeline_gate`
     (from the metric registry), distinct from the numeric `gate` value the frontend had been
     mistyping as the gate enum (so the preflight/variant groups silently never matched and
     vanished); the card now always shows all three gates — real metric rows, else a
     `not_measured` runbook placeholder, else an honest empty-state note (preflight is
     rule-based; variant extracts no metrics this build) — never a fabricated row, gate
     byte-for-byte unchanged. (3) **Top bar run switcher + F17 fix** (T-074, `17a3e56`): the flat
     run dropdown is now a searchable, 8-row-capped combobox (search by id/platform, "view all"
     footer); a shared `RUN_STATUS_META` (`verdict.ts`) now drives both the Runs list and the
     switcher's dots off the run's real lifecycle `status`, fixing a bug (F17) where the
     switcher's dot read `n_attention` and showed a running run with 0 flagged samples as a
     green "all clear." (4) **Pipeline Builder: germline template is now an editable draft**
     (T-075, `01ba673`): "New → From template" previously re-showed the read-only seeded DAG;
     `germlineTemplate()` now instantiates the same chain as real `UserNode`/`UserEdge`s, and
     `showSeeded` is gated on `isLinked` so only the original linked pipeline stays read-only —
     Save now sends the true composed graph. A fifth, smaller fix: **Monitoring's
     recurring-signatures list is now client-side paginated** (25/50/100 + pager, `e5d5043`,
     mirroring the Runs-list pattern) — distinct from the still-open per-run `rows` pagination
     gap ([tasks T-072](../planning/tasks.md)).
   - **Admin (`screens/Admin.tsx`), approver-gated governance off the gate.** Three tabs: **Users
     & roles** — an explicit **client-mock** roster (there is no backend user store; `api/auth.py`
     is a header dev-shim) with a role selector and "Act as" wired to `RoleContext.setActor`, plus
     a persistent "dev auth shim, not an identity system" banner; **Activity log** — a REAL,
     zero-new-backend audit feed merging `listThresholds` + `listPipelines` + `listTickets` into
     one append-only when/actor/kind/target/status table, facet-filterable by kind; **System** —
     REAL reads of `GET /api/health` + runbook gate count + metric-registry version/gated-count,
     labelled illustrative-not-clinical. Admin decides WHO may perform an off-gate product write
     and whose id lands in an audit field — it never sets, overrides, or displays a
     verdict/finding/confidence (ADR-0001; no confidence meter).
   - **Off-gate writes now round-trip, not just compose.** A new `Toast` system
     (`components/Toast.tsx`, `ToastProvider` mounted in `App.tsx`) surfaces the real backend
     outcome (403/409/422/503/…) of every product write instead of silently diverging. Three
     previously broken/optimistic write paths were fixed and now **await + reconcile local state
     from the response**: (a) Settings threshold save/approve — the frontend now **slugifies** the
     override name before POSTing (the display assay string's spaces/colon failed the backend's
     `^[A-Za-z0-9][A-Za-z0-9._-]*$` slug pattern, so save 422'd and approve 404'd); (b) Pipeline
     Builder Save now chains `savePipeline` → `submitPipeline` (draft → pending_review) so
     Approve's `pending_review` precondition is met (previously 409'd) — Save/Approve both await
     the response, reconcile local `version`/`status`, and toast success/failure; (c) review-queue
     **resolve/suppress RBAC relaxed** from approver-only to **reviewer+approver**
     (`api/routers/review_queue.py` `_ACTION_RULES`, matching the design's reviewer-resolves-
     hold/rerun-ticket model — an escalate ticket's approver-only nuance stays a UI-level
     distinction, not this backend gate). **Still a known, labelled limitation:** the Builder's
     **Dry-run/Diff remain a client-side-only projection** (`BuilderConsole`/`BuilderShared`) —
     `api.ts`'s `dryRunPipeline`/`pipelineDiff` exist but the Builder screen does not call them
     yet.
   **Honest, labelled frontend deferrals (no fabrication):** the Monitoring **Median-review KPI**
   (no backend field yet — the signature-level `first_seen`/`last_seen`/`trend`/`affected_run_ids`
   fields below ARE shipped); Provenance artifact links (`RunArtifact` has no `url`); Submit now
   hands off to a real execution boundary (`POST /api/runs`, T-057 — see below) but still has
   **no BaseSpace connector** and no conversational multi-turn triage chat (both still wishlist);
   Builder Dry-run/Diff/Export/Archivist-modal wiring + saved-profiles (endpoints exist, UI is a
   preview). Of the 10 operator screens: 8 (Runs, Intake, Decision cards, Review queue,
   Provenance, Agent triage, Monitoring, Settings) trace to the pre-refresh [T-022b](../planning/tasks.md)
   1:1 fidelity pass, Pipeline Builder to [T-044](../planning/tasks.md), and Submit was new in the
   T-062 rebuild; Admin (governance, not counted among the 10) is new in this batch.
   The `api/` surface (all additive / backward-compatible; the core is untouched — sorting,
   paging, aggregation, product writes, the draft→approve authoring lifecycle, and auth all live
   in `api/`, never `src/pipeguard/`):
   - **Feature-area routers (additive modularization).** New product surfaces live in `api/routers/`
     (`settings`, `review_queue`, `pipelines_lifecycle`) + `api/card_readout.py`, each an
     `APIRouter` mounted into `api/main.py` via `include_router` — kept **out of** `main.py` so
     feature areas evolve independently. Purely additive: the existing `main.py` endpoints are
     unchanged, each router computes its own data root / pulls its store via a factory (import-
     isolated, unit-testable on a bare app), and none mutates a verdict, finding, or ledger event
     (ADR-0001/0014).
   - **Auth / RBAC primitive (`api/auth.py`).** One shared identity+authorization source for every
     draft→approve flow: `Role` = `viewer` < `reviewer` < `approver` (authorization is *set-
     membership*, not an ordinal compare), the frozen `Actor{id, role}` principal, `current_actor()`
     (reads the `X-PipeGuard-Actor` / `X-PipeGuard-Role` headers), and `require_role(*roles)` — a
     dependency that 403s an under-privileged caller and otherwise **returns the `Actor`** so a
     handler gets identity + authz from one dependency (and captures `actor.id` into `*_by` audit
     fields). **Honest posture: this is a documented DEV SHIM, not a production auth boundary.**
     Header-trust is permissive (no headers → `Actor(id="dev", role="approver")`) so the offline
     demo and existing tests run with zero auth wiring — any client can name itself. A real
     deployment swaps *only* `current_actor()` for a verified identity provider (session / OIDC /
     signed JWT) returning the same `Actor`; every `require_role(...)` gate and `actor.id` capture
     keeps working unchanged (a single chokepoint to harden). Wholly OFF the gate: it can gate who
     may *write* product state, never a verdict / finding / confidence / rule (ADR-0001).
   - **Runs read-API.** `GET /api/runs` (+ `/{id}`, `/{id}/cards/{sample}`, `/{id}/artifacts`).
     Each `RunSummary` now carries `platform` + `run_date` (parsed from the SampleSheet
     `[Header]`) and an **honest run-lifecycle `status`** — `running` | `needs_review` |
     `released`, derived from provenance (`_run_status`): `running` until the run's
     `ANALYSIS_RUN_COMPLETED` event lands, then `needs_review` if any sample is actionable, else
     `released`. It is a run-lifecycle label, **NOT** a per-sample verdict (ADR-0001), and fixes
     a bug that mislabeled a still-running / 0-attention run *Released*. `GET /api/runs` also
     gained backward-compatible **Tier-0 list params** (bare call = byte-identical body): a
     `status` filter on the run-lifecycle label (`running`|`needs_review`|`released`, unknown →
     400); a **platform-aware, case-insensitive `q`** substring matching `run_id` OR `platform`
     (so `novaseq` matches a `NovaSeq` platform); a closed `sort` vocabulary
     ({`run_id`,`run_date`,`n_samples`,`n_attention`}, each with a `-` desc variant) plus friendly
     **aliases** (`recent`/`urgent`/`date`) the design UI binds to; a `verdict` filter; and
     `page`/`limit` pagination (applied only when `limit` is given). Totals + the active page/limit
     ride `X-PipeGuard-*` response headers, and a **per-status facet count** (`X-PipeGuard-Status-
     Counts`) is computed over the *full unfiltered* set so the All/Needs-review/Sequencing/Released
     chips show totals independent of the active filter + page.
   - **Monitoring aggregate.** `GET /api/monitoring?window={7d|14d|30d|all}` returns one
     pre-aggregated dashboard payload (fleet KPIs, per-run rows, per-gate flagged/total, ranked
     recurring signatures) so the frontend renders from a single response instead of fanning out
     a detail fetch per run. Its `auto_proceed_pct` is a **heuristic** throughput ratio — a
     display number, not a calibrated probability (life-science guardrail 2). Aggregation
     reuses `_aggregate_metrics()` and stays in the API layer. Each `MonitoringSignature` now
     ADDITIVELY carries `first_seen`/`last_seen` (earliest/latest `[Header]` date of a run
     carrying the signature, `None` when every carrying run is undated — never fabricated),
     `trend` (a coarse up/down/flat glyph, recent-vs-older window half by occurrence count — a
     **display heuristic**, not a calibrated rate), and `affected_run_ids` (the distinct,
     chronological run ids); the payload stays backward-compatible (fields default). The
     signature grid renders the date range + a trend arrow, and affected-run chips deep-link to
     `/runs/:id?filter=attention`. A **Median-review-time** KPI is a documented, not-yet-built
     seam — every review-ticket action carries an ISO `at` and the ticket a `created_at`, but the
     Monitoring aggregate does not yet compute the KPI from them.
   - **Off-gate product writes + a draft→approve authoring lifecycle.** `POST /api/feedback` → a
     pluggable `FeedbackStore`, plus **three product stores** that now carry an audited, append-only
     draft→approve lifecycle — each pluggable JSONL / SQLite / Postgres (degrade-to-JSONL, DSN never
     logged), **distinct from the decision `Repository`** and never touching a verdict:
     a. **Pipeline graphs** (`POST`/`GET /api/pipelines` + lifecycle in `api/routers/pipelines_lifecycle.py`):
        `submit` (draft→pending_review, reviewer/approver) → `approve` (→approved, approver-only,
        which records the emitted baseline), plus two read-only inspectors — `dry-run` (resolve the
        graph's run-layout locators against a real run dir → `matched`|`ambiguous`|`missing`|`invalid`
        + resolved *relative* paths) and `diff` (working vs last-emitted baseline). Dry-run is
        **READ-ONLY: compose ≠ execute** — it globs the filesystem (traversal-hardened: absolute /
        `..` patterns are `invalid`), never triggers a tool or orchestrator hand-off, and its
        `executed` field is a hard-coded `False` (ADR-0001/0003).
     b. **Settings / config overrides** (`api/routers/settings.py`): QC-threshold override drafts saved
        under a name, approver-promotable. **It does NOT mutate the live runbook** — `DEFAULT_RUNBOOK`
        is untouched; approving records *intent* into an override ledger, it does not change how any
        run is gated (a future, documented-not-built step could layer the latest `approved` override
        onto a per-run runbook *copy* at gate time). The payload is a tolerant, versioned envelope
        stored as-is behind a **lenient sanity envelope** (reject only obviously-nonsense numbers —
        NaN/Inf, a negative gate, a band outside [0,1]), never a field-by-field schema match, and its
        illustrative bounds are not clinical ranges (life-science guardrail 3).
     c. **Review-queue tickets** (`api/routers/review_queue.py`, ADR-0010): a writable HITL worklist
        over *already-decided* samples — open/acknowledge/escalate/resolve/suppress/reopen are ALL
        **reviewer+approver** (relaxed 2026-07-09 from an earlier approver-only resolve/suppress, to
        match the design's reviewer-resolves-hold/rerun-ticket model — an escalate ticket's
        approver-only nuance is a UI-level distinction, not a backend RBAC gate); RBAC + the
        legal-from status live in one `_ACTION_RULES` table (an illegal transition → 409). A ticket
        **snapshots** the sample's `gate`/`verdict`/`rule_id` at open-time as inert data — it never
        calls `run_gate` or re-enters a decision.
     Across all three, every `*_by` audit field and `actions[].actor` is **server-authored** from the
     authenticated `Actor` (bodies are `extra="forbid"` — no client-set identity/PII), and a store
     failure is a generic 503 that never leaks a path/DSN. A saved graph, override, or ticket (like a
     feedback note) is **product state OFF the gate** — it never becomes a verdict, finding, or ledger
     event (ADR-0001).
   - **Card QC-readout projection** (`api/card_readout.py`,
     `GET /api/runs/{id}/cards/{sid}/qc-readout`): an **API-layer join** over an already-decided card
     — the card's registry-normalized `metric_values` × the runbook's `QCThreshold`s → a gate-grouped,
     flagged-first table of Metric · Observed · Threshold · Status. Direction (`>=`/`<=`) comes from
     the runbook's `higher_is_better` (never guessed); an ungated metric is surfaced `not_gated`, not
     fabricated. Its per-metric `status` is **derived to mirror the QC rule exactly** (`pass` ⟺ no
     finding, `fail` ⟺ a CRITICAL finding, `borderline` ⟺ a WARN finding) so the readout can never
     contradict the gate, and the **core `DecisionCard` model is untouched** — pure re-presentation,
     off the deterministic path (ADR-0001).
   - **Advisory agent reads (off the gate).** Three on-demand, read-only endpoints surface the
     advisory agents without re-entering the core: `GET /api/monitoring/signatures/{signature}/repair`
     returns the pipeline-repair agent's cited `RepairProposal` for a recurring signature, and
     `GET /api/runs/{id}/archive-digest` + `GET /api/archive/index` return the archivist's
     `ArchiveDigest` (a per-run or cross-run organizational index). Each formats an advisory
     suggestion over already-decided state — it never sets/overrides a verdict, edits a pipeline, or
     moves an artifact (ADR-0001).
5. **Outbound notify seam (`notify/`, ADR-0010).** An optional `run_gate(notifier=…)` hook
   turns each *actionable* card (HOLD/RERUN/ESCALATE; clean cards are skipped) into a
   notification, tailored per verdict category (identity risk / re-run / borderline-QC) with
   the cited observed-vs-expected evidence. Like every other seam it **formats what the gate
   decided, never a verdict** (ADR-0001): stub-first ($0, in-memory), with Slack / Teams /
   Discord adapters all off by default — each armed only by its OWN live flag
   (`PIPEGUARD_SLACK_LIVE` / `PIPEGUARD_TEAMS_LIVE` / `PIPEGUARD_DISCORD_LIVE`, the webhook
   pair also needing `PIPEGUARD_{TEAMS,DISCORD}_WEBHOOK_URL`), so arming one channel never
   arms another — and every send recorded as a `notification.emitted` ledger event.
   `python -m pipeguard.notify <run_dir>` is the CLI.

## Data flow

`load_run` → `evaluate_run` (rules **normalize each metric through the registry**, then →
`Finding[]` per sample) → `run_gate` (synthesize each sample → `DecisionCard`; emit the event
trail; anchor cards to the `AnalysisRun`; optionally dispatch actionable cards through an
injected `notifier`) → the FastAPI read-API serves cards + events + config → the React
frontend renders them. The triage, pipeline-repair, and archivist agents are invoked on demand
(per flagged card / recurring signature / released run) and never re-enter the verdict path. The read-API shapes those cards for screens without re-entering the
core: it labels each run with an honest lifecycle `status` read from the provenance trail,
filters/sorts/paginates the run list, and pre-aggregates the monitoring roll-up
(`GET /api/monitoring`) so a dashboard renders from one response. The Pipeline Builder's
save/version writes (`POST /api/pipelines`) land in a **separate product store**, off the gate —
they never enter `load_run → evaluate_run` or the ledger. The same holds for the whole
draft→approve authoring lifecycle (pipeline graphs, config-threshold overrides, review-queue
tickets) and the per-card QC-readout: they are API-layer joins/writes over already-decided state,
RBAC-gated by the `api/auth.py` dev shim, and never re-enter the deterministic path — an approved
config override, notably, records intent without mutating the live runbook.

## Invariants

1. **Rules decide; AI is advisory** — never sets/overrides a verdict or confidence (ADR-0001).
2. **AI is OFF by default** with a deterministic fallback; all five AI seams (synthesizer, triage, feedback-triage, pipeline-repair, archivist) flip via env, $0 by default (ADR-0006).
3. **Event log is authoritative**; the DB is a disposable, rebuildable projection (ADR-0002).
4. **Core stays framework-agnostic** — no Streamlit/FastAPI/React imports in `src/pipeguard/`; ports & adapters (ADR-0003).
5. **Findings are immutable + content-hashed**; confidence is omitted until grounded.
6. **Off-gate product state never re-enters the gate** — in-app feedback, saved Pipeline Builder
   graphs, config-threshold overrides, and review-queue tickets are written by dedicated `api/`
   seams to their own stores (each distinct from the decision `Repository`); no product write
   becomes a verdict, finding, or authoritative ledger event, and an approved config override never
   mutates the live runbook (ADR-0001).
7. **Auth is a swappable dev shim, off the gate** — `api/auth.py` is the one shared RBAC source
   (`viewer`/`reviewer`/`approver`) for every draft→approve flow, but its header-trust
   `current_actor()` is a permissive DEV SHIM, **not** a production auth boundary; it gates who may
   *write* product state and never touches a verdict / finding / confidence. Hardening = swapping
   that single function for a verified identity provider (ADR-0010/0017).

## Swappable seams (the flex points)

| Seam | Switch | Default |
|---|---|---|
| Synthesizer (narration) | `PIPEGUARD_SYNTHESIZER=stub\|claude` | stub ($0) |
| Triage agent | `PIPEGUARD_TRIAGE_AGENT=stub\|claude` | stub ($0) |
| Feedback-triage agent (off-gate) | `PIPEGUARD_FEEDBACK_AGENT=stub\|claude` (`PIPEGUARD_FEEDBACK_MODEL`); advisory categorization of the in-app feedback corpus (`api/feedback_agent.py`) | stub ($0) |
| Pipeline-repair agent (advisory) | `PIPEGUARD_PIPELINE_REPAIR_AGENT=stub\|claude` (`PIPEGUARD_PIPELINE_REPAIR_MODEL`, default Opus-high); cross-run remediation proposals over a recurring signature (`src/pipeguard/pipeline_repair/`) | stub ($0) |
| Archivist agent (off-gate) | `PIPEGUARD_ARCHIVIST_AGENT=stub\|claude` (`PIPEGUARD_ARCHIVIST_MODEL`, default Haiku); organizational digest/index over released runs (`api/archivist.py`) | stub ($0) |
| Notify (outbound) | `PIPEGUARD_NOTIFIER=stub\|slack\|teams\|discord`; each adapter armed by its OWN `PIPEGUARD_{SLACK,TEAMS,DISCORD}_LIVE=1` (Teams/Discord also need `PIPEGUARD_{TEAMS,DISCORD}_WEBHOOK_URL`) | stub ($0, no network) |
| Metric registry (normalization) | versioned `metric_registry.yaml` + `our_key` mapping — add/remap a source metric without touching rules | canonical decimals; ON the critical path |
| Repository (persistence) | `Repository` port; SqliteRepository **and** guarded PostgresRepository built (ADR-0016), `get_repository()` selects | SQLite + JSONL (Postgres off by default) |
| Artifact store (staging) | `PIPEGUARD_ARTIFACT_STORE=local\|s3` (`src/pipeguard/artifacts/`); S3 adapter OFF by default (lazy `boto3`, degrade-to-local), realized + tested (`tests/test_artifacts_s3.py`), entry `run_gate_from_store` — the ADR-0003 ports-&-adapters storage seam | `local` |
| Feedback sink (off-gate) | `FeedbackStore` port (`api/feedback_store.py`); jsonl/sqlite/postgres, degrade-to-JSONL (ADR-0016) | JSONL |
| Pipeline-graph store (off-gate product) | `PIPEGUARD_PIPELINE_STORE=jsonl\|sqlite\|postgres` (`api/pipeline_store.py`); mirrors the feedback sink — degrade-to-JSONL, never logs the DSN (ADR-0016) | JSONL |
| Settings-override store (off-gate authoring) | `PIPEGUARD_SETTINGS_STORE=jsonl\|sqlite\|postgres` (`api/settings_store.py`); config-threshold override ledger — degrade-to-JSONL, DSN never logged. Records intent; **never mutates the live runbook** (ADR-0001/0016) | JSONL |
| Review-queue store (off-gate product) | `PIPEGUARD_REVIEW_STORE=jsonl\|sqlite\|postgres` (`api/review_store.py`); ticket lifecycle over already-decided samples — degrade-to-JSONL, DSN never logged (ADR-0010/0016) | JSONL |
| Auth / identity (off-gate) | `api/auth.py` `current_actor()` header-shim (`X-PipeGuard-Actor`/`-Role`) → swap for a verified IdP (OIDC / signed JWT) returning the same `Actor`; one chokepoint, downstream `require_role(...)` unchanged (ADR-0010/0017) | permissive dev shim (`id=dev`, `role=approver`) |
| Deployment | ports & adapters; Nextflow compute portability (ADR-0003) | local |

Unlike the AI/notify seams (off by default, adapter-swapped at the edge), the **metric registry
is on the critical path** — its "flex" is that new tool keys or unit changes are absorbed by the
versioned YAML/mapping, not by editing `rules`, keeping verdicts byte-identical across the change.

## Deployment

Local today: Streamlit (offline) + FastAPI (`uvicorn`) + React (Vite). The ports-&-adapters
boundary and Nextflow (compute) carry portability to Slurm / AWS later (ADR-0003, wishlist) —
though **storage** portability is already a realized seam, not only a future note: the **S3
artifact-store adapter is built + tested** (`src/pipeguard/artifacts/`, `PIPEGUARD_ARTIFACT_STORE=s3`,
off by default; lazy `boto3`, degrade-to-local; `tests/test_artifacts_s3.py`), so pointing
staging at S3 is an adapter flip.
The core has no cloud/DB coupling; **both** repository adapters are built — `SqliteRepository`
(default) and a guarded, off-by-default `PostgresRepository` (ADR-0016, with a
`deploy/postgres/docker-compose.yml` + a compose-gated live test verified green). IaC remains a
Phase-2+ concern.
