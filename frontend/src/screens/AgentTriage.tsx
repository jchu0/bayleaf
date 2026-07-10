import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { api } from '../api'
import { Empty, ErrorBox, Loading } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { AgentComposer } from '../components/AgentComposer'
import { AgentSourceToggle } from '../components/AgentSourceToggle'
import { AgentSubjectCard } from '../components/AgentSubjectCard'
import { VERDICT_DOT } from '../verdict'
import type { RunDetail, TriageNote } from '../types'

const VERDICT_RANK: Record<string, number> = { escalate: 0, rerun: 1, hold: 2, proceed: 3 }

export function AgentTriage() {
  const { runId = '' } = useParams()
  const [params] = useSearchParams()
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [picked, setPicked] = useState<string | null>(null)
  const [note, setNote] = useState<TriageNote | null>(null)
  const [noteState, setNoteState] = useState<'idle' | 'loading' | 'ready' | 'none'>('idle')
  // Whether the operator wants live-model narration. Reflects/requests the *narration* source
  // only — the rule engine owns the verdict regardless of this toggle (INV-c).
  const [live, setLive] = useState(false)

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

  const sampleParam = picked ?? params.get('sample')
  const active = flagged.find((c) => c.sample_id === sampleParam) ?? flagged[0] ?? null

  // Fetch the advisory triage note for the active subject. Keyed on sample so switching the
  // picker re-asks. `live` is re-seeded from whether the note carried a model (armed agent).
  useEffect(() => {
    if (!active) {
      setNoteState('idle')
      setNote(null)
      return
    }
    let cancelled = false
    setNoteState('loading')
    setNote(null)
    api
      .triage(runId, active.sample_id)
      .then((n) => {
        if (cancelled) return
        setNote(n)
        setNoteState('ready')
        setLive(!!n.model)
      })
      .catch(() => {
        if (cancelled) return
        setNote(null)
        setNoteState('none')
        setLive(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, active?.sample_id])

  const hasLiveModel = noteState === 'ready' && !!note?.model
  // Operator asked for live but the triage agent isn't armed → honest rule-derived fallback.
  const errorFallback = noteState === 'ready' && live && !note?.model
  const offline = !hasLiveModel
  const sourceLabel = errorFallback
    ? 'Live synthesis unavailable — rule-derived fallback'
    : hasLiveModel && live
      ? `Claude · ${note?.model}`
      : 'Rule-derived triage (offline)'

  if (error) return <ErrorBox message={error} />
  if (!detail) return <Loading label="Loading triage…" />

  return (
    <div className="pg-fade mx-auto max-w-[800px]">
      <PageHeader
        eyebrow="Advisory"
        title="Agent triage"
        subtitle="AI-assisted triage to speed up diagnosis. The agent advises; the human decides."
        actions={
          active ? (
            <AgentSourceToggle live={live} label={sourceLabel} onToggle={() => setLive((v) => !v)} />
          ) : undefined
        }
      />

      {flagged.length === 0 ? (
        <Empty message="No flagged samples in this run — nothing to triage." />
      ) : (
        <>
          {/* error fallback — live synthesis unavailable; the deterministic verdict is unaffected */}
          {errorFallback && (
            <div className="mt-4 flex items-center gap-[11px] rounded-[11px] border border-hold-bd bg-hold-bg px-[15px] py-[12px]">
              <AlertTriangle size={18} strokeWidth={2} className="shrink-0 text-hold" />
              <div className="text-[12.5px] leading-[1.5] text-hold-fg">
                <strong className="font-semibold">Live model synthesis is unavailable.</strong> Showing rule-derived
                triage instead — the deterministic verdict and findings are unaffected.
              </div>
            </div>
          )}

          {/* Multi-sample picker — a real run has several flagged samples (not in the single-subject
              design); the design's per-subject header layout governs whichever is selected. */}
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
                  {/* Verdict signal so escalate reads apart from hold at a glance (rules decide the verdict). */}
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${VERDICT_DOT[c.verdict]}`} />
                  {c.sample_id}
                </button>
              ))}
            </div>
          )}

          {(noteState === 'loading' || noteState === 'idle') && (
            <div className="mt-4">
              <Loading label="Asking the triage agent…" />
            </div>
          )}
          {noteState === 'none' && (
            <div className="mt-4">
              <Empty message={`No triage note for ${active?.sample_id ?? 'this sample'}.`} />
            </div>
          )}
          {noteState === 'ready' && note && active && (
            <>
              <AgentSubjectCard key={`subject-${active.sample_id}`} runId={runId} card={active} note={note} sourceLabel={sourceLabel} />
              {/* Fresh conversation per subject — remount (distinct key) clears the thread. */}
              <AgentComposer key={`composer-${active.sample_id}`} offline={offline} />
            </>
          )}
        </>
      )}
    </div>
  )
}
