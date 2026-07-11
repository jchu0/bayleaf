# Builder card — fastp

| Field | Value |
|---|---|
| **Status** | Draft |
| **Date** | 2026-07-10 (MST) |
| **Audience** | frontend / bioinformatics / design |
| **Related** | [builder-cards/README.md](README.md) · [design/frontend/README.md §6](../frontend/README.md) · [data/nf-core-conventions.md](../../data/nf-core-conventions.md) · [data/qc_metrics-sources.md](../../data/qc_metrics-sources.md) · [frontend BuilderShared.tsx](../../../frontend/src/components/BuilderShared.tsx) · [scripts/run_giab_pipeline.py](../../../scripts/run_giab_pipeline.py) |

Card-design spec for the **fastp** node in the Pipeline Builder. Expands the minimal
`BTOOLSPEC['fastp']` (`ins: ['fastq']`, `outs: ['fastp_json', 'fastq']`) to the tool's full
documented I/O so the card can host every real port. Ports are typed (a `fastq` port only
connects to a `fastq` port). Nothing here invents an I/O fastp doesn't have.

## 1. Tool overview

- **Tool / version:** `fastp` **0.23.4** (pinned in `BTOOLSPEC` + `TOOLS[n_fastp]`; verified at
  runtime via `_tool_version`, `run_giab_pipeline.py:109`).
- **Role in the germline chain:** first stage. Adapter/quality trimming **plus** read-level QC
  (Q30, duplication, reads-passing-filter). It sits at the head of the flow:
  **raw FASTQ → `fastp` → bwa-mem2 → …**, and its JSON also feeds MultiQC at the tail.
- **Real command** (`run_giab_pipeline.py:110–114`):
  ```
  fastp -i HG002.R1.fastq.gz -I HG002.R2.fastq.gz \
        -o HG002.trim.R1.fastq.gz -O HG002.trim.R2.fastq.gz \
        -j HG002.fastp.json -h HG002.fastp.html -w 3
  ```
  Paired-end in, paired-end trimmed out, one JSON report (parsed by PipeGuard's `parse_fastp`
  for Q30/reads-PF/duplication, `run_giab_pipeline.py:230`) and one HTML report.
- **PG status:** `ours` — PipeGuard parses this tool's JSON directly for gated metrics.

## 2. Input ports

| Port kind | Maps to (flag → file/glob) | Req/Opt/User | Upstream source card | Card side |
|---|---|---|---|---|
| `fastq` | `-i` / `-I` → `fastq/*_R{1,2}_001.fastq.gz` | **required** | Raw FASTQ (Submit / demux boundary) | left |
| `adapter_fasta` *(reserve)* | `--adapter_fasta` → user-supplied `.fasta` | user-defined | Reference source (`db`) | top |

Notes:
1. The builder collapses the R1/R2 mate pair into **one typed `fastq` input port**. The real
   CLI splits it across `-i`/`-I`; the `fastq` locator globs both mates as one entry
   (`GIAB_LOC` `fastq`, `field: glob`, `on: 'all'` → 2 files), so a single port is honest.
2. `adapter_fasta` is **not** used in the real run — the demo relies on `detect_adapter_for_pe`
   (a param, not a port). Reserve the port slot but leave it unwired; it needs a new
   `adapter_fasta` kind (not yet in `ARTIFACT_KINDS`) before it can carry an edge.

## 3. Output ports

| Port kind | Produces (flag → file) | Downstream consumer card(s) | Card side |
|---|---|---|---|
| `fastq` | `-o` / `-O` → `HG002.trim.R{1,2}.fastq.gz` | bwa-mem2 (`fastq` in) | right |
| `fastp_json` | `-j` → `HG002.fastp.json` | MultiQC (`fastp_json` in); PipeGuard `parse_fastp` | bottom |
| `fastp_html` *(reserve)* | `-h` → `HG002.fastp.html` | Human report / MultiQC | bottom |
| `unpaired_fastq` *(reserve)* | `--unpaired1/2` → unpaired reads | (none by default) | right |
| `failed_fastq` *(reserve)* | `--failed_out` → filtered-out reads | (none by default) | bottom |

Notes:
1. `fastq` (out) and `fastp_json` are the two real, wired outputs (see `TOOLS[n_fastp].outputs`).
2. `fastp_html` is a **real** fastp output (`-h`, `run_giab_pipeline.py:112`) but has **no
   locator kind** in `GIAB_LOC` today — reserve the port; a `fastp_html` kind would be added
   only if MultiQC/Provenance start consuming it as a typed edge.
3. `--unpaired1/2`, `--failed_out`, `-m/--merged_out` are documented fastp outputs but **off** in
   the germline run (user-defined). Reserve slots; do not wire.

## 4. Edges (concrete wires)

**Into the card:**
- Raw FASTQ (run intake / demux `fastq` output) → **fastp `fastq` (in, left)**. No upstream
  *tool* card — fastp is stage 0; the pair enters from the run's raw reads.

**Out of the card** (from `germlineTemplate()` wiring, `BuilderShared.tsx:300–309`):
- fastp **`fastq` (out, right)** → **bwa-mem2 `fastq` (in)** — `wire('n_fastp','fastq','n_bwa','fastq')`.
- fastp **`fastp_json` (out, bottom)** → **MultiQC `fastp_json` (in)** — `wire('n_fastp','fastp_json','n_multiqc','fastp_json')`.
- fastp **`fastp_html` (out, bottom)** → *(unwired — no consumer kind yet)*.

## 5. Card layout notes

1. **Size:** larger than today's 168px node — target ≈ **220×150px** so up to 2 left + 1 top
   input and 2 right + 2 bottom output half-circles fit clear of the header (icon `scissors` +
   "fastp 0.23.4" + stage label "Read QC + trim") and the `ours` badge.
2. **Port placement rationale** (Databricks-style, flow reads left→right):
   - **Left:** primary `fastq` input (the raw read pair) — main data ingress.
   - **Top:** `adapter_fasta` reference input — references/panels enter from the top, matching
     bwa-mem2's `reference_fasta` and mosdepth's `panel_bed` cards.
   - **Right:** trimmed `fastq` output — the primary flow continues to bwa-mem2.
   - **Bottom:** QC/metrics exits — `fastp_json` (→ MultiQC) and `fastp_html`, so QC artifacts
     drop away from the primary alignment lane.
3. **Reserved (unshown-by-default) ports:** `adapter_fasta` (top), `fastp_html` (bottom),
   `unpaired_fastq`/`failed_fastq` (right/bottom). Keep geometric room for them so enabling a
   user-defined output later doesn't reflow the card; render only when populated.
4. **Typed-wiring guard:** every port carries its `kind`; `fastq`↔`fastq`, `fastp_json`↔
   `fastp_json` only. The two reserved kinds (`adapter_fasta`, `fastp_html`) must be added to
   `ARTIFACT_KINDS` before their ports can accept an edge — until then they render as
   disabled/reserved stubs.
