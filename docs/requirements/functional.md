# Functional Requirements

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-09 (MST) |
| **Audience** | software / all |
| **Related** | [scope-and-wishlist.md](scope-and-wishlist.md), [nonfunctional.md](nonfunctional.md), [constraints.md](constraints.md), [design/architecture.md](../design/architecture.md), [design/agents.md](../design/agents.md), [data-platform-and-archivist.md](../design/data-platform-and-archivist.md), [metric_registry.md](../data/metric_registry.md), [schemas.md](../data/schemas.md), [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0008](../adr/ADR-0008-issue-taxonomy-suppression-escalation.md), [ADR-0009](../adr/ADR-0009-corpora-retrieval-upskilling.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md), [ADR-0012](../adr/ADR-0012-agent-scoping-model-tiering.md), [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md), [ADR-0016](../adr/ADR-0016-postgres-port.md) |

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
   from the monitoring view (the same `Finding.signature` counter `GET /api/monitoring` uses), the
   system can produce a cited **RepairProposal** {`summary`, `attach_to` (pipeline stage), `scope`
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
3. **REQ-F-042 — Operator screens.** The UI presents the full screen set (**all built +
   migrated 1:1** to the design handoff's light theme, T-022b): run overview (per-verdict
   counts + needs-attention), intake/preflight (run-level QC rollup + per-sample admission
   with manual override), decision cards (verdict + per-gate strip + cited evidence),
   agent triage (advisory note + citations + offline/live), provenance (pipeline
   **compute-DAG** with a per-stage data-I/O drill-in), review queue (tickets w/
   reviewer-vs-approver RBAC + recurring-issue banner), monitoring, and settings (runbook
   thresholds, labelled illustrative). Screens state their data boundary rather than
   fabricate instrument/compute artifacts the FASTQ-first build doesn't capture. *Trace:*
   [demo_plan.md](../demo/demo_plan.md), [architecture.md](../design/architecture.md),
   [tasks T-022/T-022b/T-037](../planning/tasks.md).
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
   [ADR-0017](../adr/ADR-0017-identity-rbac-authoring-lifecycle.md)). *Trace:*
   [pipeline-builder-brief.md](../design/frontend/pipeline-builder-brief.md),
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md),
   [tasks T-044/T-049](../planning/tasks.md).
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
   run's detail; its throughput ratio is a labelled **heuristic**, not a calibrated value.
   `GET /api/runs` accepts additive `verdict/q/sort/page/limit` (no params → byte-identical body;
   count/page/limit on response headers). *Trace:*
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md),
   [architecture.md](../design/architecture.md), [tasks T-048](../planning/tasks.md).

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
   mirroring the pipeline store (REQ-F-045). It **does NOT mutate the live runbook** — actually
   applying an approved override to a run is a documented **off-gate seam**, not yet wired, so
   REQ-F-015 (runbook profiles decide thresholds) still holds. *Trace:*
   [backend-contracts](../design/frontend/handoffs/2026-07-09-backend-contracts.md) §"NOT built #1",
   [ADR-0014](../adr/ADR-0014-productionization-fastapi-react.md),
   [ADR-0016](../adr/ADR-0016-postgres-port.md),
   [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   [tasks T-051](../planning/tasks.md).
4. **REQ-F-063 — Review-queue / ticket domain.** `api/routers/review_queue.py` +
   `api/review_store.py` back the review-queue screen (REQ-F-042) with a persisted ticket
   domain: create/list tickets plus a **role-gated action lifecycle**
   (acknowledge / resolve / escalate / suppress / reopen; **resolve & suppress are
   approver-only**, the rest reviewer+ via `require_role`, REQ-F-060), a ticket `status`
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
   re-evaluation. *Trace:* [schemas.md](../data/schemas.md) §DecisionCard/QC,
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

## Notes / deferred

1. **Notify port** is built + verified — **Slack** (T-015b, live-verified) plus **Teams +
   Discord** webhook adapters (T-035, stdlib `urllib.request`, per-adapter live flag,
   stub-default). Only the **Jira** ticket-create adapter and wiring notify into the
   read-API/ticketing flow remain *(wishlist)*.
2. **Variant gate** (REQ-F-013) is Phase 2 and depends on real variant-level data.

---

*Marker legend:* **Fact** · **Assumption** · **Decision** · **TODO**. In-scope vs
deferred boundaries are authoritative in [scope-and-wishlist.md](scope-and-wishlist.md).
