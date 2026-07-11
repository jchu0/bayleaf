import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Pencil, Plus, X } from 'lucide-react'
import { SettingsToggle } from './SettingsToggle'

// Agents & model tiering (ST1). A model per advisory agent — narration/advice ONLY; verdicts stay
// rule-derived (ADR-0001), so nothing here can move a gate. Rendered as a TABLE (not a stack of
// cards) so it scales as the roster grows, and each row edits behind an explicit Save (the
// maintainer's explicit-edit rule — a stray dropdown change no longer takes effect on its own).
// List pricing ($ in / out per 1M tokens) is ILLUSTRATIVE, not a live or contractual quote.
type ModelKey = 'opus' | 'sonnet' | 'haiku' | 'fable'

const MODELS: { key: ModelKey; name: string; cost: string }[] = [
  { key: 'opus', name: 'Claude Opus 4.8', cost: '$5 / $25' },
  { key: 'sonnet', name: 'Claude Sonnet 5', cost: '$3 / $15' },
  { key: 'haiku', name: 'Claude Haiku 4.5', cost: '$1 / $5' },
  { key: 'fable', name: 'Claude Fable 5', cost: '$0.50 / $2.50' },
]
const MODEL_NAME: Record<ModelKey, string> = Object.fromEntries(MODELS.map((m) => [m.key, m.name])) as Record<ModelKey, string>
const MODEL_COST: Record<ModelKey, string> = Object.fromEntries(MODELS.map((m) => [m.key, m.cost])) as Record<ModelKey, string>

// The real advisory-agent roster (CLAUDE.md code map §3) + the ST2 metrics-expansion agent. Every
// one is advisory + off the deterministic gate, stub-first ($0), model picked via a PIPEGUARD_*_MODEL
// env var on the backend; this table is the operator-facing view of that config.
type Agent = {
  key: string
  label: string
  desc: string
  def: ModelKey
  env: string
  where?: 'builder' // agent surfaced inside the Pipeline Builder
  phase2?: boolean // a labelled seam — proposed, not yet wired end-to-end
}
const AGENTS: Agent[] = [
  { key: 'synthesizer', label: 'Card synthesizer', desc: 'Narrates decision cards (never sets a verdict)', def: 'sonnet', env: 'PIPEGUARD_SYNTHESIZER' },
  { key: 'qc_triage', label: 'QC-triage agent', desc: 'Answers "Ask the agent" for a flagged card', def: 'sonnet', env: 'PIPEGUARD_TRIAGE_AGENT' },
  { key: 'pipeline_repair', label: 'Pipeline-repair agent', desc: 'Proposes fixes for recurring signatures', def: 'opus', env: 'PIPEGUARD_PIPELINE_REPAIR_AGENT' },
  { key: 'archivist', label: 'Archivist agent', desc: 'Organizes released runs for archival', def: 'haiku', env: 'PIPEGUARD_ARCHIVIST_AGENT' },
  { key: 'feedback', label: 'Feedback categorizer', desc: 'Categorizes reviewer overrides', def: 'haiku', env: 'PIPEGUARD_FEEDBACK_AGENT' },
  { key: 'node_author', label: 'Node-author agent', desc: 'Proposes a typed tool node from docs', def: 'sonnet', env: 'PIPEGUARD_NODE_AUTHOR', where: 'builder' },
  { key: 'metrics_expand', label: 'Metrics-expansion agent', desc: 'Proposes new QC metrics to track + wiring', def: 'sonnet', env: 'PIPEGUARD_METRICS_AGENT', phase2: true },
]
const PER_PAGE = 10 // scale-aware: paginate if the roster ever exceeds a page

type Row = { model: ModelKey; live: boolean }

export function SettingsModelTier() {
  // Committed per-agent config (model + live). Defaults: stub (live off, $0) — conserve credits.
  const [rows, setRows] = useState<Record<string, Row>>(() =>
    Object.fromEntries(AGENTS.map((a) => [a.key, { model: a.def, live: false }])),
  )
  // The row currently being edited + its staged (uncommitted) draft. Save commits; Cancel discards —
  // nothing changes until Save (explicit-edit rule).
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState<Row | null>(null)
  const [page, setPage] = useState(1)

  const beginEdit = (key: string) => {
    setEditing(key)
    setDraft({ ...rows[key] })
  }
  const cancelEdit = () => {
    setEditing(null)
    setDraft(null)
  }
  const saveEdit = () => {
    if (editing && draft) setRows((prev) => ({ ...prev, [editing]: draft }))
    cancelEdit()
  }

  const pages = Math.max(1, Math.ceil(AGENTS.length / PER_PAGE))
  const curPage = Math.min(page, pages)
  const shown = AGENTS.slice((curPage - 1) * PER_PAGE, curPage * PER_PAGE)

  return (
    <section className="rounded-[13px] border border-line bg-card px-[18px] py-[17px]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[14.5px] font-semibold text-text">Agents &amp; model tiering</div>
          <p className="mt-[3px] max-w-[560px] text-[12.5px] text-text-2">
            A model per advisory agent — narration/advice only, verdicts stay rule-derived (ADR-0001).
            Every agent is stub-first ($0) and off by default; edits apply on Save. Pricing is illustrative.
          </p>
        </div>
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

      <div className="mt-3 overflow-hidden rounded-[11px] border border-line">
        <div className="grid grid-cols-[1.6fr_1.9fr_1.5fr_0.9fr_84px] items-center gap-2 bg-card-2 px-3 py-[9px] text-[9.5px] font-bold uppercase tracking-[0.4px] text-text-3">
          <div>Agent</div>
          <div>Purpose</div>
          <div>Model</div>
          <div>Status</div>
          <div className="text-right">Edit</div>
        </div>
        {shown.map((a) => {
          const row = rows[a.key]
          const isEditing = editing === a.key
          const view = isEditing && draft ? draft : row
          return (
            <div
              key={a.key}
              className="grid grid-cols-[1.6fr_1.9fr_1.5fr_0.9fr_84px] items-center gap-2 border-t border-line px-3 py-[10px]"
            >
              <div className="min-w-0">
                <div className="truncate text-[12.5px] font-semibold text-text">{a.label}</div>
                <div className="truncate font-mono text-[9.5px] text-text-3">
                  {a.env}
                  {a.where === 'builder' ? ' · in builder' : ''}
                  {a.phase2 ? ' · phase-2' : ''}
                </div>
              </div>
              <div className="min-w-0 truncate text-[11.5px] text-text-2">{a.desc}</div>
              <div className="min-w-0">
                {isEditing ? (
                  <select
                    value={view.model}
                    onChange={(e) => setDraft((d) => (d ? { ...d, model: e.target.value as ModelKey } : d))}
                    aria-label={`${a.label} model`}
                    className="w-full cursor-pointer rounded-lg border border-line-strong bg-card px-2 py-1.5 text-[12px] font-medium text-text focus:border-accent focus:outline-none"
                  >
                    {MODELS.map((m) => (
                      <option key={m.key} value={m.key}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <div className="min-w-0">
                    <div className="truncate text-[12px] font-medium text-text">{MODEL_NAME[view.model]}</div>
                    <div className="font-mono text-[9.5px] text-text-3">{MODEL_COST[view.model]} / 1M</div>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-1.5">
                {isEditing ? (
                  <>
                    <SettingsToggle
                      on={view.live}
                      onChange={(v) => setDraft((d) => (d ? { ...d, live: v } : d))}
                      label={`${a.label} live`}
                    />
                    <span className="text-[10.5px] text-text-3">{view.live ? 'live' : 'stub'}</span>
                  </>
                ) : (
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                      view.live
                        ? 'border-proceed-bd bg-proceed-bg text-proceed-fg'
                        : 'border-line bg-card-2 text-text-3'
                    }`}
                  >
                    {view.live ? 'Live' : 'Stub · $0'}
                  </span>
                )}
              </div>
              <div className="flex items-center justify-end gap-1">
                {isEditing ? (
                  <>
                    <button
                      type="button"
                      onClick={saveEdit}
                      title="Save"
                      className="grid h-7 w-7 place-items-center rounded-md bg-accent text-white hover:bg-accent-strong"
                    >
                      <Check size={13} />
                    </button>
                    <button
                      type="button"
                      onClick={cancelEdit}
                      title="Cancel"
                      className="grid h-7 w-7 place-items-center rounded-md border border-line bg-card text-text-2 hover:border-line-strong"
                    >
                      <X size={13} />
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => beginEdit(a.key)}
                    disabled={editing !== null}
                    title="Edit model tier"
                    className="grid h-7 w-7 place-items-center rounded-md border border-line bg-card text-text-2 transition-colors hover:border-line-strong disabled:opacity-40"
                  >
                    <Pencil size={13} />
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {pages > 1 && (
        <div className="mt-2.5 flex items-center justify-between text-[11.5px] text-text-2">
          <span>
            Showing {(curPage - 1) * PER_PAGE + 1}–{Math.min(curPage * PER_PAGE, AGENTS.length)} of {AGENTS.length} agents
          </span>
          <div className="flex items-center gap-1">
            {Array.from({ length: pages }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setPage(n)}
                className={`h-7 min-w-[28px] rounded-[7px] px-2 text-[12px] ${
                  n === curPage ? 'bg-accent font-semibold text-white' : 'border border-line bg-card text-text-2 hover:border-line-strong'
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
