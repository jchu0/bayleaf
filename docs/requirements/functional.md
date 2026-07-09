# Functional Requirements

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-09 (MST) |
| **Audience** | software / all |
| **Related** | [scope-and-wishlist.md](scope-and-wishlist.md), [nonfunctional.md](nonfunctional.md), [constraints.md](constraints.md), [design/architecture.md](../design/architecture.md), [metric_registry.md](../data/metric_registry.md), [schemas.md](../data/schemas.md), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md), [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md) |

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
2. **REQ-F-041 — On-demand triage endpoint.** The API exposes a per-card triage call
   that invokes the advisory agent without re-entering the verdict path. *Trace:*
   [architecture.md](../design/architecture.md), ADR-0010.
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
   via the one write endpoint, `POST /api/feedback` — a per-decision agree/disagree signal
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
   locator's `origin` is `unknown` (config locates, never relabels provenance). *Trace:*
   [pipeline-builder-brief.md](../design/frontend/pipeline-builder-brief.md), [tasks T-044](../planning/tasks.md).

## AI configurability (ADR-0006)

1. **REQ-F-050 — Env-flippable AI, off by default.** Both AI seams flip via env —
   `PIPEGUARD_SYNTHESIZER=stub|claude` and `PIPEGUARD_TRIAGE_AGENT=stub|claude`
   (default `stub`, $0, offline); model via `PIPEGUARD_*_MODEL`. *Trace:*
   [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md), [architecture.md](../design/architecture.md)
   §Swappable seams.
2. **REQ-F-051 — Deterministic fallback on failure.** If an AI call is disabled,
   errors, or is refused by a safety classifier, the system degrades to the stub;
   the deterministic verdict and findings still stand. *Trace:* ADR-0006,
   [demo_plan.md](../demo/demo_plan.md) §Fallbacks.

## Notes / deferred

1. **Notify port** is built + verified — **Slack** (T-015b, live-verified) plus **Teams +
   Discord** webhook adapters (T-035, stdlib `urllib.request`, per-adapter live flag,
   stub-default). Only the **Jira** ticket-create adapter and wiring notify into the
   read-API/ticketing flow remain *(wishlist)*.
2. **Variant gate** (REQ-F-013) is Phase 2 and depends on real variant-level data.

---

*Marker legend:* **Fact** · **Assumption** · **Decision** · **TODO**. In-scope vs
deferred boundaries are authoritative in [scope-and-wishlist.md](scope-and-wishlist.md).
