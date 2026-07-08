# Frontend Design Brief

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-07 (MST) |
| **Audience** | design / frontend |
| **Related** | [ADR-0010](../../adr/ADR-0010-ticketing-notify-read-api.md), [scope-and-wishlist](../../requirements/scope-and-wishlist.md) |

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

## Additions since v1 — incorporate in the next iteration

Decisions made after the initial brief (see ADR-0013 and `data/qc_metrics.md`):

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

## Prototype alignment deltas — incorporate in the next iteration

An adversarial review (2026-07-07) graded `PipeGuard.html` against the now-complete
schema/QC design. The prototype is **broadly faithful** — four verdicts, three gates,
breadth/20×/callable, saliva/sample-type, provenance/origin, and it correctly omits
confidence. Close these deltas next (P1 first):

1. **Identity gate (P1).** Add an **NGSCheckMate** genotype-concordance card
   (`identity.ngscheckmate_match`, source `ngscheckmate_matched.txt`) as the *primary*
   swap signal alongside sex-concordance, and relabel **Contamination · FREEMIX** as an
   *optional, non-sarek-default* extra — not an always-on co-equal metric. Today the
   prototype has no NGSCheckMate and elevates FREEMIX, so a barcode-preserving swap could
   pass on index + sex alone. Ref `data/qc_metrics.md` identity/contamination rows.
2. **Per-gate GateResults (P1).** Surface a per-card strip with **preflight / QC /
   variant** each carrying its own verdict + severity + rationale + finding refs
   (`data/schemas.md` GateResult), or explicitly scope GateResult out of the MVP UI. Today
   the card shows only one dominant-gate tag plus a fleet-wide pass-rate.
3. **`operational` gate value (P2).** Retag PIPE-001 from `gate:'operational'` to a schema
   gate (`preflight`|`qc`) with `cat:'pipeline'` — the gate enum is preflight|qc|variant only.
4. **Evidence `source_kind` (P2).** Add the `source_kind` classifier chip
   (artifact|metric|multiqc_source|execution_trace|params|human_note) to evidence rows;
   optionally split `threshold` from `expected`.
5. **Origin tokens (P2).** Rename `origin:'real'` → `'real-giab'` (and use `'contrived'`
   where apt) to match the schema enum + CLAUDE.md data-handling rule 1.
6. **FREEMIX default (P2).** Align to the runbook's **3% fail + 1.5–3% band** (the prototype
   hardcodes ≤ 2% with no band), or annotate 2% as a deliberate project override.
7. **Missing QC metrics (P2).** Add **zero-coverage targets** (`qc.zero_cov_targets`) as a
   distinct card metric; where the assay warrants, add **% mapped**, **fold-80 uniformity**,
   and **% target ≥ 30×**.

*The prototype is a single-line minified bundle — open it in a browser to confirm which
metric cards actually render before finalizing this list.*

