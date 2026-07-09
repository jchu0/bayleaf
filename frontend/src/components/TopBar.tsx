import { ArrowLeft, Bell, ChevronDown, Search } from 'lucide-react'
import { useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import type { RunSummary } from '../types'

// Contextual page title + run pill, derived from the route (mirrors the prototype top bar).
function useCrumb(): { title: string; run: string | null } {
  const { pathname } = useLocation()
  const { runId } = useParams()
  if (pathname === '/') return { title: 'Runs', run: null }
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
  const dot = (n: number) => (n > 0 ? 'bg-hold' : 'bg-proceed')

  // Switch the run in context while keeping the same view (e.g. decision cards → decision
  // cards, provenance → provenance) by swapping the run id in the current path.
  function switchRun(id: string) {
    setMenuOpen(false)
    navigate(pathname.replace(/\/runs\/[^/]+/, `/runs/${id}`))
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-card px-5">
      {pathname !== '/' && (
        <button
          onClick={() => navigate(-1)}
          className="grid h-8 w-8 place-items-center rounded-lg text-text-2 hover:bg-page"
          aria-label="Back"
        >
          <ArrowLeft size={17} />
        </button>
      )}
      <span className="text-[15px] font-semibold text-text">{title}</span>

      {run && (
        <div className="relative">
          <button
            onClick={() => setMenuOpen((o) => !o)}
            className="flex items-center gap-1.5 rounded-lg border border-line bg-page px-2.5 py-1 font-mono text-[12px] text-text hover:border-line-strong"
          >
            <span className={`h-1.5 w-1.5 rounded-full ${dot(runs.find((r) => r.run_id === run)?.n_attention ?? 0)}`} />
            {run}
            <ChevronDown size={13} className="text-text-3" />
          </button>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
              <div className="absolute left-0 top-full z-20 mt-1 w-60 overflow-hidden rounded-lg border border-line bg-card py-1 shadow-pop">
                {runs.map((r) => (
                  <button
                    key={r.run_id}
                    onClick={() => switchRun(r.run_id)}
                    className={`flex w-full items-center gap-2 px-3 py-2 text-left font-mono text-[12px] hover:bg-page ${
                      r.run_id === run ? 'bg-page text-text' : 'text-text-2'
                    }`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${dot(r.n_attention)}`} />
                    <span className="flex-1">{r.run_id}</span>
                    {r.n_attention > 0 && <span className="text-[10px] text-hold-fg">{r.n_attention} need review</span>}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <div className="ml-auto flex items-center gap-2.5">
        <div className="hidden items-center gap-2 rounded-lg border border-line bg-page px-2.5 py-1.5 text-[13px] text-text-3 md:flex">
          <Search size={14} />
          <span>Search samples, rules…</span>
          <kbd className="rounded border border-line bg-card px-1 text-[10px] text-text-3">/</kbd>
        </div>
        <span className="flex items-center gap-1.5 text-[13px] text-text-2" title="Driven by data-fetch status (not a control)">
          <span className="h-2 w-2 rounded-full bg-proceed" />
          State: Ready
        </span>
        <button className="relative grid h-8 w-8 place-items-center rounded-lg text-text-2 hover:bg-page" aria-label="Notifications">
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
