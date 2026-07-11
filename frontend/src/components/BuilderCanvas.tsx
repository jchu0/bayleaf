import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, Cable, Lock, Minus, Plus, Redo2, Undo2, Wand2, X } from 'lucide-react'
import { SelectionActionBar, type AlignKind, type DistributeAxis } from './SelectionActionBar'
import {
  GATE_CHECKPOINTS,
  ICONS,
  PG_BADGE,
  REFS,
  TOOLS,
  V_COLOR,
  gateSegs,
  nodeBBox,
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
//
// PB2 on-canvas editing layers over the user nodes/edges only (the seeded DAG + gate stay read-only,
// non-deletable): node selection + inline rename, wire selection/deletion, marquee select, group
// move + alignment guides, and drag-to-connect. Screen↔content coordinates are converted via the
// inner plane's getBoundingClientRect() ÷ the CSS `zoom` factor, so every gesture stays true when
// zoomed (the inner plane uses non-standard CSS `zoom`, not a transform — see §Q4 of the design).

const INNER_W = 2560
const INNER_H = 460
// The inner content plane carries a fixed margin (see the plane style below). The dot grid must fill
// the ENTIRE scroll surface — the plane box PLUS its margin gutters — so the alignment dots never run
// out when panning past the cards. PAD_X/PAD_Y mirror that margin ('480px 360px') so an oversized dot
// layer (inside the zoomed plane, so it pans/zooms WITH the pipeline) covers exactly the scroll region
// and not one pixel more (a larger layer would add empty scroll; a smaller one leaves bald gutters).
const PAD_X = 360
const PAD_Y = 480
const MM_W = 210 // minimap width
const MM_H = 108 // minimap height — a bigger, squarer canvas mirror than the old 168×46 strip
const MM_SCALE = MM_W / INNER_W // uniform proportional scale (no x/y distortion)
const MM_VPAD = (MM_H - INNER_H * MM_SCALE) / 2 // vertically center the canvas strip in the box
const ZMIN = 0.6
const ZMAX = 1.4
const clampZoom = (z: number): number => Math.min(ZMAX, Math.max(ZMIN, +z.toFixed(2)))
const UW = 192 // user-node width (enlarged toward the Databricks card, builder-cards §3) — port anchors depend on it; MUST equal BuilderShared.NODE_W
const UPT = 52 // user-node first-port y-offset from card top
const UROW = 18 // user-node port-row pitch
const TW = 224 // seeded ToolCard width (w-56, enlarged from w-52) — output dots sit at its right edge
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

// A right-click menu request the screen turns into an item set (node/edge/canvas).
export type CanvasMenuReq = { x: number; y: number; kind: 'node' | 'edge' | 'canvas'; nodeId?: string; edgeIndex?: number }

type CanvasProps = {
  mode: Mode
  // false for a blank/new pipeline: render only the terminal gate + ingest band + user nodes,
  // not the hardcoded seeded germline chain (so a "New → Blank" canvas is actually empty).
  showSeeded: boolean
  selected: string | null
  selNodes: Set<string> // multi-selection (user nodes only)
  selEdge: number | null // index into userEdges, or null
  zoom: number
  userNodes: UserNode[]
  userEdges: UserEdge[]
  connectMode: boolean
  connectFrom: string | null
  guides: { x?: number; y?: number } | null // live alignment guides during a single-node drag
  renamingId: string | null // the user node whose name is being inline-edited
  canUndo: boolean
  canRedo: boolean
  fitNonce: number // bump to re-center (keyboard 'f' / context menu Fit)
  onSelect: (id: string | null) => void // seeded cards + background clear (null clears everything)
  onSelectEdge: (i: number | null) => void
  onDeleteEdge: (i: number) => void
  onMarquee: (ids: string[]) => void
  onZoom: (z: number) => void
  onToggleConnect: () => void
  onTidy: () => void
  onUndo: () => void
  onRedo: () => void
  onNodeDrag: (id: string, e: React.MouseEvent) => void
  onPortTap: (id: string, side: 'in' | 'out', idx: number) => void
  onDropConnect: (fromNode: string, fromIdx: number, toNode: string, toIdx: number) => void
  onRemoveNode: (id: string, e: React.MouseEvent) => void
  onStartRename: (id: string) => void
  onCommitRename: (id: string, name: string) => void
  onCancelRename: () => void
  onContextMenu: (m: CanvasMenuReq) => void
  onAlign: (k: AlignKind) => void
  onDistribute: (a: DistributeAxis) => void
  onDuplicateSel: () => void
  onDeleteSel: () => void
}

export function BuilderCanvas(props: CanvasProps) {
  const {
    mode,
    showSeeded,
    selected,
    selNodes,
    selEdge,
    zoom,
    userNodes,
    userEdges,
    connectMode,
    connectFrom,
    guides,
    renamingId,
  } = props
  const isView = mode === 'view'
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const innerRef = useRef<HTMLDivElement | null>(null) // the CSS-`zoom` content plane — the coord basis
  const centered = useRef(false)
  const updateVpRef = useRef<() => void>(() => {}) // set to updateVp below; used by the mount-centering + Fit rAFs

  // Transient interaction state kept local to the canvas (the screen owns topology/selection):
  //  - marquee: the live rubber-band rectangle in CONTENT coords
  //  - wireDrag: an in-progress drag-to-connect from an output port to the cursor (content coords)
  //  - hoverEdge: the edge under the cursor (surfaces its delete ×)
  const [marquee, setMarquee] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null)
  const [wireDrag, setWireDrag] = useState<{ fromNode: string; fromIdx: number; cx: number; cy: number } | null>(null)
  const [hoverEdge, setHoverEdge] = useState<number | null>(null)

  // Center the viewport on the pipeline once on mount (README §6: "loads centered").
  useEffect(() => {
    const el = scrollRef.current
    if (!el || centered.current) return
    centered.current = true
    requestAnimationFrame(() => {
      el.scrollLeft = Math.max(0, 1685 - el.clientWidth / 2)
      el.scrollTop = Math.max(0, 713 - el.clientHeight / 2)
      updateVpRef.current()
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

  // Minimap viewport rectangle — mirrors WHERE the scroll viewport currently sits on the canvas, so
  // the minimap moves in concordance with the pipeline (fixed 2026-07-10). Content coords carry the
  // 360/480 margin + the `zoom` factor (see fitToDag), so map viewport → inner → minimap accordingly.
  const [vp, setVp] = useState<{ left: number; top: number; width: number; height: number } | null>(null)
  const updateVp = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const z = zoomRef.current || 1
    const ix = el.scrollLeft / z - 360
    const iy = el.scrollTop / z - 480
    setVp({
      left: ix * MM_SCALE,
      top: MM_VPAD + iy * MM_SCALE,
      width: (el.clientWidth / z) * MM_SCALE,
      height: (el.clientHeight / z) * MM_SCALE,
    })
  }, [])
  updateVpRef.current = updateVp
  useEffect(() => {
    updateVp()
  }, [updateVp, zoom, userNodes.length])

  // Fit: reset zoom + scroll so the pipeline is centered — the seeded DAG, or the user nodes' bbox
  // when composing a draft. Content coords include the 360/480 margin the inner div carries.
  const fitToDag = useCallback(() => {
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
      updateVpRef.current()
    })
    // props.onZoom + userNodes are the only inputs; both are read fresh each call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userNodes])
  // Re-fit on a bumped nonce (keyboard 'f' / context menu). fitToDag is stable per userNodes.
  const fitRef = useRef(fitToDag)
  fitRef.current = fitToDag
  useEffect(() => {
    if (props.fitNonce > 0) fitRef.current()
  }, [props.fitNonce])

  const segs = gateSegs()

  // User-edge geometry: anchor to the exact port dots (out = right edge, in = left edge).
  const anchor = (id: string, side: 'out' | 'in', idx: number): { x: number; y: number } | null => {
    const n = userNodes.find((u) => u.id === id)
    if (!n) return null
    return { x: n.x + (side === 'out' ? UW : 0), y: n.y + UPT + idx * UROW }
  }
  // Keep the ORIGINAL userEdges index on each drawn edge so selection/delete address the right wire
  // (a filtered array would renumber and mis-target).
  const edgePaths = userEdges
    .map((ed, i) => {
      const a = anchor(ed.from.node, 'out', ed.from.idx)
      const b = anchor(ed.to.node, 'in', ed.to.idx)
      if (!a || !b) return null
      const mx = Math.round((a.x + b.x) / 2)
      return { i, d: `M${a.x} ${a.y} H${mx} V${b.y} H${b.x}`, mid: { x: mx, y: Math.round((a.y + b.y) / 2) } }
    })
    .filter((e): e is { i: number; d: string; mid: { x: number; y: number } } => e != null)

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

  // Convert a viewport point to CONTENT coords: subtract the inner plane's on-screen origin and
  // divide by the CSS `zoom` factor. This is the ONLY correct transform for the zoomed plane —
  // scroll-math drifts when zoomed (design §Q4).
  const toContent = (clientX: number, clientY: number): { x: number; y: number } | null => {
    const el = innerRef.current
    if (!el) return null
    const r = el.getBoundingClientRect()
    const z = zoomRef.current || 1
    return { x: (clientX - r.left) / z, y: (clientY - r.top) / z }
  }

  // ── Marquee select (Edit) ── begins only on a true background press (target IS the plane, never a
  // card/port/edge). Live-intersects each user node's bbox; a <4px press is a background click → clear.
  const onPlaneMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return
    if (e.target !== innerRef.current) return // a card/port/edge press is handled by that element
    if (isView) {
      props.onSelect(null)
      return
    }
    const start = toContent(e.clientX, e.clientY)
    if (!start) return
    const sx0 = e.clientX
    const sy0 = e.clientY
    setMarquee({ x1: start.x, y1: start.y, x2: start.x, y2: start.y })
    const move = (ev: MouseEvent) => {
      const c = toContent(ev.clientX, ev.clientY)
      if (!c) return
      const rect = { x1: Math.min(start.x, c.x), y1: Math.min(start.y, c.y), x2: Math.max(start.x, c.x), y2: Math.max(start.y, c.y) }
      setMarquee(rect)
      const ids = userNodes
        .filter((n) => {
          const b = nodeBBox(n)
          return b.x1 < rect.x2 && b.x2 > rect.x1 && b.y1 < rect.y2 && b.y2 > rect.y1
        })
        .map((n) => n.id)
      props.onMarquee(ids)
    }
    const up = (ev: MouseEvent) => {
      document.removeEventListener('mousemove', move)
      document.removeEventListener('mouseup', up)
      if (Math.hypot(ev.clientX - sx0, ev.clientY - sy0) < 4) props.onSelect(null) // background click → clear
      setMarquee(null)
    }
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', up)
  }

  // ── Drag-to-connect (Edit) ── press an OUTPUT dot, drag a rubber-band to an INPUT dot. The drop is
  // resolved by elementFromPoint reading the target dot's data-*; the screen re-runs the typed/dedup
  // validation (same as click-arm-click). A press with no valid drop just cancels (the click-arm-click
  // flow still fires for a plain click, so both gestures coexist).
  const startWireDrag = (fromNode: string, fromIdx: number, e: React.MouseEvent) => {
    if (isView) return
    e.preventDefault()
    e.stopPropagation()
    const c = toContent(e.clientX, e.clientY)
    if (!c) return
    setWireDrag({ fromNode, fromIdx, cx: c.x, cy: c.y })
    const move = (ev: MouseEvent) => {
      const p = toContent(ev.clientX, ev.clientY)
      if (p) setWireDrag((w) => (w ? { ...w, cx: p.x, cy: p.y } : w))
    }
    const up = (ev: MouseEvent) => {
      document.removeEventListener('mousemove', move)
      document.removeEventListener('mouseup', up)
      const el = document.elementFromPoint(ev.clientX, ev.clientY) as HTMLElement | null
      const dot = el?.closest('[data-port]') as HTMLElement | null
      if (dot && dot.dataset.side === 'in' && dot.dataset.node) {
        props.onDropConnect(fromNode, fromIdx, dot.dataset.node, Number(dot.dataset.idx))
      }
      setWireDrag(null)
    }
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', up)
  }

  return (
    <div className="relative min-w-0 flex-1">
      <div
        ref={scrollRef}
        className="absolute inset-0 overflow-auto bg-card-2"
        onMouseDown={(e) => {
          // A press on the scroll gutter (outside the plane) also clears selection.
          if (e.target === scrollRef.current) props.onSelect(null)
        }}
        onScroll={updateVp}
      >
        <div
          ref={innerRef}
          className="relative"
          onMouseDown={onPlaneMouseDown}
          onContextMenu={(e) => {
            if (e.target !== innerRef.current) return
            e.preventDefault()
            props.onContextMenu({ x: e.clientX, y: e.clientY, kind: 'canvas' })
          }}
          style={{
            width: INNER_W,
            height: INNER_H,
            margin: `${PAD_Y}px ${PAD_X}px`,
            zoom,
          }}
        >
          {/* The alignment dot grid, on a child that overhangs the plane's margin gutters by exactly
              PAD_X/PAD_Y so it fills the FULL scroll surface (plane box + gutters), not just the plane
              box (the old on-plane background stopped at the box edge, leaving bald gutters — the
              "partially present" report). Lives INSIDE the zoomed plane so it still pans/zooms WITH the
              pipeline; first child + no z-index so the edges/cards paint above it. Theme-aware via
              --canvas-dot (cool+subtle light, dim in dark). */}
          <div
            aria-hidden
            className="pointer-events-none absolute"
            style={{
              left: -PAD_X,
              top: -PAD_Y,
              width: INNER_W + PAD_X * 2,
              height: INNER_H + PAD_Y * 2,
              backgroundImage: 'radial-gradient(var(--canvas-dot) 1px, transparent 1px)',
              backgroundSize: '20px 20px',
              backgroundPosition: '12px 12px',
            }}
          />
          <svg className="pointer-events-none absolute left-0 top-0 overflow-visible" width={INNER_W} height={INNER_H}>
            {showSeeded &&
              seededPaths.map((d, i) => (
                <path key={`s${i}`} d={d} fill="none" stroke="#c6ced7" strokeWidth={1.5} />
              ))}
            {showSeeded &&
              refPaths.map((d, i) => (
                <path key={`r${i}`} d={d} fill="none" stroke="#d3dae1" strokeWidth={1.25} strokeDasharray="5 4" />
              ))}
            {/* Live alignment guides (single-node drag) — full-extent dashed accent lines. */}
            {guides?.x != null && (
              <line x1={guides.x} y1={-1000} x2={guides.x} y2={INNER_H + 2000} stroke="var(--color-accent)" strokeWidth={1} strokeDasharray="4 3" />
            )}
            {guides?.y != null && (
              <line x1={-1000} y1={guides.y} x2={INNER_W + 2000} y2={guides.y} stroke="var(--color-accent)" strokeWidth={1} strokeDasharray="4 3" />
            )}
            {/* User edges: a visible line + an invisible fat hit-path (pointer-events re-enabled only
                on the stroke) so a wire can be selected/deleted without a node. */}
            {edgePaths.map((e) => {
              const active = e.i === selEdge || e.i === hoverEdge
              return (
                <g key={`u${e.i}`}>
                  <path d={e.d} fill="none" stroke="var(--color-accent)" strokeWidth={e.i === selEdge ? 2.6 : 1.8} opacity={e.i === selEdge ? 1 : 0.9} />
                  {!isView && (
                    <path
                      d={e.d}
                      fill="none"
                      stroke="transparent"
                      strokeWidth={12}
                      style={{ pointerEvents: 'stroke', cursor: 'pointer' }}
                      onClick={(ev) => {
                        ev.stopPropagation()
                        props.onSelectEdge(e.i)
                      }}
                      onMouseEnter={() => setHoverEdge(e.i)}
                      onMouseLeave={() => setHoverEdge((h) => (h === e.i ? null : h))}
                      onContextMenu={(ev) => {
                        ev.preventDefault()
                        ev.stopPropagation()
                        props.onContextMenu({ x: ev.clientX, y: ev.clientY, kind: 'edge', edgeIndex: e.i })
                      }}
                    />
                  )}
                  {active && <circle cx={e.mid.x} cy={e.mid.y} r={3} fill="var(--color-accent)" />}
                </g>
              )
            })}
            {/* Drag-to-connect rubber band. */}
            {wireDrag &&
              (() => {
                const a = anchor(wireDrag.fromNode, 'out', wireDrag.fromIdx)
                if (!a) return null
                return <path d={`M${a.x} ${a.y} L${wireDrag.cx} ${wireDrag.cy}`} fill="none" stroke="var(--color-accent)" strokeWidth={1.8} strokeDasharray="5 4" />
              })()}
          </svg>

          {/* Wire delete ×: an HTML button in the content plane at the edge midpoint (shown for the
              selected/hovered wire). One-click, undoable — a single wire is a direct object, not a cascade. */}
          {!isView &&
            edgePaths
              .filter((e) => e.i === selEdge || e.i === hoverEdge)
              .map((e) => (
                <button
                  key={`x${e.i}`}
                  type="button"
                  title="Delete wire"
                  onClick={(ev) => {
                    ev.stopPropagation()
                    props.onDeleteEdge(e.i)
                  }}
                  onMouseEnter={() => setHoverEdge(e.i)}
                  onMouseLeave={() => setHoverEdge((h) => (h === e.i ? null : h))}
                  className="absolute z-[6] grid h-[18px] w-[18px] -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-escalate-bd bg-escalate-bg text-escalate-fg shadow-card hover:opacity-90"
                  style={{ left: e.mid.x, top: e.mid.y }}
                >
                  <X size={11} />
                </button>
              ))}

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
              isView={isView}
              selected={selNodes.has(n.id)}
              renaming={renamingId === n.id}
              connectMode={connectMode}
              connectFrom={connectFrom}
              onDown={props.onNodeDrag}
              onPortTap={props.onPortTap}
              onStartWireDrag={startWireDrag}
              onRemove={props.onRemoveNode}
              onStartRename={props.onStartRename}
              onCommitRename={props.onCommitRename}
              onCancelRename={props.onCancelRename}
              onContextMenu={(ev) => {
                ev.preventDefault()
                ev.stopPropagation()
                props.onContextMenu({ x: ev.clientX, y: ev.clientY, kind: 'node', nodeId: n.id })
              }}
            />
          ))}

          {/* Marquee rectangle (content plane, so it scales with zoom). */}
          {marquee && (
            <div
              className="pointer-events-none absolute z-[6] rounded-[2px] border border-dashed border-accent bg-accent/10"
              style={{ left: marquee.x1, top: marquee.y1, width: marquee.x2 - marquee.x1, height: marquee.y2 - marquee.y1 }}
            />
          )}
        </div>
      </div>

      {/* Canvas action cluster (Edit): Connect + Tidy (auto-layout) + Undo/Redo */}
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
          <div className="flex items-center rounded-lg border border-line-strong bg-card">
            <button
              onClick={props.onUndo}
              disabled={!props.canUndo}
              title="Undo (⌘Z)"
              className={`grid h-[31px] w-8 place-items-center rounded-l-lg ${props.canUndo ? 'text-text-2 hover:bg-page' : 'cursor-not-allowed text-text-3'}`}
            >
              <Undo2 size={14} />
            </button>
            <div className="h-[18px] w-px bg-line" />
            <button
              onClick={props.onRedo}
              disabled={!props.canRedo}
              title="Redo (⌘⇧Z)"
              className={`grid h-[31px] w-8 place-items-center rounded-r-lg ${props.canRedo ? 'text-text-2 hover:bg-page' : 'cursor-not-allowed text-text-3'}`}
            >
              <Redo2 size={14} />
            </button>
          </div>
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
        className="absolute right-3.5 top-3.5 z-[6] overflow-hidden rounded-lg border border-line-strong bg-card shadow-card"
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
            className={`absolute rounded-[1px] ${selNodes.has(n.id) ? 'bg-accent-strong' : 'bg-accent'}`}
            style={{ left: n.x * MM_SCALE, top: MM_VPAD + n.y * MM_SCALE, width: UW * MM_SCALE, height: 46 * MM_SCALE }}
          />
        ))}
        {/* Viewport rectangle — where the scroll viewport currently sits, so the minimap tracks the
            canvas position. Clamped into the box so a partly-off-canvas viewport still reads. */}
        {vp && (
          <span
            className="pointer-events-none absolute rounded-[2px] border-[1.5px] border-accent bg-accent/10"
            style={{
              left: Math.max(0, Math.min(vp.left, MM_W)),
              top: Math.max(0, Math.min(vp.top, MM_H)),
              width: Math.max(6, Math.min(vp.width, MM_W - Math.max(0, vp.left))),
              height: Math.max(6, Math.min(vp.height, MM_H - Math.max(0, vp.top))),
            }}
          />
        )}
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

      {/* Multi-selection action bar (align / distribute / duplicate / delete). */}
      {!isView && selNodes.size > 1 && (
        <SelectionActionBar
          count={selNodes.size}
          onAlign={props.onAlign}
          onDistribute={props.onDistribute}
          onDuplicate={props.onDuplicateSel}
          onDelete={props.onDeleteSel}
        />
      )}
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
      className="absolute w-56 overflow-hidden rounded-xl text-left"
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

// User-composed node: identical language to the seeded cards, but draggable + wireable + selectable.
// Ports carry data-* so drag-to-connect can resolve a drop via elementFromPoint; the name double-clicks
// into an inline rename. Selection (from the drag/click handler in the screen) shows an accent ring.
function UserCard({
  n,
  isView,
  selected,
  renaming,
  connectMode,
  connectFrom,
  onDown,
  onPortTap,
  onStartWireDrag,
  onRemove,
  onStartRename,
  onCommitRename,
  onCancelRename,
  onContextMenu,
}: {
  n: UserNode
  isView: boolean
  selected: boolean
  renaming: boolean
  connectMode: boolean
  connectFrom: string | null
  onDown: (id: string, e: React.MouseEvent) => void
  onPortTap: (id: string, side: 'in' | 'out', idx: number) => void
  onStartWireDrag: (fromNode: string, fromIdx: number, e: React.MouseEvent) => void
  onRemove: (id: string, e: React.MouseEvent) => void
  onStartRename: (id: string) => void
  onCommitRename: (id: string, name: string) => void
  onCancelRename: () => void
  onContextMenu: (e: React.MouseEvent) => void
}) {
  // Armed = this node is the connect-mode source; highlight = armed OR multi-selected (both read as an
  // accent ring, one visual language for "acted-on").
  const armed = connectFrom != null && connectFrom.split('|')[0] === n.id
  const highlight = armed || selected
  const Icon = ICONS[n.icon]
  const dotStyle = (isArmed: boolean): React.CSSProperties => ({
    width: 12,
    height: 12,
    borderRadius: '50%',
    boxSizing: 'border-box',
    border: '2px solid var(--color-accent)',
    background: isArmed ? 'var(--color-accent)' : 'var(--color-card)',
    flexShrink: 0,
    cursor: connectMode ? 'pointer' : 'default',
    zIndex: 7,
  })
  return (
    <div
      onMouseDown={(e) => onDown(n.id, e)}
      onContextMenu={onContextMenu}
      className="absolute select-none"
      style={{
        left: n.x,
        top: n.y,
        width: UW,
        background: 'var(--color-card)',
        border: `1px solid ${highlight ? 'var(--color-accent)' : 'var(--color-line-strong)'}`,
        borderLeft: `3px solid ${highlight ? 'var(--color-accent)' : '#c6ced7'}`,
        borderRadius: 11,
        boxShadow: highlight ? '0 0 0 3px var(--color-accent-weak)' : '0 2px 8px rgba(16,24,40,.1)',
        cursor: connectMode ? 'default' : 'grab',
        overflow: connectMode || renaming ? 'visible' : 'hidden',
        zIndex: selected ? 6 : 5,
      }}
    >
      <div className="flex items-center gap-1.5 px-2.5 pb-1.5 pt-2">
        <span className="grid h-[22px] w-[22px] shrink-0 place-items-center rounded-md bg-card-2 text-text-2">
          <Icon size={13} />
        </span>
        <span className="min-w-0 flex-1">
          {renaming ? (
            <input
              autoFocus
              defaultValue={n.name}
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
              onFocus={(e) => e.target.select()}
              onBlur={(e) => onCommitRename(n.id, e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  onCommitRename(n.id, (e.target as HTMLInputElement).value)
                } else if (e.key === 'Escape') {
                  e.preventDefault()
                  onCancelRename()
                }
              }}
              className="block w-full rounded border border-accent bg-card px-1 py-0.5 text-[11.5px] font-semibold text-text outline-none"
            />
          ) : (
            <span
              onDoubleClick={(e) => {
                if (isView) return
                e.stopPropagation()
                onStartRename(n.id)
              }}
              className="block truncate text-[11.5px] font-semibold text-text"
              title={isView ? undefined : 'Double-click to rename'}
            >
              {n.name}
            </span>
          )}
          <span className="block truncate font-mono text-[9px] text-text-3">{n.version}</span>
        </span>
        {!isView && (
          <button
            onClick={(e) => onRemove(n.id, e)}
            onMouseDown={(e) => e.stopPropagation()}
            className="grid h-[18px] w-[18px] shrink-0 place-items-center text-text-3 hover:text-escalate-fg"
            title="Delete node"
          >
            <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
      <div className="flex gap-1.5 px-2.5 pb-2 pt-0.5">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          {n.ins.map((k, idx) => (
            <div key={idx} className="-ml-4 flex items-center gap-1.5">
              <span
                data-port="1"
                data-node={n.id}
                data-side="in"
                data-idx={idx}
                data-kind={k}
                style={dotStyle(connectFrom === `${n.id}|in|${idx}`)}
                onMouseDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation()
                  onPortTap(n.id, 'in', idx)
                }}
              />
              <span className="truncate font-mono text-[9.5px] text-text-2">{k}</span>
            </div>
          ))}
        </div>
        <div className="flex min-w-0 flex-1 flex-col items-end gap-1.5">
          {n.outs.map((k, idx) => (
            <div key={idx} className="-mr-4 flex max-w-full items-center gap-1.5">
              <span className="truncate font-mono text-[9.5px] text-text-2">{k}</span>
              <span
                data-port="1"
                data-node={n.id}
                data-side="out"
                data-idx={idx}
                data-kind={k}
                style={dotStyle(connectFrom === `${n.id}|out|${idx}`)}
                onMouseDown={(e) => onStartWireDrag(n.id, idx, e)}
                onClick={(e) => {
                  e.stopPropagation()
                  onPortTap(n.id, 'out', idx)
                }}
              />
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
