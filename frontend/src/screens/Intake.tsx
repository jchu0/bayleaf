import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { EvidenceTable } from '../components/EvidenceTable'
import { GateResultStrip } from '../components/GateResultStrip'
import { Empty, ErrorBox, Loading } from '../components/States'
import { VerdictBadge } from '../components/VerdictBadge'
import type { DecisionCard, GateResult, RunDetail, Verdict } from '../types'

// Preflight verdicts ranked most-urgent first (matches the gate's ordering).
const VERDICT_ORDER: Record<Verdict, number> = { escalate: 0, rerun: 1, hold: 2, proceed: 3 }

// A sample flagged at the preflight/intake gate, carried with its run + gate rollup.
type IntakeItem = { runId: string; card: DecisionCard; preflightGate: GateResult }

// The samples that cleared intake, grouped by run for a compact "receded" summary.
type ClearedGroup = { runId: string; sampleIds: string[] }

// The intake screen reads the SAME per-sample DecisionCards as every other screen and
// projects them onto the first gate (preflight): a card is flagged at intake iff its
// gate_results carries a preflight rollup — which, by construction, only appears when
// that gate did not `proceed`. So this view invents no verdict; the rules already decided.
export function Intake() {
  const [runs, setRuns] = useState<RunDetail[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .runs()
      .then((summaries) => Promise.all(summaries.map((r) => api.run(r.run_id))))
      .then(setRuns)
      .catch((e) => setError(String(e)))
  }, [])

  if (error) return <ErrorBox message={error} />
  if (!runs) return <Loading label="Loading intake…" />
  if (runs.length === 0) return <Empty message="No runs found." />

  const flagged: IntakeItem[] = []
  const cleared: ClearedGroup[] = []
  let totalSamples = 0
  for (const detail of runs) {
    const clearedIds: string[] = []
    for (const card of detail.cards) {
      totalSamples += 1
      const preflightGate = card.gate_results.find((g) => g.gate === 'preflight')
      if (preflightGate) flagged.push({ runId: detail.run_id, card, preflightGate })
      else clearedIds.push(card.sample_id)
    }
    if (clearedIds.length > 0) cleared.push({ runId: detail.run_id, sampleIds: clearedIds })
  }
  flagged.sort((a, b) => VERDICT_ORDER[a.preflightGate.verdict] - VERDICT_ORDER[b.preflightGate.verdict])
  const clearedCount = totalSamples - flagged.length

  return (
    <div className="max-w-4xl">
      <Link to="/" className="text-ink-dim text-sm hover:text-ink">
        ← All runs
      </Link>
      <h2 className="mt-2 text-2xl font-semibold">Intake / preflight</h2>
      <p className="text-ink-dim text-sm mb-6">
        The first gate, before QC — barcode/index integrity, sample identity, required
        intake metadata, and pipeline failures. Across all runs; the samples needing a
        human surface first. Thresholds are illustrative, not clinical.
      </p>

      <div className="mb-6 grid grid-cols-3 gap-4">
        <div className="rounded-xl border border-border bg-surface-2 p-4">
          <div className="text-2xl font-semibold text-proceed">{clearedCount}</div>
          <div className="text-ink-dim text-xs uppercase tracking-wide">cleared intake</div>
        </div>
        <div className="rounded-xl border border-border bg-surface-2 p-4">
          <div className={`text-2xl font-semibold ${flagged.length ? 'text-hold' : 'text-proceed'}`}>
            {flagged.length}
          </div>
          <div className="text-ink-dim text-xs uppercase tracking-wide">need a human</div>
        </div>
        <div className="rounded-xl border border-border bg-surface-2 p-4">
          <div className="text-2xl font-semibold">{runs.length}</div>
          <div className="text-ink-dim text-xs uppercase tracking-wide">
            run{runs.length === 1 ? '' : 's'}
          </div>
        </div>
      </div>

      {flagged.length === 0 ? (
        <p className="text-proceed">
          Every sample cleared intake — no barcode swaps, absent-from-sheet samples, missing
          metadata, or pipeline failures across all runs.
        </p>
      ) : (
        <div className="grid gap-4">
          {flagged.map((item) => (
            <IntakeCard key={`${item.runId}-${item.card.sample_id}`} {...item} />
          ))}
        </div>
      )}

      {cleared.length > 0 && (
        <div className="mt-8">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-dim">
            Cleared intake
          </h3>
          <div className="grid gap-2">
            {cleared.map(({ runId, sampleIds }) => (
              <div key={runId} className="flex items-start gap-3">
                <Link
                  to={`/runs/${runId}`}
                  className="w-44 shrink-0 truncate font-mono text-xs text-ink-dim hover:text-ink"
                >
                  {runId}
                </Link>
                <div className="flex flex-wrap gap-1.5">
                  {sampleIds.map((id) => (
                    <span
                      key={id}
                      className="rounded border border-border bg-surface px-2 py-0.5 font-mono text-xs text-ink-dim"
                    >
                      {id}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function IntakeCard({ runId, card, preflightGate }: IntakeItem) {
  // Only the preflight-gate findings — the cited evidence for the intake issue (QC and
  // variant findings, if any, live on the full decision card in the run view).
  const preflightFindings = card.findings.filter((f) => f.gate === 'preflight')
  const headline = preflightFindings.map((f) => f.title).join(' · ') || preflightGate.rationale
  return (
    <article className="bg-surface-2 border border-border rounded-xl p-5">
      <div className="flex items-center gap-3">
        <span className="font-mono text-lg">{card.sample_id}</span>
        <VerdictBadge verdict={preflightGate.verdict} />
        <Link
          to={`/runs/${runId}`}
          className="ml-auto shrink-0 font-mono text-xs text-ink-dim hover:text-ink"
        >
          {runId} →
        </Link>
      </div>
      <p className="mt-2 font-semibold">{headline}</p>

      <div className="mt-4">
        <GateResultStrip results={[preflightGate]} />
      </div>

      <div className="mt-4">
        <EvidenceTable findings={preflightFindings} />
      </div>
    </article>
  )
}
