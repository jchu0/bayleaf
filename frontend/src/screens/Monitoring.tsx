import { EyeOff, RotateCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Bar, CartesianGrid, ComposedChart, Line, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { DateRangePicker } from '../components/DateRangePicker'
import { MonitoringSignatureRow } from '../components/MonitoringSignatureRow'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl, type SegmentOption } from '../components/SegmentedControl'
import { Empty, ErrorBox, Loading } from '../components/States'
import { useRefresh } from '../hooks/useRefresh'
import type { Gate, MonitoringMetrics, MonitoringWindow, Verdict } from '../types'
import { GATE_DOT, VERDICT_LABEL } from '../verdict'

// The window control offers the three dated windows README §5.8 mandates; the backend applies one
// window to the whole payload, so it governs the KPIs, throughput, gate-pass, and signatures
// uniformly. ('all' is a valid MonitoringWindow but intentionally not offered here.)
const WINDOW_OPTIONS: SegmentOption<MonitoringWindow>[] = [
  { value: '7d', label: '7d' },
  { value: '14d', label: '14d' },
  { value: '30d', label: '30d' },
]
const WINDOW_LABEL: Record<string, string> = { '7d': '7 days', '14d': '14 days', '30d': '30 days', all: 'all time' }

// Per-page options for the signatures pager, mirroring the Runs list (RunOverview). NOTE: the
// Verdict-over-time chart no longer has a per-page control (it scrolls sideways instead, M5).
type PerPage = '25' | '50' | '100'
const PER_PAGE_OPTIONS: SegmentOption<PerPage>[] = [
  { value: '25', label: '25' },
  { value: '50', label: '50' },
  { value: '100', label: '100' },
]

// Verdict base colors — theme-INVARIANT (the dark theme overrides only the -bg/-bd/-fg variants,
// not these bases), so they're safe to hand to Recharts as literal fills in both light and dark.
const V_HEX: Record<Verdict, string> = {
  proceed: '#1a854e',
  hold: '#b07714',
  rerun: '#c1560f',
  escalate: '#cf3238',
}
// The flagged-trend line — a neutral blue that reads on both the sand and dark canvases and is
// distinct from every verdict color.
const TREND_HEX = '#3b73d6'

// Gate-pass row labels — the design labels only QC/Variant with "gate".
const GATE_PASS_LABEL: Record<Gate, string> = { preflight: 'Preflight', qc: 'QC gate', variant: 'Variant gate' }

// Frame geometry for the throughput chart: a constant per-column slot so bar density never distorts
// as the run count changes; the chart holds a ~14-day frame (FRAME_W) and scrolls sideways beyond it.
const COL_W = 42
const FRAME_W = 588
const CLEARED_KEY = 'pipeguard.monitoring.cleared'

// Throughput-bar date in DD-MM-YY (maintainer preference, includes the year) from the run's [Header]
// ISO date. We never fabricate a date: an undated run (shouldn't appear in a dated window) → run id.
function shortDate(runDate: string | null, runId: string): string {
  if (runDate && runDate.length >= 10) {
    const [y, m, d] = runDate.slice(0, 10).split('-')
    return `${d}-${m}-${y.slice(2)}`
  }
  return runId.length > 6 ? runId.slice(-6) : runId
}

// The five toggleable trend lines (M7): the four verdicts + the flagged (non-proceed) total. Each
// overlays the stacked bars as a monotone line; the legend chips toggle them on/off.
const TREND_LINES: { key: Verdict | 'flagged'; label: string; color: string }[] = [
  { key: 'proceed', label: 'Proceed', color: '#1a854e' },
  { key: 'hold', label: 'Hold', color: '#b07714' },
  { key: 'rerun', label: 'Rerun', color: '#c1560f' },
  { key: 'escalate', label: 'Escalate', color: '#cf3238' },
  { key: 'flagged', label: 'Flagged', color: '#3b73d6' },
]

type ChartDatum = {
  label: string
  runId: string
  samples: number
  proceed: number
  hold: number
  rerun: number
  escalate: number
  flagged: number
}

// Grounded hover card (M2): every number comes from the run's real per-verdict counts — no synthesis.
function ChartTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: ChartDatum }> }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const rows: [Verdict, number][] = [
    ['proceed', d.proceed],
    ['hold', d.hold],
    ['rerun', d.rerun],
    ['escalate', d.escalate],
  ]
  return (
    <div className="rounded-lg border border-line-strong bg-card px-3 py-2 text-[11px] shadow-pop">
      <div className="font-mono text-[11px] font-semibold text-text">{d.runId}</div>
      <div className="mb-1 text-[10px] text-text-3">
        {d.label} · {d.samples} samples
      </div>
      {rows
        .filter(([, n]) => n > 0)
        .map(([v, n]) => (
          <div key={v} className="flex items-center gap-1.5">
            <span className="inline-block h-[8px] w-[8px] rounded-[2px]" style={{ background: V_HEX[v] }} />
            <span className="text-text-2">{VERDICT_LABEL[v]}</span>
            <span className="ml-auto pl-4 font-mono font-semibold text-text">{n}</span>
          </div>
        ))}
      <div className="mt-1 flex items-center gap-1.5 border-t border-line pt-1">
        <span className="inline-block h-[8px] w-[8px] rounded-full" style={{ background: TREND_HEX }} />
        <span className="text-text-2">Flagged</span>
        <span className="ml-auto pl-4 font-mono font-semibold text-text">{d.flagged}</span>
      </div>
    </div>
  )
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
  const [sigPerPage, setSigPerPage] = useState<PerPage>('25')
  const [sigPage, setSigPage] = useState(1)
  // Signatures the operator has cleared from view (M4) — a REVERSIBLE, client-side view filter
  // (localStorage-persisted, keyed by the unique signature id), never a DB purge. Cleared signatures
  // stay searchable/recoverable via the "Cleared" toggle + each row's Restore action.
  const [cleared, setCleared] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(CLEARED_KEY)
      return new Set<string>(raw ? (JSON.parse(raw) as string[]) : [])
    } catch {
      return new Set<string>()
    }
  })
  const [showCleared, setShowCleared] = useState(false)
  // Which of the 5 trend lines are drawn (M7). Default: flagged on (the prior behavior), the four
  // verdict lines off — they overlay the bars, so on-by-default would clutter.
  const [trendOn, setTrendOn] = useState<Record<string, boolean>>({
    proceed: false,
    hold: false,
    rerun: false,
    escalate: false,
    flagged: true,
  })
  useEffect(() => {
    try {
      localStorage.setItem(CLEARED_KEY, JSON.stringify([...cleared]))
    } catch {
      /* localStorage unavailable — the view filter simply won't persist across reloads. */
    }
  }, [cleared])
  const toggleClear = useCallback((signature: string) => {
    setCleared((prev) => {
      const next = new Set(prev)
      if (next.has(signature)) next.delete(signature)
      else next.add(signature)
      return next
    })
  }, [])

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
    return data.signatures.filter((s) => `${s.signature} ${s.rule_id} ${s.title}`.toLowerCase().includes(q))
  }, [data, query])

  // Split the (search-filtered) signatures into the main view vs. the cleared set (M4). Both stay
  // searchable — clearing only moves a row into the collapsible "Cleared" section, never drops it.
  const visibleSigs = useMemo(() => filteredSigs.filter((s) => !cleared.has(s.signature)), [filteredSigs, cleared])
  const clearedSigs = useMemo(() => filteredSigs.filter((s) => cleared.has(s.signature)), [filteredSigs, cleared])

  // Client-side pagination over the visible signatures (the payload is uncapped, F21).
  const sigPer = Number(sigPerPage)
  const sigTotal = visibleSigs.length
  const sigPages = Math.max(1, Math.ceil(sigTotal / sigPer))
  const sigCurPage = Math.min(sigPage, sigPages) // clamp so a narrowing filter can't strand the pager
  const sigFrom = sigTotal === 0 ? 0 : (sigCurPage - 1) * sigPer + 1
  const sigTo = Math.min(sigCurPage * sigPer, sigTotal)
  const pagedSigs = visibleSigs.slice((sigCurPage - 1) * sigPer, sigCurPage * sigPer)
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

  // Chart rows carry each run's real per-verdict counts + a flagged (non-proceed) total for the
  // trend line. No fabricated values — an absent verdict is a 0, not a guess.
  const chartData: ChartDatum[] = chartRuns.map((r) => {
    const hold = r.counts.hold ?? 0
    const rerun = r.counts.rerun ?? 0
    const escalate = r.counts.escalate ?? 0
    return {
      label: shortDate(r.run_date, r.run_id),
      runId: r.run_id,
      samples: r.n_samples,
      proceed: r.counts.proceed ?? 0,
      hold,
      rerun,
      escalate,
      flagged: hold + rerun + escalate,
    }
  })
  // Freeze to a ~14-day frame, scroll beyond it (M1). Width is a constant per-column slot × count,
  // floored at the frame so few runs don't stretch; maxBarSize caps bar width so they don't fatten.
  const chartWidth = Math.max(FRAME_W, chartData.length * COL_W)

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
        <div className="min-w-0 rounded-[14px] border border-line bg-card px-[18px] py-4">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <div className="text-[13.5px] font-semibold text-text">Verdicts over time</div>
            {/* Honest scope note (a): the date range narrows only this chart. The KPI tiles and the
                gate-pass rate stay aggregated over the selected window because api.monitoring exposes
                a window enum, not date params, so they cannot be re-derived client-side. */}
            <div className="text-[10.5px] text-text-3">
              Date range refines this chart only · KPIs &amp; gate-pass stay {windowShort}-scoped
            </div>
          </div>
          {chartData.length === 0 ? (
            <p className="mt-4 text-[12.5px] text-text-3">
              {hasDateFilter ? 'No runs in the selected date range.' : 'No dated runs in this window.'}
            </p>
          ) : (
            // Fixed 14-day frame; the chart scrolls sideways when the run count exceeds it (M1). The
            // Y-axis lives inside the plot, so it scrolls with the earliest runs — reading left→right
            // (oldest→newest) keeps it in view for the common case.
            <div className="mt-3 overflow-x-auto">
              <ComposedChart
                width={chartWidth}
                height={224}
                data={chartData}
                margin={{ top: 8, right: 12, bottom: 0, left: -6 }}
                barCategoryGap="24%"
              >
                <CartesianGrid vertical={false} stroke="rgba(128,138,152,0.22)" />
                <YAxis
                  tick={{ fontSize: 9, fill: '#8b95a1' }}
                  axisLine={false}
                  tickLine={false}
                  width={34}
                  allowDecimals={false}
                  label={{ value: 'samples', angle: -90, position: 'insideLeft', style: { fontSize: 9, fill: '#8b95a1', textAnchor: 'middle' }, offset: 18 }}
                />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 9, fill: '#8b95a1', angle: -35, textAnchor: 'end' }}
                  height={46}
                  tickMargin={4}
                  axisLine={{ stroke: 'rgba(128,138,152,0.3)' }}
                  tickLine={false}
                  interval={0}
                />
                <Tooltip cursor={{ fill: 'rgba(128,138,152,0.12)' }} content={<ChartTooltip />} />
                <Bar dataKey="proceed" stackId="v" fill={V_HEX.proceed} maxBarSize={26} isAnimationActive={false} />
                <Bar dataKey="hold" stackId="v" fill={V_HEX.hold} maxBarSize={26} isAnimationActive={false} />
                <Bar dataKey="rerun" stackId="v" fill={V_HEX.rerun} maxBarSize={26} isAnimationActive={false} />
                <Bar dataKey="escalate" stackId="v" fill={V_HEX.escalate} maxBarSize={26} radius={[2, 2, 0, 0]} isAnimationActive={false} />
                {/* Toggleable trend lines (M7) — the four verdicts + flagged, each an overlay. */}
                {TREND_LINES.filter((t) => trendOn[t.key]).map((t) => (
                  <Line
                    key={t.key}
                    type="monotone"
                    dataKey={t.key}
                    name={t.label}
                    stroke={t.color}
                    strokeWidth={2}
                    dot={{ r: 2, fill: t.color, strokeWidth: 0 }}
                    isAnimationActive={false}
                  />
                ))}
              </ComposedChart>
            </div>
          )}
          {/* Legend doubles as the trend-line toggles (M7): swatch colors match the stacked bars, and
              each chip toggles its overlay line on/off. Flagged = the non-proceed total. */}
          <div className="mt-[14px] flex flex-wrap items-center gap-2 border-t border-line pt-3">
            <span className="mr-1 text-[10.5px] font-medium uppercase tracking-[0.4px] text-text-3">Trend lines</span>
            {TREND_LINES.map((t) => {
              const on = trendOn[t.key]
              return (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setTrendOn((p) => ({ ...p, [t.key]: !p[t.key] }))}
                  aria-pressed={on}
                  title={`${on ? 'Hide' : 'Show'} the ${t.label} trend line`}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-[3px] text-[11px] transition-colors ${
                    on ? 'border-line-strong bg-card-2 text-text' : 'border-line bg-card text-text-3 hover:border-line-strong'
                  }`}
                >
                  <span className="inline-block h-[3px] w-[13px] rounded-full" style={{ background: t.color, opacity: on ? 1 : 0.45 }} />
                  {t.label}
                </button>
              )
            })}
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
          <div className="flex flex-wrap items-center gap-2">
            {/* Cleared-view toggle (M4) — shows the reversibly-hidden signatures; count keeps them
                discoverable so a cleared item is never silently lost. */}
            {cleared.size > 0 && (
              <button
                type="button"
                onClick={() => setShowCleared((v) => !v)}
                className={`inline-flex items-center gap-1.5 rounded-[9px] border px-[10px] py-[6px] text-[11.5px] transition-colors ${
                  showCleared ? 'border-accent bg-accent-weak text-accent-strong' : 'border-line bg-card-2 text-text-2 hover:border-line-strong'
                }`}
                title="Show signatures you've cleared from the main view (reversible)"
              >
                <EyeOff size={13} />
                Cleared · {cleared.size}
              </button>
            )}
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
              cleared={false}
              onToggleClear={() => toggleClear(s.signature)}
            />
          ))}

          {visibleSigs.length === 0 &&
            (query.trim() ? (
              <div className="rounded-[10px] border border-dashed border-line-strong px-6 py-6 text-center text-[12.5px] text-text-2">
                No historic issues match “{query.trim()}”{cleared.size > 0 ? ' in the main view' : ''}.
              </div>
            ) : cleared.size > 0 ? (
              <div className="rounded-[10px] border border-dashed border-line-strong px-6 py-6 text-center text-[12.5px] text-text-2">
                All recurring signatures are cleared from view. Use “Cleared · {cleared.size}” to review or restore them.
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
                <SegmentedControl<PerPage> options={PER_PAGE_OPTIONS} value={sigPerPage} onChange={setSigPerPage} />
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

        {/* Cleared signatures (M4) — reversibly hidden; still fully rendered + searchable + escalatable. */}
        {showCleared && clearedSigs.length > 0 && (
          <div className="mt-4 border-t border-line pt-3">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">
              Cleared from view · {clearedSigs.length}
            </div>
            <div className="flex flex-col gap-[9px] opacity-90">
              {clearedSigs.map((s) => (
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
                  cleared={true}
                  onToggleClear={() => toggleClear(s.signature)}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
