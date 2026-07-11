import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import type { PageId } from './access'
import { Layout } from './components/Layout'
import { PageAccessDenied } from './components/PageAccessDenied'
import { ToastProvider } from './components/Toast'
import { ConfirmProvider } from './components/ConfirmDialog'
import { AccessProvider, useAccess } from './context/AccessContext'
import { InboxProvider } from './context/InboxContext'
import { PrefsProvider } from './context/PrefsContext'
import { RoleProvider, useRole } from './context/RoleContext'
import { Accession } from './screens/Accession'
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

// Page-access VIEW-GATE (not a security control): hides a page a user's access profile lacks and
// shows a friendly denied state instead. isAdmin + the floor + the enforce switch live in
// useAccess().canSee, so an admin/floor page always passes. The API still authorizes every write by
// wire role (api/auth.py, unchanged) — deep-linking a denied URL hides the page, not a fetch.
function RequirePage({ page, children }: { page: PageId; children: ReactNode }) {
  const { canSee } = useAccess()
  if (!canSee(page)) return <PageAccessDenied page={page} />
  return <>{children}</>
}

export default function App() {
  return (
    <ToastProvider>
      <ConfirmProvider>
      <PrefsProvider>
      <RoleProvider>
      <AccessProvider>
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
              <Route path="/" element={<RequirePage page="runs"><RunOverview /></RequirePage>} />
              <Route path="/accession" element={<RequirePage page="accession"><Accession /></RequirePage>} />
              <Route path="/submit" element={<RequirePage page="submit"><Submit /></RequirePage>} />
              <Route path="/inbox" element={<RequirePage page="inbox"><Inbox /></RequirePage>} />
              <Route path="/runs/:runId" element={<RequirePage page="cards"><RunDetail /></RequirePage>} />
              <Route path="/runs/:runId/provenance" element={<RequirePage page="provenance"><Provenance /></RequirePage>} />
              <Route path="/runs/:runId/intake" element={<RequirePage page="intake"><Intake /></RequirePage>} />
              <Route path="/runs/:runId/agent" element={<RequirePage page="agent"><AgentTriage /></RequirePage>} />
              <Route path="/settings" element={<RequirePage page="settings"><Settings /></RequirePage>} />
              {/* Admin stays governed solely by isAdmin (its own guard) — never page-gated. */}
              <Route path="/admin" element={<Admin />} />
              <Route path="/monitoring" element={<RequirePage page="monitoring"><Monitoring /></RequirePage>} />
              <Route path="/queue" element={<RequirePage page="queue"><ReviewQueue /></RequirePage>} />
              <Route path="/builder" element={<RequirePage page="builder"><PipelineBuilder /></RequirePage>} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AccessProvider>
      </RoleProvider>
      </PrefsProvider>
      </ConfirmProvider>
    </ToastProvider>
  )
}
