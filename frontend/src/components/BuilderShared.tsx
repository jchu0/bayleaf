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
  Wrench,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

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
  | 'activity' | 'wrench' | 'archive' | 'shield' | 'db'
export const ICONS: Record<IconKey, LucideIcon> = {
  scissors: Scissors, merge: GitMerge, copy: Copy, bars: BarChart3, dna: Dna,
  funnel: Filter, layers: Layers, activity: Activity, wrench: Wrench,
  archive: Archive, shield: ShieldCheck, db: Database,
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
}
export type UserEdge = { from: { node: string; idx: number }; to: { node: string; idx: number } }

export const PG_BADGE: Record<PgStatus, { label: string; fg: string; bg: string }> = {
  ours: { label: 'ours', fg: '#1f5fd0', bg: '#eaf0fc' },
  full: { label: 'consumes', fg: '#0e8f7e', bg: '#e2f4f0' },
  partial: { label: 'substitute', fg: '#c1560f', bg: '#fceee2' },
}
export const V_COLOR: Record<VStatus, string> = { ok: '#1a854e', warn: '#b07714', blocked: '#cf3238' }

// Seeded germline chain: fastp → bwa-mem2 → samtools markdup → {mosdepth, bcftools call →
// bcftools norm} → MultiQC. Kinds on the ports drive the palette subs + kind-matching.
export const TOOLS: Tool[] = [
  {
    id: 'n_fastp', tool: 'fastp', version: '0.23.4', stageLabel: 'Read QC + trim', pg: 'ours', icon: 'scissors',
    x: 40, y: 180, vstatus: 'ok', inputs: [{ kind: 'fastq' }], outputs: [{ kind: 'fastp_json' }, { kind: 'fastq' }],
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
    x: 340, y: 180, vstatus: 'ok', inputs: [{ kind: 'fastq' }, { kind: 'reference_fasta', ref: true }], outputs: [{ kind: 'bam' }],
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
    x: 640, y: 180, vstatus: 'ok', inputs: [{ kind: 'bam' }], outputs: [{ kind: 'bam' }, { kind: 'bai' }, { kind: 'markdup_metrics' }],
    params: [{ k: 'remove_duplicates', v: 'false', help: 'Mark, do not drop' }],
    io: [
      { name: 'HG002.md.bam', sha: 'sha256:7a11…4c2', size: '32 GB', origin: 'real-giab' },
      { name: 'HG002.markdup.txt', sha: 'sha256:c93e…08a', size: '2 KB', origin: 'real-giab' },
    ],
  },
  {
    id: 'n_mosdepth', tool: 'mosdepth', version: '0.3.8', stageLabel: 'Coverage', pg: 'ours', icon: 'bars',
    x: 940, y: 180, vstatus: 'warn', inputs: [{ kind: 'bam' }, { kind: 'panel_bed', ref: true }], outputs: [{ kind: 'mosdepth_summary' }, { kind: 'mosdepth_thresholds' }],
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
    x: 1240, y: 180, vstatus: 'ok', inputs: [{ kind: 'bam' }, { kind: 'reference_fasta', ref: true }, { kind: 'panel_bed', ref: true }], outputs: [{ kind: 'vcf' }],
    params: [
      { k: 'min_MQ', v: '20', help: 'mpileup min mapping quality' },
      { k: 'min_BQ', v: '20', help: 'mpileup min base quality' },
      { k: 'variants_only', v: 'true', help: 'Emit variant sites only' },
    ],
    io: [{ name: 'HG002.bcftools.vcf.gz', sha: 'sha256:be77…512', size: '128 MB', origin: 'real-giab' }],
  },
  {
    id: 'n_norm', tool: 'bcftools norm', version: '1.20', stageLabel: 'Filter / normalize', pg: 'partial', icon: 'funnel',
    x: 1540, y: 180, vstatus: 'ok', inputs: [{ kind: 'vcf' }, { kind: 'reference_fasta', ref: true }], outputs: [{ kind: 'filtered_vcf' }],
    params: [
      { k: 'norm', v: '-m -both', help: 'Split multiallelics' },
      { k: 'fasta_ref', v: 'GRCh38.fa', help: 'Left-align against the reference' },
    ],
    io: [{ name: 'HG002.norm.filtered.vcf.gz', sha: 'sha256:12ab…9f0', size: '44 MB', origin: 'real-giab' }],
  },
  {
    id: 'n_multiqc', tool: 'MultiQC', version: '1.21', stageLabel: 'QC aggregation', pg: 'full', icon: 'layers',
    x: 1840, y: 180, vstatus: 'ok', inputs: [{ kind: 'fastp_json' }, { kind: 'markdup_metrics' }, { kind: 'mosdepth_summary' }], outputs: [{ kind: 'multiqc_json' }],
    params: [{ k: 'force', v: 'true', help: 'Overwrite existing report' }],
    io: [{ name: 'multiqc_data.json', sha: 'sha256:5be3…9c4', size: '2.1 MB', origin: 'real-giab' }],
  },
]

// (Seeded canvas edges are now COMPUTED from the tool/ref card geometry in BuilderCanvas —
// SEEDED_WIRES/REF_WIRES — so they stay attached to the ports; the old hardcoded path table was
// removed with the "broken lines" fix.)

export type Ref = { id: string; label: string; kind: string; file: string; x: number }
export const REFS: Ref[] = [
  { id: 'r_fasta', label: 'Reference genome', kind: 'reference_fasta', file: 'reference/GRCh38.fa', x: 340 },
  { id: 'r_bed', label: 'Panel BED', kind: 'panel_bed', file: 'reference/panel.bed', x: 940 },
  { id: 'r_truth', label: 'Truth VCF', kind: 'truth_vcf', file: 'HG002…benchmark.vcf.gz', x: 2300 },
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
  'fastp': { version: '0.23.4', icon: 'scissors', ins: ['fastq'], outs: ['fastp_json', 'fastq'] },
  'bwa-mem2': { version: '2.2.1', icon: 'merge', ins: ['fastq', 'reference_fasta'], outs: ['bam'] },
  'samtools markdup': { version: '1.20', icon: 'copy', ins: ['bam'], outs: ['bam', 'bai', 'markdup_metrics'] },
  'mosdepth': { version: '0.3.8', icon: 'bars', ins: ['bam', 'panel_bed'], outs: ['mosdepth_summary', 'mosdepth_thresholds'] },
  'bcftools call': { version: '1.20', icon: 'dna', ins: ['bam', 'reference_fasta', 'panel_bed'], outs: ['vcf'] },
  'bcftools norm': { version: '1.20', icon: 'funnel', ins: ['vcf', 'reference_fasta'], outs: ['filtered_vcf'] },
  'MultiQC': { version: '1.21', icon: 'layers', ins: ['fastp_json', 'markdup_metrics', 'mosdepth_summary'], outs: ['multiqc_json'] },
  'NGSCheckMate': { version: '1.0.1', icon: 'bars', ins: ['bam'], outs: ['ngscheckmate'] },
  // Reference SOURCES — no inputs; each emits a reference artifact a tool's ref input consumes
  // (fasta → bwa/call/norm, bed → mosdepth/call, truth VCF → benchmarking). Typed wiring keeps
  // a fasta from landing on a fastq port.
  'Reference FASTA': { version: 'GRCh38', icon: 'db', ins: [], outs: ['reference_fasta'] },
  'Panel BED': { version: 'panel', icon: 'db', ins: [], outs: ['panel_bed'] },
  'Truth VCF': { version: 'v4.2.1', icon: 'db', ins: [], outs: ['truth_vcf'] },
}

export function makeUserNode(name: string, kind: string, index: number): UserNode {
  const spec = BTOOLSPEC[name] ?? { version: 'v1.0', icon: 'merge' as IconKey, ins: [kind], outs: [kind] }
  const x = 150 + (index % 3) * 200
  const y = 80 + Math.floor(index / 3) * 160
  return { id: `u${Date.now().toString(36)}${index}`, name, kind, version: spec.version, icon: spec.icon, ins: spec.ins, outs: spec.outs, x, y }
}

// ── On-canvas editing helpers (PB2) ────────────────────────────────────────
// Pure array rewrites + geometry, framework-thin so the screen owns the history/state and these
// stay unit-testable. Every mutation is over the local draft (compose ≠ execute).

// User-node width mirrors BuilderCanvas UW (the card is a fixed 192px — enlarged toward the
// Databricks process-card footprint, docs/design/builder-cards §3); height is derived from the
// port-row count so marquee-intersection and alignment-guide hit-testing track the rendered card.
// MUST stay in lockstep with BuilderCanvas.UW (out-port anchors sit at n.x + UW).
export const NODE_W = 192
export function nodeHeight(n: UserNode): number {
  // header (icon + name + ×) ≈ 42, per-port row ≈ 18, draft footer ≈ 26 — close enough for hit-testing.
  const rows = Math.max(n.ins.length, n.outs.length, 1)
  return 42 + rows * 18 + 26
}
export function nodeBBox(n: UserNode): { x1: number; y1: number; x2: number; y2: number } {
  return { x1: n.x, y1: n.y, x2: n.x + NODE_W, y2: n.y + nodeHeight(n) }
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
  const nodes: UserNode[] = TOOLS.map((t) => ({
    id: t.id,
    name: t.tool,
    kind: t.outputs[0]?.kind ?? 'artifact',
    version: t.version,
    icon: t.icon,
    ins: t.inputs.map((p) => p.kind),
    outs: t.outputs.map((p) => p.kind),
    x: t.x,
    y: t.y,
  }))
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
  const edges: UserEdge[] = [
    wire('n_fastp', 'fastq', 'n_bwa', 'fastq'),
    wire('n_bwa', 'bam', 'n_markdup', 'bam'),
    wire('n_markdup', 'bam', 'n_mosdepth', 'bam'),
    wire('n_markdup', 'bam', 'n_call', 'bam'),
    wire('n_call', 'vcf', 'n_norm', 'vcf'),
    wire('n_fastp', 'fastp_json', 'n_multiqc', 'fastp_json'),
    wire('n_markdup', 'markdup_metrics', 'n_multiqc', 'markdup_metrics'),
    wire('n_mosdepth', 'mosdepth_summary', 'n_multiqc', 'mosdepth_summary'),
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
  { k: 'truth_vcf', field: 'path', loc: 'reference/HG002_benchmark.vcf.gz', parser: 'null', required: false, role: 'reference', on: 'error' },
]
export const ON_CYCLE: Record<OnMultiple, OnMultiple> = { first: 'all', all: 'error', error: 'first' }

// The typed port-kind vocabulary the inspector offers — the UNION of every BTOOLSPEC in/out kind
// and every emitted locator kind. Manual port editing is constrained to this set so a hand-authored
// node can never invent a kind the wiring/locators don't understand (mirrors the "flagged, never
// invented" ethos of the author-node flow). NOTE: declared AFTER GIAB_LOC — it reads GIAB_LOC at
// module-init, so it must not be hoisted above that const (would be a temporal-dead-zone crash).
export const ARTIFACT_KINDS: string[] = Array.from(
  new Set([...Object.values(BTOOLSPEC).flatMap((s) => [...s.ins, ...s.outs]), ...GIAB_LOC.map((g) => g.k)]),
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
    if (g.k === 'truth_vcf') { status = 'missing'; detail = 'no match — optional, skipped' }
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
