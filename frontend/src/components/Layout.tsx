import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { api } from '../api'
import type { RunSummary } from '../types'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

// The app shell: a fixed dark sidebar + top bar around a light, scrollable content area,
// faithful to the prototype. The run list (fetched once) feeds the attention badges, the
// sidebar's per-run nav targets, and the top-bar run switcher.
export function Layout() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  useEffect(() => {
    api
      .runs()
      .then(setRuns)
      .catch(() => setRuns([]))
  }, [])
  const attention = runs.filter((r) => r.n_attention > 0).length
  const defaultRunId = runs[0]?.run_id ?? null
  return (
    <div className="flex h-screen overflow-hidden bg-page text-text">
      <Sidebar attention={attention} defaultRunId={defaultRunId} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar attention={attention} runs={runs} />
        <main className="flex-1 overflow-y-auto px-8 py-7">
          <div className="pg-fade">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
