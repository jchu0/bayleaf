import { ChevronRight, Wrench } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Empty, ErrorBox, Loading } from '../components/States'
import type { Gate, RunDetail, RunSummary } from '../types'
import { GATE_DOT, GATE_LABEL, VERDICT_BAR, VERDICT_LABEL } from '../verdict'

const VERDICTS = ['proceed', 'hold', 'rerun', 'escalate'] as const
const GATES = ['preflight', 'qc', 'variant'] as const
// Top-N recurring signatures shown before the "Show all" toggle.
const SIG_CAP = 8
// A signature seen this many times or more gets a "Repair agent" escalation CTA.
const REPAIR_MIN = 3

export function Monitoring() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [details, setDetails] = useState<RunDetail[]>([])
  const [error, setError] = useState<string | null>(null)
  const [showAllSigs, setShowAllSigs] = useState(false)

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
  if (!runs) return <Loading label="Loading monitoring…" />
  if (runs.length === 0) return <Empty message="No runs to monitor yet." />

  const totalSamples = runs.reduce((a, r) => a + r.n_samples, 0)
  const totalAttention = runs.reduce((a, r) => a + r.n_attention, 0)
  const proceed = runs.reduce((a, r) => a + (r.counts.proceed ?? 0), 0)
  const maxSamples = Math.max(...runs.map((r) => r.n_samples), 1)

  const gateFlagged: Record<Gate, number> = { preflight: 0, qc: 0, variant: 0 }
  const sigMap = new Map<string, { rule: string; title: string; gate: Gate; count: number }>()
  let cardCount = 0
  for (const d of details) {
    for (const c of d.cards) {
      cardCount += 1
      const flagged = new Set(c.gate_results.map((g) => g.gate))
      for (const g of GATES) if (flagged.has(g)) gateFlagged[g] += 1
      for (const f of c.findings) {
        const cur = sigMap.get(f.signature) ?? { rule: f.rule_id, title: f.title, gate: f.gate, count: 0 }
        cur.count += 1
        sigMap.set(f.signature, cur)
      }
    }
  }
  const signatures = [...sigMap.values()].sort((a, b) => b.count - a.count)
  const visibleSigs = showAllSigs ? signatures : signatures.slice(0, SIG_CAP)

  const kpis = [
    { label: 'Runs', value: String(runs.length) },
    { label: 'Samples', value: String(totalSamples) },
    { label: 'Auto-proceed', value: totalSamples ? `${Math.round((proceed / totalSamples) * 100)}%` : '—' },
    { label: 'Need review', value: String(totalAttention) },
  ]

  return (
    <div className="mx-auto max-w-[1040px]">
      <h1 className="text-[22px] font-semibold tracking-tight text-text">Monitoring</h1>
      <p className="mt-1 text-[13px] text-text-2">
        Run throughput + verdict distribution. System telemetry (Prometheus <code>/metrics</code>) ships with the
        backend.
      </p>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {kpis.map((k) => (
          <div key={k.label} className="rounded-xl border border-line bg-card px-4 py-3 shadow-card">
            <div className="font-mono text-[26px] font-semibold text-text">{k.value}</div>
            <div className="mt-0.5 text-[12px] text-text-2">{k.label}</div>
          </div>
        ))}
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <div className="rounded-xl border border-line bg-card p-4 shadow-card lg:col-span-2">
          <p className="mb-3 text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-3">Verdicts over time</p>
          <div className="flex items-end gap-3">
            {runs.map((r) => {
              const barH = (r.n_samples / maxSamples) * 150
              return (
                <Link
                  key={r.run_id}
                  to={`/runs/${r.run_id}`}
                  title={`Open ${r.run_id} decision cards`}
                  className="group flex flex-1 flex-col items-center"
                >
                  <div
                    className="flex w-full max-w-12 flex-col-reverse overflow-hidden rounded-t opacity-90 transition group-hover:opacity-100 group-hover:ring-2 group-hover:ring-accent-weak"
                    style={{ height: barH }}
                  >
                    {VERDICTS.map((v) => {
                      const n = r.counts[v] ?? 0
                      return n ? (
                        <div
                          key={v}
                          className={VERDICT_BAR[v]}
                          style={{ height: (n / r.n_samples) * barH }}
                          title={`${VERDICT_LABEL[v]}: ${n}`}
                        />
                      ) : null
                    })}
                  </div>
                  <span className="mt-1.5 w-full truncate text-center font-mono text-[9px] text-text-3 group-hover:text-text-2">
                    {r.run_id}
                  </span>
                </Link>
              )
            })}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-text-2">
            {VERDICTS.map((v) => (
              <span key={v} className="flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-sm ${VERDICT_BAR[v]}`} />
                {VERDICT_LABEL[v]}
              </span>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-line bg-card p-4 shadow-card">
          <p className="mb-3 text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-3">Gate pass rate</p>
          <div className="space-y-3">
            {GATES.map((g) => {
              const passPct = cardCount ? Math.round(((cardCount - gateFlagged[g]) / cardCount) * 100) : 100
              return (
                <div key={g}>
                  <div className="mb-1 flex items-center justify-between text-[12px]">
                    <span className="flex items-center gap-1.5 text-text-2">
                      <span className={`h-1.5 w-1.5 rounded-full ${GATE_DOT[g]}`} />
                      {GATE_LABEL[g]} gate
                    </span>
                    <span className="font-mono text-text">{passPct}%</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-card-3">
                    <div className="h-full bg-proceed" style={{ width: `${passPct}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {signatures.length > 0 && (
        <div className="mt-4 rounded-xl border border-line bg-card p-4 shadow-card">
          <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-3">
            Recurring issue signatures{' '}
            <span className="font-normal normal-case tracking-normal text-text-3">· all-time</span>
          </p>
          {/* Honest labeling: counts are lifetime totals across every loaded run, not a rolling
              window — 7d/14d/30d trends land once the backend serves windowed time-series. */}
          <p className="mb-3 text-[11px] text-text-3">Lifetime counts across all runs · not yet windowed.</p>
          <div className="space-y-1.5">
            {visibleSigs.map((s) => {
              const recurring = s.count >= REPAIR_MIN
              return (
                <Link
                  key={s.rule + s.title}
                  to="/queue"
                  title="Open review queue"
                  className="flex items-center gap-3 rounded-lg border border-line px-3 py-2 transition hover:border-line-strong"
                >
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${GATE_DOT[s.gate]}`} />
                  <span className="shrink-0 font-mono text-[11px] text-text-2">{s.rule}</span>
                  <span className="min-w-0 flex-1 truncate text-[12.5px] text-text">{s.title}</span>
                  {recurring && (
                    <span className="flex shrink-0 items-center gap-1 rounded-md border border-accent bg-accent-weak px-2 py-0.5 text-[11px] font-medium text-accent-strong">
                      <Wrench size={11} /> Repair agent
                    </span>
                  )}
                  <span className="shrink-0 rounded border border-line bg-card-2 px-1.5 py-0.5 font-mono text-[10.5px] text-text-2">
                    ×{s.count}
                  </span>
                  <ChevronRight size={15} className="shrink-0 text-text-3" />
                </Link>
              )
            })}
          </div>
          {signatures.length > SIG_CAP && (
            <button
              onClick={() => setShowAllSigs((v) => !v)}
              className="mt-2.5 text-[12px] font-medium text-accent hover:underline"
            >
              {showAllSigs ? `Show top ${SIG_CAP}` : `Show all (${signatures.length})`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
