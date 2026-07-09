# PipeGuard — judge one-pager

| Field | Value |
|---|---|
| **Status** | Draft |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | judges / all |
| **Related** | [demo_plan.md](demo_plan.md), [run-of-show.md](run-of-show.md), [../../README.md](../../README.md), [../design/architecture.md](../design/architecture.md), [../quality/evaluation.md](../quality/evaluation.md), [ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md), [ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md) |

> **DRAFT — maintainer to tune.** A skimmable, judge-facing summary. Every claim here is
> traced to code/docs; trim or re-voice for the final handout as needed.

## 1. The problem

Bioinformatics pipelines are good at *executing* workflow steps, but *operating* them is
still manual. When a sequencing run finishes, someone must decide **per sample** —
proceed / hold / rerun / escalate — by combing scattered logs, QC reports, and dashboards
by hand, then reconstructing what happened, why it matters, and what to do next. That
reconstruction is slow, error-prone, and lives in one person's head.

## 2. What PipeGuard is

PipeGuard is the **operations layer** — a decision gate for a sequencing run. It ingests
the run's artifacts, checks them for provenance risks, missing metadata, and borderline
QC, and produces a **decision card per sample** with **cited evidence**. The human still
makes the call; they just no longer reconstruct the context by hand. The load-bearing
invariant: **rules decide; AI narrates and advises — and never sets or overrides a
verdict** ([ADR-0001](../adr/ADR-0001-deterministic-gate-advisory-ai.md)).

## 3. What makes it different

a. **Deterministic gate + cited evidence.** A rule engine owns the *facts* (barcode /
   index-swap, sample identity, missing metadata, QC vs. runbook thresholds, pipeline
   failures). Each is an immutable, content-hashed `Finding` that traces to a source file
   and a rule; the **verdict is computed from the findings**, never guessed by a model.
b. **Event-sourced provenance, rebuildable from the log.** Every run emits an append-only
   event trail; the relational database is a **disposable projection** that `rebuild-db`
   reconstructs from the authoritative log — same run, samples, findings, and cards
   ([ADR-0002](../adr/ADR-0002-event-driven-core-provenance-ledger.md)).
c. **Advisory Claude triage, off the critical path.** On a flagged card, an agent suggests
   a likely cause and next action, grounded in a curated corpus with citations. It is
   **off by default**, imports the SDK lazily, and **degrades to a deterministic stub** on
   any API error or safety refusal — it never touches the verdict.
d. **Metric registry / units contract.** A versioned registry normalizes every metric to a
   canonical decimal **before** the QC gate thresholds it, so a source-unit change (e.g.
   percent vs. fraction) **can't silently move a verdict**. This one runs *on* the critical
   path; new tool keys are absorbed by the registry, not by editing rules.
e. **Live Slack ops integration.** An outbound port turns each *actionable* card into a
   per-verdict, evidence-cited notification. Off by default ($0, nothing leaves the
   machine); the live Slack post is armed **only** by an explicit flag, and every send is
   recorded as a `notification.emitted` provenance event.

## 4. Why it's real (not a mock-up)

a. **320 offline tests across 19 files (317 pass; 3 Postgres live-integration skips)**, all runnable with no API key
   (`uv sync --all-extras && uv run pytest`) — pinning verdicts, the ledger→DB rebuild,
   the units contract, the AI-degrades-to-stub path, and the notify seam.
b. **Real GIAB HG002 data runs through the FULL gate** on a bioconda toolchain — the fetch is
   validated end-to-end (NIST truth VCF, a 470-record panel VCF, a 70,996-read panel BAM
   slice), and **real QC metrics are derived from the real reads**: `samtools fastq | fastp`
   → **Q30 88.2%, duplication 0.006%, reads-passing 99.3%**, and `mosdepth` → **55.8× panel
   coverage**. All four clear their thresholds → **PROCEED**, and the **metric registry
   normalizes each real value from its declared unit exactly as it does for a mock run** —
   proving the units contract on real data, not just fixtures. Accessions + fetch script
   committed; the raw bytes are git-ignored (never committed). *(Validating verdicts against
   the GIAB truth VCF — EVAL-030 — is Phase 2.)*
c. **Byte-identical reproducibility.** A fixed run + pinned runbook yield identical
   verdicts, findings, and content hashes every time; the ledger→DB rebuild is idempotent
   and hash-preserving (the DB is a pure function of the log).
d. **Three delivery layers run today** over one framework-agnostic core: Streamlit (the
   always-green offline fallback), a FastAPI read-API (the production seam), and a React +
   Vite + Tailwind UI.

## 5. Honest guardrails

a. **Not a clinical decision system.** A research/demo tool with production intent — **no
   diagnostic, therapeutic, or pathogenicity claims.** It sits *on top of* a pipeline; it
   does not build or modify a clinical one.
b. **Rules decide; AI is advisory** and off the deterministic critical path — and **off by
   default**, with a deterministic fallback.
c. **Thresholds are illustrative and configurable**, not clinical thresholds. Any
   confidence value is a heuristic, not a calibrated probability, and is **omitted until
   grounded**.
d. **No patient data (PHI).** Public/synthetic only for the hackathon; clinical variant
   claims stay grounded in ClinVar/GIAB truth.

---

**Read next:** [README.md](../../README.md) · [architecture.md](../design/architecture.md)
· [demo_plan.md](demo_plan.md) · [run-of-show.md](run-of-show.md) · the
[ADRs](../adr/) (the *why* behind each decision).

*Marker legend — distinguish claim types where confusion is likely:*
**Fact** · **Assumption** · **Decision** · **TODO**.
