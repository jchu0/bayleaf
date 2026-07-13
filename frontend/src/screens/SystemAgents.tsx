import { useCallback, useEffect, useRef, useState } from 'react'
import { Archive, Plus, RotateCcw, Send, Sparkles, Trash2, Wrench } from 'lucide-react'
import { PageHeader } from '../components/PageHeader'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/ConfirmDialog'
import { api } from '../api'
import type { ChatMessage, ChatSession, SystemAgentInfo } from '../types'

// System agents — the org-wide advisory agents (pipeline-repair, archivist) that act ACROSS runs
// and the whole organization, never on a single run and never on a verdict (ADR-0001). This page
// is a CHAT surface (design/system-agents-chat.md): pick an agent on the left, converse on the
// right, and revisit past chats. History is structured + retained; archive/delete are view-scoped
// soft-deletes (the record stays in the store for ML). Advisory + off-gate throughout.
const AGENT_ICON: Record<string, React.ReactNode> = {
  pipeline_repair: <Wrench size={15} strokeWidth={2} />,
  archivist: <Archive size={15} strokeWidth={2} />,
}

export function SystemAgents() {
  const { toast } = useToast()
  const confirm = useConfirm()
  const [agents, setAgents] = useState<SystemAgentInfo[]>([])
  const [selected, setSelected] = useState<string>('')
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [includeArchived, setIncludeArchived] = useState(false)
  const [active, setActive] = useState<ChatSession | null>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await api.chatList(includeArchived))
    } catch (e) {
      toast(`Couldn't load chats — ${(e as Error).message}`, 'error')
    }
  }, [includeArchived, toast])

  useEffect(() => {
    api.systemAgents().then((a) => {
      setAgents(a)
      setSelected((s) => s || a[0]?.id || '')
    }).catch(() => setAgents([]))
  }, [])

  useEffect(() => {
    void refreshSessions()
  }, [refreshSessions])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [active?.messages.length, sending])

  const mine = sessions.filter((s) => s.agent_id === selected)

  const openSession = async (id: string) => {
    try {
      setActive(await api.chatGet(id))
    } catch (e) {
      toast(`Couldn't open chat — ${(e as Error).message}`, 'error')
    }
  }

  const newChat = () => setActive(null)

  const send = async () => {
    const message = input.trim()
    if (!message || sending || !selected) return
    setSending(true)
    setInput('')
    // Optimistic: create a provisional session so the user turn shows immediately.
    const optimistic: ChatMessage = {
      id: `tmp-${Date.now()}`, role: 'user', content: message, ts: new Date().toISOString(),
      citations: [], generated_by: null, model: null,
    }
    setActive((cur) =>
      cur ? { ...cur, messages: [...cur.messages, optimistic] } : null,
    )
    try {
      const resp = await api.chatSend(selected, { message, session_id: active?.session_id })
      setActive(resp.session)
      await refreshSessions()
    } catch (e) {
      toast(`Send failed — ${(e as Error).message}`, 'error')
      setInput(message) // restore the text so it isn't lost
    } finally {
      setSending(false)
    }
  }

  const archiveSession = async (s: ChatSession) => {
    try {
      await api.chatArchive(s.session_id)
      if (active?.session_id === s.session_id) setActive(null)
      await refreshSessions()
      toast('Chat archived (retained for the record).', 'success')
    } catch (e) {
      toast(`Archive failed — ${(e as Error).message}`, 'error')
    }
  }

  const restoreSession = async (s: ChatSession) => {
    try {
      await api.chatRestore(s.session_id)
      await refreshSessions()
    } catch (e) {
      toast(`Restore failed — ${(e as Error).message}`, 'error')
    }
  }

  const deleteSession = async (s: ChatSession) => {
    const ok = await confirm({
      title: 'Delete this chat from your view?',
      body: 'It disappears from your chat list. The record is retained in the store for the audit trail and analytics — this is a view-scoped removal, not a hard delete.',
      confirmLabel: 'Delete',
    })
    if (!ok) return
    try {
      await api.chatDelete(s.session_id)
      if (active?.session_id === s.session_id) setActive(null)
      await refreshSessions()
      toast('Chat removed from your view.', 'success')
    } catch (e) {
      toast(`Delete failed — ${(e as Error).message}`, 'error')
    }
  }

  const agentLabel = (id: string) => agents.find((a) => a.id === id)?.label || id

  return (
    <div className="pg-fade mx-auto max-w-[1180px]">
      <PageHeader
        title="System agents"
        subtitle="Chat with the org-wide advisory agents — across runs, never a single run, never a verdict."
      />

      <div className="mt-4 grid gap-3 md:grid-cols-[280px_1fr]">
        {/* Left: agent picker + my chats */}
        <aside className="flex flex-col gap-3">
          <div className="rounded-[11px] border border-line bg-card p-2">
            <div className="px-1.5 pb-1.5 text-[10px] font-bold uppercase tracking-[0.3px] text-text-3">
              Agent
            </div>
            <div className="flex flex-col gap-1">
              {agents.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => { setSelected(a.id); setActive(null) }}
                  className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[12.5px] transition-colors ${
                    selected === a.id
                      ? 'bg-accent-weak text-accent-strong'
                      : 'text-text hover:bg-page'
                  }`}
                >
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-card-2 text-text-2">
                    {AGENT_ICON[a.id] ?? <Sparkles size={15} />}
                  </span>
                  <span className="min-w-0 flex-1 truncate font-semibold">{a.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-[11px] border border-line bg-card p-2">
            <div className="flex items-center justify-between px-1.5 pb-1.5">
              <span className="text-[10px] font-bold uppercase tracking-[0.3px] text-text-3">
                My chats
              </span>
              <button
                type="button"
                onClick={newChat}
                className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold text-accent-strong hover:bg-page"
              >
                <Plus size={13} /> New
              </button>
            </div>
            <div className="flex flex-col gap-1">
              {mine.length === 0 && (
                <p className="px-1.5 py-2 text-[11.5px] text-text-3">
                  No chats yet with {agentLabel(selected)}.
                </p>
              )}
              {mine.map((s) => (
                <div
                  key={s.session_id}
                  className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 ${
                    active?.session_id === s.session_id ? 'bg-page' : 'hover:bg-page'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => openSession(s.session_id)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <span className="block truncate text-[12px] text-text">{s.title || 'Untitled'}</span>
                    <span className="block truncate text-[10.5px] text-text-3">
                      {s.messages.length} msg · {s.status}
                    </span>
                  </button>
                  {s.status === 'archived' ? (
                    <button
                      type="button"
                      title="Restore"
                      onClick={() => restoreSession(s)}
                      className="shrink-0 rounded p-1 text-text-3 opacity-0 transition-opacity hover:text-text group-hover:opacity-100"
                    >
                      <RotateCcw size={13} />
                    </button>
                  ) : (
                    <button
                      type="button"
                      title="Archive"
                      onClick={() => archiveSession(s)}
                      className="shrink-0 rounded p-1 text-text-3 opacity-0 transition-opacity hover:text-text group-hover:opacity-100"
                    >
                      <Archive size={13} />
                    </button>
                  )}
                  <button
                    type="button"
                    title="Delete from my view"
                    onClick={() => deleteSession(s)}
                    className="shrink-0 rounded p-1 text-text-3 opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
            <label className="mt-1 flex items-center gap-1.5 px-1.5 pt-1.5 text-[11px] text-text-3">
              <input
                type="checkbox"
                checked={includeArchived}
                onChange={(e) => setIncludeArchived(e.target.checked)}
              />
              Show archived
            </label>
          </div>
        </aside>

        {/* Right: chat window */}
        <section className="flex min-h-[540px] flex-col rounded-[11px] border border-line bg-card">
          <div className="flex items-center gap-2 border-b border-line px-3.5 py-2.5">
            <span className="grid h-7 w-7 place-items-center rounded-md bg-accent-weak text-accent-strong">
              {AGENT_ICON[selected] ?? <Sparkles size={15} />}
            </span>
            <span className="text-[13px] font-semibold text-text">{agentLabel(selected)}</span>
            <span className="rounded bg-card-2 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.3px] text-text-3">
              advisory
            </span>
          </div>

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-3.5 py-3.5">
            {!active || active.messages.length === 0 ? (
              <div className="grid h-full place-items-center text-center">
                <p className="max-w-[420px] text-[12.5px] text-text-3">
                  Ask {agentLabel(selected)} a question. Answers are advisory and cited — they never
                  set a verdict. With AI off you get a grounded, retrieval-based reply.
                </p>
              </div>
            ) : (
              active.messages.map((m) => <Bubble key={m.id} m={m} />)
            )}
            {sending && (
              <p className="text-[11.5px] text-text-3">{agentLabel(selected)} is thinking…</p>
            )}
          </div>

          <div className="border-t border-line p-2.5">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void send()
                  }
                }}
                rows={2}
                placeholder={`Message ${agentLabel(selected)}…  (Enter to send, Shift+Enter for newline)`}
                className="flex-1 resize-none rounded-lg border border-line bg-page px-3 py-2 text-[12.5px] text-text outline-none placeholder:text-text-3 focus:border-line-strong"
              />
              <button
                type="button"
                onClick={() => void send()}
                disabled={sending || !input.trim()}
                className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent text-white transition-opacity disabled:opacity-40"
              >
                <Send size={15} />
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

// One chat turn. A user turn is right-aligned; an agent turn is left-aligned with its provenance
// (stub/claude + model) and deterministic citations rendered beneath (evidence separable from prose).
function Bubble({ m }: { m: ChatMessage }) {
  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-[11px] rounded-br-sm bg-accent-weak px-3 py-2 text-[12.5px] text-text">
          {m.content}
        </div>
      </div>
    )
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%]">
        <div className="whitespace-pre-wrap rounded-[11px] rounded-bl-sm border border-line bg-page px-3 py-2 text-[12.5px] text-text">
          {m.content}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 px-1 text-[10px] text-text-3">
          <span className="font-semibold uppercase tracking-[0.3px]">
            {m.generated_by === 'claude' ? `claude · ${m.model ?? ''}` : 'retrieval (AI off)'}
          </span>
          {m.citations.map((c) => (
            <span key={`${c.kind}:${c.ref}`} className="rounded bg-card-2 px-1.5 py-0.5">
              {c.title || c.ref}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
