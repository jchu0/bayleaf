import { Calendar, ChevronRight, ExternalLink, Star } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { AgentProposal, MonitoringSignature } from '../types'
import { GATE_LABEL } from '../verdict'

// A signature carries no per-signature affected-run list in the live aggregate yet (F2 backend
// gap) — read it defensively so the chips light up the moment the backend serves them, without
// fabricating a mapping in the meantime.
type SignatureWithRuns = MonitoringSignature & { affected_run_ids?: string[] }

// A recurring-issue-signature row on the fixed 5-column grid (chevron · signature · first→last
// seen · frequency · trend). The whole header row toggles the detail panel open; the detail is a
// sibling of the header (not nested), so its links/buttons don't bubble into the toggle.
//
// Honesty invariants held here: first_seen/last_seen/trend are omitted (not faked) until the
// backend carries them; the Escalate CTA hits the advisory read-only repair endpoint and never
// mutates a verdict (rules decide / AI advises).
export function MonitoringSignatureRow({
  sig,
  open,
  onToggle,
  windowShort,
  windowLabel,
}: {
  sig: MonitoringSignature
  open: boolean
  onToggle: () => void
  /** e.g. "7d" — for the "/ window" frequency suffix. */
  windowShort: string
  /** e.g. "7 days" — spelled-out window for the detail copy. */
  windowLabel: string
}) {
  const [escState, setEscState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [proposal, setProposal] = useState<AgentProposal | null>(null)
  const [escError, setEscError] = useState<string | null>(null)

  const affectedRuns = (sig as SignatureWithRuns).affected_run_ids ?? []
  const hasDates = Boolean(sig.first_seen && sig.last_seen)
  const recurring = sig.count >= 3
  const autoNote = recurring ? `Auto-escalated · recurred ${sig.count}×` : 'Available for manual escalation'
  const desc = `${sig.title}. Flagged by ${sig.rule_id} on the ${GATE_LABEL[sig.gate]} gate; recorded ${sig.count}× in the last ${windowLabel}.`

  async function escalate() {
    setEscState('loading')
    setEscError(null)
    try {
      // Advisory, off-gate read: returns a RepairProposal for a human to weigh, never an action.
      const p = await api.signatureRepair(sig.signature)
      setProposal(p)
      setEscState('done')
    } catch (e) {
      setEscError(String(e))
      setEscState('error')
    }
  }

  return (
    <div className="overflow-hidden rounded-[10px] border border-line bg-card">
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onToggle()
          }
        }}
        className="grid cursor-pointer items-center gap-3 px-[14px] py-[11px] text-left"
        style={{ gridTemplateColumns: '18px minmax(0,1fr) 148px 104px 18px' }}
      >
        {/* Col 1 — rotating chevron */}
        <ChevronRight
          size={14}
          strokeWidth={2.4}
          className={`shrink-0 text-text-3 transition-transform duration-200 ${open ? 'rotate-90' : ''}`}
        />
        {/* Col 2 — signature (rule · title), mono, ellipsis */}
        <span className="min-w-0 truncate font-mono text-[12px] text-text">
          {sig.rule_id} · {sig.title}
        </span>
        {/* Col 3 — first → last seen; omitted honestly until the aggregate carries dates (F2) */}
        {hasDates ? (
          <span className="inline-flex min-w-0 items-center gap-[5px] whitespace-nowrap font-mono text-[10.5px] text-text-3">
            <Calendar size={12} className="shrink-0" />
            {sig.first_seen} → {sig.last_seen}
          </span>
        ) : (
          <span />
        )}
        {/* Col 4 — frequency */}
        <span className="whitespace-nowrap text-[11px] text-text-2">
          <strong className="font-mono text-text">{sig.count}×</strong> / {windowShort}
        </span>
        {/* Col 5 — trend glyph; empty until the backend serves a trend (F2) */}
        <span className="text-center text-[12px] font-bold">
          {sig.trend === 'up' ? (
            <span className="text-escalate">▲</span>
          ) : sig.trend === 'down' ? (
            <span className="text-proceed">▼</span>
          ) : null}
        </span>
      </div>

      {open && (
        <div className="border-t border-line bg-card-2 pb-[15px] pl-[34px] pr-[16px] pt-[14px]">
          <div className="text-[12.5px] leading-[1.55] text-text-2">{desc}</div>

          {affectedRuns.length > 0 ? (
            <>
              <div className="mb-[6px] mt-[13px] text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">
                Affected runs · {affectedRuns.length}
              </div>
              <div className="flex flex-wrap gap-[6px]">
                {affectedRuns.map((rid) => (
                  <Link
                    key={rid}
                    to={`/runs/${encodeURIComponent(rid)}?filter=attention`}
                    title="Open this run's decision cards · Needs attention"
                    className="inline-flex items-center gap-[5px] rounded-[6px] border border-line-strong bg-card px-[9px] py-[3px] font-mono text-[10.5px] text-accent-strong transition-colors hover:border-accent"
                  >
                    {rid}
                    <ExternalLink size={10} className="shrink-0" />
                  </Link>
                ))}
              </div>
            </>
          ) : (
            // Honest empty: the aggregate does not yet map a signature to its runs (F2). No
            // fabricated links — the chips light up once the backend carries affected_run_ids.
            <div className="mt-[13px] text-[10.5px] text-text-3">
              Per-signature affected-run list not yet served by the monitoring aggregate.
            </div>
          )}

          <div className="mt-[14px] flex flex-wrap items-center gap-[11px]">
            <button
              type="button"
              onClick={escalate}
              disabled={escState === 'loading'}
              className="inline-flex items-center gap-[6px] whitespace-nowrap rounded-[8px] bg-escalate px-[13px] py-[7px] text-[11.5px] font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-60"
            >
              <Star size={13} />
              {escState === 'loading' ? 'Consulting repair agent…' : 'Escalate to repair agent'}
            </button>
            <span className="text-[10.5px] text-text-3">{autoNote}</span>
          </div>

          {escState === 'done' && proposal && (
            // Advisory result, read-only and clearly labelled off-gate (rules decide / AI advises).
            <div className="mt-[10px] rounded-lg border border-line bg-card px-3 py-2">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">
                Repair agent · advisory ({proposal.mode})
              </div>
              <p className="text-[11.5px] leading-normal text-text-2">{proposal.summary}</p>
              <p className="mt-1 text-[10px] text-text-3">
                Advisory only — off the deterministic gate; no verdict changes.
              </p>
            </div>
          )}
          {escState === 'error' && (
            <p className="mt-[10px] text-[10.5px] text-escalate-fg">
              Repair agent unavailable ({escError}). Advisory only — no verdict changes.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
