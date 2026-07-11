import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { Layout } from './components/Layout'
import { ToastProvider } from './components/Toast'
import { ConfirmProvider } from './components/ConfirmDialog'
import { InboxProvider } from './context/InboxContext'
import { PrefsProvider } from './context/PrefsContext'
import { RoleProvider, useRole } from './context/RoleContext'
import { Admin } from './screens/Admin'
import { AgentTriage } from './screens/AgentTriage'
import { Inbox } from './screens/Inbox'
import { Intake } from './screens/Intake'
import { Login } from './screens/Login'
import { Monitoring } from './screens/Monitoring'
import { PipelineBuilder } from './screens/PipelineBuilder'
import { Provenance } from './screens/Provenance'
import { ReviewQueue } from './screens/ReviewQueue'
import { RunDetail } from './screens/RunDetail'
import { RunOverview } from './screens/RunOverview'
import { Settings } from './screens/Settings'
import { Submit } from './screens/Submit'

// Auth gate: an unauthenticated visitor is redirected to /login, preserving where they were headed
// so login can bounce them back. Everything under <Layout> is protected; /login is the one public route.
function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useRole()
  const location = useLocation()
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <ToastProvider>
      <ConfirmProvider>
      <PrefsProvider>
      <RoleProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              element={
                <RequireAuth>
                  <InboxProvider>
                    <Layout />
                  </InboxProvider>
                </RequireAuth>
              }
            >
              <Route path="/" element={<RunOverview />} />
              <Route path="/submit" element={<Submit />} />
              <Route path="/inbox" element={<Inbox />} />
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
      </PrefsProvider>
      </ConfirmProvider>
    </ToastProvider>
  )
}
