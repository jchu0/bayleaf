# Builder Card — samtools markdup

| Field | Value |
|---|---|
| **Status** | draft |
| **Date** | 2026-07-10 (MST) · corrected 2026-07-11 (MST, NGSCheckMate retired + `samtools_stats` is now a real wired port, not reserved) |
| **Audience** | design / frontend / bioinformatics |
| **Related** | [./README.md](./README.md) (builder-cards index, §7) · [../frontend/README.md](../frontend/README.md) §6 (Pipeline builder — full model) · [../../data/nf-core-conventions.md](../../data/nf-core-conventions.md) (§6 sarek outputs → `ArtifactRef`) · [frontend `BuilderShared.tsx`](../../../frontend/src/components/BuilderShared.tsx) (`BTOOLSPEC` · `TOOLS.n_markdup` · `GIAB_LOC`) · [`scripts/run_giab_pipeline.py`](../../../scripts/run_giab_pipeline.py) `step_align_markdup()` · [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md) (custom-script successor to the retired NGSCheckMate node) |

## 1. Tool overview

1. **Tool.** `samtools markdup` — flags optical/PCR duplicate reads (SAM flag `0x400`) on a
   coordinate-sorted BAM. **Pinned version: 1.20** (`BTOOLSPEC['samtools markdup'].version`,
   `TOOLS.n_markdup.version`).
2. **Role in the germline chain.** Stage 3, `stageLabel: "Duplicate marking"` (`pg: full` —
   bayleaf consumes its outputs directly). Sits between **bwa-mem2** (alignment) and the fan-out
   to **mosdepth** (coverage) + **bcftools call** (variant calling); its metrics file also fans
   into **MultiQC**. **Corrected 2026-07-11 (Branch A of the custom-script-card effort):** the
   `NGSCheckMate` palette node this doc used to name as a BAM consumer was an unwired, never-seeded
   card and has been retired (`docs/design/builder-cards/README.md` §7) — the `ngscheckmate` KIND
   stays in the vocabulary, so an operator can still wire the dedup BAM into an
   [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md) custom-script card running
   the real `NGSCheckMate` command, but there is no longer a bespoke palette tile for it.
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
| `bam` | `HG002.dedup.bam` → GIAB locator glob `align/*.md.bam` (parser `null`, required) | **mosdepth**, **bcftools call** | **right** (primary flow) |
| `bai` | `HG002.dedup.bam.bai` — from the bundled `samtools index` (L156; markdup can also `--write-index` inline) | **mosdepth**, **bcftools call** (random-access sidecar, travels with `bam`) | **right** (below `bam`) |
| `markdup_metrics` | `HG002.markdup.txt` → GIAB locator path `qc/HG002.markdup.txt` (parser `markdup_metrics`, **optional** — `required: false`) | **MultiQC** | **bottom** (metrics/QC exit) |
| `samtools_stats` | `<sample>.samtools_stats.txt` — a real `samtools stats` command over the dedup BAM (`src/bayleaf/nextflow/catalog.py`) | **MultiQC** | **bottom** (QC exit) |

Grounding: `bam`/`markdup_metrics` = markdup `-f` + output at L146–L149; `bai` = `samtools index`
at L156; both `bam` and `markdup_metrics` match `GIAB_LOC` (`BuilderShared.tsx` L326–L327) and
`BTOOLSPEC['samtools markdup'].outs = ['bam','bai','markdup_metrics','samtools_stats']`.
**Corrected 2026-07-11 (W4, this doc was stale):** `samtools_stats` was previously described here
as "not emitted today / reserved" — that is no longer true. `samtools stats` is now a REAL,
wireable optional port: the compiler's `catalog.py` runs `samtools stats` on the dedup BAM and
publishes `*.samtools_stats.txt`, and `BuilderShared.tsx`'s `BTOOLSPEC['samtools markdup']` +
`germlineTemplate()` wire it straight to MultiQC (`wire('n_markdup','samtools_stats',
'n_multiqc','samtools_stats')`) — verified by reading both files directly. This card no longer
has any reserved/unwired output; `NGSCheckMate` is likewise no longer a consumer of `bam` — see
§1.2 above.

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
5. ~~**samtools markdup** `bam` (right) → **NGSCheckMate** `bam` (left)~~ — **retired 2026-07-11**
   (Branch A of the custom-script-card effort, `docs/design/builder-cards/README.md` §7):
   `NGSCheckMate` was never a seeded `TOOLS` node and the unwired palette tile is now gone. An
   operator can still wire `bam` into an [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md)
   custom-script card running the real `NGSCheckMate` command.
6. **samtools markdup** `bai` (right) → **mosdepth** / **bcftools call** (companion index; usually
   implicit, carried with edges 3–4).
7. **samtools markdup** `markdup_metrics` (bottom) → **MultiQC** `markdup_metrics` (top) — *seeded*
   (`wire('n_markdup','markdup_metrics','n_multiqc','markdup_metrics')`).
8. **samtools markdup** `samtools_stats` (bottom) → **MultiQC** `samtools_stats` (top) — *seeded*
   (`wire('n_markdup','samtools_stats','n_multiqc','samtools_stats')`; **corrected 2026-07-11, W4**
   — this was reserved/unwired when this doc was first written (T-083), it is a real wire now, see
   §3 above).

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
   - **Bottom:** `markdup_metrics` + `samtools_stats` — QC/metrics fan out downward to MultiQC, off
     the primary left→right spine (both are real wires, see §3's 2026-07-11 correction).
   - **Top:** `reference_fasta` — references enter from the top (matches bwa-mem2 / bcftools cards).
3. **Bundled sub-steps (collapse inside the card body, no ports of their own):** `samtools sort -n`
   → `samtools fixmate -m` → `samtools sort` → `samtools markdup -f` → `samtools index`
   (`run_giab_pipeline.py` L131–L156). Surface them as a small "5 samtools steps" caption or expand
   affordance, not as edges — the graph's typed contract is the stage boundary only.
4. **Reserve space for the one remaining user-defined port:** `reference_fasta` (top, CRAM output
   only) is optional and unwired in the germline chain (the chain writes BAM, not CRAM); the
   enlarged card must be able to host it when an operator opts in, but it renders inert/empty by
   default — grounded, never auto-invented. `samtools_stats` no longer needs reserved space — it is
   wired (§3).
