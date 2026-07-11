import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { useRole } from './RoleContext'

// GA3 — the intentional notification workspace. This is a PERSONAL organization layer that sits
// entirely OFF the deterministic gate (like the feedback widget): it reads the already-off-gate
// review-queue tickets and lets an operator triage them on their OWN terms — read/unread, flag,
// re-prioritize, drag onto a kanban board, schedule with a due date, annotate — plus author their
// own reminders (the "self-notification" system). It never sets or reads a verdict/confidence.
//
// Why a context (not a screen-local hook): the whole point of the maintainer's ask is that page
// changes must NOT lose your place — so the triage state lives above the router and persists to
// localStorage, scoped per operator. Derived items come from the live ticket feed; the user's
// overlay (what they did to each item) is stored keyed by item id so a re-fetch never clobbers it.

export type InboxSource = 'escalate' | 'rerun' | 'hold' | 'self'
export type InboxColumn = 'inbox' | 'todo' | 'doing' | 'done'
export type InboxPriority = 'high' | 'med' | 'low' | 'none'

// The user-owned mutable state for a single item (both derived tickets and self-authored items).
// Every field is optional — an absent overlay means "untouched", so defaults come from the base.
type ItemMeta = {
  read?: boolean
  flagged?: boolean
  priority?: InboxPriority
  column?: InboxColumn
  due?: string | null // yyyy-mm-dd, or null
  note?: string
}

// A self-authored reminder — the immutable creation record; its mutable state lives in the overlay
// like any other item, so flag/priority/column/due/note all work uniformly.
type SelfRaw = { id: string; title: string; createdAt: string }

// The merged, render-ready item the UI consumes.
export type InboxItem = {
  id: string
  source: InboxSource
  title: string
  runId: string | null
  sampleId: string | null
  gate: string | null
  link: string | null
  createdAt: string
  isSelf: boolean
  // resolved overlay (base default ⋈ user overlay):
  read: boolean
  flagged: boolean
  priority: InboxPriority
  column: InboxColumn
  due: string | null
  note: string
}

type InboxState = {
  items: InboxItem[]
  unreadCount: number
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  markRead: (id: string, read?: boolean) => void
  markAllRead: () => void
  toggleFlag: (id: string) => void
  setPriority: (id: string, p: InboxPriority) => void
  setColumn: (id: string, c: InboxColumn) => void
  setDue: (id: string, due: string | null) => void
  setNote: (id: string, note: string) => void
  addSelfItem: (title: string, opts?: { due?: string | null; note?: string }) => void
  deleteSelfItem: (id: string) => void
}

const PRIORITY_FROM_TICKET: Record<string, InboxPriority> = { high: 'high', medium: 'med', low: 'low' }

function overlayKey(actorId: string): string {
  return `pipeguard.inbox.overlay.${actorId}`
}
function selfKey(actorId: string): string {
  return `pipeguard.inbox.self.${actorId}`
}

function loadJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

const InboxContext = createContext<InboxState | null>(null)

export function InboxProvider({ children }: { children: ReactNode }) {
  const { actor } = useRole()
  const actorId = actor.id
  const [tickets, setTickets] = useState<{ id: string; title: string; run_id: string; sample_id: string; gate: string; verdict: string; created_at: string; priority: string }[]>([])
  const [selfItems, setSelfItems] = useState<SelfRaw[]>(() => loadJson(selfKey(actorId), []))
  const [overlay, setOverlay] = useState<Record<string, ItemMeta>>(() => loadJson(overlayKey(actorId), {}))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Re-read the per-operator overlay + self items whenever the acting operator changes (Admin's
  // "Act as" swaps identity), so each person sees their own triage state, not a shared one.
  useEffect(() => {
    setSelfItems(loadJson(selfKey(actorId), []))
    setOverlay(loadJson(overlayKey(actorId), {}))
  }, [actorId])

  // Persist the two user-owned stores. Derived tickets are re-fetched, never persisted.
  useEffect(() => {
    try {
      localStorage.setItem(overlayKey(actorId), JSON.stringify(overlay))
    } catch {
      /* localStorage unavailable — triage state simply won't survive a reload. */
    }
  }, [overlay, actorId])
  useEffect(() => {
    try {
      localStorage.setItem(selfKey(actorId), JSON.stringify(selfItems))
    } catch {
      /* see above */
    }
  }, [selfItems, actorId])

  // Pull the actionable tickets (open + in review) — these ARE the notifications. Resolved tickets
  // drop off the feed. A failed fetch degrades to an empty derived feed; self items still work.
  const refresh = useCallback(async () => {
    setError(null)
    try {
      const [open, inReview] = await Promise.all([
        api.listTickets({ status: 'open' }),
        api.listTickets({ status: 'in_review' }),
      ])
      setTickets(
        [...open, ...inReview].map((t) => ({
          id: t.id,
          title: t.title,
          run_id: t.run_id,
          sample_id: t.sample_id,
          gate: t.gate,
          verdict: t.verdict,
          created_at: t.created_at,
          priority: t.priority,
        })),
      )
    } catch (e) {
      setError(String(e))
      setTickets([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Merge base (ticket or self) with its overlay into a render-ready item. Derived defaults:
  // unread, unflagged, priority from the ticket, in the inbox column. Self items start read
  // (you wrote them) and unprioritized.
  const items = useMemo<InboxItem[]>(() => {
    const derived: InboxItem[] = tickets.map((t) => {
      const m = overlay[t.id] ?? {}
      const src = (t.verdict === 'escalate' || t.verdict === 'rerun' || t.verdict === 'hold' ? t.verdict : 'hold') as InboxSource
      return {
        id: t.id,
        source: src,
        title: t.title,
        runId: t.run_id,
        sampleId: t.sample_id,
        gate: t.gate,
        link: '/queue',
        createdAt: t.created_at,
        isSelf: false,
        read: m.read ?? false,
        flagged: m.flagged ?? false,
        priority: m.priority ?? PRIORITY_FROM_TICKET[t.priority] ?? 'none',
        column: m.column ?? 'inbox',
        due: m.due ?? null,
        note: m.note ?? '',
      }
    })
    const selves: InboxItem[] = selfItems.map((s) => {
      const m = overlay[s.id] ?? {}
      return {
        id: s.id,
        source: 'self',
        title: s.title,
        runId: null,
        sampleId: null,
        gate: null,
        link: null,
        createdAt: s.createdAt,
        isSelf: true,
        read: m.read ?? true,
        flagged: m.flagged ?? false,
        priority: m.priority ?? 'none',
        column: m.column ?? 'inbox',
        due: m.due ?? null,
        note: m.note ?? '',
      }
    })
    // Newest first — self reminders and tickets interleaved by creation time.
    return [...derived, ...selves].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
  }, [tickets, selfItems, overlay])

  // Unread = not yet read and not archived (the "done" column is the archive). This drives the bell.
  const unreadCount = useMemo(() => items.filter((i) => !i.read && i.column !== 'done').length, [items])

  const patch = useCallback((id: string, meta: ItemMeta) => {
    setOverlay((prev) => ({ ...prev, [id]: { ...prev[id], ...meta } }))
  }, [])

  const markRead = useCallback((id: string, read = true) => patch(id, { read }), [patch])
  const markAllRead = useCallback(() => {
    setOverlay((prev) => {
      const next = { ...prev }
      for (const i of items) if (!i.read) next[i.id] = { ...next[i.id], read: true }
      return next
    })
  }, [items])
  const toggleFlag = useCallback(
    (id: string) => {
      const cur = items.find((i) => i.id === id)
      patch(id, { flagged: !(cur?.flagged ?? false) })
    },
    [items, patch],
  )
  const setPriority = useCallback((id: string, priority: InboxPriority) => patch(id, { priority }), [patch])
  const setColumn = useCallback(
    (id: string, column: InboxColumn) => {
      // Moving onto the board (or to done) implies you've seen it, so mark read too.
      patch(id, { column, read: true })
    },
    [patch],
  )
  const setDue = useCallback((id: string, due: string | null) => patch(id, { due }), [patch])
  const setNote = useCallback((id: string, note: string) => patch(id, { note }), [patch])

  const addSelfItem = useCallback(
    (title: string, opts?: { due?: string | null; note?: string }) => {
      const t = title.trim()
      if (!t) return
      const id = `self:${crypto.randomUUID()}`
      setSelfItems((prev) => [{ id, title: t, createdAt: new Date().toISOString() }, ...prev])
      if (opts?.due || opts?.note) patch(id, { due: opts.due ?? null, note: opts.note ?? '' })
    },
    [patch],
  )
  const deleteSelfItem = useCallback((id: string) => {
    setSelfItems((prev) => prev.filter((s) => s.id !== id))
    setOverlay((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
  }, [])

  const value: InboxState = {
    items,
    unreadCount,
    loading,
    error,
    refresh,
    markRead,
    markAllRead,
    toggleFlag,
    setPriority,
    setColumn,
    setDue,
    setNote,
    addSelfItem,
    deleteSelfItem,
  }
  return <InboxContext.Provider value={value}>{children}</InboxContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useInbox(): InboxState {
  const ctx = useContext(InboxContext)
  if (!ctx) throw new Error('useInbox must be used within <InboxProvider>')
  return ctx
}
