import {
  Activity,
  ChevronUp,
  FileCheck2,
  FileUp,
  Filter,
  GitFork,
  Inbox,
  LogOut,
  type LucideIcon,
  Rows3,
  Settings,
  Shield,
  SlidersVertical,
  Star,
  Waypoints,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useRole } from '../context/RoleContext'
import type { RunSummary } from '../types'
import { UserSettingsDialog } from './UserSettingsDialog'

type Item = { label: string; to: string; icon: LucideIcon; active: boolean; badge?: number }
type Group = { heading: string; items: Item[] }

// Two-group nav (Operate / Configure) per README §4 — the source of truth over the stale
// 3-group prototype. Per-run views resolve to the run in context (else the first run) so they
// always navigate somewhere useful. The Decision-cards badge shows the CURRENT run's flagged
// sample count (hold+rerun+escalate = its n_attention), in mono.
function useNav(runs: RunSummary[], defaultRunId: string | null): Group[] {
  const { pathname } = useLocation()
  const { runId } = useParams()
  const run = runId ?? defaultRunId
  const runHome = run ? `/runs/${run}` : '/'
  const flagged = runs.find((r) => r.run_id === run)?.n_attention ?? 0
  return [
    {
      heading: 'Operate',
      items: [
        { label: 'Submit samplesheet', to: '/submit', icon: FileUp, active: pathname.startsWith('/submit') },
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
          badge: flagged || undefined,
        },
        { label: 'Review queue', to: '/queue', icon: Inbox, active: pathname.startsWith('/queue') },
        {
          label: 'Provenance',
          to: run ? `/runs/${run}/provenance` : '/',
          icon: Waypoints,
          active: pathname.includes('/provenance') || pathname.includes('/canvas'),
        },
        {
          label: 'Agent triage',
          to: run ? `/runs/${run}/agent` : '/',
          icon: Star,
          active: pathname.includes('/agent'),
        },
        { label: 'Monitoring', to: '/monitoring', icon: Activity, active: pathname.startsWith('/monitoring') },
      ],
    },
    {
      heading: 'Configure',
      items: [
        { label: 'Pipeline builder', to: '/builder', icon: GitFork, active: pathname.startsWith('/builder') },
        { label: 'Settings', to: '/settings', icon: SlidersVertical, active: pathname.startsWith('/settings') },
      ],
    },
  ]
}

function UserPanel() {
  const { role, toggleRole } = useRole()
  const [open, setOpen] = useState(false)
  const [dialog, setDialog] = useState(false)
  const roleLabel = role.charAt(0).toUpperCase() + role.slice(1)

  return (
    <div className="relative border-t border-nav-border p-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2.5 rounded-[9px] bg-nav-hover px-2.5 py-[7px] text-left transition-colors hover:brightness-110"
      >
        <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-full bg-[linear-gradient(150deg,#3a7,#186)] text-[12px] font-semibold text-white">
          AR
        </span>
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate text-[12.5px] font-semibold text-[#e7ecf1]">a.rivera</span>
          <span className="flex items-center gap-1.5">
            <span className="h-[5px] w-[5px] rounded-full bg-[#3ba55d]" />
            <span className="text-[10.5px] text-[#7c8794]">{roleLabel}</span>
          </span>
        </span>
        <ChevronUp size={14} className="shrink-0 text-[#7c8794]" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute bottom-[66px] left-3 right-3 z-40 overflow-hidden rounded-[11px] border border-[#2b3543] bg-nav-hover shadow-[0_16px_40px_rgba(0,0,0,0.4)]">
            <div className="border-b border-[#2b3543] px-3.5 py-3">
              <div className="text-[12.5px] font-semibold text-[#e7ecf1]">Ada Rivera</div>
              <div className="font-mono text-[10.5px] text-[#7c8794]">a.rivera@lab.org</div>
            </div>
            <button
              onClick={() => {
                setOpen(false)
                setDialog(true)
              }}
              className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[12.5px] text-[#c3ccd6] hover:bg-white/5"
            >
              <Settings size={14} className="text-[#c3ccd6]" />
              Settings
            </button>
            <button
              onClick={toggleRole}
              className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[12.5px] text-[#c3ccd6] hover:bg-white/5"
            >
              <Shield size={14} className="text-[#c3ccd6]" />
              <span className="flex-1">Role</span>
              <span className="font-mono text-[10.5px] capitalize text-[#8b97a4]">{role}</span>
            </button>
            <button className="flex w-full items-center gap-2.5 border-t border-[#2b3543] px-3.5 py-2.5 text-left text-[12.5px] text-[#e0868c] hover:bg-white/5">
              <LogOut size={14} />
              Sign out
            </button>
          </div>
        </>
      )}

      {dialog && <UserSettingsDialog onClose={() => setDialog(false)} />}
    </div>
  )
}

export function Sidebar({
  runs = [],
  defaultRunId = null,
}: {
  runs?: RunSummary[]
  defaultRunId?: string | null
}) {
  const groups = useNav(runs, defaultRunId)
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
          <span className="block text-[10.5px] font-medium uppercase tracking-[0.3px] text-[#7c8794]">
            Decision gate
          </span>
        </span>
      </Link>

      <nav className="flex-1 overflow-y-auto pb-2">
        {groups.map((g, gi) => (
          <div key={g.heading} className={gi === 0 ? 'mt-1.5' : 'mt-3.5'}>
            <p className="px-3 pb-1 pt-1.5 text-[10.5px] font-semibold uppercase tracking-[0.6px] text-nav-label">
              {g.heading}
            </p>
            <div className="flex flex-col gap-0.5 px-3">
              {g.items.map((it) => (
                <Link
                  key={it.label}
                  to={it.to}
                  className={`flex items-center gap-2.5 rounded-lg px-[11px] py-2 text-[13.5px] leading-[1.1] transition-colors ${
                    it.active
                      ? 'bg-nav-active font-semibold text-white'
                      : 'text-[#aab4bf] hover:bg-nav-hover hover:text-white'
                  }`}
                >
                  <it.icon size={17} strokeWidth={1.7} className="shrink-0" />
                  <span className="flex-1">{it.label}</span>
                  {it.badge != null && (
                    <span className="grid h-[17px] min-w-[17px] place-items-center rounded-[9px] bg-escalate px-[5px] font-mono text-[10.5px] font-semibold text-white">
                      {it.badge}
                    </span>
                  )}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <UserPanel />
    </aside>
  )
}
