import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Intake } from './screens/Intake'
import { Monitoring } from './screens/Monitoring'
import { Provenance } from './screens/Provenance'
import { ReviewQueue } from './screens/ReviewQueue'
import { RunDetail } from './screens/RunDetail'
import { RunOverview } from './screens/RunOverview'
import { Settings } from './screens/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<RunOverview />} />
          <Route path="/runs/:runId" element={<RunDetail />} />
          <Route path="/runs/:runId/provenance" element={<Provenance />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/queue" element={<ReviewQueue />} />
          <Route path="/intake" element={<Intake />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
