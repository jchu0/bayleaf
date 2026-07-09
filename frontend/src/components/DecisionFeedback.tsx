import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Check, Send, ThumbsDown, ThumbsUp } from 'lucide-react'
import { api } from '../api'
import type { FeedbackReasonCode, FeedbackSignal, Gate, Verdict } from '../types'

// Reason quick-picks — decision-relevant, low-PII (higher signal than free text for tuning).
const REASONS: { code: FeedbackReasonCode; label: string }[] = [
  { code: 'threshold_too_strict', label: 'Too strict' },
  { code: 'threshold_too_loose', label: 'Too loose' },
  { code: 'wrong_root_cause', label: 'Wrong root cause' },
  { code: 'missing_context', label: 'Missing context' },
  { code: 'other', label: 'Other' },
]

type Phase = 'idle' | 'submitting' | 'done' | 'error'

// A quiet "was this verdict right?" footer inside the expanded decision card. It posts
// off-gate telemetry (never influences the verdict, ADR-0001) keyed to the exact call the
// operator is reacting to (verdict + gate + rule_ids + card content hash).
export function DecisionFeedback({
  runId,
  sampleId,
  verdict,
  gate,
  ruleIds,
  cardContentHash,
}: {
  runId: string
  sampleId: string
  verdict: Verdict
  gate?: Gate | null
  ruleIds: string[]
  cardContentHash: string
}) {
  const { pathname } = useLocation()
  const [signal, setSignal] = useState<FeedbackSignal | null>(null)
  const [reason, setReason] = useState<FeedbackReasonCode | null>(null)
  const [message, setMessage] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')

  function reset() {
    setSignal(null)
    setReason(null)
    setMessage('')
    setPhase('idle')
  }

  async function submit() {
    if (!signal) return
    setPhase('submitting')
    try {
      await api.feedback({
        target: 'decision',
        signal,
        reason_code: reason,
        message: message.trim() || null,
        context: {
          run_id: runId,
          sample_id: sampleId,
          verdict,
          gate: gate ?? null,
          rule_ids: ruleIds,
          card_content_hash: cardContentHash,
          route: pathname,
          screen: 'Decision cards',
        },
      })
      setPhase('done')
    } catch {
      setPhase('error')
    }
  }

  if (phase === 'done') {
    return (
      <div
        className="mt-4 flex items-center gap-2 border-t border-line pt-3 text-[12px] text-proceed-fg"
        role="status"
      >
        <Check size={14} />
        Thanks — feedback recorded.
        <button onClick={reset} className="ml-1 text-text-3 underline-offset-2 hover:underline">
          Change
        </button>
      </div>
    )
  }

  return (
    <div className="mt-4 border-t border-line pt-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[12px] text-text-3">Does this verdict match your call?</span>
        <div className="flex gap-1.5">
          <ThumbButton active={signal === 'agree'} tone="agree" onClick={() => setSignal('agree')} />
          <ThumbButton active={signal === 'disagree'} tone="disagree" onClick={() => setSignal('disagree')} />
        </div>
      </div>

      {signal && (
        <div className="pg-fade mt-3">
          <div className="flex flex-wrap gap-1.5">
            {REASONS.map((r) => (
              <button
                key={r.code}
                onClick={() => setReason(reason === r.code ? null : r.code)}
                className={`rounded-[20px] border px-3 py-1 text-[13px] transition-colors ${
                  reason === r.code
                    ? 'border-accent bg-accent-weak font-medium text-accent'
                    : 'border-line bg-card text-text-2 hover:border-line-strong'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            maxLength={2000}
            placeholder="Add context (optional — no names or PHI)"
            className="mt-2 min-h-[64px] w-full resize-none rounded-lg border border-line bg-card-2 px-3 py-2 text-[13px] text-text placeholder:text-text-3 focus:border-accent focus:outline-none"
          />
          <div className="mt-2 flex items-center justify-between">
            <span className={`text-[11px] ${message.length > 1800 ? 'text-hold-fg' : 'text-text-3'}`}>
              {message.length}/2000
            </span>
            <div className="flex items-center gap-2">
              <button onClick={reset} className="rounded-lg px-2.5 py-1.5 text-[12px] text-text-2 hover:text-text">
                Dismiss
              </button>
              <button
                onClick={submit}
                disabled={phase === 'submitting'}
                className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-[12px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                <Send size={14} />
                {phase === 'submitting' ? 'Sending…' : 'Send'}
              </button>
            </div>
          </div>
          {phase === 'error' && (
            <div className="mt-2 rounded-lg border border-escalate-bd bg-escalate-bg px-3 py-2 text-[12px] text-escalate-fg">
              Couldn't save feedback —{' '}
              <button onClick={submit} className="font-medium underline">
                try again
              </button>
              .
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ThumbButton({
  active,
  tone,
  onClick,
}: {
  active: boolean
  tone: 'agree' | 'disagree'
  onClick: () => void
}) {
  const Icon = tone === 'agree' ? ThumbsUp : ThumbsDown
  // Disagree highlights amber (a flag for review), NOT escalate-red — a downvote must never
  // read as a decision alarm.
  const activeCls =
    tone === 'agree'
      ? 'border-proceed-bd bg-proceed-bg text-proceed-fg'
      : 'border-hold-bd bg-hold-bg text-hold-fg'
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      aria-label={tone === 'agree' ? 'Verdict matches my call' : 'Verdict does not match my call'}
      className={`grid h-8 w-8 place-items-center rounded-lg border transition-colors ${
        active ? activeCls : 'border-line bg-card text-text-2 hover:border-line-strong hover:text-text'
      }`}
    >
      <Icon size={15} />
    </button>
  )
}
