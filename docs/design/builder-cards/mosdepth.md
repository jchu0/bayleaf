# Builder card — mosdepth (coverage)

| Field | Value |
|---|---|
| **Status** | draft |
| **Date** | 2026-07-10 (MST) |
| **Related** | [builder-cards/README.md](README.md) · [design/frontend/README.md §6](../frontend/README.md) · [data/nf-core-conventions.md](../../data/nf-core-conventions.md) · [data/qc_metrics-sources.md §D](../../data/qc_metrics-sources.md) · [frontend BuilderShared.tsx](../../../frontend/src/components/BuilderShared.tsx) (`BTOOLSPEC['mosdepth']`, `GIAB_LOC`) · [scripts/run_giab_pipeline.py](../../../scripts/run_giab_pipeline.py) (`step_mosdepth`) |

Card-design spec for the **mosdepth** node in the Pipeline Builder. Defines the full set of
typed connection ports the card must host — grounded in the real germline command, the mosdepth
CLI docs, and the repo's artifact-kind vocabulary — not the current minimal 2-in/2-out guess.

## 1. Tool overview

1. **Tool / version.** `mosdepth` **0.3.8** (pinned in `BTOOLSPEC['mosdepth']` and seeded
   `TOOLS.n_mosdepth`). Fast BAM/CRAM depth calculator (Pedersen & Quinlan, *Bioinformatics* 2018).
2. **Role in the germline chain.** Coverage QC leaf. It sits after `samtools markdup` and runs in
   parallel with `bcftools call`: `… → samtools markdup → {mosdepth, bcftools call → norm} → …`.
   It reads the dedup BAM (+ the panel BED for region mode) and emits the coverage-summary and
   per-threshold breadth files that MultiQC aggregates and that `run_gate` derives **mean coverage**
   and **breadth ≥20×/≥30×** from.
3. **Real command** (`run_giab_pipeline.py:174`, `step_mosdepth`):
   `mosdepth --by <panel.bed> --no-per-base --thresholds 1,10,20,30 -t 2 <prefix> <dedup.bam>`.
   `--no-per-base` suppresses the per-base BED this run; `--thresholds` turns on the thresholds BED
   that the breadth metrics are computed from; `--by <panel.bed>` puts mosdepth in per-region mode.

## 2. Input ports

| Port kind | Maps to (file / glob) | Req / opt / user-defined | Upstream source card | Card side |
|---|---|---|---|---|
| `bam` | dedup BAM, the positional input — `align/*.md.bam` (`GIAB_LOC.bam`) | **required** | `samtools markdup` (`n_markdup`) `bam` out | left |
| `bai` | BAM index sidecar (`.bam.bai`/`.csi`) — mosdepth requires an **indexed** BAM | **required companion** (bundled with `bam`; may be hidden by default) | `samtools markdup` (`n_markdup`) `bai` out | left |
| `panel_bed` | `--by <panel.bed>` region file — `reference/panel.bed` (`GIAB_LOC.panel_bed`) | **user-defined** (optional in general mosdepth; `--by` can also take a window int). Required for the panel/region metrics this chain produces | `Panel BED` reference source (`r_bed`) | top |

Notes: `bam` + `bai` are the primary data flow (left→right); `panel_bed` is a reference that
enters from the **top**, matching the convention that references/panels drop in from above.
`--by` is user-defined — a lab may swap the panel or pass a window size instead — so the card must
reserve the `panel_bed` input even though it is not one of the two "minimal" ports.

## 3. Output ports

mosdepth's output family is derived from its `<prefix>` argument; which members appear depends on
the flags. Cite: [mosdepth CLI docs](https://github.com/brentp/mosdepth#usage) + `qc_metrics-sources.md §D`.

| Port kind | File produced (`<prefix>` = `HG002.panel`) | Emitted this run? | Downstream consumer card(s) | Card side |
|---|---|---|---|---|
| `mosdepth_summary` | `HG002.panel.mosdepth.summary.txt` (`total_region` row → mean cov) | **yes**, always | `MultiQC` (`n_multiqc` `mosdepth_summary` in) + `run_gate` mean-coverage metric | right |
| `mosdepth_thresholds` | `HG002.panel.thresholds.bed.gz` (+ `.csi`) — base counts ≥ each threshold | **yes** (`--thresholds 1,10,20,30`) | `run_gate` breadth ≥20×/≥30× (`step_mosdepth`); MultiQC can plot | right |
| `mosdepth_regions` | `HG002.panel.regions.bed.gz` (+ `.csi`) — per-region mean depth | **yes** (produced whenever `--by` is set) | user-defined (per-region review); not consumed by this chain | bottom |
| `mosdepth_global_dist` | `HG002.panel.mosdepth.global.dist.txt` — cumulative depth dist | **yes**, always | MultiQC coverage plot (user-defined) | bottom |
| `mosdepth_region_dist` | `HG002.panel.mosdepth.region.dist.txt` — per-region cumulative dist | **yes** (produced when `--by` set) | MultiQC coverage plot (user-defined) | bottom |
| `per_base` | `HG002.panel.per-base.bed.gz` (+ `.csi`) — per-base depth | **no** — suppressed by `--no-per-base` | user-defined (fine-grained depth); reserve the port | bottom |

Notes:
1. Only **`mosdepth_summary`** is an emitted `run_layout.yaml` locator today (`GIAB_LOC`,
   `parser: mosdepth_summary`). `mosdepth_thresholds` is a real port kind (`BTOOLSPEC` out) that
   the pipeline reads inline for breadth but does **not** surface as a separate locator — mark it
   produced-and-consumed, not a locator.
2. `mosdepth_regions` / `mosdepth_global_dist` / `mosdepth_region_dist` / `per_base` are **not yet**
   in the artifact-kind vocabulary (`ARTIFACT_KINDS` / `nf-core-conventions.md`). They are honest
   mosdepth outputs; the card should reserve bottom ports for them (labelled user-defined / not-yet-a-locator),
   never invent a downstream wire the chain doesn't have.

## 4. Edges (concrete wires in/out of this card)

Grounded in `germlineTemplate()` (`BuilderShared.tsx`) + the real command. Kind-matched, typed.

**In:**
1. `samtools markdup` (`n_markdup`) `bam` out → `mosdepth` `bam` in — the dedup BAM
   (`wire('n_markdup','bam','n_mosdepth','bam')`, template line ~303).
2. `samtools markdup` (`n_markdup`) `bai` out → `mosdepth` `bai` in — index companion (new; mosdepth
   requires the index, not wired in the current minimal template).
3. `Panel BED` (`r_bed`) `panel_bed` out → `mosdepth` `panel_bed` in — the `--by` region file
   (`REF_WIRES`, seeded from ref-card geometry).

**Out:**
4. `mosdepth` `mosdepth_summary` out → `MultiQC` (`n_multiqc`) `mosdepth_summary` in
   (`wire('n_mosdepth','mosdepth_summary','n_multiqc','mosdepth_summary')`, template line ~308).
5. `mosdepth` `mosdepth_thresholds` out → *(no card)* — read inline by `step_mosdepth` for breadth;
   card shows the port, no outgoing edge unless a user adds a consumer.
6. `mosdepth` `mosdepth_regions` / `mosdepth_global_dist` / `mosdepth_region_dist` / `per_base` out →
   *(no seeded card)* — bottom ancillary ports; reserved for a user-added MultiQC/report consumer.

## 5. Card layout notes

1. **Size.** Larger than today's minimal card — target a Databricks process-card footprint (roughly
   1.5–2× the current 168 px width, taller header) so up to **3 input + 6 output** half-circle ports
   fit on the perimeter without crowding the tool name / version / stage label ("Coverage") / `ours`
   badge. Today's card renders only 2-in/2-out; the expansion needs the extra real estate.
2. **Port placement rationale.**
   - **Left:** primary data in — `bam` (top-left) with its `bai` companion just below it (they arrive
     together from `samtools markdup`).
   - **Top:** `panel_bed` reference in — references/panels drop from above, distinct from the
     left→right primary flow (matches the convention and the `REF_WIRES` geometry).
   - **Right:** the two **consumed / gated** outputs on the primary flow toward MultiQC —
     `mosdepth_summary` (top-right) and `mosdepth_thresholds` (below it).
   - **Bottom:** the **ancillary / QC-artifact** outputs — `mosdepth_regions`, `mosdepth_global_dist`,
     `mosdepth_region_dist`, and the reserved `per_base` port — QC/metric byproducts exit the bottom,
     keeping the right edge clean for the main flow.
3. **User-defined ports to reserve space for.**
   - `panel_bed` in — `--by` is user-defined (swap panel / pass a window int); always show the port.
   - `per_base` out — off by default here (`--no-per-base`); reserve a dimmed/optional bottom port so
     dropping `--no-per-base` has somewhere to wire.
   - `mosdepth_regions` / `*_dist` outs — produced but not consumed by this chain; render as
     optional bottom ports the operator can wire to a report/MultiQC node.
4. **Honesty flags.** Badge each port required / optional / user-defined per §2–§3. The seeded card's
   `mapq: 20` param is **illustrative** — the real `step_mosdepth` command does not pass `--mapq`
   (it passes `--by`, `--no-per-base`, `--thresholds`, `-t 2`); note the drift so the param panel and
   the actual run stay reconcilable.
