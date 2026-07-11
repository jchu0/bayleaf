# Architecture — System Shape

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-10 (MST) |
| **Audience** | software / bioinformatics / reviewers |
| **Related** | [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md), [ADR-0016](../adr/ADR-0016-postgres-port.md), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), [schemas.md](../data/schemas.md), [metric_registry.md](../data/metric_registry.md), [qc_metrics.md](../data/qc_metrics.md), [provenance.md](../data/provenance.md), [journal 2026-07-09 frontend-batch2](../journal/2026-07-09-frontend-batch2.md), [journal 2026-07-09 frontend-batch3](../journal/2026-07-09-frontend-batch3.md), [journal 2026-07-10](../journal/2026-07-10-provenance-qc-builder-auth.md), [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md), [journal 2026-07-10 batch6](../journal/2026-07-10-admin-settings-builder-wiring.md), [journal 2026-07-10 batch7](../journal/2026-07-10-builder-modals-and-run-selector.md), [journal 2026-07-10 batch8](../journal/2026-07-10-batch8-theme-monitoring-recharts.md) |

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
   - **Frontend fixes batch 4 (2026-07-09→10, commits `71a06d6`→`07f53af`, [journal](../journal/2026-07-10-provenance-qc-builder-auth.md)), eight maintainer-reported gaps closed.**
     (1) **Provenance download + full digest + a real QC input** (T-077, `71a06d6`, above).
     (2) **UI refinements** (T-078, `e3e1995`): Review-queue 25/50/100 pagination + per-run
     grouping + a default open-tickets filter; Runs-card two-row layout (a long `run_id` no
     longer squeezes the verdict bar); Monitoring gains a `DateRangePicker` + a Y-axis gutter +
     gridlines on the throughput chart (no charting lib added); Agent-triage's non-scalable pill
     selector becomes a verdict-ranked Sample·Verdict·Gate·Headline·Findings table.
     (3) **Grafana dashboard** (T-079, `f696bc7`, `deploy/telemetry/`): Prometheus/Grafana were
     already wired (T-036) but Grafana booted empty; a provisioned "PipeGuard — QC decision gate"
     board now renders the four already-shipped `/metrics` series (no new series) — config-only,
     still off the offline demo path. (4) **Hash label + chart-width fix** (T-080, `eb7d016`,
     above + the Monitoring throughput bars going constant-width/scrollable instead of
     stretching/squishing as run count grows). (5) **Demo login gate + a real admin role**
     (T-081, `0f7e85f`): a login screen now fronts the whole app (`frontend/src/auth.ts` +
     `screens/Login.tsx`, four demo accounts, every production auth seam labelled as NOT
     implemented — OAuth/OIDC, server-side password hashing, httpOnly session cookie, real
     CAPTCHA); **`isAdmin` now follows the LOGIN identity**, a frontend-only governance
     capability layered over the wire roles (an admin is an approver who *also* holds
     governance) — this **corrects** the Admin paragraph below, previously gated on "any
     approver." (6) **QC enrichment → an honest three-gate readout** (T-082, above).
     (7)/(8) **Pipeline Builder connector + tool-I/O fix, and canvas navigation** (T-083/T-084,
     `d8c1625`/`07f53af`): the seeded DAG's connectors were hardcoded SVG paths that detached
     from a port whenever a card's port count changed — now **computed** from the tool/reference
     card geometry + typed ports (`BuilderCanvas` `SEEDED_WIRES`/`REF_WIRES`), and several tools
     had wrong I/O (bcftools call/norm's `panel_bed`, markdup's real outputs, mosdepth's
     thresholds output, a phantom `samtools_stats`) — all corrected against the real pipeline
     (`scripts/run_giab_pipeline.py`); **Fit** now centers/zooms to the pipeline (not just a zoom
     reset), ctrl-wheel/trackpad-pinch zooms the canvas natively (native `{ passive: false }`
     listener, since React's `onWheel` is passive), and the minimap grew to a 210×108
     proportional mirror (was 168×46).
   - **Admin (`screens/Admin.tsx`), `isAdmin`-gated governance off the gate.** Three tabs: **Users
     & roles** — an explicit **client-mock** roster (there is no backend user store; `api/auth.py`
     is a header dev-shim) with a role selector and "Act as" wired to `RoleContext.setActor`, plus
     a persistent "dev auth shim, not an identity system" banner. **Role-staging hardening
     (2026-07-10, T-092, commit `5774143`):** a role change no longer applies on the first click of
     a toggle — the control is now a dropdown, and a change **stages into a draft** ("unsaved"
     badge) behind an explicit Save/Discard bar (only Save writes the roster, re-syncing the live
     actor if its own role changed), and "Act as" now `window.confirm()`s before impersonating.
     Still the same client-mock roster ([risks.md](../quality/risks.md) RISK-035) — this hardens
     the legitimate UI path, not the underlying (already non-production) security boundary.
     **Activity log** — a REAL,
     zero-new-backend audit feed merging `listThresholds` + `listPipelines` + `listTickets` into
     one append-only when/actor/kind/target/status table, facet-filterable by kind.
     **Paginated + expandable (2026-07-10, T-093, commit `8a14661`, "A2"):** the flat, uncapped
     list (a formatting mess as it grows) now paginates 25/50/100 with a numbered pager
     ("Showing X–Y of Z," resets on filter change), and each row is a compact summary that
     expands on click to a labelled Detail/Target/Actor/When panel (one open at a time) — no
     backend change. **System** —
     REAL reads of `GET /api/health` + runbook gate count + metric-registry version/gated-count,
     labelled illustrative-not-clinical. **Built out (2026-07-10, T-094, commit `7c56564`,
     "A3/A4"):** gained an Artifact-store stat card (`local` · the `PIPEGUARD_ARTIFACT_STORE` s3
     seam) and an Observability section linking the read-API's `/metrics` exporter, Prometheus
     (`:9090`), and the Grafana "PipeGuard — QC decision gate" dashboard (`:3000`, built
     T-036/T-079) as links (Grafana blocks framing; the stack is off the offline demo path), with
     a note on bringing up the `deploy/telemetry/` compose stack; Users & roles also gained a
     per-user password/email-reset action — a labelled production seam (no live mail), which
     toasts what would happen rather than sending anything. Admin decides WHO may perform an off-gate product write
     and whose id lands in an audit field — it never sets, overrides, or displays a
     verdict/finding/confidence (ADR-0001; no confidence meter). **Gating corrected 2026-07-10**
     (T-081): the nav item and `/admin` route now gate on `isAdmin` — a frontend-only governance
     capability (`frontend/src/auth.ts` `ADMIN_IDS`, derived from the login roster) layered over
     the wire roles, distinct from "any approver" — not the earlier any-approver framing.
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
     distinction, not this backend gate). **Dry-run/Diff wired to the real endpoints
     (2026-07-10, T-096, commit `4208f0b`, see the batch-6 bullet below)** — closes the earlier
     "client-side-only projection" limitation this paragraph used to flag.
   - **Frontend fixes batch 5 (2026-07-10, commits `14c9f3c`→`5774143`, T-085–T-092,
     [journal](../journal/2026-07-10-batch5-builder-card-admin-prefs.md)), 8 UI-polish items —
     all re-presentation/UX, no verdict/gate/ADR-0001 boundary changed.** (1) **Builder Tidy is
     flow-preserving** (T-085, `14c9f3c`): each node's longest-path depth from a source is
     relaxed over the composed edges, then placed in the column of its depth (parallel nodes
     stacked), so upstream→downstream reads left→right instead of one row losing the connection
     structure; a **Cancel** button (draft-only) discards the in-progress build back to the
     linked pipeline in View; the minimap moved bottom-right→top-right. (2) **Reference SOURCE
     palette cards + collapsible sections** (T-086, `c6a6210`): a new References section
     (Reference FASTA/Panel BED/Truth VCF, no-input nodes emitting their ref artifact) fills the
     earlier "no way to add bed/vcf/reference cards" gap; palette sections collapse (chevron +
     count), overridden by an active search. (3) **Gate dependency, `blocked_by`** (T-087,
     `545c893`, "DC2 part 1" of the maintainer's two-tier gate model — see the Card QC-readout
     projection bullet below for the full mechanism). (4)/(5) **Decision-card pill polish**
     (T-088/T-089, `24940e1`/`d5fdcb2`): the top-strip "Passed" gate chip is now green (proceed
     tokens, was neutral grey; "Not run" stays grey), and the redundant 3px verdict-colored left
     spine is dropped (verdict is already carried by badges/pills; the colored rail is now
     reserved for Pipeline-Builder tool cards). (6) **Provenance: view vs. download split**
     (T-090, `de5fa94`, see the Runs read-API bullet below). (7) **Real, persisted theme +
     density** (T-091, `08a42ad`): a new `context/PrefsContext.tsx` (theme light/dark/system,
     density split/brief/dense, `localStorage`-persisted) makes the previously-inert Settings
     dialog controls real; a full dark theme in `index.css`
     (`:root[data-theme="dark"]` overriding the `@theme --color-*` vars) retargets every
     existing Tailwind utility with no per-component change; density is now one setting shared
     by the dialog and `RunDetail`'s own Layout control. (8) **Admin role-staging** (T-092,
     `5774143`, see the Admin bullet below).
   - **Frontend fixes batch 6 (2026-07-10, commits `8a14661`→`4208f0b`, T-093–T-096,
     [journal](../journal/2026-07-10-admin-settings-builder-wiring.md)), 4 items — also
     re-presentation/UX, no verdict/gate/ADR-0001 boundary changed.** (1) **Admin Activity-log
     pagination + expandable rows** (T-093, `8a14661`, "A2," see the Admin bullet above). (2)
     **Admin System observability + artifact-store card + password reset** (T-094, `7c56564`,
     "A3/A4," see the Admin bullet above). (3) **Settings sample-type dropdown** (T-095,
     `869cf55`, "S1"): `SettingsAssayTable.tsx`'s two side-by-side Whole-blood/Saliva columns
     become a single value column driven by a new Sample-type dropdown beside the Assay
     selector — cleaner and scales as more sample types are added; editing/save/approve, the
     per-tissue values, and the audit lifecycle (REQ-F-062) are unchanged. (4) **Builder
     Dry-run/Diff wired to the real endpoints** (T-096, `4208f0b`, "Item E"): once the graph is
     Saved, `BuilderConsole`'s Dry-run tab calls `POST /api/pipelines/{name}/dry-run?run_id=…`
     (a plain run-id text input, not yet a searchable picker — [tasks
     T-070](../planning/tasks.md) stays open), rendering the real per-locator
     matched/ambiguous/missing/invalid resolution + summary; Diff calls `GET
     /api/pipelines/{name}/diff`, rendering added/changed/removed vs the approved baseline (or
     "no baseline yet"); both fall back to the earlier client-side preview before Save. Compose
     ≠ execute holds (a dry-run globs paths, reads no bytes, runs nothing). **Closes** the
     "`dryRunPipeline`/`pipelineDiff` exist but aren't called yet" limitation this doc previously
     flagged; **narrows** [tasks T-069](../planning/tasks.md) to the remaining Run-hand-off /
     pipeline-repair / archivist Builder modals (still static `phase-2` previews) + saved-profiles.
   - **Frontend fixes batch 7 (2026-07-10, commits `34bca5d`→`adfd7aa`, T-069/T-070/T-072,
     [journal](../journal/2026-07-10-builder-modals-and-run-selector.md)), closes the last of the
     Builder/Monitoring deferrals this doc had been carrying — also re-presentation/wiring-only,
     no verdict/gate/ADR-0001 boundary changed.** (1) **Monitoring per-run pagination** (`34bca5d`):
     the "Verdicts over time" throughput columns (`data.runs`) now paginate client-side too
     (25/50/100 + numbered pager, "Showing X–Y of N runs"), ported verbatim from the signatures
     pager with independent state and a reset-to-page-1 effect on window/date-range/per-page
     change; `maxSamples` stays computed over the full filtered set. **This closes only the
     frontend half of [tasks T-072](../planning/tasks.md) — the backend `GET /api/monitoring`
     `runs[]` payload stays uncapped server-side, so T-072 itself is still open.** (2) **Reusable
     `RunSelector`** (`3c6455e`, **closes** [tasks T-070](../planning/tasks.md)): a new
     `frontend/src/components/RunSelector.tsx` — a searchable (id/platform), 8-row-capped
     combobox sharing the top-bar switcher idiom (real `RUN_STATUS_META` status dot, F17, never
     `n_attention`), self-fetching `api.runs()` lazily with an honest "Couldn't load runs" on
     failure — replaces `BuilderConsole`'s plain run-id text input for Dry-run; its props leave it
     ready for the archivist/run-handoff surfaces as future consumers (not yet wired there). (3)
     **Builder advisory-modal wiring + saved-profiles** (`adfd7aa`, **closes** [tasks
     T-069](../planning/tasks.md)): `PipelineRepairModal` now calls `GET /api/monitoring` (a
     signature picker) + `GET /api/monitoring/signatures/{sig}/repair` and renders the real
     `RepairProposal` (a **"heuristic" score label, never "confidence"**; "Send to review queue"
     navigates to `/queue` rather than fabricating a ticket — a signature-level fix has no
     sample_id/verdict to attach one to); `ArchivistModal` calls `GET /api/archive/index` and
     renders the real cross-run `ArchiveDigest` (archive-ready counts, origins verbatim, proposed
     action, the backend disclaimer; "Queue archive" stays inert — no write endpoint exists);
     `RunHandoffModal` now shows the real composed `run_layout.yaml` and its button copies it
     (compose ≠ execute holds, no network call, no more fake "Hand off to Nextflow"). A new
     toolbar **"Open" action** lists `GET /api/pipelines` and hydrates the canvas from a chosen
     saved graph — the saved-profiles gap this doc flagged — with approved graphs opening
     read-only (re-saving mints a new draft) and a foreign/topology-less envelope loading empty
     with a labelled toast rather than fabricated nodes. All three commits verified frontend-only
     (`git diff --stat a728cb7..adfd7aa -- src/ api/ tests/` empty).
   - **Frontend fixes batch 8 (2026-07-10, commits `5763be1`→`f8a6f35`, T-098–T-100,
     [journal](../journal/2026-07-10-batch8-theme-monitoring-recharts.md)), a maintainer
     UI-feedback pass — also re-presentation/UX-only, no verdict/gate/ADR-0001 boundary changed**
     (`git diff --stat 1169e37 f8a6f35 -- src/ api/ tests/` empty). **(1) Theme** (`5763be1`,
     T-098): light mode softened to a warm japandi sand/greige palette (`frontend/src/index.css`
     `@theme` neutrals — page `#f5f7f9`→`#f2efe7`, cards `#fff`→`#faf9f4`, insets/lines/text
     warmed to greige, contrast kept AA+; functional verdict colors, the dark nav, and the blue
     accent are unchanged), and a new theme-aware `--canvas-dot` var (warm+subtle in light, much
     dimmer `rgba(150,165,185,.08)` in dark — was a hardcoded light hex that read as distracting
     on the dark canvas) moves the Pipeline-Builder dot grid onto the scroll surface
     (`BuilderCanvas.tsx`) so it spans the whole canvas, not just the content plane. **(2) UI
     feedback pass** (`3c6dacb`, T-099): the Builder's advisory-agent palette tiles
     (QC-triage/Pipeline-repair/Archivist) gain an `alwaysEnabled` `PaletteItem` flag and are now
     clickable in **View** mode — they only ever open a read-only advisory modal/pill, never
     mutate the graph, so an operator can consult one without switching the whole canvas into
     Edit (node-adding tiles still require Edit); Provenance relabels the artifact digest "hash"
     → "**fingerprint**" (`Provenance.tsx`, continuing T-080's defense-in-depth framing — a
     content digest, not a process/run id) with the full value now shown on hover; the Runs
     verdict bar is capped `max-w-[300px]` with 2px inter-segment gaps so adjacent tones (hold
     amber / rerun orange) read as distinct blocks (`RunOverview.tsx`); Agent-triage's
     flagged-samples table caps at 10 rows/page + a numbered pager (`AgentTriage.tsx`). **(3)
     Monitoring rework** (`f8a6f35`, T-100, "Wave 2"): adds **recharts 3.9.2 (MIT)** — the
     frontend's first real charting dependency, justified per the repo's Dependencies guardrail
     (a hand-rolled SVG bar chart couldn't give hover tooltips + a trend line + a stable frozen
     frame without reinventing a chart library; React-19-compatible, added at the maintainer's
     request). The "Verdicts over time" chart is now a Recharts `ComposedChart` (stacked
     per-verdict bars + a monotone "Flagged (trend)" line + a grounded per-run hover tooltip +
     dashed gridlines), FROZEN to a ~14-day column frame that scrolls sideways beyond it instead
     of resizing the card on a 7d/14d/30d toggle. **This REVERSES, not just narrows, batch 7's
     per-run pager** (`34bca5d`, [tasks T-072](../planning/tasks.md)) — the chart now renders
     every fetched run as a scrolling bar rather than a paginated table, because (per the
     maintainer) "it scrolls now, so paging the throughput columns made no sense"; the
     signatures pager is unaffected. Recurring signatures gain a unique, stable display id
     (`SIG-<first 8 chars of the signature hash>`, disambiguating e.g. two PIPE-001 patterns) and
     a REVERSIBLE, `localStorage`-persisted clear-from-view/restore (never a DB purge, never
     touches `api/`) — a cleared signature moves into a collapsible "Cleared · N" section, stays
     searchable, and restores in one click.
   **Honest, labelled frontend deferrals (no fabrication):** the Monitoring **Median-review KPI**
   (no backend field yet — the signature-level `first_seen`/`last_seen`/`trend`/`affected_run_ids`
   fields below ARE shipped); Submit now
   hands off to a real execution boundary (`POST /api/runs`, T-057 — see below) but still has
   **no BaseSpace connector** and no conversational multi-turn triage chat (both still wishlist);
   and `GET /api/monitoring`'s per-run `rows[]` stays uncapped server-side ([tasks
   T-072](../planning/tasks.md)'s backend half — as of batch 8 there is no longer a frontend
   render-cap either, since the throughput chart now scrolls instead of paginating; the
   underlying payload-size risk T-072 tracks is unmitigated in either direction until the
   backend gains `page`/`limit` on `runs[]`, mirroring `GET /api/runs` — fine at today's ~29–30
   run volume, a real concern once `synthetic/scale.py` (T-050) seeds a much larger window). The
   Builder's Run-hand-off / pipeline-repair / archivist modals + saved-profiles (T-069) and the
   reusable run-selector (T-070) are **both now closed** (batch 7 above) — this paragraph no
   longer carries them as open gaps. Of the 10 operator screens: 8 (Runs, Intake, Decision cards, Review queue,
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
   - **Runs read-API.** `GET /api/runs` (+ `/{id}`, `/{id}/cards/{sample}`, `/{id}/artifacts`, and
     now `/{id}/artifacts/{name}` — a traversal-hardened download, `FileResponse`, name must be a
     bare filename resolving inside the run dir; `RunArtifact` gained a `url` field pointing at it,
     closing the earlier "no download URL" deferral, T-077 `71a06d6`). **View vs. download split
     (2026-07-10, T-090, commit `de5fa94`):** the endpoint gained a `download: bool = False` query
     param — `Content-Disposition` is `inline` by default (click-to-view at its location) and
     `attachment` only on `?download=1`; the frontend's artifact-name click uses the bare `url`
     (view) and the Download button appends `?download=1` (save) — previously both hit the same
     always-`attachment` URL. The artifact-stage map
     (`_ARTIFACT_STAGE`) now attaches each file to a **list** of `(stage, role)` edges rather than
     one, so `demux_stats.csv`/`reads` are both the demux stage's OUTPUT *and* the QC stage's INPUT
     — the same bytes feed the QC node in the Provenance compute-DAG, which previously read as
     input-less. The frontend also stopped naming the digest algorithm on screen ("hash" /
     "content hash," not "sha256," in Provenance + the Archivist manifest — defense-in-depth,
     2026-07-10 `eb7d016`; the wire field is still `sha256`), and added a "show full" toggle
     revealing all 64 hex chars.
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
     fabricated, and now **labelled with the registry's `display_name`** (e.g. "Genotype quality
     (GQ)") rather than the raw `our_key` (2026-07-10, `a9b06ad`). Its per-metric `status` is
     **derived to mirror the QC rule exactly** (`pass` ⟺ no
     finding, `fail` ⟺ a CRITICAL finding, `borderline` ⟺ a WARN finding) so the readout can never
     contradict the gate, and the **core `DecisionCard` model is untouched** — pure re-presentation,
     off the deterministic path (ADR-0001). **QC enrichment (T-082, 2026-07-10, commits
     `a8fc73b`→`a9b06ad`):** the core `QCMetrics` model gained 8 additional registered fields
     (`preflight.phix_aligned`; `qc.breadth_20x`/`breadth_30x`/`pct_mapped`/`on_target`;
     `variant.dp`/`gq`/`titv`, [schemas.md](../data/schemas.md)) so the **preflight and variant**
     groups — previously always an empty note for every run, regardless of data — can now populate
     with real measured rows when a run's QC report carries them; 5 of the 8 gained an **optional**
     (`required=False`) runbook threshold that scores a present value but never NA-flags an absent
     one, so a lean real run stays exactly as before while a richer contrived run is fully gated
     (10 gated / 10 ungated of 20 registered metrics, [metric_registry.md](../data/metric_registry.md)
     §Wiring status). The synthetic generator emits all 8 (contrived, comfortably passing); the real
     GIAB HG002 driver (`scripts/run_giab_pipeline.py`) now also writes its own real
     `breadth_20x`/`breadth_30x` from mosdepth (honest extra QC from that run's own data, not
     contrived) while everything it doesn't produce stays blank — no result is ever fabricated,
     and the gate's verdict logic is unchanged. **Gate dependency, `blocked_by`** (2026-07-10,
     T-087, commit `545c893`, "DC2 part 1" of the maintainer's two-tier gate model: sequencing-tier
     QC gates sample **processing**, sample-tier QC gates **downstream analysis**): `GateReadout`
     gains `blocked_by: Gate | None`. `build_qc_readout` computes `unclear = {gr.gate for gr in
     card.gate_results if gr.verdict is not PROCEED}` (a gate only carries a `gate_result` when it
     has findings, so "has one" ⟺ "not clear") and `_blocking_gate()` walks upstream from each gate
     to the nearest gate in `unclear`. A gate blocked by an unclear upstream gate now renders
     "blocked · clear \<upstream\> first" instead of "all clear," so a QC hold no longer looks like
     the sample proceeded to variant calling. **Pure re-presentation** — the card's own verdict
     already reflects the QC finding; this only stops a *downstream* gate's UI from misreading as
     clear (ADR-0001 intact; `rules.py`/`synthesis/` untouched, verified by diff). The frontend
     (`MetricsPanel.tsx`'s `Rollup`, `RunDetail.tsx`'s `CardBody`) mirrors the same nearest-upstream
     computation for the placeholder/empty gate groups it synthesizes client-side. Part 2
     (user-clearable HOLD/ESCALATE, individually + in batches) is the next slice, not yet built.
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
