# Builder Card — `bcftools norm`

| Field | Value |
|---|---|
| **Status** | draft |
| **Date** | 2026-07-10 (MST) · corrected 2026-07-11 (MST, the `Truth VCF` reference source this doc named is retired, see §4 edge 5) · corrected 2026-07-12 (MST, reserved-port honesty pass — `vcf_index` promoted to a real optional port; the `panel_bed` regions input removed) |
| **Audience** | frontend / bioinformatics |
| **Related** | [builder-cards/README.md](README.md) (§7) · [frontend/README.md §6](../frontend/README.md#6-pipeline-builder--full-model) · [nf-core-conventions.md](../../data/nf-core-conventions.md) · [BuilderShared.tsx](../../../frontend/src/components/BuilderShared.tsx) (`BTOOLSPEC['bcftools norm']`, `GIAB_LOC`) · [scripts/run_giab_pipeline.py](../../../scripts/run_giab_pipeline.py) (`step_variants`) · [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md) (the custom-script benchmarking seam replacing the retired Truth VCF node) |

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
Notes (updated 2026-07-12 — reserved-port honesty pass): the current `BTOOLSPEC` is
`ins: ['vcf', 'reference_fasta']`, and `reference_fasta` is a `ref: true` port (reference-tone
half-circle, wired by `REF_WIRES` in `BuilderCanvas`, not `SEEDED_WIRES`). **The `panel_bed`
(regions) input this doc used to reserve was REMOVED** (`BuilderShared.tsx`, commit `1621e3f`): the
catalog command `bcftools norm -f ${reference}` normalizes genome-wide (left-align + split
multiallelics), consuming no regions/targets BED — the maintainer's I/O correction explicitly took
`panel_bed` off norm — so a reserved regions port could never carry a real wire and was dropped
rather than left superficial (`panel_bed` stays on `bcftools call`, where it is real).

## 3. Output ports

| Kind | File it produces | Downstream consumer card(s) | Card side |
|---|---|---|---|
| `filtered_vcf` | `-Oz -o HG002.norm.vcf.gz` (`run_giab_pipeline.py:218`); locator `variants/*.norm.filtered.vcf.gz` (`GIAB_LOC.filtered_vcf`, `parser: vcf`, `required: true`) | **ingest → variant gate** (terminal output; no downstream tool card in the seeded chain). Seam: a benchmarking step comparing against a GIAB truth VCF would also consume it — see the corrected note below §4 edge 5. | **right** (primary data out) |
| `vcf_index` (companion `.csi`) *(optional, real)* | `bcftools index -f HG002.norm.vcf.gz` → `HG002.norm.vcf.gz.csi` (`run_giab_pipeline.py`) | Sidecar for the `filtered_vcf` (like `.bai` to a `bam`). **PROMOTED 2026-07-12 (`1621e3f`) from reserved to a real optional port:** the catalog `script:` already ran `bcftools index -f`, so the `.csi` is a genuine byproduct — the compiler now declares + publishes it as a real `emit: vcf_index` channel, and it is in `ARTIFACT_KINDS`. | **bottom** (companion/sidecar) |

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
3. *(removed 2026-07-12)* the `Panel BED → n_norm` regions edge this doc used to list is gone —
   the `panel_bed` input port was removed from `bcftools norm` (norm is genome-wide; see §2).

**Out:**
4. `bcftools norm` (`n_norm`) OUTPUT `filtered_vcf` → **ingest / variant gate** (no tool-card
   target; terminates the variant branch). The locator `filtered_vcf`
   (`variants/*.norm.filtered.vcf.gz`) is what ingest resolves; `run_gate` computes the
   verdict — never stored on the graph (README §6/§7).
5. *(seam, no edge today)* `n_norm` OUTPUT `filtered_vcf` → a benchmarking card vs a GIAB truth
   VCF, if/when one is added. **Corrected 2026-07-11 (Branch A of the custom-script-card
   effort):** the dedicated `Truth VCF` reference source (`r_truth`) this seam used to name is
   retired — it was an unwired placeholder no tool in the seeded chain consumed
   (`docs/design/builder-cards/README.md` §7). The seam is still open, just via a different
   shape: a generic **File input** card (any operator-picked kind, incl. `truth_vcf` — the KIND
   itself is unchanged/still in `ARTIFACT_KINDS`) feeding an
   [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md) custom-script
   benchmarking node (e.g. `bcftools isec`/`hap.py`), rather than a bespoke seeded reference
   node + a bespoke seeded comparison tool.

## 5. Card layout notes

- **Size:** larger than today's fixed 168px node — target ≈ **220×150px** so four sides can
  host half-circle ports without crowding the tool name / version / stage label. Databricks
  process-card aesthetic: header row (icon `funnel` + `bcftools norm` + `v1.20`), a thin
  stage strip (*Filter / normalize*), body clear for port labels.
- **Port placement rationale:**
  - **Left:** `vcf` in — the primary variant stream flows left→right through the chain.
  - **Top:** `reference_fasta` in (required, reference-tone) — references descend from the top,
    matching `bwa-mem2` / `bcftools call` / `mosdepth` cards. (The former `panel_bed` regions port
    was removed — §2.)
  - **Right:** `filtered_vcf` out — continues the left→right primary flow toward the gate.
  - **Bottom:** the `vcf_index` companion (sidecar), kept off the primary flow line.
- **Optional real ports (no reserved-only ports remain on this card, 2026-07-12):** `vcf_index`
  (bottom) is a real optional companion output — a published `emit: vcf_index` channel, in
  `ARTIFACT_KINDS`, rendered bundled with `filtered_vcf` and wireable when connected.
- **Do-not-invent guard:** every port above traces to a real flag/output
  (`run_giab_pipeline.py`) — `vcf_index` is the `.csi` the existing `bcftools index -f` step writes,
  now a real published channel, and `panel_bed` was removed because norm consumes no regions BED.
