import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { RunSummary } from '../types'
import { VERDICT_TEXT } from '../verdict'

const VERDICTS = ['proceed', 'hold', 'rerun', 'escalate'] as const

export function RunOverview() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .runs()
      .then(setRuns)
      .catch((e) => setError(String(e)))
  }, [])

  if (error) {
    return (
      <div className="text-escalate border border-escalate rounded-lg p-4 max-w-3xl">
        {error}. Is the API running?
      </div>
    )
  }
  if (!runs) return <p className="text-ink-dim">Loading runs…</p>
  if (runs.length === 0) return <p className="text-ink-dim">No runs found.</p>

  return (
    <div className="grid gap-4 max-w-3xl">
      {runs.map((run) => (
        <Link
          key={run.run_id}
          to={`/runs/${run.run_id}`}
          className="block bg-surface-2 border border-border rounded-xl p-5 transition-colors hover:border-ink-dim"
        >
          <div className="flex items-baseline justify-between">
            <h2 className="text-xl font-mono">{run.run_id}</h2>
            <span className="text-ink-dim text-sm">{run.n_samples} samples</span>
          </div>
          {run.n_attention > 0 && (
            <p className="text-hold text-sm mt-1">{run.n_attention} need attention</p>
          )}
          <div className="flex gap-6 mt-4">
            {VERDICTS.map((v) => (
              <div key={v} className="flex flex-col">
                <span className={`text-2xl font-semibold ${VERDICT_TEXT[v]}`}>
                  {run.counts[v] ?? 0}
                </span>
                <span className="text-ink-dim text-xs uppercase tracking-wide">{v}</span>
              </div>
            ))}
          </div>
        </Link>
      ))}
    </div>
  )
}
