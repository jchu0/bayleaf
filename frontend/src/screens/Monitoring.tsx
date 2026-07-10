import { RotateCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { DateRangePicker } from '../components/DateRangePicker'
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

// Recurring-signature pagination, mirroring the Runs list (RunOverview) so the two are consistent.
type SigPerPage = '25' | '50' | '100'
const SIG_PER_PAGE: SegmentOption<SigPerPage>[] = [
  { value: '25', label: '25' },
  { value: '50', label: '50' },
  { value: '100', label: '100' },
]

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
  // Date-range refinement for the throughput chart only (see the chart note below). api.monitoring
  // takes a window enum, not date params, so this filters the already-fetched runs client-side.
  const [dateStart, setDateStart] = useState<string | null>(null)
  const [dateEnd, setDateEnd] = useState<string | null>(null)
  const [openSigs, setOpenSigs] = useState<Set<string>>(new Set())
  const [sigPerPage, setSigPerPage] = useState<SigPerPage>('25')
  const [sigPage, setSigPage] = useState(1)

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

  // Client-side pagination over the filtered signatures (the payload is uncapped, F21).
  const sigPer = Number(sigPerPage)
  const sigTotal = filteredSigs.length
  const sigPages = Math.max(1, Math.ceil(sigTotal / sigPer))
  const sigCurPage = Math.min(sigPage, sigPages) // clamp so a narrowing filter can't strand the pager
  const sigFrom = sigTotal === 0 ? 0 : (sigCurPage - 1) * sigPer + 1
  const sigTo = Math.min(sigCurPage * sigPer, sigTotal)
  const pagedSigs = filteredSigs.slice((sigCurPage - 1) * sigPer, sigCurPage * sigPer)
  // Reset to page 1 when the window, search, or per-page changes.
  useEffect(() => {
    setSigPage(1)
  }, [window, query, sigPerPage])

  const control = (
    <div className="flex items-center gap-2">
      <SegmentedControl options={WINDOW_OPTIONS} value={window} onChange={setWindow} />
      <DateRangePicker start={dateStart} end={dateEnd} onChange={(s, e) => { setDateStart(s); setDateEnd(e) }} />
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
  // The date range refines ONLY the throughput chart. api.monitoring(window) has no date params, so
  // KPIs (o) and gate-pass (data.gates) are server-aggregated over the whole window and can't be
  // re-derived client-side — we filter the already-fetched per-run rows and note the scope limit.
  const hasDateFilter = !!(dateStart || dateEnd)
  const chartRuns = hasDateFilter
    ? data.runs.filter((r) => {
        const iso = r.run_date // already ISO YYYY-MM-DD → lexicographic compare is date-correct
        if (!iso) return false
        if (dateStart && iso < dateStart) return false
        if (dateEnd && iso > dateEnd) return false
        return true
      })
    : data.runs
  const maxSamples = Math.max(...chartRuns.map((r) => r.n_samples), 1)

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
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <div className="text-[13.5px] font-semibold text-text">Verdicts over time</div>
            {/* Honest scope note (a): the date range narrows only this chart. The KPI tiles and the
                gate-pass rate stay aggregated over the selected window because api.monitoring exposes
                a window enum, not date params, so they cannot be re-derived client-side. */}
            <div className="text-[10.5px] text-text-3">
              Date range refines this chart only · KPIs &amp; gate-pass stay {windowShort}-scoped
            </div>
          </div>
          {chartRuns.length === 0 ? (
            <p className="mt-4 text-[12.5px] text-text-3">
              {hasDateFilter ? 'No runs in the selected date range.' : 'No dated runs in this window.'}
            </p>
          ) : (
            <div className="mt-4 flex gap-2">
              {/* Y-axis gutter: a rotated "samples" axis label + max / half / 0 tick labels aligned to
                  the plot height (kept in its own flex sub-columns so the label never overlaps a tick). */}
              <div className="flex h-[150px] shrink-0 gap-1" aria-hidden="true">
                <div className="relative w-3">
                  <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 -rotate-90 whitespace-nowrap text-[9px] font-medium tracking-wide text-text-3">
                    samples
                  </span>
                </div>
                <div className="relative w-6">
                  <span className="absolute right-0 top-0 -translate-y-1/2 font-mono text-[9px] text-text-3">
                    {maxSamples}
                  </span>
                  <span className="absolute right-0 top-1/2 -translate-y-1/2 font-mono text-[9px] text-text-3">
                    {Math.round(maxSamples / 2)}
                  </span>
                  <span className="absolute bottom-0 right-0 translate-y-1/2 font-mono text-[9px] text-text-3">
                    0
                  </span>
                </div>
              </div>

              {/* Scroll viewport: bars are a CONSTANT width so the row never distorts as the run
                  count grows (a long window ≈ a 14-day view's density); when they overrun the row
                  it scrolls sideways instead of squishing. `w-max min-w-full` fills the row when
                  few runs, then grows to content (scroll) when many. The Y-axis gutter stays fixed. */}
              <div className="min-w-0 flex-1 overflow-x-auto">
                <div className="w-max min-w-full">
                  {/* Plot area: gridlines (0 / half / max) drawn behind the bars, both 150px tall so
                      the stacked bar % heights read against the same scale the ticks label. */}
                  <div className="relative h-[150px]">
                    <div className="pointer-events-none absolute inset-0" aria-hidden="true">
                      {[0, 0.5, 1].map((f) => (
                        <div
                          key={f}
                          className="absolute inset-x-0 border-t border-dashed border-line"
                          style={{ top: `${(1 - f) * 100}%` }}
                        />
                      ))}
                    </div>
                    <div className="relative flex h-full items-end gap-[12px]">
                      {chartRuns.map((r) => (
                        <div
                          key={r.run_id}
                          className="flex h-full w-[28px] shrink-0 flex-col justify-end gap-[2px]"
                          title={`${r.run_id} · ${r.n_samples} samples`}
                        >
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
                      ))}
                    </div>
                  </div>
                  {/* Date labels — mirror the bar flex so each sits centered under its column. */}
                  <div className="mt-[7px] flex gap-[12px]">
                    {chartRuns.map((r) => (
                      <div key={r.run_id} className="w-[28px] shrink-0 text-center">
                        <span className="whitespace-nowrap font-mono text-[9px] text-text-3">
                          {shortDate(r.run_date, r.run_id)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
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
          {pagedSigs.map((s) => (
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

        {sigTotal > 0 && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3 text-[11.5px] text-text-2">
            <span>
              Showing {sigFrom}–{sigTo} of {sigTotal} signatures
            </span>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className="text-[11.5px] text-text-3">Per page</span>
                <SegmentedControl<SigPerPage> options={SIG_PER_PAGE} value={sigPerPage} onChange={setSigPerPage} />
              </div>
              {sigPages > 1 && (
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setSigPage(Math.max(1, sigCurPage - 1))}
                    className="h-7 min-w-[28px] rounded-[7px] border border-line bg-card text-[13px] text-text-2 transition-colors hover:border-line-strong"
                    aria-label="Previous page"
                  >
                    ‹
                  </button>
                  {Array.from({ length: sigPages }, (_, i) => i + 1).map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setSigPage(n)}
                      className={`h-7 min-w-[28px] rounded-[7px] px-2 text-[12px] transition-colors ${
                        n === sigCurPage
                          ? 'bg-accent font-semibold text-white'
                          : 'border border-line bg-card text-text-2 hover:border-line-strong'
                      }`}
                    >
                      {n}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => setSigPage(Math.min(sigPages, sigCurPage + 1))}
                    className="h-7 min-w-[28px] rounded-[7px] border border-line bg-card text-[13px] text-text-2 transition-colors hover:border-line-strong"
                    aria-label="Next page"
                  >
                    ›
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
