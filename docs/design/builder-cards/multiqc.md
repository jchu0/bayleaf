# Builder card — MultiQC (QC aggregation)

| Field | Value |
|---|---|
| **Status** | Draft |
| **Date** | 2026-07-10 (MST) · corrected 2026-07-11 (MST, `samtools_stats`/`mosdepth_thresholds` are now wired not reserved, W4; NGSCheckMate retired, Branch A) |
| **Audience** | design / frontend / bioinformatics |
| **Related** | [builder-cards/README.md](README.md) (card-set index, §7) · [design/frontend/README.md §6](../frontend/README.md) (builder node model) · [data/nf-core-conventions.md §4](../../data/nf-core-conventions.md) (MultiQC → `MetricValue` + registry) · [data/qc_metrics-sources.md](../../data/qc_metrics-sources.md) (module keys) · [frontend `BuilderShared.tsx`](../../../frontend/src/components/BuilderShared.tsx) (`TOOLS` n_multiqc, `BTOOLSPEC['MultiQC']`, `GIAB_LOC`) · [`src/pipeguard/nextflow/catalog.py`](../../../src/pipeguard/nextflow/catalog.py) (the compiler's `MultiQC` `ProcessSpec`, the ground truth for the 5 wired inputs) · [`scripts/run_giab_pipeline.py`](../../../scripts/run_giab_pipeline.py) (producers of the inputs) · [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md) (custom-script successor to the retired NGSCheckMate node) |

## 1. Tool overview + role in the chain

**MultiQC** — pinned **v1.21** (matches `BuilderShared.tsx`; MultiQC's current line is 1.x). Icon `layers`, stage label **"QC aggregation"**, PG badge **consumes** (`pg: 'full'`).

MultiQC is an **aggregator**: it *scans a directory tree*, auto-detects log/report files from ~150 supported tools, and merges them into one HTML report plus a machine-readable `multiqc_data/` bundle. It is the **terminal QC node** of the germline chain — the fan-in point where fastp / samtools-markdup / mosdepth outputs converge. Its `multiqc_json` output is an **emitted locator** that deterministic ingest reads into `MetricValue` (nf-core-conventions §4); the terminal **Gate** decides from the frozen `run/` CSVs, never from a direct MultiQC edge (README §6).

> **Grounding honesty.** The offline demo driver `run_giab_pipeline.py` does **not** invoke MultiQC — it parses `HG002.fastp.json` (`parse_fastp`, L230) and `HG002.mosdepth.summary.txt` (`step_mosdepth`, L168–193) directly in Python. This card is therefore grounded in MultiQC's **documented CLI I/O** + nf-core-conventions §4, and in the script only as the **producer of MultiQC's inputs** (fastp JSON at L108/step_fastp; markdup stats at L146–149; mosdepth summary at L179). The card is design-forward but never invents an I/O the tool lacks.

**Aggregator implication (the maintainer's ask):** MultiQC's inputs are *open-ended* — it discovers logs by scanning, so a real card must **host many input ports** and reserve capacity for QC logs beyond the three the demo chain wires today. Ports below split into **wired** (present in `germlineTemplate()`) and **reserved / user-defined** (documented MultiQC modules an operator may drop into this pipeline).

## 2. INPUT PORTS

Primary QC fan-in enters from the **left** (flows left→right from upstream stage cards). Additional discoverable QC logs enter from a **top** fan-in bay (they are scanned, not strictly ordered in the stage flow).

| Port kind | File / glob it maps to | Req / Opt / User-def | Upstream source card | Card side |
|---|---|---|---|---|
| `fastp_json` | `qc/HG002.fastp.json` (`GIAB_LOC` fastp_json) | **required** (wired) | fastp | left |
| `markdup_metrics` | `qc/HG002.markdup.txt` (`GIAB_LOC` markdup_metrics; `samtools markdup -f`, script L146–149) | optional (wired) | samtools markdup | left |
| `samtools_stats` | `<sample>.samtools_stats.txt` (compiler `catalog.py`, a real `samtools stats` over the dedup BAM) | optional (**wired**) | samtools markdup | left |
| `mosdepth_summary` | `mosdepth/HG002.summary.txt` (`GIAB_LOC` mosdepth_summary) | required (wired) | mosdepth | left |
| `mosdepth_thresholds` | `mosdepth/HG002.thresholds.bed.gz` (compiler `catalog.py`) | optional (**wired**) | mosdepth | left |
| `fastqc_zip` | `qc/*_fastqc.zip` | user-defined | FastQC (not in demo chain) | top |
| `bcftools_stats` | `qc/*.bcftools.stats` | user-defined | bcftools stats (not in demo chain) | top |
| `picard_hsmetrics` | `qc/*.hs_metrics.txt` | user-defined | Picard CollectHsMetrics (panel; nf-core §4) | top |

**Corrected 2026-07-11 (W4, this table was stale):** `samtools_stats` and `mosdepth_thresholds`
were previously listed here as unwired/reserved user-defined ports — that is no longer true. Both
are REAL wired inputs, verified by reading `src/pipeguard/nextflow/catalog.py`'s `MultiQC`
`ProcessSpec` and `BuilderShared.tsx`'s `germlineTemplate()` wire list directly. MultiQC now
ingests **5** QC streams (was 3). The `ngscheckmate` row this table used to carry is retired
(Branch A of the custom-script-card effort, `docs/design/builder-cards/README.md` §7) — `NGSCheckMate`
was never a seeded producer card, so there was never a real edge to remove; `ngscheckmate` stays a
valid `ARTIFACT_KINDS` member an operator's custom-script card ([ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md))
could still emit and wire into this same top bay.

> **User-defined ports are real MultiQC modules**, not invented kinds. `fastqc_zip`/`bcftools_stats`/`picard_hsmetrics` are **not yet in `ARTIFACT_KINDS`** (the union of `BTOOLSPEC` + `GIAB_LOC`); adding any as a live port requires registering the kind + a producer card first. The card **reserves the port slots**; the wiring only offers kinds the vocabulary knows.

## 3. OUTPUT PORTS

| Port kind | File it produces | Downstream consumer card(s) | Card side |
|---|---|---|---|
| `multiqc_json` | `multiqc_data/multiqc_data.json` (`GIAB_LOC` multiqc_json, `required: false`, parser `null`) | deterministic **ingest** → `MetricValue`/`MetricRegistry` → terminal **Gate** (nf-core §4; not a direct on-canvas edge) | right |
| `multiqc_html` | `multiqc_report.html` | **none** — human-facing terminal report artifact (Provenance / operator download) | bottom |

> `multiqc_json` is the machine output PipeGuard cares about; its keys (`report_general_stats_data`, `report_saved_raw_data`, **`report_data_sources`** — the per-metric file pointer, `report_general_stats_headers`) are the `MetricValue` + `Evidence.source` bridge (nf-core §4). `multiqc_html` is **not** in the current kind vocabulary — reserve the port; it wires to no downstream card (it is read by humans, not the gate).

## 4. EDGES (concrete wires in/out)

**Inbound (5, all present in `germlineTemplate()`, corrected 2026-07-11 — was 3):**

1. `fastp` · out `fastp_json` → `MultiQC` · in `fastp_json`
2. `samtools markdup` · out `markdup_metrics` → `MultiQC` · in `markdup_metrics`
3. `samtools markdup` · out `samtools_stats` → `MultiQC` · in `samtools_stats` (W3/W4; was reserved)
4. `mosdepth` · out `mosdepth_summary` → `MultiQC` · in `mosdepth_summary`
5. `mosdepth` · out `mosdepth_thresholds` → `MultiQC` · in `mosdepth_thresholds` (W3/W4; was reserved)

**Outbound:**

6. `MultiQC` · out `multiqc_json` → **(no tool card)**. Emitted as the `multiqc_json` locator (`multiqc_data/multiqc_data.json`); consumed off-canvas by deterministic ingest → the terminal Gate. MultiQC is a **graph sink** — `germlineTemplate()` wires no edge out of `n_multiqc`.
7. `MultiQC` · out `multiqc_html` → **(no card)**. Terminal human report (still unwired — `multiqc_html` is not a wired `BTOOLSPEC`/compiler output today).

**Reserved (user-defined, not wired today):** any of the §2 top-bay ports → `MultiQC`, once its producer card + kind exist (e.g. a FastQC card → `fastqc_zip`).

## 5. Card layout notes

1. **Size — larger than the 168px default (`NODE_W`).** MultiQC is the widest fan-in in the chain; target **~230 × ~150** so 5 left ports + a top reserve bay + 2 output ports fit without crowding the "MultiQC · v1.21 · QC aggregation" header (Databricks process-card aesthetic: generous header, ports on the perimeter, clear body).
2. **Left = primary QC fan-in** (5 wired ports, stacked top-to-bottom in stage order: fastp_json, markdup_metrics, samtools_stats, mosdepth_summary, mosdepth_thresholds — **corrected 2026-07-11, was 3**) — these flow left→right from the upstream stage cards.
3. **Top = discoverable-log bay** (reserved user-defined ports) — reflects that MultiQC *scans* for logs rather than receiving them in the linear stage flow; keep them visually distinct (faded/optional styling) from the wired left ports.
4. **Right = `multiqc_json`** — the machine output continuing toward the terminal Gate (which sits to MultiQC's right in the seeded layout, x:1840 → gate).
5. **Bottom = `multiqc_html`** — the human report exiting downward as a terminal artifact (matches the "QC/reports exit bottom" side convention).
6. **Reserve space for growth:** the top bay should host **≥3–4** optional port slots so an operator can drop FastQC / bcftools-stats / Picard-CollectHsMetrics into the pipeline and wire them in without the card re-flowing (`samtools_stats` moved out of this list 2026-07-11 — it is wired, §2). A lab that wants an identity/swap check like NGSCheckMate feeding this bay authors it as an [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md) custom-script card (there is no longer a bespoke NGSCheckMate palette tile, `docs/design/builder-cards/README.md` §7) — its `ngscheckmate`-kind output is still a real, wireable `ARTIFACT_KINDS` member. Typed wiring keeps a non-QC kind (e.g. a `bam` or `fastq`) off every MultiQC input.
7. **No verdict color / no left spine** — MultiQC is a tool card; the verdict-colored spine is reserved and the node is `draft`-neutral until a run binds (README §6).
