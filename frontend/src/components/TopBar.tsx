import { ArrowLeft, Bell, ChevronDown, Search } from 'lucide-react'
import { useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import type { RunSummary } from '../types'
import { RUN_STATUS_META } from '../verdict'

// The run switcher shows at most this many rows; search narrows the full set, and a footer links
// to the full Runs list. A flat dropdown of every run does not scale (the prototype's pattern).
const MAX_RUN_ROWS = 8

// Contextual page title + run pill, derived from the route (mirrors the prototype top bar).
function useCrumb(): { title: string; run: string | null } {
  const { pathname } = useLocation()
  const { runId } = useParams()
  if (pathname === '/') return { title: 'Runs', run: null }
  if (pathname.startsWith('/submit')) return { title: 'Submit samplesheet', run: null }
  if (pathname.includes('/intake')) return { title: 'Intake gate', run: runId ?? null }
  if (pathname.startsWith('/queue')) return { title: 'Review queue', run: null }
  if (pathname.startsWith('/monitoring')) return { title: 'Monitoring', run: null }
  if (pathname.startsWith('/builder')) return { title: 'Pipeline builder', run: null }
  if (pathname.startsWith('/settings')) return { title: 'Settings', run: null }
  if (pathname.includes('/provenance') || pathname.includes('/canvas'))
    return { title: 'Provenance', run: runId ?? null }
  if (pathname.includes('/agent')) return { title: 'Agent triage', run: runId ?? null }
  if (runId) return { title: 'Decision cards', run: runId }
  return { title: 'Runs', run: null }
}

export function TopBar({ attention = 0, runs = [] }: { attention?: number; runs?: RunSummary[] }) {
  const { title, run } = useCrumb()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [query, setQuery] = useState('')

  // Switch the run in context while keeping the same view (e.g. decision cards → decision
  // cards, provenance → provenance) by swapping the run id in the current path.
  function switchRun(id: string) {
    setMenuOpen(false)
    setQuery('')
    navigate(pathname.replace(/\/runs\/[^/]+/, `/runs/${id}`))
  }
  function closeMenu() {
    setMenuOpen(false)
    setQuery('')
  }

  // F17: the pill dot reflects the run's REAL status (needs_review/running/released), never
  // inferred from n_attention. Search filters the full set by run id or platform; the list is
  // capped and a footer links to the full Runs list, so the switcher scales past a handful.
  const current = runs.find((r) => r.run_id === run)
  const q = query.trim().toLowerCase()
  const matches = q
    ? runs.filter(
        (r) => r.run_id.toLowerCase().includes(q) || (r.platform ?? '').toLowerCase().includes(q),
      )
    : runs
  const shownRuns = matches.slice(0, MAX_RUN_ROWS)

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-card px-5">
      {pathname !== '/' && (
        <button
          onClick={() => navigate(-1)}
          className="grid h-8 w-8 place-items-center rounded-lg text-text-2 hover:bg-card-2"
          aria-label="Back"
        >
          <ArrowLeft size={17} />
        </button>
      )}
      <span className="text-[15px] font-semibold text-text">{title}</span>

      {run && <span className="text-[13px] text-text-3">/</span>}
      {run && (
        <div className="relative">
          <button
            onClick={() => (menuOpen ? closeMenu() : setMenuOpen(true))}
            className="flex items-center gap-1.5 rounded-lg border border-line bg-card-2 px-2.5 py-1 font-mono text-[12px] text-text hover:border-line-strong"
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${current ? RUN_STATUS_META[current.status].dot : 'bg-line-strong'}`}
            />
            {run}
            <ChevronDown size={13} className="text-text-3" />
          </button>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={closeMenu} />
              <div className="absolute left-0 top-full z-20 mt-1 w-[360px] overflow-hidden rounded-xl border border-line-strong bg-card shadow-pop">
                <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
                  <Search size={14} className="text-text-3" />
                  {/* eslint-disable-next-line jsx-a11y/no-autofocus -- opening the switcher is an explicit user action; focusing search is expected */}
                  <input
                    autoFocus
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search runs by id or platform…"
                    className="min-w-0 flex-1 bg-transparent text-[12.5px] text-text outline-none placeholder:text-text-3"
                  />
                </div>
                <div className="max-h-[300px] overflow-y-auto p-1.5">
                  {shownRuns.map((r) => {
                    const meta = RUN_STATUS_META[r.status]
                    return (
                      <button
                        key={r.run_id}
                        onClick={() => switchRun(r.run_id)}
                        className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-card-2 ${
                          r.run_id === run ? 'bg-card-2' : ''
                        }`}
                      >
                        <span className={`h-[7px] w-[7px] shrink-0 rounded-full ${meta.dot}`} />
                        <span className="font-mono text-[12.5px] font-medium text-text">{r.run_id}</span>
                        {r.platform && <span className="text-[11px] text-text-3">· {r.platform}</span>}
                        <span className="ml-auto shrink-0 text-[11px] text-text-3">{meta.label}</span>
                      </button>
                    )
                  })}
                  {matches.length === 0 && (
                    <div className="px-3 py-5 text-center text-[12px] text-text-2">
                      No runs match “{query}”.
                    </div>
                  )}
                </div>
                <button
                  onClick={() => {
                    closeMenu()
                    navigate('/')
                  }}
                  className="flex w-full items-center justify-between border-t border-line bg-card px-3 py-2.5 hover:bg-card-2"
                >
                  <span className="text-[12px] font-semibold text-accent-strong">View all runs</span>
                  <span className="text-[11px] text-text-3">{runs.length} runs →</span>
                </button>
              </div>
            </>
          )}
        </div>
      )}

      <div className="ml-auto flex items-center gap-2.5">
        <div className="flex w-[230px] items-center gap-2 rounded-lg border border-line bg-card-2 px-2.5 py-1.5 text-[13px] text-text-3">
          <Search size={14} />
          <span>Search samples, rules…</span>
          <kbd className="rounded border border-line bg-card px-1 text-[10px] text-text-3">/</kbd>
        </div>
        <span className="flex items-center gap-1.5 text-[13px] text-text-2" title="Driven by data-fetch status (not a control)">
          <span className="h-2 w-2 rounded-full bg-proceed" />
          State: Ready
        </span>
        <button className="relative grid h-8 w-8 place-items-center rounded-lg text-text-2 hover:bg-card-2" aria-label="Notifications">
          <Bell size={17} strokeWidth={1.8} />
          {attention > 0 && (
            <span className="absolute right-0 top-0.5 grid h-[15px] min-w-[15px] place-items-center rounded-full bg-escalate px-0.5 text-[9px] font-semibold text-white">
              {attention}
            </span>
          )}
        </button>
      </div>
    </header>
  )
}
