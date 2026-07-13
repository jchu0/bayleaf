# Constraints

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | all |
| **Related** | [functional.md](functional.md), [nonfunctional.md](nonfunctional.md), [planning/tasks.md](../planning/tasks.md), [data/licensing.md](../data/licensing.md), [data/qc_metrics-rare-disease.md](../data/qc_metrics-rare-disease.md), [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md) |

## Overview

The fixed boundaries the design must respect (**REQ-C-NNN**) — time, money,
licensing, and domain-safety. Unlike functional/non-functional requirements, these
are largely external givens; the architecture is shaped *around* them. Each is
traced to its source.

## Timeline

1. **REQ-C-001 — Submission deadline.** Due **Mon Jul 13, 2026, 6:00 pm MST**
   (9:00 pm ET). Work is planned in day buckets (design → build → harden → demo →
   flex → buffer), not hour estimates. *Trace:* [tasks.md](../planning/tasks.md)
   §Timeline.
2. **REQ-C-002 — MVP-first sequencing.** Prioritize a working, understandable core
   flow behind production-ready seams; defer wishlist items rather than dilute the
   core. Heavyweight process docs are skipped during the sprint. *Trace:*
   [DOCUMENTATION_HABITS.md](../DOCUMENTATION_HABITS.md) §Delivery posture,
   [scope-and-wishlist.md](scope-and-wishlist.md).
3. **REQ-C-003 — Guaranteed-working fallback.** Because demo time is fixed and
   unforgiving, an offline Streamlit path over the same core is maintained as the
   always-green fallback. *Trace:* [demo_plan.md](../demo/demo_plan.md), ADR-0014.

## Budget

1. **REQ-C-010 — Fixed API budget.** A fixed **~$200** product API budget (separate
   from dev tooling) constrains live-Claude usage. *Trace:* [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md);
   MEMORY: conserve-API-credits.
2. **REQ-C-011 — AI off by default.** Every AI component is off by default and
   selected by config, so dev, CI, and the default demo cost **$0** and run offline;
   live AI is flipped on only for the demo moment. *Trace:* [ADR-0006](../adr/ADR-0006-ai-off-by-default-fallback.md),
   [nonfunctional.md](nonfunctional.md) REQ-NF-030/031.
3. **REQ-C-012 — Model selection is a cost lever.** Model is configurable per AI seam
   (`BAYLEAF_*_MODEL`) to trade cost against quality within the budget. *Trace:*
   ADR-0006, [architecture.md](../design/architecture.md) §Swappable seams.

## Licensing

1. **REQ-C-020 — External-process invocation only.** Third-party genomics tools are
   invoked as **external processes** (arm's-length subprocess), which keeps bayleaf's
   own code MIT-licensable. Verified for VerifyBamID2 (MIT), peddy (MIT), Picard
   (MIT), and PLINK (GPL-3.0) in [qc_metrics-rare-disease.md](../data/qc_metrics-rare-disease.md)
   §4. *Trace:* [licensing.md](../data/licensing.md).
2. **REQ-C-021 — Do not redistribute GPL binaries in-tree.** A GPLv3 tool (e.g.
   PLINK) is fine via CLI (mere aggregation), but **bundling its binary** (e.g. baked
   into a Docker image) triggers GPLv3 obligations on that binary. Prefer installing
   from upstream and invoking what is on `PATH`. *Trace:* [qc_metrics-rare-disease.md](../data/qc_metrics-rare-disease.md)
   §4.
3. **REQ-C-022 — Open data sources only.** Use open sources (GIAB, gnomAD, ClinVar);
   **no licensed data sources** (e.g. HGMD). *Trace:* [scope-and-wishlist.md](scope-and-wishlist.md)
   §Out of scope, [strategy.md](../data/strategy.md).
4. **REQ-C-023 — Verify unconfirmed tool licenses before relying on them.** Only the
   four tools above are verified verbatim in-repo; other stack tools' licenses are
   *unverified* and must be confirmed against upstream LICENSE files before any
   distribution claim. *Trace:* [licensing.md](../data/licensing.md) (verification
   status column).

## Domain safety

1. **REQ-C-030 — Research/demo tool, not a clinical decision system.** bayleaf has
   production intent but makes **no diagnostic, therapeutic, or safety claims** and is
   not a clinical decision system. *Trace:* CLAUDE.md life-science guardrails,
   [scope-and-wishlist.md](scope-and-wishlist.md) §Out of scope.
2. **REQ-C-031 — No invented genomics facts or pathogenicity.** Clinical variant
   statements stay grounded in ClinVar/GIAB truth; pathogenicity is never invented.
   gnomAD/ClinVar are used for annotation, not gating claims. *Trace:* CLAUDE.md,
   [strategy.md](../data/strategy.md).
3. **REQ-C-032 — Thresholds are illustrative and per-assay.** Runbook thresholds are
   guideline **examples**, configurable per assay — not clinical thresholds; no
   universal hard number is hardcoded (guidelines defer to per-assay validation).
   *Trace:* [qc_metrics.md](../data/qc_metrics.md) §Principles, [qc_metrics-rare-disease.md](../data/qc_metrics-rare-disease.md).
4. **REQ-C-033 — Confidence is a heuristic.** Confidence values are heuristics, not
   calibrated probabilities, and are omitted until grounded. *Trace:* CLAUDE.md
   guardrails, T-019.
5. **REQ-C-034 — No PHI during the hackathon.** Real patient data is out of scope;
   public/synthetic/contrived only, pending a de-identification module *(wishlist
   #14)*. *Trace:* [scope-and-wishlist.md](scope-and-wishlist.md), [nonfunctional.md](nonfunctional.md)
   REQ-NF-021/023.

## Scope boundary

1. **REQ-C-040 — Sit on top of the pipeline, do not build it.** bayleaf is the
   operations layer over an existing bioinformatics pipeline; building or modifying
   the upstream clinical pipeline is out of scope. Inputs are VCF + QC outputs (VCF-first,
   ADR-0004). *Trace:* [scope-and-wishlist.md](scope-and-wishlist.md), [strategy.md](../data/strategy.md).

---

*Marker legend:* **Fact** · **Assumption** · **Decision** · **TODO**. Licensing rows
not verified verbatim in-repo are flagged in [data/licensing.md](../data/licensing.md).
