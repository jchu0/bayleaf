import { useEffect, useState } from 'react'

type RunSummary = {
  run_id: string
  n_samples: number
  n_attention: number
  counts: Record<string, number>
}

const VERDICTS = ['proceed', 'hold', 'rerun', 'escalate'] as const

// Static classes so Tailwind's compiler can see them (no dynamic `text-${v}`).
const VERDICT_COLOR: Record<string, string> = {
  proceed: 'text-proceed',
  hold: 'text-hold',
  rerun: 'text-rerun',
  escalate: 'text-escalate',
}

export default function App() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/runs')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setRuns)
      .catch((e) => setError(String(e)))
  }, [])

  return (
    <div className="min-h-screen bg-surface text-ink p-8">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold flex items-center gap-2">
          <span>🧬</span> PipeGuard
        </h1>
        <p className="text-ink-dim mt-1">
          AI-assisted provenance &amp; QC decision gate — run overview
        </p>
      </header>

      {error && (
        <div className="text-escalate border border-escalate rounded-lg p-4 max-w-3xl">
          Failed to load runs: {error}. Is the API running on :8000?
        </div>
      )}
      {!runs && !error && <p className="text-ink-dim">Loading runs…</p>}
      {runs && runs.length === 0 && <p className="text-ink-dim">No runs found.</p>}

      <div className="grid gap-4 max-w-3xl">
        {runs?.map((run) => (
          <article
            key={run.run_id}
            className="bg-surface-2 border border-border rounded-xl p-5"
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
                  <span className={`text-2xl font-semibold ${VERDICT_COLOR[v]}`}>
                    {run.counts[v] ?? 0}
                  </span>
                  <span className="text-ink-dim text-xs uppercase tracking-wide">{v}</span>
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
