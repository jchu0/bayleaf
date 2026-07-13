import { ArrowLeft } from 'lucide-react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { pageLabel, type PageId } from '../access'
import { useApiHealth, type Health } from '../hooks/useApiHealth'
import type { RunSummary } from '../types'
import { NotificationBell } from './NotificationBell'
import { RunSelector } from './RunSelector'

// Top-bar reachability pill labels, driven by the shared real health poll (useApiHealth). Ready =
// API answered ok; Offline = it didn't; Checking = first poll in flight.
const HEALTH_META: Record<Health, { label: string; dot: string; tip: string }> = {
  checking: { label: 'Checking…', dot: 'bg-line-strong', tip: 'Checking the read-API…' },
  ready: { label: 'Ready', dot: 'bg-proceed', tip: 'The read-API is reachable.' },
  offline: { label: 'Offline', dot: 'bg-escalate', tip: 'The read-API is not reachable.' },
}

// The per-run sub-views (they carry a :runId in the path) — these show the run pill after the title.
const PER_RUN_PAGES: ReadonlySet<PageId> = new Set(['cards', 'intake', 'provenance', 'agent'])

// Route → PageId, so the crumb title comes from the SAME catalog that labels the nav (access.ts):
// one owner for each page's name, and no route silently falls through to "Runs" (accession / inbox
// were doing exactly that). Admin has no PageId (excluded from the catalog by design), so it's named
// literally. Order matters — the per-run sub-views live under /runs/:id/… and must be matched before
// the bare decision-cards route.
function routePage(pathname: string): PageId | 'admin' | null {
  if (pathname === '/') return 'runs'
  // The run-independent System agents page has its own PageId now; match it before the generic
  // /agent branch below so the crumb comes from the shared catalog like every other page.
  if (pathname === '/system-agents') return 'systemAgents'
  if (pathname.startsWith('/accession')) return 'accession'
  if (pathname.startsWith('/submit')) return 'submit'
  if (pathname.startsWith('/inbox')) return 'inbox'
  if (pathname.startsWith('/queue')) return 'queue'
  if (pathname.startsWith('/monitoring')) return 'monitoring'
  if (pathname.startsWith('/builder')) return 'builder'
  if (pathname.startsWith('/settings')) return 'settings'
  if (pathname.startsWith('/admin')) return 'admin'
  if (pathname.includes('/intake')) return 'intake'
  if (pathname.includes('/provenance') || pathname.includes('/canvas')) return 'provenance'
  if (pathname.includes('/agent')) return 'agent'
  if (pathname.startsWith('/runs/')) return 'cards'
  return null
}

// Contextual page title + run pill, derived from the route (mirrors the prototype top bar).
function useCrumb(): { title: string; run: string | null } {
  const { pathname } = useLocation()
  const { runId } = useParams()
  const page = routePage(pathname)
  const title = page === 'admin' ? 'Admin' : page ? pageLabel(page) : 'Runs'
  const run = page && page !== 'admin' && PER_RUN_PAGES.has(page) ? (runId ?? null) : null
  return { title, run }
}

export function TopBar({ runs = [] }: { runs?: RunSummary[] }) {
  const { title, run } = useCrumb()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const health = useApiHealth()

  // Switch the run in context while keeping the same view (e.g. decision cards → decision
  // cards, provenance → provenance) by swapping the run id in the current path.
  function switchRun(id: string) {
    navigate(pathname.replace(/\/runs\/[^/]+/, `/runs/${id}`))
  }

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
        // The shared, keyboard-navigable, loading/error-aware run picker (RunSelector) instead of a
        // bespoke switcher — one idiom everywhere. Runs are injected from Layout, so it never needs
        // to self-fetch; the footer jumps to the full Runs index.
        <RunSelector value={run} onChange={switchRun} runs={runs} onViewAll={() => navigate('/')} />
      )}

      <div className="ml-auto flex items-center gap-2.5">
        <span className="flex items-center gap-1.5 text-[13px] text-text-2" title={HEALTH_META[health].tip}>
          <span className={`h-2 w-2 rounded-full ${HEALTH_META[health].dot}`} />
          {HEALTH_META[health].label}
        </span>
        <NotificationBell />
      </div>
    </header>
  )
}
