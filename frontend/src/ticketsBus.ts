// UX-DUP (Review + Inbox #1): a tiny shared invalidation bus that ends the ticket STATUS drift
// between the Review queue and the Inbox. Both surfaces write ticket status to the SAME backend
// (/api/review/tickets), but each held its OWN client cache — so a resolve/escalate/assign in the
// queue left the Inbox (a long-lived context that wraps the router and never remounts) showing the
// ticket as still open until a manual refresh (the drift the UX review names as the headline bug).
//
// The backend is the one source of truth for ticket status; this bus carries NO ticket data and owns
// NO status — it is PURE invalidation ("tickets changed on the backend, re-read them"). That is the
// safest option available: it never touches the queue's optimistic overlay / syncAction / selection
// (those invariants are preserved byte-for-byte); it only lets a stale long-lived consumer re-fetch.
//
// Direction: the Review queue (a screen that remounts each visit) announces its writes; the Inbox
// context (always mounted) subscribes and re-reads. The reverse — an Inbox resolve reflecting in the
// queue — needs no announcement: the queue re-reads from the same backend the next time you open it
// (it remounts), so both directions converge on backend truth.
//
// Framework-agnostic (no React import), mirroring the module-singleton idiom of useApiHealth /
// useRuns; consumers subscribe from an effect.

const listeners = new Set<() => void>()

// Coalesce a burst of writes (e.g. a batch-resolve of N tickets, each firing on its own settled
// write) into ONE notification, so N status writes cause ONE re-fetch, not N — scale-friendly for
// the 100+-sample flowcells this app targets. Trailing debounce: the first bump schedules the fire,
// bumps within the window are absorbed, and any bump completing before the fire is reflected because
// the re-fetch reads the authoritative backend (never a missed update — at worst a slightly later one).
const COALESCE_MS = 250
let timer: number | null = null

// Announce that ticket status changed on the backend. Call AFTER a successful write.
export function bumpTickets(): void {
  if (timer != null) return
  timer = window.setTimeout(() => {
    timer = null
    for (const fn of listeners) fn()
  }, COALESCE_MS)
}

// Subscribe to ticket-change announcements; returns an unsubscribe fn for an effect cleanup.
export function onTicketsChanged(fn: () => void): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}
