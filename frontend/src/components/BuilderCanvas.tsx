import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Activity, Cable, Database, Lock, Minus, Plus, Redo2, Undo2, Wand2, X } from 'lucide-react'
import { SelectionActionBar, type AlignKind, type DistributeAxis } from './SelectionActionBar'
import { BuilderLegend } from './BuilderLegend'
import {
  ADVISORY_AGENT,
  BOX_META,
  BOX_TOP,
  CARD_FOOTER_H,
  CARD_HEADER_H,
  GATE_CHECKPOINTS,
  ICONS,
  NODE_W,
  PG_BADGE,
  PORT_R,
  REFS,
  TOOLS,
  V_COLOR,
  boxCols,
  boxPorts,
  cardHeight,
  computeGraphPortLayout,
  fanPortsToTargets,
  gateSegs,
  isRefKind,
  kindColor,
  layoutCardPorts,
  nodeBBox,
  nodeHeight,
  rowTag,
  type BoxCat,
  type BoxRow,
  type LaidPort,
  type Mode,
  type PortSide,
  type Tool,
  type UserEdge,
  type UserNode,
  type VStatus,
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

// The content plane. Sized for the SPINE + BRANCH layout: the spine (fastp@40 → norm@1560) on one row
// (y 260), the branch (mosdepth/MultiQC/File-output, y 600) below it, the source band above (y 40), and
// the ingest + terminal gate to the right (agent right edge ≈2552). Tall + generous so the whole layout
// fits with headroom and cards can be placed across the full surface (was 560 — cards clamped near y560).
const INNER_W = 3000
const INNER_H = 1120
// Layout landmarks shared by the seeded cards + minimap + centering (kept in ONE place so a re-space
// updates render, Fit, and the minimap together). Spine at y 260, branch at y 600, sources in a top
// band (REF_Y 40); ingest + gate to the right of the pipeline, at a middle height between the rows.
const REF_Y = 40 // source band (references + FASTQ input), above the spine
const INGEST_X = 2040
const INGEST_Y = 400
const INGEST_W = 200
const INGEST_H = 118
const GATE_X = 2320
const GATE_Y = 360
const GATE_W = 208
const GATE_H = 156
// The advisory agent is OFF-gate (ADR-0001): it sits with the QC tools it observes (below the branch),
// NOT clustered with the data terminals (gate/ingest) — its dotted links fan UP to its attached tools.
const AGENT_X = 1180
const AGENT_Y = 940
const AGENT_W = 236
const AGENT_H = 96
const GATE_PORT_Y = GATE_Y + 36 // the gate's non-composable run/ input port (item 4 display connector)
// Advisory attach badge — a small dashed-accent marker hugging each TOOL card's top-right corner (clear
// of the typed data ports + the delete button), distinct from the half-circle data ports. Its centre is
// the advisory-edge endpoint on the tool side.
const ADV_BADGE_DX = NODE_W - 8
const ADV_BADGE_DY = -8
const ADV_BADGE_R = 8
// Mount/Fit centering target (content coords include the plane's 360/480 margin): matches fitToDag's
// user-node framing (min_x 40, max_x 1560, y-band 40..600) so mount and Fit agree, nudged right so the
// terminal cluster peeks in.
const CENTER_X = 1440
const CENTER_Y = 860
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
const UW = NODE_W // user-node width — MUST equal BuilderShared.NODE_W (port anchors sit at n.x + UW)
const TW = NODE_W // seeded ToolCard width — same footprint as the composed cards (builder-cards §3)

// A port's outward normal (which way its half-circle faces) — used to give each wire endpoint a
// short stub in the port's facing direction so a four-sided wire leaves/enters the port cleanly.
function sideVec(s: PortSide): [number, number] {
  return s === 'left' ? [-1, 0] : s === 'right' ? [1, 0] : s === 'top' ? [0, -1] : [0, 1]
}
// Orthogonal wire route between two typed ports, honouring each port's side: a stub out of the
// source, a stub into the target, joined by an elbow. Reduces to the classic right→left elbow for
// the common primary-flow wire, and stays attached for bottom→left (QC) / top (reference) ports.
function routeEdge(
  a: { x: number; y: number; side: PortSide },
  b: { x: number; y: number; side: PortSide },
): { d: string; mid: { x: number; y: number } } {
  const stub = 16
  const [avx, avy] = sideVec(a.side)
  const [bvx, bvy] = sideVec(b.side)
  const ax2 = a.x + avx * stub
  const ay2 = a.y + avy * stub
  const bx2 = b.x + bvx * stub
  const by2 = b.y + bvy * stub
  const mx = Math.round((ax2 + bx2) / 2)
  const d = `M${a.x} ${a.y} L${ax2} ${ay2} H${mx} V${by2} H${bx2} L${b.x} ${b.y}`
  return { d, mid: { x: mx, y: Math.round((ay2 + by2) / 2) } }
}
// Card border widths, shared by ToolCard + UserCard: a 3px coloured left spine + 1px on the other
// three sides. Ports are position:absolute CHILDREN, so their left/top resolve against the card's
// PADDING box (inside the borders) — WITHOUT compensation a left port lands ON the 3px spine and a
// right port overhangs the edge. BORD_X/BORD_Y shift every port so its FLAT SIDE sits on the card's
// OUTER border-box edge (= p.lx / p.ly, where the wire anchor lives), so the port and the wire tip
// meet exactly. (A1 — ported from the design mockup's portStyle.)
const BORD_X = 3 // card border-left width (the spine)
const BORD_Y = 1 // card top/right/bottom border width
// Absolute-position + half-circle shape for a laid port: the flat side sits ON the card's outer
// border-box edge at (lx, ly) — the wire anchor — and the round bulge pokes OUTWARD (overflow-visible).
function portBoxStyle(p: LaidPort): React.CSSProperties {
  const R = PORT_R
  const base: React.CSSProperties = { position: 'absolute', boxSizing: 'border-box' }
  if (p.side === 'left') return { ...base, left: p.lx - R - BORD_X, top: p.ly - R - BORD_Y, width: R, height: 2 * R, borderRadius: '999px 0 0 999px' }
  if (p.side === 'right') return { ...base, left: p.lx - BORD_X, top: p.ly - R - BORD_Y, width: R, height: 2 * R, borderRadius: '0 999px 999px 0' }
  if (p.side === 'top') return { ...base, left: p.lx - R - BORD_X, top: p.ly - R - BORD_Y, width: 2 * R, height: R, borderRadius: '999px 999px 0 0' }
  return { ...base, left: p.lx - R - BORD_X, top: p.ly - BORD_Y, width: 2 * R, height: R, borderRadius: '0 0 999px 999px' }
}

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
  // The linked run's non-composable terminals (the gate's run/ input port, the advisory agent, the
  // ingest connectors + tether) render whenever this is the linked doc, even once the germline itself
  // is editable user nodes and showSeeded is off (ADR-0019 slice 1a).
  showTerminals: boolean
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
    showTerminals,
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
  // Advisory attachments (the QC-triage agent → the tools it observes). Deliberately NOT UserEdges — an
  // agent is OFF the deterministic critical path (ADR-0001), so its links never live in the typed data
  // graph and can never influence a verdict. Seeded, and operator-togglable via each tool's advisory badge.
  const [advisoryAttach, setAdvisoryAttach] = useState<Set<string>>(() => new Set(ADVISORY_AGENT.defaultAttach))
  const toggleAdvisory = useCallback((toolId: string) => {
    setAdvisoryAttach((s) => {
      const next = new Set(s)
      if (next.has(toolId)) next.delete(toolId)
      else next.add(toolId)
      return next
    })
  }, [])

  // Center the viewport on the pipeline once on mount (README §6: "loads centered").
  useEffect(() => {
    const el = scrollRef.current
    if (!el || centered.current) return
    centered.current = true
    requestAnimationFrame(() => {
      el.scrollLeft = Math.max(0, CENTER_X - el.clientWidth / 2)
      el.scrollTop = Math.max(0, CENTER_Y - el.clientHeight / 2)
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
    let tx = CENTER_X
    let ty = CENTER_Y
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

  // DYNAMIC NEAREST-SIDE port placement for the whole editable graph, recomputed whenever a node moves or
  // an edge changes (so ports re-aim live during a drag). This ONE map drives BOTH the card render (each
  // UserCard's `laid`) AND the wire anchors (anchorFull) — the render↔wiring shared-layout invariant: a
  // wire endpoint and its half-circle are computed from the same laid port, so they can never diverge.
  const nodesById = useMemo(() => new Map(userNodes.map((n) => [n.id, n])), [userNodes])
  const portLayout = useMemo(() => computeGraphPortLayout(userNodes, userEdges), [userNodes, userEdges])

  // User-edge geometry: anchor a wire to the EXACT half-circle port on its (now dynamic) side, from the
  // shared portLayout the card renders with — so an endpoint and its port are one point at any zoom.
  // PASS-2 A: a split port has one laid sub-port PER edge, so the anchor is looked up by (dir, idx, EID) —
  // each edge lands on its OWN sub-point, and no two edges share an endpoint. The eid=-1 fallback (drag
  // preview / a not-yet-laid edge) resolves to the port's first sub-point. Wire-to-tip: offset outward by
  // PORT_R along the port's side normal so the wire meets the half-circle's outer edge.
  const anchorForEdge = (id: string, dir: 'out' | 'in', idx: number, eid: number): { x: number; y: number; side: PortSide } | null => {
    const n = nodesById.get(id)
    const laid = portLayout.get(id)
    const p = laid?.find((q) => q.dir === dir && q.idx === idx && q.eid === eid) ?? laid?.find((q) => q.dir === dir && q.idx === idx)
    if (!n || !p) return null
    const [nx, ny] = sideVec(p.side)
    return { x: n.x + p.lx + nx * PORT_R, y: n.y + p.ly + ny * PORT_R, side: p.side }
  }
  // Keep the ORIGINAL userEdges index on each drawn edge so selection/delete address the right wire
  // (a filtered array would renumber and mis-target). That index IS the edge's eid — the split-port key.
  const edgePaths = userEdges
    .map((ed, i) => {
      const a = anchorForEdge(ed.from.node, 'out', ed.from.idx, i)
      const b = anchorForEdge(ed.to.node, 'in', ed.to.idx, i)
      if (!a || !b) return null
      const { d, mid } = routeEdge(a, b)
      // Kind-COLOUR each editable wire by its SOURCE port's data kind — the SAME --k-* family the seeded
      // wires + port borders use (fastq violet, bam blue, vcf teal, ref, QC gold), not a flat accent blue.
      // (Advisory agent→tool edges are drawn separately and stay dotted-accent — ADR-0001 distinct.)
      const srcKind = nodesById.get(ed.from.node)?.outs[ed.from.idx]
      const color = srcKind ? kindColor(srcKind) : 'var(--color-text-3)'
      return { i, d, mid, color }
    })
    .filter((e): e is { i: number; d: string; mid: { x: number; y: number }; color: string } => e != null)

  // Seeded-DAG edges, COMPUTED from the tool card geometry + typed four-sided ports via the shared
  // layoutPorts (not hardcoded SVG paths, which detached whenever a card's port count changed — the
  // "broken lines" report). The output port sits on its real side (right/bottom), the input on its
  // real side (left/top), so a wire attaches to the exact half-circle it names.
  const toolAnchorFull = (id: string, dir: 'out' | 'in', kind: string): { x: number; y: number; side: PortSide } | null => {
    const t = TOOLS.find((x) => x.id === id)
    if (!t) return null
    const ins = t.inputs.map((p) => p.kind)
    const outs = t.outputs.map((p) => p.kind)
    const idx = (dir === 'out' ? outs : ins).findIndex((k) => k === kind)
    if (idx < 0) return null
    const p = layoutCardPorts(t.tool, ins, outs, TW, cardHeight(t.tool, ins, outs)).find((q) => q.dir === dir && q.idx === idx)
    if (!p) return null
    const [nx, ny] = sideVec(p.side)
    return { x: t.x + p.lx + nx * PORT_R, y: t.y + p.ly + ny * PORT_R, side: p.side }
  }
  // Kind-COLOURED wires (B#1): stroke each seeded wire by its data-kind via kindColor (a theme-aware
  // --k-* var) instead of a flat grey — fastq violet, bam blue, vcf teal, and the QC fan-in gold
  // (coloured by the OUTPUT kind fk, so the fan-in reads gold automatically).
  const seededPaths = SEEDED_WIRES.map(([fid, fk, tid, tk]) => {
    const a = toolAnchorFull(fid, 'out', fk)
    const b = toolAnchorFull(tid, 'in', tk)
    if (!a || !b) return null
    return { d: routeEdge(a, b).d, color: kindColor(fk) }
  }).filter((e): e is { d: string; color: string } => e != null)
  // Reference cards sit ABOVE the spine (y = REF_Y); their edges DESCEND from the ref card bottom into
  // the tool's reference port — which now lives on the LEFT side (batch 3a: ports are left/right only).
  // routeEdge(bottom → left) drops from the ref card, then comes into the left port from the left. b is
  // already the port TIP (toolAnchorFull offsets by PORT_R), so the wire meets the half-circle.
  const refPaths = REF_WIRES.map(([rid, tid, tk]) => {
    const r = REFS.find((x) => x.id === rid)
    const b = toolAnchorFull(tid, 'in', tk)
    if (!r || !b) return null
    const a = { x: r.x + 75, y: REF_Y + 52, side: 'bottom' as PortSide } // ref card bottom-centre (card is 150 wide)
    return { d: routeEdge(a, b).d, color: kindColor(tk) }
  }).filter((e): e is { d: string; color: string } => e != null)

  // Item 4 — non-composable DISPLAY connectors for the terminal cluster (norm/MultiQC → ingest → gate).
  // These are pure SVG, seeded-view only; they are NEVER UserEdges and never touch the wiring model.
  // In the spine+branch layout the gate sits between the two rows: norm (spine, upper) enters the ingest
  // left near its top; MultiQC (branch, lower) rises just left of the File-output sink then enters the
  // ingest left lower down; ingest → gate lands on the gate's run/ port. No dip needed (MultiQC is no
  // longer between norm and ingest).
  const termConnectors: string[] = []
  if (showTerminals) {
    const normOut = toolAnchorFull('n_norm', 'out', 'filtered_vcf')
    const mqOut = toolAnchorFull('n_multiqc', 'out', 'multiqc_json')
    const ingY = INGEST_Y + INGEST_H / 2
    if (normOut) termConnectors.push(`M${normOut.x} ${normOut.y} H${INGEST_X - 24} V${INGEST_Y + 38} H${INGEST_X}`)
    if (mqOut) termConnectors.push(`M${mqOut.x} ${mqOut.y} V${INGEST_Y + INGEST_H - 38} H${INGEST_X}`)
    termConnectors.push(`M${INGEST_X + INGEST_W} ${ingY} H${INGEST_X + INGEST_W + 16} V${GATE_PORT_Y} H${GATE_X - PORT_R}`)
  }
  // Advisory fan-out (replaces the old gate↔agent tether): the agent card links to EACH attached tool via
  // a DISTINCT dotted accent line — visually + semantically apart from the solid kind-coloured DATA wires,
  // reflecting that the agent OBSERVES/advises but never carries data or sets a verdict (ADR-0001). ONE
  // agent → MANY tools: a fan-out port per attached tool, placed nearest that tool (like a multi-out ref).
  const attachedTools = showTerminals
    ? userNodes.filter((n) => advisoryAttach.has(n.id) && n.ins.length > 0 && n.outs.length > 0)
    : []
  const toolBadgeOf = (n: UserNode) => ({ x: n.x + ADV_BADGE_DX, y: n.y + ADV_BADGE_DY })
  const agentFan = fanPortsToTargets({ x: AGENT_X, y: AGENT_Y, w: AGENT_W, h: AGENT_H }, attachedTools.map(toolBadgeOf))
  const advisoryEdges = attachedTools.map((n, i) => ({ from: agentFan[i], to: toolBadgeOf(n) }))

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
              seededPaths.map((p, i) => (
                <path key={`s${i}`} d={p.d} fill="none" stroke={p.color} strokeWidth={2} />
              ))}
            {showSeeded &&
              refPaths.map((p, i) => (
                <path key={`r${i}`} d={p.d} fill="none" stroke={p.color} strokeWidth={1.5} strokeDasharray="5 4" />
              ))}
            {/* Item 4 — non-composable terminal connectors (norm/MultiQC → ingest → gate), dotted neutral.
                Display-only; not graph edges. */}
            {termConnectors.map((d, i) => (
              <path key={`term${i}`} d={d} fill="none" stroke="var(--color-text-3)" strokeWidth={1.6} strokeDasharray="2 4" />
            ))}
            {/* ADVISORY edges (agent → each attached tool). DELIBERATELY distinct from the solid, kind-
                coloured DATA wires: a thin DOTTED accent line, so an agent visibly never sits on a data
                edge (ADR-0001). Straight (not the orthogonal data elbow) to read as a soft observe-link. */}
            {advisoryEdges.map((e, i) => (
              <path
                key={`adv${i}`}
                d={`M${e.from.x} ${e.from.y} L${e.to.x} ${e.to.y}`}
                fill="none"
                stroke="var(--color-accent)"
                strokeWidth={1.4}
                strokeDasharray="1 5"
                strokeLinecap="round"
                opacity={0.75}
              />
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
                  <path d={e.d} fill="none" stroke={e.color} strokeWidth={e.i === selEdge ? 2.6 : 1.8} opacity={e.i === selEdge ? 1 : 0.9} />
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
                const a = anchorForEdge(wireDrag.fromNode, 'out', wireDrag.fromIdx, -1)
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

          <span className="absolute left-10 top-[222px] text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">
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
          <GateCard isView={isView} selected={selected === 'g_gate'} segs={segs} onActivate={() => props.onSelect('g_gate')} />
          {/* Item 4 — the gate's non-composable run/ INPUT: a dashed escalate half-circle on the gate's
              left edge (a canvas-plane sibling, so the gate's overflow-hidden doesn't clip it) + label.
              It reads run/ via deterministic ingest — not a typed data edge. */}
          {showTerminals && (
            <>
              <span
                className="pointer-events-none absolute z-[4]"
                title="run/ · ingest input · not a typed data edge"
                style={{
                  left: GATE_X - PORT_R,
                  top: GATE_PORT_Y - PORT_R,
                  width: PORT_R,
                  height: 2 * PORT_R,
                  borderRadius: '999px 0 0 999px',
                  background: 'var(--color-card)',
                  border: '1.5px dashed var(--color-escalate)',
                  boxSizing: 'border-box',
                }}
              />
              <span
                className="pointer-events-none absolute z-[4] font-mono text-[8px] font-bold"
                style={{ left: GATE_X - 32, top: GATE_PORT_Y - 16, color: 'var(--color-escalate-fg)' }}
              >
                run/
              </span>
            </>
          )}
          {/* Advisory agent (off-gate) + its fan-out ports (one per attached tool). The dotted advisory
              edges are drawn in the SVG layer above; these markers sit on the agent card's perimeter. */}
          {showTerminals && (
            <>
              <AgentCard
                selected={selected === ADVISORY_AGENT.id}
                onActivate={() => props.onSelect(ADVISORY_AGENT.id)}
                attachCount={attachedTools.length}
              />
              {agentFan.map((p, i) => (
                <AdvisoryPortMarker key={`ap${i}`} x={p.x} y={p.y} />
              ))}
            </>
          )}

          {userNodes.map((n) => (
            <UserCard
              key={n.id}
              n={n}
              laid={portLayout.get(n.id) ?? []}
              isView={isView}
              selected={selNodes.has(n.id)}
              renaming={renamingId === n.id}
              connectMode={connectMode}
              connectFrom={connectFrom}
              advisoryShown={showTerminals && n.ins.length > 0 && n.outs.length > 0}
              advisoryOn={advisoryAttach.has(n.id)}
              onAdvisoryToggle={() => toggleAdvisory(n.id)}
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
              style={{
                left: t.x * MM_SCALE,
                top: MM_VPAD + t.y * MM_SCALE,
                width: TW * MM_SCALE,
                height: cardHeight(t.tool, t.inputs.map((p) => p.kind), t.outputs.map((p) => p.kind)) * MM_SCALE,
              }}
            />
          ))}
        {showSeeded &&
          REFS.map((r) => (
            <span
              key={r.id}
              className="absolute rounded-[1px] bg-line"
              style={{ left: r.x * MM_SCALE, top: MM_VPAD + REF_Y * MM_SCALE, width: 150 * MM_SCALE, height: 40 * MM_SCALE }}
            />
          ))}
        {/* terminal gate */}
        <span
          className="absolute rounded-[1px] bg-text-3"
          style={{ left: GATE_X * MM_SCALE, top: MM_VPAD + GATE_Y * MM_SCALE, width: Math.max(4, 208 * MM_SCALE), height: 64 * MM_SCALE }}
        />
        {userNodes.map((n) => (
          <span
            key={n.id}
            className={`absolute rounded-[1px] ${selNodes.has(n.id) ? 'bg-accent-strong' : 'bg-accent'}`}
            style={{ left: n.x * MM_SCALE, top: MM_VPAD + n.y * MM_SCALE, width: UW * MM_SCALE, height: nodeHeight(n) * MM_SCALE }}
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

      {/* Card-system legend — a dismissible panel toggled from the canvas top-left (item 3). */}
      <BuilderLegend edit={!isView} />

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

// ── Shared card-port rendering (builder-cards §2/§3) — used by BOTH ToolCard (read-only) and
// UserCard (interactive), so a port looks identical whichever card hosts it. ──

// Per-stage accent hue for the header stage label + the top stage strip (mockup --stage-* vars,
// inlined so no extra CSS tokens are needed — these mid-tones read on both themes).
// Theme-aware via the --stage-* vars in index.css (B#3): the dark set brightens so the strip/label
// stay legible on the dark card (the previous fixed light hexes read dim on dark).
const STAGE_HEX: Record<string, string> = {
  'Read QC + trim': 'var(--stage-readqc)',
  Alignment: 'var(--stage-align)',
  'Duplicate marking': 'var(--stage-dedup)',
  Coverage: 'var(--stage-cov)',
  'Variant calling': 'var(--stage-var)',
  'Filter / normalize': 'var(--stage-var)',
  'QC aggregation': 'var(--stage-agg)',
}
const LIST_ROW_H = 15

// Batch 3a point 1 — the run status is now carried by the card's LEFT SPINE (no number badge): the
// bound-run vstatus colours the 3px rail (passed / attention / blocked), neutral when no run is bound
// (a fresh compose). Honest: per-STEP pass/attention from the pre-committed run, not live "running".
type RunStatus = 'passed' | 'attention' | 'blocked' | 'notrun'
const RUN_STATUS: Record<RunStatus, { rail: string; label: string }> = {
  passed: { rail: 'var(--color-proceed)', label: 'passed' },
  attention: { rail: 'var(--color-hold)', label: 'needs attention' },
  blocked: { rail: 'var(--color-escalate)', label: 'blocked' },
  notrun: { rail: '#c6ced7', label: 'not run' },
}
function runStatusOf(isView: boolean, vstatus: VStatus): RunStatus {
  if (!isView) return 'notrun' // a fresh compose has no bound run
  return vstatus === 'ok' ? 'passed' : vstatus === 'warn' ? 'attention' : 'blocked'
}

// Half-circle fill/border by data-kind + state (mockup portFillStyle). Reference-kind inputs render
// OUTLINED (card bg); required = solid kind fill; optional = 40% kind fill; reserved = dashed hollow,
// dimmed. Verdict palette is never used here (kindColor is the verdict-safe --k-* family).
function portVisualStyle(p: LaidPort): React.CSSProperties {
  const col = kindColor(p.kind)
  if (isRefKind(p.kind)) {
    return { background: 'var(--color-card)', borderColor: col, ...(p.state === 'reserved' ? { borderStyle: 'dashed', opacity: 0.7 } : {}) }
  }
  if (p.state === 'reserved') return { background: 'transparent', borderColor: col, borderStyle: 'dashed', opacity: 0.7 }
  if (p.state === 'optional') return { background: `color-mix(in srgb, ${col} 40%, transparent)`, borderColor: col }
  return { background: col, borderColor: col }
}
// A non-interactive port half-circle (seeded ToolCard). The flat side sits on the edge = the wire tip.
function StaticPort({ p }: { p: LaidPort }) {
  return (
    <span
      className="pointer-events-none absolute"
      title={`#${p.cidx} · ${p.kind} · ${p.dir} · ${p.state}`}
      style={{ ...portBoxStyle(p), borderWidth: 1.5, borderStyle: 'solid', zIndex: 4, ...portVisualStyle(p) }}
    />
  )
}
// Batch 3a point 2 — the per-port NUMBER marker sits OUTSIDE the card, just beyond its half-circle
// (a left port's number to the left of the card, a right port's to the right), aligned on the port's
// y. Moving them out frees the interior for the three boxes. Digit centred (leading-none); a solid
// card bg + shadow so a wired port's number reads over the wire it sits on.
function PortIndexChip({ p, w }: { p: LaidPort; w: number }) {
  // The number sits just OUTSIDE the port's half-circle, on whichever of the four dynamic sides it landed:
  // left/right → beside it (keyed to p.ly), top/bottom → above/below it (keyed to p.lx). Number is p.cidx —
  // the STABLE box number, unchanged by where the port moved.
  const R = PORT_R
  const pos: React.CSSProperties =
    p.side === 'left'
      ? { left: -26, top: p.ly - BORD_Y - R }
      : p.side === 'right'
        ? { left: w + 6, top: p.ly - BORD_Y - R }
        : p.side === 'top'
          ? { left: p.lx - BORD_X - R, top: -22 }
          : { left: p.lx - BORD_X - R, top: p.ly + 8 }
  return (
    <span
      className="pointer-events-none absolute z-[6] grid h-3.5 w-3.5 place-items-center rounded-full bg-card text-[8px] font-bold leading-none text-text-2 shadow-card"
      style={{ ...pos, border: `1px solid ${kindColor(p.kind)}` }}
    >
      {p.cidx}
    </span>
  )
}
// The category-tag chip on a box row (refine pass): one consistent set across every box — REQ / REF /
// OPT / RSVD. REQ neutral, REF tinted with the reference-kind colour, OPT accent (wireable now), RSVD
// muted (reserved). Same chip shape/size for all four so the tag column reads as one column.
const TAG_CLASS: Record<'REQ' | 'OPT' | 'RSVD', string> = {
  REQ: 'bg-card-2 text-text-2',
  OPT: 'bg-accent-weak text-accent-strong',
  RSVD: 'bg-card-3 text-text-3',
}
function RowTagChip({ tag }: { tag: ReturnType<typeof rowTag> }) {
  if (tag === 'REF')
    return (
      <span
        className="shrink-0 rounded px-1 text-[7.5px] font-bold uppercase leading-none"
        style={{ background: 'color-mix(in srgb, var(--k-ref) 18%, transparent)', color: 'var(--k-ref)' }}
      >
        REF
      </span>
    )
  return <span className={`shrink-0 rounded px-1 text-[7.5px] font-bold uppercase leading-none ${TAG_CLASS[tag]}`}>{tag}</span>
}
// One gray box (batch 3a point 3, columned in the refine pass): a titled panel whose rows are aligned
// COLUMNS — number(s) · kind · dir · tag. One row per LOGICAL port; a SPLIT port (PASS-2 A) lists the
// kind once with its N numbers (e.g. `bam · out · [2][3]`), so the row count still equals the catalog
// count the card height was sized for. A box with many rows (boxCols → 2) uses a compact 2-column grid.
function ConnBox({ cat, title, rows, top }: { cat: BoxCat; title: string; rows: BoxRow[]; top: number }) {
  const cols = boxCols(rows.length)
  const rowsPerCol = Math.ceil(rows.length / cols)
  return (
    <div
      className="pointer-events-none absolute left-[11px] right-[11px] rounded-lg border border-line px-2 pb-1.5 pt-1"
      style={{ top, background: 'color-mix(in srgb, var(--color-card-2) 60%, transparent)' }}
    >
      <div className="mb-0.5 text-[8px] font-bold uppercase tracking-[0.5px] text-text-3">{title} · {rows.length}</div>
      <div
        className="grid gap-x-2.5"
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridTemplateRows: `repeat(${rowsPerCol}, ${LIST_ROW_H}px)`, gridAutoFlow: 'column' }}
      >
        {rows.map((r) => (
          <div key={r.pidx} className="flex items-center gap-1">
            <span className="flex shrink-0 items-center gap-0.5">
              {r.cidxs.map((c) => (
                <span
                  key={c}
                  className="inline-grid h-[13px] w-[13px] place-items-center rounded-full bg-card text-[7.5px] font-bold leading-none text-text-2"
                  style={{ border: `1px solid ${kindColor(r.kind)}` }}
                >
                  {c}
                </span>
              ))}
            </span>
            <span className="min-w-0 flex-1 truncate font-mono text-[9.5px] text-text">{r.kind}</span>
            <span className="shrink-0 text-[8px] text-text-3">{r.dir}</span>
            <RowTagChip tag={rowTag(cat, r.state)} />
          </div>
        ))}
      </div>
    </div>
  )
}
// The THREE separate gray boxes (batch 3a point 3), stacked top→bottom: REQUIRED, REFERENCE,
// OPTIONAL / RESERVED — each rendered only when it has rows; height follows its 1/2-column layout.
function CardBoxes({ laid }: { laid: LaidPort[] }) {
  let top = BOX_TOP
  return (
    <>
      {BOX_META.map(({ cat, title }) => {
        const rows = boxPorts(laid, cat)
        if (!rows.length) return null
        const at = top
        top += 24 + Math.ceil(rows.length / boxCols(rows.length)) * LIST_ROW_H + 8
        return <ConnBox key={cat} cat={cat} title={title} rows={rows} top={at} />
      })}
    </>
  )
}

function ToolCard({ t, isView, selected, onSelect }: { t: Tool; isView: boolean; selected: boolean; onSelect: (id: string) => void }) {
  const badge = PG_BADGE[t.pg]
  // Batch 3a point 1 — the LEFT SPINE now carries the full run-status colour (passed green / attention
  // amber / blocked red / neutral not-run) via runStatusOf; the 0–6 number badge is removed entirely.
  const rail = RUN_STATUS[runStatusOf(isView, t.vstatus)].rail
  // Per-side borders (not the `border` shorthand) so the 3px colored left spine can coexist
  // with the other sides without React's shorthand/longhand conflict warning.
  const cardBorder = selected
    ? '1px solid var(--color-accent)'
    : isView
      ? '1px solid var(--color-line)'
      : '1px dashed var(--color-line-strong)'
  const Icon = ICONS[t.icon]
  const ins = t.inputs.map((p) => p.kind)
  const outs = t.outputs.map((p) => p.kind)
  const H = cardHeight(t.tool, ins, outs)
  const laid = layoutCardPorts(t.tool, ins, outs, TW, H)
  const stageHex = STAGE_HEX[t.stageLabel] ?? 'var(--color-text-3)'
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onSelect(t.id)
      }}
      // overflow VISIBLE so the four-sided half-circle ports can poke past the card edge. Card-state
      // shading (default / hover / selected) comes from the .pg-node classes (item 1) — box-shadow
      // lives there so :hover can lift; the inline border keeps the dynamic rail.
      className={`pg-node absolute rounded-xl text-left${selected ? ' is-selected' : ''}`}
      style={{
        left: t.x,
        top: t.y,
        width: TW,
        height: H,
        overflow: 'visible',
        background: isView ? 'var(--color-card)' : 'var(--color-card-3)',
        borderTop: cardBorder,
        borderRight: cardBorder,
        borderBottom: cardBorder,
        borderLeft: `3px ${isView || selected ? 'solid' : 'dashed'} ${rail}`,
      }}
    >
      {/* PG pill in an absolute top-right slot; the header reserves 90px on the right (no truncation).
          The run-status is on the spine now (no top-left badge — batch 3a point 1). */}
      <span
        className="absolute z-[5] rounded-[5px] px-[7px] py-0.5 text-[8.5px] font-bold uppercase tracking-wide"
        style={{ top: 9, right: 12, color: badge.fg, background: badge.bg }}
      >
        {badge.label}
      </span>
      {/* Header pinned to the top (absolute — a native <button> would otherwise vertically-center its
          only in-flow child). Ports are now left/right only + numbered OUTSIDE, so no top gutter. */}
      <div className="absolute inset-x-0 top-0 flex items-center gap-2.5 pl-3 pr-[90px]" style={{ height: CARD_HEADER_H }}>
        <span className={`grid h-[30px] w-[30px] shrink-0 place-items-center rounded-lg ${isView ? 'bg-card-2 text-text' : 'bg-card-3 text-text-3'}`}>
          <Icon size={16} />
        </span>
        <span className="min-w-0 flex-1">
          <span className={`block truncate font-mono text-[12.5px] font-semibold ${isView ? 'text-text' : 'text-text-2'}`}>{t.tool}</span>
          <span className="mt-0.5 flex items-center gap-1.5">
            <span className="shrink-0 rounded border border-line bg-card-2 px-1 font-mono text-[10px] text-text-2">{t.version}</span>
            <span className="text-[10px] text-text-3">·</span>
            <span className="truncate text-[9px] font-bold uppercase tracking-[0.4px]" style={{ color: stageHex }}>
              {t.stageLabel}
            </span>
          </span>
        </span>
      </div>
      {/* Stage strip — a thin stage-coloured line under the header (mockup .strip). */}
      <span className="absolute left-[3px] right-0 h-1" style={{ top: CARD_HEADER_H, background: stageHex, borderRadius: '0 3px 0 0' }} />
      {laid.map((p) => (
        <StaticPort key={p.pidx} p={p} />
      ))}
      {laid.map((p) => (
        <PortIndexChip key={`c${p.pidx}`} p={p} w={TW} />
      ))}
      <CardBoxes laid={laid} />
      <div className="absolute inset-x-0 bottom-0 flex items-center gap-1.5 border-t border-line px-3" style={{ height: CARD_FOOTER_H }}>
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
        top: REF_Y,
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

// ── Unified canvas card frame (item 1) ───────────────────────────────────────
// The SAME chrome the tool/source cards use — so the terminals (gate / ingest / advisory agent) read as
// first-class cards instead of bespoke pills: pg-node body (hover/selected shading), rounded-xl, a 3px
// left spine, an icon-tile + title + subtitle header, an optional right slot + child body. Callers keep
// their SPECIAL semantics in the body; this only unifies the LOOK. overflow-visible so ports can poke out.
function CanvasCardFrame({
  x, y, w, h, selected, onActivate, railColor, railSolid = true, borderColor, dashedBorder, iconTone, icon, title, subtitle, right, children,
}: {
  x: number
  y: number
  w: number
  h?: number
  selected: boolean
  onActivate?: () => void
  railColor: string
  railSolid?: boolean
  borderColor: string
  dashedBorder?: boolean
  iconTone?: React.CSSProperties
  icon: React.ReactNode
  title: string
  subtitle: string
  right?: React.ReactNode
  children?: React.ReactNode
}) {
  const sideBorder = `1px ${dashedBorder ? 'dashed' : 'solid'} ${selected ? 'var(--color-accent)' : borderColor}`
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onActivate?.()
      }}
      className={`pg-node absolute rounded-xl text-left${selected ? ' is-selected' : ''}`}
      style={{
        left: x,
        top: y,
        width: w,
        height: h,
        overflow: 'visible',
        background: 'var(--color-card)',
        borderTop: sideBorder,
        borderRight: sideBorder,
        borderBottom: sideBorder,
        borderLeft: `3px ${railSolid ? 'solid' : 'dashed'} ${selected ? 'var(--color-accent)' : railColor}`,
        cursor: onActivate ? 'pointer' : 'default',
      }}
    >
      <div className="flex items-center gap-2 px-3" style={{ height: CARD_HEADER_H }}>
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-card-2 text-text-2" style={iconTone}>
          {icon}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[12px] font-bold text-text">{title}</span>
          <span className="block truncate font-mono text-[9.5px] text-text-3">{subtitle}</span>
        </span>
        {right}
      </div>
      {children}
    </button>
  )
}

// Deterministic ingest (item 1) — non-composable (dashed frame + neutral spine): writes run/ for the gate.
function IngestBand() {
  return (
    <CanvasCardFrame
      x={INGEST_X}
      y={INGEST_Y}
      w={INGEST_W}
      h={INGEST_H}
      selected={false}
      railColor="#8b95a1"
      borderColor="var(--color-line-strong)"
      dashedBorder
      icon={<Database size={15} className="text-text-3" />}
      title="Deterministic ingest"
      subtitle="non-composable"
    >
      <div className="px-3 pt-1.5">
        <p className="font-mono text-[10px] leading-snug text-text-2">write_run_dir</p>
        <p className="font-mono text-[10px] leading-snug text-text-3">→ run/ (5 CSVs)</p>
        <p className="mt-1.5 text-[9px] italic text-text-3">writes the run dir the gate reads</p>
      </div>
    </CanvasCardFrame>
  )
}

// Advisory agent (item 1 + 3) — OFF-gate: dashed ACCENT frame/spine, no data ports, no verdict (ADR-0001).
// `attachCount` = how many tools it currently observes (its fan-out ports render as canvas-plane siblings).
function AgentCard({ selected, onActivate, attachCount }: { selected: boolean; onActivate?: () => void; attachCount: number }) {
  return (
    <CanvasCardFrame
      x={AGENT_X}
      y={AGENT_Y}
      w={AGENT_W}
      h={AGENT_H}
      selected={selected}
      onActivate={onActivate}
      railColor="var(--color-accent)"
      railSolid={false}
      borderColor="var(--color-accent)"
      dashedBorder
      iconTone={{ background: 'var(--color-accent-weak)', color: 'var(--color-accent-strong)' }}
      icon={<Activity size={15} />}
      title={ADVISORY_AGENT.name}
      subtitle="advisory · off-gate"
      right={<span className="shrink-0 rounded bg-card-2 px-1.5 py-0.5 font-mono text-[9px] text-text-2">{ADVISORY_AGENT.model}</span>}
    >
      <div className="px-3 pt-1">
        <p className="text-[9.5px] text-text-2">
          observes <span className="font-mono">{ADVISORY_AGENT.observes}</span> · never sets a verdict
        </p>
        <p className="mt-1.5 text-[9px] font-bold uppercase tracking-[0.3px] text-accent-strong">
          {attachCount} tool{attachCount === 1 ? '' : 's'} attached · advisory link only
        </p>
      </div>
    </CanvasCardFrame>
  )
}

// Decision gate (item 1) — the non-composable TERMINAL: escalate spine, a Lock (non-removable), the three
// checkpoints, and the verdict readout footer. Its run/ INPUT port renders as a canvas-plane sibling.
function GateCard({ isView, selected, segs, onActivate }: { isView: boolean; selected: boolean; segs: { c: string; w: string }[]; onActivate?: () => void }) {
  return (
    <CanvasCardFrame
      x={GATE_X}
      y={GATE_Y}
      w={GATE_W}
      h={GATE_H}
      selected={selected}
      onActivate={onActivate}
      railColor={isView ? 'var(--color-escalate)' : '#c6ced7'}
      borderColor="var(--color-line-strong)"
      iconTone={{ background: 'var(--color-escalate-bg)', color: 'var(--color-escalate-fg)' }}
      icon={<ShieldCheckSmall />}
      title="Decision gate"
      subtitle="terminal · reads run/"
      right={<Lock size={13} className="shrink-0 text-text-3" aria-label="non-removable" />}
    >
      <div className="flex flex-col gap-1 px-3 pt-1">
        {GATE_CHECKPOINTS.map((c) => (
          <div key={c.label} className="flex items-center gap-1.5">
            <span className="h-[7px] w-[7px] rounded-full" style={{ background: c.c }} />
            <span className="text-[11px] font-medium text-text-2">{c.label}</span>
          </div>
        ))}
      </div>
      <div className="absolute inset-x-0 bottom-0 overflow-hidden rounded-b-[10px] border-t border-line bg-card-2 px-3 py-2">
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
    </CanvasCardFrame>
  )
}

// One ADVISORY fan-out port on the agent card's perimeter — a dashed ACCENT ring, deliberately NOT a
// half-circle data port (an advisory link never carries data). Rendered as a canvas-plane sibling.
function AdvisoryPortMarker({ x, y }: { x: number; y: number }) {
  const R = 6
  return (
    <span
      className="pointer-events-none absolute z-[4] rounded-full"
      title="advisory link · off-gate (no data)"
      style={{
        left: x - R,
        top: y - R,
        width: 2 * R,
        height: 2 * R,
        background: 'var(--color-accent-weak)',
        border: '1.5px dashed var(--color-accent)',
        boxSizing: 'border-box',
      }}
    />
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
  laid,
  isView,
  selected,
  renaming,
  connectMode,
  connectFrom,
  advisoryShown,
  advisoryOn,
  onAdvisoryToggle,
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
  laid: LaidPort[]
  isView: boolean
  selected: boolean
  renaming: boolean
  connectMode: boolean
  connectFrom: string | null
  advisoryShown: boolean
  advisoryOn: boolean
  onAdvisoryToggle: () => void
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
  const armedNode = connectFrom != null && connectFrom.split('|')[0] === n.id
  const highlight = armedNode || selected
  const Icon = ICONS[n.icon]
  const H = nodeHeight(n)
  // `laid` is the DYNAMIC nearest-side port placement, computed once for the whole graph in the parent
  // (computeGraphPortLayout) and passed in — so the card render and the wire anchors share one layout.
  // Left spine carries the bound run's per-step status (passed/attention/blocked) exactly like the seeded
  // ToolCard; neutral when the node has no bound run — a hand-composed node, or Edit mode (ADR-0019).
  const rail = n.vstatus ? RUN_STATUS[runStatusOf(isView, n.vstatus)].rail : RUN_STATUS.notrun.rail
  return (
    <div
      onMouseDown={(e) => onDown(n.id, e)}
      onContextMenu={onContextMenu}
      // Card-state shading (default / hover / selected) via .pg-node (item 1) — box-shadow lives in
      // the class so :hover lifts; the inline border keeps the highlight (armed/selected) accent rail.
      className={`pg-node absolute select-none${highlight ? ' is-selected' : ''}`}
      style={{
        left: n.x,
        top: n.y,
        width: UW,
        height: H,
        background: 'var(--color-card)',
        border: `1px solid ${highlight ? 'var(--color-accent)' : 'var(--color-line-strong)'}`,
        borderLeft: `3px solid ${highlight ? 'var(--color-accent)' : rail}`,
        borderRadius: 11,
        cursor: connectMode ? 'default' : 'grab',
        // overflow VISIBLE so the half-circle ports poke past the card edge (ports are left/right only,
        // numbered OUTSIDE — batch 3a — so no top gutter is needed).
        overflow: 'visible',
        zIndex: selected ? 6 : 5,
      }}
    >
      <div className="flex items-center gap-1.5 px-2.5" style={{ height: CARD_HEADER_H }}>
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
              className="block w-full rounded border border-accent bg-card px-1 py-0.5 font-mono text-[11.5px] font-semibold text-text outline-none"
            />
          ) : (
            <span
              onDoubleClick={(e) => {
                if (isView) return
                e.stopPropagation()
                onStartRename(n.id)
              }}
              className="block truncate font-mono text-[11.5px] font-semibold text-text"
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
      {/* Typed half-circle ports on all four sides, kind + state coloured. WIREABLE ports (required /
          optional) carry data-* so drag-to-connect resolves a drop via elementFromPoint; out ports
          start a wire on mousedown, in/out both arm click-to-connect. RESERVED ports render but are
          NON-connectable — no data-* (elementFromPoint ignores them) and no handlers. */}
      {laid.map((p) => {
        if (p.state === 'reserved') {
          return (
            <span
              key={p.cidx}
              className="pointer-events-none absolute"
              title={`#${p.cidx} · ${p.kind} · ${p.dir} · reserved`}
              style={{ ...portBoxStyle(p), borderWidth: 1.5, borderStyle: 'solid', zIndex: 4, ...portVisualStyle(p) }}
            />
          )
        }
        const armed = connectFrom === `${n.id}|${p.dir}|${p.idx}`
        return (
          <span
            key={p.cidx}
            data-port="1"
            data-node={n.id}
            data-side={p.dir}
            data-idx={p.idx}
            data-kind={p.kind}
            title={`#${p.cidx} · ${p.kind} · ${p.dir} · ${p.state}`}
            onMouseDown={(e) => {
              if (p.dir === 'out') onStartWireDrag(n.id, p.idx, e)
              else e.stopPropagation()
            }}
            onClick={(e) => {
              e.stopPropagation()
              onPortTap(n.id, p.dir, p.idx)
            }}
            style={{
              ...portBoxStyle(p),
              borderWidth: 1.5,
              borderStyle: 'solid',
              zIndex: 7,
              ...portVisualStyle(p),
              ...(armed ? { background: 'var(--color-accent)', borderColor: 'var(--color-accent)' } : {}),
              cursor: connectMode ? 'pointer' : p.dir === 'out' ? 'crosshair' : 'default',
            }}
          />
        )
      })}
      {laid.map((p) => (
        <PortIndexChip key={`c${p.cidx}`} p={p} w={UW} />
      ))}
      {/* ADVISORY agent-attach point (item 2) — a small dashed-accent badge hugging the top-right corner,
          DISTINCT from the half-circle data ports (an advisory link, not a data edge). Click toggles the
          agent's attachment to THIS tool; when attached it fills accent. Off-gate: never a data/verdict edge. */}
      {advisoryShown && (
        <button
          type="button"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation()
            onAdvisoryToggle()
          }}
          title={advisoryOn ? 'Advisory agent attached — click to detach' : 'Attach advisory agent (off-gate)'}
          className="absolute z-[7] grid place-items-center rounded-full"
          style={{
            left: ADV_BADGE_DX - ADV_BADGE_R,
            top: ADV_BADGE_DY - ADV_BADGE_R,
            width: 2 * ADV_BADGE_R,
            height: 2 * ADV_BADGE_R,
            boxSizing: 'border-box',
            background: advisoryOn ? 'var(--color-accent)' : 'var(--color-card)',
            border: `1.5px ${advisoryOn ? 'solid' : 'dashed'} var(--color-accent)`,
            color: advisoryOn ? '#fff' : 'var(--color-accent-strong)',
          }}
        >
          <Activity size={9} />
        </button>
      )}
      <CardBoxes laid={laid} />
      <div className="absolute inset-x-0 bottom-0 flex items-center border-t border-line px-2.5" style={{ height: CARD_FOOTER_H }}>
        <span className="inline-flex items-center gap-1.5 text-[8.5px] font-bold uppercase tracking-[0.4px] text-accent-strong">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          draft
        </span>
      </div>
    </div>
  )
}
