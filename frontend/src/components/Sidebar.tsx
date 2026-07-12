import {
  Activity,
  Bell,
  ChevronUp,
  ClipboardList,
  FileCheck2,
  FileUp,
  Filter,
  GitFork,
  Inbox,
  LogOut,
  type LucideIcon,
  PanelLeftClose,
  PanelLeftOpen,
  Rows3,
  Settings,
  Shield,
  SlidersVertical,
  Star,
  UserCog,
  Waypoints,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import type { PageId } from '../access'
import { useAccess } from '../context/AccessContext'
import { useInbox } from '../context/InboxContext'
import { usePrefs } from '../context/PrefsContext'
import { useRole } from '../context/RoleContext'
import type { RunSummary } from '../types'
import { UserSettingsDialog } from './UserSettingsDialog'
import { Logo } from './Logo'

// `page` tags an item with its PageId so the page-access view-gate can filter it (canSee). Admin
// items carry no page — they're gated by isAdmin, not by the access profile.
type Item = { label: string; to: string; icon: LucideIcon; active: boolean; badge?: number; page?: PageId }
type Group = { heading: string; items: Item[] }

// Nav groups (Operate / Analyze / Configure, + an approver-only Admin group). Per-run views
// resolve to the run in context (else the first run) so they always navigate somewhere useful.
// The Decision-cards badge shows the CURRENT run's flagged sample count (its n_attention), in mono.
function useNav(runs: RunSummary[], defaultRunId: string | null): Group[] {
  const { pathname } = useLocation()
  const { runId } = useParams()
  const { isAdmin } = useRole()
  const { canSee } = useAccess()
  const { unreadCount } = useInbox()
  const run = runId ?? defaultRunId
  const runHome = run ? `/runs/${run}` : '/'
  const flagged = runs.find((r) => r.run_id === run)?.n_attention ?? 0
  const groups: Group[] = [
    {
      // Ordered Notification → Action → Steps (G4): the operator starts at what needs their
      // attention (Inbox), then what needs resolving (Review queue), then walks the process steps.
      // Accessioning is the FIRST process step (upstream of the samplesheet), so it leads the
      // step sub-sequence: accession → submit → intake → decide, with Runs (a list/index, not a
      // process step) pinned to the BOTTOM of the group (UIC-15).
      heading: 'Operate',
      items: [
        // Notification: the personal triage workspace (GA3), badged with the operator's unread count.
        { label: 'Inbox', to: '/inbox', icon: Bell, active: pathname.startsWith('/inbox'), badge: unreadCount || undefined, page: 'inbox' },
        // Action: issues waiting on a human.
        { label: 'Review queue', to: '/queue', icon: Inbox, active: pathname.startsWith('/queue'), page: 'queue' },
        // Steps: the process flow, beginning at subject accessioning (the CRM step).
        { label: 'Sample accessioning', to: '/accession', icon: ClipboardList, active: pathname.startsWith('/accession'), page: 'accession' },
        { label: 'Submit samplesheet', to: '/submit', icon: FileUp, active: pathname.startsWith('/submit'), page: 'submit' },
        {
          label: 'Intake gate',
          to: run ? `/runs/${run}/intake` : '/',
          icon: Filter,
          active: pathname.includes('/intake'),
          page: 'intake',
        },
        {
          label: 'Decision cards',
          to: runHome,
          icon: FileCheck2,
          active: /^\/runs\/[^/]+$/.test(pathname),
          badge: flagged || undefined,
          page: 'cards',
        },
        // Runs sits at the BOTTOM of the group — a list/index the operator returns to, not a
        // sequential process step (UIC-15).
        { label: 'Runs', to: '/', icon: Rows3, active: pathname === '/', page: 'runs' },
      ],
    },
    {
      heading: 'Analyze',
      items: [
        {
          label: 'Provenance',
          to: run ? `/runs/${run}/provenance` : '/',
          icon: Waypoints,
          active: pathname.includes('/provenance') || pathname.includes('/canvas'),
          page: 'provenance',
        },
        {
          label: 'Agent triage',
          to: run ? `/runs/${run}/agent` : '/',
          icon: Star,
          active: pathname.includes('/agent'),
          page: 'agent',
        },
        { label: 'Monitoring', to: '/monitoring', icon: Activity, active: pathname.startsWith('/monitoring'), page: 'monitoring' },
      ],
    },
    {
      heading: 'Configure',
      items: [
        { label: 'Pipeline builder', to: '/builder', icon: GitFork, active: pathname.startsWith('/builder'), page: 'builder' },
        { label: 'Settings', to: '/settings', icon: SlidersVertical, active: pathname.startsWith('/settings'), page: 'settings' },
      ],
    },
    // Admin is governance (users/RBAC/audit), gated to the dedicated admin capability (the login
    // identity, not just any approver) — see auth.ts / RoleContext.isAdmin. Its item has no `page`,
    // so it bypasses the access filter (isAdmin already bounds the whole group).
    ...(isAdmin
      ? [
          {
            heading: 'Admin',
            items: [
              { label: 'Admin panel', to: '/admin', icon: UserCog, active: pathname.startsWith('/admin') },
            ],
          },
        ]
      : []),
  ]
  // Page-access view-gate: keep only items this actor may see (untagged admin items always pass),
  // then drop any group left empty. isAdmin + the floor make canSee permissive, so a governance
  // user still sees everything.
  return groups
    .map((g) => ({ ...g, items: g.items.filter((it) => it.page == null || canSee(it.page)) }))
    .filter((g) => g.items.length > 0)
}

function UserPanel({ collapsed = false }: { collapsed?: boolean }) {
  const { actor, role, toggleRole, logout } = useRole()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [dialog, setDialog] = useState(false)
  const roleLabel = role.charAt(0).toUpperCase() + role.slice(1)
  // Reflect the live actor (Admin "Act as" can switch it), not a hardcoded user.
  const initials = actor.id.split(/[.\-_ ]/).map((p) => p[0]?.toUpperCase() ?? '').join('').slice(0, 2) || 'U'

  return (
    <div className={`relative border-t border-nav-border ${collapsed ? 'p-2' : 'p-3'}`}>
      <button
        onClick={() => setOpen((o) => !o)}
        // Collapsed: just the avatar acts as the account trigger; a title/aria-label keeps it legible.
        aria-label={collapsed ? `${actor.id} — account menu` : undefined}
        title={collapsed ? `${actor.id} (${roleLabel})` : undefined}
        className={`flex w-full items-center rounded-[9px] bg-nav-hover text-left transition-colors hover:brightness-110 ${
          collapsed ? 'justify-center p-1.5' : 'gap-2.5 px-2.5 py-[7px]'
        }`}
      >
        <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-full bg-[linear-gradient(150deg,#3a7,#186)] text-[12px] font-semibold text-white">
          {initials}
        </span>
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block truncate font-mono text-[12.5px] font-semibold text-nav-text">{actor.id}</span>
              <span className="flex items-center gap-1.5">
                <span className="h-[5px] w-[5px] rounded-full bg-[#3ba55d]" />
                <span className="text-[10.5px] text-nav-label">{roleLabel}</span>
              </span>
            </span>
            <ChevronUp size={14} className="shrink-0 text-nav-label" />
          </>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          {/* When collapsed the rail is too narrow to host the menu, so it pops out to a fixed
              width beyond the rail's right edge (still anchored to the account button). */}
          <div
            className={`absolute z-40 overflow-hidden rounded-[11px] border border-nav-border bg-nav-hover shadow-[0_16px_40px_rgba(0,0,0,0.4)] ${
              collapsed ? 'bottom-[54px] left-2 w-[232px]' : 'bottom-[66px] left-3 right-3'
            }`}
          >
            <div className="border-b border-nav-border px-3.5 py-3">
              <div className="font-mono text-[12.5px] font-semibold text-nav-text">{actor.id}</div>
              <div className="font-mono text-[10.5px] text-nav-label">{actor.id}@lab.org</div>
            </div>
            <button
              onClick={() => {
                setOpen(false)
                setDialog(true)
              }}
              className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[12.5px] text-nav-text hover:bg-nav-hover"
            >
              <Settings size={14} className="text-nav-text" />
              Settings
            </button>
            <button
              onClick={toggleRole}
              className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[12.5px] text-nav-text hover:bg-nav-hover"
            >
              <Shield size={14} className="text-nav-text" />
              <span className="flex-1">Role</span>
              <span className="font-mono text-[10.5px] capitalize text-nav-label">{role}</span>
            </button>
            <button
              onClick={() => {
                setOpen(false)
                logout()
                navigate('/login', { replace: true })
              }}
              className="flex w-full items-center gap-2.5 border-t border-nav-border px-3.5 py-2.5 text-left text-[12.5px] text-escalate-fg hover:bg-nav-hover"
            >
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
  // Collapse state lives in the shared prefs store (localStorage-persisted), so the rail survives
  // navigation + reload like the other prefs. Collapsing to an icons-only rail hands the reclaimed
  // width to the main content (which is flex-1 in Layout) — e.g. the Builder canvas beside its inspector.
  const { navCollapsed: collapsed, setNavCollapsed } = usePrefs()

  return (
    <aside
      // Width via inline style (not a w-[Npx] class) so the collapse works regardless of whether the
      // Tailwind JIT has generated the arbitrary-value rule; the transition-[width] class still animates it.
      className="relative flex shrink-0 flex-col border-r border-nav-border bg-nav text-nav-text transition-[width] duration-200 ease-in-out"
      style={{ width: collapsed ? 64 : 236 }}
    >
      <div
        className={`flex items-center pb-[15px] pt-[17px] ${
          collapsed ? 'flex-col gap-2 px-2' : 'gap-2.5 px-[18px]'
        }`}
      >
        <Link
          to="/"
          title="bayleaf — Runs"
          className={`flex min-w-0 items-center gap-2.5 ${collapsed ? '' : 'flex-1'}`}
        >
          <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-lg bg-[linear-gradient(155deg,#5aae77,#2f7a52)]">
            <Logo size={19} />
          </span>
          {!collapsed && (
            <span className="min-w-0 leading-[1.1]">
              <span className="block truncate text-[15px] font-bold tracking-[-0.2px] text-nav-text">bayleaf</span>
              <span className="block text-[10.5px] font-medium uppercase tracking-[0.3px] text-nav-label">
                Decision gate
              </span>
            </span>
          )}
        </Link>

        {/* Collapse / expand toggle — a chevron at the rail's inner edge. aria-expanded reflects
            the OPEN state (expanded = true), and the label/title flip so it stays legible collapsed. */}
        <button
          type="button"
          onClick={() => setNavCollapsed(!collapsed)}
          aria-expanded={!collapsed}
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-nav-label transition-colors hover:bg-nav-hover hover:text-nav-active-text"
        >
          {collapsed ? <PanelLeftOpen size={17} strokeWidth={1.8} /> : <PanelLeftClose size={17} strokeWidth={1.8} />}
        </button>
      </div>

      {/* overflow-x-hidden clips label reflow during the width transition so nothing spills into
          the content column mid-animation. */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden pb-2">
        {groups.map((g, gi) => (
          <div key={g.heading} className={gi === 0 ? 'mt-1.5' : 'mt-3.5'}>
            {collapsed
              ? gi > 0 && <div className="mx-3 mb-1 border-t border-nav-border/70" />
              : (
                  <p className="px-3 pb-1 pt-1.5 text-[10.5px] font-semibold uppercase tracking-[0.6px] text-nav-label">
                    {g.heading}
                  </p>
                )}
            <div className={`flex flex-col gap-0.5 ${collapsed ? 'px-2' : 'px-3'}`}>
              {g.items.map((it) => (
                <Link
                  key={it.label}
                  to={it.to}
                  // Collapsed rows are icon-only, so carry the label as aria-label + a hover tooltip.
                  aria-label={collapsed ? it.label : undefined}
                  title={collapsed ? it.label : undefined}
                  className={`flex items-center rounded-lg text-[13.5px] leading-[1.1] transition-colors ${
                    collapsed ? 'justify-center px-0 py-2.5' : 'gap-2.5 px-[11px] py-2'
                  } ${
                    it.active
                      ? 'bg-nav-active font-semibold text-nav-active-text'
                      : 'text-nav-text hover:bg-nav-hover hover:text-nav-active-text'
                  }`}
                >
                  <span className="relative flex shrink-0">
                    <it.icon size={17} strokeWidth={1.7} className="shrink-0" />
                    {/* Collapsed: the count can't sit inline, so pin a compact badge to the icon corner. */}
                    {collapsed && it.badge != null && (
                      <span className="absolute -right-1.5 -top-1.5 grid h-[13px] min-w-[13px] place-items-center rounded-full bg-escalate px-[3px] font-mono text-[8.5px] font-semibold leading-none text-white">
                        {it.badge}
                      </span>
                    )}
                  </span>
                  {!collapsed && <span className="flex-1 whitespace-nowrap">{it.label}</span>}
                  {!collapsed && it.badge != null && (
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

      <UserPanel collapsed={collapsed} />
    </aside>
  )
}
