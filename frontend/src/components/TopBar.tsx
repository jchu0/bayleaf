import { Bell, ChevronDown, Search } from 'lucide-react'
import { useLocation, useParams } from 'react-router-dom'

// Contextual page title + run pill, derived from the route (mirrors the prototype top bar).
function useCrumb(): { title: string; run: string | null } {
  const { pathname } = useLocation()
  const { runId } = useParams()
  if (pathname === '/') return { title: 'Runs', run: null }
  if (pathname.startsWith('/intake')) return { title: 'Intake gate', run: null }
  if (pathname.startsWith('/queue')) return { title: 'Review queue', run: null }
  if (pathname.startsWith('/monitoring')) return { title: 'Monitoring', run: null }
  if (pathname.startsWith('/settings')) return { title: 'Settings', run: null }
  if (pathname.includes('/provenance') || pathname.includes('/canvas'))
    return { title: 'Provenance', run: runId ?? null }
  if (runId) return { title: 'Decision cards', run: runId }
  return { title: 'Runs', run: null }
}

export function TopBar({ attention = 0 }: { attention?: number }) {
  const { title, run } = useCrumb()
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-card px-5">
      <span className="text-[15px] font-semibold text-text">{title}</span>
      {run && (
        <span className="flex items-center gap-1.5 rounded-lg border border-line bg-page px-2.5 py-1 font-mono text-[12px] text-text">
          <span className="h-1.5 w-1.5 rounded-full bg-hold" />
          {run}
          <ChevronDown size={13} className="text-text-3" />
        </span>
      )}

      <div className="ml-auto flex items-center gap-2.5">
        <div className="hidden items-center gap-2 rounded-lg border border-line bg-page px-2.5 py-1.5 text-[13px] text-text-3 md:flex">
          <Search size={14} />
          <span>Search samples, rules…</span>
          <kbd className="rounded border border-line bg-card px-1 text-[10px] text-text-3">/</kbd>
        </div>
        <span className="flex items-center gap-1.5 text-[13px] text-text-2">
          <span className="h-2 w-2 rounded-full bg-proceed" />
          State: Ready
        </span>
        <button className="relative grid h-8 w-8 place-items-center rounded-lg text-text-2 hover:bg-page">
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
