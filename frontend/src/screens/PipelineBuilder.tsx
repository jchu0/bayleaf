import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  GitBranch,
  LayoutGrid,
  Play,
  Plus,
  Save,
  Search,
  ShieldCheck,
  X,
} from 'lucide-react'
import { SegmentedControl } from '../components/SegmentedControl'
import { useToast } from '../components/Toast'
import type { SegmentOption } from '../components/SegmentedControl'
import { BuilderCanvas } from '../components/BuilderCanvas'
import { BuilderConsole } from '../components/BuilderConsole'
import { BuilderInspector } from '../components/BuilderInspector'
import { BuilderProfileCombobox } from '../components/BuilderProfileCombobox'
import { ArchivistModal, AuthorToolNodeModal, PipelineRepairModal, RunHandoffModal } from '../components/BuilderModals'
import {
  GRAPH_ID,
  ICONS,
  LINKED_RUN,
  ON_CYCLE,
  REFS,
  TOOLS,
  curLocMap,
  gateSegs,
  germlineTemplate,
  isEditableProfile,
  makeUserNode,
  mergedLoc,
  savedLocators,
  yamlFor,
  type ConsoleTab,
  type IconKey,
  type LocEdits,
  type Mode,
  type SaveStatus,
  type Tab,
  type UserEdge,
  type UserNode,
} from '../components/BuilderShared'
import { useRole } from '../context/RoleContext'
import { api } from '../api'

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
type PaletteItem = { name: string; sub: string; icon: IconKey; disabled?: boolean; onClick?: () => void }

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

  const [locEdits, setLocEdits] = useState<LocEdits>({})
  const [refLoc, setRefLoc] = useState<Record<string, string>>({})

  const [saveStatus, setSaveStatus] = useState<SaveStatus>('draft')
  const [version, setVersion] = useState(3)

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
    setVersion(1)
    setSaveStatus('draft')
    setEmitted(false)
    setEmittedSnap(null)
    setProfile(kind === 'blank' ? 'default' : 'giab_panel')
    setMode('edit')
    setNewOpen(false)
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
    setConnectMode(false)
    setConnectFrom(null)
    setVersion(3)
    setSaveStatus('draft')
    setEmitted(false)
    setEmittedSnap(null)
    setProfile('giab_panel')
    setMode('view')
  }
  const selTool = useMemo(() => TOOLS.find((t) => t.id === selected) ?? null, [selected])
  const selRef = useMemo(() => REFS.find((r) => r.id === selected) ?? null, [selected])
  const isGate = selected === 'g_gate'
  const isAgent = selected === 'a_qc_triage'
  const inspectorOn = !!(selTool || selRef || isGate || isAgent)

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
    setUserNodes((arr) => [...arr, makeUserNode(name, kind, arr.length)])
  }
  const removeNode = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setUserNodes((ns) => ns.filter((n) => n.id !== id))
    setUserEdges((es) => es.filter((ed) => ed.from.node !== id && ed.to.node !== id))
  }
  // Tidy = a flow-preserving auto-layout: place each node in the column of its longest-path depth
  // from a source (so upstream→downstream reads left→right), and stack parallel nodes in a column.
  // This keeps the connection structure legible instead of dropping every card into one row.
  const tidy = () =>
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
      for (const n of [...ns].sort((a, b) => (depth.get(a.id)! - depth.get(b.id)!) || a.x - b.x)) {
        const col = depth.get(n.id) ?? 0
        const row = rowOf.get(col) ?? 0
        rowOf.set(col, row + 1)
        pos.set(n.id, { x: 60 + col * 230, y: 56 + row * 120 })
      }
      return ns.map((n) => ({ ...n, ...(pos.get(n.id) ?? { x: n.x, y: n.y }) }))
    })

  const nodeDrag = (id: string, e: React.MouseEvent) => {
    if (connectMode) return
    e.preventDefault()
    const n0 = userNodes.find((n) => n.id === id)
    if (!n0) return
    const z = zoom
    const ox = e.clientX
    const oy = e.clientY
    const sx = n0.x
    const sy = n0.y
    const move = (ev: MouseEvent) =>
      setUserNodes((ns) => ns.map((n) => (n.id === id ? { ...n, x: sx + (ev.clientX - ox) / z, y: sy + (ev.clientY - oy) / z } : n)))
    const up = () => {
      document.removeEventListener('mousemove', move)
      document.removeEventListener('mouseup', up)
      // Snap to the 20px grid + clamp on release.
      setUserNodes((ns) =>
        ns.map((n) => (n.id === id ? { ...n, x: Math.max(0, Math.round(n.x / 20) * 20), y: Math.max(0, Math.round(n.y / 20) * 20) } : n)),
      )
    }
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', up)
  }

  // Port-to-port wiring. ENFORCE typed-port kind-matching (INV-e): an output kind connects only
  // to a matching input kind — free composition can never silently forge an invalid edge.
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
    const fromNode = userNodes.find((n) => n.id === fid)
    const toNode = userNodes.find((n) => n.id === id)
    if (!fromNode || !toNode) {
      setConnectFrom(null)
      return
    }
    if (fromNode.outs[fidx] !== toNode.ins[idx]) {
      // Kind mismatch — reject the edge, keep the graph honest, re-arm from scratch.
      setConnectFrom(null)
      return
    }
    const edge: UserEdge = { from: { node: fid, idx: fidx }, to: { node: id, idx } }
    const exists = userEdges.some(
      (x) => x.from.node === edge.from.node && x.from.idx === edge.from.idx && x.to.node === edge.to.node && x.to.idx === edge.to.idx,
    )
    setUserEdges(exists ? userEdges : [...userEdges, edge])
    setConnectFrom(null)
  }

  const toggleConnect = () => {
    setConnectMode((c) => !c)
    setConnectFrom(null)
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
        { name: 'QC-triage', sub: 'advisory · MVP', icon: 'activity', onClick: () => setSelected('a_qc_triage') },
        { name: 'Pipeline-repair', sub: 'advisory · proposes fixes', icon: 'wrench', onClick: () => setRepairOpen(true) },
        { name: 'Archivist', sub: 'advisory · cold storage', icon: 'archive', onClick: () => setArchivistOpen(true) },
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
          zoom={zoom}
          userNodes={userNodes}
          userEdges={userEdges}
          connectMode={connectMode}
          connectFrom={connectFrom}
          onSelect={setSelected}
          onZoom={setZoom}
          onToggleConnect={toggleConnect}
          onTidy={tidy}
          onNodeDrag={nodeDrag}
          onPortTap={portTap}
          onRemoveNode={removeNode}
        />

        {inspectorOn && (
          <BuilderInspector
            tool={selTool}
            reference={selRef}
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
            onClose={() => setSelected(null)}
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
      />

      {/* ── modals ── */}
      {runOpen && <RunHandoffModal envHint={envHint} onClose={() => setRunOpen(false)} />}
      {authorOpen && <AuthorToolNodeModal onClose={() => setAuthorOpen(false)} />}
      {repairOpen && <PipelineRepairModal onClose={() => setRepairOpen(false)} />}
      {archivistOpen && <ArchivistModal onClose={() => setArchivistOpen(false)} />}
      {newOpen && <NewPipelineModal onClose={() => setNewOpen(false)} onCreate={newPipeline} />}
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
                    const disabled = it.disabled || isView
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
