import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { RunDetail } from './screens/RunDetail'
import { RunOverview } from './screens/RunOverview'

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-surface text-ink">
        <header className="border-b border-border px-8 py-4">
          <Link to="/" className="flex w-fit items-center gap-2">
            <span className="text-xl">🧬</span>
            <span className="text-xl font-semibold">PipeGuard</span>
            <span className="text-ink-dim text-sm ml-2">provenance &amp; QC decision gate</span>
          </Link>
        </header>
        <main className="p-8">
          <Routes>
            <Route path="/" element={<RunOverview />} />
            <Route path="/runs/:runId" element={<RunDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
