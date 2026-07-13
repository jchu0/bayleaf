import { type KeyboardEvent, useState } from 'react'
import { ExternalLink, MessageSquare, Paperclip, Send } from 'lucide-react'
import { api, type AgentReply } from '../api'

// Canned triage prompts surfaced as one-click chips above the composer, so an operator can
// drive the (advisory) agent without typing. They reuse the same submit path as free text.
const QUICK_ASKS = [
  'How sure are you this is a swap, not contamination?',
  'What if I re-demux with the corrected sheet?',
  'Which other sample is affected?',
] as const

// An agent turn carries the real AgentReply (its cited answer + provenance) so we render what the
// server actually returned, never a hardcoded string; `error` marks a turn where the ask failed.
type Msg =
  | { role: 'user'; text: string }
  | { role: 'agent'; text: string; reply?: AgentReply; error?: boolean }

// "Ask the agent" chat composer (dc.html 1166-1204). Multi-line textarea (Enter sends,
// Shift+Enter newlines), suggestion chips, and a pop-out/minimize toggle that lifts the
// window into a fixed modal. INV: advisory only — no message ever sets or changes a verdict
// or confidence; every reply is a REAL server AgentReply (the offline stub returns a
// retrieval-grounded answer, never a fabricated constant), rendered with its honest provenance.
export function AgentComposer({
  runId,
  sampleId,
  offline,
}: {
  runId: string
  sampleId: string
  offline: boolean
}) {
  const [thread, setThread] = useState<Msg[]>([])
  const [draft, setDraft] = useState('')
  const [popped, setPopped] = useState(false)
  const [sending, setSending] = useState(false)

  // The single ask path shared by the textarea and the quick-ask chips. It POSTs to the advisory
  // /ask endpoint and renders the returned AgentReply verbatim — the offline stub is a real
  // retrieval-grounded answer, the armed agent is prose; either way it can never touch the verdict.
  async function submit(raw: string) {
    const q = raw.trim()
    if (!q || sending) return
    setThread((t) => [...t, { role: 'user', text: q }])
    setDraft('')
    setSending(true)
    try {
      const reply = await api.askAgent(runId, sampleId, q)
      setThread((t) => [...t, { role: 'agent', text: reply.answer, reply }])
    } catch (e) {
      // An honest failure surface — never a fabricated answer standing in for a real one.
      setThread((t) => [
        ...t,
        { role: 'agent', text: `Couldn't reach the advisory agent — ${String(e)}`, error: true },
      ])
    } finally {
      setSending(false)
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter inserts a newline (multi-line composer).
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void submit(draft)
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
              {thread.map((m, i) =>
                m.role === 'user' ? (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[84%] rounded-[13px_13px_3px_13px] bg-accent px-[12px] py-[9px] text-[12.5px] leading-[1.55] text-white">
                      {m.text}
                    </div>
                  </div>
                ) : (
                  <div key={i} className="flex max-w-[84%] flex-col items-start gap-[3px]">
                    <div
                      className={`rounded-[13px_13px_13px_3px] border px-[12px] py-[9px] text-[12.5px] leading-[1.55] ${
                        m.error
                          ? 'border-escalate-bd bg-escalate-bg text-escalate-fg'
                          : 'border-line bg-card-2 text-text'
                      }`}
                    >
                      {m.text}
                    </div>
                    {/* Honest per-reply provenance: the REAL source ('stub' retrieval vs armed Claude)
                        and grounding-citation count, so a deterministic reply never reads as model prose. */}
                    {m.reply && (
                      <div className="flex flex-wrap items-center gap-x-[7px] gap-y-0.5 pl-[2px] text-[10.5px] text-text-3">
                        <span>
                          {m.reply.generated_by === 'claude' && m.reply.model
                            ? `Claude · ${m.reply.model}`
                            : 'Rule-derived (retrieval)'}
                        </span>
                        {m.reply.citations.length > 0 && (
                          <span>
                            · {m.reply.citations.length} citation
                            {m.reply.citations.length === 1 ? '' : 's'}
                          </span>
                        )}
                        <span>· advisory</span>
                      </div>
                    )}
                  </div>
                ),
              )}
              {sending && (
                <div className="flex justify-start">
                  <div className="max-w-[84%] rounded-[13px_13px_13px_3px] border border-line bg-card-2 px-[12px] py-[9px] text-[12.5px] italic leading-[1.55] text-text-3">
                    Asking the advisory agent…
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center gap-[9px] px-4 py-6 text-center text-text-3">
              <MessageSquare size={26} strokeWidth={1.5} />
              <div className="max-w-[300px] text-[12.5px] leading-[1.5]">
                No messages yet. Ask a question below, or start from a suggested prompt — the agent's replies
                appear here.
                {offline && (
                  <>
                    {' '}
                    The live agent isn't armed, so replies are deterministic (retrieval-grounded), not model prose.
                  </>
                )}
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
                onClick={() => void submit(q)}
                disabled={sending}
                className="shrink-0 whitespace-nowrap rounded-full border border-[#cfe0fb] bg-accent-weak px-[11px] py-[6px] text-left text-[12px] text-accent-strong disabled:opacity-50"
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
                onClick={() => void submit(draft)}
                disabled={sending || !draft.trim()}
                className="inline-flex shrink-0 items-center gap-[7px] rounded-[9px] bg-accent px-[15px] py-2 text-[12.5px] font-semibold text-white disabled:opacity-50"
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
