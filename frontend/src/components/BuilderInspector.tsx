import { Link } from 'react-router-dom'
import { Activity, BarChart3, Lock, Plus, Trash2, X } from 'lucide-react'
import {
  ARTIFACT_KINDS,
  GIAB_LOC,
  ICON_CHOICES,
  ICONS,
  ON_CYCLE,
  RUNBOOK_ROWS,
  mergedLoc,
  type IconKey,
  type LocEdits,
  type OnMultiple,
  type Ref,
  type Tab,
  type Tool,
  type UserNode,
} from './BuilderShared'

// The 360px inspector. One panel, five subjects: a COMPOSED user node (name/icon/ports/locators/
// delete — the PB2 editable branch, which wins whenever a user node is selected), a seeded tool node
// (Params · Locators · I/O · Agents), the terminal gate (read-only runbook thresholds), the advisory
// agent (port-less), and a reference card. Locators is the load-bearing authoring surface — editable
// path/parser/on_multiple/required — while Params is a read-only schema display. Origin is never authored.

const IN_ORIGIN = (
  <div className="flex items-center gap-1.5 rounded-md border border-line bg-card-2 px-2 py-1.5">
    <Lock size={12} className="text-text-3" />
    <span className="text-[9.5px] uppercase tracking-[0.3px] text-text-3">origin</span>
    <span className="font-mono text-[11px] text-text-2">unknown</span>
    <span className="ml-auto text-[9.5px] text-text-3">stamped at ingest</span>
  </div>
)

type InspectorProps = {
  tool: Tool | null
  reference: Ref | null
  userNode: UserNode | null
  isGate: boolean
  isAgent: boolean
  isView: boolean
  tab: Tab
  locEdits: LocEdits
  locEditable: boolean
  refLoc: Record<string, string>
  onTab: (t: Tab) => void
  onSetLoc: (kind: string, field: 'loc' | 'parser', value: string) => void
  onToggleRequired: (kind: string) => void
  onCycleOnMultiple: (kind: string) => void
  onSetRefLoc: (id: string, value: string) => void
  // User-node authoring callbacks (PB2). Every one is a local draft mutation; the screen records
  // history + reconciles edges. Compose ≠ execute.
  onRenameNode: (id: string, name: string) => void
  onSetNodeIcon: (id: string, icon: IconKey) => void
  onAddPort: (id: string, dir: 'ins' | 'outs', kind: string) => void
  onRemovePort: (id: string, dir: 'ins' | 'outs', idx: number) => void
  onSetPortKind: (id: string, dir: 'ins' | 'outs', idx: number, kind: string) => void
  onDeleteNode: (id: string) => void
  onClose: () => void
}

export function BuilderInspector(props: InspectorProps) {
  const { tool, reference, userNode, isGate, isAgent } = props

  const header = ((): { title: string; sub: string; icon: React.ReactNode } => {
    if (userNode) {
      const Icon = ICONS[userNode.icon]
      return { title: userNode.name, sub: `${userNode.version} · composed node`, icon: <Icon size={16} /> }
    }
    if (tool) {
      const Icon = ICONS[tool.icon]
      return { title: tool.tool, sub: `${tool.version} · ${tool.stageLabel}`, icon: <Icon size={16} /> }
    }
    if (isGate) return { title: 'Decision gate', sub: 'terminal · reads run/ CSVs', icon: <ShieldGlyph /> }
    if (isAgent) return { title: 'QC-triage agent', sub: 'advisory · sonnet-mid', icon: <Activity size={16} /> }
    if (reference) return { title: reference.label, sub: `${reference.kind} · reference`, icon: <BarChart3 size={16} /> }
    return { title: '', sub: '', icon: null }
  })()

  return (
    <aside className="flex w-[360px] shrink-0 flex-col border-l border-line bg-card">
      <div className="flex items-center gap-2.5 border-b border-line px-4 py-3">
        <span className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-lg bg-card-2 text-text">{header.icon}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-semibold text-text">{header.title}</p>
          <p className="truncate font-mono text-[10.5px] text-text-3">{header.sub}</p>
        </div>
        <button onClick={props.onClose} className="grid h-7 w-7 place-items-center rounded-lg border border-line text-text-2 hover:bg-page">
          <X size={14} />
        </button>
      </div>

      {userNode ? (
        // A composed user node wins over every seeded subject (its id can collide with a seeded id
        // in a template draft — see the selUserNode-wins rule in the screen).
        <UserNodeInspector
          node={userNode}
          isView={props.isView}
          locEdits={props.locEdits}
          locEditable={props.locEditable}
          onRename={props.onRenameNode}
          onSetIcon={props.onSetNodeIcon}
          onAddPort={props.onAddPort}
          onRemovePort={props.onRemovePort}
          onSetPortKind={props.onSetPortKind}
          onDelete={props.onDeleteNode}
          onSetLoc={props.onSetLoc}
          onToggleRequired={props.onToggleRequired}
          onCycleOnMultiple={props.onCycleOnMultiple}
        />
      ) : reference ? (
        <ReferenceView reference={reference} refLoc={props.refLoc} editable={!props.isView} onSetRefLoc={props.onSetRefLoc} />
      ) : isGate ? (
        <GateView />
      ) : isAgent ? (
        <AgentView />
      ) : tool ? (
        <ToolView
          tool={tool}
          tab={props.tab}
          isView={props.isView}
          locEdits={props.locEdits}
          locEditable={props.locEditable}
          onTab={props.onTab}
          onSetLoc={props.onSetLoc}
          onToggleRequired={props.onToggleRequired}
          onCycleOnMultiple={props.onCycleOnMultiple}
        />
      ) : null}
    </aside>
  )
}

const inputCls = (editable: boolean) =>
  `w-full rounded-md border px-2 py-1.5 font-mono text-[11px] text-text outline-none ${
    editable ? 'border-line-strong bg-card focus:border-accent' : 'border-line bg-card-2'
  }`

// The locator-authoring list, keyed on a set of output kinds — shared by the seeded ToolView and the
// composed UserNodeInspector so a hand-authored node gets the SAME run_layout authoring as a seeded
// one. Repointing a path changes inputs, never thresholds (the config locates; it never judges).
function LocatorList({
  outKinds,
  locEdits,
  locEditable,
  onSetLoc,
  onToggleRequired,
  onCycleOnMultiple,
}: {
  outKinds: string[]
  locEdits: LocEdits
  locEditable: boolean
  onSetLoc: (kind: string, field: 'loc' | 'parser', value: string) => void
  onToggleRequired: (kind: string) => void
  onCycleOnMultiple: (kind: string) => void
}) {
  const locators = GIAB_LOC.filter((g) => outKinds.includes(g.k)).map((g) => mergedLoc(g.k, locEdits))
  if (!locators.length) return <p className="text-[11px] text-text-3">No emitted locators for this node's output kinds.</p>
  return (
    <>
      {locators.map((l) => (
        <div key={l.k} className="mb-3 rounded-[10px] border border-line p-3">
          <div className="mb-2.5 flex items-center justify-between gap-2">
            <span className="font-mono text-[12px] font-semibold text-text">{l.k}</span>
            <span className="rounded border border-line bg-card-2 px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-[0.3px] text-text-2">{l.role}</span>
          </div>
          <div className="flex flex-col gap-2">
            <div>
              <div className="mb-0.5 text-[9.5px] uppercase tracking-[0.3px] text-text-3">{l.field}</div>
              <input value={l.loc} readOnly={!locEditable} onChange={(e) => onSetLoc(l.k, 'loc', e.target.value)} className={inputCls(locEditable)} />
            </div>
            <div className="flex gap-2">
              <div className="min-w-0 flex-1">
                <div className="mb-0.5 text-[9.5px] uppercase tracking-[0.3px] text-text-3">parser</div>
                <input value={l.parser} readOnly={!locEditable} onChange={(e) => onSetLoc(l.k, 'parser', e.target.value)} className={inputCls(locEditable)} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-0.5 text-[9.5px] uppercase tracking-[0.3px] text-text-3">on_multiple</div>
                <button
                  onClick={() => locEditable && onCycleOnMultiple(l.k)}
                  className={`w-full rounded-md border border-line bg-card-2 px-2 py-1.5 text-left font-mono text-[11px] text-text-2 ${
                    locEditable ? 'cursor-pointer hover:border-line-strong' : 'cursor-default'
                  }`}
                  title={locEditable ? `→ ${ON_CYCLE[l.on as OnMultiple]}` : undefined}
                >
                  {l.on}
                </button>
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-0.5 text-[9.5px] uppercase tracking-[0.3px] text-text-3">required</div>
                <button
                  onClick={() => locEditable && onToggleRequired(l.k)}
                  className={`w-full rounded-md border px-2 py-1.5 text-center font-mono text-[11px] ${
                    l.required ? 'border-[#cfe0fb] bg-accent-weak text-accent-strong' : 'border-line bg-card-2 text-text-3'
                  } ${locEditable ? 'cursor-pointer' : 'cursor-default'}`}
                >
                  {l.required ? 'required' : 'optional'}
                </button>
              </div>
            </div>
            {IN_ORIGIN}
          </div>
        </div>
      ))}
    </>
  )
}

// The editable inspector for a COMPOSED user node (PB2 §4.3): rename, icon, typed port editing, the
// shared locator authoring, and delete. Every port kind is chosen from the typed ARTIFACT_KINDS vocab
// — never free-invented — so the wiring/locators always understand it.
function UserNodeInspector({
  node,
  isView,
  locEdits,
  locEditable,
  onRename,
  onSetIcon,
  onAddPort,
  onRemovePort,
  onSetPortKind,
  onDelete,
  onSetLoc,
  onToggleRequired,
  onCycleOnMultiple,
}: {
  node: UserNode
  isView: boolean
  locEdits: LocEdits
  locEditable: boolean
  onRename: (id: string, name: string) => void
  onSetIcon: (id: string, icon: IconKey) => void
  onAddPort: (id: string, dir: 'ins' | 'outs', kind: string) => void
  onRemovePort: (id: string, dir: 'ins' | 'outs', idx: number) => void
  onSetPortKind: (id: string, dir: 'ins' | 'outs', idx: number, kind: string) => void
  onDelete: (id: string) => void
  onSetLoc: (kind: string, field: 'loc' | 'parser', value: string) => void
  onToggleRequired: (kind: string) => void
  onCycleOnMultiple: (kind: string) => void
}) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      {/* Identity — name + icon. Name commits on blur/Enter (keyed to the node so it resets on reselect). */}
      <div className="mb-4 rounded-[10px] border border-line p-3">
        <div className="mb-0.5 text-[9.5px] uppercase tracking-[0.3px] text-text-3">name</div>
        <input
          key={node.id}
          defaultValue={node.name}
          readOnly={isView}
          onBlur={(e) => !isView && onRename(node.id, e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
          }}
          className={`w-full rounded-md border px-2 py-1.5 text-[12.5px] font-semibold text-text outline-none ${
            isView ? 'border-line bg-card-2' : 'border-line-strong bg-card focus:border-accent'
          }`}
        />
        {!isView && (
          <div className="mt-2.5">
            <div className="mb-1 text-[9.5px] uppercase tracking-[0.3px] text-text-3">icon</div>
            <div className="flex flex-wrap gap-1">
              {ICON_CHOICES.map((k) => {
                const I = ICONS[k]
                const on = node.icon === k
                return (
                  <button
                    key={k}
                    onClick={() => onSetIcon(node.id, k)}
                    title={k}
                    className={`grid h-8 w-8 place-items-center rounded-md border ${
                      on ? 'border-accent bg-accent-weak text-accent-strong' : 'border-line text-text-2 hover:border-line-strong'
                    }`}
                  >
                    <I size={15} />
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* Typed port editing. */}
      <PortEditor node={node} dir="ins" label="Inputs" isView={isView} onAddPort={onAddPort} onRemovePort={onRemovePort} onSetPortKind={onSetPortKind} />
      <PortEditor node={node} dir="outs" label="Outputs" isView={isView} onAddPort={onAddPort} onRemovePort={onRemovePort} onSetPortKind={onSetPortKind} />

      {/* Locators for this node's output kinds — the same authoring surface as a seeded node. */}
      <div className="mb-2 mt-1 text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">Locators</div>
      <LocatorList
        outKinds={node.outs}
        locEdits={locEdits}
        locEditable={locEditable}
        onSetLoc={onSetLoc}
        onToggleRequired={onToggleRequired}
        onCycleOnMultiple={onCycleOnMultiple}
      />

      {!isView && (
        <button
          onClick={() => onDelete(node.id)}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-escalate-bd bg-escalate-bg px-3 py-1.5 text-[12.5px] font-medium text-escalate-fg hover:opacity-90"
        >
          <Trash2 size={13} />
          Delete node
        </button>
      )}
    </div>
  )
}

function PortEditor({
  node,
  dir,
  label,
  isView,
  onAddPort,
  onRemovePort,
  onSetPortKind,
}: {
  node: UserNode
  dir: 'ins' | 'outs'
  label: string
  isView: boolean
  onAddPort: (id: string, dir: 'ins' | 'outs', kind: string) => void
  onRemovePort: (id: string, dir: 'ins' | 'outs', idx: number) => void
  onSetPortKind: (id: string, dir: 'ins' | 'outs', idx: number, kind: string) => void
}) {
  const ports = node[dir]
  return (
    <div className="mb-3">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">{label}</span>
        {!isView && (
          <button
            onClick={() => onAddPort(node.id, dir, ARTIFACT_KINDS[0])}
            className="inline-flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-[10.5px] font-medium text-text-2 hover:border-line-strong"
          >
            <Plus size={11} />
            Add
          </button>
        )}
      </div>
      {ports.length === 0 && <p className="text-[10.5px] text-text-3">No {dir === 'ins' ? 'inputs' : 'outputs'}.</p>}
      <div className="flex flex-col gap-1.5">
        {ports.map((k, idx) => (
          <div key={idx} className="flex items-center gap-1.5">
            {isView ? (
              <span className="flex-1 truncate rounded-md border border-line bg-card-2 px-2 py-1 font-mono text-[11px] text-text-2">{k}</span>
            ) : (
              <select
                value={k}
                onChange={(e) => onSetPortKind(node.id, dir, idx, e.target.value)}
                className="min-w-0 flex-1 rounded-md border border-line-strong bg-card px-2 py-1 font-mono text-[11px] text-text outline-none focus:border-accent"
              >
                {ARTIFACT_KINDS.map((ak) => (
                  <option key={ak} value={ak}>
                    {ak}
                  </option>
                ))}
              </select>
            )}
            {!isView && (
              <button
                onClick={() => onRemovePort(node.id, dir, idx)}
                title="Remove port"
                className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-text-3 hover:text-escalate-fg"
              >
                <X size={13} />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function ToolView({
  tool,
  tab,
  isView,
  locEdits,
  locEditable,
  onTab,
  onSetLoc,
  onToggleRequired,
  onCycleOnMultiple,
}: {
  tool: Tool
  tab: Tab
  isView: boolean
  locEdits: LocEdits
  locEditable: boolean
  onTab: (t: Tab) => void
  onSetLoc: (kind: string, field: 'loc' | 'parser', value: string) => void
  onToggleRequired: (kind: string) => void
  onCycleOnMultiple: (kind: string) => void
}) {
  const tabs: Tab[] = ['params', 'locators', 'io', 'agents']

  return (
    <>
      <div className="flex border-b border-line">
        {tabs.map((tb) => (
          <button
            key={tb}
            onClick={() => onTab(tb)}
            className={`flex-1 border-b-2 py-2.5 text-center text-[12px] font-semibold capitalize ${
              tab === tb ? 'border-accent text-accent-strong' : 'border-line text-text-3 hover:text-text'
            }`}
          >
            {tb === 'io' ? 'I/O' : tb}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {tab === 'params' && (
          <div>
            {tool.params.map((p) => (
              <div key={p.k} className="mb-3">
                <div className="mb-0.5 font-mono text-[11.5px] font-semibold text-text">{p.k}</div>
                <div className="mb-1.5 text-[10.5px] text-text-3">{p.help}</div>
                <div className="truncate rounded-md border border-line bg-card-2 px-2.5 py-1.5 font-mono text-[11.5px] text-text">{p.v}</div>
              </div>
            ))}
            <p className="border-t border-line pt-3 text-[10.5px] leading-relaxed text-text-3">
              Schema-driven form from the bundled <span className="font-mono">nextflow_schema.json</span> — no code editor, no live fetch.
            </p>
          </div>
        )}

        {tab === 'locators' && (
          <div>
            <div className="mb-3 rounded-lg border border-[#d5e2fb] bg-accent-weak px-3 py-2.5 text-[11px] leading-relaxed text-text-2">
              Repointing a path changes <strong>inputs</strong>, not thresholds. The config <strong>locates inputs; it never judges them.</strong>
            </div>
            <LocatorList
              outKinds={tool.outputs.map((o) => o.kind)}
              locEdits={locEdits}
              locEditable={locEditable}
              onSetLoc={onSetLoc}
              onToggleRequired={onToggleRequired}
              onCycleOnMultiple={onCycleOnMultiple}
            />
          </div>
        )}

        {tab === 'io' && (
          <div>
            {tool.io.map((o) => (
              <div key={o.name} className="mb-2.5 rounded-[9px] border border-line px-3 py-2.5">
                <div className="mb-1.5 truncate font-mono text-[11.5px] font-semibold text-text">{o.name}</div>
                <div className="flex gap-2.5">
                  <span className="font-mono text-[10px] text-text-3">{isView ? o.sha : 'sha256: —'}</span>
                  <span className="font-mono text-[10px] text-text-3">{isView ? o.size : '—'}</span>
                  <span className="ml-auto font-mono text-[10px] text-text-3">{isView ? o.origin : 'unknown'}</span>
                </div>
              </div>
            ))}
            {!isView && (
              <p className="border-t border-line pt-3 text-[10.5px] leading-relaxed text-text-3">
                Declared ports — no bytes yet. Hashes, sizes &amp; origin fill in from the ledger in linked <strong>View</strong>.
              </p>
            )}
          </div>
        )}

        {tab === 'agents' && (
          <div>
            <div className="mb-3 flex items-center gap-2.5 rounded-[10px] border border-line px-3 py-2.5">
              <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-lg bg-accent-weak">
                <Activity size={15} className="text-accent-strong" />
              </span>
              <div className="flex-1">
                <div className="text-[12.5px] font-semibold text-text">QC-triage</div>
                <div className="text-[10.5px] text-text-3">advisory · off critical path</div>
              </div>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card-2 px-2.5 py-1 font-mono text-[11px] text-text-2">
                <span className="h-1.5 w-1.5 rounded-full bg-text-3" />
                stub · $0
              </span>
            </div>
            <p className="text-[10.5px] leading-relaxed text-text-3">
              Snap-in observes this node's checkpoint output. It has <strong>no data ports</strong> — it can never set, route, or delay a verdict.
              Flip to <span className="font-mono">claude</span> via <span className="font-mono">PIPEGUARD_TRIAGE_AGENT</span>; any error degrades to the stub.
            </p>
          </div>
        )}
      </div>
    </>
  )
}

function GateView() {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="mb-3 rounded-lg border border-line bg-card-2 px-3 py-2.5 text-[11px] leading-relaxed text-text-2">
        The gate reads the frozen five <span className="font-mono">run/</span> CSVs — <strong>not</strong> raw tool outputs. Its verdict is computed by
        rules + runbook. Thresholds are <strong>read-only</strong> here.
      </div>
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">Runbook thresholds (read-only)</div>
      <div className="mb-3 overflow-hidden rounded-[10px] border border-line">
        {RUNBOOK_ROWS.map((rb) => (
          <div key={rb.metric} className="flex items-center gap-2 border-b border-line px-3 py-2.5 last:border-b-0">
            <span className="flex-1 text-[11.5px] text-text">{rb.metric}</span>
            <span className="font-mono text-[11px] text-text-2">{rb.gate}</span>
            <span className="font-mono text-[10px] text-text-3">hard {rb.hard}</span>
          </div>
        ))}
      </div>
      <Link
        to="/settings"
        className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-line"
      >
        <BarChart3 size={13} />
        Open runbook in Settings
      </Link>
    </div>
  )
}

function AgentView() {
  const rows = [
    { k: 'attachTo', v: 'g_gate' },
    { k: 'scope', v: 'qc' },
    { k: 'tier', v: 'sonnet-mid' },
  ]
  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="mb-3 rounded-lg border border-[#d5e2fb] bg-accent-weak px-3 py-2.5 text-[11px] leading-relaxed text-text-2">
        Advisory snap-in. <strong>No data ports</strong>, so it can never sit on the path to the gate — "off the critical path" is enforced by shape,
        not a lint rule.
      </div>
      <div className="flex flex-col gap-2.5">
        {rows.map((r) => (
          <div key={r.k} className="flex items-center gap-2">
            <span className="w-[78px] text-[11px] text-text-3">{r.k}</span>
            <span className="font-mono text-[11.5px] text-text">{r.v}</span>
          </div>
        ))}
        <div className="flex items-center gap-2">
          <span className="w-[78px] text-[11px] text-text-3">mode</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card-2 px-2.5 py-1 font-mono text-[11px] text-text-2">
            <span className="h-1.5 w-1.5 rounded-full bg-text-3" />
            stub · $0
          </span>
        </div>
      </div>
    </div>
  )
}

function ReferenceView({
  reference,
  refLoc,
  editable,
  onSetRefLoc,
}: {
  reference: Ref
  refLoc: Record<string, string>
  editable: boolean
  onSetRefLoc: (id: string, value: string) => void
}) {
  const value = refLoc[reference.id] ?? reference.file
  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="mb-3 rounded-lg border border-[#d5e2fb] bg-accent-weak px-3 py-2.5 text-[11px] leading-relaxed text-text-2">
        A reference input — located by config, <strong>never gated</strong>. Origin is stamped at ingest.
      </div>
      <div className="rounded-[10px] border border-line p-3">
        <div className="mb-2.5 flex items-center justify-between gap-2">
          <span className="font-mono text-[12px] font-semibold text-text">{reference.kind}</span>
          <span className="rounded border border-line bg-card-2 px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-[0.3px] text-text-2">reference</span>
        </div>
        <div className="flex flex-col gap-2">
          <div>
            <div className="mb-0.5 text-[9.5px] uppercase tracking-[0.3px] text-text-3">location</div>
            <input
              value={value}
              readOnly={!editable}
              onChange={(e) => onSetRefLoc(reference.id, e.target.value)}
              className={`w-full rounded-md border px-2 py-1.5 font-mono text-[11px] text-text outline-none ${
                editable ? 'border-line-strong bg-card focus:border-accent' : 'border-line bg-card-2'
              }`}
            />
          </div>
          <div className="flex gap-2">
            <div className="min-w-0 flex-1">
              <div className="mb-0.5 text-[9.5px] uppercase tracking-[0.3px] text-text-3">parser</div>
              <div className="rounded-md border border-line bg-card-2 px-2 py-1.5 font-mono text-[11px] text-text-3">null · pointer-only</div>
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-0.5 text-[9.5px] uppercase tracking-[0.3px] text-text-3">role</div>
              <div className="rounded-md border border-line bg-card-2 px-2 py-1.5 font-mono text-[11px] text-text-2">reference</div>
            </div>
          </div>
          {IN_ORIGIN}
        </div>
      </div>
    </div>
  )
}

function ShieldGlyph() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  )
}
