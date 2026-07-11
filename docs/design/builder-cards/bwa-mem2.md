# Builder card — bwa-mem2 (alignment)

| Field | Value |
|---|---|
| **Status** | draft |
| **Date** | 2026-07-10 (MST) |
| **Related** | [builder-cards README](../builder-cards/README.md) · [frontend README §6](../frontend/README.md) · [nf-core conventions](../../data/nf-core-conventions.md) · [BuilderShared.tsx](../../../frontend/src/components/BuilderShared.tsx) · [run_giab_pipeline.py](../../../scripts/run_giab_pipeline.py) |

Card-design spec for the **bwa-mem2** node in the Pipeline Builder (README §6). Grounds the card's
half-circle connection ports in the tool's real CLI I/O and the exact command the germline chain
runs. The current [`BTOOLSPEC`](../../../frontend/src/components/BuilderShared.tsx) entry
(`ins: ['fastq', 'reference_fasta']`, `outs: ['bam']`) is the **minimum**; this doc expands it to
the tool's full real I/O and lays out where the ports sit.

## 1. Tool overview

- **Tool / version:** `bwa-mem2 mem` — **2.2.1** (pinned in `BTOOLSPEC['bwa-mem2']` and the seeded
  `TOOLS` node `n_bwa`; `pg: partial` → the "substitute" badge, a drop-in for `bwa mem`).
- **Role in the chain:** **Alignment.** Second stage — maps the fastp-trimmed paired reads onto the
  reference, emitting the alignment stream that feeds duplicate marking.
- **Data flow:** `Reference FASTA (indexed) + fastp(fastq) → bwa-mem2 → samtools markdup`.
- **Real command** (`run_giab_pipeline.py` `step_align_markdup`, L124-130):
  `bwa-mem2 mem -t 4 -R "@RG\tID:HG002\tSM:HG002\tPL:ILLUMINA\tLB:HG002-panel" <ref> <R1> <R2>`,
  its SAM piped straight into `samtools sort -n | fixmate -m | sort | markdup` (never written to a
  file in this pipeline).
- **Reference bundle:** the `<ref>` argument is the FASTA **prefix** (`data/real-giab/ref/chr20.fa`)
  plus the sidecar index built once by `bwa-mem2 index chr20.fa` (`scripts/README.md` L145). bwa-mem2
  resolves the sidecars by the FASTA path — they travel as **one** logical reference artifact, so the
  card carries a **single** `reference_fasta` input port, not one per sidecar file.

## 2. INPUT PORTS

| Port kind | File / glob it maps to | Required? | Upstream source card | Card side |
|---|---|---|---|---|
| `fastq` | trimmed pair `HG002.trim.R{1,2}.fastq.gz` (glob `fastq/*_R{1,2}_001.fastq.gz`; `GIAB_LOC.fastq`, `on_multiple: all`) | **required** | fastp (`n_fastp` → `fastq` out) | **left** |
| `reference_fasta` | indexed reference bundle: `reference/GRCh38.fa` + `.0123` · `.amb` · `.ann` · `.bwt.2bit.64` · `.pac` (`GIAB_LOC.reference_fasta`, role `reference`) | **required** | Reference FASTA source (`r_fasta` → `reference_fasta` out) | **top** |
| `read_group` (`-R @RG\t…`) | not an artifact — the `@RG` header string (`run_giab_pipeline.py` L123) | **user-defined** | — (Params tab; reserve an optional config port, not wired today) | left (reserved) |

Notes:
1. The `fastq` port represents the **R1+R2 pair** as one typed edge (the `*_R{1,2}` glob resolves
   both mates; `on_multiple: all`). One port, two files — not two ports.
2. `reference_fasta` is the **indexed** bundle. The five bwa-mem2 sidecars
   (`.0123` packed forward+reverse sequence · `.amb` ambiguous/non-ACGT bases · `.ann` contig
   names/lengths · `.bwt.2bit.64` the FMD/BWT index · `.pac` 2-bit packed reference) are the tool's
   real index inputs but are **keyed off the FASTA prefix**, so they do not get their own port kinds
   (none exist in `GIAB_LOC`). The `samtools faidx` `.fai` is **not** consumed by `bwa-mem2 mem`
   (it's a downstream random-access accessory for mosdepth/bcftools) — do not add a port for it here.
3. `read_group` is a **param string**, not a wired artifact — it lives in the Params inspector.
   Reserve space for one optional user-defined config port so a future read-group source could wire
   in, but leave it unwired by default (compose ≠ execute; today it is authored, not fed).

## 3. OUTPUT PORTS

| Port kind | File it produces | Downstream consumer card(s) | Card side |
|---|---|---|---|
| `bam` | aligned reads — SAM on **stdout**, streamed (not a persisted file in this chain) | samtools markdup (`n_markdup` → `bam` in) | **right** |

Notes:
1. bwa-mem2 mem emits **SAM to stdout**; in the germline chain it is piped directly into
   `samtools sort/fixmate/markdup` and never lands as its own file. The card's single `bam` output
   port is the honest abstraction of that alignment stream (kind `bam`, matching the current
   `TOOLS` / `BTOOLSPEC` output and the `germlineTemplate()` wire `n_bwa:bam → n_markdup:bam`).
2. **No bottom/QC port.** Unlike fastp (`fastp_json`), samtools markdup (`markdup_metrics`), and
   mosdepth (`mosdepth_summary`), bwa-mem2 produces **no QC/metrics artifact** of its own — so this
   card has **no bottom metrics port**. Alignment-derived QC (mapping rate, insert size) comes from
   `samtools flagstat`/Picard downstream, not from the aligner. Keep the bottom edge clean.
3. The `.bai` index is **not** a bwa-mem2 output — it is produced downstream by `samtools index`
   after markdup (`n_markdup` outputs `bam`·`bai`·`markdup_metrics`). NGSCheckMate reads that
   **deduped, indexed** BAM, so it is a consumer of markdup's output, **not** a direct consumer of
   this card's `bam` port.

## 4. EDGES

Concrete wires touching this card (kind-matched, per `germlineTemplate()` and `SEEDED_WIRES`):

| Direction | From (card · out port) | To (card · in port) | Kind |
|---|---|---|---|
| in | Reference FASTA (`r_fasta` · `reference_fasta`) | **bwa-mem2** (`reference_fasta`, top) | `reference_fasta` |
| in | fastp (`n_fastp` · `fastq`) | **bwa-mem2** (`fastq`, left) | `fastq` |
| out | **bwa-mem2** (`bam`, right) | samtools markdup (`n_markdup` · `bam`, left) | `bam` |

No edge leaves the bottom of this card (no QC artifact). Typed compatibility holds on every wire
(`reference_fasta`→`reference_fasta`, `fastq`→`fastq`, `bam`→`bam`); a fasta can never land on a
fastq port.

## 5. Card layout notes

1. **Size.** Grow beyond today's 168 px (`NODE_W`/`UW`) — target ≈ **230 × 130 px** so a top ref
   port, a left data port, and a right output port each get clear real estate without crowding the
   `bwa-mem2` / `2.2.1` / "Alignment" header text. Databricks-style process card: rounded rect,
   left accent rail (verdict-neutral here; the colored rail is a tool-card affordance), icon =
   `merge`.
2. **Port placement rationale (all four sides in play, three used):**
   - **Top —** `reference_fasta` (references/panel enter from the top per the builder convention;
     visually separates the static reference bundle from the flowing sample data).
   - **Left —** `fastq` (primary sample data flows left→right through the chain).
   - **Right —** `bam` (alignment stream exits right into markdup).
   - **Bottom —** intentionally **empty** (no metrics/QC artifact; documents the asymmetry vs
     fastp/markdup/mosdepth cards that do exit metrics from the bottom).
3. **Reserved / user-defined ports.** Keep space (top-left) for one **optional** user-defined
   config port for the `@RG` read-group string, rendered as a half-circle only when the operator
   opts to wire a read-group source; default state shows it in the **Params** tab, unwired. Threads
   (`-t`) and other flags stay Params-only, never ports.
4. **Port count to host:** 2 required data ins + 1 required out + 1 reserved user-defined =
   **up to 4 half-circles**, comfortably inside a 230 × 130 card with the ports distributed across
   three sides.
