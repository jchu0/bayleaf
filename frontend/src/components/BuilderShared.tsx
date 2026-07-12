// Shared data contract + helpers for the Pipeline Builder (screen §5.9 / §6 / §7).
// Kept framework-thin: pure types + seed data + YAML/diff/dry-run projections that the
// screen and the Builder* panels both import. The graph is authoring state only — the
// verdict is computed at run time by run_gate, never stored here (README §7). The sole
// grounded output is run_layout.yaml.

import {
  Activity,
  Archive,
  BarChart3,
  Copy,
  Database,
  Dna,
  Filter,
  GitMerge,
  Layers,
  Scissors,
  ShieldCheck,
  Terminal,
  Wrench,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { FileKind } from '../types'

export const GRAPH_ID = 'PIPE-2026-07-08-GERMLINE-PANEL'
export const LINKED_RUN = 'RUN-2026-07-07-A'

export type Mode = 'edit' | 'view'
export type Tab = 'params' | 'locators' | 'io' | 'agents'
export type ConsoleTab = 'validate' | 'diff' | 'dryrun'
// Local pill status. Maps to the wire PipelineStatus (draft | pending_review | approved);
// 'pending' shows as "pending approval". Kept local so the demo works offline.
export type SaveStatus = 'draft' | 'pending' | 'approved'
export type OnMultiple = 'first' | 'all' | 'error'

// One icon vocabulary shared by seeded tool cards, palette tiles, and user-composed nodes.
export type IconKey =
  | 'scissors' | 'merge' | 'copy' | 'bars' | 'dna' | 'funnel' | 'layers'
  | 'activity' | 'wrench' | 'archive' | 'shield' | 'db' | 'terminal'
export const ICONS: Record<IconKey, LucideIcon> = {
  scissors: Scissors, merge: GitMerge, copy: Copy, bars: BarChart3, dna: Dna,
  funnel: Filter, layers: Layers, activity: Activity, wrench: Wrench,
  archive: Archive, shield: ShieldCheck, db: Database, terminal: Terminal,
}

export type Port = { kind: string; ref?: boolean }
export type PgStatus = 'ours' | 'full' | 'partial'
export type VStatus = 'ok' | 'warn' | 'blocked'
export type Io = { name: string; sha: string; size: string; origin: string }
export type Tool = {
  id: string
  tool: string
  version: string
  stageLabel: string
  pg: PgStatus
  icon: IconKey
  x: number
  y: number
  vstatus: VStatus
  inputs: Port[]
  outputs: Port[]
  params: { k: string; v: string; help: string }[]
  io: Io[]
}

// Free-composition node the operator drops onto the canvas (Edit). Visually identical to the
// seeded DAG cards; carries typed I/O ports so Connect-mode wiring can enforce kind-matching.
// `vstatus` (optional) carries a bound run's per-STEP QC status — set on the linked germline nodes
// so their left spine reads passed/attention/blocked exactly as the seeded ToolCard did; a
// hand-composed node has none (→ neutral 'not run'). It is display-only: the verdict is computed at
// run time, never stored on the graph (README §7); it just retints the spine.
export type UserNode = {
  id: string
  name: string
  kind: string
  version: string
  icon: IconKey
  ins: string[]
  outs: string[]
  x: number
  y: number
  vstatus?: VStatus
  // ── Operator-authored custom-script process (ADR-0020) ──────────────────────
  // `custom` marks a custom-script card — a distinct thing from a catalogued tool or a source: a
  // HUMAN authored a verbatim Nextflow `script:` body, and the compiler renders THAT body (never
  // the tool catalog), wired from this node's own typed ports. `runtime` picks which packaging is
  // sent to the compiler (a container image OR a conda spec — both kept so a toggle doesn't lose
  // text). `outGlobs` is the operator's per-output emit glob, PARALLEL to `outs` (an authoring aid:
  // the emitted process captures the whole work dir via `path("*")`, ADR-0020 follow-up — the glob
  // is not yet consumed by the command). All optional/absent on an ordinary card, so the change is
  // purely additive — the seeded chain carries none and its compiled output is byte-identical.
  custom?: boolean
  script?: string
  runtime?: 'container' | 'conda'
  container?: string
  conda?: string
  outGlobs?: string[]
}
export type UserEdge = { from: { node: string; idx: number }; to: { node: string; idx: number } }

export const PG_BADGE: Record<PgStatus, { label: string; fg: string; bg: string }> = {
  ours: { label: 'ours', fg: '#1f5fd0', bg: '#eaf0fc' },
  full: { label: 'consumes', fg: '#0e8f7e', bg: '#e2f4f0' },
  partial: { label: 'substitute', fg: '#c1560f', bg: '#fceee2' },
}
export const V_COLOR: Record<VStatus, string> = { ok: '#1a854e', warn: '#b07714', blocked: '#cf3238' }

// Seeded germline chain in a SPINE + BRANCH layout: the primary spine fastp → bwa-mem2 → samtools
// markdup → bcftools call → bcftools norm sits on one row (y = SPINE_Y 260); mosdepth (off markdup)
// and MultiQC (the QC fan-in) drop to a BRANCH row below (y = BRANCH_Y 600). Reference/FASTQ sources
// live in a top band (y = REF_Y 40) above their consumers. Kinds on the ports drive the palette
// subs + kind-matching. x pitch = NODE_W (320) + ~60px gap = 380.
export const TOOLS: Tool[] = [
  {
    id: 'n_fastp', tool: 'fastp', version: '0.23.4', stageLabel: 'Read QC + trim', pg: 'ours', icon: 'scissors',
    x: 40, y: 260, vstatus: 'ok', inputs: [{ kind: 'fastq' }], outputs: [{ kind: 'fastp_json' }, { kind: 'fastq' }, { kind: 'fastp_html' }],
    params: [
      { k: 'qualified_quality_phred', v: '15', help: 'Per-base quality floor' },
      { k: 'length_required', v: '50', help: 'Min read length after trim' },
      { k: 'detect_adapter_for_pe', v: 'true', help: 'Auto-detect adapters (PE)' },
    ],
    io: [
      { name: 'HG002.fastp.json', sha: 'sha256:5f2a…c81', size: '18 KB', origin: 'real-giab' },
      { name: 'HG002.R1.trim.fastq.gz', sha: 'sha256:9b04…7de', size: '1.9 GB', origin: 'real-giab' },
    ],
  },
  {
    id: 'n_bwa', tool: 'bwa-mem2', version: '2.2.1', stageLabel: 'Alignment', pg: 'partial', icon: 'merge',
    x: 420, y: 260, vstatus: 'ok', inputs: [{ kind: 'fastq' }, { kind: 'reference_fasta', ref: true }], outputs: [{ kind: 'bam' }],
    params: [
      { k: 'read_group', v: '@RG\\tID:HG002\\tSM:HG002', help: 'Read-group header' },
      { k: 'sort', v: 'coordinate', help: 'Output sort order' },
    ],
    io: [
      { name: 'HG002.bam', sha: 'sha256:44c9…d10', size: '31 GB', origin: 'real-giab' },
      { name: 'HG002.bam.bai', sha: 'sha256:1e77…4a2', size: '8 MB', origin: 'real-giab' },
    ],
  },
  {
    id: 'n_markdup', tool: 'samtools markdup', version: '1.20', stageLabel: 'Duplicate marking', pg: 'full', icon: 'copy',
    x: 800, y: 260, vstatus: 'ok', inputs: [{ kind: 'bam' }], outputs: [{ kind: 'bam' }, { kind: 'bai' }, { kind: 'markdup_metrics' }, { kind: 'samtools_stats' }],
    params: [{ k: 'remove_duplicates', v: 'false', help: 'Mark, do not drop' }],
    io: [
      { name: 'HG002.md.bam', sha: 'sha256:7a11…4c2', size: '32 GB', origin: 'real-giab' },
      { name: 'HG002.markdup.txt', sha: 'sha256:c93e…08a', size: '2 KB', origin: 'real-giab' },
    ],
  },
  {
    id: 'n_mosdepth', tool: 'mosdepth', version: '0.3.8', stageLabel: 'Coverage', pg: 'ours', icon: 'bars',
    x: 800, y: 600, vstatus: 'warn', inputs: [{ kind: 'bam' }, { kind: 'panel_bed', ref: true }],
    // The 3 optional *_dist/regions coverage byproducts (mosdepth --by emits these) — the ONLY new
    // WIREABLE graph ports this change adds (builder-cards/mosdepth.md §2/§3). They are compose
    // affordances (bottom QC exits), NOT emitted run_layout locators: GIAB_LOC is untouched.
    outputs: [{ kind: 'mosdepth_summary' }, { kind: 'mosdepth_thresholds' }, { kind: 'mosdepth_regions' }, { kind: 'mosdepth_global_dist' }, { kind: 'mosdepth_region_dist' }],
    params: [
      { k: 'by', v: 'panel.bed', help: 'Regions to summarise' },
      { k: 'thresholds', v: '1,10,20,30', help: 'Breadth thresholds (x)' },
      { k: 'mapq', v: '20', help: 'Min mapping quality' },
      { k: 'no_per_base', v: 'true', help: 'Summary only' },
    ],
    io: [{ name: 'HG002.panel.mosdepth.summary.txt', sha: 'sha256:aa71…c09', size: '4 KB', origin: 'real-giab' }],
  },
  {
    id: 'n_call', tool: 'bcftools call', version: '1.20', stageLabel: 'Variant calling', pg: 'partial', icon: 'dna',
    x: 1180, y: 260, vstatus: 'ok', inputs: [{ kind: 'bam' }, { kind: 'reference_fasta', ref: true }, { kind: 'panel_bed', ref: true }], outputs: [{ kind: 'vcf' }],
    params: [
      { k: 'min_MQ', v: '20', help: 'mpileup min mapping quality' },
      { k: 'min_BQ', v: '20', help: 'mpileup min base quality' },
      { k: 'variants_only', v: 'true', help: 'Emit variant sites only' },
    ],
    io: [{ name: 'HG002.bcftools.vcf.gz', sha: 'sha256:be77…512', size: '128 MB', origin: 'real-giab' }],
  },
  {
    id: 'n_norm', tool: 'bcftools norm', version: '1.20', stageLabel: 'Filter / normalize', pg: 'partial', icon: 'funnel',
    x: 1560, y: 260, vstatus: 'ok', inputs: [{ kind: 'vcf' }, { kind: 'reference_fasta', ref: true }], outputs: [{ kind: 'filtered_vcf' }],
    params: [
      { k: 'norm', v: '-m -both', help: 'Split multiallelics' },
      { k: 'fasta_ref', v: 'GRCh38.fa', help: 'Left-align against the reference' },
    ],
    io: [{ name: 'HG002.norm.filtered.vcf.gz', sha: 'sha256:12ab…9f0', size: '44 MB', origin: 'real-giab' }],
  },
  {
    id: 'n_multiqc', tool: 'MultiQC', version: '1.21', stageLabel: 'QC aggregation', pg: 'full', icon: 'layers',
    x: 1180, y: 600, vstatus: 'ok', inputs: [{ kind: 'fastp_json' }, { kind: 'markdup_metrics' }, { kind: 'samtools_stats' }, { kind: 'mosdepth_summary' }, { kind: 'mosdepth_thresholds' }], outputs: [{ kind: 'multiqc_json' }],
    params: [{ k: 'force', v: 'true', help: 'Overwrite existing report' }],
    io: [{ name: 'multiqc_data.json', sha: 'sha256:5be3…9c4', size: '2.1 MB', origin: 'real-giab' }],
  },
]

// (Seeded canvas edges are now COMPUTED from the tool/ref card geometry in BuilderCanvas —
// SEEDED_WIRES/REF_WIRES — so they stay attached to the ports; the old hardcoded path table was
// removed with the "broken lines" fix.)

export type Ref = { id: string; label: string; kind: string; file: string; x: number }
// Reference source cards sit in a top band ABOVE the spine (REF_Y=40). x is EDGE-OCCLUSION-biased (PASS-2
// B): fasta→bwa (x420); Panel BED at x1150 — NOT over its primary consumer's column (x800), because an
// occlusion-scoring relaxation (minimise edges routed BEHIND a non-endpoint card) found that stacking it
// over markdup put its panel_bed→mosdepth wire behind markdup AND put it on the fasta→call/norm lanes;
// moving it right (above the markdup·call gap / call) clears 3 of the layout's occlusions at once. Pitch
// matches the tool spine (NODE_W 320 + ~60 gap). (The old unwired Truth VCF benchmark source was retired;
// a truth/benchmark VCF is now a generic typed 'File input' — see BTOOLSPEC below.)
export const REFS: Ref[] = [
  { id: 'r_fasta', label: 'Reference genome', kind: 'reference_fasta', file: 'reference/GRCh38.fa', x: 420 },
  { id: 'r_bed', label: 'Panel BED', kind: 'panel_bed', file: 'reference/panel.bed', x: 1150 },
]

export const GATE_CHECKPOINTS = [
  { label: 'preflight', c: '#1f6feb' },
  { label: 'qc', c: '#1f5fd0' },
  { label: 'variant', c: '#0e8f7e' },
]

// Seeded verdict spread of the linked run (RUN-2026-07-07-A): 3 proceed · 1 hold · 1 escalate.
export const GATE_COUNTS: Record<'proceed' | 'hold' | 'rerun' | 'escalate', number> = {
  proceed: 3, hold: 1, rerun: 0, escalate: 1,
}
export const VERDICT_HEX: Record<'proceed' | 'hold' | 'rerun' | 'escalate', string> = {
  proceed: '#1a854e', hold: '#b07714', rerun: '#c1560f', escalate: '#cf3238',
}
export function gateSegs(): { c: string; w: string }[] {
  const total = Object.values(GATE_COUNTS).reduce((a, b) => a + b, 0) || 1
  return (['proceed', 'hold', 'rerun', 'escalate'] as const)
    .filter((v) => GATE_COUNTS[v] > 0)
    .map((v) => ({ c: VERDICT_HEX[v], w: `${(GATE_COUNTS[v] / total) * 100}%` }))
}

// Palette → node spec. bwa-mem2 icon key is 'merge'; funnel = bcftools norm. Unknown tools
// fall back to a merge icon + a single artifact kind (still typed, never invented).
export const BTOOLSPEC: Record<string, { version: string; icon: IconKey; ins: string[]; outs: string[] }> = {
  // fastp now also emits fastp_html (the report it already writes); markdup emits samtools_stats
  // (a real `samtools stats` stream) — both were dangling reserved ports, now wired in the
  // compiler catalog (W3 full-port-wiring). MultiQC ingests every QC stream (was only 3).
  'fastp': { version: '0.23.4', icon: 'scissors', ins: ['fastq'], outs: ['fastp_json', 'fastq', 'fastp_html'] },
  'bwa-mem2': { version: '2.2.1', icon: 'merge', ins: ['fastq', 'reference_fasta'], outs: ['bam'] },
  'samtools markdup': { version: '1.20', icon: 'copy', ins: ['bam'], outs: ['bam', 'bai', 'markdup_metrics', 'samtools_stats'] },
  'mosdepth': { version: '0.3.8', icon: 'bars', ins: ['bam', 'panel_bed'], outs: ['mosdepth_summary', 'mosdepth_thresholds', 'mosdepth_regions', 'mosdepth_global_dist', 'mosdepth_region_dist'] },
  'bcftools call': { version: '1.20', icon: 'dna', ins: ['bam', 'reference_fasta', 'panel_bed'], outs: ['vcf'] },
  'bcftools norm': { version: '1.20', icon: 'funnel', ins: ['vcf', 'reference_fasta'], outs: ['filtered_vcf'] },
  'MultiQC': { version: '1.21', icon: 'layers', ins: ['fastp_json', 'markdup_metrics', 'samtools_stats', 'mosdepth_summary', 'mosdepth_thresholds'], outs: ['multiqc_json'] },
  // Reference SOURCES — no inputs; each emits ONE output port PER consumer (same kind, distinct idx)
  // so every consumer edge is a clean one-to-one wire instead of many edges branching off one port
  // (the "tangled mess"): fasta → bwa/call/norm (3 outs), panel BED → mosdepth/call (2 outs). Typed
  // wiring keeps a fasta from landing on a fastq port.
  'Reference FASTA': { version: 'GRCh38', icon: 'db', ins: [], outs: ['reference_fasta', 'reference_fasta', 'reference_fasta'] },
  'Panel BED': { version: 'panel', icon: 'db', ins: [], outs: ['panel_bed', 'panel_bed'] },
  // Primary-lane INPUT source (raw FASTQ folder) + a GENERIC typed 'File input' (emits ONE artifact
  // kind the operator picks — makeUserNode honours the chosen kind, e.g. a vcf / truth_vcf / bam to
  // re-analyse; the inspector's per-port kind picker retypes it) + a file-OUTPUT sink, so the graph
  // closes on both ends: source → tools → sink (ADR-0019 slice 1c). All three compose ≠ execute — a
  // source emits an artifact, it never runs a tool. 'File input' defaults to fastq (overridden per node).
  'FASTQ input': { version: 'folder', icon: 'db', ins: [], outs: ['fastq'] },
  'File input': { version: 'file', icon: 'db', ins: [], outs: ['fastq'] },
  'File output': { version: 'file', icon: 'archive', ins: ['multiqc_json'], outs: [] },
}

export function makeUserNode(name: string, kind: string, index: number): UserNode {
  const spec = BTOOLSPEC[name] ?? { version: 'v1.0', icon: 'merge' as IconKey, ins: [kind], outs: [kind] }
  // 'File input' is the GENERIC typed source: it emits whichever ONE artifact kind the operator picks
  // (fastq / vcf / bam / reference_fasta / truth_vcf / …), so a re-analysis input (e.g. a VCF or truth
  // VCF to re-gate) is a plain typed source card rather than a bespoke palette node. Every other
  // catalogued node keeps its fixed BTOOLSPEC ports. compose ≠ execute: a source emits, never runs.
  const outs = name === 'File input' ? [kind] : spec.outs
  const x = 150 + (index % 3) * 200
  const y = 80 + Math.floor(index / 3) * 160
  return { id: `u${Date.now().toString(36)}${index}`, name, kind, version: spec.version, icon: spec.icon, ins: spec.ins, outs, x, y }
}

// ── Operator-authored custom-script process card (ADR-0020) ──────────────────────────────────────
// A HUMAN authors a verbatim Nextflow `script:` body on this card; the compiler renders it as a REAL
// process (never the tool catalog), wired from the card's own typed ports. It is NOT a curated tool —
// it runs whatever the operator wrote on the compute host — so it carries an honest label and reaches
// a compute host ONLY behind the W1 approval gate (compose ≠ execute; the core never runs a tool).
export const CUSTOM_NODE_NAME = 'Custom script'
export const CUSTOM_NODE_VERSION = 'operator-authored'
// The honest sentence surfaced on/near the card (ADR-0020 safety [ii]) — kept here so the UI and the
// emitted process header say the same thing, never a softer paraphrase.
export const CUSTOM_SAFETY_LABEL =
  'operator-authored — runs on the compute host; production needs sandboxing'
export const DEFAULT_CUSTOM_CONTAINER = 'quay.io/biocontainers/bcftools:1.20--h8b25389_0'
export const DEFAULT_CUSTOM_CONDA = 'bioconda::bcftools=1.20'
// A believable starter body — a step OFF the curated catalog (the exact case ADR-0020 motivates).
// It references only `${vcf}` (the wired input port — the compiler names each input path variable
// after its port KIND) and `${meta.id}` (the per-sample meta, always present), so the emitted process
// is self-consistent. The operator edits it; PipeGuard transcribes it verbatim, never rewriting it.
export const DEFAULT_CUSTOM_SCRIPT = `# operator-authored — transcribed verbatim into the emitted process (compose ≠ execute)
# example: split multiallelic sites on a called VCF, then index the result
bcftools norm -m -both -Oz -o \${meta.id}.norm.vcf.gz \${vcf}
tabix -p vcf \${meta.id}.norm.vcf.gz`

export function isCustomNode(n: UserNode): boolean {
  return n.custom === true
}

// A fresh custom-script card: a typed vcf→filtered_vcf process seeded with the starter body + a
// container runtime. `filtered_vcf` output is chosen deliberately — it has a GIAB_LOC locator, so the
// inspector's locator authoring (and its Browse picker) has something to point at out of the box.
export function makeCustomNode(index: number): UserNode {
  const x = 150 + (index % 3) * 220
  const y = 90 + Math.floor(index / 3) * 200
  return {
    id: `u${Date.now().toString(36)}${index}c`,
    name: CUSTOM_NODE_NAME,
    kind: 'filtered_vcf',
    version: CUSTOM_NODE_VERSION,
    icon: 'terminal',
    ins: ['vcf'],
    outs: ['filtered_vcf'],
    outGlobs: ['*.norm.vcf.gz'],
    x,
    y,
    custom: true,
    runtime: 'container',
    container: DEFAULT_CUSTOM_CONTAINER,
    conda: DEFAULT_CUSTOM_CONDA,
    script: DEFAULT_CUSTOM_SCRIPT,
  }
}

// Keep `outGlobs` aligned to `outs` (same length) after a port add/remove — an undefined array
// initializes to one '*' per existing output, so the parallel-array invariant never drifts.
export function alignOutGlobs(outGlobs: string[] | undefined, outs: string[]): string[] {
  const g = outGlobs ?? []
  return outs.map((_, i) => g[i] ?? '*')
}

// The node shape POST /api/pipelines/compile (and .../run) accepts. Structurally identical to
// NextflowGraphBody['nodes'][number] in types.ts (kept in sync by hand).
export type CompileNodePayload = {
  id: string
  name: string
  ins: string[]
  outs: string[]
  script?: string
  container?: string
  conda?: string
}

// Project a builder node into the compile/run node shape. A custom-script card threads its
// operator-authored `script` + the ACTIVE runtime's packaging (container OR conda) so the backend
// renders the operator's real Nextflow process (ADR-0020). An ordinary catalogued/source card omits
// all three, leaving the pre-existing wire shape byte-identical. A blank custom script is sent AS-IS
// (`''`): the compiler REJECTS it (422) rather than fabricating a command — an honest error, never an
// invented one (ADR-0020 safety [v]).
export function toCompileNode(n: UserNode): CompileNodePayload {
  const base: CompileNodePayload = { id: n.id, name: n.name, ins: n.ins, outs: n.outs }
  if (!isCustomNode(n)) return base
  const container = n.runtime !== 'conda' ? n.container?.trim() : undefined
  const conda = n.runtime === 'conda' ? n.conda?.trim() : undefined
  return {
    ...base,
    script: n.script ?? '',
    ...(container ? { container } : {}),
    ...(conda ? { conda } : {}),
  }
}

// Normalize a node for the SAVE payload so the STORED graph (which the approved-run path re-compiles
// server-side, ADR-0020 safety [i]) matches what the export/compile preview shows: a custom node keeps
// only its ACTIVE runtime's packaging, so preview == run (WYSIWYG — the backend run path reads a stored
// node's container/conda directly). UI-only fields (runtime/outGlobs/script/custom) are preserved so a
// reload restores the authoring surface. A non-custom node is returned untouched.
export function normalizeSavedNode(n: UserNode): UserNode {
  if (!isCustomNode(n)) return n
  return {
    ...n,
    container: n.runtime !== 'conda' ? n.container : undefined,
    conda: n.runtime === 'conda' ? n.conda : undefined,
  }
}

// Map an artifact/locator KIND (the builder vocabulary) → the FileKind(s) the server-side file browser
// infers from a file extension (files.py), so a kind-scoped Browse picker (e.g. a filtered_vcf locator)
// only lets a MATCHING file be selected. A kind with no clean extension mapping returns undefined → no
// filter (every file selectable). Lives here (a component-free module) so the FileBrowser stays a
// single-component file (react-refresh only-export-components).
const KIND_TO_FILEKINDS: Record<string, FileKind[]> = {
  fastq: ['fastq'],
  bam: ['bam'],
  vcf: ['vcf'],
  filtered_vcf: ['vcf'],
  joint_vcf: ['vcf'],
  gvcf: ['vcf'],
  truth_vcf: ['vcf'],
  reference_fasta: ['reference_fasta'],
  panel_bed: ['panel_bed'],
}
export function fileKindsFor(artifactKind: string): FileKind[] | undefined {
  return KIND_TO_FILEKINDS[artifactKind]
}

// ── On-canvas editing helpers (PB2) ────────────────────────────────────────
// Pure array rewrites + geometry, framework-thin so the screen owns the history/state and these
// stay unit-testable. Every mutation is over the local draft (compose ≠ execute).

// ── Card geometry (builder-cards §3) ─────────────────────────────────────────
// Larger Databricks-style process cards with typed half-circle ports on all FOUR sides. These
// constants + functions are the SINGLE source of truth for BOTH the render (BuilderCanvas cards)
// AND the wire/anchor math — a wire endpoint is computed from the exact same layoutCardPorts() that
// positions the port, so an edge can never detach from its port when a card's size/port-count
// changes. MUST stay in lockstep with BuilderCanvas.UW/TW (out-port anchors sit at n.x + width).
export const NODE_W = 320 // card width (232 → 296 → 320; bigger cards seat the inside-aligned port index numbers cleanly, §3)
export const CARD_HEADER_H = 48 // header band (icon · name · version · stage · PG pill)
export const CARD_FOOTER_H = 22 // draft / verdict status strip
export const PORT_R = 7 // half-circle port radius (its flat side sits on the card edge = the anchor point)
const PORT_PITCH = 26 // vertical pitch between stacked left/right ports
const PORTS_ZONE_MIN = 34 // min height of the left/right ports band (a 1-port card isn't cramped)
const LIST_ROW = 15 // one on-card panel row (index · kind · side · tag)

export type PortSide = 'left' | 'right' | 'top' | 'bottom'

// Reference/panel INPUT kinds enter from the TOP; QC/metric OUTPUT kinds exit the BOTTOM; everything
// else follows the primary left(in)→right(out) data lane (builder-cards §2 + each per-tool card doc).
// A kind's side depends on its DIRECTION: fastp_json is a BOTTOM output on fastp but a LEFT input on
// MultiQC; mosdepth_summary stays on the RIGHT (a consumed/gated output, not a bottom QC byproduct).
// portSide() is the FALLBACK for a hand-composed node with no catalog entry; a catalogued node's
// side/state come from CARD_PORTS (below), which is explicit where portSide can't derive (MultiQC's
// top discovered-log bay, failed_fastq's bottom exit).
const REF_IN_KINDS = new Set(['reference_fasta', 'panel_bed', 'truth_vcf', 'adapter_fasta'])
const METRIC_OUT_KINDS = new Set([
  'fastp_json', 'fastp_html', 'markdup_metrics', 'samtools_stats', 'multiqc_html',
  'mosdepth_regions', 'mosdepth_global_dist', 'mosdepth_region_dist', 'per_base', 'vcf_index',
])
export function portSide(kind: string, dir: 'in' | 'out'): PortSide {
  if (dir === 'in') return REF_IN_KINDS.has(kind) ? 'top' : 'left'
  return METRIC_OUT_KINDS.has(kind) ? 'bottom' : 'right'
}
// Reference-tone INPUT ports (top) render outlined rather than filled.
export function isRefKind(kind: string): boolean {
  return REF_IN_KINDS.has(kind)
}

// Port data-kind → colour family (the verdict-SAFE --k-* palette defined in index.css, theme-aware
// light/dark). Deliberately NOT the proceed/hold/rerun/escalate hues, so a data-kind port never
// reads as a decision (design invariant: the verdict palette is reserved for the gate).
const KIND_VAR: Record<string, string> = {
  fastq: '--k-reads', unpaired_fastq: '--k-reads', failed_fastq: '--k-reads',
  bam: '--k-align', bai: '--k-align',
  vcf: '--k-var', filtered_vcf: '--k-var', vcf_index: '--k-var',
  fastp_json: '--k-qc', fastp_html: '--k-qc', markdup_metrics: '--k-qc', samtools_stats: '--k-qc',
  mosdepth_summary: '--k-qc', mosdepth_thresholds: '--k-qc', mosdepth_regions: '--k-qc',
  mosdepth_global_dist: '--k-qc', mosdepth_region_dist: '--k-qc', per_base: '--k-qc',
  multiqc_json: '--k-qc', multiqc_html: '--k-qc', fastqc_zip: '--k-qc', bcftools_stats: '--k-qc',
  picard_hsmetrics: '--k-qc', ngscheckmate: '--k-qc',
  reference_fasta: '--k-ref', panel_bed: '--k-ref', truth_vcf: '--k-ref', adapter_fasta: '--k-ref',
  read_group: '--k-cfg',
}
export function kindColor(kind: string): string {
  return `var(${KIND_VAR[kind] ?? '--color-text-3'})`
}

// ── Port state + card-port catalog (builder-cards §2/§3) ─────────────────────
// A port is required (solid), optional (half-fill, still wireable), or reserved (a documented-but-
// inert slot: rendered, NEVER wired). State is DISPLAY-ONLY — no wiring logic reads it; the graph
// invariants (kind-match + dedup) are unchanged. CARD_PORTS is the DOCUMENTED full port set per tool
// (lifted from the design mockup + builder-cards/*.md): side/state stored explicitly, since a few
// specs assign a side the "ref→top / metric→bottom" heuristic can't derive.
export type PortState = 'required' | 'optional' | 'reserved'
export type CardPort = { kind: string; dir: 'in' | 'out'; side: PortSide; state: PortState }

// The authority for RENDER + STATE, keyed EXACTLY to Tool.tool / UserNode.name / BTOOLSPEC keys.
// A catalogued RESERVED port renders but is never in ins/outs/BTOOLSPEC/ARTIFACT_KINDS (non-wireable).
// A catalogued REQUIRED input that a tool's real ins doesn't carry (e.g. mosdepth/bcftools-call `bai`)
// is documentation-only: cardPortList resolves render from the WIREABLE ins/outs + the reserved
// catalog, so such an entry is simply not shown (only the 3 mosdepth *_dist outs were added as real
// wireable graph ports; no new inputs). Sides/state are verbatim from the mockup CARDS array.
export const CARD_PORTS: Record<string, CardPort[]> = {
  fastp: [
    { kind: 'fastq', dir: 'in', side: 'left', state: 'required' },
    { kind: 'adapter_fasta', dir: 'in', side: 'top', state: 'reserved' },
    { kind: 'fastq', dir: 'out', side: 'right', state: 'required' },
    { kind: 'unpaired_fastq', dir: 'out', side: 'right', state: 'reserved' },
    { kind: 'fastp_json', dir: 'out', side: 'bottom', state: 'required' },
    { kind: 'fastp_html', dir: 'out', side: 'bottom', state: 'optional' }, // now a real published output (compiler catalog)
    { kind: 'failed_fastq', dir: 'out', side: 'bottom', state: 'reserved' },
  ],
  'bwa-mem2': [
    { kind: 'fastq', dir: 'in', side: 'left', state: 'required' },
    { kind: 'reference_fasta', dir: 'in', side: 'top', state: 'required' },
    { kind: 'read_group', dir: 'in', side: 'left', state: 'reserved' },
    { kind: 'bam', dir: 'out', side: 'right', state: 'required' },
  ],
  'samtools markdup': [
    { kind: 'bam', dir: 'in', side: 'left', state: 'required' },
    { kind: 'reference_fasta', dir: 'in', side: 'top', state: 'reserved' },
    { kind: 'bam', dir: 'out', side: 'right', state: 'required' },
    { kind: 'bai', dir: 'out', side: 'right', state: 'required' },
    { kind: 'markdup_metrics', dir: 'out', side: 'bottom', state: 'optional' },
    { kind: 'samtools_stats', dir: 'out', side: 'bottom', state: 'optional' }, // now a real `samtools stats` output → MultiQC
  ],
  mosdepth: [
    { kind: 'bam', dir: 'in', side: 'left', state: 'required' },
    { kind: 'bai', dir: 'in', side: 'left', state: 'required' }, // doc-only: not in real ins → not rendered
    { kind: 'panel_bed', dir: 'in', side: 'top', state: 'required' },
    { kind: 'mosdepth_summary', dir: 'out', side: 'right', state: 'required' },
    { kind: 'mosdepth_thresholds', dir: 'out', side: 'right', state: 'required' },
    { kind: 'mosdepth_regions', dir: 'out', side: 'bottom', state: 'optional' },
    { kind: 'mosdepth_global_dist', dir: 'out', side: 'bottom', state: 'optional' },
    { kind: 'mosdepth_region_dist', dir: 'out', side: 'bottom', state: 'optional' },
    { kind: 'per_base', dir: 'out', side: 'bottom', state: 'reserved' },
  ],
  'bcftools call': [
    { kind: 'bam', dir: 'in', side: 'left', state: 'required' },
    { kind: 'bai', dir: 'in', side: 'left', state: 'required' }, // doc-only: not in real ins → not rendered
    { kind: 'reference_fasta', dir: 'in', side: 'top', state: 'required' },
    { kind: 'panel_bed', dir: 'in', side: 'top', state: 'optional' },
    { kind: 'vcf', dir: 'out', side: 'right', state: 'required' },
  ],
  'bcftools norm': [
    { kind: 'vcf', dir: 'in', side: 'left', state: 'required' },
    { kind: 'reference_fasta', dir: 'in', side: 'top', state: 'required' },
    { kind: 'panel_bed', dir: 'in', side: 'top', state: 'reserved' },
    { kind: 'filtered_vcf', dir: 'out', side: 'right', state: 'required' },
    { kind: 'vcf_index', dir: 'out', side: 'bottom', state: 'reserved' },
  ],
  MultiQC: [
    { kind: 'fastp_json', dir: 'in', side: 'left', state: 'required' },
    { kind: 'markdup_metrics', dir: 'in', side: 'left', state: 'optional' },
    { kind: 'samtools_stats', dir: 'in', side: 'left', state: 'optional' }, // now wired from markdup (compiler catalog)
    { kind: 'mosdepth_summary', dir: 'in', side: 'left', state: 'required' },
    { kind: 'mosdepth_thresholds', dir: 'in', side: 'left', state: 'optional' }, // now ingested (was dangling)
    { kind: 'fastqc_zip', dir: 'in', side: 'top', state: 'reserved' },
    { kind: 'bcftools_stats', dir: 'in', side: 'top', state: 'reserved' },
    { kind: 'picard_hsmetrics', dir: 'in', side: 'top', state: 'reserved' },
    { kind: 'ngscheckmate', dir: 'in', side: 'top', state: 'reserved' },
    { kind: 'multiqc_json', dir: 'out', side: 'right', state: 'required' },
    { kind: 'multiqc_html', dir: 'out', side: 'bottom', state: 'reserved' },
  ],
  // Reference SOURCES — one output port PER consumer (same kind, distinct idx) so each consumer edge is
  // a 1:1 wire (no branching). Side is 'right' (balanceSides lays ref OUTPUTS on the right, with the
  // required outputs); the count MUST match BTOOLSPEC outs (3 fasta / 2 bed / 1 truth).
  'Reference FASTA': [
    { kind: 'reference_fasta', dir: 'out', side: 'right', state: 'required' },
    { kind: 'reference_fasta', dir: 'out', side: 'right', state: 'required' },
    { kind: 'reference_fasta', dir: 'out', side: 'right', state: 'required' },
  ],
  'Panel BED': [
    { kind: 'panel_bed', dir: 'out', side: 'right', state: 'required' },
    { kind: 'panel_bed', dir: 'out', side: 'right', state: 'required' },
  ],
  'FASTQ input': [{ kind: 'fastq', dir: 'out', side: 'right', state: 'required' }],
  // 'File input' has NO fixed catalog entry: its single output port kind is dynamic (whatever the
  // operator picks), and cardPortList falls back to {required, portSide(kind,'out')} for it — so the
  // one port renders correctly for any chosen artifact kind.
  'File output': [{ kind: 'multiqc_json', dir: 'in', side: 'left', state: 'required' }],
}

// Resolve a node's FULL render port list. ins/outs are the WIREABLE truth (editable); their
// side/state come from the catalog by (kind, dir), defaulting to {required, portSide()} for a
// hand-composed node with no catalog entry (backward-compatible: all-required, no reserved, no
// panels beyond its real ports). Reserved ports come from the catalog ONLY. Return order — the
// card-wide identity order — is: wireable ins, wireable outs, then reserved.
export function cardPortList(name: string | undefined, ins: string[], outs: string[]): CardPort[] {
  const cat = (name && CARD_PORTS[name]) || []
  const look = (kind: string, dir: 'in' | 'out'): CardPort | undefined =>
    cat.find((p) => p.kind === kind && p.dir === dir)
  const wIn: CardPort[] = ins.map((kind) => look(kind, 'in') ?? { kind, dir: 'in', side: portSide(kind, 'in'), state: 'required' })
  const wOut: CardPort[] = outs.map((kind) => look(kind, 'out') ?? { kind, dir: 'out', side: portSide(kind, 'out'), state: 'required' })
  // Reserved from the catalog, minus any (kind, dir) already made wireable (never double-render).
  const reserved = cat.filter(
    (p) => p.state === 'reserved' && !(p.dir === 'in' ? ins : outs).includes(p.kind),
  )
  return [...wIn, ...wOut, ...reserved]
}

// A laid-out port: geometry + identity. `idx` = index into the node's ins/outs for a WIREABLE port
// (the wire-anchor key), or -1 for a reserved catalog-only port (never wireable). `pidx` = 1-based
// card-wide identity badge number (wireable ins → wireable outs → reserved, matching cardPortList).
export type LaidPort = {
  kind: string
  dir: 'in' | 'out'
  side: PortSide
  state: PortState
  idx: number
  pidx: number
  cidx: number // DISPLAY number keyed to the box row — never the wire idx
  // The specific EDGE (index into the graph's edge list) this laid port serves, or -1 for an unconnected
  // /reserved port. A wireable port that connects to N cards SPLITS into N laid ports (one per edge),
  // each carrying its edge's eid, so no two edges ever share a start/end point (PASS-2 A). Ports that
  // share a `pidx` are the split halves of ONE logical port (grouped back into one box row).
  eid: number
  lx: number
  ly: number
}
type IndexedPort = CardPort & { idx: number; pidx: number }

// cardPortList + the wire-anchor idx (index into ins/outs; -1 for reserved) + the card-wide pidx.
function indexedPorts(name: string | undefined, ins: string[], outs: string[]): IndexedPort[] {
  let inC = 0
  let outC = 0
  return cardPortList(name, ins, outs).map((p, i) => {
    const wireable = p.state !== 'reserved'
    const idx = wireable ? (p.dir === 'in' ? inC++ : outC++) : -1
    return { ...p, idx, pidx: i + 1 }
  })
}

// ── Two-side balanced port layout (batch 3a — ports ONLY on left/right, no top/bottom) ──
// LEFT = required non-ref inputs then reference INPUTS (below); RIGHT = required non-ref outputs then
// reference OUTPUTS (source cards emit their ref artifact rightward, toward the consumers below/right —
// so a top-band source's wires don't loop back across the card). The optional/reserved non-ref ports
// are then DISTRIBUTED across both sides to balance the per-side count (~equal; an odd total gives LEFT
// the extra, so left ≥ right always). The card's ins/outs arrays, the wire idx, and the wiring model
// are untouched — only each port's SIDE / position / display number change. Tool cards are unchanged
// (they carry no ref OUTPUT); only reference-source cards move their outputs left→right.
const isRef = (kind: string): boolean => REF_IN_KINDS.has(kind)
function balanceSides(ports: IndexedPort[]): { left: IndexedPort[]; right: IndexedPort[] } {
  const reqIn = ports.filter((p) => !isRef(p.kind) && p.state === 'required' && p.dir === 'in')
  const refIn = ports.filter((p) => isRef(p.kind) && p.dir === 'in')
  const refOut = ports.filter((p) => isRef(p.kind) && p.dir === 'out')
  const reqOut = ports.filter((p) => !isRef(p.kind) && p.state === 'required' && p.dir === 'out')
  const distrib = ports.filter((p) => !isRef(p.kind) && p.state !== 'required')
  const leftBase = [...reqIn, ...refIn]
  const rightBase = [...reqOut, ...refOut]
  const toLeft = Math.max(0, Math.min(Math.ceil(ports.length / 2) - leftBase.length, distrib.length))
  return { left: [...leftBase, ...distrib.slice(0, toLeft)], right: [...rightBase, ...distrib.slice(toLeft)] }
}

// The three in-card boxes (batch 3a): REQUIRED (required non-ref), REFERENCE (reference kinds),
// OPTIONAL/RESERVED (opt/reserved non-ref). A box row = one PORT (un-deduped, so the row columns
// number·kind·dir·tag line up), so its row count = ports in that category.
export type BoxCat = 'required' | 'reference' | 'optreserved'
export const BOX_META: { cat: BoxCat; title: string }[] = [
  { cat: 'required', title: 'required' },
  { cat: 'reference', title: 'reference' },
  { cat: 'optreserved', title: 'optional / reserved' },
]
function inCat(kind: string, state: PortState, cat: BoxCat): boolean {
  if (cat === 'reference') return isRef(kind)
  if (cat === 'required') return !isRef(kind) && state === 'required'
  return !isRef(kind) && state !== 'required'
}
// One box ROW per port (un-deduped, so the row columns number·kind·dir·tag line up cleanly). A box
// with many entries uses a compact 2-column grid so it stays scannable (batch 3a-refine point 3).
function catPortCount(ports: IndexedPort[], cat: BoxCat): number {
  return ports.filter((p) => inCat(p.kind, p.state, cat)).length
}
export function boxCols(n: number): number {
  return n >= 6 ? 2 : 1
}
function boxH(n: number): number {
  return n ? 24 + Math.ceil(n / boxCols(n)) * LIST_ROW : 0
}
// Total stacked height of the (non-empty) boxes, with an 8px gap between each.
function boxesTotalH(ports: IndexedPort[]): number {
  const hs = BOX_META.map((b) => boxH(catPortCount(ports, b.cat))).filter((h) => h > 0)
  return hs.length ? hs.reduce((a, b) => a + b, 0) + 8 * (hs.length - 1) : 0
}
function portsZoneH(ports: IndexedPort[]): number {
  const { left, right } = balanceSides(ports)
  return Math.max(Math.max(left.length, right.length, 1) * PORT_PITCH, PORTS_ZONE_MIN)
}
// Card BODY = the taller of the ports band and the boxes (ports flank the boxes on the edges — the
// port numbers now render OUTSIDE the card, freeing the interior for the boxes, batch 3a).
function bodyHeight(ports: IndexedPort[]): number {
  return Math.max(portsZoneH(ports), boxesTotalH(ports))
}
export function cardHeight(name: string | undefined, ins: string[], outs: string[]): number {
  return CARD_HEADER_H + bodyHeight(indexedPorts(name, ins, outs)) + CARD_FOOTER_H + 6
}
export const BOX_TOP = CARD_HEADER_H + 6 // local y where the box stack starts (just below the header)

// Lay every port onto its balanced side (left/right only), evenly stacked over the card body. cidx =
// the DISPLAY number in reading order for the 2-side layout: down the left (1..leftN) then down the
// right (leftN+1..N). (lx, ly) is the flat-side anchor — render + wiring share this one formula, so a
// wire endpoint (which reads the SAME layout by dir+idx) stays attached wherever the side lands.
export function layoutCardPorts(name: string | undefined, ins: string[], outs: string[], w: number, _h: number): LaidPort[] {
  const ports = indexedPorts(name, ins, outs)
  const bodyH = bodyHeight(ports)
  const bodyTop = CARD_HEADER_H
  const { left, right } = balanceSides(ports)
  const laid: LaidPort[] = []
  left.forEach((p, i) => laid.push({ ...p, side: 'left', lx: 0, ly: bodyTop + (bodyH * (i + 1)) / (left.length + 1), cidx: i + 1, eid: -1 }))
  right.forEach((p, i) => laid.push({ ...p, side: 'right', lx: w, ly: bodyTop + (bodyH * (i + 1)) / (right.length + 1), cidx: left.length + i + 1, eid: -1 }))
  return laid
}

// Rows for ONE of the three boxes. A row = one LOGICAL port (grouped by `pidx`), so a split port (N laid
// halves) lists the kind ONCE with its N numbers — the row count stays = the catalog port count the card
// height was sized for, and the box reads coherently (kind · dir · [1][2] · tag). Ordered by lowest number.
export type BoxRow = { pidx: number; kind: string; dir: 'in' | 'out'; state: PortState; cidxs: number[]; minCidx: number }
export function boxPorts(laid: LaidPort[], cat: BoxCat): BoxRow[] {
  const byPidx = new Map<number, LaidPort[]>()
  for (const p of laid) {
    if (!inCat(p.kind, p.state, cat)) continue
    const arr = byPidx.get(p.pidx)
    if (arr) arr.push(p)
    else byPidx.set(p.pidx, [p])
  }
  const rows: BoxRow[] = [...byPidx.values()].map((ps) => {
    ps.sort((a, b) => a.cidx - b.cidx)
    return { pidx: ps[0].pidx, kind: ps[0].kind, dir: ps[0].dir, state: ps[0].state, cidxs: ps.map((p) => p.cidx), minCidx: ps[0].cidx }
  })
  rows.sort((a, b) => a.minCidx - b.minCidx)
  return rows
}
// The category tag stamped on every box row — one consistent set across all boxes: REQ / REF / OPT /
// RSVD. Reference-box rows read REF regardless of their req/opt state (the box header already carries
// "reference"); the OPTIONAL/RESERVED box splits OPT (wireable now) vs RSVD (documented, not-yet-wireable).
export type RowTag = 'REQ' | 'REF' | 'OPT' | 'RSVD'
export function rowTag(cat: BoxCat, state: PortState): RowTag {
  if (cat === 'reference') return 'REF'
  if (cat === 'required') return 'REQ'
  return state === 'optional' ? 'OPT' : 'RSVD'
}

// Backward-compatible fallback for a hand-composed node with no catalog (all-required, no reserved).
export function layoutPorts(ins: string[], outs: string[], w: number, h: number): LaidPort[] {
  return layoutCardPorts(undefined, ins, outs, w, h)
}

// The local (x, y) of ONE WIREABLE port by direction + index — the wire-anchor lookup. Mirrors
// layoutCardPorts (idx is the index into ins/outs; reserved ports carry idx -1, never matched here).
export function portAnchorLocal(
  name: string | undefined, ins: string[], outs: string[], w: number, h: number, dir: 'in' | 'out', idx: number,
): { x: number; y: number } | null {
  const p = layoutCardPorts(name, ins, outs, w, h).find((q) => q.dir === dir && q.idx === idx)
  return p ? { x: p.lx, y: p.ly } : null
}

export function nodeHeight(n: UserNode): number {
  return cardHeight(n.name, n.ins, n.outs)
}
export function nodeBBox(n: UserNode): { x1: number; y1: number; x2: number; y2: number } {
  return { x1: n.x, y1: n.y, x2: n.x + NODE_W, y2: n.y + nodeHeight(n) }
}

// ── Dynamic NEAREST-SIDE port placement (supersedes the fixed left/right balance for RENDERING) ──
// A port's SIDE + position is driven by WHERE its connected node sits: each edge endpoint anchors to the
// point on its card's perimeter nearest the node it connects to, so every wire takes the shortest natural
// path (a card feeding a node below it puts that output near its bottom edge; a node to the right → right
// edge; etc.). Ports can sit on ANY of the four sides. What DOESN'T change: the port NUMBER (cidx) — it is
// still the stable layoutCardPorts numbering, so the three gray boxes reference every port by the SAME
// number and the number↔port↔box-row mapping is untouched; only positions move. A port with NO edge falls
// back to its kind's conventional CATALOG side (a reference-log bay stays on top, a metric byproduct on the
// bottom). Ports that land on the same side are spread evenly (ordered by their desired position) so they
// never overlap. Render (UserCard) AND wire anchors (anchorFull) read this SAME map → the render↔wiring
// invariant holds: a wire meets its port exactly, wherever the dynamic side puts it.
type Vec2 = { x: number; y: number }
const PORT_EDGE_MARGIN = 44 // keep top/bottom ports off the corners (and clear of the 3px left spine)
function sideToVec(s: PortSide): Vec2 {
  return s === 'left' ? { x: -1, y: 0 } : s === 'right' ? { x: 1, y: 0 } : s === 'top' ? { x: 0, y: -1 } : { x: 0, y: 1 }
}
// Which card edge a ray from the centre exits, + the coordinate along that edge (used ONLY to order the
// ports that share a side — the final position is re-spread evenly across the edge).
function sideAndAlong(dir: Vec2, w: number, h: number): { side: PortSide; along: number } {
  const adx = Math.abs(dir.x)
  const ady = Math.abs(dir.y)
  const tx = adx > 1e-6 ? w / 2 / adx : Infinity
  const ty = ady > 1e-6 ? h / 2 / ady : Infinity
  if (tx <= ty) return { side: dir.x >= 0 ? 'right' : 'left', along: h / 2 + dir.y * tx }
  return { side: dir.y >= 0 ? 'bottom' : 'top', along: w / 2 + dir.x * ty }
}
// PASS-2 A — SPLIT PORTS. Any wireable port that connects to N cards splits into N laid ports (one per
// edge), each aimed at ITS target, so no two edges ever share a start/end point (unrelated I/O edges stop
// visually merging). The split is layout-only: the graph model (ins/outs/idx) and the save contract are
// untouched — only the RENDER + wire anchors gain per-edge sub-points. `eid` on each laid port keys it to
// its edge; the wire looks itself up by (dir, idx, eid). Split halves share a `pidx`, so the box regroups
// them into one row (kind once, N numbers) and the card height (sized by catalog count) is unchanged.
export function computeGraphPortLayout(nodes: UserNode[], edges: UserEdge[]): Map<string, LaidPort[]> {
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const centerOf = (n: UserNode): Vec2 => ({ x: n.x + NODE_W / 2, y: n.y + nodeHeight(n) / 2 })
  const result = new Map<string, LaidPort[]>()
  for (const n of nodes) {
    const h = nodeHeight(n)
    // Stable identity per LOGICAL port (kind/dir/idx/pidx/state); side + display number recomputed below.
    const stable = layoutCardPorts(n.name, n.ins, n.outs, NODE_W, h)
    const catalog = cardPortList(n.name, n.ins, n.outs) // conventional side per port (pidx order), for the unconnected fallback
    const nc = centerOf(n)
    // 1. Expand each logical port into one SLOT per edge (splitting multi-edge ports); a 0-edge port keeps
    //    a single slot on its conventional catalog side. Assign the display number sequentially so split
    //    halves get consecutive numbers, then aim each slot at ITS edge's target (nearest side).
    const aimTo = (targetId: string, kind: string, dir: 'in' | 'out'): Vec2 => {
      const t = byId.get(targetId)
      if (!t) return sideToVec(portSide(kind, dir))
      const tc = centerOf(t)
      const d = { x: tc.x - nc.x, y: tc.y - nc.y }
      return d.x === 0 && d.y === 0 ? sideToVec(portSide(kind, dir)) : d
    }
    type Slot = { p: LaidPort; side: PortSide; along: number }
    const slots: Slot[] = []
    let cidx = 0
    for (const p of stable) {
      const conn =
        p.idx >= 0
          ? edges
              .map((e, ei) => ({ e, ei }))
              .filter(
                ({ e }) =>
                  (p.dir === 'out' && e.from.node === n.id && e.from.idx === p.idx) ||
                  (p.dir === 'in' && e.to.node === n.id && e.to.idx === p.idx),
              )
          : []
      if (conn.length === 0) {
        cidx += 1
        const dir = sideToVec(catalog[p.pidx - 1]?.side ?? portSide(p.kind, p.dir))
        slots.push({ p: { ...p, cidx, eid: -1 }, ...sideAndAlong(dir, NODE_W, h) })
      } else {
        for (const { e, ei } of conn) {
          cidx += 1
          const dir = aimTo(p.dir === 'out' ? e.to.node : e.from.node, p.kind, p.dir)
          slots.push({ p: { ...p, cidx, eid: ei }, ...sideAndAlong(dir, NODE_W, h) })
        }
      }
    }
    // 2. Spread each side's slots evenly (ordered by desired position) so they never overlap. Left/right
    //    slots occupy the body band (below header, above footer); top/bottom slots span the width, inset.
    const laid: LaidPort[] = []
    for (const side of ['left', 'right', 'top', 'bottom'] as PortSide[]) {
      const grp = slots.filter((q) => q.side === side).sort((a, b) => a.along - b.along)
      const vert = side === 'left' || side === 'right'
      const lo = vert ? CARD_HEADER_H + 4 : PORT_EDGE_MARGIN
      const hi = vert ? h - CARD_FOOTER_H - 4 : NODE_W - PORT_EDGE_MARGIN
      const span = Math.max(0, hi - lo)
      grp.forEach((q, i) => {
        const t = lo + (span * (i + 1)) / (grp.length + 1)
        const lx = side === 'left' ? 0 : side === 'right' ? NODE_W : t
        const ly = side === 'top' ? 0 : side === 'bottom' ? h : t
        laid.push({ ...q.p, side, lx, ly })
      })
    }
    result.set(n.id, laid)
  }
  return result
}

// ── Advisory agents (off-gate, ADR-0001) ─────────────────────────────────────
// An advisory agent OBSERVES tools and advises; it is OFF the deterministic critical path — it never
// carries typed data and never sets a verdict/confidence. It is deliberately NOT a UserNode and its
// links are NOT UserEdges, so it can never sit on a data edge or influence the gate. `defaultAttach`
// seeds which tools it watches; the canvas holds the live (togglable) attach set. One agent can attach
// to MANY tools (multi-port fan-out, like a multi-output reference source).
export type AdvisoryAgent = { id: string; name: string; observes: string; model: string; live: boolean; defaultAttach: string[] }
export const ADVISORY_AGENT: AdvisoryAgent = {
  id: 'a_qc_triage',
  name: 'QC-triage',
  observes: 'qc',
  model: 'stub',
  live: false,
  // The QC-signal producers + the aggregator this agent triages (seeded; the operator can re-attach).
  defaultAttach: ['n_fastp', 'n_mosdepth', 'n_multiqc'],
}

// Place ONE anchor point per target on a rectangle's perimeter, each on the side nearest its target and
// spread evenly per side so they never overlap — the agent-card fan-out (mirrors the nearest-side port
// model, but for a non-graph terminal card against arbitrary target points). Returns content-space points.
export type FanPort = { side: PortSide; x: number; y: number }
export function fanPortsToTargets(rect: { x: number; y: number; w: number; h: number }, targets: Vec2[]): FanPort[] {
  const cx = rect.x + rect.w / 2
  const cy = rect.y + rect.h / 2
  const want = targets.map((t, i) => {
    const raw = { x: t.x - cx, y: t.y - cy }
    const dir = raw.x === 0 && raw.y === 0 ? { x: 1, y: 0 } : raw
    return { i, ...sideAndAlong(dir, rect.w, rect.h) }
  })
  const out: FanPort[] = new Array(targets.length)
  for (const side of ['left', 'right', 'top', 'bottom'] as PortSide[]) {
    const grp = want.filter((q) => q.side === side).sort((a, b) => a.along - b.along)
    const vert = side === 'left' || side === 'right'
    const lo = vert ? 10 : 14
    const hi = vert ? rect.h - 10 : rect.w - 14
    const span = Math.max(0, hi - lo)
    grp.forEach((q, k) => {
      const pos = lo + (span * (k + 1)) / (grp.length + 1)
      const lx = side === 'left' ? 0 : side === 'right' ? rect.w : pos
      const ly = side === 'top' ? 0 : side === 'bottom' ? rect.h : pos
      out[q.i] = { side, x: rect.x + lx, y: rect.y + ly }
    })
  }
  return out
}

export function renameNode(ns: UserNode[], id: string, name: string): UserNode[] {
  return ns.map((n) => (n.id === id ? { ...n, name } : n))
}
export function setNodeIcon(ns: UserNode[], id: string, icon: IconKey): UserNode[] {
  return ns.map((n) => (n.id === id ? { ...n, icon } : n))
}

// Copy a node with a fresh id, offset position, and no edges (the caller re-wires deliberately).
// `index` disambiguates ids when duplicating a whole selection in one gesture.
export function duplicateNode(n: UserNode, index = 0, offset = 24): UserNode {
  return {
    ...n,
    id: `u${Date.now().toString(36)}${index}${Math.floor(Math.random() * 1296).toString(36)}`,
    name: `${n.name} copy`,
    ins: [...n.ins],
    outs: [...n.outs],
    outGlobs: n.outGlobs ? [...n.outGlobs] : undefined, // deep-copy the parallel emit-glob array (ADR-0020)
    x: n.x + offset,
    y: n.y + offset,
  }
}

// Drop any edge whose endpoint node/port-idx no longer exists or whose kinds no longer match — the
// safety net after a port retype/remove so no dangling or mistyped wire survives (honest typed graph).
export function reconcileEdges(ns: UserNode[], es: UserEdge[]): UserEdge[] {
  return es.filter((e) => {
    const f = ns.find((n) => n.id === e.from.node)
    const t = ns.find((n) => n.id === e.to.node)
    if (!f || !t) return false
    const fk = f.outs[e.from.idx]
    const tk = t.ins[e.to.idx]
    return fk != null && tk != null && fk === tk
  })
}

export function edgeMidpoint(a: { x: number; y: number }, b: { x: number; y: number }): { x: number; y: number } {
  // The elbow path routes through mx = (a.x+b.x)/2; the visual midpoint sits there at the mean y.
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
}

// The germline panel chain as EDITABLE user nodes + wired edges (the exact fastp → bwa-mem2 →
// samtools markdup → {mosdepth, bcftools call → norm} → MultiQC pipeline the demo ran). Powers
// "New → From template" and "Fork" so those open a MODIFIABLE draft instead of the read-only
// seeded cards (the hard-coded-DAG report). Node ids/positions/ports mirror the seeded TOOLS, so
// the layout, the typed-port wiring, and the Validate focus refs all line up. Pure — no run state.
export function germlineTemplate(): { nodes: UserNode[]; edges: UserEdge[] } {
  const toolNodes: UserNode[] = TOOLS.map((t) => ({
    id: t.id,
    name: t.tool,
    kind: t.outputs[0]?.kind ?? 'artifact',
    version: t.version,
    icon: t.icon,
    ins: t.inputs.map((p) => p.kind),
    outs: t.outputs.map((p) => p.kind),
    x: t.x,
    y: t.y,
    vstatus: t.vstatus, // carry the bound run's per-step status onto the editable node → left-spine (ADR-0019)
  }))
  // Reference SOURCES as first-class editable nodes (ins:[]) so the WHOLE pipeline — sources + tools —
  // is one editable, saveable graph (ADR-0019 slice 1a). Positioned in the top reference band (y ≈ REF_Y),
  // x aligned over their primary consumer (mirrors the static REFS layout).
  const SRC_NAME: Record<string, string> = { r_fasta: 'Reference FASTA', r_bed: 'Panel BED' }
  const REF_Y = 40
  const sourceNodes: UserNode[] = REFS.map((r) => {
    const name = SRC_NAME[r.id] ?? r.label
    const spec = BTOOLSPEC[name] ?? { version: 'v1.0', icon: 'db' as IconKey, ins: [], outs: [r.kind] }
    return { id: r.id, name, kind: r.kind, version: spec.version, icon: spec.icon, ins: [], outs: [r.kind], x: r.x, y: REF_Y }
  })
  // Primary-lane FASTQ input source (raw fastq folder → fastp) so the first card is fed (slice 1c),
  // above fastp in the top source band. And a File-output SINK on the branch row near MultiQC, so the
  // whole graph closes on both ends: source → tools → sink (the intent recorded in BTOOLSPEC's comment).
  const fastqSource: UserNode = { id: 'src_fastq', name: 'FASTQ input', kind: 'fastq', version: 'folder', icon: 'db', ins: [], outs: ['fastq'], x: 40, y: REF_Y }
  const fileOutput: UserNode = { id: 'sink_file', name: 'File output', kind: 'multiqc_json', version: 'file', icon: 'archive', ins: ['multiqc_json'], outs: [], x: 1560, y: 600 }
  const nodes: UserNode[] = [...toolNodes, ...sourceNodes, fastqSource, fileOutput]
  // Resolve a port index by kind (0 if absent), so the wiring can never forge a mismatched edge.
  const portIdx = (nodeId: string, side: 'ins' | 'outs', kind: string): number => {
    const n = nodes.find((x) => x.id === nodeId)
    const i = n ? n[side].indexOf(kind) : -1
    return i < 0 ? 0 : i
  }
  const wire = (fromId: string, outKind: string, toId: string, inKind: string): UserEdge => ({
    from: { node: fromId, idx: portIdx(fromId, 'outs', outKind) },
    to: { node: toId, idx: portIdx(toId, 'ins', inKind) },
  })
  // A reference source now has ONE output port per consumer (same kind), so its edges must address a
  // DISTINCT output idx each — portIdx-by-kind would return 0 for all of them and re-branch. wireOut
  // pins the exact source output index; the consumer input is still resolved by kind (one per tool).
  const wireOut = (fromId: string, fromIdx: number, toId: string, inKind: string): UserEdge => ({
    from: { node: fromId, idx: fromIdx },
    to: { node: toId, idx: portIdx(toId, 'ins', inKind) },
  })
  const edges: UserEdge[] = [
    wire('n_fastp', 'fastq', 'n_bwa', 'fastq'),
    wire('n_bwa', 'bam', 'n_markdup', 'bam'),
    wire('n_markdup', 'bam', 'n_mosdepth', 'bam'),
    wire('n_markdup', 'bam', 'n_call', 'bam'),
    wire('n_call', 'vcf', 'n_norm', 'vcf'),
    wire('n_fastp', 'fastp_json', 'n_multiqc', 'fastp_json'),
    wire('n_markdup', 'markdup_metrics', 'n_multiqc', 'markdup_metrics'),
    wire('n_markdup', 'samtools_stats', 'n_multiqc', 'samtools_stats'), // samtools stats → MultiQC (W3)
    wire('n_mosdepth', 'mosdepth_summary', 'n_multiqc', 'mosdepth_summary'),
    wire('n_mosdepth', 'mosdepth_thresholds', 'n_multiqc', 'mosdepth_thresholds'), // thresholds → MultiQC (W3)
    // reference source → tool ref-input edges, each off a DISTINCT source output port (fasta out 0/1/2
    // → bwa/call/norm; bed out 0/1 → mosdepth/call; truth VCF unwired).
    wireOut('r_fasta', 0, 'n_bwa', 'reference_fasta'),
    wireOut('r_fasta', 1, 'n_call', 'reference_fasta'),
    wireOut('r_fasta', 2, 'n_norm', 'reference_fasta'),
    wireOut('r_bed', 0, 'n_mosdepth', 'panel_bed'),
    wireOut('r_bed', 1, 'n_call', 'panel_bed'),
    wire('src_fastq', 'fastq', 'n_fastp', 'fastq'), // FASTQ input source → fastp (slice 1c)
    wire('n_multiqc', 'multiqc_json', 'sink_file', 'multiqc_json'), // QC report → file-output sink
  ]
  return { nodes, edges }
}

// ── the emitted locator set (giab_panel), in emit order ──────────────────────
export type GiabLoc = {
  k: string
  field: 'path' | 'glob'
  loc: string
  parser: string
  required: boolean
  role: 'output' | 'reference'
  on: OnMultiple
}
export const GIAB_LOC: GiabLoc[] = [
  { k: 'fastq', field: 'glob', loc: 'fastq/*_R{1,2}_001.fastq.gz', parser: 'null', required: true, role: 'output', on: 'all' },
  { k: 'fastp_json', field: 'path', loc: 'qc/HG002.fastp.json', parser: 'fastp_json', required: true, role: 'output', on: 'error' },
  { k: 'bam', field: 'glob', loc: 'align/*.md.bam', parser: 'null', required: true, role: 'output', on: 'error' },
  { k: 'markdup_metrics', field: 'path', loc: 'qc/HG002.markdup.txt', parser: 'markdup_metrics', required: false, role: 'output', on: 'error' },
  { k: 'mosdepth_summary', field: 'path', loc: 'mosdepth/HG002.summary.txt', parser: 'mosdepth_summary', required: true, role: 'output', on: 'error' },
  { k: 'filtered_vcf', field: 'glob', loc: 'variants/*.norm.filtered.vcf.gz', parser: 'vcf', required: true, role: 'output', on: 'error' },
  { k: 'multiqc_json', field: 'path', loc: 'multiqc_data/multiqc_data.json', parser: 'null', required: false, role: 'output', on: 'error' },
  { k: 'reference_fasta', field: 'path', loc: 'reference/GRCh38.fa', parser: 'null', required: true, role: 'reference', on: 'error' },
  { k: 'panel_bed', field: 'path', loc: 'reference/panel.bed', parser: 'null', required: true, role: 'reference', on: 'error' },
]
export const ON_CYCLE: Record<OnMultiple, OnMultiple> = { first: 'all', all: 'error', error: 'first' }

// Known artifact kinds with NO seeded palette node or emitted locator, kept OFFERABLE so a generic
// 'File input' source (or a hand-composed node) can still stand in for a retired named source — e.g. a
// truth/benchmark VCF or an identity report to re-gate. Mirrors the backend node_author ARTIFACT_KINDS
// literal (src/pipeguard/node_author/models.py), which also carries truth_vcf + ngscheckmate after the
// Truth VCF / NGSCheckMate palette nodes were removed; the two vocabularies stay in sync.
const EXTRA_VOCAB_KINDS = ['truth_vcf', 'ngscheckmate']
// The typed port-kind vocabulary the inspector offers — the UNION of every BTOOLSPEC in/out kind,
// every emitted locator kind, and EXTRA_VOCAB_KINDS. Manual port editing is constrained to this set so
// a hand-authored node can never invent a kind the wiring/locators don't understand (mirrors the
// "flagged, never invented" ethos of the author-node flow). NOTE: declared AFTER GIAB_LOC — it reads
// GIAB_LOC at module-init, so it must not be hoisted above that const (would be a temporal-dead-zone crash).
export const ARTIFACT_KINDS: string[] = Array.from(
  new Set([
    ...Object.values(BTOOLSPEC).flatMap((s) => [...s.ins, ...s.outs]),
    ...GIAB_LOC.map((g) => g.k),
    ...EXTRA_VOCAB_KINDS,
  ]),
).sort()

// Per-kind locator edits (path/parser/on_multiple/required). Origin is NEVER editable — it is
// locked 'unknown' at emit and stamped only at ingest (INV: origin never relabels up).
export type LocEdit = Partial<Pick<GiabLoc, 'loc' | 'parser' | 'required' | 'on'>>
export type LocEdits = Record<string, LocEdit>

// The builder's read-back view of a saved PipelineGraph.graph envelope (T-069 saved-profiles load
// path). Every field optional: the store keeps `graph` as an arbitrary dict (api/pipeline.py), so a
// save from another schema_version may omit these. Absent → treat as empty; never invent a topology.
export type BuilderGraphPayload = {
  nodes?: UserNode[]
  edges?: UserEdge[]
  locator_edits?: LocEdits
  reference_locators?: Record<string, string>
}

export function mergedLoc(k: string, edits: LocEdits): GiabLoc {
  const base = GIAB_LOC.find((x) => x.k === k)
  if (!base) throw new Error(`unknown locator kind ${k}`)
  return { ...base, ...(edits[k] ?? {}) }
}

function padr(s: string | number, n: number): string {
  const str = String(s)
  return str.length >= n ? str : str + ' '.repeat(n - str.length)
}

// Build the live YAML for an editable (giab/custom) profile from the merged locators.
export function buildYaml(profile: string, edits: LocEdits): string {
  const out = ['schema_version: run_layout/1', `profile: ${padr(profile, 20)}# PIPEGUARD_RUN_LAYOUT=${profile}`, 'locators:']
  for (const g of GIAB_LOC) {
    const m = mergedLoc(g.k, edits)
    const body = `${m.field}: "${m.loc}"`
    out.push(
      '  ' + padr(`${g.k}:`, 18) + '{ ' + padr(`${body},`, 46) +
      ` parser: ${padr(`${m.parser},`, 17)} required: ${padr(`${m.required},`, 7)} role: ${padr(`${m.role},`, 11)} on_multiple: ${padr(`${m.on},`, 7)} origin: unknown }`,
    )
  }
  return out.join('\n')
}

export const YAML_DEFAULT = `schema_version: run_layout/1
profile: default                     # PIPEGUARD_RUN_LAYOUT=default
locators:
  fastp_json:       { path: "qc/{sample}.fastp.json",        parser: fastp_json,       required: true,  role: output,    on_multiple: error, origin: unknown }
  recal_cram:       { glob: "preprocessing/**/*.recal.cram", parser: null,             required: true,  role: output,    on_multiple: error, origin: unknown }
  recal_table:      { glob: "preprocessing/**/*.recal.table",parser: null,             required: false, role: output,    on_multiple: error, origin: unknown }
  mosdepth_summary: { path: "reports/mosdepth/{sample}.summary.txt", parser: mosdepth_summary, required: true, role: output, on_multiple: error, origin: unknown }
  vcf:              { glob: "variant_calling/**/*.vcf.gz",   parser: vcf,              required: true,  role: output,    on_multiple: error, origin: unknown }
  reference_fasta:  { path: "reference/GRCh38.fa",           parser: null,             required: true,  role: reference, on_multiple: error, origin: unknown }
  # default profile shape uses recal_cram — never coerced to bam.`

export const YAML_SAREK = `# sarek profile — illustrative / target-state (not yet wired end-to-end)
schema_version: run_layout/1
profile: sarek                       # PIPEGUARD_RUN_LAYOUT=sarek
locators:
  fastp_json:       { glob: "**/fastp/*.json",              parser: fastp_json,       required: true,  role: output,    on_multiple: error, origin: unknown }
  recal_cram:       { glob: "preprocessing/recalibrated/**/*.cram", parser: null,      required: true,  role: output,    on_multiple: error, origin: unknown }
  mosdepth_summary: { glob: "reports/mosdepth/**/*.summary.txt", parser: mosdepth_summary, required: true, role: output, on_multiple: error, origin: unknown }
  joint_vcf:        { glob: "variant_calling/haplotypecaller/**/*.vcf.gz", parser: vcf, required: true, role: output, on_multiple: error, origin: unknown }
  reference_fasta:  { path: "igenomes/GRCh38/genome.fasta", parser: null,             required: true,  role: reference, on_multiple: error, origin: unknown }`

// default/sarek are static shapes; every other profile (giab_panel, saved, draft-from-graph)
// is editable and renders live from the merged locators.
export function yamlFor(profile: string, edits: LocEdits): string {
  if (profile === 'default') return YAML_DEFAULT
  if (profile === 'sarek') return YAML_SAREK
  return buildYaml(profile, edits)
}
export function isEditableProfile(profile: string): boolean {
  return profile !== 'default' && profile !== 'sarek'
}

// The merged FULL locator set for the save payload, in the shape the backend's tolerant
// `_extract_locators` recognizes (a top-level `locators` list of {kind, path|glob, parser,
// required, role, on_multiple}). F2 originally saved only the partial `locEdits` dict, which the
// dry-run/diff endpoints can't read; this projects GIAB_LOC ⋈ edits into the consumable list so a
// saved pipeline actually resolves at dry-run time. `origin` is deliberately omitted (stamped at
// ingest, never authored — INV: origin never relabels up).
export function savedLocators(edits: LocEdits): Array<Record<string, unknown>> {
  return GIAB_LOC.map((g) => {
    const m = mergedLoc(g.k, edits)
    return {
      kind: m.k,
      [m.field]: m.loc, // 'path' or 'glob' key — the mode the backend infers from
      parser: m.parser,
      required: m.required,
      role: m.role,
      on_multiple: m.on,
    }
  })
}

// One-line projection of each locator, for the Diff tab (current vs last-Emit snapshot).
export function curLocMap(edits: LocEdits): Record<string, string> {
  const out: Record<string, string> = {}
  for (const g of GIAB_LOC) {
    const m = mergedLoc(g.k, edits)
    out[g.k] = `${m.field} ${m.loc} · parser ${m.parser} · ${m.required ? 'required' : 'optional'} · on_multiple ${m.on}`
  }
  return out
}

// Dry-run resolution against a mock run dir — paths only, reads no bytes (compose ≠ execute).
export type DryStatus = 'matched' | 'ambiguous' | 'missing'
export type DryRow = { kind: string; status: DryStatus; detail: string }
export function dryRows(edits: LocEdits): DryRow[] {
  return GIAB_LOC.map((g) => {
    const m = mergedLoc(g.k, edits)
    let status: DryStatus = 'matched'
    let detail = 'run/' + m.loc.replace('*', 'HG002')
    if (g.k === 'fastq') detail = '2 files · run/fastq/HG002_R{1,2}_001.fastq.gz'
    if (g.k === 'multiqc_json') { status = 'ambiguous'; detail = '2 candidates under run/multiqc_data/' }
    return { kind: g.k, status, detail }
  })
}

// Static typed checks (README §6 Validate). V3/V7 focus the norm node; the rest keep the
// currently-selected node in view. All honest against the invariants (origin=unknown, gate
// terminal, agents port-less, DAG).
export type ValSev = 'ok' | 'info'
export const VAL_ROWS: { sev: ValSev; code: string; msg: string; focus?: string }[] = [
  { sev: 'ok', code: 'V1', msg: 'Typed ports — all edges kind-matched' },
  { sev: 'ok', code: 'V2', msg: 'Required config satisfied on every node' },
  { sev: 'ok', code: 'V3', msg: 'Gate reachable via ingest — fastp_json · mosdepth_summary · filtered_vcf present', focus: 'n_norm' },
  { sev: 'ok', code: 'V4', msg: 'Gate terminal, singular, non-removable' },
  { sev: 'ok', code: 'V5', msg: 'Agents off the critical path (0 data ports)' },
  { sev: 'ok', code: 'V6', msg: 'origin = unknown on every emitted locator' },
  { sev: 'info', code: 'V7', msg: 'variants/*.norm.filtered.vcf.gz · on_multiple:error — ambiguity resolves at ingest', focus: 'n_norm' },
  { sev: 'ok', code: 'V8', msg: 'Acyclic (DAG)' },
]

export const RUNBOOK_ROWS = [
  { metric: 'Q30', gate: '≥ 85%', hard: '75%' },
  { metric: '% reads identified', gate: '≥ 70%', hard: '50%' },
  { metric: 'Mean coverage', gate: '≥ 30×', hard: '15×' },
  { metric: 'Cluster PF', gate: '≥ 80%', hard: '60%' },
  { metric: 'Duplication rate', gate: '≤ 30%', hard: '50%' },
]

export type SavedProfile = { k: string; ver: string; status: string }
export const SAVED_PROFILES: SavedProfile[] = [
  { k: 'wes-trio-v2', ver: 'v4', status: 'approved' },
  { k: 'cardio-panel-v1', ver: 'v2', status: 'draft' },
]
export const BUILTIN_PROFILES = ['default', 'giab_panel', 'sarek']

// ── Run hand-off stepper (composes ≠ executes) ──
export const RUN_STEPS: { title: string; desc: string }[] = [
  { title: 'Emit run_layout.yaml', desc: 'PipeGuard writes the artifact-kind → path config.' },
  { title: 'Nextflow / bioconda executes', desc: 'Your engine runs the tools — outside PipeGuard.' },
  { title: 'Deterministic ingest', desc: 'write_run_dir freezes run/ (5 CSVs).' },
  { title: 'run_gate gates + records', desc: 'Rules compute the verdict; the ledger is written.' },
  { title: 'Decision cards', desc: 'Per-sample verdicts land for review.' },
]

// ── Author-a-tool-node: parsed STAR --help + proposed flags ──
export const STAR_HELP = `STAR 2.7.11b (RNA-seq aligner)
--readFilesIn R1.fq.gz R2.fq.gz
--genomeDir /ref/star_index
--outSAMtype BAM SortedByCoordinate
--quantMode GeneCounts
outputs:
  Aligned.sortedByCoord.out.bam
  SJ.out.tab
  ReadsPerGene.out.tab
  Log.final.out`

// ProposedFlag shape (README §7). `on` seeds the checklist; the human toggles + edits values.
export type AuthorFlag = { flag: string; value: string; help: string; on: boolean }
export const AUTHOR_FLAGS: AuthorFlag[] = [
  { flag: '--outSAMtype', value: 'BAM SortedByCoordinate', help: 'sorted BAM output', on: true },
  { flag: '--quantMode', value: 'GeneCounts', help: 'per-gene read counts', on: true },
  { flag: '--twopassMode', value: 'Basic', help: '2-pass splice discovery', on: false },
  { flag: '--sjdbOverhang', value: '100', help: 'read length − 1', on: true },
  { flag: '--outFilterMultimapNmax', value: '20', help: 'max multimappers', on: false },
  { flag: '--peOverlapNbasesMin', value: '12', help: 'min PE overlap', on: false },
]

// Icon-picker choices for the proposed ToolNode (README §6 mandates an icon picker).
export const ICON_CHOICES: IconKey[] = ['merge', 'scissors', 'copy', 'bars', 'dna', 'funnel', 'layers']
