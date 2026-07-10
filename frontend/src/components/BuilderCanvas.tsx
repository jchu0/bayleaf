import { useEffect, useRef } from 'react'
import { Activity, Cable, Lock, Minus, Plus, Wand2 } from 'lucide-react'
import {
  GATE_CHECKPOINTS,
  ICONS,
  PG_BADGE,
  REFS,
  TOOLS,
  V_COLOR,
  gateSegs,
  type Mode,
  type Port,
  type Tool,
  type UserEdge,
  type UserNode,
} from './BuilderShared'

// The builder canvas: the seeded germline DAG + reference cards + terminal gate + advisory
// agent pill + deterministic-ingest band, plus the free-composition layer (user nodes, elbow
// edges), a minimap, Connect/Tidy action cluster, and floating zoom. Pannable in any direction;
// centers on the pipeline on mount. Compose ≠ execute: nothing here runs a tool.

const INNER_W = 2560
const INNER_H = 460
const MM_W = 210 // minimap width
const MM_H = 108 // minimap height — a bigger, squarer canvas mirror than the old 168×46 strip
const MM_SCALE = MM_W / INNER_W // uniform proportional scale (no x/y distortion)
const MM_VPAD = (MM_H - INNER_H * MM_SCALE) / 2 // vertically center the canvas strip in the box
const ZMIN = 0.6
const ZMAX = 1.4
const clampZoom = (z: number): number => Math.min(ZMAX, Math.max(ZMIN, +z.toFixed(2)))
const UW = 168 // user-node width — port anchors depend on it
const UPT = 52 // user-node first-port y-offset from card top
const UROW = 18 // user-node port-row pitch
const TW = 208 // seeded ToolCard width (w-52) — output dots sit at its right edge
const TPT = 56 // seeded ToolCard first-port y-offset from card top (header + grid start)
const TROW = 18 // seeded ToolCard port-row pitch

// The seeded germline wiring [fromNode, outKind, toNode, inKind], typed so the computed edges
// attach output→input by KIND (kept in lockstep with the corrected TOOLS ports). Mirrors
// germlineTemplate's tool→tool chain (fastp → bwa → markdup → {mosdepth, call → norm} + MultiQC fan-in).
const SEEDED_WIRES: [string, string, string, string][] = [
  ['n_fastp', 'fastq', 'n_bwa', 'fastq'],
  ['n_bwa', 'bam', 'n_markdup', 'bam'],
  ['n_markdup', 'bam', 'n_mosdepth', 'bam'],
  ['n_markdup', 'bam', 'n_call', 'bam'],
  ['n_call', 'vcf', 'n_norm', 'vcf'],
  ['n_fastp', 'fastp_json', 'n_multiqc', 'fastp_json'],
  ['n_markdup', 'markdup_metrics', 'n_multiqc', 'markdup_metrics'],
  ['n_mosdepth', 'mosdepth_summary', 'n_multiqc', 'mosdepth_summary'],
]
// Reference-card → tool ref-input wiring [refId, toolNode, inKind]: fasta feeds bwa/call/norm, the
// panel BED feeds mosdepth (--by) + bcftools call (mpileup -R).
const REF_WIRES: [string, string, string][] = [
  ['r_fasta', 'n_bwa', 'reference_fasta'],
  ['r_fasta', 'n_call', 'reference_fasta'],
  ['r_fasta', 'n_norm', 'reference_fasta'],
  ['r_bed', 'n_mosdepth', 'panel_bed'],
  ['r_bed', 'n_call', 'panel_bed'],
]

type CanvasProps = {
  mode: Mode
  // false for a blank/new pipeline: render only the terminal gate + ingest band + user nodes,
  // not the hardcoded seeded germline chain (so a "New → Blank" canvas is actually empty).
  showSeeded: boolean
  selected: string | null
  zoom: number
  userNodes: UserNode[]
  userEdges: UserEdge[]
  connectMode: boolean
  connectFrom: string | null
  onSelect: (id: string | null) => void
  onZoom: (z: number) => void
  onToggleConnect: () => void
  onTidy: () => void
  onNodeDrag: (id: string, e: React.MouseEvent) => void
  onPortTap: (id: string, side: 'in' | 'out', idx: number) => void
  onRemoveNode: (id: string, e: React.MouseEvent) => void
}

export function BuilderCanvas(props: CanvasProps) {
  const { mode, showSeeded, selected, zoom, userNodes, userEdges, connectMode, connectFrom } = props
  const isView = mode === 'view'
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const centered = useRef(false)

  // Center the viewport on the pipeline once on mount (README §6: "loads centered").
  useEffect(() => {
    const el = scrollRef.current
    if (!el || centered.current) return
    centered.current = true
    requestAnimationFrame(() => {
      el.scrollLeft = Math.max(0, 1685 - el.clientWidth / 2)
      el.scrollTop = Math.max(0, 713 - el.clientHeight / 2)
    })
  }, [])

  // Trackpad / mouse zoom: a ctrl-wheel (what a trackpad pinch and Ctrl+scroll both emit) zooms the
  // canvas instead of zooming the whole page. Attached natively with { passive: false } because
  // React's synthetic onWheel is passive and can't preventDefault. Plain wheel keeps panning.
  const zoomRef = useRef(zoom)
  zoomRef.current = zoom
  const onZoomRef = useRef(props.onZoom)
  onZoomRef.current = props.onZoom
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return
      e.preventDefault()
      onZoomRef.current(clampZoom(zoomRef.current + (e.deltaY > 0 ? -0.1 : 0.1)))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  // Fit: reset zoom + scroll so the pipeline is centered — the seeded DAG, or the user nodes' bbox
  // when composing a draft. Content coords include the 360/480 margin the inner div carries.
  const fitToDag = () => {
    props.onZoom(1)
    const el = scrollRef.current
    if (!el) return
    let tx = 1685
    let ty = 713
    if (userNodes.length) {
      const xs = userNodes.map((n) => n.x)
      const ys = userNodes.map((n) => n.y)
      tx = 360 + (Math.min(...xs) + Math.max(...xs) + UW) / 2
      ty = 480 + (Math.min(...ys) + Math.max(...ys)) / 2 + 40
    }
    requestAnimationFrame(() => {
      el.scrollLeft = Math.max(0, tx - el.clientWidth / 2)
      el.scrollTop = Math.max(0, ty - el.clientHeight / 2)
    })
  }

  const segs = gateSegs()

  // User-edge geometry: anchor to the exact port dots (out = right edge, in = left edge).
  const anchor = (id: string, side: 'out' | 'in', idx: number): { x: number; y: number } | null => {
    const n = userNodes.find((u) => u.id === id)
    if (!n) return null
    return { x: n.x + (side === 'out' ? UW : 0), y: n.y + UPT + idx * UROW }
  }
  const edgePaths = userEdges
    .map((ed) => {
      const a = anchor(ed.from.node, 'out', ed.from.idx)
      const b = anchor(ed.to.node, 'in', ed.to.idx)
      if (!a || !b) return null
      const mx = Math.round((a.x + b.x) / 2)
      return `M${a.x} ${a.y} H${mx} V${b.y} H${b.x}`
    })
    .filter((d): d is string => d != null)

  // Seeded-DAG edges, COMPUTED from the tool/ref card geometry + typed ports (not the old hardcoded
  // SVG paths, which detached from the ports whenever a card's port count changed — the "broken
  // lines" report). Anchors mirror the user-edge scheme: an output dot sits at the card's right
  // edge, an input dot at its left, at TPT + idx·TROW down from the card top.
  const toolAnchor = (id: string, side: 'out' | 'in', kind: string): { x: number; y: number } | null => {
    const t = TOOLS.find((x) => x.id === id)
    if (!t) return null
    const ports = side === 'out' ? t.outputs : t.inputs
    const idx = Math.max(0, ports.findIndex((p) => p.kind === kind))
    return { x: t.x + (side === 'out' ? TW : 0), y: t.y + TPT + idx * TROW }
  }
  const seededPaths = SEEDED_WIRES.map(([fid, fk, tid, tk]) => {
    const a = toolAnchor(fid, 'out', fk)
    const b = toolAnchor(tid, 'in', tk)
    if (!a || !b) return null
    const mx = Math.round((a.x + b.x) / 2)
    return `M${a.x} ${a.y} H${mx} V${b.y} H${b.x}`
  }).filter((d): d is string => d != null)
  // Reference cards sit BELOW the spine (y≈372); their edges rise into a tool's ref input.
  const refPaths = REF_WIRES.map(([rid, tid, tk]) => {
    const r = REFS.find((x) => x.id === rid)
    const b = toolAnchor(tid, 'in', tk)
    if (!r || !b) return null
    const ax = r.x + 75 // ref card horizontal center (card is 150 wide)
    return `M${ax} 372 V${Math.round((372 + b.y) / 2)} H${b.x} V${b.y}`
  }).filter((d): d is string => d != null)


  return (
    <div className="relative min-w-0 flex-1">
      <div
        ref={scrollRef}
        className="absolute inset-0 overflow-auto bg-card-2"
        onClick={() => props.onSelect(null)}
      >
        <div
          className="relative"
          style={{
            width: INNER_W,
            height: INNER_H,
            margin: '480px 360px',
            zoom,
            backgroundImage: 'radial-gradient(#dbe1e8 1px, transparent 1px)',
            backgroundSize: '20px 20px',
            backgroundPosition: '12px 12px',
          }}
        >
          <svg className="pointer-events-none absolute left-0 top-0 overflow-visible" width={INNER_W} height={INNER_H}>
            {showSeeded &&
              seededPaths.map((d, i) => (
                <path key={`s${i}`} d={d} fill="none" stroke="#c6ced7" strokeWidth={1.5} />
              ))}
            {showSeeded &&
              refPaths.map((d, i) => (
                <path key={`r${i}`} d={d} fill="none" stroke="#d3dae1" strokeWidth={1.25} strokeDasharray="5 4" />
              ))}
            {edgePaths.map((d, i) => (
              <path key={`u${i}`} d={d} fill="none" stroke="var(--color-accent)" strokeWidth={1.8} />
            ))}
          </svg>

          <span className="absolute left-10 top-[140px] text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">
            Composed tool nodes
          </span>

          <IngestBand />

          {showSeeded &&
            TOOLS.map((t) => (
              <ToolCard key={t.id} t={t} isView={isView} selected={selected === t.id} onSelect={props.onSelect} />
            ))}
          {showSeeded &&
            REFS.map((r) => (
              <RefCard key={r.id} r={r} selected={selected === r.id} onSelect={props.onSelect} />
            ))}
          <GateCard isView={isView} selected={selected === 'g_gate'} segs={segs} onSelect={props.onSelect} />
          {showSeeded && <AgentPill selected={selected === 'a_qc_triage'} onSelect={props.onSelect} />}

          {userNodes.map((n) => (
            <UserCard
              key={n.id}
              n={n}
              connectMode={connectMode}
              connectFrom={connectFrom}
              onDown={props.onNodeDrag}
              onPortTap={props.onPortTap}
              onRemove={props.onRemoveNode}
            />
          ))}
        </div>
      </div>

      {/* Canvas action cluster (Edit): Connect + Tidy (auto-layout) */}
      {!isView && (
        <div className="absolute left-3.5 top-3.5 z-[6] flex gap-1.5">
          <button
            onClick={props.onToggleConnect}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11.5px] font-medium ${
              connectMode ? 'border-accent bg-accent text-white' : 'border-line-strong bg-card text-text-2'
            }`}
          >
            <Cable size={14} />
            Connect
          </button>
          <button
            onClick={props.onTidy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[11.5px] font-medium text-text-2 hover:border-line"
          >
            <Wand2 size={14} />
            Tidy
          </button>
        </div>
      )}

      {/* Connect-mode banner */}
      {connectMode && (
        <div className="absolute left-1/2 top-3.5 z-[7] -translate-x-1/2 rounded-full bg-accent-strong px-3.5 py-1.5 text-[11.5px] font-medium text-white shadow-pop">
          {connectFrom ? 'Click a target node to draw the edge' : 'Connect mode — click a source node, then its target'}
        </div>
      )}

      {/* Minimap — a bigger, proportional mirror of the whole canvas (uniform scale, no distortion):
          seeded tool cards + references + the terminal gate + any composed nodes, each to scale. */}
      <div
        className="absolute bottom-3.5 right-3.5 z-[6] overflow-hidden rounded-lg border border-line-strong bg-card shadow-card"
        style={{ width: MM_W, height: MM_H }}
      >
        <div className="absolute inset-0 bg-card-2" />
        {showSeeded &&
          TOOLS.map((t) => (
            <span
              key={t.id}
              className="absolute rounded-[1px] bg-line-strong"
              style={{ left: t.x * MM_SCALE, top: MM_VPAD + t.y * MM_SCALE, width: TW * MM_SCALE, height: 62 * MM_SCALE }}
            />
          ))}
        {showSeeded &&
          REFS.map((r) => (
            <span
              key={r.id}
              className="absolute rounded-[1px] bg-line"
              style={{ left: r.x * MM_SCALE, top: MM_VPAD + 372 * MM_SCALE, width: 150 * MM_SCALE, height: 40 * MM_SCALE }}
            />
          ))}
        {/* terminal gate */}
        <span
          className="absolute rounded-[1px] bg-text-3"
          style={{ left: 2100 * MM_SCALE, top: MM_VPAD + 196 * MM_SCALE, width: Math.max(4, 120 * MM_SCALE), height: 64 * MM_SCALE }}
        />
        {userNodes.map((n) => (
          <span
            key={n.id}
            className="absolute rounded-[1px] bg-accent"
            style={{ left: n.x * MM_SCALE, top: MM_VPAD + n.y * MM_SCALE, width: UW * MM_SCALE, height: 46 * MM_SCALE }}
          />
        ))}
      </div>

      {/* Zoom controls */}
      <div className="absolute bottom-3.5 left-3.5 z-[6] flex items-center gap-0.5 rounded-lg border border-line-strong bg-card p-1 shadow-card">
        <button
          onClick={() => props.onZoom(clampZoom(zoom - 0.1))}
          className="grid h-7 w-7 place-items-center rounded-md text-text-2 hover:bg-page"
        >
          <Minus size={15} />
        </button>
        <span className="min-w-[38px] text-center font-mono text-[11px] text-text-2">{Math.round(zoom * 100)}%</span>
        <button
          onClick={() => props.onZoom(clampZoom(zoom + 0.1))}
          className="grid h-7 w-7 place-items-center rounded-md text-text-2 hover:bg-page"
        >
          <Plus size={15} />
        </button>
        <div className="mx-0.5 h-[18px] w-px bg-line" />
        <button onClick={fitToDag} title="Fit — center the pipeline" className="rounded-md px-2 py-1 text-[11px] font-medium text-text-2 hover:bg-page">
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
  // Per-side borders (not the `border` shorthand) so the 3px colored left spine can coexist
  // with the other sides without React's shorthand/longhand conflict warning.
  const cardBorder = selected
    ? '1px solid var(--color-accent)'
    : isView
      ? '1px solid var(--color-line)'
      : '1px dashed var(--color-line-strong)'
  const rows = Math.max(t.inputs.length, t.outputs.length)
  const Icon = ICONS[t.icon]
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
        background: isView ? 'var(--color-card)' : 'var(--color-card-3)',
        borderTop: cardBorder,
        borderRight: cardBorder,
        borderBottom: cardBorder,
        borderLeft: `3px ${isView || selected ? 'solid' : 'dashed'} ${rail}`,
        boxShadow: selected ? '0 0 0 2px var(--color-accent-weak), 0 6px 18px rgba(16,24,40,.13)' : '0 1px 2px rgba(16,24,40,.05)',
      }}
    >
      <div className="flex items-center gap-2 px-3 pt-2.5">
        <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg ${isView ? 'bg-card-2 text-text' : 'bg-card-3 text-text-3'}`}>
          <Icon size={15} />
        </span>
        <span className="min-w-0 flex-1">
          <span className={`block truncate text-[12.5px] font-semibold ${isView ? 'text-text' : 'text-text-2'}`}>{t.tool}</span>
          <span className="block font-mono text-[10px] text-text-3">{t.version}</span>
        </span>
        <span className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide" style={{ color: badge.fg, background: badge.bg }}>
          {badge.label}
        </span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 px-3">
        <div className="space-y-1">{t.inputs.map((p, i) => <PortRow key={i} port={p} dir="in" isView={isView} />)}</div>
        <div className="space-y-1">{t.outputs.map((p, i) => <PortRow key={i} port={p} dir="out" isView={isView} />)}</div>
      </div>
      <div className="mt-2 flex items-center gap-1.5 px-3 pb-2.5" style={{ minHeight: 4 + rows * 2 }}>
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: isView ? V_COLOR[t.vstatus] : '#8b95a1' }} />
        <span className="text-[9.5px] font-bold uppercase tracking-[0.4px]" style={{ color: isView ? V_COLOR[t.vstatus] : 'var(--color-text-3)' }}>
          {isView ? t.vstatus : 'draft'}
        </span>
      </div>
    </button>
  )
}

function RefCard({ r, selected, onSelect }: { r: (typeof REFS)[number]; selected: boolean; onSelect: (id: string) => void }) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onSelect(r.id)
      }}
      className="absolute w-[150px] rounded-[10px] px-2.5 py-2 text-left"
      style={{
        left: r.x,
        top: 372,
        background: 'var(--color-card)',
        borderTop: selected ? '1px solid var(--color-accent)' : '1px solid var(--color-line)',
        borderRight: selected ? '1px solid var(--color-accent)' : '1px solid var(--color-line)',
        borderBottom: selected ? '1px solid var(--color-accent)' : '1px solid var(--color-line)',
        borderLeft: `3px solid ${selected ? 'var(--color-accent)' : '#c6ced7'}`,
        boxShadow: selected ? '0 0 0 3px var(--color-accent-weak), 0 2px 8px rgba(16,24,40,.1)' : '0 1px 2px rgba(16,24,40,.04)',
      }}
    >
      <div className="flex items-center gap-1.5">
        <span className="h-[9px] w-[9px] shrink-0 rounded-full border-[1.5px] border-text-3" />
        <span className="truncate text-[11px] font-medium text-text-2">{r.label}</span>
      </div>
      <p className="mt-0.5 truncate font-mono text-[9.5px] text-text-3">{r.file}</p>
      <p className="mt-0.5 text-[9px] italic text-text-3">reference · never gated</p>
    </button>
  )
}

function IngestBand() {
  return (
    <div
      className="absolute flex flex-col items-center justify-center gap-1.5 rounded-[10px] border border-dashed border-line-strong bg-card-3 p-3.5 text-center"
      style={{ left: 2100, top: 180, width: 160, height: 150 }}
    >
      <span className="text-[10px] font-bold uppercase tracking-[0.3px] text-text-2">Deterministic ingest</span>
      <p className="font-mono text-[9.5px] leading-snug text-text-3">
        write_run_dir
        <br />→ run/ (5 CSVs)
      </p>
      <p className="text-[9px] italic text-text-3">non-composable</p>
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
      <div className="text-[8.5px] font-bold uppercase tracking-[0.5px] text-accent-strong">Advisory</div>
      <div className="mt-0.5 flex items-center gap-1.5">
        <Activity size={13} className="text-accent-strong" />
        <span className="flex-1 text-[12px] font-semibold text-accent-strong">QC-triage</span>
        <span className="h-[7px] w-[7px] rounded-full bg-text-3" />
        <span className="font-mono text-[9.5px] text-text-2">stub</span>
      </div>
      <p className="mt-0.5 text-[9.5px] text-text-2">
        observes <span className="font-mono">qc</span> · no data ports
      </p>
    </button>
  )
}

function GateCard({
  isView,
  selected,
  segs,
  onSelect,
}: {
  isView: boolean
  selected: boolean
  segs: { c: string; w: string }[]
  onSelect: (id: string) => void
}) {
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
        background: 'var(--color-card)',
        borderTop: selected ? '1px solid var(--color-accent)' : '1.5px solid var(--color-line-strong)',
        borderRight: selected ? '1px solid var(--color-accent)' : '1.5px solid var(--color-line-strong)',
        borderBottom: selected ? '1px solid var(--color-accent)' : '1.5px solid var(--color-line-strong)',
        borderLeft: `3px solid ${isView ? 'var(--color-escalate)' : '#c6ced7'}`,
        boxShadow: selected ? '0 0 0 2px var(--color-accent-weak), 0 8px 22px rgba(16,24,40,.16)' : '0 3px 12px rgba(16,24,40,.09)',
      }}
    >
      <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-card-2 text-text-2">
          <ShieldCheckSmall />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[12px] font-bold text-text">Decision gate</span>
          <span className="block font-mono text-[9.5px] text-text-3">terminal · reads run/</span>
        </span>
        <Lock size={13} className="shrink-0 text-text-3" aria-label="non-removable" />

      </div>
      <div className="flex flex-col gap-1.5 px-3 py-2.5">
        {GATE_CHECKPOINTS.map((c) => (
          <div key={c.label} className="flex items-center gap-1.5">
            <span className="h-[7px] w-[7px] rounded-full" style={{ background: c.c }} />
            <span className="text-[11px] font-medium text-text-2">{c.label}</span>
          </div>
        ))}
      </div>
      <div className="border-t border-line bg-card-2 px-3 py-2">
        {isView && (
          <div className="mb-1.5 flex h-[7px] overflow-hidden rounded bg-card-3">
            {segs.map((s, i) => (
              <div key={i} style={{ width: s.w, background: s.c }} />
            ))}
          </div>
        )}
        <div className="text-[10px] font-semibold uppercase tracking-[0.3px] text-text-2">
          {isView ? 'proceed 3 · hold 1 · escalate 1' : 'pending — no verdict'}
        </div>
      </div>
    </button>
  )
}

// Shield-check glyph matching the gate icon (kept local so the card header can size it tightly).
function ShieldCheckSmall() {
  return (
    <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  )
}

// User-composed node: identical language to the seeded cards, but draggable + wireable. Ports
// become full connect-circles in Connect mode; the armed source port fills accent.
function UserCard({
  n,
  connectMode,
  connectFrom,
  onDown,
  onPortTap,
  onRemove,
}: {
  n: UserNode
  connectMode: boolean
  connectFrom: string | null
  onDown: (id: string, e: React.MouseEvent) => void
  onPortTap: (id: string, side: 'in' | 'out', idx: number) => void
  onRemove: (id: string, e: React.MouseEvent) => void
}) {
  const sel = connectFrom != null && connectFrom.split('|')[0] === n.id
  const Icon = ICONS[n.icon]
  const dotStyle = (armed: boolean): React.CSSProperties => ({
    width: 12,
    height: 12,
    borderRadius: '50%',
    boxSizing: 'border-box',
    border: '2px solid var(--color-accent)',
    background: armed ? 'var(--color-accent)' : 'var(--color-card)',
    flexShrink: 0,
    cursor: connectMode ? 'pointer' : 'default',
    zIndex: 7,
  })
  return (
    <div
      onMouseDown={(e) => onDown(n.id, e)}
      className="absolute select-none"
      style={{
        left: n.x,
        top: n.y,
        width: UW,
        background: 'var(--color-card)',
        border: `1px solid ${sel ? 'var(--color-accent)' : 'var(--color-line-strong)'}`,
        borderLeft: `3px solid ${sel ? 'var(--color-accent)' : '#c6ced7'}`,
        borderRadius: 11,
        boxShadow: sel ? '0 0 0 3px var(--color-accent-weak)' : '0 2px 8px rgba(16,24,40,.1)',
        cursor: connectMode ? 'default' : 'grab',
        overflow: connectMode ? 'visible' : 'hidden',
        zIndex: 5,
      }}
    >
      <div className="flex items-center gap-1.5 px-2.5 pb-1.5 pt-2">
        <span className="grid h-[22px] w-[22px] shrink-0 place-items-center rounded-md bg-card-2 text-text-2">
          <Icon size={13} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[11.5px] font-semibold text-text">{n.name}</span>
          <span className="block truncate font-mono text-[9px] text-text-3">{n.version}</span>
        </span>
        <button
          onClick={(e) => onRemove(n.id, e)}
          onMouseDown={(e) => e.stopPropagation()}
          className="grid h-[18px] w-[18px] shrink-0 place-items-center text-text-3 hover:text-escalate-fg"
        >
          <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div className="flex gap-1.5 px-2.5 pb-2 pt-0.5">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          {n.ins.map((k, idx) => (
            <div key={idx} className="-ml-4 flex items-center gap-1.5">
              <span style={dotStyle(connectFrom === `${n.id}|in|${idx}`)} onMouseDown={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); onPortTap(n.id, 'in', idx) }} />
              <span className="truncate font-mono text-[9.5px] text-text-2">{k}</span>
            </div>
          ))}
        </div>
        <div className="flex min-w-0 flex-1 flex-col items-end gap-1.5">
          {n.outs.map((k, idx) => (
            <div key={idx} className="-mr-4 flex max-w-full items-center gap-1.5">
              <span className="truncate font-mono text-[9.5px] text-text-2">{k}</span>
              <span style={dotStyle(connectFrom === `${n.id}|out|${idx}`)} onMouseDown={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); onPortTap(n.id, 'out', idx) }} />
            </div>
          ))}
        </div>
      </div>
      <div className="px-2.5 pb-2">
        <span className="inline-flex items-center gap-1.5 text-[8.5px] font-bold uppercase tracking-[0.4px] text-accent-strong">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          draft
        </span>
      </div>
    </div>
  )
}
