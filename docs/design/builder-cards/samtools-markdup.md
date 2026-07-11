# Builder Card — samtools markdup

| Field | Value |
|---|---|
| **Status** | draft |
| **Date** | 2026-07-10 (MST) |
| **Audience** | design / frontend / bioinformatics |
| **Related** | [./README.md](./README.md) (builder-cards index) · [../frontend/README.md](../frontend/README.md) §6 (Pipeline builder — full model) · [../../data/nf-core-conventions.md](../../data/nf-core-conventions.md) (§6 sarek outputs → `ArtifactRef`) · [frontend `BuilderShared.tsx`](../../../frontend/src/components/BuilderShared.tsx) (`BTOOLSPEC` · `TOOLS.n_markdup` · `GIAB_LOC`) · [`scripts/run_giab_pipeline.py`](../../../scripts/run_giab_pipeline.py) `step_align_markdup()` |

## 1. Tool overview

1. **Tool.** `samtools markdup` — flags optical/PCR duplicate reads (SAM flag `0x400`) on a
   coordinate-sorted BAM. **Pinned version: 1.20** (`BTOOLSPEC['samtools markdup'].version`,
   `TOOLS.n_markdup.version`).
2. **Role in the germline chain.** Stage 3, `stageLabel: "Duplicate marking"` (`pg: full` —
   PipeGuard consumes its outputs directly). Sits between **bwa-mem2** (alignment) and the fan-out
   to **mosdepth** (coverage) + **bcftools call** (variant calling); its metrics file also fans
   into **MultiQC**, and its BAM is read by **NGSCheckMate** (identity/contamination).
3. **The card is a STAGE, not one binary.** In `run_giab_pipeline.py::step_align_markdup()` the
   node collapses a streamed samtools sub-pipeline (lines 126–156): `bwa-mem2 mem` → `samtools sort
   -n` (name-sort, L131) → `samtools fixmate -m` (adds the `ms`/`MC` mate tags markdup **requires**,
   L137) → `samtools sort` (coord-sort, L142) → `samtools markdup -f <stats>` (L149) → `samtools
   index` (L156). The card exposes only the **stage boundary** ports; the internal sub-steps are
   documented as bundled (§5), not as separate ports or cards. (`samtools view -c` at L158 is a
   log-only read count, not an artifact.)

## 2. Input ports

| Port kind | File / glob it maps to | Required / optional / user-defined | Upstream source card | Suggested side |
|---|---|---|---|---|
| `bam` | Aligned reads (SAM/BAM stream from `bwa-mem2 mem`, internally name-sorted → fixmate → coord-sorted before markdup) | **required** | **bwa-mem2** (`bam` out) | **left** (primary flow) |
| `reference_fasta` | `reference/GRCh38.fa` | **optional · user-defined** — needed **only** for CRAM output (`--reference` / CRAM encoding). The chain writes BAM (`-O bam`), so it is **not wired today**; reserve the port. | **Reference FASTA** source | **top** (references enter from top) |

Grounding: input `bam` = bwa-mem2 stdout, `run_giab_pipeline.py` L126–L130 piped into the
sort/fixmate/markdup chain (`BTOOLSPEC['samtools markdup'].ins = ['bam']`). CRAM-only reference
requirement is standard htslib `samtools markdup`/`sort` behaviour — never consumed for BAM output,
hence optional/reserved.

## 3. Output ports

| Port kind | File it produces | Downstream consumer card(s) | Suggested side |
|---|---|---|---|
| `bam` | `HG002.dedup.bam` → GIAB locator glob `align/*.md.bam` (parser `null`, required) | **mosdepth**, **bcftools call**, **NGSCheckMate** | **right** (primary flow) |
| `bai` | `HG002.dedup.bam.bai` — from the bundled `samtools index` (L156; markdup can also `--write-index` inline) | **mosdepth**, **bcftools call** (random-access sidecar, travels with `bam`) | **right** (below `bam`) |
| `markdup_metrics` | `HG002.markdup.txt` → GIAB locator path `qc/HG002.markdup.txt` (parser `markdup_metrics`, **optional** — `required: false`) | **MultiQC** | **bottom** (metrics/QC exit) |
| `samtools_stats` | *(not emitted today)* — `samtools stats` is **not run** in the current chain; if added it would write `reports/samtools/<sample>.stats` | **MultiQC** | **bottom** (reserved) |

Grounding: `bam`/`markdup_metrics` = markdup `-f` + output at L146–L149; `bai` = `samtools index`
at L156; both `bam` and `markdup_metrics` match `GIAB_LOC` (`BuilderShared.tsx` L326–L327) and
`BTOOLSPEC['samtools markdup'].outs = ['bam','bai','markdup_metrics']`. **`samtools_stats` is
optional · user-defined and unwired** — the phantom `samtools_stats` output was removed in T-083
(no producer in the real chain, frontend README §6); it is a documented samtools QC command that
*could* attach at this stage and feed MultiQC (nf-core sarek emits it under `reports/samtools/`,
nf-core-conventions §6), so the card reserves the port but must **never** auto-emit it.

## 4. Edges (concrete wires in/out of this card)

**Inbound**

1. **bwa-mem2** `bam` (right) → **samtools markdup** `bam` (left) — *seeded*
   (`germlineTemplate()` `wire('n_bwa','bam','n_markdup','bam')`; run L126→L149).
2. **Reference FASTA** `reference_fasta` (bottom) → **samtools markdup** `reference_fasta` (top) —
   *optional / reserved*, CRAM output only; **not present in the germline chain**.

**Outbound**

3. **samtools markdup** `bam` (right) → **mosdepth** `bam` (left) — *seeded*
   (`wire('n_markdup','bam','n_mosdepth','bam')`).
4. **samtools markdup** `bam` (right) → **bcftools call** `bam` (left) — *seeded*
   (`wire('n_markdup','bam','n_call','bam')`).
5. **samtools markdup** `bam` (right) → **NGSCheckMate** `bam` (left) — *palette-composable*
   (germline-chain note "NGSCheckMate reads the BAM"; `BTOOLSPEC['NGSCheckMate'].ins = ['bam']`; not
   in seeded `TOOLS`).
6. **samtools markdup** `bai` (right) → **mosdepth** / **bcftools call** (companion index; usually
   implicit, carried with edges 3–4).
7. **samtools markdup** `markdup_metrics` (bottom) → **MultiQC** `markdup_metrics` (top) — *seeded*
   (`wire('n_markdup','markdup_metrics','n_multiqc','markdup_metrics')`).
8. **samtools markdup** `samtools_stats` (bottom) → **MultiQC** `samtools_stats` (top) — *reserved /
   unwired* (T-083 removed this fan-in as a phantom; drawn only if a user adds `samtools stats`).

Typed-port rule (`reconcileEdges`): `bam`↔`bam`, `bai`↔`bai`, `markdup_metrics`/`samtools_stats`
only to MultiQC's matching fan-in kind, `reference_fasta` only from a fasta source — a mismatched
wire is dropped, never coerced.

## 5. Card layout notes

1. **Size.** Larger than today's fixed 168px node (`BuilderShared.NODE_W`) — a Databricks-style
   process card that hosts up to **2 inputs + 4 outputs = 6 half-circle ports** without crowding the
   header (`copy` icon · "samtools markdup" · `v1.20` · "Duplicate marking"). Height should clear
   the 4 stacked right/bottom ports.
2. **Port placement rationale.**
   - **Left:** `bam` in — primary data flow enters left.
   - **Right:** `bam` out (top) + `bai` out (below it) — primary flow exits right; the index sits
     with its BAM.
   - **Bottom:** `markdup_metrics` (+ reserved `samtools_stats`) — QC/metrics fan out downward to
     MultiQC, off the primary left→right spine.
   - **Top:** `reference_fasta` — references enter from the top (matches bwa-mem2 / bcftools cards).
3. **Bundled sub-steps (collapse inside the card body, no ports of their own):** `samtools sort -n`
   → `samtools fixmate -m` → `samtools sort` → `samtools markdup -f` → `samtools index`
   (`run_giab_pipeline.py` L131–L156). Surface them as a small "5 samtools steps" caption or expand
   affordance, not as edges — the graph's typed contract is the stage boundary only.
4. **Reserve space for user-defined ports:** `reference_fasta` (top, CRAM output) and
   `samtools_stats` (bottom, QC) are optional and unwired in the germline chain; the enlarged card
   must be able to host them when an operator opts in, but they render inert/empty by default —
   grounded, never auto-invented.
