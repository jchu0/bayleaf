import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { BookOpen, FileText, Send, Sparkles } from 'lucide-react'
import { api } from '../api'
import { Empty, ErrorBox, Loading } from '../components/States'
import { VerdictBadge } from '../components/VerdictBadge'
import type { DecisionCard, RunDetail, TriageCitation, TriageNote } from '../types'

const VERDICT_RANK: Record<string, number> = { escalate: 0, rerun: 1, hold: 2, proceed: 3 }

export function AgentTriage() {
  const { runId = '' } = useParams()
  const [params] = useSearchParams()
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [picked, setPicked] = useState<string | null>(null)

  useEffect(() => {
    setDetail(null)
    setPicked(null)
    api.run(runId).then(setDetail).catch((e) => setError(String(e)))
  }, [runId])

  const flagged = useMemo(
    () =>
      (detail?.cards ?? [])
        .filter((c) => c.verdict !== 'proceed')
        .sort((a, b) => VERDICT_RANK[a.verdict] - VERDICT_RANK[b.verdict]),
    [detail],
  )

  if (error) return <ErrorBox message={error} />
  if (!detail) return <Loading label="Loading triage…" />

  const active = flagged.find((c) => c.sample_id === (picked ?? params.get('sample'))) ?? flagged[0] ?? null

  return (
    <div className="mx-auto max-w-[800px]">
      <h1 className="text-[22px] font-semibold tracking-tight text-text">Agent triage</h1>
      <p className="mt-1 text-[13px] text-text-2">
        AI-assisted triage to speed up diagnosis. The agent advises; the human decides.
      </p>

      {flagged.length === 0 ? (
        <div className="mt-5">
          <Empty message="No flagged samples in this run — nothing to triage." />
        </div>
      ) : (
        <>
          {flagged.length > 1 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {flagged.map((c) => (
                <button
                  key={c.sample_id}
                  onClick={() => setPicked(c.sample_id)}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-[12px] transition-colors ${
                    c.sample_id === active?.sample_id
                      ? 'border-accent bg-accent-weak text-accent'
                      : 'border-line bg-card text-text-2 hover:text-text'
                  }`}
                >
                  {c.sample_id}
                </button>
              ))}
            </div>
          )}
          {active && <TriageCard key={active.sample_id} runId={runId} card={active} />}
        </>
      )}
    </div>
  )
}

function TriageCard({ runId, card }: { runId: string; card: DecisionCard }) {
  const [note, setNote] = useState<TriageNote | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'none'>('loading')
  const [thread, setThread] = useState<{ role: 'user' | 'agent'; text: string }[]>([])
  const [draft, setDraft] = useState('')

  useEffect(() => {
    setState('loading')
    setNote(null)
    setThread([])
    api
      .triage(runId, card.sample_id)
      .then((n) => {
        setNote(n)
        setState('ready')
      })
      .catch(() => setState('none'))
  }, [runId, card.sample_id])

  const offline = !note?.model // stub agent has no model; a live run stamps one

  function ask(e: FormEvent) {
    e.preventDefault()
    const q = draft.trim()
    if (!q) return
    // The live agent is env-armed (PIPEGUARD_TRIAGE_AGENT=claude); offline we echo an honest
    // stub reply rather than fabricate an answer.
    setThread((t) => [
      ...t,
      { role: 'user', text: q },
      {
        role: 'agent',
        text: offline
          ? 'Offline (rule-derived stub) — see the suggested action above. Live agent Q&A is env-armed (set PIPEGUARD_TRIAGE_AGENT=claude).'
          : 'The live agent would answer here from the cited findings + knowledge corpus.',
      },
    ])
    setDraft('')
  }

  if (state === 'loading') return <div className="mt-4"><Loading label="Asking the triage agent…" /></div>
  if (state === 'none' || !note)
    return (
      <div className="mt-4">
        <Empty message={`No triage note for ${card.sample_id}.`} />
      </div>
    )

  const findings = note.citations.filter((c) => c.source_kind === 'finding')
  const knowledge = note.citations.filter((c) => c.source_kind === 'knowledge')

  return (
    <div className="mt-4 overflow-hidden rounded-xl border border-accent/25 bg-card shadow-card">
      <div className="border-b border-line bg-accent-weak/50 px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <Sparkles size={16} className="text-accent" />
          <span className="rounded border border-line bg-card px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-2">
            Advisory
          </span>
          <span className="rounded border border-line bg-card px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-text-3">
            {offline ? 'Rule-derived triage (offline)' : `live · ${note.model}`}
          </span>
          <span className="ml-auto flex items-center gap-2">
            <VerdictBadge verdict={card.verdict} />
            <span className="font-mono text-[11px] text-text-3">
              {runId} · {card.sample_id}
            </span>
          </span>
        </div>
        <h3 className="mt-2 text-[15px] font-semibold text-text">{card.headline}</h3>
      </div>

      <div className="space-y-4 px-5 py-4">
        <Block label="Likely cause">{note.likely_cause}</Block>
        <Block label="Suggested action">{note.suggested_action}</Block>

        <div>
          <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-3">Citations</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <CiteColumn
              icon={<FileText size={12} />}
              title="From this run's findings"
              cites={findings}
              runId={runId}
            />
            <CiteColumn icon={<BookOpen size={12} />} title="Knowledge & experience" cites={knowledge} runId={runId} />
          </div>
        </div>
      </div>

      {/* Ask the agent */}
      <div className="border-t border-line px-5 py-4">
        {thread.length > 0 && (
          <div className="mb-3 space-y-2">
            {thread.map((m, i) => (
              <div
                key={i}
                className={`max-w-[85%] rounded-lg px-3 py-2 text-[12.5px] ${
                  m.role === 'user'
                    ? 'ml-auto bg-accent text-white'
                    : 'bg-card-2 text-text-2'
                }`}
              >
                {m.text}
              </div>
            ))}
          </div>
        )}
        <form onSubmit={ask} className="flex items-center gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask the agent about this sample…"
            className="min-w-0 flex-1 rounded-lg border border-line bg-page px-3 py-2 text-[13px] text-text placeholder:text-text-3 focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-90"
          >
            <Send size={14} />
            Ask
          </button>
        </form>
      </div>
    </div>
  )
}

function Block({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-3">{label}</p>
      <p className="text-[13px] leading-relaxed text-text">{children}</p>
    </div>
  )
}

function CiteColumn({
  icon,
  title,
  cites,
  runId,
}: {
  icon: ReactNode
  title: string
  cites: TriageCitation[]
  runId: string
}) {
  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-[11px] font-medium text-text-2">
        {icon}
        {title}
      </p>
      {cites.length === 0 ? (
        <p className="text-[12px] text-text-3">—</p>
      ) : (
        <div className="space-y-1.5">
          {cites.map((c) => {
            const body = (
              <div className="rounded-lg border border-line bg-card-2/40 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-[11.5px] text-text">{c.ref}</span>
                  {c.score != null && (
                    <span className="shrink-0 font-mono text-[10px] text-text-3">{c.score.toFixed(2)}</span>
                  )}
                </div>
                {c.title && <p className="mt-0.5 text-[12px] text-text-2">{c.title}</p>}
              </div>
            )
            return c.source_kind === 'finding' ? (
              <Link key={c.ref} to={`/runs/${runId}`} className="block hover:opacity-80">
                {body}
              </Link>
            ) : (
              <div key={c.ref}>{body}</div>
            )
          })}
        </div>
      )}
    </div>
  )
}
