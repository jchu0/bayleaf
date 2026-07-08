# Frontend Design Brief

| Field | Value |
|---|---|
| **Status** | Active |
| **Last updated** | 2026-07-07 (MST) |
| **Audience** | design / frontend |
| **Related** | [ADR-0010](../adr/ADR-0010-ticketing-notify-read-api.md), [scope-and-wishlist](../requirements/scope-and-wishlist.md) |

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
