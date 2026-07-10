import { useState } from 'react'
import { Pencil } from 'lucide-react'
import { api } from '../api'
import { useRole } from '../context/RoleContext'
import { useToast } from './Toast'

// A threshold-override name must be a slug the backend accepts (^[A-Za-z0-9][A-Za-z0-9._-]*$);
// the assay display string ("Rare-disease germline v3") has spaces the store rejects.
function slugFor(assay: string): string {
  return `thresholds-${assay.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')}`
}
function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

// Runbook thresholds, keyed on assay × sample type (dc.html 1265-1311, 2233-2261, 2781-2799).
//
// The assay×tissue matrix has no core data source — /api/config returns a flat runbook — so the
// rows are SEEDED client-side (the design's CONFIG) and, on save, packed into the opaque
// `payload` of a ThresholdOverride (F18). This is a config-authoring flow, not an AI action:
// nothing here sets or moves a verdict (rules decide / AI advises, ADR-0001). Editing is
// read-only by default, unlocked by "Edit thresholds", and the save is audited + approver-gated.

type Dir = '≥' | '≤'
type Row = { metric: string; unit: string; dir: Dir; blood: string; saliva: string }

const ASSAYS = ['Rare-disease germline v3', 'Cardio panel v2', 'Exome v1'] as const

// Seed matches the prototype CONFIG.rowsByAssay verbatim (blood/saliva as strings for controlled
// inputs). Saliva loosens mapping / on-target on some assays; contamination is left unchanged.
const ROWS_BY_ASSAY: Record<string, Row[]> = {
  'Rare-disease germline v3': [
    { metric: 'Q30', unit: '%', dir: '≥', blood: '85', saliva: '85' },
    { metric: 'Mean genome depth', unit: '×', dir: '≥', blood: '30', saliva: '30' },
    { metric: '% genome ≥ 20×', unit: '%', dir: '≥', blood: '95', saliva: '95' },
    { metric: 'Mapping rate', unit: '%', dir: '≥', blood: '90', saliva: '85' },
    { metric: 'Contamination · FREEMIX', unit: '', dir: '≤', blood: '0.03', saliva: '0.03' },
    { metric: 'Duplication', unit: '%', dir: '≤', blood: '30', saliva: '35' },
  ],
  'Cardio panel v2': [
    { metric: 'Q30', unit: '%', dir: '≥', blood: '85', saliva: '85' },
    { metric: 'Mean target depth', unit: '×', dir: '≥', blood: '200', saliva: '200' },
    { metric: '% target ≥ 100×', unit: '%', dir: '≥', blood: '98', saliva: '95' },
    { metric: 'On-target rate', unit: '%', dir: '≥', blood: '90', saliva: '80' },
    { metric: 'Uniformity · Fold-80', unit: '', dir: '≤', blood: '1.8', saliva: '2.0' },
    { metric: 'Contamination · FREEMIX', unit: '', dir: '≤', blood: '0.02', saliva: '0.02' },
    { metric: 'Duplication', unit: '%', dir: '≤', blood: '20', saliva: '25' },
  ],
  'Exome v1': [
    { metric: 'Q30', unit: '%', dir: '≥', blood: '85', saliva: '85' },
    { metric: 'Mean target depth', unit: '×', dir: '≥', blood: '50', saliva: '50' },
    { metric: '% target ≥ 20×', unit: '%', dir: '≥', blood: '90', saliva: '90' },
    { metric: 'On-target rate', unit: '%', dir: '≥', blood: '75', saliva: '60' },
    { metric: 'Contamination · FREEMIX', unit: '', dir: '≤', blood: '0.03', saliva: '0.03' },
    { metric: 'Duplication', unit: '%', dir: '≤', blood: '30', saliva: '35' },
  ],
}

type Status = 'draft' | 'pending' | 'approved'
type Life = { status: Status; by: string; when: string }

const STATUS_LABEL: Record<Status, string> = {
  draft: 'unsaved draft',
  pending: 'pending approval',
  approved: 'approved · live',
}
const STATUS_CHIP: Record<Status, string> = {
  draft: 'text-text-2 bg-card-2 border-line-strong',
  pending: 'text-hold-fg bg-hold-bg border-hold-bd',
  approved: 'text-proceed-fg bg-proceed-bg border-proceed-bd',
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
function today(): string {
  const d = new Date()
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`
}

function auditLine(l: Life): string {
  if (l.status === 'draft') return `edited by ${l.by} · unsaved`
  if (l.status === 'pending') return `saved by ${l.by} · awaiting approver`
  return `approved by ${l.by} · ${l.when}`
}

// Guardrail (F10): non-negative always; percent metrics clamp to 0–100. In-progress input
// ('', '.', a trailing '0.') passes through so decimals stay typeable. The assay table carries
// one value per (metric × tissue) with no separate hard-fail column, so "a gate can't cross its
// hard-fail" has no in-table cross to enforce here — the representable clamp is the percent ceiling.
function clampCell(raw: string, unit: string): string {
  const t = raw.trim()
  if (t === '' || t === '.') return raw
  const n = Number(raw)
  if (!Number.isFinite(n)) return raw
  let c = Math.max(0, n)
  if (unit === '%') c = Math.min(100, c)
  return c === n ? raw : String(c)
}

export function SettingsAssayTable({
  requiredMetadata,
  disclaimer,
}: {
  requiredMetadata: string[]
  disclaimer?: string
}) {
  const { actor, role, isApprover, toggleRole } = useRole()
  const { toast } = useToast()

  const [assay, setAssay] = useState<string>(ASSAYS[0])
  const [rows, setRows] = useState<Record<string, Row[]>>(() =>
    Object.fromEntries(ASSAYS.map((a) => [a, ROWS_BY_ASSAY[a].map((r) => ({ ...r }))])),
  )
  const [life, setLife] = useState<Record<string, Life>>(() =>
    // Seeded state: each assay starts approved & live from a prior (historical) approver.
    Object.fromEntries(ASSAYS.map((a) => [a, { status: 'approved', by: 'k.osei', when: 'Jul 7, 2026' } as Life])),
  )
  const [editing, setEditing] = useState(false)
  // Snapshot taken at Edit so Cancel restores both the values and the lifecycle state.
  const [snapshot, setSnapshot] = useState<{ rows: Row[]; life: Life } | null>(null)

  const current = rows[assay]
  const currentLife = life[assay]

  function beginEdit() {
    setSnapshot({ rows: current.map((r) => ({ ...r })), life: { ...currentLife } })
    setEditing(true)
  }
  function cancelEdit() {
    if (snapshot) {
      setRows((prev) => ({ ...prev, [assay]: snapshot.rows }))
      setLife((prev) => ({ ...prev, [assay]: snapshot.life }))
    }
    setSnapshot(null)
    setEditing(false)
  }
  function editCell(i: number, field: 'blood' | 'saliva', raw: string) {
    setRows((prev) => {
      const next = prev[assay].map((r) => ({ ...r }))
      next[i] = { ...next[i], [field]: clampCell(raw, next[i].unit) }
      return { ...prev, [assay]: next }
    })
    // Any edit drops the row into an unsaved draft, attributed to the current actor.
    setLife((prev) => ({ ...prev, [assay]: { status: 'draft', by: actor.id, when: '' } }))
  }
  async function save() {
    // Reviewer save parks the change pending an approver; approver save publishes it live.
    const prevLife = life[assay]
    const next: Life = isApprover
      ? { status: 'approved', by: actor.id, when: today() }
      : { status: 'pending', by: actor.id, when: '' }
    setLife((prev) => ({ ...prev, [assay]: next }))
    setEditing(false)
    setSnapshot(null)
    // Pack the assay's rows into the opaque override payload (F18). The override name must be a
    // slug (^[A-Za-z0-9][.\w-]*$) — the assay display string has spaces/colons the backend rejects.
    try {
      const ack = await api.saveThresholds({ name: slugFor(assay), payload: { assay, rows: rows[assay] } })
      toast(`Saved ${assay} thresholds · v${ack.version}`, 'success')
    } catch (e) {
      setLife((prev) => ({ ...prev, [assay]: prevLife })) // reconcile: the write didn't land
      toast(`Couldn't save thresholds — ${errMsg(e)}`, 'error')
    }
  }
  async function approve() {
    if (!isApprover) return
    const prevLife = life[assay]
    setLife((prev) => ({ ...prev, [assay]: { status: 'approved', by: actor.id, when: today() } }))
    try {
      await api.approveThresholds(slugFor(assay))
      toast(`Approved ${assay} thresholds`, 'success')
    } catch (e) {
      setLife((prev) => ({ ...prev, [assay]: prevLife })) // reconcile
      toast(`Couldn't approve thresholds — ${errMsg(e)}`, 'error')
    }
  }

  const inputCls = editing
    ? 'w-[64px] rounded-[7px] border border-line-strong bg-card px-[7px] py-[5px] text-center font-mono text-[12.5px] font-semibold text-text focus:border-accent focus:outline-none'
    : 'w-[64px] cursor-default rounded-[7px] border border-transparent bg-transparent px-[7px] py-[5px] text-center font-mono text-[12.5px] font-semibold text-text outline-none'

  return (
    <section className="rounded-[13px] border border-line bg-card px-[18px] py-[17px]">
      <div className="flex items-center gap-[9px]">
        <div className="text-[14.5px] font-semibold text-text">Runbook thresholds</div>
        <span className="rounded-[5px] border border-proceed-bd bg-proceed-bg px-[7px] py-[2px] text-[10px] font-semibold uppercase tracking-[0.4px] text-proceed-fg">
          Editable
        </span>
      </div>
      <p className="mt-[3px] text-[12.5px] text-text-2">
        Operator-adjustable, keyed on <strong className="text-text">assay × sample type</strong>.
        Saliva loosens mapping / on-target; contamination is unchanged.
      </p>

      {/* Assay selector — swaps the whole table */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">Assay</span>
        <select
          value={assay}
          onChange={(e) => {
            setAssay(e.target.value)
            setEditing(false)
            setSnapshot(null)
          }}
          aria-label="Assay"
          className="min-w-[150px] cursor-pointer rounded-lg border border-line-strong bg-card px-[11px] py-[7px] text-[12.5px] font-medium text-text focus:border-accent focus:outline-none"
        >
          {ASSAYS.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      </div>

      {/* Status + audit + RBAC-gated action bar */}
      <div className="mt-3 flex flex-wrap items-center gap-[10px] rounded-[10px] border border-line bg-card-2 px-[13px] py-[10px]">
        <span
          className={`inline-flex items-center whitespace-nowrap rounded-full border px-[10px] py-[3px] text-[11px] font-semibold ${STATUS_CHIP[currentLife.status]}`}
        >
          {STATUS_LABEL[currentLife.status]}
        </span>
        <span className="text-[11.5px] text-text-3">{auditLine(currentLife)}</span>
        <div className="flex-1" />
        <button
          type="button"
          onClick={toggleRole}
          title="Toggle RBAC role (demo)"
          className="rounded-[7px] border border-line bg-transparent px-2 py-1 text-[10.5px] text-text-3"
        >
          as {role}
        </button>
        {!editing && (
          <button
            type="button"
            onClick={beginEdit}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12px] font-medium text-accent-strong"
          >
            <Pencil size={13} strokeWidth={1.9} />
            Edit thresholds
          </button>
        )}
        {editing && (
          <>
            <button
              type="button"
              onClick={cancelEdit}
              className="rounded-lg border border-line-strong bg-card px-[11px] py-1.5 text-[12px] text-text-2"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={save}
              className="rounded-lg bg-accent px-[13px] py-[7px] text-[12px] font-semibold text-white"
            >
              Save changes
            </button>
          </>
        )}
        {currentLife.status === 'pending' && isApprover && (
          <button
            type="button"
            onClick={approve}
            className="rounded-lg bg-proceed px-[13px] py-[7px] text-[12px] font-semibold text-white"
          >
            Approve
          </button>
        )}
      </div>

      <p className="mt-2 text-[11px] leading-[1.55] text-text-3">
        Guardrails: a gate can’t cross its hard-fail; percentages clamp 0–100. Every save writes an{' '}
        <strong className="text-text-2">audited edit</strong> (who · when · old→new); only an{' '}
        <strong className="text-text-2">approver</strong> makes a change live.
      </p>

      {/* Threshold matrix */}
      <div className="mt-[13px] overflow-hidden rounded-[10px] border border-line">
        <div className="grid grid-cols-[1.4fr_1fr_1fr] bg-card-2 text-[9.5px] font-semibold uppercase tracking-[0.4px] text-text-3">
          <div className="px-[13px] py-[9px]">Metric</div>
          <div className="px-[10px] py-[9px] text-center">Whole blood</div>
          <div className="px-[10px] py-[9px] text-center">Saliva</div>
        </div>
        {current.map((r, i) => (
          <div
            key={r.metric}
            className="grid grid-cols-[1.4fr_1fr_1fr] items-center border-t border-line"
          >
            <div className="px-[13px] py-[9px] text-[12.5px] text-text">{r.metric}</div>
            <div className="flex items-center justify-center gap-[6px] px-2 py-[7px]">
              <span className="shrink-0 font-mono text-[12px] text-text-3">{r.dir}</span>
              <input
                value={r.blood}
                readOnly={!editing}
                inputMode="decimal"
                onChange={(e) => editCell(i, 'blood', e.target.value)}
                aria-label={`${r.metric} · whole blood`}
                className={inputCls}
              />
              {r.unit && <span className="shrink-0 font-mono text-[12px] text-text-3">{r.unit}</span>}
            </div>
            <div className="flex items-center justify-center gap-[6px] bg-card-2 px-2 py-[7px]">
              <span className="shrink-0 font-mono text-[12px] text-text-3">{r.dir}</span>
              <input
                value={r.saliva}
                readOnly={!editing}
                inputMode="decimal"
                onChange={(e) => editCell(i, 'saliva', e.target.value)}
                aria-label={`${r.metric} · saliva`}
                className={inputCls}
              />
              {r.unit && <span className="shrink-0 font-mono text-[12px] text-text-3">{r.unit}</span>}
            </div>
          </div>
        ))}
      </div>

      {/* Required intake metadata — from the consumed runbook (F12) */}
      <div className="mt-[13px] text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">
        Required metadata
      </div>
      <div className="mt-[7px] flex flex-wrap gap-[6px]">
        {requiredMetadata.map((f) => (
          <span
            key={f}
            className="rounded-[6px] border border-line bg-card-2 px-[9px] py-[3px] font-mono text-[11px] text-text-2"
          >
            {f}
          </span>
        ))}
      </div>

      {disclaimer && <p className="mt-3 text-[11px] leading-[1.5] text-text-3">{disclaimer}</p>}
    </section>
  )
}
