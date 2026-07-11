# Functional Requirements

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-10 (MST) |
| **Audience** | software / all |
| **Related** | [scope-and-wishlist.md](scope-and-wishlist.md), [nonfunctional.md](nonfunctional.md), [constraints.md](constraints.md), [design/architecture.md](../design/architecture.md), [design/agents.md](../design/agents.md), [data-platform-and-archivist.md](../design/data-platform-and-archivist.md), [metric_registry.md](../data/metric_registry.md), [qc_metrics.md](../data/qc_metrics.md), [schemas.md](../data/schemas.md), [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md), [ADR-0008](../adr/ADR-0008-issue-taxonomy-suppression-escalation.md), [ADR-0009](../adr/ADR-0009-corpora-retrieval-upskilling.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md), [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md), [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md), [ADR-0016](../adr/ADR-0016-postgres-port.md), [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), [journal 2026-07-09 frontend-batch2](../journal/2026-07-09-frontend-batch2.md), [journal 2026-07-09 frontend-batch3](../journal/2026-07-09-frontend-batch3.md), [journal 2026-07-10](../journal/2026-07-10-provenance-qc-builder-auth.md), [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md), [journal 2026-07-10 batch6](../journal/2026-07-10-admin-settings-builder-wiring.md), [journal 2026-07-10 batch7](../journal/2026-07-10-builder-modals-and-run-selector.md) |

## Overview

What PipeGuard must *do*, as traceable capability requirements (**REQ-F-NNN**). Each
traces to an ADR, the architecture, or a grounded data doc. Quality attributes
(determinism, security, performance) live in [nonfunctional.md](nonfunctional.md);
boundaries in [scope-and-wishlist.md](scope-and-wishlist.md). Requirements describe
in-scope MVP behavior; deferred items are marked *(wishlist)*.

## Decision gate

1. **REQ-F-001 — Per-sample verdict.** For each sample in a run, the system produces
   exactly one **DecisionCard** with a verdict of **proceed / hold / rerun /
   escalate** (one card per sample × analysis-run). *Trace:* [architecture.md](../design/architecture.md),
   [schemas.md](../data/schemas.md) §DecisionCard.
2. **REQ-F-002 — Cited evidence.** Every finding and card cites **Evidence**
   traceable to a source artifact + field (and, where present, a content hash), with
   observed vs expected values. No number appears without a source. *Trace:*
   [schemas.md](../data/schemas.md) invariants, ADR-0001.
3. **REQ-F-003 — Rules decide, deterministically.** Verdict and (when present)
   confidence are computed by the deterministic rule/aggregation layer, **never** by
   the LLM. *Trace:* [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   `synthesis/base.py`.
4. **REQ-F-004 — Immutable, content-hashed findings.** Findings are immutable and
   content-hashed; each derives its gate and a rule-version-independent signature.
   Suppression/resolution never mutate a finding. *Trace:* [schemas.md](../data/schemas.md)
   §Finding, ADR-0008.
5. **REQ-F-005 — Confidence omitted until grounded.** Confidence is nullable and is
   omitted rather than fabricated when not grounded; when shown it is labelled a
   heuristic, not a calibrated probability. *Trace:* CLAUDE.md guardrails, T-019.

## Three-gate model & verdict policy (ADR-0013)

1. **REQ-F-010 — Three checkpoints.** Findings and verdicts are labelled by gate:
   **preflight** (intake), **qc** (per-sample QC), **variant** (Phase 2). *Trace:*
   [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [architecture.md](../design/architecture.md).
2. **REQ-F-011 — Preflight gate.** Check barcode/index integrity, sample identity,
   required metadata, and per-sample FASTQ sanity before the processing queue, with a
   manual-override path for genuinely-sparse edge cases. *Trace:* ADR-0013,
   [qc_metrics.md](../data/qc_metrics.md) Gate 1.
3. **REQ-F-012 — QC gate.** Evaluate yield/Q30, coverage **depth and breadth**,
   contamination, and sample-swap; surface depth and breadth as **distinct** signals.
   *Trace:* [qc_metrics.md](../data/qc_metrics.md) Gate 2, ADR-0013.
4. **REQ-F-013 — Variant gate.** *(Phase 2)* Per-variant DP/GQ/allele-balance plus
   gnomAD/ClinVar annotation; caller-aware. *Trace:* [qc_metrics.md](../data/qc_metrics.md)
   Gate 3.
5. **REQ-F-014 — Surface-and-decide verdict mapping.** Borderline → **HOLD**;
   provenance/identity → **ESCALATE**; operational/file-system failure → **RERUN**;
   clean → **PROCEED**; worst verdict wins. *Trace:* ADR-0013,
   [qc_metrics.md](../data/qc_metrics.md) §Verdict policy.
6. **REQ-F-015 — Config-driven thresholds.** Thresholds come from an operator-owned
   runbook **profile** keyed on **assay × sample type**; no hardcoded universal
   thresholds. *Trace:* [qc_metrics.md](../data/qc_metrics.md) §Principles, ADR-0005.
7. **REQ-F-016 — Metrics normalized through the registry; gate on canonical values.**
   Each QC metric is resolved to its canonical `our_key` and normalized to a **canonical
   decimal** via the **metric registry** before gating; the gate compares the normalized
   value against a canonical-decimal runbook threshold (both on the registry's scale), so
   a change in a source's raw unit cannot silently move a verdict, and verdicts stay
   byte-identical. The registry is **on the QC-gate critical path**; a missing field yields
   no `MetricValue` (a signal, not a crash). *Trace:* [metric_registry.md](../data/metric_registry.md),
   [schemas.md](../data/schemas.md) §QC (units contract), `rules.py`, T-024/T-025.
8. **REQ-F-017 — Execution-trace ingestion (EXEC-001).** The gate **reads** an optional
   Nextflow/nf-core `trace.txt` when the run produced one and maps a **failed pipeline
   process** to **RERUN** — the structured sibling of the free-text run-log check (PIPE-001).
   A task attaches to its sample by an **exact** nf-core `tag` match (so a zero-padded id can't
   cross-fire the way a substring would), and a task is a failure when its status is in the
   runbook's failure-status set **or** its exit code is nonzero (an OOM/time-kill fires even
   when the status isn't literally `FAILED`), yielding a cited, immutable `Finding` (PIPELINE
   category, **preflight** gate) whose suggested verdict is RERUN. It **composes ≠ executes**:
   it *reads* a trace the run already emitted and **never runs a process** (ADR-0001/0003). A
   missing, absent, or garbled trace yields **no** finding (a signal, not a crash — the pinned
   demo runs carry no `trace.txt` and are unaffected). Downstream it is **advisory only**: the
   EXEC-001 finding's recurring signature flows to the pipeline-repair agent (REQ-F-023) via the
   monitoring rollup, giving that agent a **structured executor-failure** feed distinct from
   PipeGuard's own gate findings. The **verdict policy is unchanged** — an operational/execution
   failure → RERUN (REQ-F-014). *Trace:* [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md),
   [qc_metrics.md](../data/qc_metrics.md) §Verdict policy,
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)/[ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md),
   `rules._check_execution_trace`, [tasks T-061](../planning/tasks.md).

## Advisory triage agent (ADR-0009/0012)

1. **REQ-F-020 — On-demand triage.** For a flagged card, the system can produce an
   advisory **TriageNote** (likely cause, suggested action, citations) grounded in a
   curated knowledge corpus via a retrieval interface. *Trace:* [architecture.md](../design/architecture.md)
   §Triage agent, ADR-0009.
2. **REQ-F-021 — Advisory only, off the critical path.** The triage agent never sets
   or overrides a verdict/confidence and is not on the deterministic path; its output
   is labelled advisory. *Trace:* [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   ADR-0012.
3. **REQ-F-022 — Outbound notify.** For each *actionable* card (HOLD/RERUN/ESCALATE;
   clean cards are skipped), the system can emit a per-verdict, evidence-cited notification
   through a swappable notify port (`PIPEGUARD_NOTIFIER=stub|slack`, stub-first, $0). The
   hook is **optional and off by default** — `run_gate(notifier=…)` is wired only when a
   notifier is injected, and with none the event trail is byte-for-byte unchanged. It
   **formats what the gate decided, never a verdict** (ADR-0001); the live Slack post is
   opt-in via `PIPEGUARD_SLACK_LIVE`, degrades to the stub on any error, and every send is
   recorded as a `notification.emitted` ledger event. `python -m pipeguard.notify <run_dir>`
   is the CLI. *Trace:* [architecture.md](../design/architecture.md) §Outbound notify seam,
   [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md).

## Advisory agent roster — pipeline-repair & archivist (ADR-0001/0008/0012)

Two further advisory agents (roster #2/#3, [agents.md](../design/agents.md) §Roster) join the
QC-triage agent (REQ-F-020/021). Each shares the same contract as triage: **advisory, on-demand,
and OFF the deterministic gate** — like every agent (ADR-0001) it never sets, routes, or overrides
a verdict or confidence; it is **stub-first ($0, offline)** and env-flippable to live; and its
output is an immutable, content-hashed record whose organizational/remediation fields and citations
are **deterministic**, with only the free prose optionally model-authored (the shared invariant now
holds across **five** agents — triage, feedback, pipeline-repair, archivist, and the designed
node-authoring agent).

1. **REQ-F-023 — Advisory pipeline-repair agent.** On a **recurring issue signature** rolled up
   from the monitoring view (the same `Finding.signature` counter `GET /api/monitoring` uses — now
   including structured pipeline-executor failures via EXEC-001, REQ-F-017, not only PipeGuard's own
   gate findings), the system can produce a cited **RepairProposal** {`summary`, `attach_to` (pipeline stage), `scope`
   (gate)} proposing a **human-reviewed** remediation grounded in a curated remediation corpus
   (ADR-0008 taxonomy + the runbook; **no invented thresholds**). `advisory` is pinned `True` and the
   record has **no verdict/confidence field**; `attach_to`/`scope` and every citation are
   deterministic (from the corpus + the addressed rule/signature), only the prose may be
   model-refined. It is exposed **on-demand** at
   `GET /api/monitoring/signatures/{signature}/repair` (404 if the signature does not recur in the
   window) — explicitly **not** the deferred ~3× auto-escalation trigger — and **never edits a
   pipeline** (compose ≠ execute; a fix changes nothing on the gate until a human approves + the
   builder emits a new `run_layout.yaml`). Env `PIPEGUARD_PIPELINE_REPAIR_AGENT=stub|claude`
   (Opus-high, `PIPEGUARD_PIPELINE_REPAIR_MODEL`), stub-default, degrade-to-stub on any error.
   *Trace:* [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   [ADR-0008](../adr/ADR-0008-issue-taxonomy-suppression-escalation.md),
   [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md),
   [agents.md](../design/agents.md) §Roster #2, `src/pipeguard/pipeline_repair/`,
   [tasks T-058](../planning/tasks.md).
2. **REQ-F-024 — Advisory archivist (librarian) agent.** The system can index/summarize
   already-decided runs into an **ArchiveDigest** (an organizational digest + a prepared export
   manifest + a cross-run index) — **organizational, not diagnostic**. It runs on a **least-privilege**
   input (no `subject_id`/tissue/`submitted_by`), **never opens/moves/deletes a file or relabels an
   `origin`**, `advisory` is pinned `True`, and it carries no verdict/confidence (ADR-0001); every
   organizational number is deterministic and only the summary prose may be model-authored. Its
   `released`-lifecycle readiness flag is an **organizational** state, never a per-sample verdict
   (REQ-F-003 holds). Exposed on-demand at `GET /api/runs/{id}/archive-digest` (one run) and
   `GET /api/archive/index` (cross-run). Env `PIPEGUARD_ARCHIVIST_AGENT=stub|claude` (Haiku,
   `PIPEGUARD_ARCHIVIST_MODEL`), stub-default, degrade-to-stub. *Trace:*
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md) §model-tiering,
   [data-platform-and-archivist.md](../design/data-platform-and-archivist.md) §5,
   [agents.md](../design/agents.md) §Roster #3, `api/archivist.py`,
   [tasks T-059](../planning/tasks.md).

## Provenance & persistence (ADR-0002/0003)

1. **REQ-F-030 — Append-only event ledger.** Every gate execution emits an
   append-only event trail (`analysis_run.started` → per-sample
   `sample.registered` / `finding.emitted` / `verdict.decided` →
   `analysis_run.completed`) into an EventLedger (in-memory + optional JSONL). *Trace:*
   [provenance.md](../data/provenance.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md).
2. **REQ-F-031 — Log is authoritative; DB is a projection.** The relational DB is a
   rebuildable projection reached only through a `Repository` port; the core never
   touches a DB directly. *Trace:* [provenance.md](../data/provenance.md), ADR-0003.
3. **REQ-F-032 — rebuild-db.** A `rebuild-db` command replays a JSONL ledger into a
   fresh projection deterministically and idempotently. *Trace:* [provenance.md](../data/provenance.md)
   §DB projection.
4. **REQ-F-033 — Origin labelling.** Every artifact/record is tagged `real-giab` /
   `synthetic` / `contrived`; the label is carried through the ledger and schemas.
   *Trace:* [strategy.md](../data/strategy.md), ADR-0007.

## Read API & operator screens (ADR-0010/0014)

1. **REQ-F-040 — Read API.** A FastAPI read-API serves decision cards, provenance
   events, run **artifacts** (`GET /api/runs/{id}/artifacts` — per-stage data I/O with real
   sha256 + on-disk size + origin tag; raw reads above an 8 MiB cap are size-listed, not
   hashed), export, and config over the framework-agnostic core (the production seam).
   *Trace:* [architecture.md](../design/architecture.md), ADR-0010/0014.
2. **REQ-F-041 — On-demand advisory-agent endpoints.** The API exposes per-card triage plus the
   pipeline-repair (REQ-F-023) and archivist (REQ-F-024) calls, each invoking an advisory agent
   **without re-entering the verdict path** — all read-only over already-decided artifacts.
   *Trace:* [architecture.md](../design/architecture.md), [agents.md](../design/agents.md), ADR-0010.
3. **REQ-F-042 — Operator screens.** The UI presents **10 operator screens**, rebuilt to the
   refreshed design prototype (`docs/design/frontend/`, 2026-07-09) in a **three-group nav** —
   **Operate:** submit samplesheet (register a run's SampleSheet/FASTQ and hand off to the
   `POST /api/runs` execution boundary — REQ-F-067; compose≠execute still holds at the core),
   runs overview (per-verdict counts + needs-attention + a client-side scale kit: search/facet/
   sort/date-range/paginate; the top-bar run switcher shares the Runs list's status-derived dot
   via `RUN_STATUS_META`, fixing a bug where the switcher's dot read `n_attention` instead of the
   real lifecycle `status`), intake/preflight (run-level QC rollup + per-sample admission with
   manual override), decision cards (verdict + per-gate strip + a QC-readout hero from
   REQ-F-064/REQ-F-068 + cited evidence), review queue (tickets w/ role-gated actions, REQ-F-063);
   **Analyze:** provenance (pipeline **compute-DAG** with a per-stage data-I/O drill-in), agent
   triage (advisory note + citations + offline/live), monitoring (windowed aggregate,
   REQ-F-047); **Configure:** pipeline builder (REQ-F-045) and settings (runbook thresholds,
   labelled illustrative). A separate, **approver-gated Admin** governance screen sits outside
   this operator nav (REQ-F-066) — off the deterministic gate, it is not counted among the 10.
   A shared `RoleContext` (reviewer|approver) drives every RBAC-gated control, and now exposes a
   full `setActor(actor)` (id+role together) consumed by Admin's "Act as" (REQ-F-066). Screens
   state their data boundary rather than fabricate instrument/compute artifacts the FASTQ-first
   build doesn't capture; one now-honest gap is explicitly rendered empty rather than invented:
   Monitoring's Median-review KPI (no backend field — its signature-level `first_seen`/
   `last_seen`/`trend`/`affected_run_ids` fields ARE shipped, REQ-F-047) and Provenance artifact
   links (`RunArtifact` has no `url`). *Trace:* [demo_plan.md](../demo/demo_plan.md),
   [architecture.md](../design/architecture.md),
   [tasks T-022/T-022b/T-037/T-044/T-062](../planning/tasks.md),
   [journal 2026-07-09 frontend-batch2](../journal/2026-07-09-frontend-batch2.md).
4. **REQ-F-044 — In-app feedback (off-gate telemetry).** The app captures product feedback
   via the app's first write endpoint (now one of several off-gate product-domain writes),
   `POST /api/feedback` — a per-decision agree/disagree signal
   (keyed to verdict + gate + rule ids + card hash) and a global product note, each tagged with
   the originating UI `source`. It is **off the deterministic gate** (never mutates a
   verdict/provenance event; ADR-0001), carries **no operator identity** (`extra="forbid"`
   structural guard), and resolves `origin` server-side. The sink is a **pluggable store**
   (JSONL default / SQLite / Postgres, `PIPEGUARD_FEEDBACK_STORE`) with its own table, separate
   from the decision projection and degrading to JSONL (ADR-0016). An **advisory feedback agent**
   (`python -m api.feedback_agent`, stub/claude) categorizes the corpus structurally out-of-band.
   *Trace:* [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md),
   [ADR-0016](../adr/ADR-0016-postgres-port.md), [tasks T-042/T-043](../planning/tasks.md).
5. **REQ-F-043 — Offline fallback view.** A Streamlit app renders the same core
   offline, in one process, as the guaranteed-working demo fallback. *Trace:*
   [demo_plan.md](../demo/demo_plan.md), ADR-0014.
6. **REQ-F-045 — Pipeline Builder (compose ≠ execute).** An editable node-graph screen
   (the superset of the Provenance canvas) lets an operator configure the germline pipeline
   and **emit `run_layout.yaml`** across profiles. It **composes, never executes** (the
   primary action is Emit, never Run), and renders the load-bearing invariants as visible
   guarantees: agents are port-less side-nodes (an agent→gate data edge is unrepresentable),
   the deterministic gate is a terminal locked node with no verdict control, and every emitted
   locator's `origin` is `unknown` (config locates, never relabels provenance). A composed graph
   **saves + versions** via `POST/GET /api/pipelines` — a **product-domain store off the gate**
   (pluggable JSONL/SQLite/Postgres, `PIPEGUARD_PIPELINE_STORE`, degrade-to-JSONL, ADR-0016),
   storing the graph as a **tolerant versioned envelope** (arbitrary payload kept as-is) with a
   server-authored monotonic per-name version. It **reserves** a `draft→save→approve` review
   lifecycle (`status` + reviewer/approver fields, server-authored, no identity via the
   `extra="forbid"` body); the approve transition + auth are now realized in REQ-F-061
   (`api/routers/pipelines_lifecycle.py` + `api/auth.py`,
   [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md)). **Frontend rebuild
   (2026-07-09, Wave 3):** the screen now also ships free composition (add/drag/delete
   user nodes from the palette), a typed-port **Connect mode** (kind-matched wiring only,
   INV-e), a minimap, and editable Locators with live YAML regen. **Write-wiring fix
   (2026-07-09 maintainer batch, commit `586f832`):** Save now chains `savePipeline` →
   `submitPipeline` (draft → pending_review, so Approve's `pending_review` precondition is
   met — previously 409'd) and the doc name is slugified for the backend; Save/Approve both
   **await the response and reconcile local `version`/`status` from it** (toasted
   success/failure via the new `Toast` system), no longer fire-and-forget. **Dry-run/Diff wired
   to the real endpoints (2026-07-10, T-096, commit `4208f0b`, "Item E"):** once the graph is
   Saved (exists in the pipeline store), the console's Dry-run tab calls `POST
   /api/pipelines/{name}/dry-run?run_id=…` (REQ-F-061) — via a plain run-id text input —
   rendering the
   real per-locator matched/ambiguous/missing/invalid resolution + summary, and the Diff tab
   calls `GET /api/pipelines/{name}/diff` (REQ-F-061), rendering added/changed/removed vs the
   approved baseline (or "no baseline yet"); both fall back to the earlier client-side preview
   before Save. This closes the previous "known, labelled limitation" (Dry-run/Diff existed in
   `api.ts` but the Builder screen never called them — not a fabricated success, since the
   console rendered from local state and never claimed a server round trip). **Run-selector +
   advisory-modal wiring + saved-profiles (2026-07-10, commits `34bca5d`→`adfd7aa`, T-069/T-070,
   closing both):** the Dry-run run-id text box is now a reusable, searchable `RunSelector`
   (`frontend/src/components/RunSelector.tsx`, T-070 — an 8-row-capped combobox sharing the
   top-bar switcher idiom, real `RUN_STATUS_META` status dot per F17, self-fetching `api.runs()`
   lazily with an honest "Couldn't load runs" on failure). The "Pipeline-repair" / "Archivist"
   modals — previously **static UI previews** labelled `phase-2` in-app — now call the live
   advisory-agent endpoints (T-069, REQ-F-041): `PipelineRepairModal` → `GET /api/monitoring`
   (a recurring-signature picker) + `GET /api/monitoring/signatures/{sig}/repair` → the real
   `RepairProposal`, each corpus citation labelled with a **"heuristic" score, never
   "confidence"** ("Send to review queue" navigates to `/queue`, never fabricates a ticket);
   `ArchivistModal` → `GET /api/archive/index` → the real cross-run `ArchiveDigest` ("Queue
   archive" stays inert — no write endpoint exists). The `RunHandoffModal` now shows the real
   composed `run_layout.yaml`, and a new toolbar **"Open"** action lists `GET /api/pipelines` and
   hydrates the canvas from a chosen saved graph (closing the earlier "saved-profiles has no
   backend seam" gap) — approved graphs open read-only, re-saving mints a new draft, and a
   foreign/topology-less envelope loads empty with a labelled toast rather than fabricated nodes.
   **Only the "Author a tool node" modal remains a static `phase-2` preview** — see
   [tasks T-046](../planning/tasks.md), a proposed-not-built design note, unaffected by this
   batch. **Editable template fix (2026-07-09, commit `01ba673`,
   [tasks T-075](../planning/tasks.md)):** "New → From template" previously re-showed the
   read-only seeded DAG, so the demo's own pipeline couldn't be modified in Edit;
   `germlineTemplate()` now instantiates the same fastp→…→MultiQC chain as real, editable
   `UserNode`/`UserEdge`s, and `showSeeded` is gated on `isLinked` so **only** the original
   linked pipeline still renders read-only — Save now sends the true composed 7-node graph
   (was empty for the seeded doc). **Canvas + palette polish (2026-07-10, commits
   `14c9f3c`/`c6a6210`, T-085/T-086):** Tidy is now a **flow-preserving auto-layout** — each
   node's longest-path depth from a source is relaxed over the composed edges, then placed in
   the column of its depth with parallel nodes stacked, so upstream→downstream reads
   left→right instead of one row losing the connection structure; a **Cancel** button
   (draft-only) discards an in-progress build and returns to the linked pipeline in View; the
   minimap moved bottom-right→top-right. The palette gained a **References** section
   (Reference FASTA/Panel BED/Truth VCF — no-input source nodes emitting their reference
   artifact, typed-wired so a fasta can't land on a fastq port), fixing the earlier "no way to
   add bed/vcf/reference cards" gap, and its sections are now **collapsible** (chevron +
   per-section count, overridden by an active search). *Trace:*
   [pipeline-builder-brief.md](../design/frontend/pipeline-builder-brief.md),
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md),
   [journal 2026-07-09 frontend-batch2](../journal/2026-07-09-frontend-batch2.md),
   [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md),
   [journal 2026-07-10 batch6](../journal/2026-07-10-admin-settings-builder-wiring.md),
   [journal 2026-07-10 batch7](../journal/2026-07-10-builder-modals-and-run-selector.md),
   [tasks T-044/T-049/T-062/T-069/T-070/T-085/T-086/T-096](../planning/tasks.md).
7. **REQ-F-046 — Honest run lifecycle status + run metadata.** `RunSummary` carries a real
   `status` — `running` (no completion event yet) / `needs_review` (completed, actionable
   samples) / `released` (completed, none) — derived from the provenance ledger, **not** inferred
   from `n_attention` (which mislabeled a still-running, 0-attention run as Released). It also
   surfaces `platform` + `run_date`, parsed tolerantly from the SampleSheet `[Header]`. `status`
   is a run-lifecycle label, never a per-sample verdict (REQ-F-003 holds). *Trace:*
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md),
   [schemas.md](../data/schemas.md), [tasks T-047](../planning/tasks.md).
8. **REQ-F-047 — Server-side monitoring aggregate + runs pagination.** `GET /api/monitoring`
   returns a pre-aggregated, optionally time-windowed (7d/14d/30d/all) dashboard payload (KPIs,
   per-run rows, per-gate pass-rate, ranked recurring signatures) so the UI needn't fan out every
   run's detail; its throughput ratio is a labelled **heuristic**, not a calibrated value. Each
   ranked signature ADDITIVELY carries `first_seen`/`last_seen` (earliest/latest `[Header]` run
   date, `None` when undated — never fabricated), `trend` (up/down/flat, a display heuristic
   comparing the window's recent vs older half by count — not a calibrated rate), and
   `affected_run_ids` (distinct, chronological); the payload stays backward-compatible. A
   Median-review-time KPI stays a documented, not-yet-built seam. `GET /api/runs` accepts
   additive `verdict/q/sort/page/limit` (no params → byte-identical body;
   count/page/limit on response headers). **Signatures-list pagination (2026-07-09, commit
   `e5d5043`, [tasks T-076](../planning/tasks.md)):** `Monitoring.tsx` now paginates the
   recurring-signatures grid client-side (25/50/100 + pager), mirroring the Runs-list pattern —
   distinct from [tasks T-072](../planning/tasks.md), the *per-run* `rows: list[MonitoringRunRow]`
   on the same response. **Per-run pagination, frontend half (2026-07-10, commit `34bca5d`,
   [tasks T-072](../planning/tasks.md)):** the throughput card's per-run columns now paginate the
   same way (25/50/100 + pager, "Showing X–Y of N runs," independent state, reset on
   window/date-range/per-page change) — **this closes only the frontend half**; the `rows[]`
   payload itself is still returned uncapped by `get_monitoring`, so T-072 stays open for the
   backend cap. *Trace:*
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md),
   [architecture.md](../design/architecture.md), [tasks T-048/T-072](../planning/tasks.md).

## AI configurability (ADR-0006)

1. **REQ-F-050 — Env-flippable AI, off by default.** Every AI seam flips via env, each
   defaulting to `stub` ($0, offline): the synthesizer (`PIPEGUARD_SYNTHESIZER`) plus the four
   advisory agents — QC-triage (`PIPEGUARD_TRIAGE_AGENT`), off-gate feedback
   (`PIPEGUARD_FEEDBACK_AGENT`), pipeline-repair (`PIPEGUARD_PIPELINE_REPAIR_AGENT`), and archivist
   (`PIPEGUARD_ARCHIVIST_AGENT`) — all `stub|claude`; model via `PIPEGUARD_*_MODEL`. *Trace:*
   [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md), [architecture.md](../design/architecture.md)
   §Swappable seams, [agents.md](../design/agents.md).
2. **REQ-F-051 — Deterministic fallback on failure.** If an AI call is disabled,
   errors, or is refused by a safety classifier, the system degrades to the stub;
   the deterministic verdict and findings still stand. *Trace:* ADR-0006,
   [demo_plan.md](../demo/demo_plan.md) §Fallbacks.

## Authoring lifecycle, RBAC & operator surfaces (ADR-0010/0014/0016/0017)

Backend surfaces layered **over** the read-API, all **additive/backward-compatible**,
**off the deterministic gate** (never set/override a verdict, confidence, or provenance
event; ADR-0001), and **offline-testable** with no auth wiring. They realize the
`draft→approve` review lifecycle, RBAC, and operator-workflow endpoints the
[backend-contracts handoff](../design/frontend/handoffs/2026-07-09-backend-contracts.md)
had reserved or listed as *not-yet-built*.

1. **REQ-F-060 — Identity + RBAC primitive (DEV SHIM).** `api/auth.py` gives the
   write/authoring surfaces one shared current-user + role source: a `Role`
   (**viewer | reviewer | approver**), an `Actor{id, role}`, `current_actor()` reading the
   `X-PipeGuard-Actor` / `X-PipeGuard-Role` request headers with a **permissive DEV-DEFAULT**
   (`id=dev`, `role=approver`) so the offline demo and tests need no auth wiring, and
   `require_role(*roles)` (raises **403** on an insufficient role). It is explicitly a
   documented **DEV SHIM** — it *trusts* the headers, so it is trivially **spoofable** and is
   **not** real authentication — behind a single swap point for a production identity provider.
   It grants access only; it never touches a verdict or finding (ADR-0001). *Trace:*
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md) §"NOT built #2",
   [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md),
   [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md),
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md).
2. **REQ-F-061 — Pipeline approve lifecycle.** `api/routers/pipelines_lifecycle.py` realizes
   the `draft→save→approve` review flow that REQ-F-045 previously only **reserved** on the
   pipeline envelope: `POST /api/pipelines/{name}/submit` (draft → **pending_review**,
   reviewer+), `/approve` (pending_review → **approved**, **approver-only**, stamps
   `approved_by` + records the diff baseline), `/dry-run?run_id=…` — a **READ-ONLY** locator
   resolver that checks a composed graph's locators against a real run directory
   (**compose ≠ execute**: it never triggers a run — ADR-0001/0003), and
   `GET /api/pipelines/{name}/diff` (vs the last emitted/approved version). Role gates come from
   `require_role` (REQ-F-060). *Trace:*
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md) §4/§"NOT built #2",
   [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md),
   [ADR-0016](../adr/ADR-0016-postgres-port.md),
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)/[ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md),
   [tasks T-049](../planning/tasks.md).
3. **REQ-F-062 — Config/settings authoring store *(wishlist T-051)*.** `api/routers/settings.py`
   + `api/settings_store.py` add `draft→save→approve` **config-override** authoring with
   reviewer/approver RBAC (REQ-F-060), an audit trail, and **lenient sanity guardrails** (range
   checks, not clinical thresholds), storing each override as a **tolerant versioned envelope** in
   a pluggable store (`PIPEGUARD_SETTINGS_STORE=jsonl|sqlite|postgres`, degrade-to-JSONL, ADR-0016),
   mirroring the pipeline store (REQ-F-045). The override `name` is a server-validated **slug**
   (`^[A-Za-z0-9][A-Za-z0-9._-]*$`); the Settings screen now **slugifies** the display assay
   string before POSTing (2026-07-09 maintainer batch — the un-slugified name 422'd save and
   404'd approve). It **does NOT mutate the live runbook** — actually
   applying an approved override to a run is a documented **off-gate seam**, not yet wired, so
   REQ-F-015 (runbook profiles decide thresholds) still holds. **Sample-type dropdown
   (2026-07-10, T-095, commit `869cf55`, "S1"):** `SettingsAssayTable.tsx`'s threshold matrix
   previously showed Whole-blood and Saliva as two side-by-side columns; a Sample-type dropdown
   beside the Assay selector now picks one tissue at a time and the table shows a single value
   column — a pure presentation change (cleaner, scales as more sample types are added).
   Editing/save/approve, the per-tissue values, and the audit lifecycle above are unchanged
   (still keyed on assay × sample type). *Trace:*
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md) §"NOT built #1",
   [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md),
   [ADR-0016](../adr/ADR-0016-postgres-port.md),
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   [journal 2026-07-10 batch6](../journal/2026-07-10-admin-settings-builder-wiring.md),
   [tasks T-051/T-095](../planning/tasks.md).
4. **REQ-F-063 — Review-queue / ticket domain.** `api/routers/review_queue.py` +
   `api/review_store.py` back the review-queue screen (REQ-F-042) with a persisted ticket
   domain: create/list tickets plus a **role-gated action lifecycle**
   (acknowledge / resolve / escalate / suppress / reopen — **all reviewer+approver** via
   `require_role`, REQ-F-060; RBAC relaxed 2026-07-09 (commit `586f832`) from an earlier
   approver-only resolve/suppress to match the design's reviewer-resolves-hold/rerun-ticket
   model — an escalate ticket's approver-only nuance stays a UI-level distinction, not this
   backend gate), a ticket `status`
   ∈ **open | in_review | resolved**, and recorded review-action timestamps. It is **off-gate** —
   a ticket, suppression, or resolution never changes a verdict or a finding (ADR-0001,
   consistent with REQ-F-004). *Trace:*
   [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md),
   [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md),
   [ADR-0016](../adr/ADR-0016-postgres-port.md),
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), REQ-F-042.
5. **REQ-F-064 — Decision-card QC readout (pure projection).** `api/card_readout.py` exposes
   `GET /api/runs/{id}/cards/{sid}/qc-readout` → an **API-layer projection** that joins the
   card's `metric_values` with the runbook `QCThreshold`s into a **gate-grouped
   Metric · Observed · Threshold · Status** table for the MetricsPanel (REQ-F-042 / T-045). It is
   read-only and **derives nothing new** — the core `DecisionCard`, its findings, and the gate are
   untouched (ADR-0001); Status is a deterministic restatement of the already-decided gate, not a
   re-evaluation. An ungated metric row is labelled with the registry's **display name** (e.g.
   "Ts/Tv ratio"), not the raw `our_key` (2026-07-10, `a9b06ad`). *Trace:* [schemas.md](../data/schemas.md) §DecisionCard/QC,
   [qc_metrics.md](../data/qc_metrics.md),
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [tasks T-045](../planning/tasks.md).
6. **REQ-F-065 — Runs-list reconciliations (Tier-0).** `GET /api/runs` gains, on top of the
   additive params in REQ-F-047: a `status` filter (**running | needs_review | released**, keyed to
   the honest lifecycle of REQ-F-046), `q` now matching **run_id OR platform** (case-insensitive,
   was run_id only), friendly sort aliases (**recent / urgent / date** over the raw sort keys), and
   **per-status facet counts** returned on an `X-PipeGuard-Status-Counts` response header. All
   optional and additive — no params still yields a byte-identical `RunSummary[]` body (REQ-F-047).
   *Trace:* [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md) §2,
   [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md), REQ-F-046/REQ-F-047,
   [tasks T-048](../planning/tasks.md).
7. **REQ-F-066 — Admin panel (`isAdmin`-gated governance, off-gate).** A `frontend/src/screens/Admin.tsx`
   screen at `/admin`, visible only when the LOGGED-IN identity's `isAdmin` is true — nav-gated in
   `Sidebar.tsx`, not a backend permission of its own. **Corrected 2026-07-10 (T-081,** commit
   `0f7e85f`**):** `isAdmin` is a **frontend-only governance capability** (`frontend/src/auth.ts`
   `ADMIN_IDS`, derived from the demo login roster — REQ-F-069) layered over the wire roles
   (viewer/reviewer/approver), distinct from "any approver" — an admin is an approver who *also*
   holds governance; `isAdmin` follows the **login** identity (`session`), not the "Act as" actor,
   so an admin can preview another role and still return. (Originally gated on "any approver";
   that framing is now stale and superseded by this row.) Three tabs: **(a) Users & roles** — an explicit **client-mock** roster (there is no
   backend user store; `api/auth.py` is a header dev-shim) with a per-user role selector and an
   "Act as" control wired to `RoleContext.setActor` (switches id+role together) so an operator can
   preview any seeded actor's RBAC surface, plus a persistent "dev auth shim, not an identity
   system" banner. **Role-staging (2026-07-10, T-092, commit `5774143`, "A1"):** a role change
   no longer applies on the first click of a toggle (a stray click could reassign a role) —
   the control is a dropdown, and a change **stages into a draft** ("unsaved" badge) behind an
   explicit Save/Discard bar; only Save writes the roster (re-syncing the live actor if its own
   role changed), and "Act as" now confirms before impersonating. Still the same client-mock
   roster ([risks.md](../quality/risks.md) RISK-035) — this hardens the legitimate UI path, not
   the underlying (already non-production) security boundary; **(b) Activity log** — a REAL, zero-new-backend audit feed merging
   `GET /api/settings/thresholds` + `GET /api/pipelines` + `GET /api/review/tickets` into one
   append-only when/actor/kind/target/status table, facet-filterable by kind (threshold/pipeline/
   ticket). **Paginated + expandable (2026-07-10, T-093, commit `8a14661`, "A2"):** the
   previously flat, uncapped list now paginates 25/50/100 with a numbered pager ("Showing X–Y of
   Z," resets on filter change), and each row is a compact summary expanding on click to a
   labelled Detail/Target/Actor/When panel (one open at a time); no backend change; **(c) System**
   — REAL reads of `GET /api/health` (new, trivial liveness endpoint) +
   the runbook's gate count + the metric-registry version/gated-count, labelled
   illustrative-not-clinical. **Built out (2026-07-10, T-094, commit `7c56564`, "A3/A4"):** gained
   an **Artifact-store** stat card (`local` · the `PIPEGUARD_ARTIFACT_STORE` s3 seam, built
   [tasks T-039](../planning/tasks.md), [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md)
   §3) and an **Observability** section linking the read-API's `/metrics` exporter,
   Prometheus (`:9090`), and the Grafana "PipeGuard — QC decision gate" dashboard (`:3000`, built
   under the telemetry-connector work) as off-demo-path links, with a note on bringing up the
   `deploy/telemetry/` compose stack; Users & roles also gained a per-user
   **password/email-reset** action — a labelled production seam (no live mail) that toasts what
   would happen rather than sending anything. Admin decides **who** may perform an off-gate product write and
   whose id lands in an audit `*_by` field — it never sets, overrides, or displays a
   verdict/finding/confidence, and carries **no confidence meter** (ADR-0001; life-science
   guardrail 2). *Trace:* [architecture.md](../design/architecture.md) §4,
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md), REQ-F-060, REQ-F-069,
   [journal 2026-07-09 frontend-batch2](../journal/2026-07-09-frontend-batch2.md) (commit
   `ce396f7`), [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md)
   (commit `5774143`),
   [journal 2026-07-10 batch6](../journal/2026-07-10-admin-settings-builder-wiring.md) (commits
   `8a14661`, `7c56564`), [tasks T-066/T-092/T-093/T-094](../planning/tasks.md).
8. **REQ-F-067 — Samplesheet submission triggers the real pipeline (execution boundary).**
   `POST /api/runs` (new `api/routers/intake.py`) registers a submitted samplesheet and
   **triggers** `scripts/run_giab_pipeline.py` as a background subprocess (an in-process job
   registry; `require_role(reviewer|approver)`; 409 on a duplicate run id), turning
   `data/<run_id>/` into a gate-able run; `GET /api/runs/{id}/intake-status` polls
   `queued|running|complete|failed`. This demo build only has real reads on disk for `HG002` —
   other submitted samples are **honestly skipped** (registered, reported, never fabricated a
   run for), and a submission with no processable sample 422s. **Compose ≠ execute still holds
   at the core:** `src/pipeguard/` never runs a tool — only the API layer triggers the external
   driver, mirroring the Pipeline Builder's hand-off concept (REQ-F-045) but now wired end to
   end. Reframes the earlier "Submit never runs anything" framing to "Submit hands off to an
   execution boundary." *Trace:* [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   [ADR-0003](../adr/ADR-0003-deployment-agnostic-ports.md),
   [journal 2026-07-09 frontend-batch3](../journal/2026-07-09-frontend-batch3.md) (commit
   `e77c2e6`), [tasks T-057](../planning/tasks.md).
9. **REQ-F-068 — Honest three-gate decision-card readout.** The QC-readout hero always shows
   all **three** gates (preflight → qc → variant), never silently dropping one. `GET
   /api/runbook`'s `RunbookThreshold` carries `pipeline_gate: Gate` (from the metric registry),
   distinct from the numeric `gate` threshold *value* — the two were previously conflated, so a
   client-side filter comparing a value to the gate enum silently never matched and the
   preflight/variant groups vanished. Per gate: a real measured-metric group if the card
   populated one; else the runbook's thresholds rendered as `not_measured` placeholder rows
   (REQ-F-064); else an **honest empty-state note** — preflight is rule-based (scored via the
   gate strip + cited evidence, not a metric table) and variant extracts no gating metrics in
   this build — never a fabricated row. The gate stays byte-for-byte unchanged; no
   preflight/variant thresholds were added to the runbook (doing so would spuriously flag every
   card via `rules.py`'s QC-\*-NA path). *Trace:*
   [qc_metrics.md](../data/qc_metrics.md) §Verdict policy, REQ-F-064,
   [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md),
   [journal 2026-07-09 frontend-batch3](../journal/2026-07-09-frontend-batch3.md) (commit
   `12ffa30`), [tasks T-073](../planning/tasks.md).
10. **REQ-F-069 — Demo login gate (frontend, NOT production auth).** A login screen
    (`frontend/src/screens/Login.tsx`) fronts every route; `App.tsx`'s `RequireAuth` redirects an
    unauthenticated visit to `/login` and preserves the intended destination. Four demo accounts
    (`frontend/src/auth.ts`: viewer / reviewer / approver / admin, one shared password) map to the
    same `Actor{id, role}` the API already consumes via `X-PipeGuard-Actor`/`-Role` (REQ-F-060) —
    login simply chooses which actor the app acts as; the session (`{id, role}` only, **no
    token/password**) persists to `localStorage` so a refresh stays signed in. Every production
    seam is a **labelled placeholder, not implemented**: OAuth/OIDC against a real IdP, server-side
    password hashing (argon2/bcrypt — passwords never reach the client), an httpOnly/Secure/
    SameSite session cookie or JWT+refresh, a real CAPTCHA, signed password-reset links, and TLS.
    A generic "Incorrect email or password" message never reveals which field missed. This is a
    **demo-only client-side gate** — it adds no server-side protection; `api/auth.py`'s header
    dev-shim (REQ-F-060) is unchanged and remains the actual (also non-production) authorization
    boundary. *Trace:* [architecture.md](../design/architecture.md) §4,
    [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md) §Realized addendum,
    REQ-F-060, REQ-F-066, [risks.md](../quality/risks.md) RISK-035,
    [journal 2026-07-10](../journal/2026-07-10-provenance-qc-builder-auth.md) (commit `0f7e85f`),
    [tasks T-081](../planning/tasks.md).
11. **REQ-F-070 — Provenance artifact download + full-digest reveal.** `GET
    /api/runs/{id}/artifacts/{name}` (`api/main.py`) serves the named artifact's bytes
    (`FileResponse`); the name must be a bare filename and the resolved path must stay inside the
    run directory (traversal-hardened — a `..`/absolute name 404s, never serves outside the run
    dir). `RunArtifact` gained a `url` field pointing at it, closing the earlier "no download URL"
    gap. The Provenance screen's digest column now offers a "show full" toggle revealing all 64 hex
    characters, and — a defense-in-depth UI choice, not a wire-format change — labels the field
    "hash"/"content hash" rather than naming "sha256" on screen (Provenance + the Archivist
    manifest modal); the underlying field is unchanged content-hash sha256
    ([schemas.md](../data/schemas.md) §ArtifactRef). The artifact-stage map (`_ARTIFACT_STAGE`)
    now attaches each file to a **list** of `(stage, role)` edges (was one), so
    `demux_stats.csv`/`reads` are both the demux stage's OUTPUT and the QC stage's INPUT — the
    same bytes feed the QC node in the Provenance compute-DAG (REQ-F-042), which previously
    rendered with no input edge at all. **View vs. download split (2026-07-10, T-090, commit
    `de5fa94`):** the endpoint gained `download: bool = False` — `Content-Disposition` is
    `inline` by default (name-click views the artifact at its location) and `attachment` only on
    `?download=1` (the Download button); previously both hit the same always-attachment URL and
    both forced a save. The Provenance screen also gained a hover explainer distinguishing
    `sample_metadata.csv` (intake · LIMS/subject sheet) from `SampleSheet.csv` (demux · Illumina
    barcode manifest) — the difference previously lived only in the stage grouping. *Trace:*
    [architecture.md](../design/architecture.md) §4,
    REQ-F-040, [journal 2026-07-10](../journal/2026-07-10-provenance-qc-builder-auth.md) (commits
    `71a06d6`, `eb7d016`),
    [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md) (commit
    `de5fa94`), [tasks T-077/T-080/T-090](../planning/tasks.md).
12. **REQ-F-071 — QC enrichment: registered preflight/QC/variant metrics wired end-to-end.** The
    core `QCMetrics` model, `parsers.parse_qc_metrics`, and the QCMetrics→registry mapping gain 8
    additional registered fields beyond the frozen-CSV five (`preflight.phix_aligned`;
    `qc.breadth_20x`/`breadth_30x`/`pct_mapped`/`on_target`; `variant.dp`/`gq`/`titv`,
    [schemas.md](../data/schemas.md)), each `None`-tolerant so a run that omits them is unchanged.
    `runbook.QCThreshold` gains `required: bool = True`; 5 of the 8 gain an **optional**
    (`required=False`) threshold that scores a value that IS present but never NA-flags one that's
    absent (REQ-F-016 still holds — gating stays on the registry's canonical, normalized value).
    This closes a real gap: the decision-card readout's **preflight** and **variant** gate groups
    (REQ-F-068) previously showed an empty-state note for *every* run, with no code path that
    could ever populate them; they now populate with real measured rows when a run's QC report
    carries the data. The synthetic generator emits all 8 (contrived, comfortably passing, so
    failure-mode coverage stays exactly on the original frozen five); the real GIAB HG002 driver
    additionally writes its own real `breadth_20x`/`breadth_30x` from mosdepth (not contrived) —
    the metric catalog is now 10 gated / 10 ungated of 20 registered `our_key`s
    ([metric_registry.md](../data/metric_registry.md) §Wiring status), and 7 registered metrics
    remain unwired (an honest, pre-existing gap, not introduced by this change). Gate verdict
    logic and every pinned demo verdict are unchanged. *Trace:* [qc_metrics.md](../data/qc_metrics.md)
    §Implementation status, REQ-F-012/REQ-F-013/REQ-F-064/REQ-F-068,
    [journal 2026-07-10](../journal/2026-07-10-provenance-qc-builder-auth.md) (commits `a8fc73b`,
    `a9b06ad`), [tasks T-082](../planning/tasks.md).
13. **REQ-F-072 — Gate dependency: an unclear upstream gate blocks its downstream ones
    (re-presentation).** The maintainer's two-tier gate model: sequencing-tier QC (preflight)
    gates sample **processing**; sample-tier QC gates **downstream analysis** (variant). Every
    gate the QC-readout hero renders now carries `blocked_by: Gate | None`
    (`api/card_readout.py`'s `GateReadout`): `build_qc_readout` marks a gate "not clear" when the
    card carries a non-`PROCEED` `gate_result` for it, then `_blocking_gate()` returns the
    nearest **upstream** not-clear gate. A gate blocked this way renders "blocked · clear
    \<upstream\> first" instead of "all clear" (a `hold`-toned pill, taking priority over
    "all clear"/`not_measured`), so a QC hold no longer looks like the sample proceeded to
    variant calling. **Pure re-presentation, no rule or verdict change** — the card's verdict
    already reflects the upstream finding (REQ-F-003, REQ-F-014 hold); confirmed by diff that
    `rules.py`/`synthesis/` are untouched. The frontend (`MetricsPanel.tsx`'s `Rollup`,
    `RunDetail.tsx`'s `CardBody`) mirrors the same nearest-upstream computation for the
    placeholder/empty gate groups it synthesizes client-side (REQ-F-068), so the presentation is
    consistent whether or not the API returned real rows for that gate. New test
    `test_qc_hold_blocks_the_downstream_variant_gate` (`tests/test_card_readout.py`). This is
    "part 1" of the two-tier model per the maintainer. **Part 2 — user-clearable HOLD/ESCALATE,
    individually + in batches — shipped 2026-07-10 (T-097, commit `a8fd059`):** the review-queue
    screen (`ReviewQueue.tsx`, REQ-F-042/REQ-F-063) now gives reviewers+ a select checkbox on every
    still-open (open/in-review) ticket plus a per-run select-all in the group subheader; selecting
    ≥1 raises a sticky batch bar ("N selected — Resolve selected / Suppress selected / Cancel")
    that reuses the **same backend-persisted** per-ticket `act()`/`toggleSuppress()` path
    (materialize ticket → `ticketAction`), so a bulk clear persists exactly like a single click
    (verified across a reload: Open 88→86, Resolved 1→3). Selection resolves against the live
    ticket list each render, so a key that has since left the clearable set can't re-fire an
    action; viewers see no checkboxes. The DC2 model's "HOLD is a *state*, ESCALATE is *requesting
    input*, both clearable" is thus realized — off-gate (clearing a ticket never moves a verdict,
    ADR-0001). *Trace:*
    [architecture.md](../design/architecture.md) §4, REQ-F-003, REQ-F-014, REQ-F-042, REQ-F-063,
    REQ-F-064, REQ-F-068,
    [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
    [ADR-0008](../adr/ADR-0008-issue-taxonomy-suppression-escalation.md),
    [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md),
    [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md) (commit
    `545c893`), [journal 2026-07-10 batch6](../journal/2026-07-10-admin-settings-builder-wiring.md)
    (commit `a8fd059`), [tasks T-087/T-097](../planning/tasks.md).
14. **REQ-F-073 — Persisted user preferences (theme, density).** A new
    `frontend/src/context/PrefsContext.tsx` makes the Settings dialog's Theme
    (light/dark/system) and Density (split/brief/dense) controls real, `localStorage`-persisted
    preferences, replacing local state wired to nothing. Theme resolves `system` via
    `matchMedia('(prefers-color-scheme: dark)')` and stamps `document.documentElement.dataset.theme`,
    following the OS live while on `system`; a full dark theme in `index.css`
    (`:root[data-theme="dark"]` overriding the `@theme --color-*` custom properties — page/card/
    surfaces/text/accent + dark verdict bg/border/fg + shadows) retargets every existing Tailwind
    utility with **no per-component change**. Density is now **one** setting read/written by
    both the Settings dialog and `RunDetail.tsx`'s own card-Layout control (previously two
    independent, disconnected `useState`s), so the operator's choice survives across runs and a
    page refresh. This is a **client-only demo preference store**, not a server-synced profile
    (a production seam, like the auth session, REQ-F-069) — it never touches a verdict, finding,
    or the provenance ledger. *Trace:* [design/frontend/README.md](../design/frontend/README.md)
    §4, [journal 2026-07-10 batch5](../journal/2026-07-10-batch5-builder-card-admin-prefs.md)
    (commit `08a42ad`), [tasks T-091](../planning/tasks.md).

## Notes / deferred

1. **Notify port** is built + verified — **Slack** (T-015b, live-verified) plus **Teams +
   Discord** webhook adapters (T-035, stdlib `urllib.request`, per-adapter live flag,
   stub-default). Only the **Jira** ticket-create adapter and wiring notify into the
   read-API/ticketing flow remain *(wishlist)*.
2. **Variant gate** (REQ-F-013) is Phase 2 and depends on real variant-level data.

---

*Marker legend:* **Fact** · **Assumption** · **Decision** · **TODO**. In-scope vs
deferred boundaries are authoritative in [scope-and-wishlist.md](scope-and-wishlist.md).
