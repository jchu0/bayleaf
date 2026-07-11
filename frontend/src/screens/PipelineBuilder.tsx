import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BoxSelect,
  Check,
  ChevronLeft,
  ChevronRight,
  CopyPlus,
  Download,
  FolderOpen,
  Frame,
  GitBranch,
  LayoutGrid,
  Loader2,
  Pencil,
  Play,
  Plus,
  Save,
  Search,
  ShieldCheck,
  Trash2,
  Unlink,
  Wand2,
  X,
} from 'lucide-react'
import { SegmentedControl } from '../components/SegmentedControl'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/ConfirmDialog'
import type { SegmentOption } from '../components/SegmentedControl'
import { BuilderCanvas } from '../components/BuilderCanvas'
import type { CanvasMenuReq } from '../components/BuilderCanvas'
import { BuilderConsole } from '../components/BuilderConsole'
import { BuilderInspector } from '../components/BuilderInspector'
import { BuilderProfileCombobox } from '../components/BuilderProfileCombobox'
import { BuilderContextMenu, type MenuItem } from '../components/BuilderContextMenu'
import type { AlignKind, DistributeAxis } from '../components/SelectionActionBar'
import { ArchivistModal, AuthorToolNodeModal, PipelineRepairModal, RunHandoffModal } from '../components/BuilderModals'
import {
  GRAPH_ID,
  ICONS,
  LINKED_RUN,
  NODE_W,
  ON_CYCLE,
  REFS,
  TOOLS,
  curLocMap,
  duplicateNode,
  gateSegs,
  germlineTemplate,
  isEditableProfile,
  makeUserNode,
  mergedLoc,
  nodeHeight,
  reconcileEdges,
  renameNode,
  savedLocators,
  setNodeIcon,
  yamlFor,
  type BuilderGraphPayload,
  type ConsoleTab,
  type IconKey,
  type LocEdits,
  type Mode,
  type SaveStatus,
  type Tab,
  type UserEdge,
  type UserNode,
} from '../components/BuilderShared'
import { useTopologyHistory } from '../hooks/useTopologyHistory'
import { useRole } from '../context/RoleContext'
import { api } from '../api'
import type { DiffResult, DryRunResult, PipelineGraph } from '../types'

// Live alignment-guide snap threshold (content px) + a small module helper: for a dragged node's
// {left, centerX, right}/{top, middle, bottom} anchors, find the nearest other-node anchor within
// the threshold and report the guide line + the snapped node position. Zoom-safe because it operates
// entirely in CONTENT coordinates (the caller converts the pointer via getBoundingClientRect ÷ zoom).
const GUIDE_SNAP = 6
function alignGuides(
  nx: number,
  ny: number,
  dragged: UserNode,
  others: UserNode[],
): { x?: number; y?: number; snapx?: number; snapy?: number } {
  const dh = nodeHeight(dragged)
  const myX = [nx, nx + NODE_W / 2, nx + NODE_W]
  const myY = [ny, ny + dh / 2, ny + dh]
  let bestXd = GUIDE_SNAP
  let bestYd = GUIDE_SNAP
  let gx: number | undefined
  let gy: number | undefined
  let snapx: number | undefined
  let snapy: number | undefined
  for (const o of others) {
    const oh = nodeHeight(o)
    const oX = [o.x, o.x + NODE_W / 2, o.x + NODE_W]
    const oY = [o.y, o.y + oh / 2, o.y + oh]
    for (let a = 0; a < 3; a++) {
      for (let b = 0; b < 3; b++) {
        const dxv = Math.abs(myX[a] - oX[b])
        if (dxv < bestXd) {
          bestXd = dxv
          gx = oX[b]
          snapx = nx + (oX[b] - myX[a])
        }
        const dyv = Math.abs(myY[a] - oY[b])
        if (dyv < bestYd) {
          bestYd = dyv
          gy = oY[b]
          snapy = ny + (oY[b] - myY[a])
        }
      }
    }
  }
  return { x: gx, y: gy, snapx, snapy }
}

// The Pipeline Builder (#11) — the editable superset of the Provenance canvas: a left→right DAG
// the operator *configures* (nodes, locators, the advisory agent), whose sole grounded output is
// run_layout.yaml. It COMPOSES, never executes (primary action Emit; Run only hands off); rules
// decide the verdict at run time (never stored on the graph); agents are advisory + port-less.
// Defaults to a read-only linked View; Edit unlocks free composition + authoring. See §6/§7.

const SAVE_ST: Record<SaveStatus, { label: string; cls: string }> = {
  draft: { label: 'draft', cls: 'border-line-strong bg-card-2 text-text-2' },
  pending: { label: 'pending approval', cls: 'border-hold-bd bg-hold-bg text-hold-fg' },
  approved: { label: 'approved', cls: 'border-proceed-bd bg-proceed-bg text-proceed-fg' },
}

// Palette rows: click a tool/contamination tile to add a node; agents open their advisory modal
// (or select the QC-triage pill); the gate tile is pinned/disabled.
// `alwaysEnabled` exempts an item from the View-mode palette lock — used for the advisory agents,
// which are read-only (they open a modal / select the triage pill; they never mutate the pipeline),
// so an operator can consult them without switching the whole canvas into Edit.
type PaletteItem = { name: string; sub: string; icon: IconKey; disabled?: boolean; alwaysEnabled?: boolean; onClick?: () => void }

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

export function PipelineBuilder() {
  const { role, isApprover, toggleRole } = useRole()
  const { toast } = useToast()

  const [mode, setMode] = useState<Mode>('view') // defaults to read-only View (§5.9/§6)
  const [profile, setProfile] = useState<string>('giab_panel')
  const [profMenu, setProfMenu] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('locators') // authoring surface is the default tab
  const [paletteOpen, setPaletteOpen] = useState(true)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [consoleTab, setConsoleTab] = useState<ConsoleTab>('validate')
  const [emitted, setEmitted] = useState(false)
  const [emittedSnap, setEmittedSnap] = useState<Record<string, string> | null>(null)
  const [zoom, setZoom] = useState(1)

  const [userNodes, setUserNodes] = useState<UserNode[]>([])
  const [userEdges, setUserEdges] = useState<UserEdge[]>([])
  const [connectMode, setConnectMode] = useState(false)
  const [connectFrom, setConnectFrom] = useState<string | null>(null)

  // ── PB2 on-canvas editing state ──
  // `selected` (above) stays the inspector subject (seeded OR user node); these are orthogonal:
  //  - selNodes: the multi-selection, USER NODES ONLY (never a seeded/gate id) — drives group move,
  //    bulk delete, align/distribute, and every node ring.
  //  - selEdge: a selected user edge (index into userEdges) for deletion; null when none.
  const [selNodes, setSelNodes] = useState<Set<string>>(new Set())
  const [selEdge, setSelEdge] = useState<number | null>(null)
  const [renamingId, setRenamingId] = useState<string | null>(null) // node under inline rename
  const [guides, setGuides] = useState<{ x?: number; y?: number } | null>(null) // live drag guides
  const [menu, setMenu] = useState<CanvasMenuReq | null>(null) // right-click menu request
  const [fitNonce, setFitNonce] = useState(0) // bump to re-center (keyboard 'f' / menu Fit)

  const confirm = useConfirm()
  // Undo/redo over the canvas topology (nodes/edges). record() BEFORE each discrete mutation; reset()
  // on New/Cancel/Load. This is the safety net that keeps an edge-severing delete reversible.
  const hist = useTopologyHistory(userNodes, userEdges, setUserNodes, setUserEdges)

  const [locEdits, setLocEdits] = useState<LocEdits>({})
  const [refLoc, setRefLoc] = useState<Record<string, string>>({})

  const [saveStatus, setSaveStatus] = useState<SaveStatus>('draft')
  const [version, setVersion] = useState(3)

  // Backend Dry-run/Diff — available once the graph is Saved (they resolve the stored pipeline).
  const [savedName, setSavedName] = useState<string | null>(null)
  const [dryRun, setDryRun] = useState<DryRunResult | null>(null)
  const [dryRunBusy, setDryRunBusy] = useState(false)
  const [diff, setDiff] = useState<DiffResult | null>(null)
  const [diffBusy, setDiffBusy] = useState(false)

  const [runOpen, setRunOpen] = useState(false)
  const [authorOpen, setAuthorOpen] = useState(false)
  const [repairOpen, setRepairOpen] = useState(false)
  const [archivistOpen, setArchivistOpen] = useState(false)

  // Active-document identity: the builder normally opens the one seeded germline pipeline (the
  // LINKED doc). "New pipeline" switches to a fresh draft — 'blank' (empty canvas) or 'germline'
  // (seeded from the panel template). docName drives the toolbar id; only the original seeded
  // doc reads as "Linked".
  const [docKind, setDocKind] = useState<'germline' | 'blank'>('germline')
  const [docName, setDocName] = useState<string>(GRAPH_ID)
  const [newOpen, setNewOpen] = useState(false)
  const [loadOpen, setLoadOpen] = useState(false)

  const isView = mode === 'view'
  // Only the original seeded pipeline is the LINKED doc; a new draft (blank or template) is not.
  const isLinked = docKind === 'germline' && docName === GRAPH_ID
  const linkedView = isLinked && isView

  // Create a new pipeline document. Explicit authoring action, so it opens in Edit (View-default
  // only guards accidental edits to the EXISTING linked pipeline). Blank = empty canvas; template =
  // the germline panel chain instantiated as EDITABLE user nodes (draggable/wireable/removable) —
  // NOT the read-only seeded cards. Because the new doc's name is never GRAPH_ID it is not the
  // linked doc, so `showSeeded` is off and the composed nodes are what render. Resets version/status.
  function newPipeline(kind: 'blank' | 'germline', rawName: string) {
    const name = rawName.trim() || (kind === 'blank' ? 'PIPE-DRAFT' : 'PIPE-FROM-TEMPLATE')
    const seed = kind === 'germline' ? germlineTemplate() : { nodes: [], edges: [] }
    setDocKind(kind)
    setDocName(name)
    setUserNodes(seed.nodes)
    setUserEdges(seed.edges)
    setLocEdits({})
    setRefLoc({})
    setSelected(null)
    resetEditing()
    setVersion(1)
    setSaveStatus('draft')
    setEmitted(false)
    setEmittedSnap(null)
    setSavedName(null)
    setDryRun(null)
    setDiff(null)
    setProfile(kind === 'blank' ? 'default' : 'giab_panel')
    setMode('edit')
    setNewOpen(false)
  }

  // Load a previously-saved pipeline back into the builder (T-069 saved-profiles). A loaded graph is
  // a USER graph (docKind='blank' → not the seeded LINKED doc), so its composed nodes render and it
  // stays editable. savedName=pg.name means the graph already exists in the store, so Dry-run/Diff
  // resolve immediately. Re-saving mints a NEW draft version server-side, so loading an approved
  // graph never mutates it. Compose ≠ execute; no verdict is read or written.
  function loadSavedPipeline(pg: PipelineGraph) {
    const g = (pg.graph ?? {}) as BuilderGraphPayload
    const nodes = Array.isArray(g.nodes) ? g.nodes : []
    const edges = Array.isArray(g.edges) ? g.edges : []
    setDocKind('blank')
    setDocName(pg.name)
    setUserNodes(nodes)
    setUserEdges(edges)
    setLocEdits(g.locator_edits ?? {})
    setRefLoc(g.reference_locators ?? {})
    setSelected(null)
    resetEditing()
    setConnectMode(false)
    setConnectFrom(null)
    setProfile(pg.profile ?? 'default')
    setVersion(pg.version)
    setSaveStatus(pg.status === 'approved' ? 'approved' : pg.status === 'pending_review' ? 'pending' : 'draft')
    setEmitted(false)
    setEmittedSnap(null)
    setSavedName(pg.name) // graph is in the store → Dry-run/Diff can resolve it now
    setDryRun(null)
    setDiff(null)
    setMode(pg.status === 'approved' ? 'view' : 'edit') // approved opens read-only (existing behavior)
    setLoadOpen(false)
    // Honest signal when the saved envelope carries no restorable builder topology (foreign/older
    // schema_version) — never fabricate nodes.
    if (!nodes.length) toast(`Loaded ${pg.name} · v${pg.version} — no builder topology to restore (schema ${pg.schema_version})`, 'info')
    else toast(`Loaded ${pg.name} · v${pg.version} · ${pg.status}`, 'success')
  }

  // Cancel/exit a draft: discard the in-progress build and return to the original linked pipeline
  // (View). Restores the same initial state the builder opens in, so nothing composed leaks over.
  function cancelDraft() {
    setDocKind('germline')
    setDocName(GRAPH_ID)
    setUserNodes([])
    setUserEdges([])
    setLocEdits({})
    setRefLoc({})
    setSelected(null)
    resetEditing()
    setConnectMode(false)
    setConnectFrom(null)
    setVersion(3)
    setSaveStatus('draft')
    setEmitted(false)
    setEmittedSnap(null)
    setSavedName(null)
    setDryRun(null)
    setDiff(null)
    setProfile('giab_panel')
    setMode('view')
  }
  // A composed user node WINS over any seeded subject: a template/forked draft reuses seeded ids
  // (n_fastp, …) but must resolve to the EDITABLE inspector, never the read-only seeded card (§3.1).
  const selUserNode = useMemo(() => userNodes.find((n) => n.id === selected) ?? null, [userNodes, selected])
  const selTool = useMemo(() => (selUserNode ? null : (TOOLS.find((t) => t.id === selected) ?? null)), [selUserNode, selected])
  const selRef = useMemo(() => (selUserNode ? null : (REFS.find((r) => r.id === selected) ?? null)), [selUserNode, selected])
  const isGate = !selUserNode && selected === 'g_gate'
  const isAgent = !selUserNode && selected === 'a_qc_triage'
  const inspectorOn = !!(selUserNode || selTool || selRef || isGate || isAgent)

  // ── selection model ──
  // selectNode: seeded/gate ids set only `selected` (inspectable, never delete-eligible); a user node
  // sets both `selected` + `selNodes` (additive shift/cmd toggles it into the set).
  const selectNode = (id: string, additive: boolean) => {
    const isUser = userNodes.some((n) => n.id === id)
    if (additive && isUser) {
      setSelNodes((s) => {
        const next = new Set(s)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      })
      setSelected(id)
    } else {
      setSelected(id)
      setSelNodes(isUser ? new Set([id]) : new Set())
    }
    setSelEdge(null)
  }
  const clearSelection = () => {
    setSelected(null)
    setSelNodes(new Set())
    setSelEdge(null)
  }
  const selectEdge = (i: number | null) => {
    setSelEdge(i)
    if (i != null) {
      setSelected(null)
      setSelNodes(new Set())
    }
  }
  // Canvas onSelect: null clears everything; a non-null id (seeded card or user node) selects it.
  const handleSelect = (id: string | null) => {
    if (id == null) clearSelection()
    else selectNode(id, false)
  }
  const onMarquee = (ids: string[]) => {
    setSelNodes(new Set(ids))
    setSelected(ids.length ? ids[ids.length - 1] : null)
    setSelEdge(null)
  }
  // Reset all selection + history — shared by New / Cancel / Load.
  const resetEditing = () => {
    setSelNodes(new Set())
    setSelEdge(null)
    setRenamingId(null)
    setGuides(null)
    setMenu(null)
    hist.reset()
  }

  const locEditable = isEditableProfile(profile) && !isView
  const yaml = yamlFor(profile, locEdits)
  const curLoc = curLocMap(locEdits)
  const envHint = `PIPEGUARD_RUN_LAYOUT=${profile}`

  // ── locator authoring (writes locEdits, marks the graph dirty → back to draft) ──
  const dirtyToDraft = () => setSaveStatus('draft')
  const setLoc = (kind: string, field: 'loc' | 'parser', value: string) => {
    if (!locEditable) return
    setLocEdits((m) => ({ ...m, [kind]: { ...(m[kind] ?? {}), [field]: value } }))
    dirtyToDraft()
  }
  const toggleRequired = (kind: string) => {
    if (!locEditable) return
    const cur = mergedLoc(kind, locEdits).required
    setLocEdits((m) => ({ ...m, [kind]: { ...(m[kind] ?? {}), required: !cur } }))
    dirtyToDraft()
  }
  const cycleOnMultiple = (kind: string) => {
    if (!locEditable) return
    const cur = mergedLoc(kind, locEdits).on
    setLocEdits((m) => ({ ...m, [kind]: { ...(m[kind] ?? {}), on: ON_CYCLE[cur] } }))
    dirtyToDraft()
  }

  // ── save · approval (wired to the real lifecycle store) ──
  // The backend name must be a slug; the display docName is preserved if it already is one.
  const pipelineName = () =>
    docName.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'pipeline'

  const onSave = async () => {
    const name = pipelineName()
    setSaveStatus('pending') // optimistic
    try {
      // Save creates a draft version, then submit moves it draft → pending_review so Approve is
      // actionable against the real store (off the decision domain; only approved graphs emit, §7).
      // F2: the authored locators ride INSIDE the tolerant graph envelope (nodes + edges +
      // locators + reference locators), so a saved pipeline round-trips the run_layout authoring —
      // not just the node/edge topology. The backend `graph` is a free-form dict, so no schema
      // change is needed; a later load path can rehydrate locEdits/refLoc from here.
      const ack = await api.savePipeline({
        name,
        graph: {
          nodes: userNodes,
          edges: userEdges,
          // The merged full locator LIST (backend-consumable shape) so dry-run/diff can resolve a
          // saved pipeline; keep the raw edits too for a future load path to rehydrate the UI.
          locators: savedLocators(locEdits),
          locator_edits: locEdits,
          reference_locators: refLoc,
        },
        profile,
      })
      const t = await api.submitPipeline(name)
      setVersion(ack.version)
      setSavedName(name) // the graph now exists in the store — Dry-run/Diff can resolve it
      setDryRun(null)
      setDiff(null)
      setSaveStatus(t.status === 'approved' ? 'approved' : t.status === 'pending_review' ? 'pending' : 'draft')
      toast(`Saved ${name} · v${ack.version} · ${t.status}`, 'success')
    } catch (e) {
      setSaveStatus('draft') // reconcile: the write didn't land
      toast(`Couldn't save pipeline — ${errMsg(e)}`, 'error')
    }
  }
  const onApprove = async () => {
    if (!isApprover) return
    const name = pipelineName()
    setSaveStatus('approved') // optimistic
    try {
      const t = await api.approvePipeline(name)
      setVersion(t.version)
      toast(`Approved ${name} · v${t.version}`, 'success')
    } catch (e) {
      setSaveStatus('pending') // reconcile: approve failed, stays pending
      toast(`Couldn't approve pipeline — ${errMsg(e)}`, 'error')
    }
  }

  // ── backend Dry-run / Diff (available once Saved) ──
  const onBackendDryRun = async (rid: string) => {
    if (!savedName || !rid) return
    setDryRunBusy(true)
    try {
      setDryRun(await api.dryRunPipeline(savedName, rid))
    } catch (e) {
      toast(`Dry-run failed — ${errMsg(e)}`, 'error')
    } finally {
      setDryRunBusy(false)
    }
  }
  const onBackendDiff = async () => {
    if (!savedName) return
    setDiffBusy(true)
    try {
      setDiff(await api.pipelineDiff(savedName))
    } catch (e) {
      toast(`Diff failed — ${errMsg(e)}`, 'error')
    } finally {
      setDiffBusy(false)
    }
  }

  // ── emit / validate ──
  const onEmit = () => {
    setDrawerOpen(true)
    setConsoleTab('validate')
    setEmitted(true)
    setEmittedSnap(curLoc) // snapshot for the Diff tab
    // Emit COMPOSES — it never executes. Demo logs the layout; a wired backend hands it to ingest.
    console.log(`# ${envHint}\n${yaml}`)
  }
  const onValidate = () => {
    setDrawerOpen(true)
    setConsoleTab('validate')
  }

  // ── free composition ──
  const addNode = (name: string, kind: string) => {
    if (isView) return
    hist.record()
    setUserNodes((arr) => [...arr, makeUserNode(name, kind, arr.length)])
  }

  // ── delete policy (the maintainer's "no accidental cascade" rule) ──
  // A delete that severs ≥1 wire, or a multi-node delete, is a cascade → confirm first (danger tone).
  // An isolated single node (no wires) is a one-click delete. EVERY delete is undoable (⌘Z), and the
  // toast says so — undo is the standing safety net. The card × and inspector Delete both route here.
  const deleteNodes = async (ids: string[]) => {
    if (isView) return
    const nodeIds = ids.filter((id) => userNodes.some((n) => n.id === id))
    if (!nodeIds.length) return
    const severed = userEdges.filter((e) => nodeIds.includes(e.from.node) || nodeIds.includes(e.to.node)).length
    if (nodeIds.length > 1 || severed >= 1) {
      const ok = await confirm({
        tone: 'danger',
        title: nodeIds.length > 1 ? `Delete ${nodeIds.length} nodes?` : 'Delete node?',
        body:
          severed > 0
            ? `This also removes ${severed} connected wire${severed === 1 ? '' : 's'}. You can undo (⌘Z).`
            : 'You can undo (⌘Z).',
        confirmLabel: 'Delete',
      })
      if (!ok) return
    }
    hist.record()
    setUserNodes((ns) => ns.filter((n) => !nodeIds.includes(n.id)))
    setUserEdges((es) => es.filter((e) => !nodeIds.includes(e.from.node) && !nodeIds.includes(e.to.node)))
    clearSelection()
    toast(
      `Deleted ${nodeIds.length} node${nodeIds.length === 1 ? '' : 's'}${severed ? ` · ${severed} wire${severed === 1 ? '' : 's'} removed` : ''} — ⌘Z to undo`,
      'info',
    )
  }
  const removeNode = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    void deleteNodes([id])
  }
  // A single wire is a directly-targeted object (its own × / hit-path), not a cascade → one-click, undoable.
  const deleteEdge = (i: number) => {
    if (isView) return
    if (!userEdges[i]) return
    hist.record()
    setUserEdges((es) => es.filter((_, idx) => idx !== i))
    setSelEdge(null)
    toast('Wire removed — ⌘Z to undo', 'info')
  }
  const deleteSelection = () => {
    if (isView) return
    if (selNodes.size) void deleteNodes([...selNodes])
    else if (selEdge != null) deleteEdge(selEdge)
    else if (selUserNode) void deleteNodes([selUserNode.id])
  }
  const disconnectNode = (id: string) => {
    const incident = userEdges.filter((e) => e.from.node === id || e.to.node === id).length
    if (!incident) return
    hist.record()
    setUserEdges((es) => es.filter((e) => e.from.node !== id && e.to.node !== id))
    toast(`Disconnected ${incident} wire${incident === 1 ? '' : 's'} — ⌘Z to undo`, 'info')
  }

  // ── node authoring (rename / icon / typed ports) ── each a discrete, undoable draft mutation. Port
  // edits reconcile edges so no dangling/mistyped wire survives (honest typed graph).
  const renameNodeTo = (id: string, name: string) => {
    const cur = userNodes.find((n) => n.id === id)
    if (!cur) return
    const nm = name.trim()
    if (!nm) {
      toast('Node name can’t be empty', 'error')
      return
    }
    if (nm === cur.name) return
    hist.record()
    setUserNodes((ns) => renameNode(ns, id, nm))
  }
  const setNodeIconTo = (id: string, icon: IconKey) => {
    hist.record()
    setUserNodes((ns) => setNodeIcon(ns, id, icon))
  }
  const addPort = (id: string, dir: 'ins' | 'outs', kind: string) => {
    hist.record()
    setUserNodes((ns) => ns.map((n) => (n.id === id ? { ...n, [dir]: [...n[dir], kind] } : n)))
  }
  const removePort = (id: string, dir: 'ins' | 'outs', idx: number) => {
    hist.record()
    const side = dir === 'ins' ? 'to' : 'from'
    const nextNodes = userNodes.map((n) => (n.id === id ? { ...n, [dir]: n[dir].filter((_, i) => i !== idx) } : n))
    // Drop wires on the removed port; re-index wires on later ports of this node (shift down by one).
    const nextEdges = userEdges
      .filter((e) => !(e[side].node === id && e[side].idx === idx))
      .map((e) => (e[side].node === id && e[side].idx > idx ? { ...e, [side]: { node: id, idx: e[side].idx - 1 } } : e))
    setUserNodes(nextNodes)
    setUserEdges(reconcileEdges(nextNodes, nextEdges))
  }
  const setPortKind = (id: string, dir: 'ins' | 'outs', idx: number, kind: string) => {
    hist.record()
    const nextNodes = userNodes.map((n) => (n.id === id ? { ...n, [dir]: n[dir].map((k, i) => (i === idx ? kind : k)) } : n))
    setUserNodes(nextNodes)
    const reconciled = reconcileEdges(nextNodes, userEdges)
    if (reconciled.length !== userEdges.length) {
      setUserEdges(reconciled)
      const dropped = userEdges.length - reconciled.length
      toast(`Retyped port — ${dropped} wire${dropped === 1 ? '' : 's'} removed`, 'info')
    }
  }
  const duplicateById = (id: string) => {
    const n = userNodes.find((x) => x.id === id)
    if (!n) return
    hist.record()
    const copy = duplicateNode(n)
    setUserNodes((ns) => [...ns, copy])
    setSelNodes(new Set([copy.id]))
    setSelected(copy.id)
    setSelEdge(null)
  }
  const duplicateSelection = () => {
    if (isView) return
    const ids = [...selNodes].filter((id) => userNodes.some((n) => n.id === id))
    const src = ids.length ? userNodes.filter((n) => ids.includes(n.id)) : selUserNode ? [selUserNode] : []
    if (!src.length) return
    hist.record()
    const copies = src.map((n, i) => duplicateNode(n, i))
    setUserNodes((ns) => [...ns, ...copies])
    setSelNodes(new Set(copies.map((c) => c.id)))
    setSelected(copies[0].id)
    setSelEdge(null)
  }
  const selectAll = () => {
    if (!userNodes.length) return
    const ids = userNodes.map((n) => n.id)
    setSelNodes(new Set(ids))
    setSelected(ids[ids.length - 1])
    setSelEdge(null)
  }

  // ── align / distribute (multi-selection) ──
  const alignSelection = (kind: AlignKind) => {
    const ids = [...selNodes].filter((id) => userNodes.some((n) => n.id === id))
    if (ids.length < 2) return
    const sel = userNodes.filter((n) => ids.includes(n.id))
    const left = Math.min(...sel.map((n) => n.x))
    const right = Math.max(...sel.map((n) => n.x + NODE_W))
    const top = Math.min(...sel.map((n) => n.y))
    const bottom = Math.max(...sel.map((n) => n.y + nodeHeight(n)))
    hist.record()
    setUserNodes((ns) =>
      ns.map((n) => {
        if (!ids.includes(n.id)) return n
        const h = nodeHeight(n)
        let x = n.x
        let y = n.y
        if (kind === 'left') x = left
        else if (kind === 'right') x = right - NODE_W
        else if (kind === 'hcenter') x = (left + right) / 2 - NODE_W / 2
        else if (kind === 'top') y = top
        else if (kind === 'bottom') y = bottom - h
        else if (kind === 'vmiddle') y = (top + bottom) / 2 - h / 2
        return { ...n, x: Math.round(x), y: Math.round(y) }
      }),
    )
  }
  const distributeSelection = (axis: DistributeAxis) => {
    const ids = [...selNodes].filter((id) => userNodes.some((n) => n.id === id))
    if (ids.length < 3) return
    const sel = userNodes.filter((n) => ids.includes(n.id))
    const key = axis === 'h' ? 'x' : 'y'
    const sorted = [...sel].sort((a, b) => a[key] - b[key])
    const min = sorted[0][key]
    const max = sorted[sorted.length - 1][key]
    const step = (max - min) / (sorted.length - 1)
    const pos = new Map(sorted.map((n, i) => [n.id, Math.round(min + i * step)]))
    hist.record()
    setUserNodes((ns) => ns.map((n) => (pos.has(n.id) ? { ...n, [key]: pos.get(n.id)! } : n)))
  }

  // Tidy = a flow-preserving auto-layout: place each node in the column of its longest-path depth
  // from a source (so upstream→downstream reads left→right), and stack parallel nodes in a column.
  // This keeps the connection structure legible instead of dropping every card into one row.
  const tidy = () => {
    if (!userNodes.length) return
    hist.record()
    setUserNodes((ns) => {
      if (!ns.length) return ns
      const depth = new Map(ns.map((n) => [n.id, 0]))
      // Relax longest-path depths over the DAG (|V| passes is a safe upper bound).
      for (let i = 0; i < ns.length; i++) {
        for (const e of userEdges) {
          const d = (depth.get(e.from.node) ?? 0) + 1
          if (d > (depth.get(e.to.node) ?? 0)) depth.set(e.to.node, d)
        }
      }
      const rowOf = new Map<number, number>() // next free row per column
      const pos = new Map<string, { x: number; y: number }>()
      // Deterministic order: by depth, then original x, so a re-tidy is stable.
      for (const n of [...ns].sort((a, b) => depth.get(a.id)! - depth.get(b.id)! || a.x - b.x)) {
        const col = depth.get(n.id) ?? 0
        const row = rowOf.get(col) ?? 0
        rowOf.set(col, row + 1)
        pos.set(n.id, { x: 60 + col * 230, y: 56 + row * 120 })
      }
      return ns.map((n) => ({ ...n, ...(pos.get(n.id) ?? { x: n.x, y: n.y }) }))
    })
  }

  // Node drag — click-vs-drag threshold decides select vs move; a multi-selection moves as a group.
  // Deltas divide by `zoom` (content units). Single-node drags snap to alignment guides live; all
  // moved nodes grid-snap + clamp ≥0 on release.
  const nodeDrag = (id: string, e: React.MouseEvent) => {
    if (connectMode) return
    if (isView) {
      selectNode(id, false) // View: click selects for inspection, never drags
      return
    }
    e.preventDefault()
    const additive = e.shiftKey || e.metaKey || e.ctrlKey
    const inGroup = selNodes.has(id) && selNodes.size > 1
    if (!inGroup) selectNode(id, additive) // show the ring immediately during a fresh drag
    const dragged = userNodes.find((n) => n.id === id)
    if (!dragged) return
    const group = inGroup ? [...selNodes].filter((gid) => userNodes.some((n) => n.id === gid)) : [id]
    const baselines = new Map(group.map((gid) => [gid, { x: userNodes.find((n) => n.id === gid)!.x, y: userNodes.find((n) => n.id === gid)!.y }]))
    const others = userNodes.filter((n) => !group.includes(n.id))
    const z = zoom
    const ox = e.clientX
    const oy = e.clientY
    let moved = false
    let recorded = false
    const move = (ev: MouseEvent) => {
      if (!moved && Math.hypot(ev.clientX - ox, ev.clientY - oy) < 3) return
      moved = true
      if (!recorded) {
        hist.record()
        recorded = true
      }
      const dx = (ev.clientX - ox) / z
      const dy = (ev.clientY - oy) / z
      if (group.length === 1) {
        const base = baselines.get(id)!
        let nx = base.x + dx
        let ny = base.y + dy
        const g = alignGuides(nx, ny, dragged, others)
        if (g.snapx != null) nx = g.snapx
        if (g.snapy != null) ny = g.snapy
        setGuides(g.x != null || g.y != null ? { x: g.x, y: g.y } : null)
        setUserNodes((ns) => ns.map((n) => (n.id === id ? { ...n, x: nx, y: ny } : n)))
      } else {
        setUserNodes((ns) => ns.map((n) => (group.includes(n.id) ? { ...n, x: baselines.get(n.id)!.x + dx, y: baselines.get(n.id)!.y + dy } : n)))
      }
    }
    const up = () => {
      document.removeEventListener('mousemove', move)
      document.removeEventListener('mouseup', up)
      setGuides(null)
      if (!moved) {
        if (inGroup) selectNode(id, additive) // a click inside a group collapses to just this node
        return
      }
      setUserNodes((ns) =>
        ns.map((n) => (group.includes(n.id) ? { ...n, x: Math.max(0, Math.round(n.x / 20) * 20), y: Math.max(0, Math.round(n.y / 20) * 20) } : n)),
      )
    }
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', up)
  }

  // Add a typed edge if valid (out→in, kind-matched, deduped). Shared by click-arm-click + drag-to-connect.
  const addEdgeIfValid = (fromNode: string, fromIdx: number, toNode: string, toIdx: number): boolean => {
    if (fromNode === toNode) return false
    const f = userNodes.find((n) => n.id === fromNode)
    const t = userNodes.find((n) => n.id === toNode)
    if (!f || !t || f.outs[fromIdx] == null || t.ins[toIdx] == null) return false
    if (f.outs[fromIdx] !== t.ins[toIdx]) return false
    const edge: UserEdge = { from: { node: fromNode, idx: fromIdx }, to: { node: toNode, idx: toIdx } }
    const exists = userEdges.some(
      (x) => x.from.node === edge.from.node && x.from.idx === edge.from.idx && x.to.node === edge.to.node && x.to.idx === edge.to.idx,
    )
    if (exists) return false
    hist.record()
    setUserEdges((es) => [...es, edge])
    return true
  }
  // Drag-to-connect drop: resolve + report an honest kind-mismatch (the canonical node-editor gesture,
  // layered over the same typed validation as click-arm-click).
  const onDropConnect = (fromNode: string, fromIdx: number, toNode: string, toIdx: number) => {
    const f = userNodes.find((n) => n.id === fromNode)
    const t = userNodes.find((n) => n.id === toNode)
    if (f && t && f.outs[fromIdx] != null && t.ins[toIdx] != null && f.outs[fromIdx] !== t.ins[toIdx]) {
      toast(`Can’t wire ${f.outs[fromIdx]} → ${t.ins[toIdx]} — port kinds must match`, 'error')
      return
    }
    addEdgeIfValid(fromNode, fromIdx, toNode, toIdx)
  }

  // Port-to-port wiring (click-arm-click). ENFORCE typed-port kind-matching (INV-e): an output kind
  // connects only to a matching input kind — free composition can never silently forge an invalid edge.
  const portTap = (id: string, side: 'in' | 'out', idx: number) => {
    if (!connectMode) return
    const key = `${id}|${side}|${idx}`
    if (!connectFrom) {
      if (side === 'out') setConnectFrom(key)
      return
    }
    const [fid, fside, fidxStr] = connectFrom.split('|')
    const fidx = Number(fidxStr)
    if (fid === id) {
      setConnectFrom(null)
      return
    }
    if (fside !== 'out') {
      setConnectFrom(side === 'out' ? key : null)
      return
    }
    if (side !== 'in') {
      setConnectFrom(key)
      return
    }
    addEdgeIfValid(fid, fidx, id, idx) // typed/dedup + history handled here
    setConnectFrom(null)
  }

  const toggleConnect = () => {
    setConnectMode((c) => !c)
    setConnectFrom(null)
  }

  // Undo/redo also clear selection — a restored topology may not contain the selected ids, and edge
  // indices shift, so keeping a stale selection would dangle (wrong × / off-by-one action-bar count).
  const doUndo = () => {
    hist.undo()
    clearSelection()
  }
  const doRedo = () => {
    hist.redo()
    clearSelection()
  }

  // ── inline rename (double-click a node name, or the context-menu / inspector) ──
  const startRename = (id: string) => setRenamingId(id)
  const commitRename = (id: string, name: string) => {
    setRenamingId(null)
    renameNodeTo(id, name)
  }
  const cancelRename = () => setRenamingId(null)

  // ── keyboard ── one window listener via a ref so the handler always sees fresh closures without
  // re-subscribing. Never hijack typing (input/textarea/select/contentEditable); mutating keys are
  // Edit-only. Delete/Escape/undo-redo/arrows/duplicate/select-all + 'c' (Connect) / 'f' (Fit).
  const keyHandler = useRef<(e: KeyboardEvent) => void>(() => {})
  keyHandler.current = (e: KeyboardEvent) => {
    const t = e.target as HTMLElement | null
    if (t && (/^(input|textarea|select)$/i.test(t.tagName) || t.isContentEditable)) return
    const meta = e.metaKey || e.ctrlKey
    if (meta && (e.key === 'z' || e.key === 'Z')) {
      if (isView) return
      e.preventDefault()
      if (e.shiftKey) doRedo()
      else doUndo()
      return
    }
    if (meta && (e.key === 'y' || e.key === 'Y')) {
      if (isView) return
      e.preventDefault()
      doRedo()
      return
    }
    if (e.key === 'Escape') {
      clearSelection()
      setConnectMode(false)
      setConnectFrom(null)
      setMenu(null)
      setRenamingId(null)
      return
    }
    if (isView) return
    if (meta && (e.key === 'a' || e.key === 'A')) {
      e.preventDefault()
      selectAll()
      return
    }
    if (meta && (e.key === 'd' || e.key === 'D')) {
      e.preventDefault()
      duplicateSelection()
      return
    }
    if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault()
      deleteSelection()
      return
    }
    if (e.key.startsWith('Arrow')) {
      if (!selNodes.size) return
      const step = e.shiftKey ? 1 : 20
      const dx = e.key === 'ArrowLeft' ? -step : e.key === 'ArrowRight' ? step : 0
      const dy = e.key === 'ArrowUp' ? -step : e.key === 'ArrowDown' ? step : 0
      if (!dx && !dy) return
      e.preventDefault()
      hist.record()
      const ids = selNodes
      setUserNodes((ns) => ns.map((n) => (ids.has(n.id) ? { ...n, x: Math.max(0, n.x + dx), y: Math.max(0, n.y + dy) } : n)))
      return
    }
    if (e.key === 'c' || e.key === 'C') {
      toggleConnect()
      return
    }
    if (e.key === 'f' || e.key === 'F') {
      setFitNonce((v) => v + 1)
      return
    }
  }
  useEffect(() => {
    const h = (e: KeyboardEvent) => keyHandler.current(e)
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  // Right-click menu item sets (node / edge / canvas). Bounded, contextual (Disconnect disabled when
  // the node has no wires; Select-all/Tidy disabled on an empty canvas).
  const menuItems = (m: CanvasMenuReq): MenuItem[] => {
    if (m.kind === 'node' && m.nodeId) {
      const id = m.nodeId
      const incident = userEdges.some((e) => e.from.node === id || e.to.node === id)
      return [
        {
          label: 'Rename',
          icon: Pencil,
          onClick: () => {
            selectNode(id, false)
            setRenamingId(id)
          },
        },
        { label: 'Duplicate', icon: CopyPlus, onClick: () => duplicateById(id) },
        { label: 'Disconnect all wires', icon: Unlink, disabled: !incident, onClick: () => disconnectNode(id) },
        { label: 'Delete', icon: Trash2, danger: true, onClick: () => void deleteNodes([id]) },
      ]
    }
    if (m.kind === 'edge' && m.edgeIndex != null) {
      const i = m.edgeIndex
      return [{ label: 'Delete wire', icon: Trash2, danger: true, onClick: () => deleteEdge(i) }]
    }
    return [
      { label: 'Select all', icon: BoxSelect, disabled: !userNodes.length, onClick: selectAll },
      { label: 'Fit', icon: Frame, onClick: () => setFitNonce((v) => v + 1) },
      { label: 'Tidy', icon: Wand2, disabled: !userNodes.length, onClick: tidy },
    ]
  }

  // ── palette model ──
  const paletteSections: { heading: string; items: PaletteItem[] }[] = [
    {
      heading: 'Tool nodes',
      items: [
        { name: 'fastp', sub: 'fastq · fastp_json', icon: 'scissors', onClick: () => addNode('fastp', 'fastq') },
        { name: 'bwa-mem2', sub: 'fastq → bam', icon: 'merge', onClick: () => addNode('bwa-mem2', 'bam') },
        { name: 'samtools markdup', sub: 'bam · bai · metrics', icon: 'copy', onClick: () => addNode('samtools markdup', 'bam') },
        { name: 'mosdepth', sub: 'summary · thresholds', icon: 'bars', onClick: () => addNode('mosdepth', 'mosdepth_summary') },
        { name: 'bcftools call', sub: 'vcf', icon: 'dna', onClick: () => addNode('bcftools call', 'vcf') },
        { name: 'bcftools norm', sub: 'filtered_vcf', icon: 'funnel', onClick: () => addNode('bcftools norm', 'filtered_vcf') },
        { name: 'MultiQC', sub: 'multiqc_json', icon: 'layers', onClick: () => addNode('MultiQC', 'multiqc_json') },
      ],
    },
    {
      heading: 'References',
      items: [
        { name: 'Reference FASTA', sub: 'reference_fasta', icon: 'db', onClick: () => addNode('Reference FASTA', 'reference_fasta') },
        { name: 'Panel BED', sub: 'panel_bed', icon: 'db', onClick: () => addNode('Panel BED', 'panel_bed') },
        { name: 'Truth VCF', sub: 'truth_vcf', icon: 'db', onClick: () => addNode('Truth VCF', 'truth_vcf') },
      ],
    },
    {
      heading: 'Contamination',
      items: [{ name: 'NGSCheckMate', sub: 'ngscheckmate · optional', icon: 'bars', onClick: () => addNode('NGSCheckMate', 'ngscheckmate') }],
    },
    {
      heading: 'Agents',
      items: [
        { name: 'QC-triage', sub: 'advisory · MVP', icon: 'activity', alwaysEnabled: true, onClick: () => setSelected('a_qc_triage') },
        { name: 'Pipeline-repair', sub: 'advisory · proposes fixes', icon: 'wrench', alwaysEnabled: true, onClick: () => setRepairOpen(true) },
        { name: 'Archivist', sub: 'advisory · cold storage', icon: 'archive', alwaysEnabled: true, onClick: () => setArchivistOpen(true) },
      ],
    },
    { heading: 'Gate', items: [{ name: 'Decision gate', sub: 'terminal · pinned', icon: 'shield', disabled: true }] },
  ]

  const modeOptions: SegmentOption<Mode>[] = [
    { value: 'edit', label: 'Edit' },
    { value: 'view', label: 'View' },
  ]

  return (
    <div className="-mx-8 -my-7 flex h-[calc(100vh-3.5rem)] flex-col bg-card-2">
      {/* ── sub-header toolbar ── */}
      <div className="flex h-11 shrink-0 items-center gap-2.5 border-b border-line bg-card px-3.5">
        <SegmentedControl options={modeOptions} value={mode} onChange={setMode} />
        <button
          onClick={() => setNewOpen(true)}
          title="Create a new pipeline (blank or from template)"
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-line-strong bg-card px-2.5 py-1.5 text-[12.5px] font-medium text-text hover:border-line"
        >
          <Plus size={13} />
          New
        </button>
        <button
          onClick={() => setLoadOpen(true)}
          title="Open a previously-saved pipeline"
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-line-strong bg-card px-2.5 py-1.5 text-[12.5px] font-medium text-text hover:border-line"
        >
          <FolderOpen size={13} />
          Open
        </button>
        {!isLinked && (
          <button
            onClick={cancelDraft}
            title="Discard this draft and return to the linked pipeline"
            className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12.5px] font-medium text-text-2 hover:border-line-strong"
          >
            <X size={13} />
            Cancel
          </button>
        )}
        <span className="max-w-[200px] truncate font-mono text-[11.5px] font-semibold text-text">{docName}</span>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${
            linkedView ? 'border-[#cfe0fb] bg-accent-weak text-accent-strong' : 'border-line-strong bg-card-2 text-text-2'
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${linkedView ? 'bg-accent' : 'bg-text-3'}`} />
          {linkedView ? `Linked · ${LINKED_RUN}` : 'Draft — not run'}
        </span>

        <div className="ml-auto flex items-center gap-2">
          {/* save · version · approval (RBAC) */}
          <button
            onClick={onSave}
            title="Save a new version"
            className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong"
          >
            <Save size={13} />
            Save
          </button>
          <span className="font-mono text-[11px] text-text-3">v{version}</span>
          <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${SAVE_ST[saveStatus].cls}`}>
            {SAVE_ST[saveStatus].label}
          </span>
          {saveStatus === 'pending' && isApprover && (
            <button
              onClick={onApprove}
              className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-line"
            >
              <Check size={13} />
              Approve
            </button>
          )}
          <button
            onClick={toggleRole}
            title="Toggle RBAC role (demo)"
            className="rounded-md border border-line px-2 py-1 text-[10.5px] text-text-3 hover:text-text-2"
          >
            as {role}
          </button>

          <BuilderProfileCombobox
            profile={profile}
            open={profMenu}
            onToggle={() => setProfMenu((o) => !o)}
            onSelect={(p) => {
              setProfile(p)
              setProfMenu(false)
            }}
            onNewFromGraph={() => {
              setProfile('draft-from-graph')
              setSaveStatus('draft')
              setVersion(1)
              setProfMenu(false)
            }}
          />

          <button
            onClick={onValidate}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-line"
          >
            <ShieldCheck size={14} />
            Validate
          </button>
          <button
            onClick={onEmit}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white shadow-card transition-opacity hover:opacity-90"
          >
            <Download size={14} />
            Emit
          </button>
          <button
            onClick={() => setRunOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-line"
          >
            <Play size={14} />
            Run
          </button>
        </div>
      </div>

      {/* ── linked-run strip (the seeded linked pipeline, View only) ── */}
      {linkedView && (
        <div className="flex h-12 shrink-0 items-center gap-3.5 border-b border-line bg-card px-4">
          <span className="whitespace-nowrap text-[12px] text-text-2">
            Linked to <span className="font-mono font-semibold text-text">{LINKED_RUN}</span>
          </span>
          <div className="flex h-2 w-[170px] overflow-hidden rounded-[5px] bg-card-3">
            {gateSegs().map((s, i) => (
              <div key={i} style={{ width: s.w, background: s.c }} />
            ))}
          </div>
          <span className="text-[11.5px] text-text-3">proceed 3 · hold 1 · escalate 1</span>
          <div className="flex-1" />
          <Link
            to={`/runs/${LINKED_RUN}/provenance`}
            className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong"
          >
            Open Provenance
          </Link>
          <Link
            to={`/runs/${LINKED_RUN}`}
            className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 hover:border-line-strong"
          >
            Open Decision cards
          </Link>
          <button
            onClick={() => newPipeline('germline', `${GRAPH_ID}-fork`)}
            title="Copy the linked pipeline into an editable draft"
            className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-line"
          >
            <GitBranch size={13} />
            Fork to new draft
          </button>
        </div>
      )}

      {/* ── three panes ── */}
      <div className="flex min-h-0 flex-1">
        {paletteOpen ? (
          <Palette
            sections={paletteSections}
            isView={isView}
            onCollapse={() => setPaletteOpen(false)}
            onOpenAuthor={() => setAuthorOpen(true)}
          />
        ) : (
          <aside className="flex w-11 shrink-0 flex-col items-center gap-3 border-r border-line bg-card py-2.5">
            <button
              onClick={() => setPaletteOpen(true)}
              className="grid h-[27px] w-[27px] place-items-center rounded-md border border-line bg-card text-text-3 hover:text-text"
              title="Expand palette"
            >
              <ChevronRight size={14} />
            </button>
            <div className="h-px w-[22px] bg-line" />
            <LayoutGrid size={16} className="text-text-3" />
          </aside>
        )}

        <BuilderCanvas
          mode={mode}
          // Only the ORIGINAL linked pipeline renders the read-only seeded DAG; a new/forked draft
          // shows its editable composed nodes (germlineTemplate) instead, so the chain is modifiable.
          showSeeded={isLinked}
          selected={selected}
          selNodes={selNodes}
          selEdge={selEdge}
          zoom={zoom}
          userNodes={userNodes}
          userEdges={userEdges}
          connectMode={connectMode}
          connectFrom={connectFrom}
          guides={guides}
          renamingId={renamingId}
          canUndo={hist.canUndo}
          canRedo={hist.canRedo}
          fitNonce={fitNonce}
          onSelect={handleSelect}
          onSelectEdge={selectEdge}
          onDeleteEdge={deleteEdge}
          onMarquee={onMarquee}
          onZoom={setZoom}
          onToggleConnect={toggleConnect}
          onTidy={tidy}
          onUndo={doUndo}
          onRedo={doRedo}
          onNodeDrag={nodeDrag}
          onPortTap={portTap}
          onDropConnect={onDropConnect}
          onRemoveNode={removeNode}
          onStartRename={startRename}
          onCommitRename={commitRename}
          onCancelRename={cancelRename}
          onContextMenu={setMenu}
          onAlign={alignSelection}
          onDistribute={distributeSelection}
          onDuplicateSel={duplicateSelection}
          onDeleteSel={deleteSelection}
        />

        {inspectorOn && (
          <BuilderInspector
            tool={selTool}
            reference={selRef}
            userNode={selUserNode}
            isGate={isGate}
            isAgent={isAgent}
            isView={isView}
            tab={tab}
            locEdits={locEdits}
            locEditable={locEditable}
            refLoc={refLoc}
            onTab={setTab}
            onSetLoc={setLoc}
            onToggleRequired={toggleRequired}
            onCycleOnMultiple={cycleOnMultiple}
            onSetRefLoc={(id, value) => setRefLoc((m) => ({ ...m, [id]: value }))}
            onRenameNode={renameNodeTo}
            onSetNodeIcon={setNodeIconTo}
            onAddPort={addPort}
            onRemovePort={removePort}
            onSetPortKind={setPortKind}
            onDeleteNode={(id) => void deleteNodes([id])}
            onClose={clearSelection}
          />
        )}
      </div>

      {/* ── console ── */}
      <BuilderConsole
        open={drawerOpen}
        tab={consoleTab}
        profile={profile}
        yaml={yaml}
        emitted={emitted}
        isSarek={profile === 'sarek'}
        envHint={envHint}
        curLoc={curLoc}
        emittedSnap={emittedSnap}
        locEdits={locEdits}
        selected={selected}
        onToggle={() => setDrawerOpen((o) => !o)}
        onTab={(t) => {
          setConsoleTab(t)
          setDrawerOpen(true)
        }}
        onSelect={setSelected}
        savedName={savedName}
        dryRun={dryRun}
        dryRunBusy={dryRunBusy}
        onDryRun={onBackendDryRun}
        diff={diff}
        diffBusy={diffBusy}
        onDiff={onBackendDiff}
      />

      {/* ── modals ── */}
      {runOpen && (
        <RunHandoffModal
          envHint={envHint}
          profile={profile}
          yaml={yaml}
          curLoc={curLoc}
          savedName={savedName}
          onEmit={onEmit}
          onClose={() => setRunOpen(false)}
        />
      )}
      {authorOpen && <AuthorToolNodeModal onClose={() => setAuthorOpen(false)} />}
      {repairOpen && <PipelineRepairModal onClose={() => setRepairOpen(false)} />}
      {archivistOpen && <ArchivistModal onClose={() => setArchivistOpen(false)} />}
      {newOpen && <NewPipelineModal onClose={() => setNewOpen(false)} onCreate={newPipeline} />}
      {loadOpen && <LoadSavedModal onClose={() => setLoadOpen(false)} onLoad={loadSavedPipeline} />}
      {menu && <BuilderContextMenu x={menu.x} y={menu.y} items={menuItems(menu)} onClose={() => setMenu(null)} />}
    </div>
  )
}

// "New pipeline" choice modal — blank canvas or seeded-from-template, with an optional name.
// Composes a new draft document; it never runs anything (compose != execute).
function NewPipelineModal({
  onClose,
  onCreate,
}: {
  onClose: () => void
  onCreate: (kind: 'blank' | 'germline', name: string) => void
}) {
  const [kind, setKind] = useState<'blank' | 'germline'>('blank')
  const [name, setName] = useState('')
  const choices = [
    ['blank', 'Blank graph', 'Start from an empty canvas — just the terminal Decision gate.'],
    ['germline', 'From template', 'Seed from the germline panel chain (fastp → … → MultiQC).'],
  ] as const
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-[460px] max-w-full overflow-hidden rounded-2xl border border-line bg-card shadow-pop">
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <h2 className="font-serif text-[18px] font-medium text-text">New pipeline</h2>
          <button
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-lg text-text-2 hover:bg-page"
            aria-label="Close"
          >
            <X size={17} />
          </button>
        </div>
        <div className="px-5 py-4">
          <p className="mb-3 text-[12.5px] leading-relaxed text-text-2">
            Composes a new pipeline document, opened in Edit as a fresh draft — your existing linked
            pipeline stays untouched. Emitting a config never runs a tool.
          </p>
          <div className="grid grid-cols-2 gap-2.5">
            {choices.map(([k, title, sub]) => (
              <button
                key={k}
                onClick={() => setKind(k)}
                className={`rounded-xl border p-3 text-left transition-colors ${
                  kind === k ? 'border-accent bg-accent-weak' : 'border-line hover:border-line-strong'
                }`}
              >
                <div className="text-[13px] font-semibold text-text">{title}</div>
                <div className="mt-0.5 text-[11.5px] leading-snug text-text-2">{sub}</div>
              </button>
            ))}
          </div>
          <label className="mt-4 block">
            <span className="text-[12px] font-medium text-text-2">Name (optional)</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="PIPE-2026-…"
              className="mt-1 w-full rounded-lg border border-line bg-card px-2.5 py-1.5 font-mono text-[12.5px] text-text outline-none focus:border-accent"
            />
          </label>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-line bg-card px-3.5 py-1.5 text-[13px] font-medium text-text-2 hover:bg-page"
          >
            Cancel
          </button>
          <button
            onClick={() => onCreate(kind, name)}
            className="rounded-lg bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-strong"
          >
            Create pipeline
          </button>
        </div>
      </div>
    </div>
  )
}

// "Open saved" modal — lists saved pipelines from the store (latest per name) and hydrates the
// builder from one (T-069 saved-profiles). Read-only fetch; honest loading/empty/error states;
// never invents a row. Approved graphs open read-only; loading one never mutates the store record.
function LoadSavedModal({ onClose, onLoad }: { onClose: () => void; onLoad: (pg: PipelineGraph) => void }) {
  const [rows, setRows] = useState<PipelineGraph[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    api
      .listPipelines()
      .then((r) => live && setRows(r))
      .catch((e) => live && setErr(errMsg(e)))
    return () => {
      live = false
    }
  }, [])
  const stFor = (s: PipelineGraph['status']): SaveStatus =>
    s === 'approved' ? 'approved' : s === 'pending_review' ? 'pending' : 'draft'
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-[460px] max-w-full overflow-hidden rounded-2xl border border-line bg-card shadow-pop">
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <h2 className="font-serif text-[18px] font-medium text-text">Open saved pipeline</h2>
          <button
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-lg text-text-2 hover:bg-page"
            aria-label="Close"
          >
            <X size={17} />
          </button>
        </div>
        <div className="max-h-[52vh] overflow-y-auto px-5 py-4">
          <p className="mb-3 text-[12.5px] leading-relaxed text-text-2">
            Loads a saved graph back into the builder — the latest version of each. Approved pipelines open
            read-only; loading one never mutates it. Compose ≠ execute.
          </p>
          {err ? (
            <div className="rounded-lg border border-hold-bd bg-hold-bg px-3 py-2.5 text-[12px] text-hold-fg">
              Couldn’t load saved pipelines — {err}
            </div>
          ) : rows === null ? (
            <p className="inline-flex items-center gap-1.5 text-[12.5px] text-text-3">
              <Loader2 size={13} className="animate-spin" /> Loading saved pipelines…
            </p>
          ) : rows.length === 0 ? (
            <p className="text-[12.5px] text-text-2">No saved pipelines yet — Save a draft to see it here.</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {rows.map((pg) => {
                const st = SAVE_ST[stFor(pg.status)]
                return (
                  <button
                    key={pg.id}
                    onClick={() => onLoad(pg)}
                    className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-left hover:border-line-strong hover:bg-page"
                  >
                    <span className="min-w-0 flex-1 truncate font-mono text-[12.5px] font-medium text-text">{pg.name}</span>
                    {pg.profile && <span className="shrink-0 text-[11px] text-text-3">{pg.profile}</span>}
                    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${st.cls}`}>{st.label}</span>
                    <span className="shrink-0 font-mono text-[10px] text-text-3">v{pg.version}</span>
                  </button>
                )
              })}
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-line bg-card px-3.5 py-1.5 text-[13px] font-medium text-text-2 hover:bg-page"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

function Palette({
  sections,
  isView,
  onCollapse,
  onOpenAuthor,
}: {
  sections: { heading: string; items: PaletteItem[] }[]
  isView: boolean
  onCollapse: () => void
  onOpenAuthor: () => void
}) {
  const [query, setQuery] = useState('')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const q = query.trim().toLowerCase()
  const filtered = q
    ? sections
        .map((s) => ({ ...s, items: s.items.filter((it) => it.name.toLowerCase().includes(q) || it.sub.toLowerCase().includes(q)) }))
        .filter((s) => s.items.length > 0)
    : sections

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-card">
      <div className="flex items-center gap-2 border-b border-line p-3">
        <div className="flex flex-1 items-center gap-2 rounded-lg border border-line bg-card-2 px-2.5 py-1.5 focus-within:border-accent">
          <Search size={14} className="shrink-0 text-text-3" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search nodes…"
            className="min-w-0 flex-1 bg-transparent text-[12.5px] text-text placeholder:text-text-3 focus:outline-none"
          />
        </div>
        <button onClick={onCollapse} className="grid h-7 w-7 place-items-center rounded-md border border-line text-text-3 hover:bg-page" title="Collapse">
          <ChevronLeft size={15} />
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-3.5 overflow-y-auto px-3 pb-4 pt-3">
        {filtered.length === 0 && <p className="px-1 pt-2 text-[11.5px] text-text-3">No nodes match “{query.trim()}”.</p>}
        {filtered.map((s) => {
          // Collapsible sections keep a long, growing palette navigable; a search overrides collapse
          // so matches are always visible. The count hints at how much each section holds.
          const isCollapsed = collapsed.has(s.heading) && !q
          return (
            <div key={s.heading}>
              <button
                onClick={() =>
                  setCollapsed((c) => {
                    const n = new Set(c)
                    if (n.has(s.heading)) n.delete(s.heading)
                    else n.add(s.heading)
                    return n
                  })
                }
                className="mb-1.5 flex w-full items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.5px] text-text-3 hover:text-text-2"
              >
                <ChevronRight size={11} className={`shrink-0 transition-transform ${isCollapsed ? '' : 'rotate-90'}`} />
                <span>{s.heading}</span>
                <span className="ml-auto font-mono normal-case text-text-3">{s.items.length}</span>
              </button>
              {!isCollapsed && (
                <div className="space-y-1.5">
                  {s.items.map((it) => {
                    const Icon = ICONS[it.icon]
                    const disabled = it.disabled || (isView && !it.alwaysEnabled)
                    return (
                      <div
                        key={it.name}
                        onClick={() => !disabled && it.onClick?.()}
                        className={`flex items-center gap-2.5 rounded-lg border px-2.5 py-2 ${
                          disabled ? 'cursor-not-allowed border-line bg-card-2 opacity-[0.65]' : 'cursor-pointer border-line bg-card hover:border-line-strong'
                        }`}
                      >
                        <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-card-2 ${disabled ? 'text-text-3' : 'text-text-2'}`}>
                          <Icon size={14} />
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate text-[12.5px] font-medium text-text">{it.name}</span>
                          <span className="block truncate font-mono text-[10px] text-text-3">{it.sub}</span>
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}

        {!isView ? (
          <div className="space-y-2.5">
            <button
              onClick={onOpenAuthor}
              className="flex w-full items-center gap-2 rounded-[9px] border border-dashed border-accent bg-accent-weak px-2.5 py-2.5"
            >
              <SparkleGlyph />
              <span className="flex-1 text-left">
                <span className="block text-[11.5px] font-semibold text-accent-strong">Author a tool node</span>
                <span className="block text-[9.5px] text-text-3">docs → proposed node · advisory</span>
              </span>
            </button>
            <div className="border-t border-line pt-2.5 text-[10.5px] leading-relaxed text-text-3">
              Click a tool to add it · drag to place · <strong className="text-text-2">Connect</strong> wires ports. Free composition is live.
            </div>
          </div>
        ) : (
          <div className="border-t border-line pt-2.5 text-[10.5px] leading-relaxed text-text-3">
            Read-only view. Switch to <strong className="text-text-2">Edit</strong> to add or modify nodes.
          </div>
        )}
      </div>
    </aside>
  )
}

function SparkleGlyph() {
  return (
    <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="var(--color-accent-strong)" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.4 2.4M15.3 15.3l2.4 2.4M17.7 6.3l-2.4 2.4M8.7 15.3l-2.4 2.4" />
    </svg>
  )
}
