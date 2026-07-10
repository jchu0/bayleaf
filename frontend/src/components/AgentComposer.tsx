import { type KeyboardEvent, useState } from 'react'
import { ExternalLink, MessageSquare, Paperclip, Send } from 'lucide-react'

// Canned triage prompts surfaced as one-click chips above the composer, so an operator can
// drive the (advisory) agent without typing. They reuse the same submit path as free text.
const QUICK_ASKS = [
  'How sure are you this is a swap, not contamination?',
  'What if I re-demux with the corrected sheet?',
  'Which other sample is affected?',
] as const

type Msg = { role: 'user' | 'agent'; text: string }

// "Ask the agent" chat composer (dc.html 1166-1204). Multi-line textarea (Enter sends,
// Shift+Enter newlines), suggestion chips, and a pop-out/minimize toggle that lifts the
// window into a fixed modal. INV: advisory only — no message ever sets or changes a verdict
// or confidence; the honest offline path echoes that the live Q&A seam is env-armed rather
// than fabricating a model answer.
export function AgentComposer({ offline }: { offline: boolean }) {
  const [thread, setThread] = useState<Msg[]>([])
  const [draft, setDraft] = useState('')
  const [popped, setPopped] = useState(false)

  // The single ask path shared by the textarea and the quick-ask chips. The live agent is
  // env-armed (PIPEGUARD_TRIAGE_AGENT=claude); offline we append an honest stub reply rather
  // than invent an answer. Either way, it can never touch the verdict.
  function submit(raw: string) {
    const q = raw.trim()
    if (!q) return
    setThread((t) => [
      ...t,
      { role: 'user', text: q },
      {
        role: 'agent',
        text: offline
          ? "Offline (rule-derived): I can't change the verdict — that's the rule engine's call. Live agent Q&A is env-armed (set PIPEGUARD_TRIAGE_AGENT=claude) to reason over this run's findings and the linked corpora."
          : "I can only reason over this run's findings and the linked corpora — I can't change the verdict, that's the rule engine's call. See the suggested action above for the fastest confirmation path.",
      },
    ])
    setDraft('')
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter inserts a newline (multi-line composer).
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit(draft)
    }
  }

  const windowClass = popped
    ? 'fixed left-1/2 top-[4vh] z-[60] flex h-[92vh] w-[880px] max-w-[92vw] -translate-x-1/2 flex-col overflow-hidden rounded-[16px] border border-line-strong bg-card shadow-[0_24px_60px_rgba(16,24,40,.28)]'
    : 'mt-[14px] flex flex-col overflow-hidden rounded-[14px] border border-line bg-card shadow-card'

  const msgWindowClass = popped
    ? 'min-h-0 flex-1 overflow-y-auto bg-card-2 px-[20px] py-[18px]'
    : 'max-h-[300px] overflow-y-auto bg-card-2 px-[18px] py-[16px]'

  return (
    <>
      {/* Scrim behind the popped-out window — click to minimize. */}
      {popped && (
        <div
          className="fixed inset-0 z-[59] bg-[rgba(16,24,40,.34)]"
          onClick={() => setPopped(false)}
        />
      )}

      <div className={windowClass}>
        {/* header */}
        <div className="flex shrink-0 items-center gap-[9px] border-b border-line px-[18px] py-[13px]">
          <MessageSquare size={16} strokeWidth={1.8} className="text-accent" />
          <span className="text-[13.5px] font-semibold text-text">Ask the agent</span>
          <span className="flex-1 text-[11px] text-text-3">Advisory · won't change the verdict</span>
          <button
            type="button"
            onClick={() => setPopped((p) => !p)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-[8px] border border-line-strong bg-card px-[10px] py-[5px] text-[11.5px] font-medium text-text-2"
          >
            <ExternalLink size={13} strokeWidth={1.9} />
            {popped ? 'Minimize' : 'Pop out'}
          </button>
        </div>

        {/* message window */}
        <div className={msgWindowClass}>
          {thread.length > 0 ? (
            <div className="flex flex-col gap-[9px]">
              {thread.map((m, i) => (
                <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={
                      m.role === 'user'
                        ? 'max-w-[84%] rounded-[13px_13px_3px_13px] bg-accent px-[12px] py-[9px] text-[12.5px] leading-[1.55] text-white'
                        : 'max-w-[84%] rounded-[13px_13px_13px_3px] border border-line bg-card-2 px-[12px] py-[9px] text-[12.5px] leading-[1.55] text-text'
                    }
                  >
                    {m.text}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center gap-[9px] px-4 py-6 text-center text-text-3">
              <MessageSquare size={26} strokeWidth={1.5} />
              <div className="max-w-[300px] text-[12.5px] leading-[1.5]">
                No messages yet. Ask a question below, or start from a suggested prompt — the agent's replies
                appear here.
              </div>
            </div>
          )}
        </div>

        {/* composer footer */}
        <div className="shrink-0 px-[18px] py-[14px]">
          {/* suggestion chips — horizontally scrollable, filled accent pills */}
          <div className="flex gap-[7px] overflow-x-auto pb-[3px]">
            {QUICK_ASKS.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => submit(q)}
                className="shrink-0 whitespace-nowrap rounded-full border border-[#cfe0fb] bg-accent-weak px-[11px] py-[6px] text-left text-[12px] text-accent-strong"
              >
                {q}
              </button>
            ))}
          </div>

          {/* input box: multi-line textarea + helper/send footer bar */}
          <div className="mt-[11px] overflow-hidden rounded-[14px] border border-line-strong bg-card shadow-card">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKey}
              placeholder="Message the triage agent…"
              rows={3}
              className="block max-h-[240px] min-h-[88px] w-full resize-y border-none bg-transparent px-[15px] py-[13px] text-[13.5px] leading-[1.55] text-text outline-none placeholder:text-text-3"
            />
            <div className="flex items-center gap-[10px] border-t border-line bg-card-2 py-[9px] pl-[14px] pr-[11px]">
              <Paperclip size={16} strokeWidth={1.8} className="shrink-0 text-text-3" />
              <span className="flex-1 text-[10.5px] leading-[1.4] text-text-3">
                Advisory · the agent can't change the verdict ·{' '}
                <strong className="font-semibold text-text-2">Enter</strong> to send,{' '}
                <strong className="font-semibold text-text-2">Shift+Enter</strong> for a new line
              </span>
              <button
                type="button"
                onClick={() => submit(draft)}
                className="inline-flex shrink-0 items-center gap-[7px] rounded-[9px] bg-accent px-[15px] py-2 text-[12.5px] font-semibold text-white"
              >
                Send
                <Send size={14} strokeWidth={1.9} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
