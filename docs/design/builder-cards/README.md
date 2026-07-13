# Builder cards — card-design convention + index

| Field | Value |
|---|---|
| **Status** | draft (§§1–3 now mostly REALIZED — see §5) |
| **Date** | 2026-07-10 (MST) · updated 2026-07-11 (MST, card geometry) · updated 2026-07-11 (MST, edge clarity + off-canvas boundary) · updated 2026-07-11 (MST, W4 full QC port wiring) · updated 2026-07-11 (MST, custom-script + File-input cards, §7) · updated 2026-07-12 (MST, reserved-port honesty pass — §5.4 essentially closed) |
| **Audience** | frontend / design / bioinformatics |
| **Related** | [frontend/README.md §6](../frontend/README.md#6-pipeline-builder--full-model) (Pipeline Builder — full node model) · [design/ui-conventions.md UIC-16](../ui-conventions.md) · [data/nf-core-conventions.md](../../data/nf-core-conventions.md) (tool I/O → `ArtifactRef` / `MetricValue`) · [data/qc_metrics-sources.md](../../data/qc_metrics-sources.md) (metric provenance) · [frontend `BuilderShared.tsx`](../../../frontend/src/components/BuilderShared.tsx) (`BTOOLSPEC` · `TOOLS` · `GIAB_LOC` · `germlineTemplate()` · `portSide()` · `layoutPorts()` · `cardHeight()`) · [frontend `BuilderCanvas.tsx`](../../../frontend/src/components/BuilderCanvas.tsx) (current render + wiring) · [scripts/run_giab_pipeline.py](../../../scripts/run_giab_pipeline.py) (the real germline commands the cards abstract) · [ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md) (the operator-authored custom-script card, §7) · [design/nextflow-codegen.md](../nextflow-codegen.md) (the compile path a custom-script card feeds) |

This is the **general** card-design convention for the Pipeline Builder, plus the index of the
per-tool card specs. Each per-tool doc grounds one node's ports in that tool's **real** CLI I/O and
the exact germline command it wraps; this doc holds the shared rules those specs assume. The
convention was a **design target** — as of 2026-07-11 (commit `12a9913`) the current
[`BuilderCanvas`](../../../frontend/src/components/BuilderCanvas.tsx) implements it (larger cards,
four-sided typed half-circle ports); the last open item (§5.4, the reserved-port kinds) was
**essentially closed 2026-07-12** by the reserved-port honesty pass — every shown port is now a real
channel or removed, with one deliberate `adapter_fasta` deferral left. See §5.

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
4. **User-defined ports are reserved, not all shown** — but a reserved port must correspond to a
   REAL producible artifact or be removed, never left as a superficial slot (the 2026-07-12
   reserved-port honesty rule, §5.4). A tool's genuinely optional I/O (adapter FASTA, CRAM
   reference, `--ploidy-file`) gets **geometric room reserved** on the correct edge but renders only
   when populated — so enabling one later never reflows the card. Kinds not yet in `ARTIFACT_KINDS`
   must be registered (with a producer) before their reserved port can carry an edge; a kind with no
   real producer (e.g. `mosdepth` `per_base` under `--no-per-base`, or a computed string like
   `read_group`) is **removed**, not left reserved. As of 2026-07-12 the only reserved-and-shown
   port in the germline cards is `fastp` `adapter_fasta`.

## 3. Card sizing — larger than today, and why

1. **Larger footprint.** The target card is bigger than today's fixed **168 px** node
   (`BuilderShared.NODE_W` / `BuilderCanvas.UW`; the seeded ToolCard is **208 px**, `TW`) — roughly
   **~210–230 px wide** and tall enough to host up to **6 half-circle ports** (e.g. samtools-markdup:
   2 in + 4 out; mosdepth: 3 in + 5 out after `per_base`'s 2026-07-12 removal) plus the header text.
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
[UIC-16](../ui-conventions.md)); item 4 (the reserved-port kinds) is **essentially closed
2026-07-12** — every shown port is now a real channel or removed, with one deliberate
`adapter_fasta` deferral. Verified by reading `frontend/src/components/BuilderShared.tsx` /
`BuilderCanvas.tsx` + `src/bayleaf/nextflow/catalog.py` directly:

1. **Ports are four-sided — CLOSED.** `BuilderShared.portSide(kind, dir)` is the single geometry
   source of truth: reference/panel **input** kinds (`reference_fasta`/`panel_bed`/`truth_vcf`/
   `adapter_fasta`) place on **top**, QC/metric **output** kinds place on **bottom**, and everything
   else follows the primary **left**(in)→**right**(out) data lane — matching this doc's §2
   convention exactly. `layoutPorts()` evenly spaces each side and returns the exact edge anchor;
   render and wire-endpoint math call the **same** function, so a wire can never detach from its
   port when a card's port count changes (the old hardcoded-SVG-path failure mode this doc used to
   warn about is gone).
2. **Cards are larger — CLOSED.** `NODE_W = 320` (was the fixed `168`/`208` this section used to
   cite), `cardHeight()` grows with the max of the left-in/right-out port count — the §3 enlarged,
   port-count-driven card is now real.
3. **Half-circle typed ports are the visual — CLOSED.** `PORT_R` (half-circle radius) + `overflow
   visible` on each card body render true half-circle nubs poking past the card edge on all four
   sides, becoming full circles in Connect mode (unchanged prior behavior); typing is still enforced
   in wiring (`reconcileEdges`, kind-matched).
4. **Reserved kinds — essentially CLOSED (2026-07-12, reserved-port honesty pass, commit
   `1621e3f` + the mosdepth-byproduct fix `e40784c`).** The rule the pass enforces:
   **every shown port is a real Nextflow channel, or it is removed — no superficial slots.**
   Verified by reading `BuilderShared.tsx` (`BTOOLSPEC`/`CARD_PORTS`) + `catalog.py` +
   `tests/test_nextflow_promoted_ports.py` (5 cases), the ten kinds this item used to list are now:
   1. **Promoted to real, wireable optional ports** (each a genuine product of the tool's existing
      command): `fastp_html` + `samtools_stats` (W4); then `fastp` `unpaired_fastq`/`failed_fastq`
      (fastp writes them with `--unpaired1/2`/`--failed_out`), `bcftools norm` `vcf_index` (the
      `.csi` its `bcftools index -f` step already writes), `MultiQC` `multiqc_html` (`multiqc .`
      always writes `multiqc_report.html`), and the mosdepth `regions`/`global_dist`/`region_dist`
      byproducts (the same `mosdepth --by … --thresholds` command already emits them — the frontend
      advertised all five while the catalog declared two, and that arity gap 422'd
      Export-to-Nextflow of the default Builder view until `catalog.py` declared them). Each maps to
      a real `emit:` channel; the promoted kinds are in `ARTIFACT_KINDS` (and `fastp_html`/
      `samtools_stats` in the backend `node_author.models.ARTIFACT_KINDS`, T-130).
   2. **Removed as non-real** (a Builder port wires a file channel, so none could ever carry a real
      wire — dropped rather than left dangling): `bwa-mem2` `read_group` (a computed `@RG` STRING,
      not a file), `mosdepth` `per_base` (suppressed by the command's `--no-per-base`),
      `bcftools norm` `panel_bed` (norm is genome-wide), and `MultiQC`
      `fastqc_zip`/`bcftools_stats`/`picard_hsmetrics`/`ngscheckmate` (no catalogued germline tool
      produces them, and MultiQC's inputs are fixed by its `ProcessSpec`).
   3. **Left honestly reserved — one kind, `fastp` `adapter_fasta`.** A real optional
      `--adapter_fasta` file input, but the compiler's input-drift guard is exact + positional, so
      adding it to the catalog would force EVERY fastp node (incl. the seeded golden chain) to wire
      an adapter source — too invasive for this pass, so it stays a non-armable reserved port with a
      Connect-mode tooltip. It is the ONLY port that renders reserved anywhere now.

This section is now the honest record that the spec-vs-shipped gap has effectively closed: apart
from the single deliberate `adapter_fasta` deferral, every Builder card renders only real, wired
ports. Each per-tool doc stays the authority on *what ports a node should host*; the compiler catalog
([nextflow-codegen.md §The catalog](../nextflow-codegen.md#the-catalog-catalogpy)) is the authority
on *which of those map to a real channel*, and the two are kept from drifting by the
`test_nextflow_promoted_ports.py` + output-drift guards.

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

## 7. Retired placeholders, a generic File-input source, and the custom-script card (2026-07-11, branch `feat/custom-script-io`)

Two independent pieces, together closing the "these two named nodes were unwired placeholders"
gap this doc's §4 index never actually listed them under (`Truth VCF` / `NGSCheckMate` were
**References**/**Contamination** palette tiles, not per-tool cards with their own spec doc — this
section is the closest thing to their retirement record).

1. **Branch A — retire `Truth VCF` + `NGSCheckMate`, add a generic `File input` card.** Both were
   dangling, unwired palette nodes: `Truth VCF` (`r_truth`, a reference source with an `optional`
   locator no tool in the seeded chain consumed) and `NGSCheckMate` (a palette-composable identity
   card with no seeded edge into the germline chain). Both are removed from `BuilderShared.tsx`'s
   `REFS`/`BTOOLSPEC`/`CARD_PORTS`/`GIAB_LOC` and `PipelineBuilder.tsx`'s palette (the "Contamination"
   section is gone with it). In their place, a generic typed **`File input`** card
   (`BTOOLSPEC['File input']`, `makeUserNode` honors the operator-picked output kind) can emit ANY
   single artifact kind the operator selects via the inspector's port-kind picker — a re-analysis
   VCF, a truth VCF to benchmark against, or any other one-shot typed source. **The `truth_vcf` and
   `ngscheckmate` KINDS are NOT retired** — both remain in `ARTIFACT_KINDS` via a new
   `EXTRA_VOCAB_KINDS` constant (mirrored on the backend, `node_author.models.ARTIFACT_KINDS`), so a
   File-input card (or a custom-script card, item 2 below) can still emit/consume either kind; only
   the two bespoke, unwired palette nodes are gone. `catalog.py`'s `REFERENCE_PARAM` drops
   `truth_vcf` (the germline chain never consumed it as a compiler-level reference param — it was
   never wired to the real pipeline in the first place). The node-author corpus
   (`knowledge/tool_cards.jsonl`) drops the `source_truth_vcf` card (11→10); NGSCheckMate was then
   **retired-but-pinned** from the proposable corpus (10→**9**, its JSON line commented out so
   `load_tool_card_corpus()` skips it while the `ngscheckmate` KIND stays in the vocabulary) —
   **the corpus is 9 cards now** (7 germline tools + Reference FASTA + Panel BED). Per-tool docs that referenced either removed
   node as a wiring target ([samtools-markdup.md](samtools-markdup.md),
   [bcftools-norm.md](bcftools-norm.md), [multiqc.md](multiqc.md), [bwa-mem2.md](bwa-mem2.md)) are
   corrected in the same sweep — they now describe NGSCheckMate as a real bioinformatics concept a
   File-input/custom-script card COULD stand in for, not a still-composable palette node.
2. **Branch B — the operator-authored custom-script card** ([ADR-0020](../../adr/ADR-0020-operator-authored-custom-processes.md),
   [design/nextflow-codegen.md §Operator-authored custom-script processes](../nextflow-codegen.md#operator-authored-custom-script-processes-adr-0020-compilerpy--apiroutersnextflowpy)).
   A new **"Custom script"** palette card (amber/`warn`-toned — a deliberately distinct visual
   register from a catalogued tool or a source, since it runs an OPERATOR's command on the compute
   host) opens its own dedicated inspector (`CustomScriptInspector`, replacing the generic
   `BuilderInspector` when selected) instead of following this doc's §§1-3 catalogued-tool card
   convention: a label, typed input/output ports (add/remove from the same closed `ARTIFACT_KINDS`
   vocabulary every other card uses — never free-invented), a `script:` textarea (the verbatim
   Nextflow body), a runtime toggle (container OR conda — only the active one is sent to the
   compiler), and locator authoring for its output kinds with a new server-side **Browse** picker
   (`FileBrowser.tsx` → `GET /api/files`, allowlisted + traversal-hardened, metadata only — see
   [nonfunctional.md REQ-NF-027](../../requirements/nonfunctional.md)). It is honestly NOT a
   curated tool card: the compiler renders the operator's body verbatim and never consults the
   catalog for it, even if the card's name collides with a catalogued tool. `NextflowExportModal`
   gains a per-file bundle picker (`main.nf`/`modules/*.nf`/config) so an operator can verify their
   script round-tripped. This card is orthogonal to the retired `Truth VCF`/`NGSCheckMate` nodes
   above but was designed as their natural successor: a lab that wants "the NGSCheckMate identity
   check back" now authors it as a custom-script card (a real `ngscheckmate` command, wired from a
   `bam` input to an `ngscheckmate`-kind output) rather than bayleaf shipping a second bespoke,
   possibly-unwired palette tile for it.
