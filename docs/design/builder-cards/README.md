# Builder cards — card-design convention + index

| Field | Value |
|---|---|
| **Status** | draft (§§1–3 now mostly REALIZED — see §5) |
| **Date** | 2026-07-10 (MST) · updated 2026-07-11 (MST, card geometry) · updated 2026-07-11 (MST, edge clarity + off-canvas boundary) |
| **Audience** | frontend / design / bioinformatics |
| **Related** | [frontend/README.md §6](../frontend/README.md#6-pipeline-builder--full-model) (Pipeline Builder — full node model) · [design/ui-conventions.md UIC-16](../ui-conventions.md) · [data/nf-core-conventions.md](../../data/nf-core-conventions.md) (tool I/O → `ArtifactRef` / `MetricValue`) · [data/qc_metrics-sources.md](../../data/qc_metrics-sources.md) (metric provenance) · [frontend `BuilderShared.tsx`](../../../frontend/src/components/BuilderShared.tsx) (`BTOOLSPEC` · `TOOLS` · `GIAB_LOC` · `germlineTemplate()` · `portSide()` · `layoutPorts()` · `cardHeight()`) · [frontend `BuilderCanvas.tsx`](../../../frontend/src/components/BuilderCanvas.tsx) (current render + wiring) · [scripts/run_giab_pipeline.py](../../../scripts/run_giab_pipeline.py) (the real germline commands the cards abstract) |

This is the **general** card-design convention for the Pipeline Builder, plus the index of the
per-tool card specs. Each per-tool doc grounds one node's ports in that tool's **real** CLI I/O and
the exact germline command it wraps; this doc holds the shared rules those specs assume. The
convention was a **design target** — as of 2026-07-11 (commit `12a9913`) the current
[`BuilderCanvas`](../../../frontend/src/components/BuilderCanvas.tsx) implements **most** of it
(larger cards, four-sided typed half-circle ports); one item (§5.4, registering the remaining
reserved kinds) stays open — see §5.

## 1. Philosophy — Databricks-style process cards

1. **A node is a process card, not a chip.** Model each tool as a Databricks-inspired process card:
   a rounded rectangle with a header row (icon · tool name · pinned version · stage label · PG
   badge) and a body large enough to host the tool's connection ports around its perimeter.
2. **Typed half-circle ports on all four sides.** Every input and output is a typed half-circle
   port carrying a `kind` (`fastq`, `bam`, `reference_fasta`, `mosdepth_summary`, …). A node hosts
   **enough ports for all of the tool's real I/O**, distributed across the four edges — not a single
   left-in / right-out pair.
3. **An edge is typed data flow.** An edge runs from an **output** port to a **matching input**
   port of the same `kind` (`vcf`→`vcf`, never `fasta`→`fastq`); a mismatched wire is dropped, never
   coerced (`reconcileEdges`). Kinds live in `ARTIFACT_KINDS` (the union of `BTOOLSPEC` + `GIAB_LOC`).
4. **Never invent I/O.** Consult each tool's own per-tool doc (§4) — which traces every port to a
   real flag, glob, or output in `run_giab_pipeline.py` / the tool's CLI docs — to decide its ports.
   A port that has no producer/consumer or no registered kind yet is **reserved** (a labelled,
   inert slot), never fabricated as a live wire. Compose ≠ execute: the card authors flow; the
   deterministic gate still runs at `run_gate` time, off the canvas (ADR-0001, frontend README §6).

## 2. Port-placement convention

The four edges carry fixed semantics so every card reads the same way:

1. **Left → Right = primary data flow.** The main sample-data lane enters **left** and exits
   **right** (`fastq` → `bam` → `vcf` …), so the chain reads left-to-right.
2. **Top = references / panels / regions.** Static reference inputs (`reference_fasta`, `panel_bed`,
   truth VCF, region files) enter from the **top**, visually separating the fixed reference bundle
   from the flowing sample data. Applied consistently across bwa-mem2, samtools-markdup, mosdepth,
   bcftools-call, and bcftools-norm.
3. **Bottom = QC / metrics exit.** QC and metrics artifacts (`fastp_json`, `markdup_metrics`,
   the mosdepth `*_dist` family, `multiqc_html`) drop out the **bottom**, off the primary spine,
   toward MultiQC / reports. A card with no QC artifact (bwa-mem2, bcftools-call) keeps its bottom
   edge deliberately **clean** — that asymmetry is meaningful.
4. **User-defined ports are reserved, not all shown.** A tool's optional / off-in-the-demo I/O
   (adapter FASTA, CRAM reference, `--ploidy-file`, `samtools_stats`, `per_base`, the MultiQC
   discovered-log bay) gets **geometric room reserved** on the correct edge but renders only when
   populated — so enabling one later never reflows the card. Kinds not yet in `ARTIFACT_KINDS` must
   be registered (with a producer) before their reserved port can carry an edge.

## 3. Card sizing — larger than today, and why

1. **Larger footprint.** The target card is bigger than today's fixed **168 px** node
   (`BuilderShared.NODE_W` / `BuilderCanvas.UW`; the seeded ToolCard is **208 px**, `TW`) — roughly
   **~210–230 px wide** and tall enough to host up to **6 half-circle ports** (e.g. samtools-markdup:
   2 in + 4 out; mosdepth: 3 in + 6 out) plus the header text.
2. **Why larger.** Four-sided typed ports need perimeter real estate the current small card can't
   give: a top reference bay, a left data-in, a right data-out, and a bottom QC exit must each sit
   clear of the header (icon · name · version · stage label · PG badge) and of each other. Cramming
   6 ports onto a 168 px chip crowds the labels and makes the typed half-circles unhittable. The
   Databricks process-card aesthetic (generous header, ports on the edges, a readable body) *is* the
   affordance that makes typed wiring legible.
3. **Verdict spine, not verdict fill.** Tool cards keep the vstatus-colored left accent spine
   (`V_COLOR[node.vstatus]`); the decision-card spine was dropped. A tool card is `draft`-neutral
   until a run binds — it never shows a verdict or confidence (ADR-0001, frontend README §6).

## 4. Index — per-tool card specs

Germline-chain order (fastp → bwa-mem2 → samtools-markdup → {mosdepth, bcftools-call → bcftools-norm}
→ multiqc). Each doc holds that tool's full input/output port tables, concrete edges, and layout.

| Card doc | Tool / version | Stage role (one line) |
|---|---|---|
| [fastp.md](fastp.md) | `fastp` 0.23.4 | Stage 0 — adapter/quality trim + read-level QC; emits trimmed `fastq` (→ bwa-mem2) and `fastp_json` (→ MultiQC). |
| [bwa-mem2.md](bwa-mem2.md) | `bwa-mem2` 2.2.1 | Alignment — maps trimmed reads onto the reference; emits the `bam` stream (→ markdup). No QC port. |
| [samtools-markdup.md](samtools-markdup.md) | `samtools markdup` 1.20 | Duplicate marking — a bundled sort/fixmate/markdup/index stage; emits `bam` + `bai` + `markdup_metrics`. |
| [mosdepth.md](mosdepth.md) | `mosdepth` 0.3.8 | Coverage QC leaf — mean coverage + breadth ≥20×/≥30× from the dedup BAM + panel BED. |
| [bcftools-call.md](bcftools-call.md) | `bcftools call` 1.20 | Variant calling — wraps an `mpileup | call` pipe as one node; emits the raw (unnormalized) `vcf`. |
| [bcftools-norm.md](bcftools-norm.md) | `bcftools norm` 1.20 | Left-align / normalize — terminal variant-branch node; emits the gate-ready `filtered_vcf` → variant gate. |
| [multiqc.md](multiqc.md) | `MultiQC` 1.21 | QC aggregation — terminal fan-in of the QC ports; emits `multiqc_json` → ingest → the gate. |

## 5. Open / TODO — spec-vs-shipped, updated 2026-07-11

Items 1–3 below (ports, card size, half-circle visual) **shipped 2026-07-11** (commit `12a9913`,
[UIC-16](../ui-conventions.md)); item 4 (registering the remaining reserved kinds) is still open.
Verified by reading `frontend/src/components/BuilderShared.tsx` / `BuilderCanvas.tsx` directly:

1. **Ports are four-sided — CLOSED.** `BuilderShared.portSide(kind, dir)` is the single geometry
   source of truth: reference/panel **input** kinds (`reference_fasta`/`panel_bed`/`truth_vcf`/
   `adapter_fasta`) place on **top**, QC/metric **output** kinds place on **bottom**, and everything
   else follows the primary **left**(in)→**right**(out) data lane — matching this doc's §2
   convention exactly. `layoutPorts()` evenly spaces each side and returns the exact edge anchor;
   render and wire-endpoint math call the **same** function, so a wire can never detach from its
   port when a card's port count changes (the old hardcoded-SVG-path failure mode this doc used to
   warn about is gone).
2. **Cards are larger — CLOSED.** `NODE_W = 232` (was the fixed `168`/`208` this section used to
   cite), `cardHeight()` grows with the max of the left-in/right-out port count — the §3 enlarged,
   port-count-driven card is now real.
3. **Half-circle typed ports are the visual — CLOSED.** `PORT_R` (half-circle radius) + `overflow
   visible` on each card body render true half-circle nubs poking past the card edge on all four
   sides, becoming full circles in Connect mode (unchanged prior behavior); typing is still enforced
   in wiring (`reconcileEdges`, kind-matched).
4. **Reserved kinds still need registering — STILL OPEN.** Several documented ports (`fastp_html`,
   `adapter_fasta`, `samtools_stats`, the mosdepth `*_dist`/`per_base` family, `vcf_index`,
   `multiqc_html`, MultiQC's discovered-log bay) are real tool I/O that `portSide()`'s placement
   sets (`REF_IN_KINDS`/`METRIC_OUT_KINDS`) already anticipate the correct *side* for, but they are
   still **absent from any `BTOOLSPEC` tool's actual `ins`/`outs`** and so from `ARTIFACT_KINDS`
   (verified: `grep -n 'fastp_html\|samtools_stats' BuilderShared.tsx` finds them only in the
   placement sets, not in any tool's `ins`/`outs` list) — a card renders only its real, wired ports;
   these stay reserved, unrendered, never fabricated, until each gets a kind + a producer.

Only item 4 remains a **frontend follow-up** now. Each per-tool doc stays the authority on *what
ports a node should host*; this section is the (now much smaller) honest gap between spec and code.

## 6. Edge clarity + the off-canvas decision boundary (2026-07-11, commits `a03704f`→`3d531de`)

Same day, a separate pass (not §5's card-geometry work) improved how the wires between cards read
and, on a maintainer synthesis, moved the deterministic gate/ingest off the canvas entirely.
Full detail: [journal 2026-07-11](../../journal/2026-07-11-builder-boundary-and-edges.md),
[frontend/README.md §6](../frontend/README.md#6-pipeline-builder--full-model),
[ADR-0001](../../adr/ADR-0001-deterministic-gate-advisory-ai.md) Realized §3. In short:

1. **Split multi-connection ports (`a03704f`).** A port wired to N cards now splits into N laid
   sub-ports, one per edge, each independently anchored at its own target — no two edges share an
   endpoint. This is orthogonal to §2's placement convention (which side a port lives on) and §5's
   card-geometry closure (`portSide()`/`layoutPorts()`); it only changes how many laid points one
   logical port yields when it fans out, not where the port sits.
2. **Occlusion-aware reference placement (`a03704f`).** The Panel BED reference card's x-position
   moved (800→1150) after an offline occlusion scorer found it cleared 3 of 7 wires routed behind
   a non-endpoint card. Purely a layout coordinate; no card, port, or kind changed.
3. **The gate + deterministic ingest are no longer cards on this canvas at all (`3d531de`).** This
   doc's card-design convention (§§1–4) is scoped to **tool** cards — it never specified an
   on-canvas gate/ingest card design, so §§1–4 are unaffected. What changed is structural: the
   canvas now renders only composable content (tool/reference/input/output cards) plus the movable
   advisory agent; the deterministic ingest→gate→verdict handoff is a new read-only
   `DecisionBoundaryModal.tsx`, reachable from the toolbar's "⋯ More" menu. If a future card design
   pass revisits how to represent the boundary, it should start from that modal, not the removed
   `IngestBand`/`GateCard` components.
