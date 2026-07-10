import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { setApiActor } from '../api'
import type { Actor, Role } from '../types'

// One shared RBAC source for the whole app (README §4). The user-panel popover toggles it;
// the Review queue, Settings threshold save/approve, and Pipeline-builder approve all gate on
// it. It also feeds the API client's X-PipeGuard-Actor/-Role headers. This is a DEMO affordance
// (dc.html labels the toggle "Toggle RBAC role (demo)") — flipping to approver unlocks approvals
// only, never a rules-decided verdict.
type RoleState = {
  actor: Actor
  role: Role
  isReviewer: boolean
  isApprover: boolean
  setRole: (role: Role) => void
  toggleRole: () => void
}

const DEFAULT_ACTOR: Actor = { id: 'a.rivera', role: 'reviewer' }

const RoleContext = createContext<RoleState | null>(null)

export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<Role>(DEFAULT_ACTOR.role)
  const actor = useMemo<Actor>(() => ({ id: DEFAULT_ACTOR.id, role }), [role])

  // Keep the API client's actor in lockstep so every write carries the current role.
  useEffect(() => {
    setApiActor(actor)
  }, [actor])

  const setRole = useCallback((next: Role) => setRoleState(next), [])
  const toggleRole = useCallback(
    () => setRoleState((r) => (r === 'approver' ? 'reviewer' : 'approver')),
    [],
  )

  const value = useMemo<RoleState>(
    () => ({
      actor,
      role,
      isReviewer: role === 'reviewer' || role === 'approver',
      isApprover: role === 'approver',
      setRole,
      toggleRole,
    }),
    [actor, role, setRole, toggleRole],
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
