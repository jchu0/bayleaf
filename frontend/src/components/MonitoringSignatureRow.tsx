import { Calendar, ChevronRight, ExternalLink, EyeOff, RotateCcw, Star } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { AgentProposal, MonitoringSignature } from '../types'
import { GATE_LABEL } from '../verdict'

// types.ts (frozen) doesn't type affected_run_ids on MonitoringSignature, though the aggregate
// now serves it — read it via a defensive cast so the chips render without touching the frozen
// type, and degrade to the honest empty-state when an older/partial payload omits it.
type SignatureWithRuns = MonitoringSignature & { affected_run_ids?: string[] }

// Month-abbreviated ISO date for the first→last-seen range, matching the prototype's "Jun 26 →
// Jul 8" (PipeGuard.dc.html:1383/2286). Parses the YYYY-MM-DD parts directly — no Date object, so
// there's no timezone off-by-one — and falls back to the raw string if it isn't a plain date.
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
function shortSeen(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!m) return iso
  const month = MONTHS[Number(m[2]) - 1]
  return month ? `${month} ${Number(m[3])}` : iso
}

// A recurring-issue-signature row on the fixed 5-column grid (chevron · signature · first→last
// seen · frequency · trend). The whole header row toggles the detail panel open; the detail is a
// sibling of the header (not nested), so its links/buttons don't bubble into the toggle.
//
// Honesty invariants held here: first_seen/last_seen render only when the aggregate carries them
// (a signature with only undated runs shows no range — omitted, never faked); a flat/absent trend
// draws no glyph; the Escalate CTA hits the advisory read-only repair endpoint and never mutates
// a verdict (rules decide / AI advises).
export function MonitoringSignatureRow({
  sig,
  open,
  onToggle,
  windowShort,
  windowLabel,
  cleared = false,
  onToggleClear,
}: {
  sig: MonitoringSignature
  open: boolean
  onToggle: () => void
  /** e.g. "7d" — for the "/ window" frequency suffix. */
  windowShort: string
  /** e.g. "7 days" — spelled-out window for the detail copy. */
  windowLabel: string
  /** Whether this row is currently cleared from the main view (M4). */
  cleared?: boolean
  /** Clear this signature from view / restore it — a reversible, client-side view filter (never
   *  a DB purge); the signature stays searchable and recoverable. Omit to hide the control. */
  onToggleClear?: () => void
}) {
  // Stable, unique, human-readable id for the signature (M6). The `signature` hash is already
  // unique per recurring pattern (rule_id can repeat across patterns) — surface a short prefix of it.
  const sigId = `SIG-${sig.signature.slice(0, 8)}`
  const [escState, setEscState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [proposal, setProposal] = useState<AgentProposal | null>(null)
  const [escError, setEscError] = useState<string | null>(null)

  const affectedRuns = (sig as SignatureWithRuns).affected_run_ids ?? []
  const recurring = sig.count >= 3
  const autoNote = recurring ? `Auto-escalated · recurred ${sig.count}×` : 'Available for manual escalation'
  const desc = `${sig.title}. Flagged by ${sig.rule_id} on the ${GATE_LABEL[sig.gate]} gate; recorded ${sig.count}× in the last ${windowLabel}.`

  async function escalate() {
    setEscState('loading')
    setEscError(null)
    try {
      // Advisory, off-gate read: returns a RepairProposal for a human to weigh, never an action.
      // The repair endpoint accepts ?window=, so we thread the operator's active window directly
      // (the typed api.signatureRepair() client is frozen at signature-only arity) — the proposal
      // is then computed over the same span the row shows, not the endpoint's default window.
      const res = await fetch(
        `/api/monitoring/signatures/${encodeURIComponent(sig.signature)}/repair?window=${encodeURIComponent(windowShort)}`,
      )
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const p = (await res.json()) as AgentProposal
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
        {/* Col 2 — unique id (M6) + signature (rule · title), mono, ellipsis */}
        <span className="min-w-0 truncate font-mono text-[12px] text-text">
          <span className="text-text-3" title={`Signature id · ${sig.signature}`}>{sigId}</span> · {sig.rule_id} · {sig.title}
        </span>
        {/* Col 3 — first → last seen; omitted honestly when only undated runs carry the signature */}
        {sig.first_seen && sig.last_seen ? (
          <span className="inline-flex min-w-0 items-center gap-[5px] whitespace-nowrap font-mono text-[10.5px] text-text-3">
            <Calendar size={12} className="shrink-0" />
            {shortSeen(sig.first_seen)} → {shortSeen(sig.last_seen)}
          </span>
        ) : (
          <span />
        )}
        {/* Col 4 — frequency */}
        <span className="whitespace-nowrap text-[11px] text-text-2">
          <strong className="font-mono text-text">{sig.count}×</strong> / {windowShort}
        </span>
        {/* Col 5 — trend glyph; ▲ rising / ▼ falling, nothing when flat or absent */}
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
            // Honest empty: no run mapping came back for this signature (e.g. an older/partial
            // payload). No fabricated links — chips render only from real ids the aggregate serves.
            <div className="mt-[13px] text-[10.5px] text-text-3">
              No affected runs recorded for this signature.
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
            {onToggleClear && (
              <button
                type="button"
                onClick={onToggleClear}
                title={cleared ? 'Restore this signature to the main list' : 'Clear from view (reversible — not purged; still searchable)'}
                className="inline-flex items-center gap-[6px] whitespace-nowrap rounded-[8px] border border-line-strong bg-card px-[11px] py-[7px] text-[11.5px] font-medium text-text-2 transition-colors hover:border-line"
              >
                {cleared ? <RotateCcw size={13} /> : <EyeOff size={13} />}
                {cleared ? 'Restore to view' : 'Clear from view'}
              </button>
            )}
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
