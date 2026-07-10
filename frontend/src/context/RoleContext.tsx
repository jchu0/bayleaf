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
  setActor: (actor: Actor) => void
  setRole: (role: Role) => void
  toggleRole: () => void
}

const DEFAULT_ACTOR: Actor = { id: 'a.rivera', role: 'reviewer' }

const RoleContext = createContext<RoleState | null>(null)

export function RoleProvider({ children }: { children: ReactNode }) {
  // Full actor (id + role) so the Admin "Act as" flow can switch WHO is acting, not just the
  // role — every audited write is then attributed to the chosen actor, and `viewer` is reachable.
  const [actor, setActorState] = useState<Actor>(DEFAULT_ACTOR)
  const role = actor.role

  // Keep the API client's actor in lockstep so every write carries the current id + role.
  useEffect(() => {
    setApiActor(actor)
  }, [actor])

  const setActor = useCallback((next: Actor) => setActorState(next), [])
  const setRole = useCallback((next: Role) => setActorState((a) => ({ ...a, role: next })), [])
  const toggleRole = useCallback(
    () => setActorState((a) => ({ ...a, role: a.role === 'approver' ? 'reviewer' : 'approver' })),
    [],
  )

  const value = useMemo<RoleState>(
    () => ({
      actor,
      role,
      isReviewer: role === 'reviewer' || role === 'approver',
      isApprover: role === 'approver',
      setActor,
      setRole,
      toggleRole,
    }),
    [actor, role, setActor, setRole, toggleRole],
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
