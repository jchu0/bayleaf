# Builder card — MultiQC (QC aggregation)

| Field | Value |
|---|---|
| **Status** | Draft |
| **Date** | 2026-07-10 (MST) · corrected 2026-07-11 (MST, `samtools_stats`/`mosdepth_thresholds` are now wired not reserved, W4; NGSCheckMate retired, Branch A) · corrected 2026-07-12 (MST, reserved-port honesty pass — `multiqc_html` promoted to a real optional output; the reserved top-bay input ports [`fastqc_zip`/`bcftools_stats`/`picard_hsmetrics`/`ngscheckmate`] removed) |
| **Audience** | design / frontend / bioinformatics |
| **Related** | [builder-cards/README.md](README.md) (card-set index, §7) · [design/frontend/README.md §6](../frontend/README.md) (builder node model) · [data/nf-core-conventions.md §4](../../data/nf-core-conventions.md) (MultiQC → `MetricValue` + registry) · [data/qc_metrics-sources.md](../../data/qc_metrics-sources.md) (module keys) · [frontend `BuilderShared.tsx`](../../../frontend/src/components/BuilderShared.tsx) (`TOOLS` n_multiqc, `BTOOLSPEC['MultiQC']`, `GIAB_LOC`) · [`src/pipeguard/nextflow/catalog.py`](../../../src/pipeguard/nextflow/catalog.py) (the compiler's `MultiQC` `ProcessSpec`, the ground truth for the 5 wired inputs) · [`scripts/run_giab_pipeline.py`](../../../scripts/run_giab_pipeline.py) (producers of the inputs) · [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md) (custom-script successor to the retired NGSCheckMate node) |

## 1. Tool overview + role in the chain

**MultiQC** — pinned **v1.21** (matches `BuilderShared.tsx`; MultiQC's current line is 1.x). Icon `layers`, stage label **"QC aggregation"**, PG badge **consumes** (`pg: 'full'`).

MultiQC is an **aggregator**: it *scans a directory tree*, auto-detects log/report files from ~150 supported tools, and merges them into one HTML report plus a machine-readable `multiqc_data/` bundle. It is the **terminal QC node** of the germline chain — the fan-in point where fastp / samtools-markdup / mosdepth outputs converge. Its `multiqc_json` output is an **emitted locator** that deterministic ingest reads into `MetricValue` (nf-core-conventions §4); the terminal **Gate** decides from the frozen `run/` CSVs, never from a direct MultiQC edge (README §6).

> **Grounding honesty.** The offline demo driver `run_giab_pipeline.py` does **not** invoke MultiQC — it parses `HG002.fastp.json` (`parse_fastp`, L230) and `HG002.mosdepth.summary.txt` (`step_mosdepth`, L168–193) directly in Python. This card is therefore grounded in MultiQC's **documented CLI I/O** + nf-core-conventions §4, and in the script only as the **producer of MultiQC's inputs** (fastp JSON at L108/step_fastp; markdup stats at L146–149; mosdepth summary at L179). The card is design-forward but never invents an I/O the tool lacks.

**Aggregator implication (the maintainer's ask):** MultiQC's inputs are *open-ended* in the tool itself — it discovers logs by scanning — so this card hosts **many** left input ports (5 wired QC streams). **But the shipped card no longer pre-reserves speculative top-bay input ports** (2026-07-12, §2): the compiler fixes MultiQC's inputs to its `ProcessSpec`, so a reserved port with no producer could never carry a real wire. An operator who wants an extra QC stream adds a producer via an [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md) custom-script card, not a pre-reserved port.

## 2. INPUT PORTS

Primary QC fan-in enters from the **left** (flows left→right from upstream stage cards). Additional discoverable QC logs enter from a **top** fan-in bay (they are scanned, not strictly ordered in the stage flow).

| Port kind | File / glob it maps to | Req / Opt / User-def | Upstream source card | Card side |
|---|---|---|---|---|
| `fastp_json` | `qc/HG002.fastp.json` (`GIAB_LOC` fastp_json) | **required** (wired) | fastp | left |
| `markdup_metrics` | `qc/HG002.markdup.txt` (`GIAB_LOC` markdup_metrics; `samtools markdup -f`, script L146–149) | optional (wired) | samtools markdup | left |
| `samtools_stats` | `<sample>.samtools_stats.txt` (compiler `catalog.py`, a real `samtools stats` over the dedup BAM) | optional (**wired**) | samtools markdup | left |
| `mosdepth_summary` | `mosdepth/HG002.summary.txt` (`GIAB_LOC` mosdepth_summary) | required (wired) | mosdepth | left |
| `mosdepth_thresholds` | `mosdepth/HG002.thresholds.bed.gz` (compiler `catalog.py`) | optional (**wired**) | mosdepth | left |

**Corrected 2026-07-11 (W4):** `samtools_stats` and `mosdepth_thresholds` are REAL wired inputs
(not the reserved user-defined ports this table once listed) — verified against
`src/pipeguard/nextflow/catalog.py`'s `MultiQC` `ProcessSpec` + `BuilderShared.tsx`'s
`germlineTemplate()`. MultiQC ingests **5** QC streams (was 3).

**Corrected 2026-07-12 (reserved-port honesty pass, `1621e3f`) — the top-bay reserved input ports
are REMOVED.** `fastqc_zip`, `bcftools_stats`, `picard_hsmetrics`, and `ngscheckmate` were dropped
from `MultiQC`'s `CARD_PORTS`: no tool in the catalogued germline chain produces them, and MultiQC's
inputs are **fixed by its `ProcessSpec`** (the compiler's input-drift guard is exact), so a reserved
top port could never have carried a real wire — a superficial slot, so it was removed rather than
left dangling. The design aspiration (an operator adds a QC producer) is unchanged but is now
realized differently: the operator authors that producer as an [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md)
custom-script card emitting a registered kind, rather than PipeGuard pre-reserving speculative
MultiQC top ports (`ngscheckmate` stays a valid `ARTIFACT_KINDS` member for exactly this).

## 3. OUTPUT PORTS

| Port kind | File it produces | Downstream consumer card(s) | Card side |
|---|---|---|---|
| `multiqc_json` | `multiqc_data/multiqc_data.json` (`GIAB_LOC` multiqc_json, `required: false`, parser `null`) | deterministic **ingest** → `MetricValue`/`MetricRegistry` → terminal **Gate** (nf-core §4; not a direct on-canvas edge) | right |
| `multiqc_html` *(optional, real)* | `multiqc_report.html` | **none downstream** — human-facing terminal report artifact (Provenance / operator download) | bottom |

> `multiqc_json` is the machine output PipeGuard cares about; its keys (`report_general_stats_data`, `report_saved_raw_data`, **`report_data_sources`** — the per-metric file pointer, `report_general_stats_headers`) are the `MetricValue` + `Evidence.source` bridge (nf-core §4). **`multiqc_html` was PROMOTED 2026-07-12 (`1621e3f`) from reserved to a real optional output:** `multiqc .` always writes `multiqc_report.html` (no `--no-report`), so it is a genuine product of the current command — the compiler now declares + publishes it as a real `emit: multiqc_html` channel, and it is in `ARTIFACT_KINDS`. It wires to no downstream card (read by humans, not the gate), but it is a real, wireable optional port, not a reserved slot.

## 4. EDGES (concrete wires in/out)

**Inbound (5, all present in `germlineTemplate()`, corrected 2026-07-11 — was 3):**

1. `fastp` · out `fastp_json` → `MultiQC` · in `fastp_json`
2. `samtools markdup` · out `markdup_metrics` → `MultiQC` · in `markdup_metrics`
3. `samtools markdup` · out `samtools_stats` → `MultiQC` · in `samtools_stats` (W3/W4; was reserved)
4. `mosdepth` · out `mosdepth_summary` → `MultiQC` · in `mosdepth_summary`
5. `mosdepth` · out `mosdepth_thresholds` → `MultiQC` · in `mosdepth_thresholds` (W3/W4; was reserved)

**Outbound:**

6. `MultiQC` · out `multiqc_json` → **(no tool card)**. Emitted as the `multiqc_json` locator (`multiqc_data/multiqc_data.json`); consumed off-canvas by deterministic ingest → the terminal Gate. MultiQC is a **graph sink** — `germlineTemplate()` wires no edge out of `n_multiqc`.
7. `MultiQC` · out `multiqc_html` → **(no card)**. Terminal human report — now a **real published `emit: multiqc_html` output** (promoted 2026-07-12, §3), still unwired to any downstream card because it is read by humans, not the gate.

**No reserved input ports remain (2026-07-12):** the former top-bay reserved ports were removed (§2). To add a QC producer, author it as an [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md) custom-script card emitting a registered kind — the wiring then offers only kinds the vocabulary knows.

## 5. Card layout notes

1. **Size — larger than the 168px default (`NODE_W`).** MultiQC is the widest fan-in in the chain; target **~230 × ~150** so 5 left ports + 2 output ports fit without crowding the "MultiQC · v1.21 · QC aggregation" header (Databricks process-card aesthetic: generous header, ports on the perimeter, clear body).
2. **Left = primary QC fan-in** (5 wired ports, stacked top-to-bottom in stage order: fastp_json, markdup_metrics, samtools_stats, mosdepth_summary, mosdepth_thresholds — **corrected 2026-07-11, was 3**) — these flow left→right from the upstream stage cards.
3. **Top = clean (no reserved input bay as of 2026-07-12).** The design once called for a reserved discoverable-log bay here; the shipped card dropped it (§2) because the compiler fixes MultiQC's inputs — a reserved top port could never wire. Extra QC producers arrive as custom-script cards feeding the left fan-in, not a pre-reserved top bay.
4. **Right = `multiqc_json`** — the machine output continuing toward the terminal Gate (which sits to MultiQC's right in the seeded layout, x:1840 → gate).
5. **Bottom = `multiqc_html`** — the human report exiting downward as a terminal artifact (matches the "QC/reports exit bottom" side convention).
6. **Growth without reserved slots (updated 2026-07-12):** the earlier "reserve ≥3–4 top slots"
   guidance is superseded — reserved ports for producers that don't exist are exactly what the
   reserved-port honesty pass removed. A lab that wants FastQC / bcftools-stats / Picard-CollectHsMetrics /
   an NGSCheckMate identity check feeding MultiQC authors that producer as an [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md)
   custom-script card emitting a registered kind (`ngscheckmate` is a real, wireable `ARTIFACT_KINDS`
   member for this), then wires it into the left fan-in. Typed wiring keeps a non-QC kind (a `bam` or
   `fastq`) off every MultiQC input.
7. **No verdict color / no left spine** — MultiQC is a tool card; the verdict-colored spine is reserved and the node is `draft`-neutral until a run binds (README §6).
