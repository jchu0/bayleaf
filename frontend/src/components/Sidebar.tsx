import {
  Activity,
  FileCheck2,
  Filter,
  GitBranch,
  ListChecks,
  type LucideIcon,
  Rows3,
  SlidersHorizontal,
  Sparkles,
} from 'lucide-react'
import { Link, useLocation, useParams } from 'react-router-dom'

type Item = { label: string; to: string; icon: LucideIcon; active: boolean; badge?: number }
type Group = { heading: string; items: Item[] }

// Grouped nav (Operate / Analyze / Configure), per the handoff. Per-run views (decision
// cards, provenance, triage) resolve to the run currently in context, else the first run —
// so they always navigate somewhere useful instead of dead-ending.
function useNav(attention: number, defaultRunId: string | null): Group[] {
  const { pathname } = useLocation()
  const { runId } = useParams()
  const run = runId ?? defaultRunId
  const runHome = run ? `/runs/${run}` : '/'
  return [
    {
      heading: 'Operate',
      items: [
        { label: 'Runs', to: '/', icon: Rows3, active: pathname === '/' },
        {
          label: 'Intake gate',
          to: run ? `/runs/${run}/intake` : '/',
          icon: Filter,
          active: pathname.includes('/intake'),
        },
        {
          label: 'Decision cards',
          to: runHome,
          icon: FileCheck2,
          active: /^\/runs\/[^/]+$/.test(pathname),
          badge: attention || undefined,
        },
        { label: 'Review queue', to: '/queue', icon: ListChecks, active: pathname.startsWith('/queue') },
      ],
    },
    {
      heading: 'Analyze',
      items: [
        {
          label: 'Provenance',
          to: run ? `/runs/${run}/provenance` : '/',
          icon: GitBranch,
          active: pathname.includes('/provenance') || pathname.includes('/canvas'),
        },
        {
          label: 'Agent triage',
          to: run ? `/runs/${run}/agent` : '/',
          icon: Sparkles,
          active: pathname.includes('/agent'),
        },
        { label: 'Monitoring', to: '/monitoring', icon: Activity, active: pathname.startsWith('/monitoring') },
      ],
    },
    {
      heading: 'Configure',
      items: [
        { label: 'Pipeline builder', to: '/builder', icon: GitBranch, active: pathname.startsWith('/builder') },
        { label: 'Settings', to: '/settings', icon: SlidersHorizontal, active: pathname.startsWith('/settings') },
      ],
    },
  ]
}

export function Sidebar({
  attention = 0,
  defaultRunId = null,
}: {
  attention?: number
  defaultRunId?: string | null
}) {
  const groups = useNav(attention, defaultRunId)
  return (
    <aside className="flex w-[236px] shrink-0 flex-col border-r border-nav-border bg-nav text-nav-text">
      <Link to="/" className="flex items-center gap-2.5 px-[18px] pb-[15px] pt-[17px]">
        <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-lg bg-[linear-gradient(155deg,#2f6bd6,#1a4fac)]">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={1.9} strokeLinecap="round">
            <path d="M5 3c0 6 14 6 14 12M19 3c0 6-14 6-14 12M5 21c0-2 14-2 14 0M5 3c0 2 14 2 14 0" />
            <path d="M7 6h10M8 9.5h8M8 14.5h8M7 18h10" strokeWidth={1.3} />
          </svg>
        </span>
        <span className="leading-[1.1]">
          <span className="block text-[15px] font-bold tracking-[-0.2px] text-white">PipeGuard</span>
          <span className="block text-[10.5px] font-medium uppercase tracking-[0.3px] text-nav-label">
            Decision gate
          </span>
        </span>
      </Link>

      <nav className="flex-1 overflow-y-auto pb-2">
        {groups.map((g) => (
          <div key={g.heading} className="mt-1.5">
            <p className="px-3 pb-1 pt-1.5 text-[10.5px] font-semibold uppercase tracking-[0.6px] text-nav-label">
              {g.heading}
            </p>
            <div className="flex flex-col gap-0.5 px-3">
              {g.items.map((it) => (
                <Link
                  key={it.label}
                  to={it.to}
                  className={`flex items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-[13.5px] transition-colors ${
                    it.active
                      ? 'bg-nav-hover font-medium text-white'
                      : 'text-nav-text hover:bg-nav-hover/60 hover:text-white'
                  }`}
                >
                  <it.icon size={17} strokeWidth={1.7} className="shrink-0" />
                  <span className="flex-1">{it.label}</span>
                  {it.badge != null && (
                    <span className="grid h-[18px] min-w-[18px] place-items-center rounded-full bg-escalate px-1 text-[10.5px] font-semibold text-white">
                      {it.badge}
                    </span>
                  )}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="flex items-center gap-2.5 border-t border-nav-border px-4 py-3">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-[linear-gradient(155deg,#2f6bd6,#1a4fac)] text-xs font-semibold text-white">
          AR
        </span>
        <span className="leading-tight">
          <span className="block text-[13px] font-medium text-white">a.rivera</span>
          <span className="block text-[11px] text-nav-label">Reviewer</span>
        </span>
      </div>
    </aside>
  )
}
