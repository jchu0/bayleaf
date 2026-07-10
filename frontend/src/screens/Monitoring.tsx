import { RotateCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { MonitoringSignatureRow } from '../components/MonitoringSignatureRow'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl, type SegmentOption } from '../components/SegmentedControl'
import { Empty, ErrorBox, Loading } from '../components/States'
import { useRefresh } from '../hooks/useRefresh'
import type { Gate, MonitoringMetrics, MonitoringWindow, Verdict } from '../types'
import { GATE_DOT, VERDICT_BAR, VERDICT_LABEL } from '../verdict'

// The window control offers the three dated windows README §5.8 mandates; the backend applies one
// window to the whole payload, so it governs the KPIs, throughput, gate-pass, and signatures
// uniformly. ('all' is a valid MonitoringWindow but intentionally not offered here.)
const WINDOW_OPTIONS: SegmentOption<MonitoringWindow>[] = [
  { value: '7d', label: '7d' },
  { value: '14d', label: '14d' },
  { value: '30d', label: '30d' },
]
const WINDOW_LABEL: Record<string, string> = { '7d': '7 days', '14d': '14 days', '30d': '30 days', all: 'all time' }

// Stacked-bar order, top→bottom (escalate on top, proceed at the baseline).
const STACK_ORDER: Verdict[] = ['escalate', 'rerun', 'hold', 'proceed']
// Legend order per the design.
const LEGEND_ORDER: Verdict[] = ['proceed', 'hold', 'rerun', 'escalate']
// Gate-pass row labels — the design labels only QC/Variant with "gate".
const GATE_PASS_LABEL: Record<Gate, string> = { preflight: 'Preflight', qc: 'QC gate', variant: 'Variant gate' }

// Short throughput-bar date derived from the run's [Header] date (YYYY-MM-DD → MM-DD). We never
// fabricate a date: an undated run (shouldn't appear in a dated window) falls back to its run id.
function shortDate(runDate: string | null, runId: string): string {
  if (runDate && runDate.length >= 10) return runDate.slice(5, 10)
  return runId.length > 6 ? runId.slice(-6) : runId
}

export function Monitoring() {
  const [window, setWindow] = useState<MonitoringWindow>('7d')
  const [data, setData] = useState<MonitoringMetrics | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [openSigs, setOpenSigs] = useState<Set<string>>(new Set())

  // Single pre-aggregated call (drops the old N+1 runs.map(api.run) reassembly, F21). A request
  // id guards against out-of-order responses on a window switch — only the latest may commit.
  const reqId = useRef(0)
  const load = useCallback(async () => {
    const id = ++reqId.current
    setError(null)
    const d = await api.monitoring(window)
    if (id === reqId.current) setData(d)
  }, [window])
  const { spinning, updatedLabel, refresh } = useRefresh(load)

  useEffect(() => {
    refresh().catch((e) => setError(String(e)))
  }, [refresh])

  const windowShort = window
  const windowLabel = WINDOW_LABEL[window] ?? 'window'

  const filteredSigs = useMemo(() => {
    if (!data) return []
    const q = query.trim().toLowerCase()
    if (!q) return data.signatures
    return data.signatures.filter((s) =>
      `${s.rule_id} ${s.title} ${s.signature}`.toLowerCase().includes(q),
    )
  }, [data, query])

  const control = (
    <div className="flex items-center gap-2">
      <SegmentedControl options={WINDOW_OPTIONS} value={window} onChange={setWindow} />
      <button
        type="button"
        onClick={() => refresh().catch((e) => setError(String(e)))}
        className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] text-text-2 transition-colors hover:border-line-strong"
        title="Refresh telemetry"
      >
        <RotateCw size={13} className={spinning ? 'animate-spin' : ''} />
        {updatedLabel ? `Updated ${updatedLabel}` : 'Refresh'}
      </button>
    </div>
  )

  const header = (
    <PageHeader
      eyebrow="Fleet health"
      title="Monitoring"
      subtitle="Run throughput and verdict trends across recent runs. System telemetry (Prometheus) lands with the backend."
      actions={control}
    />
  )

  if (error) return <div className="mx-auto max-w-[1040px]">{header}<ErrorBox message={error} onRetry={() => refresh().catch((e) => setError(String(e)))} /></div>
  if (!data) return <div className="mx-auto max-w-[1040px]">{header}<Loading label="Loading monitoring…" /></div>

  const o = data.overall
  const maxSamples = Math.max(...data.runs.map((r) => r.n_samples), 1)

  const kpis: { label: string; value: string; hint?: string }[] = [
    { label: `Runs · ${windowShort}`, value: String(o.n_runs) },
    { label: `Samples · ${windowShort}`, value: String(o.n_samples) },
    {
      label: 'Auto-proceed',
      value: o.auto_proceed_pct != null ? `${Math.round(o.auto_proceed_pct)}%` : '—',
      // Honest labelling (guardrail 2): a throughput ratio, NOT a calibrated confidence.
      hint: 'Throughput heuristic — share of samples the gate auto-cleared to Proceed. Not a calibrated confidence.',
    },
    // Honest placeholder (F3): no review-latency telemetry field exists on the backend yet.
    { label: 'Median review', value: '—', hint: 'Review-latency telemetry not yet captured by the backend.' },
  ]

  return (
    <div className="mx-auto max-w-[1040px]">
      {header}

      {/* KPI row — border-only tiles (no shadow), value mono 24px */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {kpis.map((k) => (
          <div key={k.label} className="rounded-xl border border-line bg-card px-4 py-[14px]" title={k.hint}>
            <div className="font-mono text-[24px] font-semibold leading-none text-text">{k.value}</div>
            <div className="mt-1.5 text-[11.5px] text-text-2">{k.label}</div>
          </div>
        ))}
      </div>

      {/* Two-column band: verdicts-over-time (1.5fr) + gate pass rate (1fr) */}
      <div className="mt-[14px] grid gap-[14px] lg:grid-cols-[1.5fr_1fr]">
        <div className="rounded-[14px] border border-line bg-card px-[18px] py-4">
          <div className="text-[13.5px] font-semibold text-text">Verdicts over time</div>
          {data.runs.length === 0 ? (
            <p className="mt-4 text-[12.5px] text-text-3">No dated runs in this window.</p>
          ) : (
            <div className="mt-4 flex h-[168px] items-end gap-[10px]">
              {data.runs.map((r) => (
                <div
                  key={r.run_id}
                  className="flex h-full min-w-0 flex-1 flex-col items-center gap-[7px]"
                  title={`${r.run_id} · ${r.n_samples} samples`}
                >
                  <div className="flex w-[26px] flex-1 flex-col justify-end gap-[2px]">
                    {STACK_ORDER.map((v) => {
                      const n = r.counts[v] ?? 0
                      return n ? (
                        <div
                          key={v}
                          className={`w-full rounded-[2px] ${VERDICT_BAR[v]}`}
                          style={{ height: `${(n / maxSamples) * 100}%` }}
                          title={`${VERDICT_LABEL[v]}: ${n}`}
                        />
                      ) : null
                    })}
                  </div>
                  <div className="whitespace-nowrap font-mono text-[9px] text-text-3">
                    {shortDate(r.run_date, r.run_id)}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="mt-[14px] flex flex-wrap gap-[14px] border-t border-line pt-3">
            {LEGEND_ORDER.map((v) => (
              <span key={v} className="inline-flex items-center gap-[5px] text-[11px] text-text-2">
                <span className={`inline-block h-[9px] w-[9px] rounded-[2px] ${VERDICT_BAR[v]}`} />
                {VERDICT_LABEL[v]}
              </span>
            ))}
          </div>
        </div>

        <div className="rounded-[14px] border border-line bg-card px-[18px] py-4">
          <div className="text-[13.5px] font-semibold text-text">Gate pass rate · {windowShort}</div>
          <div className="mt-[18px] flex flex-col gap-[17px]">
            {data.gates.map((g) => {
              const passPct = g.total ? Math.round(((g.total - g.flagged) / g.total) * 100) : 100
              return (
                <div key={g.gate}>
                  <div className="mb-[7px] flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 text-[12.5px] text-text">
                      <span className={`inline-block h-2 w-2 rounded-full ${GATE_DOT[g.gate]}`} />
                      {GATE_PASS_LABEL[g.gate]}
                    </span>
                    <span className="font-mono text-[13px] font-semibold text-text">{passPct}%</span>
                  </div>
                  {/* Fill uses THAT gate's own accent, not a blanket green. */}
                  <div className="h-2 overflow-hidden rounded-[5px] bg-card-2">
                    <div className={`h-full ${GATE_DOT[g.gate]}`} style={{ width: `${passPct}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {data.n_runs_excluded_no_date > 0 && (
        // Honest bookkeeping: undated runs can't be placed on the time axis under a dated window.
        <p className="mt-2 text-[10.5px] text-text-3">
          {data.n_runs_excluded_no_date} run{data.n_runs_excluded_no_date === 1 ? '' : 's'} without a recorded
          date {data.n_runs_excluded_no_date === 1 ? 'is' : 'are'} excluded from this window.
        </p>
      )}

      {/* Recurring issue signatures — searchable, collapsible fixed-grid rows */}
      <div className="mt-[14px] rounded-[14px] border border-line bg-card px-[18px] py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[13.5px] font-semibold text-text">Recurring issue signatures · {windowShort}</div>
            <div className="mt-0.5 text-[12px] text-text-2">
              A signature recurring 3× auto-escalates to the pipeline-repair agent.
            </div>
          </div>
          <div className="flex min-w-[230px] items-center gap-[7px] rounded-[9px] border border-line bg-card-2 px-[10px] py-[6px]">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="shrink-0 text-text-3">
              <circle cx="11" cy="11" r="7" />
              <path d="m21 21-4.1-4.1" />
            </svg>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search historic issues…"
              className="min-w-0 flex-1 border-none bg-transparent text-[12.5px] text-text outline-none placeholder:text-text-3"
            />
          </div>
        </div>

        <div className="mt-3 flex flex-col gap-[9px]">
          {filteredSigs.map((s) => (
            <MonitoringSignatureRow
              key={s.signature}
              sig={s}
              open={openSigs.has(s.signature)}
              onToggle={() =>
                setOpenSigs((prev) => {
                  const next = new Set(prev)
                  if (next.has(s.signature)) next.delete(s.signature)
                  else next.add(s.signature)
                  return next
                })
              }
              windowShort={windowShort}
              windowLabel={windowLabel}
            />
          ))}

          {filteredSigs.length === 0 &&
            (query.trim() ? (
              <div className="rounded-[10px] border border-dashed border-line-strong px-6 py-6 text-center text-[12.5px] text-text-2">
                No historic issues match “{query.trim()}”.
              </div>
            ) : (
              <Empty message={`No recurring issue signatures in the last ${windowLabel}.`} />
            ))}
        </div>
      </div>
    </div>
  )
}
