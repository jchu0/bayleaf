import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ToastProvider } from './components/Toast'
import { RoleProvider } from './context/RoleContext'
import { Admin } from './screens/Admin'
import { AgentTriage } from './screens/AgentTriage'
import { Intake } from './screens/Intake'
import { Monitoring } from './screens/Monitoring'
import { PipelineBuilder } from './screens/PipelineBuilder'
import { Provenance } from './screens/Provenance'
import { ReviewQueue } from './screens/ReviewQueue'
import { RunDetail } from './screens/RunDetail'
import { RunOverview } from './screens/RunOverview'
import { Settings } from './screens/Settings'
import { Submit } from './screens/Submit'

export default function App() {
  return (
    <ToastProvider>
      <RoleProvider>
        <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<RunOverview />} />
            <Route path="/submit" element={<Submit />} />
            <Route path="/runs/:runId" element={<RunDetail />} />
            <Route path="/runs/:runId/provenance" element={<Provenance />} />
            <Route path="/runs/:runId/intake" element={<Intake />} />
            <Route path="/runs/:runId/agent" element={<AgentTriage />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/queue" element={<ReviewQueue />} />
            <Route path="/builder" element={<PipelineBuilder />} />
          </Route>
        </Routes>
        </BrowserRouter>
      </RoleProvider>
    </ToastProvider>
  )
}
