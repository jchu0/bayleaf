import { useState } from 'react'
import { Clock, PauseCircle, Play } from 'lucide-react'
import { api } from '../api'
import { useRole } from '../context/RoleContext'
import type { IntakeStatus } from '../types'
import { useConfirm } from './ConfirmDialog'
import { useToast } from './Toast'

// Release control for a HELD or SCHEDULED intake job (ADR-0021). A parked run is registered but its
// driver has not fired — an operator releases it to start real compute (POST /api/runs/:id/release).
// Rendering only makes sense for a held/scheduled status; it returns null otherwise so a caller can
// mount it unconditionally. Off the deterministic gate — it triggers execution, never a verdict.
export function ReleaseControl({
  status,
  onReleased,
  className,
}: {
  status: IntakeStatus
  // Called with the fresh IntakeStatus the release returns (status flips to `running`) so the parent
  // can poll to completion / refetch. Release is reviewer/approver-gated + confirm-gated (real compute).
  onReleased?: (next: IntakeStatus) => void
  className?: string
}) {
  const { toast } = useToast()
  const confirm = useConfirm()
  const { isReviewer } = useRole()
  const [busy, setBusy] = useState(false)

  const held = status.status === 'held'
  const scheduled = status.status === 'scheduled'
  if (!held && !scheduled) return null

  // Honest scheduled_at rendering — the operator sees the exact parked time, never a fabricated one.
  const whenLabel = (() => {
    if (!status.scheduled_at) return null
    const d = new Date(status.scheduled_at)
    return Number.isNaN(d.getTime()) ? status.scheduled_at : d.toLocaleString()
  })()

  async function release() {
    const ok = await confirm({
      title: `Release ${status.run_id} for processing now?`,
      body: 'Fires the pipeline driver immediately — this starts real compute through the approved pipeline and cannot be paused once running.',
      confirmLabel: 'Release & process',
    })
    if (!ok) return
    setBusy(true)
    try {
      const next = await api.releaseRun(status.run_id)
      toast(`Run ${status.run_id} released — processing now.`, 'success')
      onReleased?.(next)
    } catch (e) {
      toast(`Couldn't release run — ${e instanceof Error ? e.message : String(e)}`, 'error')
      setBusy(false)
    }
  }

  const Icon = held ? PauseCircle : Clock
  return (
    <div
      className={`flex flex-wrap items-center gap-3 rounded-[11px] border border-hold-bd bg-hold-bg px-[14px] py-3 ${className ?? ''}`}
    >
      <Icon size={18} strokeWidth={1.9} className="shrink-0 text-hold-fg" />
      <div className="min-w-0 flex-1 text-[12.5px] leading-relaxed text-hold-fg">
        {held ? (
          <>
            <strong>Held — awaiting release.</strong> This run is registered but not processing.
            {status.pipeline ? (
              <>
                {' '}
                Pipeline <span className="font-mono">{status.pipeline}</span>.
              </>
            ) : null}
          </>
        ) : (
          <>
            <strong>Scheduled{whenLabel ? ` for ${whenLabel}` : ''}.</strong> Parked until released —
            a time-based auto-release is a deferred seam, so an operator releases it manually.
            {status.pipeline ? (
              <>
                {' '}
                Pipeline <span className="font-mono">{status.pipeline}</span>.
              </>
            ) : null}
          </>
        )}
      </div>
      {isReviewer ? (
        <button
          type="button"
          onClick={() => void release()}
          disabled={busy}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-[8px] bg-accent px-3.5 py-2 text-[12.5px] font-semibold text-white transition-opacity disabled:opacity-60"
        >
          <Play size={14} strokeWidth={2} />
          {busy ? 'Releasing…' : scheduled ? 'Release now' : 'Release / process now'}
        </button>
      ) : (
        <span className="shrink-0 text-[11.5px] font-medium text-text-3">
          Requires reviewer or approver
        </span>
      )}
    </div>
  )
}
