# Builder Card — `bcftools norm`

| Field | Value |
|---|---|
| **Status** | draft |
| **Date** | 2026-07-10 (MST) |
| **Audience** | frontend / bioinformatics |
| **Related** | [builder-cards/README.md](README.md) · [frontend/README.md §6](../frontend/README.md#6-pipeline-builder--full-model) · [nf-core-conventions.md](../../data/nf-core-conventions.md) · [BuilderShared.tsx](../../../frontend/src/components/BuilderShared.tsx) (`BTOOLSPEC['bcftools norm']`, `GIAB_LOC`) · [scripts/run_giab_pipeline.py](../../../scripts/run_giab_pipeline.py) (`step_variants`) |

## 1. Tool overview

`bcftools norm` **left-aligns and normalizes** variant records against the reference:
indels are shifted to the leftmost position, multiallelic sites are split (`-m -`) or
joined (`-m +`), and REF alleles are checked/corrected against the FASTA (`-c`). It is the
terminal tool node of the germline chain's **variant branch** — it takes the raw calls from
`bcftools call` and emits the normalized, gate-ready VCF that ingest hands to the variant
gate.

- **Pinned version:** `1.20` (`BTOOLSPEC['bcftools norm'].version`, `n_norm` seeded node).
- **Role in chain:** `… bcftools call → bcftools norm → (ingest → variant gate)`. It also
  consumes the **Reference FASTA** source card for left-alignment.
- **Real command** (`run_giab_pipeline.py:216–222`):
  ```
  bcftools norm -f <REF.fa> -Oz -o HG002.norm.vcf.gz  HG002.calls.vcf.gz
  bcftools index -f HG002.norm.vcf.gz
  ```
- **Honesty note — "filter":** the card's stage label reads *"Filter / normalize"* and the
  emitted locator is `variants/*.norm.filtered.vcf.gz`, but the **real command normalizes
  only** — no separate `bcftools view -f PASS` / `bcftools filter` pass is invoked today. A
  filter pass is a documented **params-level seam** (adds flags to this same card, **no new
  port**), not a wired stage. Keep the label aspirational; do not imply a filter runs.

## 2. Input ports

| Kind | File / glob it maps to | Req / Opt / User-defined | Upstream source card | Card side |
|---|---|---|---|---|
| `vcf` | positional input `HG002.calls.vcf.gz` (`run_giab_pipeline.py:218`, `str(calls)`) | **required** | `bcftools call` (`n_call`) `vcf` output | **left** (primary data in) |
| `reference_fasta` | `-f <REF.fa>` (`run_giab_pipeline.py:218`, `str(_REF)`); locator `reference/GRCh38.fa` (`GIAB_LOC.reference_fasta`, `role: reference`) | **required** — left-alignment/REF-check need it | `Reference FASTA` source (`r_fasta`) `reference_fasta` output | **top** (references enter from top) |
| `panel_bed` (regions) | `-R <regions.bed>` / `-r <chr:beg-end>` — restrict normalization to regions | **user-defined** (optional) — **not run** in the germline chain (per the code map, "bcftools call gains `panel_bed`, norm loses it"); reserve the port for a regions-scoped norm | `Panel BED` source (`r_bed`) `panel_bed` output | **top** (reserved, collapsed by default) |

Notes: `reference_fasta` and the reserved `panel_bed` are `ref: true` ports (rendered as
reference-tone half-circles, wired by `REF_WIRES` in `BuilderCanvas`, not by `SEEDED_WIRES`).
The current `BTOOLSPEC` minimum is `ins: ['vcf', 'reference_fasta']` — this doc adds the
optional `panel_bed` regions port as reserved space, per the card-design convention (host all
of the tool's real I/O even when a run leaves it unused).

## 3. Output ports

| Kind | File it produces | Downstream consumer card(s) | Card side |
|---|---|---|---|
| `filtered_vcf` | `-Oz -o HG002.norm.vcf.gz` (`run_giab_pipeline.py:218`); locator `variants/*.norm.filtered.vcf.gz` (`GIAB_LOC.filtered_vcf`, `parser: vcf`, `required: true`) | **ingest → variant gate** (terminal output; no downstream tool card in the seeded chain). Seam: a benchmarking card comparing against the `Truth VCF` source (`r_truth`) would also consume it. | **right** (primary data out) |
| `vcf_index` (companion `.csi`) | `bcftools index -f HG002.norm.vcf.gz` (`run_giab_pipeline.py:222`) | Sidecar for the `filtered_vcf` (like `.bai` to a `bam`); consumed implicitly by any tool that opens the VCF. **Not yet in the kind vocabulary** (`ARTIFACT_KINDS` / `GIAB_LOC` have no `vcf_index`/`csi`) — reserve as an **optional companion port** or bundle visually with `filtered_vcf`; do not fabricate a locator kind. | **bottom** (companion/sidecar) |

Note: `filtered_vcf` is **not** wired to MultiQC — MultiQC's inputs are `fastp_json`,
`markdup_metrics`, `mosdepth_summary` only (`n_multiqc`), so the norm output does not flow to
QC aggregation. It exits the graph to the deterministic gate.

## 4. Edges — concrete wires in / out of this card

**In:**
1. `bcftools call` (`n_call`) OUTPUT `vcf` → `bcftools norm` (`n_norm`) INPUT `vcf`
   (left). Seeded edge: `wire('n_call', 'vcf', 'n_norm', 'vcf')`
   (`BuilderShared.germlineTemplate`, line ~305).
2. `Reference FASTA` (`r_fasta`) OUTPUT `reference_fasta` → `bcftools norm` (`n_norm`) INPUT
   `reference_fasta` (top). A `REF_WIRE` (reference-tone), computed from card geometry in
   `BuilderCanvas`, not a `SEEDED_WIRE`.
3. *(reserved, no edge today)* `Panel BED` (`r_bed`) OUTPUT `panel_bed` → `n_norm` INPUT
   `panel_bed` regions (top) — only when the operator scopes norm to a region set.

**Out:**
4. `bcftools norm` (`n_norm`) OUTPUT `filtered_vcf` → **ingest / variant gate** (no tool-card
   target; terminates the variant branch). The locator `filtered_vcf`
   (`variants/*.norm.filtered.vcf.gz`) is what ingest resolves; `run_gate` computes the
   verdict — never stored on the graph (README §6/§7).
5. *(seam, no edge today)* `n_norm` OUTPUT `filtered_vcf` → a benchmarking card vs the
   `Truth VCF` source (`r_truth`), if/when one is added.

## 5. Card layout notes

- **Size:** larger than today's fixed 168px node — target ≈ **220×150px** so four sides can
  host half-circle ports without crowding the tool name / version / stage label. Databricks
  process-card aesthetic: header row (icon `funnel` + `bcftools norm` + `v1.20`), a thin
  stage strip (*Filter / normalize*), body clear for port labels.
- **Port placement rationale:**
  - **Left:** `vcf` in — the primary variant stream flows left→right through the chain.
  - **Top:** `reference_fasta` in (required, reference-tone) and the reserved `panel_bed`
    regions in (optional) — references/panels descend from the top, matching `bwa-mem2` /
    `bcftools call` / `mosdepth` cards.
  - **Right:** `filtered_vcf` out — continues the left→right primary flow toward the gate.
  - **Bottom:** the `vcf_index` companion (sidecar), kept off the primary flow line.
- **User-defined / reserved ports:** (a) the `panel_bed` **regions** input — collapsed by
  default, expandable when a run scopes norm; (b) the `vcf_index` **companion** output —
  render bundled with `filtered_vcf` until a `vcf_index`/`csi` kind is added to
  `ARTIFACT_KINDS`. Reserve top-edge and bottom-edge space for both so adding them never
  reflows the card.
- **Do-not-invent guard:** every port above traces to a real flag/output
  (`run_giab_pipeline.py:216–222`) or a documented `bcftools norm` option; the `vcf_index`
  companion is real but has **no kind in the current vocabulary**, so it is marked reserved
  rather than wired.
