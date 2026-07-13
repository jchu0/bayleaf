import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Empty, ErrorBox, Loading } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { Pager } from '../components/Pager'
import { Truncate } from '../components/Truncate'
import { AgentComposer } from '../components/AgentComposer'
import { AgentSubjectCard } from '../components/AgentSubjectCard'
import { GATE_DOT, GATE_LABEL, VERDICT_DOT, VERDICT_LABEL, governingGate } from '../verdict'
import { useRun } from '../hooks/useRun'
import type { TriageNote } from '../types'

const VERDICT_RANK: Record<string, number> = { escalate: 0, rerun: 1, hold: 2, proceed: 3 }

export function AgentTriage() {
  const { runId = '' } = useParams()
  // Per-run triage only: this run's flagged samples. The org-wide system agents (pipeline-repair,
  // archivist) live on their own /system-agents screen, so this page is no longer a two-in-one.
  const [params] = useSearchParams()
  const { detail, error } = useRun(runId)
  const [picked, setPicked] = useState<string | null>(null)
  const [note, setNote] = useState<TriageNote | null>(null)
  const [noteState, setNoteState] = useState<'idle' | 'loading' | 'ready' | 'none'>('idle')
  const [page, setPage] = useState(1)

  // Reset the triage-specific UI when the run changes; detail/error now come from the shared useRun
  // cache (the legacy /agents deep-link has no runId → the empty "open a run" prompt renders).
  useEffect(() => {
    setPicked(null)
    setPage(1)
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

  // Cap the flagged table at 10 rows/page — a large mixed flowcell can flag dozens of samples, and
  // an unbounded table doesn't scale (scale-aware UI rule). Selection persists across pages.
  const PER = 10
  const pages = Math.max(1, Math.ceil(flagged.length / PER))
  const curPage = Math.min(page, pages)
  const pagedFlagged = flagged.slice((curPage - 1) * PER, curPage * PER)

  // Fetch the advisory triage note for the active subject. Keyed on sample so switching the
  // picker re-asks.
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
      })
      .catch(() => {
        if (cancelled) return
        setNote(null)
        setNoteState('none')
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, active?.sample_id])

  // Whether the SERVED note carried a model — the honest signal that the live triage agent is
  // armed (env: BAYLEAF_TRIAGE_AGENT=claude). It is not operator-toggleable (arming is env-side),
  // so it is reported as a status, never offered as a switch the UI can't action.
  const hasLiveModel = noteState === 'ready' && !!note?.model
  const offline = !hasLiveModel
  // A served note that carries a model IS model-generated narration — never relabel it
  // "rule-derived" (rules decide / AI advises: don't present model prose as deterministic output).
  const sourceLabel = hasLiveModel ? `Claude · ${note?.model}` : 'Rule-derived triage (offline)'

  return (
    <div className="pg-fade mx-auto max-w-[1080px]">
      <PageHeader
        title="Triage"
        subtitle="The agent advises; the human decides."
        actions={active ? <AgentStatus armed={hasLiveModel} label={sourceLabel} /> : undefined}
      />

      {/* Per-run triage section. It depends on a run in context; when there's no run (the legacy
          /agents deep-link) or the run fails to load we surface that here. */}
      {!runId ? (
        <Empty message="Open a run to triage its flagged samples." />
      ) : error ? (
        <ErrorBox message={error} />
      ) : !detail ? (
        <Loading label="Loading triage…" />
      ) : flagged.length === 0 ? (
        <Empty message="No flagged samples in this run — nothing to triage." />
      ) : (
        <>
          {/* Flagged-sample selector — a real run has several flagged samples (not in the single-
              subject design). A table (not pills) scales to a full run's worth of rows; the design's
              per-subject header layout governs whichever row is selected. Verdict-rank order (escalate
              first) is inherited from `flagged`. Rendered for any non-empty run, one row per sample. */}
          <div className="mt-4">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">
              Flagged samples · select a row to triage
            </div>
            <div className="overflow-hidden rounded-[10px] border border-line">
              <div className="grid grid-cols-[1.1fr_1fr_0.9fr_2fr_0.6fr] bg-card-2 text-[9.5px] font-semibold uppercase tracking-[0.4px] text-text-3">
                <div className="px-[13px] py-[9px]">Sample</div>
                <div className="px-[10px] py-[9px]">Verdict</div>
                <div className="px-[10px] py-[9px]">Gate</div>
                <div className="px-[10px] py-[9px]">Headline</div>
                <div className="px-[10px] py-[9px] text-center">Findings</div>
              </div>
              {pagedFlagged.map((c, i) => {
                const isActive = c.sample_id === active?.sample_id
                // The gate that drove this card's verdict (else the leading finding's gate) — the
                // same governing-gate derivation CardHead uses. Rules decide the verdict; this only
                // labels where it originated.
                const gate = governingGate(c)
                return (
                  <button
                    key={c.sample_id}
                    type="button"
                    onClick={() => setPicked(c.sample_id)}
                    aria-pressed={isActive}
                    className={`grid w-full grid-cols-[1.1fr_1fr_0.9fr_2fr_0.6fr] items-center border-t border-line text-left transition-colors ${
                      isActive ? 'bg-accent-weak' : i % 2 === 1 ? 'bg-card-2 hover:bg-accent-weak' : 'bg-card hover:bg-accent-weak'
                    }`}
                  >
                    <div
                      className={`px-[13px] py-[10px] font-mono text-[12.5px] font-semibold ${isActive ? 'text-accent' : 'text-text'}`}
                    >
                      {c.sample_id}
                    </div>
                    <div className="flex items-center gap-[6px] px-[10px] py-[10px]">
                      {/* Verdict signal so escalate reads apart from hold at a glance (rules decide the verdict). */}
                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${VERDICT_DOT[c.verdict]}`} />
                      <span className="text-[12px] text-text-2">{VERDICT_LABEL[c.verdict]}</span>
                    </div>
                    <div className="flex items-center gap-[6px] px-[10px] py-[10px] text-[12px] text-text-2">
                      {gate ? (
                        <>
                          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${GATE_DOT[gate]}`} />
                          {GATE_LABEL[gate]}
                        </>
                      ) : (
                        <span className="text-text-3">—</span>
                      )}
                    </div>
                    <Truncate text={c.headline} className="min-w-0 px-[10px] py-[10px] text-[12.5px] text-text" />
                    <div className="px-[10px] py-[10px] text-center font-mono text-[12px] font-semibold text-text-2">
                      {c.findings.length}
                    </div>
                  </button>
                )
              })}
            </div>
            {/* Canonical shared <Pager> (UIUX-03) — fixed 10/page, so the per-page control is hidden. */}
            {flagged.length > PER && (
              <Pager total={flagged.length} page={page} perPage="10" onPage={setPage} hidePerPage noun="flagged" />
            )}
          </div>

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
              <AgentComposer
                key={`composer-${active.sample_id}`}
                runId={runId}
                sampleId={active.sample_id}
                offline={offline}
              />
            </>
          )}
        </>
      )}
    </div>
  )
}

// The narration-source STATUS indicator (not a switch). Arming the live agent is env-side
// (BAYLEAF_TRIAGE_AGENT=claude), so the UI can only report whether the served note came from an
// armed model — never offer a toggle it can't action. A steady dot + the honest source label; when
// unarmed it reads "not armed" rather than pretending the operator can flip it on.
function AgentStatus({ armed, label }: { armed: boolean; label: string }) {
  return (
    <span
      title="Narration source — the live triage agent is armed env-side (BAYLEAF_TRIAGE_AGENT=claude). Advisory: never changes the verdict."
      className="inline-flex shrink-0 items-center gap-2 rounded-full border border-line-strong bg-card py-[5px] pl-3 pr-3.5 text-[11.5px] font-medium text-text-2"
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${armed ? 'bg-accent' : 'bg-card-3'}`} />
      {armed ? label : 'Live agent: not armed'}
    </span>
  )
}
