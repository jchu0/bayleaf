# Frontend Design Brief

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-08 (MST) |
| **Audience** | design / frontend |
| **Related** | [ADR-0010](../../adr/ADR-0010-ticketing-notify-read-api.md), [ADR-0014](../../adr/ADR-0014-productionization-fastapi-react.md), [scope-and-wishlist](../../requirements/scope-and-wishlist.md), [README.md](./README.md) |

## How to use

A carry-over brief for a UI/UX design session. The **Brief** section below is
self-contained — paste it into your design tool; it assumes no prior context.

## Brief

**Product.** PipeGuard is an AI-assisted **provenance & QC decision gate** for
genomics pipeline runs — the operations layer that sits on top of a bioinformatics
pipeline. For each sample in a sequencing run it recommends **proceed / hold /
rerun / escalate**, always with the supporting evidence, and it uses AI to
accelerate triage (cut the "comb the logs" diagnosis time). Domain: rare-disease
germline DNA panel, Illumina short-read. It governs decisions on genomics data —
so the feel is trustworthy and evidence-forward, not flashy.

**Primary user.** A bioinformatics pipeline operator reviewing runs — technical,
time-pressured, needs to see "what needs my attention" in seconds. (Secondary,
future: a bench scientist who runs pipelines without the terminal.)

**Design principles.**
1. Functional and simple over polished. Clean, legible, information-dense without clutter.
2. Attention-first: surface the samples that need a human immediately; let clean ones recede.
3. Evidence-forward and conservative in tone (clinical-adjacent). The AI advises; the human decides.
4. Clear states everywhere: loading, empty, error. Use believable sample data.

**Core screens.**
1. **Run overview (home).** List of sequencing runs; per-run counts by verdict
   (proceed/hold/rerun/escalate); an "N samples need attention" banner; light
   filters. Verdict color-coding. The entry point.
2. **Decision card (per sample) — the hero.** Verdict badge, one-line headline,
   short rationale, recommended next steps, a **cited-evidence table**
   (source file · value · expected), and a **confidence indicator labeled as a
   heuristic** (not a probability), plus the **sample type** (whole blood / saliva). Reads as "here's the call, and exactly why." QC expectations are sample-type-aware — saliva carries more off-target microbial content than blood.
3. **Review queue (human-in-the-loop).** Cards-as-tickets with status
   (open → in-review → resolved); actions to **acknowledge/suppress an issue class**
   (so it stops re-prompting), **escalate**, and resolve; a hint at tiered access
   (reviewer vs approver).
4. **Provenance canvas (read-only).** A stage/DAG view of the pipeline
   (fastp → align → variant-call → gate); click a stage to drill into that run's
   **data I/O** — inputs, outputs, hashes, origin label (real/synthetic). The
   visual face of the provenance ledger.
5. **Agent triage panel.** The AI triage note for a flagged issue: likely cause,
   suggested action, and **citations** to both the findings and the
   knowledge/experience corpora. Advisory framing.
6. **Settings (light).** Profile (lean vs granular), notify channel (Slack), and
   model tiering — mostly informational.

**Design-system hints.**
1. Verdict semantics: proceed = go/green, hold = caution/amber, rerun = orange,
   escalate = alert/red. Finding severity icons: critical / warn / info.
2. First-class: evidence tables, citations, status badges, a confidence meter
   (labeled heuristic), origin tags (real/synthetic).
3. Target implementation is **React + a component library (shadcn/ui or Mantine)** —
   design in composable components and standard patterns; theme-aware and
   responsive are nice-to-haves.

**Out of scope for this pass** (wishlist): the editable pipeline builder, deep
settings, and data-platform integrations. Keep to the core flow above.

**Deliverable.** Wireframes/mockups for screens 1–5, a simple color + component
system, and the key states (loading / empty / error).

## Build status (2026-07-08)

The full screen set is now **built** in the React frontend (`frontend/`) and mirrored in the
clickable prototype (`PipeGuard.html`): the six core screens below **plus** the v2 additions —
including the **preflight/intake gate** — all exist. This brief stays the stable spec; the
sections below record the intent the build followed.

## Additions since v1 — incorporated (now built)

Decisions made after the initial brief (see ADR-0013 and `data/qc_metrics.md`), now
implemented in both the prototype and the React frontend:

1. **Three-gate model + preflight/intake gate.** The gate is three checkpoints:
   **preflight/intake** (before processing) → **QC gate** → **variant gate**. Add an
   intake view — run-level sequencing QC (e.g. `% PhiX aligned > 90%` = "didn't
   sequence it") + a **manual override** to admit a genuinely-sparse sample. Label
   which gate each finding/verdict came from.
2. **Verdict philosophy — surface, don't prescribe.** The tool surfaces evidence + a
   recommendation; the human decides. **RERUN is for operational/file-system failures**
   (network, missing files, race conditions), **not** data quality — a low-coverage
   sample is a **HOLD**. Surface **depth vs breadth/coverage as distinct signals**.
3. **Richer QC evidence.** The evidence table carries the full metric set, grouped by
   gate: **breadth/callability** (% target ≥ 20×, callable-region gaps),
   **contamination** (FREEMIX), **sex/identity** concordance, **variant-level**
   (DP/GQ/allele balance, gnomAD AF, ClinVar) — not just Q30/coverage.
4. **Recurring-issue escalation.** In the review queue: a signature recurring ~3×
   **escalates to a pipeline-repair agent (#2)**. Support **class-level fix** *and*
   per-instance **"see-one / fix-one"** approvals (beyond suppress). Keep the
   reviewer-vs-approver (RBAC) gating.
5. **Sample-type-aware.** Sample type (whole blood / saliva) shapes QC expectations
   (saliva → more off-target microbial content → looser mapping/on-target/yield;
   contamination FREEMIX unchanged). Surface it and note where thresholds vary by it.
6. **Config, not read-only.** Runbook thresholds should be **operator-adjustable**
   (a config surface), keyed on **assay × sample type** — not merely displayed.
7. **Confidence stays omitted** until it's grounded (fastp/MultiQC-derived later) —
   design's call to leave it out is correct; don't add a meaningless heuristic bar.
8. **(Light) monitoring view.** A run-throughput / verdict-over-time surface serves
   the monitoring focus (system telemetry via Prometheus arrives with the backend).

## Handoffs

Episodic review→design deltas live as dated docs under [handoffs/](handoffs/) — kept out
of this brief so it stays the stable, paste-and-go spec:

1. [2026-07-07 — alignment & freshness](handoffs/2026-07-07-alignment.md) — prototype
   graded against the final schema/QC design: identity gate (NGSCheckMate), per-gate
   results, plus five polish items.
