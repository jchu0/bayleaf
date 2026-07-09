import { AlertTriangle, ChevronRight } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Empty, ErrorBox, Loading } from '../components/States'
import type { RunSummary } from '../types'
import { VERDICT_BAR } from '../verdict'

const VERDICTS = ['proceed', 'hold', 'rerun', 'escalate'] as const
type Filter = 'all' | 'attention' | 'released'

function SegmentedBar({ counts, total }: { counts: RunSummary['counts']; total: number }) {
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-card-3">
      {VERDICTS.map((v) => {
        const n = counts[v] ?? 0
        return n ? (
          <div key={v} className={VERDICT_BAR[v]} style={{ width: `${(n / total) * 100}%` }} />
        ) : null
      })}
    </div>
  )
}

export function RunOverview() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')

  useEffect(() => {
    api
      .runs()
      .then(setRuns)
      .catch((e) => setError(String(e)))
  }, [])

  const filtered = useMemo(() => {
    if (!runs) return []
    if (filter === 'attention') return runs.filter((r) => r.n_attention > 0)
    if (filter === 'released') return runs.filter((r) => r.n_attention === 0)
    return runs
  }, [runs, filter])

  if (error) return <ErrorBox message={`${error}. Is the API running?`} />
  if (!runs) return <Loading label="Loading runs…" />

  const nAttention = runs.filter((r) => r.n_attention > 0).length
  const pills: { key: Filter; label: string; count: number }[] = [
    { key: 'all', label: 'All runs', count: runs.length },
    { key: 'attention', label: 'Needs attention', count: nAttention },
    { key: 'released', label: 'Released', count: runs.length - nAttention },
  ]

  return (
    <div className="mx-auto max-w-[1080px]">
      <h1 className="text-[22px] font-semibold tracking-tight text-text">Sequencing runs</h1>
      <p className="mt-1 flex items-center gap-2 text-[13px] text-text-2">
        Provenance &amp; QC decision gate. Each run resolves to a per-sample verdict —{' '}
        <span className="font-medium text-text">proceed, hold, rerun, or escalate</span>.
        <span className="ml-auto flex items-center gap-1.5 text-text-2">
          <span className="h-2 w-2 rounded-full bg-proceed" /> Gate online
        </span>
      </p>

      <div className="mt-5 flex items-center gap-2">
        {pills.map((p) => (
          <button
            key={p.key}
            onClick={() => setFilter(p.key)}
            className={`flex items-center gap-1.5 rounded-[20px] border px-3 py-1 text-[13px] transition-colors ${
              filter === p.key
                ? 'border-line-strong bg-card-2 font-medium text-text'
                : 'border-line bg-card text-text-2 hover:border-line-strong'
            }`}
          >
            {p.label} <span className="text-text-3">{p.count}</span>
          </button>
        ))}
      </div>

      <div className="mt-4 space-y-2.5">
        {filtered.length === 0 && <Empty message="No runs match this filter." />}
        {filtered.map((run) => {
          const total = VERDICTS.reduce((s, v) => s + (run.counts[v] ?? 0), 0) || 1
          const needs = run.n_attention > 0
          return (
            <Link
              key={run.run_id}
              to={`/runs/${run.run_id}`}
              className="flex items-center gap-5 rounded-xl border border-line bg-card px-5 py-4 shadow-card transition hover:border-line-strong"
            >
              <div className="w-52 shrink-0">
                <div className="font-mono text-[13.5px] font-semibold text-text">{run.run_id}</div>
                <div className="mt-1 flex items-center gap-1.5 text-[12px] text-text-2">
                  <span className={`h-1.5 w-1.5 rounded-full ${needs ? 'bg-hold' : 'bg-proceed'}`} />
                  {needs ? 'Needs review' : 'Released'}
                </div>
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-2 text-[12px] text-text-2">{run.n_samples} samples</div>
                <SegmentedBar counts={run.counts} total={total} />
              </div>
              {needs && (
                <span className="flex shrink-0 items-center gap-1.5 rounded-lg border border-hold-bd bg-hold-bg px-2.5 py-1 text-[12px] font-medium text-hold-fg">
                  <AlertTriangle size={13} /> {run.n_attention} need attention
                </span>
              )}
              <ChevronRight size={17} className="shrink-0 text-text-3" />
            </Link>
          )
        })}
      </div>
    </div>
  )
}
