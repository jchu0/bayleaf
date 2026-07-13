import { Outlet } from 'react-router-dom'
import { useRuns } from '../hooks/useRuns'
import { FeedbackWidget } from './FeedbackWidget'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

// The app shell: a fixed dark sidebar + top bar around a light, scrollable content area,
// faithful to the prototype. The run list feeds the attention badges, the sidebar's per-run nav
// targets, and the top-bar run switcher — sourced from the shared useRuns store (UX-DUP Runs #6)
// so RunOverview and the RunSelector fallback read the SAME single fetch, never a parallel copy.
export function Layout() {
  const { runs: storeRuns } = useRuns()
  const runs = storeRuns ?? []
  const defaultRunId = runs[0]?.run_id ?? null
  return (
    <div className="flex h-screen overflow-hidden bg-page text-text">
      <Sidebar runs={runs} defaultRunId={defaultRunId} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar runs={runs} />
        <main className="flex-1 overflow-y-auto px-8 py-7">
          <div className="pg-fade">
            <Outlet />
          </div>
          {/* One global feedback FAB in the light content column — rides every screen,
              touches none of them (off-gate product telemetry, W12). */}
          <FeedbackWidget />
        </main>
      </div>
    </div>
  )
}
