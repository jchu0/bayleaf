import { Fragment, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Search, SlidersHorizontal, Trash2 } from 'lucide-react'
import { Check } from './Check'
import { Pager } from './Pager'
import { SegmentedControl, type SegmentOption } from './SegmentedControl'
import { useRangeSelect } from '../hooks/useRangeSelect'
import { useConfirm } from './ConfirmDialog'
import { useToast } from './Toast'

// Agents & model tiering (ST1 + UIC-12). A model per advisory agent — narration/advice ONLY; verdicts
// stay rule-derived (ADR-0001), so nothing here can move a gate. Rendered as a scale-aware TABLE with
// the app-wide UIC-3 checkbox model (shift-range select + select-all) so several agents can be edited
// or removed at once, an active/available split (a clear status divide), and edits staged behind an
// explicit inline-expander Save (the maintainer's explicit-edit rule — a stray dropdown change never takes
// effect on its own). Purely local demo state — the T-045 seam (nothing here is wired to the real
// PIPEGUARD_*_MODEL env vars yet), so writes surface via a toast rather than an audit-backed persist.
// List pricing ($ in / out per 1M tokens) is ILLUSTRATIVE, not a live or contractual quote.
type ModelKey = 'opus' | 'sonnet' | 'haiku' | 'fable'

const MODELS: { key: ModelKey; name: string; cost: string }[] = [
  { key: 'opus', name: 'Claude Opus 4.8', cost: '$5 / $25' },
  { key: 'sonnet', name: 'Claude Sonnet 5', cost: '$3 / $15' },
  { key: 'haiku', name: 'Claude Haiku 4.5', cost: '$1 / $5' },
  { key: 'fable', name: 'Claude Fable 5', cost: '$0.50 / $2.50' },
]
const MODEL_NAME: Record<ModelKey, string> = Object.fromEntries(MODELS.map((m) => [m.key, m.name])) as Record<ModelKey, string>
// Retained but referenced ONLY at the edit moment (the illustrative price caption under the Model select) —
// deliberately kept out of the roster table + the select options so cost never reads as a live quote.
const MODEL_COST: Record<ModelKey, string> = Object.fromEntries(MODELS.map((m) => [m.key, m.cost])) as Record<ModelKey, string>

// The real advisory-agent roster (CLAUDE.md code map §3) + the ST2 metrics-expansion agent. Every one
// is advisory + off the deterministic gate, stub-first ($0), model picked via a PIPEGUARD_*_MODEL env
// var on the backend; this table is the operator-facing view of that config. `wired` = the agent is
// actually plumbed end-to-end today (starts ACTIVE); the phase-2 seams start AVAILABLE (designed, add-
// able to the roster, but not yet running) — that split is the honest active/available divide.
type Agent = {
  key: string
  label: string
  desc: string
  def: ModelKey
  env: string
  wired: boolean // plumbed end-to-end today → seeds the Active roster (vs. an Available seam)
  where?: 'builder' // agent surfaced inside the Pipeline Builder
  phase2?: boolean // a labelled seam — proposed, not yet wired end-to-end
}
const AGENTS: Agent[] = [
  { key: 'synthesizer', label: 'Card synthesizer', desc: 'Narrates decision cards (never sets a verdict)', def: 'sonnet', env: 'PIPEGUARD_SYNTHESIZER', wired: true },
  { key: 'qc_triage', label: 'QC-triage agent', desc: 'Answers "Ask the agent" for a flagged card', def: 'sonnet', env: 'PIPEGUARD_TRIAGE_AGENT', wired: true },
  { key: 'pipeline_repair', label: 'Pipeline-repair agent', desc: 'Proposes fixes for recurring signatures', def: 'opus', env: 'PIPEGUARD_PIPELINE_REPAIR_AGENT', wired: true },
  { key: 'archivist', label: 'Archivist agent', desc: 'Organizes released runs for archival', def: 'haiku', env: 'PIPEGUARD_ARCHIVIST_AGENT', wired: true },
  { key: 'feedback', label: 'Feedback categorizer', desc: 'Categorizes reviewer overrides', def: 'haiku', env: 'PIPEGUARD_FEEDBACK_AGENT', wired: true },
  { key: 'node_author', label: 'Node-author agent', desc: 'Proposes a typed tool node for the Builder palette', def: 'sonnet', env: 'PIPEGUARD_NODE_AUTHOR_AGENT', wired: true, where: 'builder' },
  { key: 'metrics_expand', label: 'Metrics-expansion agent', desc: 'Proposes new QC metrics to track + wiring', def: 'sonnet', env: 'PIPEGUARD_METRICS_AGENT', wired: false, phase2: true },
]
const AGENT_BY_KEY: Record<string, Agent> = Object.fromEntries(AGENTS.map((a) => [a.key, a]))
const INITIAL_ACTIVE = AGENTS.filter((a) => a.wired).map((a) => a.key)

type Row = { model: ModelKey; live: boolean; desc: string }
type LiveChoice = 'keep' | 'on' | 'off' // 'keep' only offered on a multi-agent edit (leave each as-is)
type StatusFilter = 'all' | 'live' | 'stub'

// The panel's live control: a bare on/stub for one agent, a keep-aware triple when editing several.
const LIVE_OPTS_SINGLE: SegmentOption<LiveChoice>[] = [
  { value: 'on', label: 'Live' },
  { value: 'off', label: 'Stub · $0' },
]
const LIVE_OPTS_MULTI: SegmentOption<LiveChoice>[] = [
  { value: 'keep', label: 'Keep' },
  { value: 'on', label: 'Live' },
  { value: 'off', label: 'Stub' },
]
// Toolbar status segment — filters the roster VIEW by the committed live flag (never mutates it).
const STATUS_OPTS: SegmentOption<StatusFilter>[] = [
  { value: 'all', label: 'All' },
  { value: 'live', label: 'Live' },
  { value: 'stub', label: 'Stub' },
]

const GRID = 'grid grid-cols-[26px_1.6fr_1.9fr_1.5fr_0.9fr] items-center gap-2'

export function SettingsModelTier() {
  const confirm = useConfirm()
  const { toast } = useToast()
  // Committed per-agent config (model + live + editable purpose). Defaults: stub (live off, $0) — conserve credits.
  const [rows, setRows] = useState<Record<string, Row>>(() =>
    Object.fromEntries(AGENTS.map((a) => [a.key, { model: a.def, live: false, desc: a.desc }])),
  )
  // Which agents are in the Active roster (the rest are Available). Removing moves an agent to
  // Available; adding moves it back — local demo state, never a backend delete (T-045 seam).
  const [activeKeys, setActiveKeys] = useState<Set<string>>(() => new Set(INITIAL_ACTIVE))
  const [page, setPage] = useState(1)
  // Toolbar view state — a search box + a status segment, each resets to page 1 so a filter never
  // strands the operator on an empty tail page.
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  // The inline tiering editor: which agents it targets + its staged (uncommitted) draft. Save applies;
  // Cancel/close/Esc discards. Nothing mutates until Save (explicit-edit rule).
  const [panelKeys, setPanelKeys] = useState<string[] | null>(null)
  const [draftModel, setDraftModel] = useState<ModelKey | 'keep'>('keep')
  const [draftLive, setDraftLive] = useState<LiveChoice>('keep')
  const [draftDesc, setDraftDesc] = useState('')

  const activeAgents = AGENTS.filter((a) => activeKeys.has(a.key))
  const availableAgents = AGENTS.filter((a) => !activeKeys.has(a.key))

  // Filter the active roster by the search box + status segment before paging. matchStatus reads the
  // committed live flag (not the agent's default), matchSearch spans label + env + the editable purpose.
  const q = search.trim().toLowerCase()
  const matchStatus = (a: Agent) =>
    statusFilter === 'all' || (statusFilter === 'live' ? rows[a.key].live : !rows[a.key].live)
  const matchSearch = (a: Agent) => q === '' || `${a.label} ${a.env} ${rows[a.key].desc}`.toLowerCase().includes(q)
  const filteredActive = activeAgents.filter((a) => matchStatus(a) && matchSearch(a))

  const per = 10 // hard page size — a 100-agent roster stays navigable without a per-page toggle
  const pages = Math.max(1, Math.ceil(filteredActive.length / per))
  const curPage = Math.min(page, pages)
  const shown = filteredActive.slice((curPage - 1) * per, curPage * per)
  const pageKeys = shown.map((a) => a.key) // flat render order → drives the shift-range math

  const sel = useRangeSelect(pageKeys)
  const allShown = sel.allSelected(pageKeys)
  const someShown = pageKeys.some((k) => sel.isSelected(k))
  // Selection can span pages; the batch bar acts on every still-active selected agent.
  const selectedKeys = activeAgents.filter((a) => sel.isSelected(a.key)).map((a) => a.key)

  // Exactly one agent open in the inline expander (null when closed or when a multi/batch edit is open).
  const singleEditKey = panelKeys?.length === 1 ? panelKeys[0] : null

  const openPanel = (keys: string[]) => {
    if (keys.length === 0) return
    const first = rows[keys[0]]
    const sameModel = keys.every((k) => rows[k].model === first.model)
    const sameLive = keys.every((k) => rows[k].live === first.live)
    // Single agent → prefill its real values. Multiple → prefill only where they already agree,
    // else 'keep' so a bulk edit can't silently clobber a field the operator didn't touch.
    setDraftModel(keys.length === 1 || sameModel ? first.model : 'keep')
    setDraftLive(keys.length === 1 ? (first.live ? 'on' : 'off') : sameLive ? (first.live ? 'on' : 'off') : 'keep')
    setDraftDesc(first.desc) // purpose is only editable single (§4d), but seed it either way
    setPanelKeys(keys)
  }
  const closePanel = () => setPanelKeys(null)
  // Row click / Enter toggles the single-agent expander: same row re-clicked closes it, else opens it.
  const toggleEdit = (key: string) => {
    if (singleEditKey === key) closePanel()
    else openPanel([key])
  }

  const applyPanel = async () => {
    if (!panelKeys) return
    const next = { ...rows }
    let turningLiveOn = false
    for (const k of panelKeys) {
      const cur = rows[k]
      const model = draftModel === 'keep' ? cur.model : draftModel
      const live = draftLive === 'keep' ? cur.live : draftLive === 'on'
      if (live && !cur.live) turningLiveOn = true
      // Purpose is only offered on a single edit; a batch keeps each agent's existing text.
      next[k] = { model, live, desc: panelKeys.length === 1 ? draftDesc : cur.desc }
    }
    // Flipping an agent to Live turns on real (billed) Claude calls — the app's central cost guardrail
    // (stub-first, conserve credits). Confirm that specifically; a model-only edit applies on Save.
    if (turningLiveOn) {
      const ok = await confirm({
        title: 'Enable live model calls?',
        body: 'Live agents make real, billed Claude API calls; Stub stays $0. Demo seam — nothing here persists to the backend yet.',
        confirmLabel: 'Enable live',
      })
      if (!ok) return
    }
    setRows(next)
    closePanel()
    sel.clear()
    toast(`Updated ${panelKeys.length} agent${panelKeys.length === 1 ? '' : 's'}`, 'success')
  }

  const removeKeys = async (keys: string[]) => {
    if (keys.length === 0) return
    const ok = await confirm({
      title: `Remove ${keys.length} agent${keys.length === 1 ? '' : 's'} from the active roster?`,
      body: 'They move to Available and can be added back anytime. Local demo state — no backend agent is deleted.',
      confirmLabel: 'Remove',
      tone: 'danger',
    })
    if (!ok) return
    setActiveKeys((prev) => {
      const n = new Set(prev)
      for (const k of keys) n.delete(k)
      return n
    })
    closePanel()
    sel.clear()
    toast(`Removed ${keys.length} agent${keys.length === 1 ? '' : 's'} from the roster`, 'info')
  }

  const addKey = (key: string) => {
    setActiveKeys((prev) => new Set(prev).add(key))
    toast(`Added ${AGENT_BY_KEY[key].label} to the roster`, 'success')
  }

  const panelAgents = panelKeys ? panelKeys.map((k) => AGENT_BY_KEY[k]) : []
  const isMulti = (panelKeys?.length ?? 0) > 1

  // Esc closes the open editor (single or multi) — matches the explicit-edit "nothing until Save" rule.
  useEffect(() => {
    if (panelKeys == null) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPanelKeys(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [panelKeys])

  // The staged tiering editor body — reused verbatim by the single-row expander and the multi/batch
  // block. It reads component state, so the caller only decides WHERE to mount it (single vs. batch).
  const renderEditor = () => {
    const single = singleEditKey ? AGENT_BY_KEY[singleEditKey] : null
    return (
      <div className="space-y-3.5">
        {/* (1) micro-header — the agent name + its env var (single), or the ·-joined labels (multi). */}
        <div className="min-w-0">
          {single ? (
            <>
              <div className="text-[13px] font-semibold text-text">{single.label}</div>
              <div className="truncate font-mono text-[9.5px] text-text-3">
                {single.env}
                {single.where === 'builder' ? ' · in builder' : ''}
                {single.phase2 ? ' · phase-2' : ''}
              </div>
            </>
          ) : (
            <div className="text-[13px] font-semibold text-text">{panelAgents.map((a) => a.label).join(' · ')}</div>
          )}
        </div>

        {/* (2) Purpose — editable single only (§4d); a batch keeps each agent's own text. */}
        {single ? (
          <div>
            <label className="text-[11px] font-bold uppercase tracking-[0.5px] text-text-3">Purpose</label>
            <textarea
              rows={2}
              value={draftDesc}
              onChange={(e) => setDraftDesc(e.target.value)}
              aria-label="Purpose"
              className="mt-1.5 w-full resize-none rounded-lg border border-line-strong bg-card px-2.5 py-2 text-[13px] text-text focus:border-accent focus:outline-none"
            />
            <p className="mt-1 text-[11px] text-text-3">Shown on the card and in the roster.</p>
          </div>
        ) : (
          <p className="text-[11.5px] text-text-3">Purpose is edited one agent at a time.</p>
        )}

        {/* (3) Model tier — pricing STRIPPED from the options; it lives in the caption below (§5). */}
        <div>
          <label className="text-[11px] font-bold uppercase tracking-[0.5px] text-text-3">Model</label>
          <select
            value={draftModel}
            onChange={(e) => setDraftModel(e.target.value as ModelKey | 'keep')}
            aria-label="Model"
            className="mt-1.5 w-full cursor-pointer rounded-lg border border-line-strong bg-card px-2.5 py-2 text-[13px] font-medium text-text focus:border-accent focus:outline-none"
          >
            {isMulti && <option value="keep">Keep current (per agent)</option>}
            {MODELS.map((m) => (
              <option key={m.key} value={m.key}>
                {m.name}
              </option>
            ))}
          </select>
          {/* (4) illustrative price — surfaced only at the edit moment, clearly labelled. */}
          <p className="mt-1 font-mono text-[9.5px] text-text-3">
            {draftModel === 'keep' ? 'mixed / unchanged' : `≈ ${MODEL_COST[draftModel]} per 1M · illustrative`}
          </p>
        </div>

        {/* (5) Execution — the live/stub segment + the R6 honesty one-liner (§6.3). */}
        <div>
          <label className="text-[11px] font-bold uppercase tracking-[0.5px] text-text-3">Execution</label>
          <div className="mt-1.5">
            <SegmentedControl<LiveChoice>
              options={isMulti ? LIVE_OPTS_MULTI : LIVE_OPTS_SINGLE}
              value={draftLive}
              onChange={setDraftLive}
            />
          </div>
          <p className="mt-1.5 text-[11px] leading-[1.5] text-text-3">
            Live = real billed Claude calls; Stub = deterministic $0. Advisory only — never sets a verdict (ADR-0001).
          </p>
        </div>

        {/* (6) Actions — remove (left), cancel/save (right). Nothing mutates until Save. */}
        <div className="flex items-center justify-between gap-2 pt-0.5">
          <button
            type="button"
            onClick={() => void removeKeys(panelKeys ?? [])}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12.5px] font-medium text-escalate-fg transition-colors hover:bg-escalate-bg"
          >
            <Trash2 size={13} />
            Remove from roster
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={closePanel}
              className="rounded-lg border border-line bg-card px-3.5 py-1.5 text-[13px] font-medium text-text-2 hover:bg-page"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void applyPanel()}
              className="rounded-lg bg-accent px-3.5 py-1.5 text-[13px] font-semibold text-white hover:bg-accent-strong"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <section className="rounded-[13px] border border-line bg-card px-[18px] py-[17px]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        {/* Left cluster: title + the card-level honesty chip strip (R6's home — replaces the old blurb). */}
        <div>
          <div className="text-[14.5px] font-semibold text-text">Agents &amp; model tiering</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <span className="rounded-full border border-line bg-card-2 px-2 py-0.5 text-[10px] font-medium text-text-3">
              Advisory · off the gate
            </span>
            <span className="rounded-full border border-line bg-card-2 px-2 py-0.5 text-[10px] font-medium text-text-3">
              Stub-first · $0
            </span>
            <span
              title="Each model is a PIPEGUARD_*_MODEL env var. Live = real, billed Claude calls. Verdicts stay rule-derived (ADR-0001)."
              className="grid h-4 w-4 cursor-help place-items-center rounded-full border border-line text-[9px] font-bold text-text-3"
            >
              i
            </span>
          </div>
        </div>
        {/* Right cluster toolbar: search → status filter → create-new (node-author lives in the Builder). */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-text-3" />
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
              placeholder="Search agents"
              aria-label="Search agents"
              className="w-[180px] rounded-lg border border-line bg-card pl-7 pr-2 py-1.5 text-[12.5px]"
            />
          </div>
          <SegmentedControl<StatusFilter>
            options={STATUS_OPTS}
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter(v)
              setPage(1)
            }}
          />
          {/* ST1: create a new agent by designing it in the Pipeline Builder (node-author lives there). */}
          <Link
            to="/builder"
            title="Design a new agent in the Pipeline Builder"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-accent-strong transition-colors hover:border-accent"
          >
            <Plus size={14} />
            New agent
          </Link>
        </div>
      </div>

      {/* ── Active roster ─────────────────────────────────────────────────────────────────── */}
      <div className="mt-4 flex items-center justify-between gap-2">
        <div className="text-[11px] font-bold uppercase tracking-[0.6px] text-text-3">
          Active · {activeAgents.length}
        </div>
        {selectedKeys.length > 0 && (
          <button
            type="button"
            onClick={sel.clear}
            className="text-[11.5px] text-text-3 transition-colors hover:text-text-2"
          >
            Clear selection
          </button>
        )}
      </div>

      {/* Batch bar (UIC-3): edit or remove every selected agent at once. Mirrors the review-queue idiom. */}
      {selectedKeys.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-2.5 rounded-lg border border-accent bg-accent-weak px-3.5 py-2.5">
          <span className="text-[12.5px] font-semibold text-text">{selectedKeys.length} selected</span>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => openPanel(selectedKeys)}
              className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-card px-2.5 py-1 text-[12px] font-semibold text-text hover:border-accent hover:text-accent-strong"
            >
              <SlidersHorizontal size={13} />
              Edit tiers
            </button>
            <button
              type="button"
              onClick={() => void removeKeys(selectedKeys)}
              className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-card px-2.5 py-1 text-[12px] font-semibold text-escalate-fg hover:bg-escalate-bg"
            >
              <Trash2 size={13} />
              Remove
            </button>
          </div>
        </div>
      )}

      {/* Multi/batch tiering editor — an inline block directly under the batch bar (never a popout). */}
      {isMulti && (
        <div className="mt-2 rounded-[11px] border border-line border-l-2 border-l-accent bg-card-2 px-4 py-3.5">
          {renderEditor()}
        </div>
      )}

      <div className="mt-2 overflow-hidden rounded-[11px] border border-line">
        {/* Header row carries the select-all (parent) checkbox — scoped to the visible page (UIC-3.2). */}
        <div className={`${GRID} bg-card-2 px-3 py-[9px] text-[9.5px] font-bold uppercase tracking-[0.4px] text-text-3`}>
          <div className="flex items-center">
            {pageKeys.length > 0 && (
              <Check
                checked={allShown}
                indeterminate={someShown && !allShown}
                onToggle={() => sel.setMany(pageKeys, !allShown)}
                label="Select all agents on this page"
              />
            )}
          </div>
          <div>Agent</div>
          <div>Purpose</div>
          <div>Model</div>
          <div>Status</div>
        </div>
        {shown.length === 0 ? (
          <div className="px-3 py-6 text-center text-[12.5px] text-text-3">
            {activeAgents.length === 0 ? 'No active agents — add one from Available below.' : 'No agents match.'}
          </div>
        ) : (
          shown.map((a) => {
            const row = rows[a.key]
            const checked = sel.isSelected(a.key)
            const editing = singleEditKey === a.key
            return (
              <Fragment key={a.key}>
                <div
                  className={`${GRID} cursor-pointer border-t border-line px-3 py-[10px] transition-colors hover:bg-card-2 ${
                    checked || editing ? 'bg-accent-weak' : ''
                  }`}
                  role="button"
                  tabIndex={0}
                  onClick={() => toggleEdit(a.key)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') toggleEdit(a.key)
                  }}
                  title="Edit this agent's model tier"
                >
                  {/* Checkbox stops propagation so selecting a row never opens the editor (and vice-versa). */}
                  <div className="flex items-center" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
                    <Check
                      checked={checked}
                      onToggle={(shift) => sel.toggle(a.key, shift)}
                      label={`Select ${a.label}`}
                    />
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-[12.5px] font-semibold text-text">{a.label}</div>
                    <div className="truncate font-mono text-[9.5px] text-text-3">
                      {a.env}
                      {a.where === 'builder' ? ' · in builder' : ''}
                      {a.phase2 ? ' · phase-2' : ''}
                    </div>
                  </div>
                  <div className="min-w-0 truncate text-[11.5px] text-text-2">{row.desc}</div>
                  <div className="min-w-0">
                    <div className="truncate text-[12px] font-medium text-text">{MODEL_NAME[row.model]}</div>
                  </div>
                  <div>
                    <span
                      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                        row.live
                          ? 'border-proceed-bd bg-proceed-bg text-proceed-fg'
                          : 'border-line bg-card-2 text-text-3'
                      }`}
                    >
                      {row.live ? 'Live' : 'Stub · $0'}
                    </span>
                  </div>
                </div>
                {/* Single-agent inline expander — the immediate sibling of its row, inside the table border. */}
                {editing && (
                  <div className="border-t border-line border-l-2 border-l-accent bg-card-2 px-4 py-3.5">
                    {renderEditor()}
                  </div>
                )}
              </Fragment>
            )
          })
        )}
      </div>

      {/* Pager only when the filtered roster overflows one page (>10). No per-page toggle (fixed size). */}
      {filteredActive.length > per && (
        <Pager total={filteredActive.length} page={curPage} perPage="10" onPage={setPage} hidePerPage noun="agents" />
      )}

      {/* ── Available (not in the active roster) ──────────────────────────────────────────── */}
      {availableAgents.length > 0 && (
        <div className="mt-4">
          <div className="text-[11px] font-bold uppercase tracking-[0.6px] text-text-3">
            Available · {availableAgents.length}
          </div>
          <p className="mt-[3px] text-[11.5px] text-text-3">
            Designed agents not currently in the active roster — add one to run it (each stays stub-first, $0).
          </p>
          <div className="mt-2 space-y-[7px]">
            {availableAgents.map((a) => (
              <div
                key={a.key}
                className="flex items-center gap-3 rounded-[10px] border border-dashed border-line-strong bg-card-2 px-[13px] py-[10px]"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12.5px] font-semibold text-text">{a.label}</div>
                  <div className="truncate text-[11.5px] text-text-2">{rows[a.key].desc}</div>
                  <div className="truncate font-mono text-[9.5px] text-text-3">
                    {a.env}
                    {a.where === 'builder' ? ' · in builder' : ''}
                    {a.phase2 ? ' · phase-2' : ''}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => addKey(a.key)}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12px] font-medium text-accent-strong transition-colors hover:border-accent"
                >
                  <Plus size={13} />
                  Add
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
