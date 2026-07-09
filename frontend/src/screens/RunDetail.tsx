import { AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { DecisionFeedback } from '../components/DecisionFeedback'
import { EvidenceTable } from '../components/EvidenceTable'
import { GateResultStrip } from '../components/GateResultStrip'
import { Empty, ErrorBox, Loading } from '../components/States'
import { TriagePanel } from '../components/TriagePanel'
import { VerdictBadge } from '../components/VerdictBadge'
import type { DecisionCard, RunDetail as RunDetailData, Verdict } from '../types'
import { GATE_DOT, GATE_LABEL, VERDICT_STRIPE, VERDICT_TEXT } from '../verdict'

type Density = 'split' | 'brief' | 'dense'
type CardFilter = Verdict | 'all' | 'attention'
const ORDER: Record<Verdict, number> = { escalate: 0, rerun: 1, hold: 2, proceed: 3 }
const TILES: { key: Verdict | 'all'; label: string }[] = [
  { key: 'all', label: 'Samples' },
  { key: 'proceed', label: 'Proceed' },
  { key: 'hold', label: 'Hold' },
  { key: 'rerun', label: 'Rerun' },
  { key: 'escalate', label: 'Escalate' },
]

export function RunDetail() {
  const { runId = '' } = useParams()
  const [detail, setDetail] = useState<RunDetailData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<CardFilter>('all')
  const [density, setDensity] = useState<Density>('split')
  // Per-card explicit open/closed overrides. Absent → fall back to the density default
  // (`defaultOpen`): only Split auto-expands the non-proceed cards, so switching to Brief
  // no longer springs every attention card open. Cleared when the run changes.
  const [override, setOverride] = useState<Record<string, boolean>>({})

  useEffect(() => {
    setOverride({})
    api
      .run(runId)
      .then(setDetail)
      .catch((e) => setError(String(e)))
  }, [runId])

  if (error) return <ErrorBox message={error} />
  if (!detail) return <Loading label="Loading run…" />

  const counts = detail.summary.counts
  const cards = [...detail.cards].sort(
    (a, b) => ORDER[a.verdict] - ORDER[b.verdict] || a.sample_id.localeCompare(b.sample_id),
  )
  const filtered = cards.filter((c) =>
    filter === 'all' ? true : filter === 'attention' ? c.verdict !== 'proceed' : c.verdict === filter,
  )
  const chips: { key: CardFilter; label: string; count: number }[] = [
    { key: 'all', label: 'All', count: cards.length },
    { key: 'attention', label: 'Needs attention', count: detail.summary.n_attention },
    { key: 'escalate', label: 'Escalate', count: counts.escalate ?? 0 },
    { key: 'rerun', label: 'Rerun', count: counts.rerun ?? 0 },
    { key: 'hold', label: 'Hold', count: counts.hold ?? 0 },
    { key: 'proceed', label: 'Proceed', count: counts.proceed ?? 0 },
  ]

  // Density default: only Split auto-expands the actionable (non-proceed) cards; an explicit
  // per-card override (from a toggle or expand/collapse-all) always wins.
  const defaultOpen = (c: DecisionCard) => density === 'split' && c.verdict !== 'proceed'
  const isOpen = (c: DecisionCard) => override[c.sample_id] ?? defaultOpen(c)
  const allOpen = filtered.length > 0 && filtered.every(isOpen)
  const toggleAll = () =>
    setOverride((o) => ({
      ...o,
      ...Object.fromEntries(filtered.map((c) => [c.sample_id, !allOpen])),
    }))
  const activeLabel = chips.find((c) => c.key === filter)?.label ?? 'this'

  return (
    <div className="mx-auto max-w-[1080px]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-text">Decision cards</h1>
          <p className="mt-1 font-mono text-[12.5px] text-text-2">
            {detail.run_id} · {detail.summary.n_samples} samples · sorted most-urgent first
          </p>
        </div>
        <div className="flex items-center gap-3 text-[12.5px]">
          {density !== 'dense' && (
            <button
              onClick={toggleAll}
              className="rounded-lg border border-line bg-card px-2.5 py-1 text-text-2 hover:border-line-strong hover:text-text"
            >
              {allOpen ? 'Collapse all' : 'Expand all'}
            </button>
          )}
          <div className="flex items-center gap-2">
            <span className="text-text-3">Layout</span>
            <div className="flex overflow-hidden rounded-lg border border-line">
              {(['split', 'brief', 'dense'] as Density[]).map((d) => (
                <button
                  key={d}
                  onClick={() => setDensity(d)}
                  className={`px-2.5 py-1 capitalize ${
                    density === d ? 'bg-card-2 font-medium text-text' : 'bg-card text-text-2 hover:text-text'
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-5">
        {TILES.map((t) => {
          const n = t.key === 'all' ? detail.summary.n_samples : (counts[t.key] ?? 0)
          return (
            <div key={t.key} className="rounded-xl border border-line bg-card px-4 py-3 shadow-card">
              <div
                className={`font-mono text-[26px] font-semibold ${t.key === 'all' ? 'text-text' : VERDICT_TEXT[t.key]}`}
              >
                {n}
              </div>
              <div className="mt-0.5 text-[12px] text-text-2">{t.label}</div>
            </div>
          )
        })}
      </div>

      {detail.summary.n_attention > 0 && (
        <div className="mt-4 flex items-center gap-3 rounded-xl border border-hold-bd bg-hold-bg px-4 py-3">
          <AlertTriangle size={16} className="shrink-0 text-hold-fg" />
          <span className="text-[13px] text-hold-fg">
            <b>{detail.summary.n_attention} sample(s) need operator attention</b> before this run can be released.
          </span>
          <Link
            to="/queue"
            className="ml-auto shrink-0 rounded-lg border border-hold-bd bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-line-strong"
          >
            Open review queue
          </Link>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {chips.map((c) => (
          <button
            key={c.key}
            onClick={() => setFilter(c.key)}
            className={`flex items-center gap-1.5 rounded-[20px] border px-3 py-1 text-[13px] transition-colors ${
              filter === c.key
                ? 'border-accent bg-accent-weak font-medium text-accent-strong'
                : 'border-line bg-card text-text-2 hover:border-line-strong'
            }`}
          >
            {c.label} <span className={filter === c.key ? 'text-accent-strong/70' : 'text-text-3'}>{c.count}</span>
          </button>
        ))}
      </div>

      <div className="mt-4 space-y-3">
        {filtered.length === 0 ? (
          <Empty message={`No samples match the “${activeLabel}” filter.`} />
        ) : (
          filtered.map((card) => (
            <CardView
              key={card.sample_id}
              runId={runId}
              card={card}
              density={density}
              open={isOpen(card)}
              onToggle={() =>
                setOverride((o) => ({ ...o, [card.sample_id]: !isOpen(card) }))
              }
            />
          ))
        )}
      </div>
    </div>
  )
}

function FlaggedChip({ card }: { card: DecisionCard }) {
  if (card.verdict === 'proceed') return null
  const gr = card.gate_results.find((g) => g.verdict === card.verdict) ?? card.gate_results[0]
  const gate = gr?.gate ?? card.findings[0]?.gate
  if (!gate) return null
  return (
    <span className="flex shrink-0 items-center gap-1.5 rounded-full border border-line bg-card-2 px-2 py-0.5 text-[11px] text-text-2">
      <span className={`h-1.5 w-1.5 rounded-full ${GATE_DOT[gate]}`} />
      Flagged at {GATE_LABEL[gate]}
    </span>
  )
}

function NextSteps({ steps }: { steps: string[] }) {
  if (steps.length === 0) return null
  return (
    <div className="mt-4">
      <p className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-3">
        Recommended next steps
      </p>
      <ul className="list-disc space-y-1 pl-5 text-[13px] text-text">
        {steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    </div>
  )
}

function CardView({
  runId,
  card,
  density,
  open,
  onToggle,
}: {
  runId: string
  card: DecisionCard
  density: Density
  open: boolean
  onToggle: () => void
}) {
  // Per-verdict colored spine so a collapsed/compact card reads its verdict at a glance.
  const stripe = `border-l-[3px] ${VERDICT_STRIPE[card.verdict]}`

  // Dense: a real one-line compact row — verdict + id + headline + flagged gate, no expand.
  if (density === 'dense') {
    return (
      <article
        className={`flex items-center gap-3 rounded-xl border border-line ${stripe} bg-card px-4 py-2.5 shadow-card`}
      >
        <VerdictBadge verdict={card.verdict} />
        <span className="shrink-0 font-mono text-[13px] font-semibold text-text">{card.sample_id}</span>
        <span className="min-w-0 flex-1 truncate text-[13px] text-text-2">{card.headline}</span>
        <FlaggedChip card={card} />
      </article>
    )
  }

  const actionable = card.verdict !== 'proceed'
  const full = density === 'split'
  // Keys for the per-decision feedback footer: the flagged gate (as FlaggedChip picks it) +
  // the distinct rule ids this card cites.
  const fbGr = card.gate_results.find((g) => g.verdict === card.verdict) ?? card.gate_results[0]
  const fbGate = fbGr?.gate ?? card.findings[0]?.gate ?? null
  const fbRuleIds = [...new Set(card.findings.map((f) => f.rule_id))]
  return (
    <article className={`overflow-hidden rounded-xl border border-line ${stripe} bg-card shadow-card`}>
      <button onClick={onToggle} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        {open ? (
          <ChevronDown size={16} className="shrink-0 text-text-3" />
        ) : (
          <ChevronRight size={16} className="shrink-0 text-text-3" />
        )}
        <VerdictBadge verdict={card.verdict} />
        <span className="shrink-0 font-mono text-[14px] font-semibold text-text">{card.sample_id}</span>
        <span className="min-w-0 flex-1 truncate text-[13.5px] text-text">{card.headline}</span>
        <FlaggedChip card={card} />
      </button>
      {open && (
        <div className="border-t border-line px-4 py-4">
          <p className="mb-3 text-[13px] text-text-2">{card.rationale}</p>
          {card.gate_results.length > 0 && (
            <GateResultStrip results={card.gate_results} cardVerdict={card.verdict} />
          )}
          {full ? (
            // Split: the full readout — evidence table, next steps, triage, feedback.
            <>
              <div className="mt-4">
                <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-3">
                  QC readout by gate
                </p>
                <EvidenceTable findings={card.findings} />
              </div>
              <NextSteps steps={card.next_steps} />
              {actionable && (
                <div className="mt-4">
                  <TriagePanel runId={runId} sampleId={card.sample_id} />
                </div>
              )}
              <DecisionFeedback
                runId={runId}
                sampleId={card.sample_id}
                verdict={card.verdict}
                gate={fbGate}
                ruleIds={fbRuleIds}
                cardContentHash={card.content_hash}
              />
            </>
          ) : (
            // Brief: a lighter body — gate strip + next steps only (heavy evidence table and
            // the triage/feedback panels stay in Split).
            <NextSteps steps={card.next_steps} />
          )}
        </div>
      )}
    </article>
  )
}
