import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Check,
  CheckCircle2,
  ChevronRight,
  ChevronUp,
  EyeOff,
  FileText,
  Lock,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  User,
} from 'lucide-react'
import { api } from '../api'
import { DEMO_ACCOUNTS } from '../auth'
import { PageHeader } from '../components/PageHeader'
import { Pager, type PerPage } from '../components/Pager'
import { ReviewRepairCard, type RepairApproval } from '../components/ReviewRepairCard'
import { ReviewStatusBar, type ReviewStatusSegment } from '../components/ReviewStatusBar'
import { Tabs } from '../components/Tabs'
import { ErrorBox, Loading } from '../components/States'
import { useToast } from '../components/Toast'
import { useConfirm, type ConfirmOpts } from '../components/ConfirmDialog'
import { useRole } from '../context/RoleContext'
import { useAccess } from '../context/AccessContext'
import { useRangeSelect } from '../hooks/useRangeSelect'
import { bumpTickets } from '../ticketsBus'
import type {
  AgentProposal,
  DecisionCard,
  Finding,
  Gate,
  ReviewActionName,
  RunDetail,
  Ticket,
  TicketIn,
  TicketPriority,
  TicketStatus,
  Verdict,
} from '../types'
import { GATE_DOT, GATE_LABEL, VERDICT_BADGE, VERDICT_DOT, VERDICT_LABEL, VERDICT_ORDER } from '../verdict'

// Priority is derived from the verdict, not stored — escalations/reruns block a run, holds
// are judgment calls. `bars` = filled count in the ascending signal glyph.
const PRIORITY: Record<Verdict, { label: string; bars: number }> = {
  escalate: { label: 'High', bars: 3 },
  rerun: { label: 'High', bars: 3 },
  hold: { label: 'Medium', bars: 2 },
  proceed: { label: 'Low', bars: 1 },
}

// Verdict → wire priority, for the ticket materialized on first action (createTicket).
const TICKET_PRIORITY: Record<Verdict, TicketPriority> = {
  escalate: 'high',
  rerun: 'high',
  hold: 'medium',
  proceed: 'low',
}

const STATUS_META: Record<TicketStatus, { label: string; dot: string; chip: string }> = {
  open: { label: 'Open', dot: 'bg-info', chip: 'border-line bg-card-2 text-text-2' },
  in_review: { label: 'In review', dot: 'bg-accent', chip: 'border-accent-weak bg-accent-weak text-accent-strong' },
  resolved: { label: 'Resolved', dot: 'bg-proceed', chip: 'border-proceed-bd bg-proceed-bg text-proceed-fg' },
}

// Status is a partition (a ticket is in exactly one) — no catch-all "All" peer (decision A): the
// queue defaults to Open (the actionable set), In review / Resolved are their own tabs, and a
// SEARCH escapes the status facet to span every status (below). "all" survives only as the
// internal "no status filter" sentinel a search sets — never a tab.
const STATUS_FILTERS: { key: 'all' | TicketStatus; label: string }[] = [
  { key: 'open', label: 'Open' },
  { key: 'in_review', label: 'In review' },
  { key: 'resolved', label: 'Resolved' },
]

// Resolved-tab recency window (task 4). The Resolved tab defaults to recently-opened resolved
// tickets so a long history never floods the view; the full count comes from the backend
// X-PipeGuard-Ticket-Total header, and "Show all resolved" (or a search) drops the window.
const RESOLVED_WINDOW_DAYS = 30

// The `since` value for the resolved window — an ISO date N days back (the backend filters
// created_at >= since; string-comparable because both are zero-padded ISO).
function sinceIso(daysBack: number): string {
  const d = new Date()
  d.setDate(d.getDate() - daysBack)
  return d.toISOString().slice(0, 10)
}

// A ticket derived from a flagged card (recurrence + issue class stay frontend-derived per the
// data contract — they are NOT wire fields on Ticket).
type QueueTicket = { runId: string; runDate: string | null; card: DecisionCard; primary: Finding; gate: Gate }

// Per-ticket UI state layered over the derived ticket: seeded from any matching server ticket on
// load, then overwritten by the operator's actions (optimistic; the wire write is best-effort).
type TicketUi = {
  serverId?: string
  status?: TicketStatus
  assignee?: string | null
  escalated?: boolean
  suppressed?: boolean
  resolvedBy?: string
  repairEscalated?: boolean
  repairLoading?: boolean
  repairProposal?: AgentProposal | null
  repairApproved?: RepairApproval
}

// Cross-run recurrence for the "seen N× in <window>" banner — derived on the client from the
// findings' rule_id (the issue *class*), never a wire field.
type Recurrence = { count: number; runIds: string[]; window: string; runsLabel: string }

function keyOf(t: QueueTicket): string {
  return `${t.runId}|${t.card.sample_id}`
}

// The flagged gate + the finding driving this ticket (the one matching the verdict's gate, else
// the most-severe). Mirrors the gate's own selection in RunDetail's flagged chip.
function primaryFinding(card: DecisionCard): { primary: Finding; gate: Gate } | null {
  if (card.findings.length === 0) return null
  const gr = card.gate_results.find((g) => g.verdict === card.verdict) ?? card.gate_results[0]
  const primary = (gr && card.findings.find((f) => f.gate === gr.gate)) ?? card.findings[0]
  return { primary, gate: primary.gate }
}

// Stable per-card label until a server ticket id exists: fold the content hash into T-####.
function ticketLabel(card: DecisionCard): string {
  const seed = Number.parseInt(card.content_hash.slice(0, 6), 16)
  return `T-${(seed % 9000) + 1000}`
}

function ticketInFrom(t: QueueTicket): TicketIn {
  return {
    run_id: t.runId,
    sample_id: t.card.sample_id,
    gate: t.gate,
    verdict: t.card.verdict,
    rule_id: t.primary.rule_id,
    title: t.card.headline,
    priority: TICKET_PRIORITY[t.card.verdict],
  }
}

// Server ticket → initial UI slice. Escalated/suppressed are read back from the action log;
// resolvedBy from the most-recent resolve.
function uiFromServer(t: Ticket): TicketUi {
  return {
    serverId: t.id,
    status: t.status,
    assignee: t.assignee ?? null,
    escalated: t.actions.some((a) => a.action === 'escalate'),
    suppressed: t.actions.some((a) => a.action === 'suppress'),
    resolvedBy: [...t.actions].reverse().find((a) => a.action === 'resolve')?.actor,
  }
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

// Honest resolution copy: resolving a ticket records that a reviewer/approver cleared it — it
// does NOT run a rerun or re-measure a metric (compose != execute), so we never assert a QC
// outcome that did not occur. The rerun line is a next-step, not a fabricated result.
function resolutionNote(verdict: Verdict): string {
  // A rerun is a manual next-step, not a control here: the sample must be re-submitted under a NEW
  // run id (both run endpoints 409 on a duplicate id), so we describe the action, never imply a
  // one-click requeue button that doesn't exist.
  if (verdict === 'rerun') return 'Re-run the sample under a new run id, then resolve this ticket.'
  if (verdict === 'escalate') return 'Escalation signed off by an approver.'
  return 'Cleared after manual review.'
}

// Ascending 3-bar signal glyph — filled to `level`.
function PriorityBars({ level }: { level: number }) {
  return (
    <span className="inline-flex items-end gap-[2px]" aria-hidden>
      {[1, 2, 3].map((i) => (
        <span
          key={i}
          className={`w-[3px] rounded-[1px] ${i <= level ? 'bg-text-2' : 'bg-line-strong'}`}
          style={{ height: 3 + i * 2 }}
        />
      ))}
    </span>
  )
}

export function ReviewQueue() {
  const { actor, isReviewer, isApprover } = useRole()
  const { canSee } = useAccess()
  const { toast } = useToast()
  const confirm = useConfirm()
  const [details, setDetails] = useState<RunDetail[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ui, setUi] = useState<Record<string, TicketUi>>({})
  // Default to Open so resolved (and in-review) tickets leave the active list but stay reachable via
  // their facet chip (part c) — resolved is still a searchable TicketStatus, never dropped.
  const [filter, setFilter] = useState<'all' | TicketStatus>('open')
  const [perPage, setPerPage] = useState<PerPage>('25')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<Record<string, boolean>>({})
  // Free-text search (task 2) over the loaded tickets — run id / sample id / rule id / title /
  // verdict, case-insensitive. Client-side over the derived set; resets the page on change.
  const [search, setSearch] = useState('')
  // Resolved-tab windowing (task 4): default to the recent window; the header total + "Show all"
  // let an operator reach the full history without loading it up front on every tab.
  const [showAllResolved, setShowAllResolved] = useState(false)
  const [resolvedTotal, setResolvedTotal] = useState<number | null>(null)
  const [recentResolvedKeys, setRecentResolvedKeys] = useState<Set<string>>(new Set())
  // True once the recent-resolved window loaded — so a failed window fetch falls back to showing ALL
  // resolved rather than an empty (misleading) Resolved tab.
  const [resolvedWindowLoaded, setResolvedWindowLoaded] = useState(false)
  const seededRef = useRef(false)
  // Per-key sync de-dup state (see syncAction): a synchronous server-id map + an in-flight
  // promise chain so a rapid double-action materializes exactly one server ticket.
  const serverIdRef = useRef<Record<string, string>>({})
  const pendingRef = useRef<Record<string, Promise<void>>>({})

  // Latest ui, read inside async write handlers without a stale closure.
  const uiRef = useRef(ui)
  useEffect(() => {
    uiRef.current = ui
  }, [ui])

  useEffect(() => {
    let alive = true
    Promise.all([
      api.runs().then((runs) => Promise.all(runs.map((r) => api.run(r.run_id)))),
      // ALL server tickets hydrate status/assignee/escalation — the full set is needed for status
      // correctness across tabs (an un-hydrated resolved ticket would misread as open). Empty (or
      // unreachable) is fine: the queue is derived from flagged cards either way.
      api.listTickets().catch(() => [] as Ticket[]),
      // The recent RESOLVED window + the authoritative system-wide resolved total (task 4). The
      // total comes from the X-PipeGuard-Ticket-Total header (ignores `since`); `data` names which
      // resolved tickets are recent enough to show by default. Unreachable → no window (show all).
      api
        .listTicketsPage({ status: 'resolved', since: sinceIso(RESOLVED_WINDOW_DAYS) })
        .then((p) => ({ ...p, ok: true }))
        .catch(() => ({ data: [] as Ticket[], total: null, ok: false })),
    ])
      .then(([ds, sts, resolvedPage]) => {
        if (!alive) return
        setDetails(ds)
        const init: Record<string, TicketUi> = {}
        for (const st of sts) init[`${st.run_id}|${st.sample_id}`] = uiFromServer(st)
        setUi(init)
        setResolvedTotal(resolvedPage.total)
        setRecentResolvedKeys(new Set(resolvedPage.data.map((t) => `${t.run_id}|${t.sample_id}`)))
        setResolvedWindowLoaded(resolvedPage.ok)
      })
      .catch((e) => alive && setError(String(e)))
    return () => {
      alive = false
    }
  }, [])

  const { tickets, recurrence } = useMemo(() => {
    // Recurrence is keyed on the issue *class* (rule_id), not the content signature: the banner
    // surfaces a class recurring across runs, which drives the fix-one vs. fix-class repair
    // scopes. Observation-specific signatures never dedupe, so they'd never trip the banner.
    const acc = new Map<string, { count: number; runIds: string[]; dates: (string | null)[] }>()
    const list: QueueTicket[] = []
    if (details) {
      for (const d of details) {
        for (const c of d.cards) {
          for (const f of c.findings) {
            const cur = acc.get(f.rule_id) ?? { count: 0, runIds: [], dates: [] }
            cur.count += 1
            if (!cur.runIds.includes(d.run_id)) {
              cur.runIds.push(d.run_id)
              cur.dates.push(d.summary.run_date)
            }
            acc.set(f.rule_id, cur)
          }
          if (c.verdict === 'proceed') continue
          const pf = primaryFinding(c)
          if (!pf) continue
          list.push({ runId: d.run_id, runDate: d.summary.run_date, card: c, primary: pf.primary, gate: pf.gate })
        }
      }
      list.sort((a, b) => VERDICT_ORDER[a.card.verdict] - VERDICT_ORDER[b.card.verdict])
    }
    const rec = new Map<string, Recurrence>()
    for (const [ruleId, v] of acc) {
      const ms = v.dates.map((x) => (x ? new Date(x).getTime() : NaN)).filter((n) => !Number.isNaN(n))
      const windowLabel =
        ms.length >= 2 ? `${Math.max(1, Math.round((Math.max(...ms) - Math.min(...ms)) / 86400000))}d` : 'recent runs'
      const runsLabel =
        v.runIds.slice(0, 3).join(', ') + (v.runIds.length > 3 ? ` +${v.runIds.length - 3}` : '')
      rec.set(ruleId, { count: v.count, runIds: v.runIds, window: windowLabel, runsLabel })
    }
    return { tickets: list, recurrence: rec }
  }, [details])

  // One derivation pass (counts → status filter → search → resolved window → pagination → run
  // grouping) so `orderedIds` — the flat top-to-bottom render order of the selectable checkboxes —
  // is computed BEFORE useRangeSelect below, which its shift-range math indexes into (UIC-3.1).
  // Returning statusOf/selectable keeps a single source for the same predicates in the render.
  const view = useMemo(() => {
    const statusOf = (t: QueueTicket): TicketStatus => ui[keyOf(t)]?.status ?? 'open'
    // A ticket is batch-selectable only while awaiting a decision (open/in-review); resolved
    // tickets fall out of the selection so a stale check can't re-fire an action on them.
    const selectable = (t: QueueTicket): boolean => {
      const s = statusOf(t)
      return s === 'open' || s === 'in_review'
    }
    const counts: Record<'all' | TicketStatus, number> = {
      all: tickets.length,
      open: tickets.filter((t) => statusOf(t) === 'open').length,
      in_review: tickets.filter((t) => statusOf(t) === 'in_review').length,
      resolved: tickets.filter((t) => statusOf(t) === 'resolved').length,
    }
    // Case-insensitive substring match across the ticket's identifying fields (task 2).
    const q = search.trim().toLowerCase()
    const matchesSearch = (t: QueueTicket): boolean =>
      q === '' ||
      t.runId.toLowerCase().includes(q) ||
      t.card.sample_id.toLowerCase().includes(q) ||
      t.primary.rule_id.toLowerCase().includes(q) ||
      t.card.headline.toLowerCase().includes(q) ||
      t.card.verdict.toLowerCase().includes(q)
    // The resolved recency window is only active on the Resolved tab, with no search and no
    // "Show all", and only once the window fetch succeeded — a search, "Show all", or a failed
    // window fetch reaches the full history (task 4).
    const windowActive = filter === 'resolved' && !showAllResolved && q === '' && resolvedWindowLoaded
    const inResolvedWindow = (t: QueueTicket): boolean =>
      !windowActive || recentResolvedKeys.has(keyOf(t))
    const shown = tickets.filter(
      // A search escapes the status facet (q !== '' spans every status), so dropping the "All" tab
      // never hides a ticket — you reach any status by searching. Otherwise it's the one active tab.
      (t) => (q !== '' || statusOf(t) === filter) && matchesSearch(t) && inResolvedWindow(t),
    )
    // Client-side pagination over the visible tickets, mirroring Monitoring's recurring-signature
    // pager. Clamp the current page so a narrowing filter can't strand the pager on an empty page.
    const per = Number(perPage)
    const total = shown.length
    const pages = Math.max(1, Math.ceil(total / per))
    const curPage = Math.min(page, pages)
    const fromIdx = total === 0 ? 0 : (curPage - 1) * per + 1
    const toIdx = Math.min(curPage * per, total)
    const pagedTickets = shown.slice((curPage - 1) * per, curPage * per)
    // The flat render order of the SELECTABLE checkboxes on this page — a shift-range spans exactly
    // the open tickets the operator sees (across run groups), never a hidden or resolved row.
    const orderedIds = pagedTickets.filter(selectable).map(keyOf)
    // Group the paginated slice by run so tickets read under their run. The slice is verdict-sorted
    // already; re-sort each group defensively to keep the verdict sort explicit.
    const grouped = new Map<string, QueueTicket[]>()
    for (const t of pagedTickets) {
      const g = grouped.get(t.runId)
      if (g) g.push(t)
      else grouped.set(t.runId, [t])
    }
    const groups = Array.from(grouped.entries())
    for (const [, g] of groups) g.sort((a, b) => VERDICT_ORDER[a.card.verdict] - VERDICT_ORDER[b.card.verdict])
    return { statusOf, selectable, counts, shown, total, pages, curPage, fromIdx, toIdx, pagedTickets, orderedIds, groups, windowActive }
  }, [tickets, ui, filter, perPage, page, search, showAllResolved, recentResolvedKeys, resolvedWindowLoaded])

  // The one app-wide checkbox model (UIC-3): the parent run checkbox drives its children via
  // setMany; sample checkboxes shift-click range-select via toggle(id, shiftKey).
  const rs = useRangeSelect(view.orderedIds)

  // First-open: seed the most-urgent ticket expanded once, the rest collapsed.
  useEffect(() => {
    if (!seededRef.current && tickets.length > 0) {
      seededRef.current = true
      setOpen({ [keyOf(tickets[0])]: true })
    }
  }, [tickets])

  // Reset to page 1 when the filter, per-page, or search changes (mirror Monitoring). Selection is
  // page-scoped — `selectedTickets` resolves against the current page's tickets — so a stale
  // off-page key in the Set is never surfaced or acted on (no clear-on-navigate needed).
  useEffect(() => {
    setPage(1)
  }, [filter, perPage, search])

  if (error) return <ErrorBox message={error} />
  if (!details) return <Loading label="Loading queue…" />

  const patch = (key: string, next: Partial<TicketUi>) =>
    setUi((prev) => ({ ...prev, [key]: { ...prev[key], ...next } }))

  // Restore a key's UI slice to a pre-action snapshot after a rejected wire write, so a 403/409
  // never strands a ticket in a status the server never accepted. Replaces (not merges) the slice
  // so the optimistic transition is fully undone; `serverIdRef` still holds any materialized id, so
  // dropping it from the slice can't re-create the ticket on the next action.
  const restore = (key: string, prev: TicketUi | undefined) =>
    setUi((cur) => {
      const nextMap = { ...cur }
      if (prev === undefined) delete nextMap[key]
      else nextMap[key] = prev
      return nextMap
    })

  // Optimistic local update, then a best-effort wire write (materializing the ticket on first
  // touch). These are off-gate advisory writes — a failed sync keeps the operator's intent
  // on-screen so the demo never stalls, and never touches a rules-decided verdict.
  // Per-key promise chain + the synchronous server-id ref (declared above) so a rapid
  // double-action on a not-yet-persisted ticket materializes exactly ONE server ticket (the
  // second action waits for the first createTicket, then reuses its id) instead of racing two POSTs.
  const syncAction = (t: QueueTicket, action: ReviewActionName, prev: TicketUi | undefined): Promise<void> => {
    const key = keyOf(t)
    const run = async () => {
      let id = serverIdRef.current[key] ?? uiRef.current[key]?.serverId
      if (!id) {
        const created = await api.createTicket(ticketInFrom(t))
        id = created.id
        serverIdRef.current[key] = id
        patch(key, { serverId: id })
      }
      const updated = await api.ticketAction(id, action)
      patch(key, { status: updated.status }) // reconcile from the authoritative response
      // UX-DUP (Review + Inbox #1): announce the backend status change so the always-mounted Inbox
      // context re-reads the ticket feed — a queue resolve/escalate now reflects in the bell + inbox
      // instead of drifting until a manual refresh. Only fires on a SUCCESSFUL write (a throw skips to
      // the rollback in .catch); pure invalidation, so the optimistic overlay/selection are untouched.
      bumpTickets()
    }
    const next = (pendingRef.current[key] ?? Promise.resolve()).then(run).catch((e) => {
      // Roll back the optimistic transition (mirrors PipelineBuilder's reconcile-on-catch) so a
      // rejected write doesn't leave the card reading Resolved/In-review until a manual refetch,
      // then surface the real backend outcome (403/409/…) instead of silently diverging.
      restore(key, prev)
      toast(`Couldn't ${action} ticket — ${errMsg(e)}`, 'error')
    })
    pendingRef.current[key] = next
    return next
  }

  const act = (t: QueueTicket, action: ReviewActionName) => {
    const key = keyOf(t)
    // Snapshot the slice BEFORE the optimistic patch so syncAction can revert to it on a rejected write.
    const prev = uiRef.current[key]
    if (action === 'acknowledge') patch(key, { status: 'in_review' })
    else if (action === 'resolve') patch(key, { status: 'resolved', resolvedBy: actor.id })
    else if (action === 'reopen') patch(key, { status: 'open' })
    else if (action === 'escalate') {
      // Escalating an untouched ticket also moves it into review; an already in-review ticket
      // keeps its status (don't clobber it with undefined).
      const wasOpen = (uiRef.current[key]?.status ?? 'open') === 'open'
      patch(key, wasOpen ? { escalated: true, status: 'in_review' } : { escalated: true })
    } else if (action === 'suppress') patch(key, { suppressed: true })
    void syncAction(t, action, prev)
  }

  const toggleSuppress = (t: QueueTicket) => {
    const key = keyOf(t)
    if (uiRef.current[key]?.suppressed) patch(key, { suppressed: false })
    else act(t, 'suppress')
  }

  // Assign (or unassign, assignee=null) a ticket's owner — the review↔kanban link (task 3). A
  // backend write, materializing the ticket on first touch (same per-key promise chain + server-id
  // ref as syncAction so a rapid assign+action can't race two POSTs). Optimistic, then reconciled
  // from the authoritative response; a low-stakes reversible write, so it toasts rather than
  // confirms. Never a status transition, never a verdict (ADR-0001).
  const assign = (t: QueueTicket, assignee: string | null) => {
    const key = keyOf(t)
    // Snapshot the slice BEFORE the optimistic patch so a rejected write can revert to it (mirrors
    // syncAction) — otherwise a failed assignTicket strands the WRONG owner in the queue overlay,
    // now visibly disagreeing with the Inbox, which re-reads the real backend owner on bumpTickets.
    const prev = uiRef.current[key]
    patch(key, { assignee }) // optimistic
    const run = async () => {
      let id = serverIdRef.current[key] ?? uiRef.current[key]?.serverId
      if (!id) {
        const created = await api.createTicket(ticketInFrom(t))
        id = created.id
        serverIdRef.current[key] = id
        patch(key, { serverId: id })
      }
      const updated = await api.assignTicket(id, assignee)
      patch(key, { assignee: updated.assignee }) // reconcile from the authoritative response
      // Announce the backend assignee change so the Inbox's effective-owner read re-syncs (#1).
      bumpTickets()
      toast(
        assignee ? `Assigned ${t.card.sample_id} to ${assignee}` : `Unassigned ${t.card.sample_id}`,
        'success',
      )
    }
    const next = (pendingRef.current[key] ?? Promise.resolve()).then(run).catch((e) => {
      // Roll back the optimistic assignee on a rejected write (403/409/…), then surface the error —
      // don't leave the wrong owner stranded in the overlay (mirrors syncAction's restore-on-catch).
      restore(key, prev)
      toast(`Couldn't assign ticket — ${errMsg(e)}`, 'error')
    })
    pendingRef.current[key] = next
  }

  // Explicit-confirm gate (maintainer rule: no accidental single click may fire a cascading/
  // state-changing write). Each stakes-y ticket action confirms first, naming its effect + that it's
  // audited; the actions themselves already persist to the review store, which the Admin Activity
  // log reads. Acknowledge stays a direct one-click (a soft "start reviewing", non-destructive).
  const ACTION_CONFIRM: Record<'resolve' | 'reopen', ConfirmOpts> = {
    resolve: {
      title: 'Resolve this ticket?',
      body: 'Marks the hold cleared and moves it out of the open queue. Reversible via Reopen; recorded in the audit log.',
      confirmLabel: 'Resolve',
    },
    reopen: {
      title: 'Reopen this ticket?',
      body: 'Returns a resolved ticket to the open queue. Recorded in the audit log.',
      confirmLabel: 'Reopen',
    },
  }
  const confirmAct = async (t: QueueTicket, action: 'resolve' | 'reopen') => {
    if (!(await confirm(ACTION_CONFIRM[action]))) return
    act(t, action)
  }
  // Acknowledge = start reviewing AND take ownership: picking up an UNOWNED ticket self-assigns it to
  // the acting user, so nothing sits in review without an accountable owner (the orphan-escalation
  // fix starts here). An already-owned ticket keeps its owner.
  const acknowledge = (t: QueueTicket) => {
    const key = keyOf(t)
    if (!uiRef.current[key]?.assignee) assign(t, actor.id)
    act(t, 'acknowledge')
  }
  // Escalate ROUTES the ticket to a specific approver (not a shared pool): assign to the chosen
  // approver, then transition. The UI enables this only once the ticket has an owner; the backend
  // also rejects an unassigned escalate (review_queue.act_on_ticket), so it isn't a UI-only guardrail.
  const confirmEscalate = async (t: QueueTicket, approverId: string) => {
    const target = DEMO_ACCOUNTS.find((a) => a.id === approverId)
    const ok = await confirm({
      title: 'Escalate to an approver?',
      body: `Assigns ${t.card.sample_id} to ${target?.name ?? approverId} for sign-off and moves it into review. Recorded in the audit log.`,
      confirmLabel: 'Escalate',
    })
    if (!ok) return
    assign(t, approverId)
    act(t, 'escalate')
  }
  // Suppress resolves THIS ticket and marks the issue class handled; un-suppressing merely restores
  // visibility (low-stakes), so it toggles straight through. Honesty: class-wide muting of *future*
  // tickets of this rule_id across runs is a documented, not-built seam (review_queue.py) — the copy
  // must not claim a cross-run mute that doesn't exist.
  const confirmSuppress = async (t: QueueTicket) => {
    if (uiRef.current[keyOf(t)]?.suppressed) {
      toggleSuppress(t)
      return
    }
    const ok = await confirm({
      title: 'Suppress this issue class?',
      body: `Resolves this ${t.primary.rule_id} ticket and marks the issue class handled here. It does not mute future occurrences on other runs (cross-run suppression is not built). Recorded in the audit log.`,
      confirmLabel: 'Suppress',
      tone: 'danger',
    })
    if (ok) toggleSuppress(t)
  }

  const escalateRepair = async (t: QueueTicket) => {
    const key = keyOf(t)
    patch(key, { repairEscalated: true, repairLoading: true, repairApproved: 'none' })
    try {
      const proposal = await api.signatureRepair(t.primary.signature)
      patch(key, { repairProposal: proposal, repairLoading: false })
    } catch {
      patch(key, { repairLoading: false })
    }
  }

  const approveFix = (t: QueueTicket, scope: 'instance' | 'class') => {
    if (!isApprover) return
    patch(keyOf(t), { repairApproved: scope })
  }

  // Selection + batch clearance is a reviewer capability (writes); a viewer sees no checkboxes.
  const canSelect = isReviewer
  // Escalation is gated by role AND page access (UIC-10): a viewer can't escalate, and the actor
  // must hold review-queue access. It routes to an Approver who also holds that access.
  const canEscalate = isReviewer && canSee('queue')
  const roleLabel = isApprover ? 'Approver' : isReviewer ? 'Reviewer' : 'Viewer'

  const clearSelection = () => rs.clear()
  // Global select-all / clear-all (UIC-3.2) over the selectable tickets on the CURRENT page — scoped
  // to the page so it never silently selects tickets you can't see (a surprising batch count).
  const pageSelectableKeys = view.pagedTickets.filter(view.selectable).map(keyOf)
  const allShownSelected = rs.allSelected(pageSelectableKeys)
  const selectAllShown = () => rs.setMany(pageSelectableKeys, !allShownSelected)
  // Resolve against the live paged tickets so keys that have since left the selectable set (already
  // resolved) never drive a batch action.
  const selectedTickets = view.pagedTickets.filter((t) => rs.isSelected(keyOf(t)) && view.selectable(t))
  // Batch resolve only — the sole batch action now that view-only "clear" is gone (task 1). Suppress
  // stays a deliberate per-ticket, single-issue-class decision, never a bulk sweep.
  const batchResolve = async () => {
    const n = selectedTickets.length
    if (n === 0) return
    // Batch resolve is the biggest cascading-click risk (N tickets at once) — always confirm.
    const ok = await confirm({
      title: `Resolve ${n} selected ticket${n === 1 ? '' : 's'}?`,
      body: 'Clears every selected hold at once. Reversible per-ticket via Reopen; each is recorded in the audit log.',
      confirmLabel: 'Resolve selected',
    })
    if (!ok) return
    for (const t of selectedTickets) act(t, 'resolve')
    clearSelection()
  }

  const segments: ReviewStatusSegment[] = [
    { verdict: 'escalate', label: 'Escalations', count: tickets.filter((t) => t.card.verdict === 'escalate').length },
    { verdict: 'rerun', label: 'Reruns', count: tickets.filter((t) => t.card.verdict === 'rerun').length },
    { verdict: 'hold', label: 'Holds', count: tickets.filter((t) => t.card.verdict === 'hold').length },
  ]

  const expandAll = () => setOpen(Object.fromEntries(tickets.map((t) => [keyOf(t), true])))
  const collapseAll = () => setOpen({})

  return (
    <div className="mx-auto max-w-[1080px]">
      {/* UIC-1: nav names the page — no eyebrow/subtitle prose. */}
      <PageHeader title="Review queue" />

      {/* RBAC context — reads the shared RoleContext + page access (a demo toggle in the user panel);
          the copy tracks the current role so what you can do here is never ambiguous. */}
      <div className="mt-1 flex items-start gap-2.5 rounded-xl border border-line bg-card px-[14px] py-[11px] shadow-card">
        <span className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-lg bg-accent-weak">
          <ShieldCheck size={16} className="text-accent" />
        </span>
        <p className="text-[12.5px] leading-snug text-text-2">
          Signed in as <span className="font-mono text-text">{actor.id}</span> ·{' '}
          <span className="font-semibold text-text">{roleLabel}</span>.{' '}
          {isApprover ? (
            <>You can resolve holds, reruns, and escalations.</>
          ) : isReviewer ? (
            <>
              You can resolve holds and reruns, and escalate to an{' '}
              <span className="font-semibold text-text">Approver</span> — resolving an{' '}
              <span className="font-semibold text-escalate-fg">escalation</span> needs one.
            </>
          ) : (
            <>
              You can review the queue, but acknowledging, resolving, or{' '}
              <span className="font-semibold text-text">escalating</span> a ticket needs a{' '}
              <span className="font-semibold text-text">Reviewer</span> or{' '}
              <span className="font-semibold text-text">Approver</span>.
            </>
          )}
        </p>
      </div>

      {tickets.length > 0 && <ReviewStatusBar segments={segments} />}

      {/* Status views as tabs (G5) — reads as a view selector, not highlighted values. */}
      <div className="mt-4">
        <Tabs<'all' | TicketStatus>
          items={STATUS_FILTERS.map((f) => ({ value: f.key, label: f.label, count: view.counts[f.key] }))}
          value={filter}
          onChange={setFilter}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {/* Search (task 2) — filters the loaded tickets by run / sample / rule / title / verdict. */}
        <div className="relative">
          <Search
            size={14}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-text-3"
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search run, sample, rule, verdict…"
            aria-label="Search tickets"
            className="h-8 w-[240px] max-w-full rounded-lg border border-line bg-card pl-8 pr-2 text-[12.5px] text-text placeholder:text-text-3 focus:border-accent focus:outline-none"
          />
        </div>
        {/* Global select-all / clear-all for the selection checkboxes (UIC-3.2), reviewers only. */}
        {canSelect && pageSelectableKeys.length > 0 && (
          <button
            type="button"
            onClick={selectAllShown}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-[11px] py-1.5 text-[12px] text-text-2 transition-colors hover:border-accent hover:text-accent-strong"
          >
            <span className={`grid h-3.5 w-3.5 place-items-center rounded-[3px] border ${allShownSelected ? 'border-accent bg-accent text-white' : 'border-line-strong bg-card'}`}>
              {allShownSelected && <Check size={11} strokeWidth={3} />}
            </span>
            {allShownSelected ? 'Clear all' : 'Select all'}
          </button>
        )}
        {canSelect && selectedTickets.length > 0 && (
          <button
            type="button"
            onClick={clearSelection}
            className="rounded-lg px-2 py-1.5 text-[12px] text-text-3 transition-colors hover:text-text-2"
          >
            Clear selection ({selectedTickets.length})
          </button>
        )}
        <div className="min-w-3 flex-1" />
        <button
          type="button"
          onClick={expandAll}
          className="rounded-lg border border-line-strong bg-card px-[11px] py-1.5 text-[12px] text-text-2 transition-colors hover:text-text"
        >
          Expand all
        </button>
        <button
          type="button"
          onClick={collapseAll}
          className="rounded-lg border border-line-strong bg-card px-[11px] py-1.5 text-[12px] text-text-2 transition-colors hover:text-text"
        >
          Collapse all
        </button>
      </div>

      {/* Resolved-tab window meta (task 4): the true total (from the X-PipeGuard-Ticket-Total
          header, or the derived count as a fallback) + a toggle between the recent window and the
          full history. A search already reaches the full history, so the toggle hides while searching. */}
      {filter === 'resolved' && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-text-3">
          <span>
            {resolvedTotal ?? view.counts.resolved} resolved total
            {view.windowActive && ` · showing the last ${RESOLVED_WINDOW_DAYS} days`}
          </span>
          {resolvedWindowLoaded && !search.trim() && (
            <button
              type="button"
              onClick={() => setShowAllResolved((v) => !v)}
              className="rounded-lg border border-line-strong bg-card px-2.5 py-1 text-[11.5px] text-text-2 transition-colors hover:border-accent hover:text-accent-strong"
            >
              {showAllResolved ? `Show recent (${RESOLVED_WINDOW_DAYS}d)` : 'Show all resolved'}
            </button>
          )}
        </div>
      )}

      {view.shown.length === 0 ? (
        <div className="mt-4 flex flex-col items-center gap-2.5 rounded-[13px] border border-dashed border-line-strong bg-card px-6 py-10 text-center">
          <span className="flex h-[46px] w-[46px] items-center justify-center rounded-xl bg-proceed-bg">
            <CheckCircle2 size={23} className="text-proceed" />
          </span>
          <p className="text-[15px] font-semibold text-text">
            {search.trim() ? 'No matches' : 'Queue clear'}
          </p>
          <p className="text-[13px] text-text-2">
            {search.trim()
              ? 'No tickets match your search.'
              : filter === 'all'
                ? 'Nothing needs review right now. Nice work.'
                : `No ${STATUS_META[filter].label.toLowerCase()} tickets in this view.`}
          </p>
        </div>
      ) : (
        <>
          {/* Batch resolve bar: appears once ≥1 open/in-review ticket is selected. Sits above the
              per-run sticky subheaders (z-20) so it stays reachable while scrolling. Reuses the same
              backend-persisted act('resolve') path as the per-ticket Resolve. Batch resolve is the
              only bulk action (task 1 removed the view-only "clear"); Suppress stays per-ticket. */}
          {canSelect && selectedTickets.length > 0 && (
            <div className="sticky top-0 z-20 mt-4 flex flex-wrap items-center gap-2.5 rounded-lg border border-accent bg-accent-weak px-3.5 py-2.5 shadow-sm">
              <span className="text-[12.5px] font-semibold text-text">
                {selectedTickets.length} selected
              </span>
              <span className="text-[11.5px] text-text-3">Resolve these tickets in one action</span>
              <div className="ml-auto flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void batchResolve()}
                  className="rounded-md border border-line-strong bg-card px-2.5 py-1 text-[12px] font-semibold text-text hover:border-accent hover:text-accent-strong"
                >
                  Resolve selected
                </button>
                <button
                  type="button"
                  onClick={clearSelection}
                  className="rounded-md px-2 py-1 text-[12px] text-text-3 hover:text-text-2"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
          {/* Grouped by run: the PARENT run/flowcell checkbox sits at the far LEFT, and the vertical
              group line starts UNDER it, enclosing the indented sample-ticket rows — the maintainer's
              exact parent→children tree (UIC-3.3 / UIC-10). */}
          <div className="mt-4 flex flex-col gap-5">
            {view.groups.map(([runId, groupTickets]) => {
              const groupDate = formatDate(groupTickets[0].runDate)
              // The group's selectable children (open/in-review). The parent checkbox toggles all of
              // them via setMany; the vertical rail lights accent when the group has a selection.
              const groupChildKeys = groupTickets.filter(view.selectable).map(keyOf)
              const groupAllSel = rs.allSelected(groupChildKeys)
              const groupHasSelection = groupChildKeys.some((k) => rs.isSelected(k))
              return (
                <div key={runId} className="flex flex-col">
                  {/* Run/flowcell header row — the PARENT checkbox is the leftmost element. */}
                  <div className="sticky top-0 z-10 flex items-center gap-2 bg-page py-2">
                    {canSelect && (
                      <span className="flex w-3.5 shrink-0 justify-center">
                        {groupChildKeys.length > 0 && (
                          <input
                            type="checkbox"
                            className="h-3.5 w-3.5 accent-accent"
                            aria-label={`Select all open tickets in ${runId}`}
                            checked={groupAllSel}
                            onChange={() => rs.setMany(groupChildKeys, !groupAllSel)}
                          />
                        )}
                      </span>
                    )}
                    <span className="font-mono text-[12px] font-semibold text-text-2">{runId}</span>
                    {groupDate && <span className="text-[11.5px] text-text-3">· {groupDate}</span>}
                    <span className="text-[11px] text-text-3">
                      {groupTickets.length} ticket{groupTickets.length === 1 ? '' : 's'}
                    </span>
                  </div>
                  {/* Children — the vertical group line starts UNDER the parent checkbox (ml-[6px]
                      centers the 2px rail beneath the 14px box), enclosing the indented sample rows. */}
                  <div
                    className={`ml-[6px] flex flex-col gap-[13px] border-l-2 pb-1 pl-3 transition-colors ${
                      groupHasSelection ? 'border-accent' : 'border-line-strong'
                    }`}
                  >
                    {groupTickets.map((t) => {
                      const key = keyOf(t)
                      const selectable = canSelect && view.selectable(t)
                      return (
                        <div key={key} className="flex items-start gap-2">
                          {canSelect && (
                            // Fixed gutter so every sample checkbox aligns just inside the rail;
                            // non-selectable (resolved) rows reserve it (empty) instead of shifting left.
                            <span className="flex w-3.5 shrink-0 justify-center pt-[15px]">
                              {selectable && (
                                <input
                                  type="checkbox"
                                  className="h-3.5 w-3.5 accent-accent"
                                  aria-label={`Select ${t.card.sample_id}`}
                                  checked={rs.isSelected(key)}
                                  // onClick (not onChange) so the native event's shiftKey drives the
                                  // range-select; onChange is a controlled-input no-op.
                                  onChange={() => {}}
                                  onClick={(e) => rs.toggle(key, e.shiftKey)}
                                />
                              )}
                            </span>
                          )}
                          <div className="min-w-0 flex-1">
                            <TicketCard
                              t={t}
                              ui={ui[key] ?? {}}
                              recurrence={recurrence.get(t.primary.rule_id)}
                              open={!!open[key]}
                              isApprover={isApprover}
                              canEscalate={canEscalate}
                              onToggle={() => setOpen((m) => ({ ...m, [key]: !m[key] }))}
                              canAssign={canSelect}
                              on={{
                                ack: () => acknowledge(t), // start reviewing + take ownership if unowned
                                resolve: () => void confirmAct(t, 'resolve'),
                                reopen: () => void confirmAct(t, 'reopen'),
                                escalate: (approverId) => void confirmEscalate(t, approverId),
                                suppress: () => void confirmSuppress(t),
                                assign: (assignee) => assign(t, assignee),
                                escalateRepair: () => void escalateRepair(t),
                                approveFix: (scope) => approveFix(t, scope),
                              }}
                            />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Canonical shared <Pager> (UIUX-03) */}
          <Pager total={view.total} page={page} perPage={perPage} onPage={setPage} onPerPage={setPerPage} noun="tickets" />
        </>
      )}
    </div>
  )
}

type TicketHandlers = {
  ack: () => void
  resolve: () => void
  reopen: () => void
  escalate: (approverId: string) => void
  suppress: () => void
  assign: (assignee: string | null) => void
  escalateRepair: () => void
  approveFix: (scope: 'instance' | 'class') => void
}

// Only reviewers + approvers can OWN a review ticket — a viewer can't act on one, so offering a
// viewer as an assignee would create a dead-end owner (UX review finding D). Escalation routes to
// an APPROVER specifically (who signs off).
const ASSIGNABLE_ACCOUNTS = DEMO_ACCOUNTS.filter((a) => a.role !== 'viewer')
const APPROVER_ACCOUNTS = DEMO_ACCOUNTS.filter((a) => a.role === 'approver')

// Assign a ticket's owner (task 3). Reviewers/approvers get a dropdown of the assignable roster (the
// same actor ids the audit trail uses, viewers excluded); a viewer sees the read-only owner. An
// off-roster assignee (set via the API by a user not in the demo roster) is preserved as its own
// option so a save can't drop it. "" is the unassigned sentinel → onAssign(null).
function AssignControl({
  assignee,
  canAssign,
  onAssign,
}: {
  assignee: string | null
  canAssign: boolean
  onAssign: (assignee: string | null) => void
}) {
  if (!canAssign) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card-2 px-2.5 py-1.5 text-[12px] text-text-2">
        <User size={13} className="text-text-3" />
        {assignee ?? 'Unassigned'}
      </span>
    )
  }
  const rosterIds = ASSIGNABLE_ACCOUNTS.map((a) => a.id)
  const offRoster = assignee && !rosterIds.includes(assignee) ? assignee : null
  return (
    <label className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-2 py-1 text-[12px] text-text-2 focus-within:border-accent">
      <User size={13} className="text-text-3" />
      <span className="sr-only">Assign ticket to</span>
      <select
        value={assignee ?? ''}
        onChange={(e) => onAssign(e.target.value === '' ? null : e.target.value)}
        className="max-w-[150px] cursor-pointer bg-transparent text-[12px] text-text focus:outline-none"
        aria-label="Assign ticket to"
      >
        <option value="">Unassigned</option>
        {ASSIGNABLE_ACCOUNTS.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name} ({a.id})
          </option>
        ))}
        {offRoster && <option value={offRoster}>{offRoster}</option>}
      </select>
    </label>
  )
}

function TicketCard({
  t,
  ui,
  recurrence,
  open,
  isApprover,
  canEscalate,
  canAssign,
  onToggle,
  on,
}: {
  t: QueueTicket
  ui: TicketUi
  recurrence: Recurrence | undefined
  open: boolean
  isApprover: boolean
  canEscalate: boolean
  canAssign: boolean
  onToggle: () => void
  on: TicketHandlers
}) {
  const { card, gate } = t
  const verdict = card.verdict
  const status = ui.status ?? 'open'
  const escalated = ui.escalated ?? false
  const suppressed = ui.suppressed ?? false
  const assignee = ui.assignee ?? null
  // Escalate now ROUTES to a specific approver, so the button opens an inline approver picker
  // (deliberate two-step = the audited confirm). Only offered once the ticket has an owner.
  const [escPicking, setEscPicking] = useState(false)
  const [escTo, setEscTo] = useState('')
  const prio = PRIORITY[verdict]
  // No per-ticket "opened" timestamp on the wire yet — show the run's own date as context
  // rather than fabricate a relative time.
  const date = formatDate(t.runDate)

  // A class seen across ≥2 distinct runs is the systemic signal that warrants the pipeline-repair
  // agent — a class flagged twice in one run is not the same thing.
  const recurring = !!recurrence && recurrence.runIds.length >= 2

  // RBAC: a reviewer resolves holds/reruns; an escalation (verdict or reviewer-raised) needs an
  // approver. The button is gated in the UI, matching the design's approver-only default.
  const needsApprover = verdict === 'escalate' || escalated
  const canAck = status === 'open'
  const canResolve = status !== 'resolved' && (!needsApprover || isApprover)
  const resolveLocked = status !== 'resolved' && needsApprover && !isApprover
  // Escalation is offered only to those who can escalate (UIC-10); a viewer gets a labelled locked
  // affordance so it's clear WHY they can't, not a silently-missing button.
  const showEscalate = canEscalate && !needsApprover && status !== 'resolved'
  const escalateLocked = !canEscalate && !needsApprover && status !== 'resolved'

  const header = (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[13px] font-semibold text-text">{ticketLabel(card)}</span>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10.5px] font-medium ${STATUS_META[status].chip}`}
        >
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${STATUS_META[status].dot}`} />
          {STATUS_META[status].label}
        </span>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${VERDICT_BADGE[verdict]}`}
        >
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${VERDICT_DOT[verdict]}`} />
          {VERDICT_LABEL[verdict]}
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-md border border-line bg-card-2 px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wide text-text-2">
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${GATE_DOT[gate]}`} />
          {GATE_LABEL[gate]} gate
        </span>
        <span className="inline-flex items-center gap-1.5 text-[11px] text-text-3">
          <PriorityBars level={prio.bars} />
          {prio.label}
        </span>
        <span className="ml-auto shrink-0 text-[11.5px] text-text-3">
          <span className="font-mono">{t.runId}</span> · <span className="font-mono">{card.sample_id}</span>
          {date && <> · {date}</>}
        </span>
      </div>
      <h3 className="mt-2 text-[14.5px] font-semibold text-text">{card.headline}</h3>
    </div>
  )

  return (
    <div
      className={`overflow-hidden rounded-xl border border-line bg-card shadow-card ${
        status === 'resolved' ? 'opacity-70' : ''
      }`}
    >
      {/* Header row IS the toggle — mirrors the CollapsibleRow primitive so a ticket reads like the
          app's other collapsibles. The card is hand-rolled (not CollapsibleRow) so the action /
          resolved footer can sit BELOW the drawer and stay reachable even when the ticket is
          collapsed, matching the prototype's card-level footers (triage actions must never hide). */}
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onToggle()
          }
        }}
        className="flex w-full cursor-pointer items-center gap-3 px-4 py-3 text-left"
      >
        <ChevronRight
          size={16}
          className={`shrink-0 text-text-3 transition-transform ${open ? 'rotate-90' : ''}`}
        />
        <div className="min-w-0 flex-1">{header}</div>
      </div>

      {open && (
        <div className="border-t border-line px-4 py-4">
          <p className="text-[12.5px] leading-relaxed text-text-2">{card.rationale}</p>

          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <span className="text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-3">Issue class</span>
            <span className="rounded-md border border-line bg-card-2 px-2 py-0.5 font-mono text-[11px] text-text-2">
              {t.primary.rule_id} · {t.primary.title}
            </span>
            {suppressed && (
              <span
                className="text-[11px] italic text-text-3"
                title="Marks this issue class handled on this ticket. Cross-run muting of future occurrences is not built."
              >
                suppressed — issue class marked handled here
              </span>
            )}
          </div>

          {recurring && recurrence && (
            <div className="mt-2.5 flex flex-wrap items-center gap-2.5 rounded-[9px] border border-rerun-bd bg-rerun-bg px-3 py-2.5">
              <RefreshCw size={15} className="shrink-0 text-rerun" />
              <span className="min-w-0 flex-1 text-[12px] leading-snug text-rerun-fg">
                Recurring signature — <strong>seen {recurrence.count}× in {recurrence.window}</strong> ·{' '}
                <span className="font-mono">{recurrence.runsLabel}</span>
              </span>
              {ui.repairEscalated ? (
                <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-accent-weak bg-accent-weak px-2.5 py-1 text-[11px] font-semibold text-accent-strong">
                  <Check size={12} />
                  Sent to pipeline-repair agent
                </span>
              ) : (
                <button
                  type="button"
                  onClick={on.escalateRepair}
                  className="whitespace-nowrap rounded-[7px] bg-rerun px-[11px] py-1.5 text-[11.5px] font-medium text-white transition-opacity hover:opacity-90"
                >
                  Escalate to repair agent
                </button>
              )}
            </div>
          )}

          {ui.repairEscalated && (
            <ReviewRepairCard
              proposal={ui.repairProposal ?? null}
              loading={ui.repairLoading ?? false}
              approved={ui.repairApproved ?? 'none'}
              isApprover={isApprover}
              onApprove={on.approveFix}
            />
          )}

          {needsApprover && status !== 'resolved' && (
            <div className="mt-2.5 flex items-center gap-2 rounded-lg border border-escalate-bd bg-escalate-bg px-3 py-2 text-[12px] text-escalate-fg">
              <ChevronUp size={14} className="shrink-0" />
              Escalated to approver — awaiting sign-off from an Approver with review-queue access.
            </div>
          )}
        </div>
      )}

      {/* Action / resolved footer — a card-level region OUTSIDE the drawer so triage actions stay
          reachable on a collapsed ticket (fidelity S6). */}
      {status === 'resolved' ? (
        <div className="flex items-start gap-2.5 border-t border-line bg-proceed-bg px-4 py-3">
          <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-proceed" />
          <p className="flex-1 text-[12.5px] leading-relaxed text-proceed-fg">
            <strong>
              Resolved by{' '}
              {/* Never fabricate the resolver: show a muted not-captured value, not a real user
                  name, when the resolve action carried no actor (data-handling: missing = signal). */}
              {ui.resolvedBy ?? <span className="font-normal text-text-3">unknown</span>}.
            </strong>{' '}
            {resolutionNote(verdict)}
          </p>
          {assignee && (
            <span className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-proceed-bd bg-card px-2.5 py-1.5 text-[12px] text-text-2">
              <User size={13} className="text-text-3" />
              {assignee}
            </span>
          )}
          <button
            type="button"
            onClick={on.reopen}
            className="rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12px] text-text-2 transition-colors hover:text-text"
          >
            Reopen
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2 border-t border-line bg-card-2 px-4 py-2.5">
          <Link
            to={`/runs/${t.runId}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12px] text-text-2 transition-colors hover:text-text"
          >
            <FileText size={13} />
            Open card
          </Link>
          <Link
            to={`/runs/${t.runId}/agent?sample=${encodeURIComponent(card.sample_id)}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12px] text-text-2 transition-colors hover:text-text"
          >
            <Sparkles size={13} />
            Ask agent
          </Link>
          {/* Assign owner (task 3) — the review↔kanban link. Reviewers/approvers get a dropdown of
              the demo roster; a viewer sees the read-only owner. */}
          <AssignControl assignee={assignee} canAssign={canAssign} onAssign={on.assign} />

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={on.suppress}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] transition-colors ${
                suppressed
                  ? 'border-accent-weak bg-accent-weak text-accent-strong'
                  : 'border-line bg-card text-text-2 hover:text-text'
              }`}
            >
              <EyeOff size={13} />
              {suppressed ? 'Suppressed' : 'Suppress issue class'}
            </button>
            {showEscalate && assignee && !escPicking && (
              <button
                type="button"
                onClick={() => {
                  // Pre-select the current owner if they already hold approver, else force a choice.
                  setEscTo(APPROVER_ACCOUNTS.some((a) => a.id === assignee) ? assignee : '')
                  setEscPicking(true)
                }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-escalate-bd bg-escalate-bg px-2.5 py-1.5 text-[12px] font-medium text-escalate-fg transition-colors hover:border-escalate-fg"
              >
                <ChevronUp size={13} />
                Escalate to approver
              </button>
            )}
            {showEscalate && assignee && escPicking && (
              <span className="inline-flex items-center gap-1 rounded-lg border border-escalate-bd bg-escalate-bg py-0.5 pl-2 pr-0.5">
                <select
                  value={escTo}
                  onChange={(e) => setEscTo(e.target.value)}
                  aria-label="Escalate to approver"
                  className="max-w-[130px] cursor-pointer bg-transparent text-[12px] text-escalate-fg focus:outline-none"
                >
                  <option value="">Choose approver…</option>
                  {APPROVER_ACCOUNTS.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  disabled={!escTo}
                  onClick={() => {
                    on.escalate(escTo)
                    setEscPicking(false)
                  }}
                  className="rounded-md bg-escalate-fg px-2 py-1 text-[11.5px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                >
                  Escalate
                </button>
                <button
                  type="button"
                  onClick={() => setEscPicking(false)}
                  className="rounded-md px-1.5 py-1 text-[11.5px] text-text-3 hover:text-text-2"
                >
                  Cancel
                </button>
              </span>
            )}
            {showEscalate && !assignee && (
              <span
                className="inline-flex cursor-default items-center gap-1.5 rounded-lg border border-line bg-card-2 px-2.5 py-1.5 text-[12px] text-text-3"
                title="Assign this ticket to an owner first — an escalation needs an accountable approver."
              >
                <Lock size={13} />
                Assign before escalating
              </span>
            )}
            {escalateLocked && (
              <span
                className="inline-flex cursor-default items-center gap-1.5 rounded-lg border border-line bg-card-2 px-2.5 py-1.5 text-[12px] text-text-3"
                title="Escalating a ticket requires a Reviewer or Approver with review-queue access."
              >
                <Lock size={13} />
                Escalation needs a Reviewer
              </span>
            )}
            {canAck && (
              <button
                type="button"
                onClick={on.ack}
                className="rounded-lg bg-accent px-3 py-1.5 text-[12px] font-medium text-white transition-opacity hover:opacity-90"
              >
                Acknowledge &amp; review
              </button>
            )}
            {canResolve && (
              <button
                type="button"
                onClick={on.resolve}
                className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12px] font-medium text-text transition-colors hover:border-accent hover:text-accent-strong"
              >
                <Check size={13} />
                Resolve
              </button>
            )}
            {resolveLocked && (
              <span
                className="inline-flex cursor-default items-center gap-1.5 rounded-lg border border-line bg-card-2 px-2.5 py-1.5 text-[12px] text-text-3"
                title="Resolving an escalation requires an Approver."
              >
                <Lock size={13} />
                Approver sign-off to resolve
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
