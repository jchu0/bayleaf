import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { setApiActor } from '../api'
import { type LoginResult, authenticate, isAdminId, loadSession, saveSession } from '../auth'
import type { Actor, Role } from '../types'

// One shared RBAC + auth source for the whole app (README §4). The demo login gate establishes WHO
// you are (`session`); the Admin "Act as" flow + the demo role toggle change WHO the app acts as
// (`actor`). It feeds the API client's X-Bayleaf-Actor/-Role headers. This is a DEMO affordance —
// flipping to approver unlocks approvals only, never a rules-decided verdict (dc.html labels the
// toggle "Toggle RBAC role (demo)"). `session` vs `actor`: an admin can Act-as another user for
// audited writes while keeping their own admin governance (isAdmin follows the login, not the act).
type RoleState = {
  session: Actor | null // authenticated identity (null ⇒ logged out; the app gates on this)
  isAuthenticated: boolean
  actor: Actor // acting identity (= session unless an admin "Act as" overrides it)
  role: Role
  isReviewer: boolean
  isApprover: boolean
  isAdmin: boolean // governance capability (Admin panel + Act-as), from the LOGIN identity
  login: (email: string, password: string) => LoginResult
  logout: () => void
  setActor: (actor: Actor) => void
  setRole: (role: Role) => void
  toggleRole: () => void
}

// Placeholder acting-actor while logged out — never used for a write (the gate stops render), but
// keeps `actor` a non-null Actor so consumers stay simple.
const LOGGED_OUT_ACTOR: Actor = { id: 'anonymous', role: 'viewer' }

const RoleContext = createContext<RoleState | null>(null)

export function RoleProvider({ children }: { children: ReactNode }) {
  // Rehydrate a persisted demo session (id + role only — never a token/password) so a refresh stays
  // signed in. `session` is the real login; `actor` is who the app currently acts as.
  const [session, setSession] = useState<Actor | null>(() => loadSession())
  const [actor, setActorState] = useState<Actor>(() => loadSession() ?? LOGGED_OUT_ACTOR)
  const role = actor.role

  // Send actor headers only while authenticated; a logged-out client carries none.
  useEffect(() => {
    setApiActor(session ? actor : null)
  }, [actor, session])

  const login = useCallback((email: string, password: string): LoginResult => {
    const res = authenticate(email, password)
    if (res.ok) {
      setSession(res.actor)
      setActorState(res.actor)
      saveSession(res.actor)
    }
    return res
  }, [])

  const logout = useCallback(() => {
    setSession(null)
    setActorState(LOGGED_OUT_ACTOR)
    saveSession(null)
  }, [])

  const setActor = useCallback((next: Actor) => setActorState(next), [])
  const setRole = useCallback((next: Role) => setActorState((a) => ({ ...a, role: next })), [])
  const toggleRole = useCallback(
    () => setActorState((a) => ({ ...a, role: a.role === 'approver' ? 'reviewer' : 'approver' })),
    [],
  )

  // Admin governance follows the LOGIN identity, so an admin can Act-as anyone and still return.
  const isAdmin = session != null && isAdminId(session.id)

  const value = useMemo<RoleState>(
    () => ({
      session,
      isAuthenticated: session != null,
      actor,
      role,
      isReviewer: role === 'reviewer' || role === 'approver',
      isApprover: role === 'approver',
      isAdmin,
      login,
      logout,
      setActor,
      setRole,
      toggleRole,
    }),
    [session, actor, role, isAdmin, login, logout, setActor, setRole, toggleRole],
  )

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>
}

// Co-located with its provider by design; the hook + provider are one cohesive unit.
// eslint-disable-next-line react-refresh/only-export-components
export function useRole(): RoleState {
  const ctx = useContext(RoleContext)
  if (!ctx) throw new Error('useRole must be used within <RoleProvider>')
  return ctx
}
