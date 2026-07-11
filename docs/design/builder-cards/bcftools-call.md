# Builder Card — `bcftools call` (variant calling)

| Field | Value |
|---|---|
| **Status** | draft |
| **Date** | 2026-07-10 (MST) |
| **Audience** | frontend / bioinformatics |
| **Related** | [./README.md](README.md) (card-design index) · [../frontend/README.md](../frontend/README.md) §6 (Pipeline Builder tool-card model) · [../../data/nf-core-conventions.md](../../data/nf-core-conventions.md) · [../../data/qc_metrics-sources.md](../../data/qc_metrics-sources.md) (§F variant-level) · [BuilderShared.tsx](../../../frontend/src/components/BuilderShared.tsx) (`BTOOLSPEC['bcftools call']`, seeded `n_call`, `GIAB_LOC`) · [scripts/run_giab_pipeline.py](../../../scripts/run_giab_pipeline.py) (`step_variants`, lines 197–227) |

## 1. Tool overview + role in the chain

**Tool:** `bcftools call` — pinned **v1.20** (htslib/bcftools; matches `BTOOLSPEC` + seeded `n_call`).

**Role.** The **variant-calling** stage of the germline panel chain. It sits after
`samtools markdup` and before `bcftools norm`:

```
… → samtools markdup → { mosdepth , bcftools call → bcftools norm } → MultiQC (QC aggregates elsewhere)
```

**The card wraps an `mpileup | call` pipe, not a bare `call`.** The real command
(`step_variants`, lines 203–213) is a two-process pipe rendered as one node:

```bash
bcftools mpileup -f <reference_fasta> -R <panel_bed> -Ou <dedup.bam> \
  | bcftools call -mv -Oz -o HG002.calls.vcf.gz
```

So the card's *input* ports are really `mpileup`'s inputs (reference + regions +
indexed BAM); the *output* port is `call`'s VCF. `-m` = multiallelic caller, `-v` =
variant sites only (`variants_only` param); `-Ou`/`-Oz` are the internal/final output
formats. The intermediate BCF is a pipe, never a file — it is **not** a port.

> Confidence/threshold note: any downstream gate on VCF `QUAL` is caller-dependent
> (`qc_metrics-sources.md` §F, note 5) — illustrative, not clinical. The card only
> composes the call; the verdict is computed at run time by `run_gate`, never here.

## 2. Input ports

| Kind | File / glob it maps to | Required? | Upstream source card | Card side | Cite |
|---|---|---|---|---|---|
| `bam` | `align/*.md.bam` (the dedup BAM) | **required** | `samtools markdup` → `bam` | left | `str(dedup)` line 204; `GIAB_LOC.bam` |
| `bai` | `align/*.md.bam.bai` (BAM index) | **required** *(only because `-R` region access needs a random-access index; a `-T`/streamed call would make it optional)* | `samtools markdup` → `bai` | left | `-R` line 204 + `BTOOLSPEC['samtools markdup'].outs` includes `bai`; htslib random-access requirement |
| `reference_fasta` | `reference/GRCh38.fa` | **required** | `Reference FASTA` source | top (`ref`) | `-f str(_REF)` line 204; `GIAB_LOC.reference_fasta` |
| `panel_bed` | `reference/panel.bed` | **optional** *(regions restriction; drop it for a WGS call)* | `Panel BED` source | top (`ref`) | `-R str(_PANEL_BED)` line 204; `GIAB_LOC.panel_bed` |

**Companion / user-defined inputs (reserve space, not typed ports):**
1. **Reference `.fai`** (`samtools faidx` index of `GRCh38.fa`) — `mpileup -f` implicitly
   requires it. No matching kind exists in `GIAB_LOC`, so it is **carried with**
   `reference_fasta` (a sub-artifact of the reference source), not a separate half-circle.
2. **`--ploidy` / `--ploidy-file`** (GRCh38 ploidy regions) — user-defined `call` input;
   param-level in the demo (default diploid). Reserve a top port slot if a project wires a file.
3. **`--samples` / `--samples-file`** (sample rename / subset) — user-defined; param-level.

## 3. Output ports

| Kind | File it produces | Downstream consumer card(s) | Card side | Cite |
|---|---|---|---|---|
| `vcf` | `variants/HG002.calls.vcf.gz` (bgzipped, **unnormalized**, unindexed) | `bcftools norm` → `vcf` in | right | `-Oz -o str(calls)` line 209; `BTOOLSPEC['bcftools call'].outs = ['vcf']` |

**No QC/metrics output port.** Unlike `fastp` / `samtools markdup` / `mosdepth`, `bcftools
call` emits **no** file that MultiQC aggregates in this chain — variant-level stats
(`SN` count, `ts/tv`) come from a *separate* `bcftools stats` invocation
(`qc_metrics-sources.md` §F), which the germline script does **not** run. Do **not**
invent a `variant_stats` / `bcftools_stats` output on this card; that would be its own
future node (see §5). Indexing (`bcftools index`) also happens after `norm` (line 222),
not here — so no `.csi`/`.tbi` output on this card.

## 4. Edges (concrete wires in/out)

**In:**
1. `samtools markdup` **`bam`** out → `bcftools call` **`bam`** in *(seeded `n_markdup` → `n_call`)*
2. `samtools markdup` **`bai`** out → `bcftools call` **`bai`** in *(new — index companion for `-R`)*
3. `Reference FASTA` **`reference_fasta`** out → `bcftools call` **`reference_fasta`** in (top)
4. `Panel BED` **`panel_bed`** out → `bcftools call` **`panel_bed`** in (top)

**Out:**
5. `bcftools call` **`vcf`** out → `bcftools norm` **`vcf`** in *(seeded `n_call` → `n_norm`)*

All edges are kind-matched (a `vcf` port only connects to a `vcf` port); this satisfies
Validate check **V1** (`VAL_ROWS`, typed ports).

## 5. Card layout notes

1. **Size.** Widen from today's 168 px (`NODE_W`) to **~210 px**, and tall enough for two
   left-stacked input rows (`bam`, `bai`) plus header text without the ports crowding the
   `bcftools call` / `Variant calling` label. Databricks-style: rounded rect, tool icon +
   name in the header, stage label beneath, PG badge (`substitute`) top-right.
2. **Port placement (all four sides).**
   - **Top** — the two reference/regions inputs (`reference_fasta`, `panel_bed`), matching
     the chain-wide convention that references enter from the top.
   - **Left** — the primary data inputs `bam` + `bai` (the flow that reads left→right).
   - **Right** — the single `vcf` output (flow continues into `bcftools norm`).
   - **Bottom** — **empty** here (no QC/metrics artifact). Keep the bottom edge clear so the
     card reads as "no MultiQC feed," visually distinct from `fastp`/`markdup`/`mosdepth`.
3. **Reserve, don't render, the user-defined slots.** Leave a top-edge gap so a
   `--ploidy-file` (or a future `.fai` made explicit) can be added without reflowing the
   card; do not draw a half-circle until a locator/kind backs it (honor "never invent I/O").
4. **The verdict spine stays.** Per README §6, tool cards keep the vstatus-colored left
   spine (`V_COLOR[n_call.vstatus]`, currently `ok`) — distinct from the decision-card
   spine, which was dropped.
5. **Future sibling node (out of scope for this card):** a `bcftools stats` node would take
   this card's `vcf` output and emit a `variant_stats` artifact into MultiQC — that is where
   `SN`/`ts/tv` metrics originate, and it belongs on its **own** card, not as a port here.
