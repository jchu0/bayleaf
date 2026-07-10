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
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { api } from '../api'
import { FacetChip } from '../components/FacetChip'
import { PageHeader } from '../components/PageHeader'
import { ReviewRepairCard, type RepairApproval } from '../components/ReviewRepairCard'
import { ReviewStatusBar, type ReviewStatusSegment } from '../components/ReviewStatusBar'
import { ErrorBox, Loading } from '../components/States'
import { useToast } from '../components/Toast'
import { useRole } from '../context/RoleContext'
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
import { GATE_DOT, GATE_LABEL, VERDICT_BADGE, VERDICT_DOT, VERDICT_LABEL } from '../verdict'

// Most-urgent first, matching the gate's ordering.
const VERDICT_ORDER: Record<Verdict, number> = { escalate: 0, rerun: 1, hold: 2, proceed: 3 }

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

const STATUS_FILTERS: { key: 'all' | TicketStatus; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'open', label: 'Open' },
  { key: 'in_review', label: 'In review' },
  { key: 'resolved', label: 'Resolved' },
]

// A ticket derived from a flagged card (recurrence + issue class stay frontend-derived per the
// data contract — they are NOT wire fields on Ticket).
type QueueTicket = { runId: string; runDate: string | null; card: DecisionCard; primary: Finding; gate: Gate }

// Per-ticket UI state layered over the derived ticket: seeded from any matching server ticket on
// load, then overwritten by the operator's actions (optimistic; the wire write is best-effort).
type TicketUi = {
  serverId?: string
  status?: TicketStatus
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
  if (verdict === 'rerun') return 'Requeue the sample to clear the rerun.'
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
  const { actor, isApprover } = useRole()
  const { toast } = useToast()
  const [details, setDetails] = useState<RunDetail[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ui, setUi] = useState<Record<string, TicketUi>>({})
  const [filter, setFilter] = useState<'all' | TicketStatus>('all')
  const [open, setOpen] = useState<Record<string, boolean>>({})
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
      // Existing server tickets hydrate status/escalation; empty (or unreachable) is fine — the
      // queue is derived from flagged cards either way.
      api.listTickets().catch(() => [] as Ticket[]),
    ])
      .then(([ds, sts]) => {
        if (!alive) return
        setDetails(ds)
        const init: Record<string, TicketUi> = {}
        for (const st of sts) init[`${st.run_id}|${st.sample_id}`] = uiFromServer(st)
        setUi(init)
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

  // First-open: seed the most-urgent ticket expanded once, the rest collapsed.
  useEffect(() => {
    if (!seededRef.current && tickets.length > 0) {
      seededRef.current = true
      setOpen({ [keyOf(tickets[0])]: true })
    }
  }, [tickets])

  if (error) return <ErrorBox message={error} />
  if (!details) return <Loading label="Loading queue…" />

  const patch = (key: string, next: Partial<TicketUi>) =>
    setUi((prev) => ({ ...prev, [key]: { ...prev[key], ...next } }))

  // Optimistic local update, then a best-effort wire write (materializing the ticket on first
  // touch). These are off-gate advisory writes — a failed sync keeps the operator's intent
  // on-screen so the demo never stalls, and never touches a rules-decided verdict.
  // Per-key promise chain + the synchronous server-id ref (declared above) so a rapid
  // double-action on a not-yet-persisted ticket materializes exactly ONE server ticket (the
  // second action waits for the first createTicket, then reuses its id) instead of racing two POSTs.
  const syncAction = (t: QueueTicket, action: ReviewActionName): Promise<void> => {
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
    }
    const next = (pendingRef.current[key] ?? Promise.resolve()).then(run).catch((e) => {
      // Surface the real backend outcome (403/409/…) instead of silently diverging.
      toast(`Couldn't ${action} ticket — ${errMsg(e)}`, 'error')
    })
    pendingRef.current[key] = next
    return next
  }

  const act = (t: QueueTicket, action: ReviewActionName) => {
    const key = keyOf(t)
    if (action === 'acknowledge') patch(key, { status: 'in_review' })
    else if (action === 'resolve') patch(key, { status: 'resolved', resolvedBy: actor.id })
    else if (action === 'reopen') patch(key, { status: 'open' })
    else if (action === 'escalate') {
      // Escalating an untouched ticket also moves it into review; an already in-review ticket
      // keeps its status (don't clobber it with undefined).
      const wasOpen = (uiRef.current[key]?.status ?? 'open') === 'open'
      patch(key, wasOpen ? { escalated: true, status: 'in_review' } : { escalated: true })
    } else if (action === 'suppress') patch(key, { suppressed: true })
    void syncAction(t, action)
  }

  const toggleSuppress = (t: QueueTicket) => {
    const key = keyOf(t)
    if (uiRef.current[key]?.suppressed) patch(key, { suppressed: false })
    else act(t, 'suppress')
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

  const statusOf = (t: QueueTicket): TicketStatus => ui[keyOf(t)]?.status ?? 'open'

  const counts: Record<'all' | TicketStatus, number> = {
    all: tickets.length,
    open: tickets.filter((t) => statusOf(t) === 'open').length,
    in_review: tickets.filter((t) => statusOf(t) === 'in_review').length,
    resolved: tickets.filter((t) => statusOf(t) === 'resolved').length,
  }
  const shown = tickets.filter((t) => filter === 'all' || statusOf(t) === filter)

  const segments: ReviewStatusSegment[] = [
    { verdict: 'escalate', label: 'Escalations', count: tickets.filter((t) => t.card.verdict === 'escalate').length },
    { verdict: 'rerun', label: 'Reruns', count: tickets.filter((t) => t.card.verdict === 'rerun').length },
    { verdict: 'hold', label: 'Holds', count: tickets.filter((t) => t.card.verdict === 'hold').length },
  ]

  const expandAll = () => setOpen(Object.fromEntries(tickets.map((t) => [keyOf(t), true])))
  const collapseAll = () => setOpen({})

  return (
    <div className="mx-auto max-w-[940px]">
      <PageHeader
        eyebrow="Triage"
        title="Review queue"
        subtitle="Flagged samples become tickets. Acknowledge, suppress an issue class, escalate, or resolve."
      />

      {/* RBAC context — reads the shared RoleContext (a demo toggle in the user panel); the copy
          tracks the current role so what you can resolve is never ambiguous. */}
      <div className="mt-1 flex items-start gap-2.5 rounded-xl border border-line bg-card px-[14px] py-[11px] shadow-card">
        <span className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-lg bg-accent-weak">
          <ShieldCheck size={16} className="text-accent" />
        </span>
        <p className="text-[12.5px] leading-snug text-text-2">
          Signed in as <span className="font-mono text-text">{actor.id}</span> ·{' '}
          <span className="font-semibold text-text">{isApprover ? 'Approver' : 'Reviewer'}</span>.{' '}
          {isApprover ? (
            <>You can resolve holds, reruns, and escalations.</>
          ) : (
            <>
              You can resolve holds and reruns; resolving an{' '}
              <span className="font-semibold text-escalate-fg">escalation</span> requires an{' '}
              <span className="font-semibold text-text">Approver</span>.
            </>
          )}
        </p>
      </div>

      {tickets.length > 0 && <ReviewStatusBar segments={segments} />}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {STATUS_FILTERS.map((f) => (
          <FacetChip
            key={f.key}
            label={f.label}
            count={counts[f.key]}
            active={filter === f.key}
            onClick={() => setFilter(f.key)}
          />
        ))}
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

      {shown.length === 0 ? (
        <div className="mt-4 flex flex-col items-center gap-2.5 rounded-[13px] border border-dashed border-line-strong bg-card px-6 py-10 text-center">
          <span className="flex h-[46px] w-[46px] items-center justify-center rounded-xl bg-proceed-bg">
            <CheckCircle2 size={23} className="text-proceed" />
          </span>
          <p className="text-[15px] font-semibold text-text">Queue clear</p>
          <p className="text-[13px] text-text-2">
            {filter === 'all' ? 'Nothing needs review right now. Nice work.' : `No ${STATUS_META[filter].label.toLowerCase()} tickets in this view.`}
          </p>
        </div>
      ) : (
        <div className="mt-4 flex flex-col gap-[13px]">
          {shown.map((t) => {
            const key = keyOf(t)
            return (
              <TicketCard
                key={key}
                t={t}
                ui={ui[key] ?? {}}
                recurrence={recurrence.get(t.primary.rule_id)}
                open={!!open[key]}
                isApprover={isApprover}
                onToggle={() => setOpen((m) => ({ ...m, [key]: !m[key] }))}
                on={{
                  ack: () => act(t, 'acknowledge'),
                  resolve: () => act(t, 'resolve'),
                  reopen: () => act(t, 'reopen'),
                  escalate: () => act(t, 'escalate'),
                  suppress: () => toggleSuppress(t),
                  escalateRepair: () => void escalateRepair(t),
                  approveFix: (scope) => approveFix(t, scope),
                }}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

type TicketHandlers = {
  ack: () => void
  resolve: () => void
  reopen: () => void
  escalate: () => void
  suppress: () => void
  escalateRepair: () => void
  approveFix: (scope: 'instance' | 'class') => void
}

function TicketCard({
  t,
  ui,
  recurrence,
  open,
  isApprover,
  onToggle,
  on,
}: {
  t: QueueTicket
  ui: TicketUi
  recurrence: Recurrence | undefined
  open: boolean
  isApprover: boolean
  onToggle: () => void
  on: TicketHandlers
}) {
  const { card, gate } = t
  const verdict = card.verdict
  const status = ui.status ?? 'open'
  const escalated = ui.escalated ?? false
  const suppressed = ui.suppressed ?? false
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
  const showEscalate = !needsApprover && status !== 'resolved'

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
              <span className="text-[11px] italic text-text-3">suppressed — future runs won't re-prompt</span>
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
                <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-[#cfe0fb] bg-accent-weak px-2.5 py-1 text-[11px] font-semibold text-accent-strong">
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
              Escalated to approver — awaiting sign-off from an Approver.
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
            <strong>Resolved by {ui.resolvedBy ?? 'a.rivera'}.</strong> {resolutionNote(verdict)}
          </p>
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
            {showEscalate && (
              <button
                type="button"
                onClick={on.escalate}
                className="inline-flex items-center gap-1.5 rounded-lg border border-escalate-bd bg-escalate-bg px-2.5 py-1.5 text-[12px] font-medium text-escalate-fg transition-colors hover:border-escalate-fg"
              >
                <ChevronUp size={13} />
                Escalate to approver
              </button>
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
                className="inline-flex items-center gap-1.5 rounded-lg border border-proceed-bd bg-proceed-bg px-3 py-1.5 text-[12px] font-medium text-proceed-fg transition-opacity hover:opacity-90"
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
