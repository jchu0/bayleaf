# RUN-2026-07-08-GIAB-HG002 — real-GIAB chr20 smoke run

`origin=real-giab`. This run uses **real** GIAB **HG002** reads processed end-to-end through the
Nextflow driver, but it is a deliberately downsampled **smoke test**, not a whole-panel/exome/genome
analysis. Its clean-looking QC (`breadth_20x=0.9924`, `mean_coverage=54.2`) must be read at that
scope — it implies **nothing** about clinical quality:

- The sample is GIAB **HG002** — a publicly-consented benchmark reference, **not a patient**. No
  clinical, diagnostic, or pathogenicity claim is made about it (CLAUDE.md life-science guardrail 1).
- Reads are aligned to **chr20 only** (GIAB's traditional "quick test" chromosome), then coverage is
  restricted to a **small set of ARBITRARY smoke-test windows** on chr20 defined in
  [`scripts/panel_regions.example.bed`](../../scripts/panel_regions.example.bed) — that file's own
  header says these are "ARBITRARY smoke-test windows … NOT a real clinical gene panel." They exist
  only to give the pipeline a small, reproducible region set.
- Because breadth/coverage are computed over those few narrow chr20 windows, **99.2% breadth at 20×**
  reflects depth over ~a few hundred kb of hand-picked chr20 — **not** whole-panel, whole-exome, or
  whole-genome breadth, and not a clinical-quality metric. Reading it as panel-wide/clinical quality
  would be wrong.
- `cluster_pf` is intentionally blank (a run-level SAV metric a fastq→BAM path cannot produce), so
  the gate routes this run to **HOLD** — the honest, expected result for a reads-only smoke run, not
  a quality defect in the sample.
- Replace the arbitrary window BED with a real, validated panel — and run whole-target, not a chr20
  subset — before drawing any conclusion beyond "the pipeline ran."
