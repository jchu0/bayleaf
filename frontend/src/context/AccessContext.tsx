import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from 'react'
import {
  type AccessAuditEntry,
  type AccessMap,
  DEFAULT_ACCESS,
  type PageId,
  type UserGrant,
  canSeePage,
  effectivePages,
} from '../access'
import { useRole } from './RoleContext'

// Page-access provider (mirrors PrefsContext's localStorage-persisted store). `canSee` resolves
// against the ACTING actor with an isAdmin bypass + a master `enforce` switch, so:
//   • an admin never strands themselves (isAdmin follows the LOGIN identity, RoleContext),
//   • Act-as naturally previews the impersonated user's nav (resolution keys on actor.id),
//   • turning enforcement off shows every page (the escape hatch).
// This is a client-side VIEW-GATE, not a security control — the API still authorizes every real
// write by wire role (api/auth.py, unchanged). AccessProvider MUST nest inside RoleProvider.

type AccessStore = { map: AccessMap; audit: AccessAuditEntry[]; enforce: boolean }

type AccessState = {
  map: AccessMap
  audit: AccessAuditEntry[]
  enforce: boolean // master switch (default true; admin can disable)
  canSee: (page: PageId) => boolean // resolves vs the ACTING actor, with isAdmin bypass
  effectiveFor: (userId: string) => Set<PageId> // for the editor's live preview
  setUserGrant: (userId: string, grant: UserGrant, audit: { summary: string }) => void
  resetDefaults: () => void
  setEnforce: (on: boolean) => void
}

const KEY = 'bayleaf.access'

function freshMap(): AccessMap {
  return structuredClone(DEFAULT_ACCESS)
}

function load(): AccessStore {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { map: freshMap(), audit: [], enforce: true }
    const parsed = JSON.parse(raw) as Partial<AccessStore>
    return {
      map: parsed.map ?? freshMap(),
      audit: parsed.audit ?? [],
      enforce: parsed.enforce ?? true,
    }
  } catch {
    return { map: freshMap(), audit: [], enforce: true }
  }
}

function persist(next: AccessStore): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // localStorage unavailable (private mode) — grants just won't survive a refresh.
  }
}

const AccessContext = createContext<AccessState | null>(null)

export function AccessProvider({ children }: { children: ReactNode }) {
  const { actor, session, isAdmin } = useRole()
  const [store, setStore] = useState<AccessStore>(() => load())

  // Every mutation appends a client-side audit entry attributed to the acting admin's LOGIN id
  // (session), so the Admin Activity feed shows who changed what — a labelled client-side seam.
  const auditor = session?.id ?? actor.id

  const setUserGrant = useCallback(
    (userId: string, grant: UserGrant, audit: { summary: string }) => {
      setStore((s) => {
        const entry: AccessAuditEntry = { at: new Date().toISOString(), actor: auditor, targetUser: userId, summary: audit.summary }
        const next: AccessStore = { ...s, map: { ...s.map, [userId]: grant }, audit: [entry, ...s.audit] }
        persist(next)
        return next
      })
    },
    [auditor],
  )

  const resetDefaults = useCallback(() => {
    setStore((s) => {
      const entry: AccessAuditEntry = {
        at: new Date().toISOString(),
        actor: auditor,
        targetUser: '*',
        summary: 'Reset all page-access grants to defaults',
      }
      const next: AccessStore = { map: freshMap(), audit: [entry, ...s.audit], enforce: s.enforce }
      persist(next)
      return next
    })
  }, [auditor])

  const setEnforce = useCallback(
    (on: boolean) => {
      setStore((s) => {
        const entry: AccessAuditEntry = {
          at: new Date().toISOString(),
          actor: auditor,
          targetUser: '*',
          summary: `Page-access enforcement ${on ? 'enabled' : 'disabled'}`,
        }
        const next: AccessStore = { ...s, enforce: on, audit: [entry, ...s.audit] }
        persist(next)
        return next
      })
    },
    [auditor],
  )

  // The bypass: admins always see everything (login-identity capability, never page-gated); with
  // enforcement off every page is visible; otherwise resolve the acting actor's grant.
  const canSee = useCallback(
    (page: PageId) => isAdmin || !store.enforce || canSeePage(store.map, actor.id, page),
    [isAdmin, store.enforce, store.map, actor.id],
  )
  const effectiveFor = useCallback((userId: string) => effectivePages(store.map[userId]), [store.map])

  const value = useMemo<AccessState>(
    () => ({
      map: store.map,
      audit: store.audit,
      enforce: store.enforce,
      canSee,
      effectiveFor,
      setUserGrant,
      resetDefaults,
      setEnforce,
    }),
    [store.map, store.audit, store.enforce, canSee, effectiveFor, setUserGrant, resetDefaults, setEnforce],
  )

  return <AccessContext.Provider value={value}>{children}</AccessContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAccess(): AccessState {
  const ctx = useContext(AccessContext)
  if (!ctx) throw new Error('useAccess must be used within <AccessProvider>')
  return ctx
}
