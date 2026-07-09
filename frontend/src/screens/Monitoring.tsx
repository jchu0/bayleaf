import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Empty, ErrorBox, Loading } from '../components/States'
import type { RunDetail, RunSummary } from '../types'
import { GATE_LABEL, VERDICT_BAR, VERDICT_LABEL, VERDICT_TEXT } from '../verdict'

const VERDICTS = ['proceed', 'hold', 'rerun', 'escalate'] as const
const GATES = ['preflight', 'qc', 'variant'] as const

function pct(n: number, d: number): string {
  return d ? `${Math.round((n / d) * 100)}%` : '0%'
}

export function Monitoring() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [details, setDetails] = useState<RunDetail[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .runs()
      .then((rs) => {
        setRuns(rs)
        return Promise.all(rs.map((r) => api.run(r.run_id)))
      })
      .then(setDetails)
      .catch((e) => setError(String(e)))
  }, [])

  if (error) return <ErrorBox message={error} />
  if (!runs) return <Loading />
  if (runs.length === 0) return <Empty message="No runs to monitor yet." />

  const totalSamples = runs.reduce((a, r) => a + r.n_samples, 0)
  const totalAttention = runs.reduce((a, r) => a + r.n_attention, 0)

  const verdictTotals: Record<string, number> = {}
  for (const v of VERDICTS) {
    verdictTotals[v] = runs.reduce((a, r) => a + (r.counts[v] ?? 0), 0)
  }

  const gateFlagged: Record<string, number> = { preflight: 0, qc: 0, variant: 0 }
  let cardCount = 0
  for (const d of details) {
    for (const c of d.cards) {
      cardCount += 1
      const flagged = new Set(c.gate_results.map((g) => g.gate))
      for (const g of GATES) {
        if (flagged.has(g)) gateFlagged[g] += 1
      }
    }
  }

  return (
    <div className="max-w-3xl">
      <Link to="/" className="text-ink-dim text-sm hover:text-ink">
        ← All runs
      </Link>
      <h2 className="mt-2 text-2xl font-semibold">Monitoring</h2>
      <p className="text-ink-dim text-sm mb-6">
        Across {runs.length} run{runs.length === 1 ? '' : 's'} · {totalSamples} samples.
      </p>

      <div className="mb-6 grid grid-cols-4 gap-4">
        {VERDICTS.map((v) => (
          <div key={v} className="rounded-xl border border-border bg-surface-2 p-4">
            <div className={`text-2xl font-semibold ${VERDICT_TEXT[v]}`}>{verdictTotals[v] ?? 0}</div>
            <div className="text-ink-dim text-xs uppercase tracking-wide">{v}</div>
          </div>
        ))}
      </div>

      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-dim">
        Verdict distribution
      </h3>
      <div className="mb-2 flex h-3 w-full overflow-hidden rounded bg-surface-2">
        {VERDICTS.map((v) => {
          const n = verdictTotals[v] ?? 0
          if (n === 0) return null
          return (
            <div
              key={v}
              className={VERDICT_BAR[v]}
              style={{ width: pct(n, totalSamples) }}
              title={`${VERDICT_LABEL[v]}: ${n} (${pct(n, totalSamples)})`}
            />
          )
        })}
      </div>
      <div className="mb-6 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-dim">
        {VERDICTS.map((v) => (
          <span key={v} className="flex items-center gap-1.5">
            <span className={`inline-block h-2 w-2 rounded-sm ${VERDICT_BAR[v]}`} />
            {VERDICT_LABEL[v]}
            <span className="font-mono">
              {verdictTotals[v] ?? 0} · {pct(verdictTotals[v] ?? 0, totalSamples)}
            </span>
          </span>
        ))}
      </div>

      <p className="mb-6 text-sm">
        <span className="font-semibold text-hold">{totalAttention}</span>
        <span className="text-ink-dim">
          {' '}
          of {totalSamples} samples need attention ({pct(totalAttention, totalSamples)})
        </span>
      </p>

      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-dim">
        Gate flag rate
      </h3>
      <div className="grid gap-2">
        {GATES.map((g) => (
          <div key={g} className="flex items-center gap-3">
            <span className="w-20 text-sm">{GATE_LABEL[g]}</span>
            <div className="h-2 flex-1 overflow-hidden rounded bg-surface-2">
              <div className="h-full bg-hold" style={{ width: pct(gateFlagged[g], cardCount) }} />
            </div>
            <span className="w-36 text-right text-xs text-ink-dim">
              <span className="font-mono">{pct(gateFlagged[g], cardCount)}</span> ·{' '}
              {gateFlagged[g]}/{cardCount} flagged
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
