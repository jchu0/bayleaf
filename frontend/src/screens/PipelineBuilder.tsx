import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  Copy,
  Database,
  Dna,
  Download,
  Filter,
  GitMerge,
  Layers,
  ListChecks,
  Lock,
  Minus,
  Plus,
  Scissors,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

// The Pipeline Builder (#11) — the editable superset of the Provenance canvas: a left→right
// DAG the operator *configures* (selects nodes, edits params/locators, toggles the agent),
// whose sole grounded deliverable is `run_layout.yaml`. It COMPOSES, never executes (the
// primary action is Emit, never Run); the deterministic gate still decides; agents are
// advisory + off the critical path (they carry zero data ports). Data mirrors the handoff
// prototype's contract (source/PipeGuard.dc.html). MVP = configure the pre-seeded germline
// chain + Validate/Emit across three profiles + a link-out View.

type Prof = 'default' | 'giab_panel' | 'sarek'
type Mode = 'edit' | 'view'
type Tab = 'params' | 'locators' | 'io' | 'agents'
type PgStatus = 'ours' | 'full' | 'partial'
type VStatus = 'ok' | 'warn' | 'blocked'

type Port = { kind: string; ref?: boolean }
type Locator = {
  kind: string
  pg: 'path' | 'glob'
  loc: string
  parser: string
  required: boolean
  role: 'output' | 'reference'
  on: string
}
type Io = { name: string; sha: string; size: string; origin: string }
type Tool = {
  id: string
  tool: string
  version: string
  stageLabel: string
  pg: PgStatus
  icon: LucideIcon
  x: number
  y: number
  vstatus: VStatus
  inputs: Port[]
  outputs: Port[]
  params: { k: string; v: string; help: string }[]
  locators: Locator[]
  io: Io[]
}

const PG_BADGE: Record<PgStatus, { label: string; fg: string; bg: string }> = {
  ours: { label: 'ours', fg: '#1f5fd0', bg: '#eaf0fc' },
  full: { label: 'consumes', fg: '#0e8f7e', bg: '#e2f4f0' },
  partial: { label: 'substitute', fg: '#c1560f', bg: '#fceee2' },
}
const V_COLOR: Record<VStatus, string> = { ok: '#1a854e', warn: '#b07714', blocked: '#cf3238' }

const TOOLS: Tool[] = [
  {
    id: 'n_fastp', tool: 'fastp', version: '0.23.4', stageLabel: 'Read QC + trim', pg: 'ours', icon: Scissors,
    x: 40, y: 180, vstatus: 'ok', inputs: [{ kind: 'fastq' }], outputs: [{ kind: 'fastp_json' }, { kind: 'fastq' }],
    params: [
      { k: 'qualified_quality_phred', v: '15', help: 'Per-base quality floor' },
      { k: 'length_required', v: '50', help: 'Min read length after trim' },
      { k: 'detect_adapter_for_pe', v: 'true', help: 'Auto-detect adapters (PE)' },
    ],
    locators: [
      { kind: 'fastp_json', pg: 'path', loc: 'qc/HG002.fastp.json', parser: 'fastp_json', required: true, role: 'output', on: 'error' },
      { kind: 'fastq', pg: 'glob', loc: '*.trim.fastq.gz', parser: 'null', required: true, role: 'output', on: 'all' },
    ],
    io: [
      { name: 'HG002.fastp.json', sha: 'sha256:5f2a…c81', size: '18 KB', origin: 'real-giab' },
      { name: 'HG002.R1.trim.fastq.gz', sha: 'sha256:9b04…7de', size: '1.9 GB', origin: 'real-giab' },
    ],
  },
  {
    id: 'n_bwa', tool: 'bwa-mem2', version: '2.2.1', stageLabel: 'Alignment', pg: 'partial', icon: GitMerge,
    x: 340, y: 180, vstatus: 'ok', inputs: [{ kind: 'fastq' }, { kind: 'reference_fasta', ref: true }], outputs: [{ kind: 'bam' }, { kind: 'bai' }],
    params: [
      { k: 'read_group', v: '@RG\\tID:HG002\\tSM:HG002', help: 'Read-group header' },
      { k: 'sort', v: 'coordinate', help: 'Output sort order' },
    ],
    locators: [{ kind: 'bam', pg: 'glob', loc: 'align/*.md.bam', parser: 'null', required: true, role: 'output', on: 'error' }],
    io: [
      { name: 'HG002.bam', sha: 'sha256:44c9…d10', size: '31 GB', origin: 'real-giab' },
      { name: 'HG002.bam.bai', sha: 'sha256:1e77…4a2', size: '8 MB', origin: 'real-giab' },
    ],
  },
  {
    id: 'n_markdup', tool: 'samtools markdup', version: '1.20', stageLabel: 'Duplicate marking', pg: 'full', icon: Copy,
    x: 640, y: 180, vstatus: 'ok', inputs: [{ kind: 'bam' }], outputs: [{ kind: 'bam' }, { kind: 'markdup_metrics' }, { kind: 'samtools_stats' }],
    params: [{ k: 'remove_duplicates', v: 'false', help: 'Mark, do not drop' }],
    locators: [{ kind: 'markdup_metrics', pg: 'path', loc: 'qc/HG002.markdup.txt', parser: 'markdup_metrics', required: false, role: 'output', on: 'error' }],
    io: [
      { name: 'HG002.md.bam', sha: 'sha256:7a11…4c2', size: '32 GB', origin: 'real-giab' },
      { name: 'HG002.markdup.txt', sha: 'sha256:c93e…08a', size: '2 KB', origin: 'real-giab' },
    ],
  },
  {
    id: 'n_mosdepth', tool: 'mosdepth', version: '0.3.8', stageLabel: 'Coverage', pg: 'ours', icon: BarChart3,
    x: 940, y: 180, vstatus: 'warn', inputs: [{ kind: 'bam' }, { kind: 'panel_bed', ref: true }], outputs: [{ kind: 'mosdepth_summary' }],
    params: [
      { k: 'by', v: 'panel.bed', help: 'Regions to summarise' },
      { k: 'thresholds', v: '1,10,20,30', help: 'Breadth thresholds (x)' },
      { k: 'mapq', v: '20', help: 'Min mapping quality' },
      { k: 'no_per_base', v: 'true', help: 'Summary only' },
    ],
    locators: [{ kind: 'mosdepth_summary', pg: 'path', loc: 'mosdepth/HG002.panel.mosdepth.summary.txt', parser: 'mosdepth_summary', required: true, role: 'output', on: 'error' }],
    io: [{ name: 'HG002.panel.mosdepth.summary.txt', sha: 'sha256:aa71…c09', size: '4 KB', origin: 'real-giab' }],
  },
  {
    id: 'n_call', tool: 'bcftools call', version: '1.20', stageLabel: 'Variant calling', pg: 'partial', icon: Dna,
    x: 1240, y: 180, vstatus: 'ok', inputs: [{ kind: 'bam' }, { kind: 'reference_fasta', ref: true }], outputs: [{ kind: 'vcf' }],
    params: [
      { k: 'min_MQ', v: '20', help: 'mpileup min mapping quality' },
      { k: 'min_BQ', v: '20', help: 'mpileup min base quality' },
      { k: 'variants_only', v: 'true', help: 'Emit variant sites only' },
    ],
    locators: [{ kind: 'vcf', pg: 'glob', loc: 'variants/*.bcftools.vcf.gz', parser: 'vcf', required: false, role: 'output', on: 'error' }],
    io: [{ name: 'HG002.bcftools.vcf.gz', sha: 'sha256:be77…512', size: '128 MB', origin: 'real-giab' }],
  },
  {
    id: 'n_norm', tool: 'bcftools norm', version: '1.20', stageLabel: 'Filter / normalize', pg: 'partial', icon: Filter,
    x: 1540, y: 180, vstatus: 'ok', inputs: [{ kind: 'vcf' }, { kind: 'reference_fasta', ref: true }, { kind: 'panel_bed', ref: true }], outputs: [{ kind: 'filtered_vcf' }],
    params: [
      { k: 'regions_file', v: 'panel.bed', help: 'Restrict to panel' },
      { k: 'norm', v: '-m -both', help: 'Split multiallelics' },
    ],
    locators: [{ kind: 'filtered_vcf', pg: 'glob', loc: 'variants/*.norm.filtered.vcf.gz', parser: 'vcf', required: true, role: 'output', on: 'error' }],
    io: [{ name: 'HG002.norm.filtered.vcf.gz', sha: 'sha256:12ab…9f0', size: '44 MB', origin: 'real-giab' }],
  },
  {
    id: 'n_multiqc', tool: 'MultiQC', version: '1.21', stageLabel: 'QC aggregation', pg: 'full', icon: Layers,
    x: 1840, y: 180, vstatus: 'ok', inputs: [{ kind: 'fastp_json' }, { kind: 'markdup_metrics' }, { kind: 'samtools_stats' }, { kind: 'mosdepth_summary' }], outputs: [{ kind: 'multiqc_json' }],
    params: [{ k: 'force', v: 'true', help: 'Overwrite existing report' }],
    locators: [{ kind: 'multiqc_json', pg: 'path', loc: 'multiqc_data/multiqc_data.json', parser: 'null', required: false, role: 'output', on: 'error' }],
    io: [{ name: 'multiqc_data.json', sha: 'sha256:5be3…9c4', size: '2.1 MB', origin: 'real-giab' }],
  },
]

// Orthogonal elbow edges over the seeded canvas (kept from the prototype's paths).
const EDGES: { d: string; s: string; w: number; dash: string }[] = [
  { d: 'M248 232 L340 232', s: '#c6ced7', w: 1.5, dash: '' },
  { d: 'M548 232 L640 232', s: '#c6ced7', w: 1.5, dash: '' },
  { d: 'M848 232 L940 232', s: '#c6ced7', w: 1.5, dash: '' },
  { d: 'M1448 232 L1540 232', s: '#c6ced7', w: 1.5, dash: '' },
  { d: 'M848 250 L878 250 L878 340 L1218 340 L1218 232 L1240 232', s: '#c6ced7', w: 1.5, dash: '' },
  { d: 'M248 214 L266 214 L266 150 L1822 150 L1822 214 L1840 214', s: '#d3dae1', w: 1.25, dash: '' },
  { d: 'M848 214 L866 214 L866 158 L1814 158 L1814 222 L1840 222', s: '#d3dae1', w: 1.25, dash: '' },
  { d: 'M1148 232 L1166 232 L1166 166 L1806 166 L1806 230 L1840 230', s: '#d3dae1', w: 1.25, dash: '' },
  { d: 'M248 252 L288 252 L288 388 L2082 388 L2082 232 L2100 232', s: '#d3dae1', w: 1.25, dash: '5 4' },
  { d: 'M1148 252 L1188 252 L1188 380 L2074 380 L2074 232 L2100 232', s: '#d3dae1', w: 1.25, dash: '5 4' },
  { d: 'M1748 232 L1788 232 L1788 372 L2066 372 L2066 232 L2100 232', s: '#d3dae1', w: 1.25, dash: '5 4' },
  { d: 'M2260 232 L2300 232', s: '#c6ced7', w: 1.5, dash: '' },
  { d: 'M410 372 L410 322 L444 322 L444 300', s: '#9aa4b0', w: 1, dash: '4 4' },
  { d: 'M1010 372 L1010 322 L1044 322 L1044 300', s: '#9aa4b0', w: 1, dash: '4 4' },
  { d: 'M410 372 L410 352 L1344 352 L1344 300', s: '#9aa4b0', w: 1, dash: '4 4' },
  { d: 'M1010 372 L1010 344 L1644 344 L1644 300', s: '#9aa4b0', w: 1, dash: '4 4' },
]

const REFS = [
  { id: 'r_fasta', label: 'Reference genome', file: 'reference/GRCh38.fa', x: 340 },
  { id: 'r_bed', label: 'Panel BED', file: 'reference/panel.bed', x: 940 },
  { id: 'r_truth', label: 'Truth VCF', file: 'HG002…benchmark.vcf.gz', x: 2300 },
]

const GATE_CHECKPOINTS = [
  { label: 'preflight', c: '#1f6feb' },
  { label: 'qc', c: '#1f5fd0' },
  { label: 'variant', c: '#0e8f7e' },
]

type Sev = 'critical' | 'warn' | 'info'
// Each check carries the node it references so a click can focus the offending node.
const VALIDATION: { code: string; sev: Sev; msg: string; node?: string }[] = [
  { code: 'V4', sev: 'info', msg: 'Gate is terminal, singular, and non-removable — verdict routing is unrepresentable.', node: 'g_gate' },
  { code: 'V5', sev: 'info', msg: 'QC-triage agent is off the critical path (no data ports).', node: 'a_qc_triage' },
  { code: 'V6', sev: 'info', msg: 'Every emitted locator has origin: unknown — config locates, it never relabels provenance.', node: 'n_fastp' },
  { code: 'V3', sev: 'info', msg: 'Gate reachable via ingest — all metric-bearing kinds are produced.', node: 'g_gate' },
]

// Severity → row tint + code-chip, reusing the verdict 4-shade (escalate/hold) + preflight blue.
const SEV_STYLE: Record<Sev, { row: string; chip: string }> = {
  critical: { row: 'border-escalate-bd bg-escalate-bg', chip: 'bg-escalate/15 text-escalate-fg' },
  warn: { row: 'border-hold-bd bg-hold-bg', chip: 'bg-hold/15 text-hold-fg' },
  info: { row: 'border-line bg-card', chip: 'bg-preflight/10 text-preflight' },
}

const YAML: Record<Prof, string> = {
  giab_panel: `schema_version: run_layout/1
profile: giab_panel                  # PIPEGUARD_RUN_LAYOUT=giab_panel
locators:
  # origin is unknown for EVERY locator at emit — compose != execute.
  # guarded origins are stamped only at ingest; config cannot launder provenance.
  fastq:            { glob: "fastq/*_R{1,2}_001.fastq.gz",  parser: null,             required: true,  role: output,    on_multiple: all,   origin: unknown }
  fastp_json:       { path: "qc/HG002.fastp.json",           parser: fastp_json,       required: true,  role: output,    on_multiple: error, origin: unknown }
  bam:              { glob: "align/*.md.bam",                parser: null,             required: true,  role: output,    on_multiple: error, origin: unknown }
  markdup_metrics:  { path: "qc/HG002.markdup.txt",          parser: markdup_metrics,  required: false, role: output,    on_multiple: error, origin: unknown }
  mosdepth_summary: { path: "mosdepth/HG002.summary.txt",    parser: mosdepth_summary, required: true,  role: output,    on_multiple: error, origin: unknown }
  filtered_vcf:     { glob: "variants/*.norm.filtered.vcf.gz", parser: vcf,            required: true,  role: output,    on_multiple: error, origin: unknown }
  multiqc_json:     { path: "multiqc_data/multiqc_data.json", parser: null,            required: false, role: output,    on_multiple: error, origin: unknown }
  reference_fasta:  { path: "reference/GRCh38.fa",           parser: null,             required: true,  role: reference, on_multiple: error, origin: unknown }
  panel_bed:        { path: "reference/panel.bed",           parser: null,             required: true,  role: reference, on_multiple: error, origin: unknown }
  truth_vcf:        { path: "reference/HG002_benchmark.vcf.gz", parser: null,          required: false, role: reference, on_multiple: error, origin: unknown }`,
  default: `schema_version: run_layout/1
profile: default                     # PIPEGUARD_RUN_LAYOUT=default
locators:
  fastp_json:       { path: "qc/{sample}.fastp.json",        parser: fastp_json,       required: true,  role: output,    on_multiple: error, origin: unknown }
  recal_cram:       { glob: "preprocessing/**/*.recal.cram", parser: null,             required: true,  role: output,    on_multiple: error, origin: unknown }
  recal_table:      { glob: "preprocessing/**/*.recal.table",parser: null,             required: false, role: output,    on_multiple: error, origin: unknown }
  mosdepth_summary: { path: "reports/mosdepth/{sample}.summary.txt", parser: mosdepth_summary, required: true, role: output, on_multiple: error, origin: unknown }
  vcf:              { glob: "variant_calling/**/*.vcf.gz",   parser: vcf,              required: true,  role: output,    on_multiple: error, origin: unknown }
  reference_fasta:  { path: "reference/GRCh38.fa",           parser: null,             required: true,  role: reference, on_multiple: error, origin: unknown }
  # default profile shape uses recal_cram — never coerced to bam.`,
  sarek: `# sarek profile — illustrative / target-state (not yet wired end-to-end)
schema_version: run_layout/1
profile: sarek                       # PIPEGUARD_RUN_LAYOUT=sarek
locators:
  fastp_json:       { glob: "**/fastp/*.json",              parser: fastp_json,       required: true,  role: output,    on_multiple: error, origin: unknown }
  recal_cram:       { glob: "preprocessing/recalibrated/**/*.cram", parser: null,      required: true,  role: output,    on_multiple: error, origin: unknown }
  mosdepth_summary: { glob: "reports/mosdepth/**/*.summary.txt", parser: mosdepth_summary, required: true, role: output, on_multiple: error, origin: unknown }
  joint_vcf:        { glob: "variant_calling/haplotypecaller/**/*.vcf.gz", parser: vcf, required: true, role: output, on_multiple: error, origin: unknown }
  reference_fasta:  { path: "igenomes/GRCh38/genome.fasta", parser: null,             required: true,  role: reference, on_multiple: error, origin: unknown }`,
}

const PROFILES: Prof[] = ['default', 'giab_panel', 'sarek']

export function PipelineBuilder() {
  const [mode, setMode] = useState<Mode>('edit')
  const [profile, setProfile] = useState<Prof>('giab_panel')
  const [selected, setSelected] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('params')
  const [paletteOpen, setPaletteOpen] = useState(true)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [emitted, setEmitted] = useState(false)
  const [zoom, setZoom] = useState(1)

  const isView = mode === 'view'
  const selTool = useMemo(() => TOOLS.find((t) => t.id === selected) ?? null, [selected])

  return (
    <div className="-mx-8 -my-7 flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Sub-header toolbar */}
      <div className="flex h-11 shrink-0 items-center gap-3 border-b border-line bg-card px-4">
        <div className="flex overflow-hidden rounded-md border border-line">
          {(['edit', 'view'] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1 text-[12px] font-semibold capitalize ${
                mode === m ? 'bg-card text-text shadow-sm' : 'bg-card-2 text-text-2 hover:text-text'
              }`}
            >
              {m}
            </button>
          ))}
        </div>
        <span className="truncate font-mono text-[11.5px] text-text-2">PIPE-2026-07-08-GERMLINE-PANEL</span>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${
            isView ? 'border-[#cfe0fb] bg-accent-weak text-accent-strong' : 'border-line-strong bg-card-2 text-text-2'
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${isView ? 'bg-accent' : 'bg-text-3'}`} />
          {isView ? 'Linked · RUN-2026-07-07-A' : 'Draft — not run'}
        </span>

        <div className="ml-auto flex items-center gap-3">
          <div className="flex overflow-hidden rounded-md border border-line">
            {PROFILES.map((p) => (
              <button
                key={p}
                onClick={() => setProfile(p)}
                className={`px-2.5 py-1 font-mono text-[11.5px] ${
                  profile === p ? 'bg-card font-semibold text-text shadow-sm' : 'bg-card-2 text-text-2 hover:text-text'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
          <button className="inline-flex cursor-default items-center gap-1.5 rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2" title="Auto-layout arrives in Phase 2">
            <ListChecks size={14} />
            Tidy
          </button>
          <button
            onClick={() => setDrawerOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-line"
          >
            <ShieldCheck size={14} />
            Validate
          </button>
          <button
            onClick={() => {
              setDrawerOpen(true)
              setEmitted(true)
              // Emit COMPOSES — it never executes. Demo build writes the layout to the
              // browser console; a wired backend would hand it to deterministic ingest.
              console.log(`# PIPEGUARD_RUN_LAYOUT=${profile}\n${YAML[profile]}`)
            }}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white shadow-sm transition-opacity hover:opacity-90"
          >
            <Download size={14} />
            Emit
          </button>
        </div>
      </div>

      {/* Three panes */}
      <div className="flex min-h-0 flex-1">
        {paletteOpen ? (
          <Palette onCollapse={() => setPaletteOpen(false)} />
        ) : (
          <button
            onClick={() => setPaletteOpen(true)}
            className="flex w-11 shrink-0 items-start justify-center border-r border-line bg-card pt-4 text-text-3 hover:text-text"
            title="Open palette"
          >
            <Search size={16} />
          </button>
        )}

        <Canvas
          isView={isView}
          selected={selected}
          zoom={zoom}
          onSelect={setSelected}
          onZoom={(z) => setZoom(z)}
        />

        {selected && (
          <Inspector
            tool={selTool}
            isGate={selected === 'g_gate'}
            isAgent={selected === 'a_qc_triage'}
            isView={isView}
            tab={tab}
            onTab={setTab}
            onClose={() => setSelected(null)}
          />
        )}
      </div>

      {/* Validate / Emit console */}
      <Console
        open={drawerOpen}
        onToggle={() => setDrawerOpen((o) => !o)}
        profile={profile}
        emitted={emitted}
        selected={selected}
        onSelect={setSelected}
      />
    </div>
  )
}

function Palette({ onCollapse }: { onCollapse: () => void }) {
  const [query, setQuery] = useState('')
  const sections: { heading: string; items: { name: string; sub: string; icon: LucideIcon; muted?: boolean }[] }[] = [
    {
      heading: 'Tool nodes',
      items: TOOLS.map((t) => ({ name: t.tool, sub: t.outputs.map((o) => o.kind).join(' · '), icon: t.icon })),
    },
    { heading: 'Contamination', items: [{ name: 'NGSCheckMate', sub: 'ngscheckmate · optional', icon: Activity }] },
    {
      heading: 'Agents',
      items: [
        { name: 'QC-triage', sub: 'advisory · MVP', icon: Sparkles },
        { name: 'Pipeline-repair', sub: 'planned', icon: Sparkles, muted: true },
        { name: 'Archivist', sub: 'planned', icon: Sparkles, muted: true },
      ],
    },
    { heading: 'Gate', items: [{ name: 'Decision gate', sub: 'terminal · pinned', icon: ShieldCheck }] },
  ]
  // Live filter on node name or kind — the palette is a picker, not a decoration.
  const q = query.trim().toLowerCase()
  const filtered = q
    ? sections
        .map((s) => ({ ...s, items: s.items.filter((it) => it.name.toLowerCase().includes(q) || it.sub.toLowerCase().includes(q)) }))
        .filter((s) => s.items.length > 0)
    : sections
  return (
    <div className="flex w-60 shrink-0 flex-col border-r border-line bg-card">
      <div className="flex items-center gap-2 p-3">
        <div className="flex flex-1 items-center gap-2 rounded-lg border border-line bg-page px-2.5 py-1.5 focus-within:border-accent">
          <Search size={14} className="shrink-0 text-text-3" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search nodes…"
            className="min-w-0 flex-1 bg-transparent text-[12.5px] text-text placeholder:text-text-3 focus:outline-none"
          />
        </div>
        <button onClick={onCollapse} className="grid h-7 w-7 place-items-center rounded-lg text-text-3 hover:bg-page" title="Collapse">
          <Minus size={15} />
        </button>
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 pb-4">
        {filtered.length === 0 && (
          <p className="px-1 pt-2 text-[11.5px] text-text-3">No nodes match “{query.trim()}”.</p>
        )}
        {filtered.map((s) => (
          <div key={s.heading}>
            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.5px] text-text-3">{s.heading}</p>
            <div className="space-y-1.5">
              {s.items.map((it) => (
                <div
                  key={it.name}
                  className={`flex items-center gap-2.5 rounded-lg border border-line bg-card px-2.5 py-2 ${
                    it.muted ? 'opacity-45' : 'cursor-grab hover:border-line-strong'
                  }`}
                >
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-card-2 text-text-2">
                    <it.icon size={14} />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-[12.5px] font-medium text-text">{it.name}</span>
                    <span className="block truncate font-mono text-[10px] text-text-3">{it.sub}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Canvas({
  isView,
  selected,
  zoom,
  onSelect,
  onZoom,
}: {
  isView: boolean
  selected: string | null
  zoom: number
  onSelect: (id: string | null) => void
  onZoom: (z: number) => void
}) {
  return (
    <div className="relative min-w-0 flex-1 overflow-auto bg-card-2" onClick={() => onSelect(null)}>
      <div
        className="relative"
        style={{
          width: 2560,
          height: 460,
          zoom,
          backgroundImage: 'radial-gradient(#dbe1e8 1px, transparent 1px)',
          backgroundSize: '20px 20px',
          backgroundPosition: '12px 12px',
        }}
      >
        <span className="absolute left-8 top-28 text-[10px] font-semibold uppercase tracking-[0.5px] text-text-3">
          Composed tool nodes
        </span>

        <svg className="pointer-events-none absolute inset-0" width={2560} height={460}>
          {EDGES.map((e, i) => (
            <path key={i} d={e.d} fill="none" stroke={e.s} strokeWidth={e.w} strokeDasharray={e.dash} />
          ))}
        </svg>

        {TOOLS.map((t) => (
          <ToolCard key={t.id} t={t} isView={isView} selected={selected === t.id} onSelect={onSelect} />
        ))}
        {REFS.map((r) => (
          <RefCard key={r.id} r={r} />
        ))}
        <IngestBand />
        <AgentPill selected={selected === 'a_qc_triage'} onSelect={onSelect} />
        <GateCard isView={isView} selected={selected === 'g_gate'} onSelect={onSelect} />
      </div>

      {/* Zoom controls */}
      <div
        className="absolute bottom-4 left-4 flex items-center gap-1 rounded-lg border border-line bg-card px-1 py-1 shadow-card"
        onClick={(e) => e.stopPropagation()}
      >
        <button onClick={() => onZoom(Math.max(0.6, +(zoom - 0.1).toFixed(2)))} className="grid h-7 w-7 place-items-center rounded-md text-text-2 hover:bg-page">
          <Minus size={14} />
        </button>
        <span className="w-10 text-center font-mono text-[11px] text-text-2">{Math.round(zoom * 100)}%</span>
        <button onClick={() => onZoom(Math.min(1.4, +(zoom + 0.1).toFixed(2)))} className="grid h-7 w-7 place-items-center rounded-md text-text-2 hover:bg-page">
          <Plus size={14} />
        </button>
        <button onClick={() => onZoom(1)} className="rounded-md px-2 py-1 text-[11px] text-text-2 hover:bg-page">
          Fit
        </button>
      </div>
    </div>
  )
}

function PortRow({ port, dir, isView }: { port: Port; dir: 'in' | 'out'; isView: boolean }) {
  const dot = port.ref ? (
    <span className="h-[9px] w-[9px] shrink-0 rounded-full border-[1.5px] border-text-3 bg-transparent" />
  ) : (
    <span className="h-[7px] w-[7px] shrink-0 rounded-full bg-text-3" />
  )
  // Pull the port dot out to the card edge (undoing the grid's px-3) so the seeded edge
  // paths — which terminate on each node's left/right border — visibly touch a real port.
  return (
    <div className={`flex items-center gap-1.5 ${dir === 'out' ? '-mr-3 flex-row-reverse' : '-ml-3'}`}>
      {dot}
      <span className={`truncate font-mono text-[10px] ${isView ? 'text-text-2' : 'text-text-3'}`}>{port.kind}</span>
    </div>
  )
}

function ToolCard({ t, isView, selected, onSelect }: { t: Tool; isView: boolean; selected: boolean; onSelect: (id: string) => void }) {
  const badge = PG_BADGE[t.pg]
  const rail = isView ? V_COLOR[t.vstatus] : '#c6ced7'
  const rows = Math.max(t.inputs.length, t.outputs.length)
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onSelect(t.id)
      }}
      className="absolute w-52 overflow-hidden rounded-xl text-left"
      style={{
        left: t.x,
        top: t.y,
        borderLeft: `3px solid ${rail}`,
        background: isView ? 'var(--color-card)' : 'var(--color-card-3)',
        border: selected ? '1px solid var(--color-accent)' : isView ? '1px solid var(--color-line)' : '1px dashed var(--color-line-strong)',
        borderLeftWidth: 3,
        borderLeftColor: rail,
        boxShadow: selected ? '0 0 0 2px var(--color-accent-weak), 0 6px 18px rgba(16,24,40,.13)' : '0 1px 2px rgba(16,24,40,.05)',
      }}
    >
      <div className="flex items-center gap-2 px-3 pt-2.5">
        <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg ${isView ? 'bg-card-2 text-text' : 'bg-card-3 text-text-3'}`}>
          <t.icon size={15} />
        </span>
        <span className="min-w-0 flex-1">
          <span className={`block truncate text-[12.5px] font-semibold ${isView ? 'text-text' : 'text-text-2'}`}>{t.tool}</span>
          <span className="block font-mono text-[10px] text-text-3">{t.version}</span>
        </span>
        <span
          className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide"
          style={{ color: badge.fg, background: badge.bg }}
        >
          {badge.label}
        </span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 px-3">
        <div className="space-y-1">{t.inputs.map((p, i) => <PortRow key={i} port={p} dir="in" isView={isView} />)}</div>
        <div className="space-y-1">{t.outputs.map((p, i) => <PortRow key={i} port={p} dir="out" isView={isView} />)}</div>
      </div>
      <div className="mt-2 flex items-center gap-1.5 px-3 pb-2.5" style={{ minHeight: 4 + rows * 2 }}>
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: isView ? V_COLOR[t.vstatus] : '#8b95a1' }} />
        <span
          className="text-[9.5px] font-bold uppercase tracking-[0.4px]"
          style={{ color: isView ? V_COLOR[t.vstatus] : 'var(--color-text-3)' }}
        >
          {isView ? t.vstatus : 'draft'}
        </span>
      </div>
    </button>
  )
}

function RefCard({ r }: { r: (typeof REFS)[number] }) {
  return (
    <div className="absolute w-[150px] rounded-[10px] border border-line bg-card px-2.5 py-2 shadow-card" style={{ left: r.x, top: 372 }}>
      <div className="flex items-center gap-1.5">
        <Database size={12} className="text-text-3" />
        <span className="truncate text-[11px] font-medium text-text">{r.label}</span>
      </div>
      <p className="mt-0.5 truncate font-mono text-[9.5px] text-text-3">{r.file}</p>
      <p className="mt-0.5 text-[9px] text-text-3">reference · never gated</p>
    </div>
  )
}

function IngestBand() {
  return (
    <div
      className="absolute flex flex-col items-center justify-center gap-1.5 rounded-[10px] border border-dashed border-line-strong bg-card-3 p-3.5 text-center"
      style={{ left: 2100, top: 180, width: 160, height: 150 }}
    >
      <span className="text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">Deterministic ingest</span>
      <p className="font-mono text-[9.5px] leading-snug text-text-3">write_run_dir → run/ (5 CSVs)</p>
    </div>
  )
}

function AgentPill({ selected, onSelect }: { selected: boolean; onSelect: (id: string) => void }) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onSelect('a_qc_triage')
      }}
      className="absolute box-border w-52 rounded-2xl border-[1.5px] border-dashed border-accent bg-accent-weak px-3 py-2 text-left"
      style={{ left: 2300, top: 92, boxShadow: selected ? '0 0 0 2px var(--color-accent-weak), 0 5px 14px rgba(31,95,208,.2)' : 'none' }}
    >
      <div className="flex items-center gap-1.5">
        <Activity size={13} className="text-accent-strong" />
        <span className="text-[9px] font-bold uppercase tracking-[0.5px] text-accent-strong">Advisory</span>
        <span className="ml-auto flex items-center gap-1 text-[10px] text-text-2">
          <span className="h-[7px] w-[7px] rounded-full bg-text-3" />
          stub
        </span>
      </div>
      <p className="mt-1 text-[12px] font-semibold text-text">QC-triage</p>
      <p className="font-mono text-[9.5px] text-text-3">observes qc checkpoint · no ports</p>
    </button>
  )
}

function GateCard({ isView, selected, onSelect }: { isView: boolean; selected: boolean; onSelect: (id: string) => void }) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onSelect('g_gate')
      }}
      className="absolute w-52 overflow-hidden rounded-xl text-left"
      style={{
        left: 2300,
        top: 180,
        minHeight: 96,
        background: 'var(--color-card)',
        border: selected ? '1px solid var(--color-accent)' : '1.5px solid var(--color-line-strong)',
        borderLeft: `3px solid ${isView ? 'var(--color-escalate)' : '#c6ced7'}`,
        boxShadow: selected ? '0 0 0 2px var(--color-accent-weak), 0 8px 22px rgba(16,24,40,.16)' : '0 3px 12px rgba(16,24,40,.09)',
      }}
    >
      <div className="flex items-center gap-2 px-3 pt-2.5">
        <ShieldCheck size={15} className="text-text-2" />
        <span className="flex-1 text-[12.5px] font-semibold text-text">Decision gate</span>
        <Lock size={13} className="text-text-3" />
      </div>
      <div className="mt-2 flex flex-wrap gap-1 px-3">
        {GATE_CHECKPOINTS.map((c) => (
          <span key={c.label} className="inline-flex items-center gap-1 rounded border border-line px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide" style={{ color: c.c }}>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: c.c }} />
            {c.label}
          </span>
        ))}
      </div>
      <p className="mt-2 px-3 pb-2.5 text-[9.5px] font-bold uppercase tracking-[0.4px] text-text-3">
        {isView ? 'proceed 3 · hold 1 · escalate 1' : 'pending — no verdict'}
      </p>
    </button>
  )
}

function Inspector({
  tool,
  isGate,
  isAgent,
  isView,
  tab,
  onTab,
  onClose,
}: {
  tool: Tool | null
  isGate: boolean
  isAgent: boolean
  isView: boolean
  tab: Tab
  onTab: (t: Tab) => void
  onClose: () => void
}) {
  // Controlled param edits, keyed by `${tool}:${param}` so switching nodes keeps prior edits.
  // Display-only vs the emitted YAML (compose != execute), but no longer uncontrolled.
  const [paramEdits, setParamEdits] = useState<Record<string, string>>({})
  const title = isGate ? 'Decision gate' : isAgent ? 'QC-triage agent' : tool?.tool ?? ''
  const sub = isGate ? 'terminal · runbook-read-only' : isAgent ? 'advisory · off critical path' : tool?.stageLabel ?? ''
  return (
    <div className="flex w-[360px] shrink-0 flex-col border-l border-line bg-card">
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-semibold text-text">{title}</p>
          <p className="truncate text-[11.5px] text-text-3">{sub}</p>
        </div>
        <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-lg text-text-3 hover:bg-page">
          <X size={15} />
        </button>
      </div>

      {isGate ? (
        <div className="space-y-3 p-4 text-[12.5px] text-text-2">
          <p>The gate reads the frozen five <code className="font-mono text-[11px]">run/</code> CSVs and decides deterministically. Thresholds are read-only here.</p>
          <div className="rounded-lg border border-hold-bd bg-hold-bg px-3 py-2 text-[11.5px] text-hold-fg">
            No threshold or verdict control lives on the canvas — the runbook decides.
          </div>
          <Link to="/settings" className="inline-flex text-[12.5px] font-medium text-accent hover:underline">
            Open runbook in Settings →
          </Link>
        </div>
      ) : isAgent ? (
        <div className="space-y-3 p-4 text-[12.5px] text-text-2">
          <Row label="attachTo" value="g_gate" />
          <Row label="scope" value="qc" />
          <Row label="mode" value="stub" />
          <Row label="tier" value="advisory" />
          <div className="rounded-lg border border-line bg-card-2/50 px-3 py-2 text-[11.5px] text-text-3">
            The agent has no data ports — it can never set or route a verdict. Toggling stub ⇄ claude never changes graph validity.
          </div>
        </div>
      ) : tool ? (
        <>
          <div className="flex gap-1 border-b border-line px-3 pt-2">
            {(['params', 'locators', 'io', 'agents'] as Tab[]).map((tb) => (
              <button
                key={tb}
                onClick={() => onTab(tb)}
                className={`rounded-t-md px-3 py-1.5 text-[12px] font-medium capitalize ${
                  tab === tb ? 'border-b-2 border-accent text-text' : 'text-text-3 hover:text-text'
                }`}
              >
                {tb === 'io' ? 'I/O' : tb}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {tab === 'params' && (
              <div className="space-y-3">
                {tool.params.map((p) => {
                  const key = `${tool.id}:${p.k}`
                  return (
                    <div key={p.k}>
                      <label className="mb-1 block font-mono text-[11px] text-text-2">{p.k}</label>
                      <input
                        value={paramEdits[key] ?? p.v}
                        onChange={(e) => setParamEdits((m) => ({ ...m, [key]: e.target.value }))}
                        readOnly={isView}
                        className="w-full rounded-lg border border-line bg-card-2 px-2.5 py-1.5 font-mono text-[12px] text-text focus:border-accent focus:outline-none"
                      />
                      <p className="mt-0.5 text-[10.5px] text-text-3">{p.help}</p>
                    </div>
                  )
                })}
              </div>
            )}
            {tab === 'locators' && (
              <div className="space-y-3">
                {tool.locators.map((l) => (
                  <div key={l.kind} className="rounded-lg border border-line p-3">
                    <p className="mb-1.5 font-mono text-[11px] font-semibold text-text">{l.kind}</p>
                    <div className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 font-mono text-[11px]">
                      <span className="text-text-3">{l.pg}</span>
                      <span className="truncate text-text">{l.loc}</span>
                      <span className="text-text-3">parser</span>
                      <span className="text-text-2">{l.parser}</span>
                      <span className="text-text-3">required</span>
                      <span className="text-text-2">{String(l.required)}</span>
                      <span className="text-text-3">role</span>
                      <span className="text-text-2">{l.role}</span>
                      <span className="text-text-3">on_multiple</span>
                      <span className="text-text-2">{l.on}</span>
                      <span className="text-text-3">origin</span>
                      <span className="text-text-3">unknown 🔒</span>
                    </div>
                  </div>
                ))}
                <p className="text-[10.5px] text-text-3">
                  Config locates inputs; it cannot relabel provenance. Origin is stamped at ingest from the run's marker.
                </p>
              </div>
            )}
            {tab === 'io' && (
              <div className="space-y-2">
                {tool.io.map((o) => (
                  <div key={o.name} className="rounded-lg border border-line bg-card-2/40 px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-[11.5px] text-text">{o.name}</span>
                      <span className="shrink-0 rounded border border-preflight/30 bg-preflight/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-preflight">
                        {isView ? o.origin : 'draft'}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-3 font-mono text-[10px] text-text-3">
                      <span className="text-accent">{isView ? o.sha : 'sha256: —'}</span>
                      <span>{isView ? o.size : '—'}</span>
                    </div>
                  </div>
                ))}
                {!isView && <p className="text-[10.5px] text-text-3">Placeholders in draft — filled from the ledger in linked View.</p>}
              </div>
            )}
            {tab === 'agents' && (
              <div className="space-y-3 text-[12.5px] text-text-2">
                <div className="flex items-center justify-between rounded-lg border border-line px-3 py-2">
                  <span>QC-triage on this checkpoint</span>
                  <span className="font-mono text-[11px] text-text-3">stub</span>
                </div>
                <p className="text-[10.5px] text-text-3">Advisory only ($0 stub default). Snapping an agent never adds a data edge.</p>
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[11px] text-text-3">{label}</span>
      <span className="font-mono text-[12px] text-text">{value}</span>
    </div>
  )
}

function Console({
  open,
  onToggle,
  profile,
  emitted,
  selected,
  onSelect,
}: {
  open: boolean
  onToggle: () => void
  profile: Prof
  emitted: boolean
  selected: string | null
  onSelect: (id: string) => void
}) {
  const [copied, setCopied] = useState(false)
  const yaml = YAML[profile]

  const onCopy = () => {
    navigator.clipboard
      ?.writeText(yaml)
      .then(() => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      })
      .catch(() => {})
  }

  const onDownload = () => {
    const blob = new Blob([yaml], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'run_layout.yaml'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="shrink-0 border-t border-line bg-card">
      <button onClick={onToggle} className="flex h-9 w-full items-center gap-2 px-4 text-left">
        <ShieldCheck size={14} className="text-proceed-fg" />
        <span className="text-[12.5px] font-medium text-text">Validate &amp; emit console</span>
        <span className="rounded-full border border-proceed-bd bg-proceed-bg px-2 py-0.5 text-[10.5px] font-medium text-proceed-fg">
          {emitted ? 'Emitted' : 'Ready to emit'}
        </span>
        <span className="ml-auto font-mono text-[11px] text-text-3">PIPEGUARD_RUN_LAYOUT={profile}</span>
      </button>
      {open && (
        <div className="grid h-[240px] grid-cols-[minmax(0,340px),1fr] gap-4 border-t border-line px-4 py-3">
          <div className="min-h-0 overflow-y-auto">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.5px] text-text-3">Validation</p>
            <div className="space-y-1.5">
              {VALIDATION.map((v) => {
                const st = SEV_STYLE[v.sev]
                const active = v.node != null && v.node === selected
                const inner = (
                  <>
                    <span className={`shrink-0 rounded px-1 py-0.5 font-mono text-[10px] font-bold ${st.chip}`}>{v.code}</span>
                    <span className="text-[11.5px] text-text-2">{v.msg}</span>
                  </>
                )
                // A check with a node is click-to-focus: selecting it opens the inspector on the node.
                return v.node ? (
                  <button
                    key={v.code}
                    onClick={() => onSelect(v.node!)}
                    title="Focus the referenced node"
                    className={`flex w-full items-start gap-2 rounded-lg border px-2.5 py-2 text-left transition-colors hover:border-line-strong ${st.row} ${
                      active ? 'ring-1 ring-accent' : ''
                    }`}
                  >
                    {inner}
                  </button>
                ) : (
                  <div key={v.code} className={`flex items-start gap-2 rounded-lg border px-2.5 py-2 ${st.row}`}>
                    {inner}
                  </div>
                )
              })}
            </div>
          </div>
          <div className="flex min-h-0 flex-col">
            <div className="mb-2 flex items-center gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.5px] text-text-3">run_layout.yaml</p>
              <span className="ml-auto flex gap-2">
                <button
                  onClick={onCopy}
                  className="inline-flex items-center gap-1 rounded border border-line px-2 py-0.5 text-[11px] text-text-2 transition-colors hover:border-line-strong hover:text-text"
                >
                  <Copy size={12} /> {copied ? 'Copied' : 'Copy'}
                </button>
                <button
                  onClick={onDownload}
                  className="inline-flex items-center gap-1 rounded border border-line px-2 py-0.5 text-[11px] text-text-2 transition-colors hover:border-line-strong hover:text-text"
                >
                  <Download size={12} /> Download
                </button>
              </span>
            </div>
            {emitted && (
              <div className="mb-2 flex items-start gap-1.5 rounded-md border border-proceed-bd bg-proceed-bg px-2.5 py-1.5 text-[11px] text-proceed-fg">
                <ShieldCheck size={13} className="mt-0.5 shrink-0" />
                <span>
                  Emitted <span className="font-mono">PIPEGUARD_RUN_LAYOUT={profile}</span> → <span className="font-mono">run_layout.yaml</span>. Demo build logs it
                  to the browser console; compose never executes.
                </span>
              </div>
            )}
            <pre className="min-h-0 flex-1 overflow-auto rounded-lg border border-line bg-card-2/50 p-3 font-mono text-[10.5px] leading-relaxed text-text">
              {yaml}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
