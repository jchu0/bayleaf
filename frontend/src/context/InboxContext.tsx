import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { DEMO_ACCOUNTS } from '../auth'
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

// IB4 — per-reminder notification config. Channels reuse the names the backend notify port already
// speaks (Slack/Teams via ADR-0010) + email; the actual per-reminder ping is a labelled demo seam.
// `leads` are how-far-ahead reminders fire, capped at 3 instances.
export type NotifyChannel = 'slack' | 'teams' | 'discord' | 'email'
export type NotifyCadence = 'once' | 'daily' | 'weekdays'
export type InboxNotify = { channels: NotifyChannel[]; cadence: NotifyCadence; leads: string[] }
export const MAX_LEADS = 3

// IB14 — a kanban card comment (UIC-14). Author is the ACTING operator at write time (snapshotted so
// a later roster edit can't rewrite history); `mentions` are the roster ids @-mentioned in the body,
// resolved on write. Like the rest of this context it persists per-operator to localStorage — so
// mentions are a labelled DEMO seam (a real ping to the mentioned user needs a shared server store),
// never a live notification. Off the gate: a comment never sets or reads a verdict/confidence.
export type InboxComment = {
  id: string
  authorId: string
  authorName: string
  body: string
  createdAt: string
  mentions: string[]
}

// The user-owned mutable state for a single item (both derived tickets and self-authored items).
// Every field is optional — an absent overlay means "untouched", so defaults come from the base.
type ItemMeta = {
  read?: boolean
  flagged?: boolean
  priority?: InboxPriority
  column?: InboxColumn
  due?: string | null // yyyy-mm-dd, or null
  note?: string
  folder?: string | null // IB8 — the notes folder this item is filed under
  notify?: InboxNotify | null // IB4 — per-reminder notification config
  assignee?: string | null // IB14 — roster id this card is assigned to (UIC-14), or null
}

// A self-authored reminder — the immutable creation record; its mutable state lives in the overlay
// like any other item, so flag/priority/column/due/note all work uniformly. `updatedAt` is set on
// an explicit edit (IB6) so a note can show when it was last modified vs. created.
type SelfRaw = { id: string; title: string; createdAt: string; updatedAt?: string }

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
  updatedAt: string | null
  isSelf: boolean
  // resolved overlay (base default ⋈ user overlay):
  read: boolean
  flagged: boolean
  priority: InboxPriority
  column: InboxColumn
  due: string | null
  note: string
  folder: string | null
  notify: InboxNotify | null
  assignee: string | null
}

type InboxState = {
  items: InboxItem[]
  unreadCount: number
  folders: string[]
  comments: Record<string, InboxComment[]> // IB14 — keyed by item id
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  markRead: (id: string, read?: boolean) => void
  markAllRead: () => void
  markAllUnread: () => void
  toggleFlag: (id: string) => void
  setPriority: (id: string, p: InboxPriority) => void
  setColumn: (id: string, c: InboxColumn) => void
  setDue: (id: string, due: string | null) => void
  setNote: (id: string, note: string) => void
  setNotify: (id: string, notify: InboxNotify | null) => void
  setAssignee: (id: string, assignee: string | null) => void // IB14 — wire assignment to the roster
  addComment: (id: string, body: string) => void // IB14 — comment (mentions resolved from body)
  deleteComment: (id: string, commentId: string) => void
  resolveTicket: (id: string) => Promise<void> // close a ticket-derived card (audited server-side)
  addSelfItem: (title: string, opts?: { due?: string | null; note?: string; folder?: string | null }) => void
  updateSelfItem: (id: string, patch: { title?: string; note?: string }) => void
  deleteSelfItem: (id: string) => void
  setFolder: (id: string, folder: string | null) => void
  addFolder: (name: string) => void
  renameFolder: (from: string, to: string) => void
  deleteFolder: (name: string) => void
}

const PRIORITY_FROM_TICKET: Record<string, InboxPriority> = { high: 'high', medium: 'med', low: 'low' }

function overlayKey(actorId: string): string {
  return `pipeguard.inbox.overlay.${actorId}`
}
function selfKey(actorId: string): string {
  return `pipeguard.inbox.self.${actorId}`
}
function folderKey(actorId: string): string {
  return `pipeguard.inbox.folders.${actorId}`
}
function commentsKey(actorId: string): string {
  return `pipeguard.inbox.comments.${actorId}`
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
  const [folders, setFolders] = useState<string[]>(() => loadJson(folderKey(actorId), []))
  const [comments, setComments] = useState<Record<string, InboxComment[]>>(() => loadJson(commentsKey(actorId), {}))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Re-read the per-operator overlay + self items + folders whenever the acting operator changes
  // (Admin's "Act as" swaps identity), so each person sees their own triage state, not a shared one.
  useEffect(() => {
    setSelfItems(loadJson(selfKey(actorId), []))
    setOverlay(loadJson(overlayKey(actorId), {}))
    setFolders(loadJson(folderKey(actorId), []))
    setComments(loadJson(commentsKey(actorId), {}))
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
  useEffect(() => {
    try {
      localStorage.setItem(folderKey(actorId), JSON.stringify(folders))
    } catch {
      /* see above */
    }
  }, [folders, actorId])
  useEffect(() => {
    try {
      localStorage.setItem(commentsKey(actorId), JSON.stringify(comments))
    } catch {
      /* see above */
    }
  }, [comments, actorId])

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
        updatedAt: null,
        isSelf: false,
        read: m.read ?? false,
        flagged: m.flagged ?? false,
        priority: m.priority ?? PRIORITY_FROM_TICKET[t.priority] ?? 'none',
        column: m.column ?? 'inbox',
        due: m.due ?? null,
        note: m.note ?? '',
        folder: m.folder ?? null,
        notify: m.notify ?? null,
        assignee: m.assignee ?? null,
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
        updatedAt: s.updatedAt ?? null,
        isSelf: true,
        read: m.read ?? true,
        flagged: m.flagged ?? false,
        priority: m.priority ?? 'none',
        column: m.column ?? 'inbox',
        due: m.due ?? null,
        note: m.note ?? '',
        folder: m.folder ?? null,
        notify: m.notify ?? null,
        assignee: m.assignee ?? null,
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
  // IB2: the inverse — flip every non-archived item back to unread.
  const markAllUnread = useCallback(() => {
    setOverlay((prev) => {
      const next = { ...prev }
      for (const i of items) if (i.read && i.column !== 'done') next[i.id] = { ...next[i.id], read: false }
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
  const setFolder = useCallback((id: string, folder: string | null) => patch(id, { folder }), [patch])
  const setNotify = useCallback((id: string, notify: InboxNotify | null) => patch(id, { notify }), [patch])
  // IB14: assign the card to a roster id (or clear). Assignment is user-system state, not a verdict —
  // it rides the same per-item overlay as flag/priority/column so it persists + survives a re-fetch.
  const setAssignee = useCallback((id: string, assignee: string | null) => patch(id, { assignee }), [patch])

  // IB14: append a comment authored by the ACTING operator. Mentions are resolved from the body here
  // (single source of truth) against the demo roster; an @token that isn't a real account is ignored.
  const addComment = useCallback(
    (id: string, body: string) => {
      const text = body.trim()
      if (!text) return
      const mentions = [...new Set([...text.matchAll(/@([a-z0-9._-]+)/gi)].map((mm) => mm[1]))].filter((h) =>
        DEMO_ACCOUNTS.some((a) => a.id === h),
      )
      const acct = DEMO_ACCOUNTS.find((a) => a.id === actorId)
      const comment: InboxComment = {
        id: `c:${crypto.randomUUID()}`,
        authorId: actorId,
        authorName: acct?.name ?? actorId,
        body: text,
        createdAt: new Date().toISOString(),
        mentions,
      }
      setComments((prev) => ({ ...prev, [id]: [...(prev[id] ?? []), comment] }))
    },
    [actorId],
  )
  const deleteComment = useCallback((id: string, commentId: string) => {
    setComments((prev) => {
      const list = prev[id]
      if (!list) return prev
      const next = list.filter((c) => c.id !== commentId)
      const copy = { ...prev }
      // Drop the key entirely when the last comment goes, so the store doesn't accrete empty arrays.
      if (next.length) copy[id] = next
      else delete copy[id]
      return copy
    })
  }, [])

  // Resolve a review-queue-derived card straight from the Inbox. `id` is the item's REAL backend
  // ticket id — a derived item's id IS the ticket id from listTickets (shortItemId is display-only) —
  // so the close lands on the right ticket. It's an audited server-side write; refresh then re-pulls
  // the open/in-review feed, dropping the now-resolved ticket so its card leaves the board columns.
  const resolveTicket = useCallback(
    async (id: string) => {
      await api.ticketAction(id, 'resolve')
      await refresh()
    },
    [refresh],
  )

  const addSelfItem = useCallback(
    (title: string, opts?: { due?: string | null; note?: string; folder?: string | null }) => {
      const t = title.trim()
      if (!t) return
      const id = `self:${crypto.randomUUID()}`
      setSelfItems((prev) => [{ id, title: t, createdAt: new Date().toISOString() }, ...prev])
      if (opts?.due || opts?.note || opts?.folder) {
        patch(id, { due: opts.due ?? null, note: opts.note ?? '', folder: opts.folder ?? null })
      }
    },
    [patch],
  )
  // IB5/IB6: edit a self item's title/note behind an explicit Save, stamping updatedAt so the note
  // can show "edited …". A note lives in the overlay; a title lives on the SelfRaw record.
  const updateSelfItem = useCallback(
    (id: string, patchIn: { title?: string; note?: string }) => {
      if (patchIn.title !== undefined) {
        const t = patchIn.title.trim()
        setSelfItems((prev) =>
          prev.map((s) => (s.id === id ? { ...s, title: t || s.title, updatedAt: new Date().toISOString() } : s)),
        )
      } else {
        // A note-only edit still bumps updatedAt on the record so the timestamp reflects it.
        setSelfItems((prev) => prev.map((s) => (s.id === id ? { ...s, updatedAt: new Date().toISOString() } : s)))
      }
      if (patchIn.note !== undefined) patch(id, { note: patchIn.note })
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

  // IB8: folders to file notes under. Renaming/deleting a folder re-points any item filed in it
  // (delete → back to "Unfiled"), so a filed note is never orphaned to a folder that's gone.
  const addFolder = useCallback((name: string) => {
    const n = name.trim()
    if (!n) return
    setFolders((prev) => (prev.includes(n) ? prev : [...prev, n]))
  }, [])
  const renameFolder = useCallback((from: string, to: string) => {
    const t = to.trim()
    if (!t || from === t) return
    setFolders((prev) => prev.map((f) => (f === from ? t : f)))
    setOverlay((prev) => {
      const next: Record<string, ItemMeta> = {}
      for (const [k, v] of Object.entries(prev)) next[k] = v.folder === from ? { ...v, folder: t } : v
      return next
    })
  }, [])
  const deleteFolder = useCallback((name: string) => {
    setFolders((prev) => prev.filter((f) => f !== name))
    setOverlay((prev) => {
      const next: Record<string, ItemMeta> = {}
      for (const [k, v] of Object.entries(prev)) next[k] = v.folder === name ? { ...v, folder: null } : v
      return next
    })
  }, [])

  const value: InboxState = {
    items,
    unreadCount,
    folders,
    comments,
    loading,
    error,
    refresh,
    markRead,
    markAllRead,
    markAllUnread,
    toggleFlag,
    setPriority,
    setColumn,
    setDue,
    setNote,
    setNotify,
    setAssignee,
    addComment,
    deleteComment,
    resolveTicket,
    addSelfItem,
    updateSelfItem,
    deleteSelfItem,
    setFolder,
    addFolder,
    renameFolder,
    deleteFolder,
  }
  return <InboxContext.Provider value={value}>{children}</InboxContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useInbox(): InboxState {
  const ctx = useContext(InboxContext)
  if (!ctx) throw new Error('useInbox must be used within <InboxProvider>')
  return ctx
}
