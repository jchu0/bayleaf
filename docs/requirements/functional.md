# Functional Requirements

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | software / all |
| **Related** | [scope-and-wishlist.md](scope-and-wishlist.md), [nonfunctional.md](nonfunctional.md), [constraints.md](constraints.md), [design/architecture.md](../design/architecture.md), [ADR-0013](../adr/ADR-0013-gate-architecture-verdict-policy.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md) |

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

## Advisory triage agent (ADR-0009/0012)

1. **REQ-F-020 — On-demand triage.** For a flagged card, the system can produce an
   advisory **TriageNote** (likely cause, suggested action, citations) grounded in a
   curated knowledge corpus via a retrieval interface. *Trace:* [architecture.md](../design/architecture.md)
   §Triage agent, ADR-0009.
2. **REQ-F-021 — Advisory only, off the critical path.** The triage agent never sets
   or overrides a verdict/confidence and is not on the deterministic path; its output
   is labelled advisory. *Trace:* [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md),
   ADR-0012.

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
   events, and config over the framework-agnostic core (the production seam). *Trace:*
   [architecture.md](../design/architecture.md), ADR-0010/0014.
2. **REQ-F-041 — On-demand triage endpoint.** The API exposes a per-card triage call
   that invokes the advisory agent without re-entering the verdict path. *Trace:*
   [architecture.md](../design/architecture.md), ADR-0010.
3. **REQ-F-042 — Operator screens.** The UI presents: run overview (per-verdict
   counts + needs-attention), decision cards (verdict + per-gate strip + cited
   evidence), triage, provenance (event trail), review queue, monitoring, and
   settings (runbook thresholds, labelled illustrative). *Trace:* [demo_plan.md](../demo/demo_plan.md),
   [architecture.md](../design/architecture.md); intake / review-queue screens are
   partly backend-blocked ([tasks T-022](../planning/tasks.md)).
4. **REQ-F-043 — Offline fallback view.** A Streamlit app renders the same core
   offline, in one process, as the guaranteed-working demo fallback. *Trace:*
   [demo_plan.md](../demo/demo_plan.md), ADR-0014.

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

1. **Slack notify port** for the triage/review flow is deferred *(wishlist,
   [tasks T-015b](../planning/tasks.md))*.
2. **Variant gate** (REQ-F-013) is Phase 2 and depends on real variant-level data.

---

*Marker legend:* **Fact** · **Assumption** · **Decision** · **TODO**. In-scope vs
deferred boundaries are authoritative in [scope-and-wishlist.md](scope-and-wishlist.md).
