import { AlertTriangle, ChevronRight, RotateCw, Search, Truck } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { DateRangePicker } from '../components/DateRangePicker'
import { FacetChip } from '../components/FacetChip'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
import type { RunStatus, RunSummary } from '../types'
import { RUN_STATUS_META as STATUS_META, VERDICT_BAR, VERDICT_LABEL } from '../verdict'

const VERDICTS = ['proceed', 'hold', 'rerun', 'escalate'] as const
type StatusFacet = 'all' | RunStatus
type SortKey = 'recent' | 'urgent'
type PerPage = '25' | '50' | '100'

const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
// ISO "2026-07-08" → "Jul 8, 2026" without a Date() round-trip (avoids a TZ day-shift).
function formatRunDate(iso: string | null): string | null {
  if (!iso) return null
  const [y, m, d] = iso.split('-')
  const label = MONTHS_SHORT[Number(m) - 1]
  return label ? `${label} ${Number(d)}, ${y}` : iso
}

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'recent', label: 'Recent' },
  { value: 'urgent', label: 'Urgent' },
]
const PER_PAGE_OPTIONS: { value: PerPage; label: string }[] = [
  { value: '25', label: '25' },
  { value: '50', label: '50' },
  { value: '100', label: '100' },
]
const FACETS: { key: StatusFacet; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'needs_review', label: 'Needs review' },
  { key: 'running', label: 'Sequencing' },
  { key: 'released', label: 'Released' },
]

// The stacked verdict bar: proceed→hold→rerun→escalate widths by count share. A `running` run
// has no per-sample verdicts yet, so it reads a single neutral track instead of an empty bar.
function VerdictBar({ counts, running }: { counts: Record<string, number>; running: boolean }) {
  const total = VERDICTS.reduce((s, v) => s + (counts[v] ?? 0), 0) || 1
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-[5px] bg-card-2">
      {running ? (
        <div className="w-full bg-card-3" title="sequencing" />
      ) : (
        VERDICTS.map((v) => {
          const n = counts[v] ?? 0
          return n ? (
            <div key={v} className={VERDICT_BAR[v]} style={{ width: `${(n / total) * 100}%` }} title={`${n} ${v}`} />
          ) : null
        })
      )}
    </div>
  )
}

// Inline per-verdict count legend under the bar — review rows only (running/released omit it,
// since a full-green or empty bar needs no gloss). e.g. "19 Proceed · 5 Hold · 2 Rerun · 2 Escalate".
function VerdictLegend({ counts }: { counts: Record<string, number> }) {
  const items = VERDICTS.filter((v) => (counts[v] ?? 0) > 0)
  if (!items.length) return null
  return (
    <div className="mt-2 flex flex-wrap gap-x-3.5 gap-y-1.5">
      {items.map((v) => (
        <span key={v} className="inline-flex items-center gap-1.5 text-[11px] text-text-3">
          <span className={`h-1.5 w-1.5 rounded-full ${VERDICT_BAR[v]}`} />
          <strong className="font-bold text-text-2">{counts[v]}</strong> {VERDICT_LABEL[v]}
        </span>
      ))}
    </div>
  )
}

function StatusPill({ status }: { status: RunStatus }) {
  const meta = STATUS_META[status]
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card-2 px-2 py-0.5 text-[11px] font-medium text-text-2">
      <span className={`h-[5px] w-[5px] rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  )
}

function RunCard({ run }: { run: RunSummary }) {
  const attn = run.n_attention > 0
  const running = run.status === 'running'
  // Both fields are honestly nullable; show only what was captured (never fabricate a value).
  const meta = [run.platform, formatRunDate(run.run_date)].filter(Boolean).join(' · ') || 'Details not captured'
  return (
    <Link
      to={`/runs/${run.run_id}`}
      className={`block rounded-xl border bg-card px-[17px] py-[15px] shadow-card transition-[box-shadow,border-color] duration-150 hover:border-line-strong hover:shadow-[0_4px_14px_rgba(16,24,40,0.10)] ${
        attn ? 'border-line-strong' : 'border-line'
      }`}
    >
      <div className="flex items-center gap-3.5">
        <div className="min-w-[172px]">
          <div className="font-mono text-[14px] font-semibold text-text">{run.run_id}</div>
          <div className="mt-[3px] text-[11.5px] text-text-3">{meta}</div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="mb-[7px] flex items-center gap-2.5">
            <span className="text-[12px] text-text-2">
              <strong className="font-mono text-text">{run.n_samples}</strong> samples
            </span>
            <StatusPill status={run.status} />
          </div>
          <VerdictBar counts={run.counts} running={running} />
          {run.status === 'needs_review' && <VerdictLegend counts={run.counts} />}
        </div>

        <div className="flex w-[190px] items-center justify-end gap-2.5">
          {attn && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-hold-bd bg-hold-bg px-[9px] py-[3px] text-[11.5px] font-semibold text-hold-fg">
              <AlertTriangle size={13} /> {run.n_attention} need attention
            </span>
          )}
          <ChevronRight size={18} className="shrink-0 text-text-3" />
        </div>
      </div>
    </Link>
  )
}

// Static title block — renders during loading/error too, so the shell stays stable.
function RunsHeader() {
  return (
    <PageHeader
      eyebrow="Operations"
      title="Sequencing runs"
      subtitle={
        <>
          Provenance &amp; QC decision gate. Each run resolves to a per-sample verdict —{' '}
          <span className="font-medium text-text">proceed, hold, rerun, or escalate</span>.
        </>
      }
      actions={
        <span className="flex items-center gap-2 whitespace-nowrap text-[12px] text-text-3">
          <span className="h-[7px] w-[7px] rounded-full bg-proceed shadow-[0_0_0_3px_var(--color-proceed-bg)]" />
          Gate online
        </span>
      }
    />
  )
}

// The design's specific run-index error (vs the generic shared ErrorBox): a named failure with
// mono status/path and an in-place retry.
function RunsError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="mt-[22px] flex flex-col items-center gap-3 rounded-[14px] border border-escalate-bd bg-escalate-bg p-[34px] text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-escalate-bd bg-card">
        <AlertTriangle size={24} className="text-escalate" strokeWidth={1.9} />
      </div>
      <div>
        <div className="text-[16px] font-semibold text-escalate-fg">Couldn't load run index</div>
        <div className="mt-1 max-w-[420px] text-[13px] text-text-2">
          The artifact store returned <span className="font-mono text-[12px]">503</span> reading{' '}
          <span className="font-mono text-[12px]">/runs</span>. Cached verdicts may be stale.
        </div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="mt-0.5 inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-[14px] py-2 text-[13px] font-medium text-text transition-colors hover:border-text-3"
      >
        <RotateCw size={14} /> Retry
      </button>
    </div>
  )
}

function RunsEmpty({ onClear }: { onClear: () => void }) {
  return (
    <div className="mt-[22px] flex flex-col items-center gap-2.5 rounded-[14px] border border-dashed border-line-strong bg-card p-10 text-center">
      <div className="flex h-[46px] w-[46px] items-center justify-center rounded-xl bg-card-2">
        <Truck size={23} className="text-text-3" strokeWidth={1.7} />
      </div>
      <div className="text-[16px] font-semibold text-text">No runs match this filter</div>
      <div className="max-w-[380px] text-[13px] text-text-2">
        Nothing is waiting on the gate right now. Clear the filter to see released runs.
      </div>
      <button
        type="button"
        onClick={onClear}
        className="mt-1 rounded-lg bg-accent px-[15px] py-2 text-[13px] font-medium text-white transition-colors hover:bg-accent-strong"
      >
        Show all runs
      </button>
    </div>
  )
}

export function RunOverview() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  // Header-borne full-set facet counts (X-PipeGuard-Status-Counts) — authoritative and stable
  // across the client-side filters below, so a chip's count never shifts as you narrow the list.
  const [statusCounts, setStatusCounts] = useState<Record<RunStatus, number> | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFacet>('all')
  const [sort, setSort] = useState<SortKey>('recent')
  const [dateStart, setDateStart] = useState<string | null>(null)
  const [dateEnd, setDateEnd] = useState<string | null>(null)
  const [perPage, setPerPage] = useState<PerPage>('25')
  const [page, setPage] = useState(1)

  // The whole scale kit (search · facet · sort · date · paginate) runs client-side over one
  // fetch: date-range has no backend param (F16) and it couples with pagination, so a single
  // in-memory pass keeps facet counts + the pager trivially consistent (28 runs). runsPage still
  // supplies the header-borne total + status-facet counts a header-blind runs() would drop.
  const load = useCallback(() => {
    setError(null)
    setRuns(null)
    api
      .runsPage()
      .then((res) => {
        setRuns(res.data)
        setStatusCounts(res.statusCounts)
      })
      .catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const filtered = useMemo(() => {
    if (!runs) return []
    const q = query.trim().toLowerCase()
    const out = runs.filter((r) => {
      if (statusFilter !== 'all' && r.status !== statusFilter) return false
      if (q && !r.run_id.toLowerCase().includes(q) && !(r.platform ?? '').toLowerCase().includes(q)) return false
      if (dateStart || dateEnd) {
        const iso = r.run_date // already ISO YYYY-MM-DD → lexicographic compare is date-correct
        if (!iso) return false
        if (dateStart && iso < dateStart) return false
        if (dateEnd && iso > dateEnd) return false
      }
      return true
    })
    return [...out].sort((a, b) => {
      if (sort === 'urgent') return b.n_attention - a.n_attention || b.n_samples - a.n_samples
      // recent: newest run_date first, run_id as the stable tiebreak (mirrors the API's key).
      const ka = a.run_date ?? a.run_id
      const kb = b.run_date ?? b.run_id
      return kb.localeCompare(ka) || b.run_id.localeCompare(a.run_id)
    })
  }, [runs, query, statusFilter, sort, dateStart, dateEnd])

  const per = Number(perPage)
  const total = filtered.length
  const pages = Math.max(1, Math.ceil(total / per))
  const currentPage = Math.min(page, pages) // clamp so a narrowing filter can't strand the pager
  const from = total === 0 ? 0 : (currentPage - 1) * per + 1
  const to = Math.min(currentPage * per, total)
  const pageRuns = filtered.slice((currentPage - 1) * per, currentPage * per)

  // Facet counts come from the header (full set, filter-independent); fall back to a client tally.
  const facetCount = (key: StatusFacet): number => {
    if (!runs) return 0
    if (key === 'all') return runs.length
    return statusCounts ? statusCounts[key] : runs.filter((r) => r.status === key).length
  }

  // Every control change resets to page 1 (a stale page could land past the new last page).
  const onQuery = (v: string) => {
    setQuery(v)
    setPage(1)
  }
  const onStatus = (k: StatusFacet) => {
    setStatusFilter(k)
    setPage(1)
  }
  const onSort = (k: SortKey) => {
    setSort(k)
    setPage(1)
  }
  const onDate = (s: string | null, e: string | null) => {
    setDateStart(s)
    setDateEnd(e)
    setPage(1)
  }
  const onPerPage = (v: PerPage) => {
    setPerPage(v)
    setPage(1)
  }
  const clearFilters = () => {
    setQuery('')
    setStatusFilter('all')
    setDateStart(null)
    setDateEnd(null)
    setPage(1)
  }

  return (
    <div className="pg-fade mx-auto max-w-[1080px]">
      <RunsHeader />

      {error ? (
        <RunsError onRetry={load} />
      ) : !runs ? (
        <div className="mt-[22px] flex flex-col gap-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-[78px] animate-pulse rounded-xl border border-line bg-card-2" />
          ))}
        </div>
      ) : (
        <>
          {/* toolbar row 1 — search · sort · date range */}
          <div className="mt-5 flex flex-wrap items-center gap-2.5">
            <div className="flex min-w-[230px] max-w-[340px] flex-1 items-center gap-2 rounded-[9px] border border-line bg-card px-[11px] py-[7px]">
              <Search size={15} className="shrink-0 text-text-3" />
              <input
                value={query}
                onChange={(e) => onQuery(e.target.value)}
                placeholder="Search run id or platform…"
                className="min-w-0 flex-1 border-none bg-transparent text-[13px] text-text outline-none placeholder:text-text-3"
              />
            </div>
            <div className="flex-1" />
            <span className="text-[11.5px] font-medium text-text-3">Sort</span>
            <SegmentedControl<SortKey> options={SORT_OPTIONS} value={sort} onChange={onSort} />
            <DateRangePicker start={dateStart} end={dateEnd} onChange={onDate} />
          </div>

          {/* toolbar row 2 — status facets w/ counts */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {FACETS.map((f) => (
              <FacetChip
                key={f.key}
                label={f.label}
                count={facetCount(f.key)}
                active={statusFilter === f.key}
                onClick={() => onStatus(f.key)}
              />
            ))}
          </div>

          {total === 0 ? (
            <RunsEmpty onClear={clearFilters} />
          ) : (
            <>
              <div className="mt-4 flex flex-col gap-[11px]">
                {pageRuns.map((run) => (
                  <RunCard key={run.run_id} run={run} />
                ))}
              </div>

              {/* pagination footer */}
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <span className="text-[12px] text-text-3">
                  Showing {from}–{to} of {total} runs
                </span>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[11.5px] text-text-3">Per page</span>
                    <SegmentedControl<PerPage> options={PER_PAGE_OPTIONS} value={perPage} onChange={onPerPage} />
                  </div>
                  {pages > 1 && (
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setPage(Math.max(1, currentPage - 1))}
                        className="h-7 min-w-[28px] rounded-[7px] border border-line bg-card text-[13px] text-text-2 transition-colors hover:border-line-strong"
                        aria-label="Previous page"
                      >
                        ‹
                      </button>
                      {Array.from({ length: pages }, (_, i) => i + 1).map((n) => (
                        <button
                          key={n}
                          type="button"
                          onClick={() => setPage(n)}
                          className={`h-7 min-w-[28px] rounded-[7px] px-2 text-[12px] transition-colors ${
                            n === currentPage
                              ? 'bg-accent font-semibold text-white'
                              : 'border border-line bg-card text-text-2 hover:border-line-strong'
                          }`}
                        >
                          {n}
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={() => setPage(Math.min(pages, currentPage + 1))}
                        className="h-7 min-w-[28px] rounded-[7px] border border-line bg-card text-[13px] text-text-2 transition-colors hover:border-line-strong"
                        aria-label="Next page"
                      >
                        ›
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
