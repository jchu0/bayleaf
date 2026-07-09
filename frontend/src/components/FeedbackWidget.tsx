import { useEffect, useRef, useState } from 'react'
import { useLocation, useParams, useSearchParams } from 'react-router-dom'
import { AlertCircle, Check, Heart, HelpCircle, Lightbulb, MessageSquarePlus, Send, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { api } from '../api'
import type { FeedbackKind } from '../types'

const KINDS: { kind: FeedbackKind; label: string; Icon: LucideIcon }[] = [
  { kind: 'idea', label: 'Idea', Icon: Lightbulb },
  { kind: 'problem', label: 'Problem', Icon: AlertCircle },
  { kind: 'confusing', label: 'Confusing', Icon: HelpCircle },
  { kind: 'praise', label: 'Praise', Icon: Heart },
]

// Coarse human label for the current screen — pins a product report to a surface without
// needing the route table (mirrors TopBar's crumb).
function screenLabel(p: string): string {
  if (p === '/') return 'Runs'
  if (p.includes('/intake')) return 'Intake gate'
  if (p.includes('/provenance')) return 'Provenance'
  if (p.includes('/agent')) return 'Agent triage'
  if (p.startsWith('/queue')) return 'Review queue'
  if (p.startsWith('/monitoring')) return 'Monitoring'
  if (p.startsWith('/settings')) return 'Settings'
  if (p.startsWith('/runs/')) return 'Decision cards'
  return 'PipeGuard'
}

type Phase = 'idle' | 'submitting' | 'done' | 'error'

// A single global feedback FAB, mounted once in the Layout as a sibling of <Outlet/> so it
// rides every screen without touching any of them. Posts off-gate product telemetry (W12).
export function FeedbackWidget() {
  const { pathname } = useLocation()
  const params = useParams()
  const [search] = useSearchParams()
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<FeedbackKind>('idea')
  const [message, setMessage] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (open && phase !== 'done') textareaRef.current?.focus()
  }, [open, phase])

  function close() {
    setOpen(false)
    setKind('idea')
    setMessage('')
    setPhase('idle')
  }

  async function submit() {
    if (!message.trim()) return
    setPhase('submitting')
    try {
      await api.feedback({
        target: 'product',
        source: 'product-fab',
        kind,
        message: message.trim(),
        context: {
          run_id: params.runId ?? null,
          sample_id: search.get('sample') ?? null,
          route: pathname,
          screen: screenLabel(pathname),
        },
      })
      setPhase('done')
    } catch {
      setPhase('error')
    }
  }

  // Auto-dismiss shortly after a successful submit.
  useEffect(() => {
    if (phase !== 'done') return
    const t = setTimeout(close, 1600)
    return () => clearTimeout(t)
  }, [phase])

  return (
    <div className="fixed bottom-6 right-6 z-40">
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={close} />
          <div
            role="dialog"
            aria-label="Share feedback"
            className="pg-fade absolute bottom-[calc(100%+10px)] right-0 z-50 w-[340px] overflow-hidden rounded-xl border border-line bg-card shadow-pop"
          >
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <span className="text-[14px] font-semibold text-text">Share feedback</span>
              <button
                onClick={close}
                aria-label="Close"
                className="grid h-7 w-7 place-items-center rounded-lg text-text-3 hover:bg-page"
              >
                <X size={15} />
              </button>
            </div>
            <div className="px-4 py-3">
              {phase === 'done' ? (
                <div className="flex items-center gap-2 py-4 text-[13px] text-proceed-fg" role="status">
                  <Check size={15} />
                  Thanks — feedback recorded.
                </div>
              ) : (
                <>
                  <p className="mb-3 text-[12px] text-text-2">
                    Product feedback only — not part of any QC decision. No names, emails, or sample data.
                  </p>
                  <div role="radiogroup" aria-label="Feedback kind" className="mb-2 flex flex-wrap gap-1.5">
                    {KINDS.map(({ kind: k, label, Icon }) => (
                      <button
                        key={k}
                        role="radio"
                        aria-checked={kind === k}
                        onClick={() => setKind(k)}
                        className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] transition-colors ${
                          kind === k
                            ? 'border-accent bg-accent-weak text-accent'
                            : 'border-line bg-card text-text-2 hover:text-text'
                        }`}
                      >
                        <Icon size={13} />
                        {label}
                      </button>
                    ))}
                  </div>
                  <textarea
                    ref={textareaRef}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    maxLength={2000}
                    placeholder="What's on your mind? (no names or PHI)"
                    className="min-h-[80px] w-full resize-none rounded-lg border border-line bg-card-2 px-3 py-2 text-[13px] text-text placeholder:text-text-3 focus:border-accent focus:outline-none"
                  />
                  <div className="mt-2 flex items-center justify-between">
                    <span className={`text-[11px] ${message.length > 1800 ? 'text-hold-fg' : 'text-text-3'}`}>
                      {message.length}/2000
                    </span>
                    <button
                      onClick={submit}
                      disabled={phase === 'submitting' || !message.trim()}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-[12px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                    >
                      <Send size={14} />
                      {phase === 'submitting' ? 'Sending…' : 'Send'}
                    </button>
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
                </>
              )}
            </div>
          </div>
        </>
      )}
      {/* Icon-only by default; the label slides out to the left of the icon on hover
          (icon stays anchored at the fixed bottom-right corner). */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Share feedback"
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Share feedback"
        className="group relative z-50 flex items-center rounded-full border border-line bg-card p-3 text-[13px] font-medium text-text-2 shadow-pop transition-all hover:border-line-strong hover:pl-4 hover:text-text"
      >
        <span className="max-w-0 overflow-hidden whitespace-nowrap opacity-0 transition-all duration-200 group-hover:mr-1.5 group-hover:max-w-[72px] group-hover:opacity-100">
          Feedback
        </span>
        <MessageSquarePlus size={18} className="shrink-0 text-accent" />
      </button>
    </div>
  )
}
