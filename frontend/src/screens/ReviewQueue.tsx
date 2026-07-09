import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BellOff, Check, FileText, Lock, RefreshCw, Shield, Sparkles, TrendingUp } from 'lucide-react'
import { api } from '../api'
import { Empty, ErrorBox, Loading } from '../components/States'
import { VerdictBadge } from '../components/VerdictBadge'
import type { DecisionCard, Finding, Gate, RunDetail } from '../types'
import { GATE_DOT, GATE_LABEL } from '../verdict'

// Most-urgent first, matching the gate's ordering.
const VERDICT_ORDER: Record<string, number> = { escalate: 0, rerun: 1, hold: 2, proceed: 3 }

// Priority is derived from the verdict, not stored — escalations/reruns block a run,
// holds are judgment calls. Bars = filled count in the ascending signal glyph.
const PRIORITY: Record<string, { label: string; bars: number }> = {
  escalate: { label: 'High', bars: 3 },
  rerun: { label: 'High', bars: 3 },
  hold: { label: 'Medium', bars: 2 },
}

type Status = 'open' | 'in-review' | 'resolved'
type Ticket = {
  runId: string
  card: DecisionCard
  primary: Finding
  gate: Gate
  ticketId: string
}
type Recurrence = { count: number; runs: string[] }

// Session-local until the ticketing backend lands — actions here mutate ephemeral state
// only. Suppress / escalate-to-approver carry backend semantics, so they stay non-wired.
const PROTO_TIP = 'Suppress + escalate route through the ticketing backend (not wired in this build).'

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

function GatePill({ gate }: { gate: Gate }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card-2 px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide text-text-2">
      <span className={`h-1.5 w-1.5 rounded-full ${GATE_DOT[gate]}`} />
      {GATE_LABEL[gate]} gate
    </span>
  )
}

// The flagged gate + the finding that drives this ticket (the one matching the verdict's
// gate, else the most-severe). Mirrors the gate's own selection in RunDetail's FlaggedChip.
function primaryFinding(card: DecisionCard): { primary: Finding; gate: Gate } | null {
  if (card.findings.length === 0) return null
  const gr = card.gate_results.find((g) => g.verdict === card.verdict) ?? card.gate_results[0]
  const primary = (gr && card.findings.find((f) => f.gate === gr.gate)) ?? card.findings[0]
  return { primary, gate: primary.gate }
}

function ticketId(card: DecisionCard): string {
  // Stable per card, no server ticket id yet: fold the content hash into a T-#### label.
  const seed = Number.parseInt(card.content_hash.slice(0, 6), 16)
  return `T-${(seed % 9000) + 1000}`
}

export function ReviewQueue() {
  const [details, setDetails] = useState<RunDetail[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<Record<string, Status>>({})
  const [filter, setFilter] = useState<'all' | Status>('all')

  useEffect(() => {
    api
      .runs()
      .then((runs) => Promise.all(runs.map((r) => api.run(r.run_id))))
      .then(setDetails)
      .catch((e) => setError(String(e)))
  }, [])

  const { tickets, recurrence } = useMemo(() => {
    // Keyed on the issue *class* (rule_id), not the content signature: the §4 banner
    // surfaces a class recurring across runs (PROV-001 seen 3×), which drives the
    // fix-one vs fix-class repair-agent scopes. Observation-specific signatures never
    // dedupe (each barcode value differs), so they'd never trip the banner.
    const recurrence = new Map<string, Recurrence>()
    const tickets: Ticket[] = []
    if (details) {
      for (const d of details) {
        for (const c of d.cards) {
          for (const f of c.findings) {
            const cur = recurrence.get(f.rule_id) ?? { count: 0, runs: [] }
            cur.count += 1
            if (!cur.runs.includes(d.run_id)) cur.runs.push(d.run_id)
            recurrence.set(f.rule_id, cur)
          }
          if (c.verdict === 'proceed') continue
          const pf = primaryFinding(c)
          if (!pf) continue
          tickets.push({ runId: d.run_id, card: c, primary: pf.primary, gate: pf.gate, ticketId: ticketId(c) })
        }
      }
      tickets.sort((a, b) => VERDICT_ORDER[a.card.verdict] - VERDICT_ORDER[b.card.verdict])
    }
    return { tickets, recurrence }
  }, [details])

  if (error) return <ErrorBox message={error} />
  if (!details) return <Loading label="Loading queue…" />

  const statusOf = (t: Ticket): Status => status[t.ticketId] ?? 'open'
  const counts: Record<'all' | Status, number> = {
    all: tickets.length,
    open: tickets.filter((t) => statusOf(t) === 'open').length,
    'in-review': tickets.filter((t) => statusOf(t) === 'in-review').length,
    resolved: tickets.filter((t) => statusOf(t) === 'resolved').length,
  }
  const shown = tickets.filter((t) => filter === 'all' || statusOf(t) === filter)
  const setTicket = (id: string, s: Status) => setStatus((m) => ({ ...m, [id]: s }))

  const CHIPS: { key: 'all' | Status; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'open', label: 'Open' },
    { key: 'in-review', label: 'In review' },
    { key: 'resolved', label: 'Resolved' },
  ]

  return (
    <div className="mx-auto max-w-[940px]">
      <h1 className="text-[22px] font-semibold tracking-tight text-text">Review queue</h1>
      <p className="mt-1 text-[13px] text-text-2">
        Flagged samples become tickets. Acknowledge, suppress an issue class, escalate, or resolve.
      </p>

      <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-line bg-card px-4 py-3 text-[12.5px] text-text-2 shadow-card">
        <Shield size={15} className="mt-0.5 shrink-0 text-accent" />
        <p>
          Signed in as <span className="font-mono text-text">a.rivera</span> · <span className="text-text">Reviewer</span>.
          You can resolve holds and reruns; resolving an <span className="font-medium text-text">escalation</span> requires
          an <span className="font-medium text-text">Approver</span>.
        </p>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {CHIPS.map((c) => (
          <button
            key={c.key}
            onClick={() => setFilter(c.key)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12.5px] transition-colors ${
              filter === c.key
                ? 'border-accent bg-accent-weak font-medium text-accent'
                : 'border-line bg-card text-text-2 hover:text-text'
            }`}
          >
            {c.label}
            <span
              className={`rounded-full px-1.5 text-[10.5px] font-semibold ${
                filter === c.key ? 'bg-accent text-white' : 'bg-card-2 text-text-3'
              }`}
            >
              {counts[c.key]}
            </span>
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <div className="mt-4">
          <Empty message={filter === 'all' ? 'Nothing to review — every sample cleared.' : `No ${filter} tickets.`} />
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {shown.map((t) => (
            <TicketCard
              key={t.runId + t.card.sample_id}
              t={t}
              status={statusOf(t)}
              recurrence={recurrence.get(t.primary.rule_id)}
              onAcknowledge={() => setTicket(t.ticketId, 'in-review')}
              onResolve={() => setTicket(t.ticketId, 'resolved')}
              onReopen={() => setTicket(t.ticketId, 'open')}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function TicketCard({
  t,
  status,
  recurrence,
  onAcknowledge,
  onResolve,
  onReopen,
}: {
  t: Ticket
  status: Status
  recurrence: Recurrence | undefined
  onAcknowledge: () => void
  onResolve: () => void
  onReopen: () => void
}) {
  const { card, runId, primary, gate } = t
  const prio = PRIORITY[card.verdict] ?? { label: 'Low', bars: 1 }
  const needsApprover = card.verdict === 'escalate'
  // Cross-run recurrence (≥2 distinct runs) is the systemic signal that warrants a
  // pipeline-repair agent — a class flagged twice in one run is not the same thing.
  const recurring = recurrence && recurrence.runs.length >= 2

  return (
    <article
      className={`overflow-hidden rounded-xl border bg-card shadow-card ${
        status === 'resolved' ? 'border-line opacity-70' : 'border-line'
      }`}
    >
      <div className="p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[12px] font-semibold text-text-3">{t.ticketId}</span>
          <VerdictBadge verdict={card.verdict} />
          <GatePill gate={gate} />
          <span className="inline-flex items-center gap-1.5 text-[11px] text-text-3">
            <PriorityBars level={prio.bars} />
            {prio.label}
          </span>
          <span className="ml-auto shrink-0 font-mono text-[11px] text-text-3">
            {runId} · {card.sample_id}
          </span>
        </div>

        <h3 className="mt-2.5 text-[14.5px] font-semibold text-text">{card.headline}</h3>
        <p className="mt-1 text-[13px] text-text-2">{card.rationale}</p>

        <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[11px]">
          <span className="font-semibold uppercase tracking-[0.4px] text-text-3">Issue class</span>
          <span className="font-mono text-text-2">{primary.rule_id}</span>
          <span className="text-text-3">·</span>
          <span className="text-text-2">{primary.title}</span>
        </div>

        {recurring && (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-hold-bd bg-hold-bg px-3 py-2">
            <RefreshCw size={14} className="shrink-0 text-hold-fg" />
            <span className="text-[12px] text-hold-fg">
              Recurring signature — <span className="font-semibold">seen {recurrence.count}×</span> ·{' '}
              <span className="font-mono">{recurrence.runs.slice(0, 3).join(', ')}</span>
            </span>
            <button
              title={PROTO_TIP}
              className="ml-auto inline-flex cursor-default items-center gap-1.5 rounded-md bg-hold-fg/90 px-2.5 py-1 text-[11.5px] font-medium text-white"
            >
              <TrendingUp size={13} />
              Escalate to repair agent
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-line bg-card-2/50 px-4 py-2.5">
        <Link
          to={`/runs/${runId}`}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12px] text-text-2 transition-colors hover:text-text"
        >
          <FileText size={13} />
          Open card
        </Link>
        <Link
          to={`/runs/${runId}?agent=${card.sample_id}`}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12px] text-text-2 transition-colors hover:text-text"
        >
          <Sparkles size={13} />
          Ask agent
        </Link>

        {status === 'resolved' ? (
          <span className="ml-auto flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 text-[12px] text-proceed-fg">
              <Check size={14} />
              Resolved · a.rivera
            </span>
            <button
              onClick={onReopen}
              className="rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12px] text-text-2 transition-colors hover:text-text"
            >
              Reopen
            </button>
          </span>
        ) : (
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button
              title={PROTO_TIP}
              className="inline-flex cursor-default items-center gap-1.5 rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12px] text-text-3"
            >
              <BellOff size={13} />
              Suppress issue class
            </button>
            {status === 'open' && (
              <button
                onClick={onAcknowledge}
                className="rounded-lg bg-accent px-3 py-1.5 text-[12px] font-medium text-white transition-opacity hover:opacity-90"
              >
                Acknowledge &amp; review
              </button>
            )}
            {needsApprover ? (
              <button
                title="Resolving an escalation requires an Approver."
                className="inline-flex cursor-default items-center gap-1.5 rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12px] text-text-3"
              >
                <Lock size={13} />
                Approver sign-off to resolve
              </button>
            ) : (
              <button
                onClick={onResolve}
                className="inline-flex items-center gap-1.5 rounded-lg border border-proceed-bd bg-proceed-bg px-3 py-1.5 text-[12px] font-medium text-proceed-fg transition-opacity hover:opacity-90"
              >
                <Check size={13} />
                Resolve
              </button>
            )}
          </div>
        )}
      </div>
    </article>
  )
}
