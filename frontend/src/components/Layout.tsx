import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { api } from '../api'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

// The app shell: a fixed dark sidebar + top bar around a light, scrollable content area,
// faithful to the prototype (docs/design/frontend/PipeGuard.html). The attention count
// (runs with samples needing review) feeds the sidebar + bell badges.
export function Layout() {
  const [attention, setAttention] = useState(0)
  useEffect(() => {
    api
      .runs()
      .then((rs) => setAttention(rs.filter((r) => r.n_attention > 0).length))
      .catch(() => setAttention(0))
  }, [])
  return (
    <div className="flex h-screen overflow-hidden bg-page text-text">
      <Sidebar attention={attention} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar attention={attention} />
        <main className="flex-1 overflow-y-auto px-8 py-7">
          <div className="pg-fade">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
