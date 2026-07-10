import { AlertTriangle, ArrowRight, Check, CheckCircle2, GitBranch, Sparkles } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { CollapsibleRow } from '../components/CollapsibleRow'
import { DecisionContextRail } from '../components/DecisionContextRail'
import { DecisionFeedback } from '../components/DecisionFeedback'
import { DecisionLoading, DecisionReleased, DecisionSynthesisError } from '../components/DecisionStates'
import { DecisionVerdictBar } from '../components/DecisionVerdictBar'
import { CitedEvidence } from '../components/EvidenceTable'
import { FacetChip } from '../components/FacetChip'
import { GateResultStrip } from '../components/GateResultStrip'
import { QCReadout } from '../components/MetricsPanel'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
import { ErrorBox } from '../components/States'
import { VerdictBadge } from '../components/VerdictBadge'
import type { CardHeader, CardReadout, DecisionCard, Gate, RunDetail as RunDetailData, Verdict } from '../types'
import { GATE_DOT, VERDICT_STRIPE } from '../verdict'

type Density = 'split' | 'brief' | 'dense'
type CardFilter = Verdict | 'all' | 'attention'
// Readout join keyed by sample; 'error' marks a readout that failed to load (the card still
// renders rule-derived content — a missing hero is a signal, not a crash).
type ReadoutState = Record<string, CardReadout | 'error'>

const ORDER: Record<Verdict, number> = { escalate: 0, rerun: 1, hold: 2, proceed: 3 }
const FILTERS: CardFilter[] = ['all', 'attention', 'escalate', 'rerun', 'hold', 'proceed']
const LAYOUTS: { value: Density; label: string }[] = [
  { value: 'split', label: 'Split' },
  { value: 'brief', label: 'Brief' },
  { value: 'dense', label: 'Dense' },
]
// The design's origin tags — where a card's verdict originated (qc/variant read as "… gate").
const GATE_TAG: Record<Gate, string> = { preflight: 'Preflight', qc: 'QC gate', variant: 'Variant gate' }

export function RunDetail() {
  const { runId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const [detail, setDetail] = useState<RunDetailData | null>(null)
  const [readouts, setReadouts] = useState<ReadoutState>({})
  const [error, setError] = useState<string | null>(null)
  const [density, setDensity] = useState<Density>('split')
  const [reload, setReload] = useState(0)
  // Per-card open overrides + a screen-wide expand/collapse latch. Absent override → the
  // default (first card open, rest collapsed); expand/collapse-all clears the overrides.
  const [override, setOverride] = useState<Record<string, boolean>>({})
  const [allState, setAllState] = useState<'all' | 'none' | null>(null)

  useEffect(() => {
    setOverride({})
    setAllState(null)
    setReadouts({})
    setDetail(null)
    setError(null)
    let cancelled = false
    api
      .run(runId)
      .then((d) => {
        if (cancelled) return
        setDetail(d)
        // Running (no final cards) / released (cards hidden) runs don't render cards — skip the
        // readout fan-out for them.
        if (d.summary.status === 'running' || d.summary.status === 'released') return
        // Fetch each card's QC readout independently — the hero table + honest header chips come
        // from the api projection; a failure degrades one card, never the screen.
        for (const c of d.cards) {
          api
            .qcReadout(runId, c.sample_id)
            .then((rd) => !cancelled && setReadouts((m) => ({ ...m, [c.sample_id]: rd })))
            .catch(() => !cancelled && setReadouts((m) => ({ ...m, [c.sample_id]: 'error' })))
        }
      })
      .catch((e) => !cancelled && setError(String(e)))
    return () => {
      cancelled = true
    }
  }, [runId, reload])

  // The URL owns the filter so Monitoring can deep-link `?filter=attention` to a run's flagged
  // samples. Unknown values fall back to "all".
  const rawFilter = searchParams.get('filter')
  const filter: CardFilter = rawFilter && FILTERS.includes(rawFilter as CardFilter) ? (rawFilter as CardFilter) : 'all'
  const setFilter = (f: CardFilter) =>
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev)
        if (f === 'all') p.delete('filter')
        else p.set('filter', f)
        return p
      },
      { replace: true },
    )

  const subtitle: ReactNode = detail ? (
    <span>
      <span className="font-mono text-text">{detail.run_id}</span> · {detail.summary.platform ?? '—'} ·{' '}
      {detail.summary.run_date ?? '—'} · {detail.summary.n_samples} samples · sorted most-urgent first
    </span>
  ) : (
    <span>
      <span className="font-mono text-text">{runId}</span> · loading…
    </span>
  )

  return (
    <div className="mx-auto max-w-[1080px]">
      <PageHeader
        eyebrow="Decision gate"
        title="Decision cards"
        subtitle={subtitle}
        actions={
          <div className="flex items-center gap-2.5">
            <span className="text-[11.5px] font-medium text-text-3">Layout</span>
            <SegmentedControl<Density> options={LAYOUTS} value={density} onChange={setDensity} />
          </div>
        }
      />
      {renderBody()}
    </div>
  )

  function renderBody() {
    if (error) return <ErrorBox message={error} onRetry={() => setReload((r) => r + 1)} />
    if (!detail) return <DecisionLoading />
    if (detail.summary.status === 'running') return <DecisionLoading />
    if (detail.summary.status === 'released') return <DecisionReleased count={detail.summary.n_samples} />

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

    // Synthesis-error banner (rules decide / AI narrates): the rule engine produced findings but
    // narration is blank across the board — surface it, and STILL render the cards below.
    const synthesisError =
      detail.cards.length > 0 &&
      detail.cards.some((c) => c.findings.length > 0) &&
      detail.cards.every((c) => !c.rationale?.trim())

    const defaultOpen = (idx: number) => (allState === 'all' ? true : allState === 'none' ? false : idx === 0)
    const isOpen = (c: DecisionCard, idx: number) => override[c.sample_id] ?? defaultOpen(idx)

    return (
      <>
        {synthesisError && <DecisionSynthesisError onRetry={() => setReload((r) => r + 1)} />}

        <DecisionVerdictBar counts={counts} />

        {detail.summary.n_attention > 0 && (
          <div className="mt-3.5 flex items-center gap-3 rounded-[12px] border border-hold-bd bg-hold-bg px-4 py-3">
            <div className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-[9px] border border-hold-bd bg-white">
              <AlertTriangle size={18} strokeWidth={2} className="text-hold" />
            </div>
            <div className="flex-1 text-[13.5px] text-hold-fg">
              <b>{detail.summary.n_attention} sample(s) need operator attention</b> before this run can be released.
            </div>
            <Link
              to="/queue"
              className="whitespace-nowrap rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-text-3"
            >
              Open review queue
            </Link>
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {chips.map((c) => (
            <FacetChip
              key={c.key}
              label={c.label}
              count={c.count}
              active={filter === c.key}
              onClick={() => setFilter(c.key)}
            />
          ))}
          <div className="min-w-3 flex-1" />
          <button
            onClick={() => {
              setAllState('all')
              setOverride({})
            }}
            className="rounded-lg border border-line-strong bg-card px-[11px] py-1.5 text-[12px] text-text-2 hover:text-text"
          >
            Expand all
          </button>
          <button
            onClick={() => {
              setAllState('none')
              setOverride({})
            }}
            className="rounded-lg border border-line-strong bg-card px-[11px] py-1.5 text-[12px] text-text-2 hover:text-text"
          >
            Collapse all
          </button>
        </div>

        {filtered.length === 0 ? (
          <div className="mt-4 rounded-[13px] border border-dashed border-line-strong bg-card p-[38px] text-center">
            <div className="text-[15px] font-semibold text-text">No samples match this filter</div>
            <div className="mt-1 text-[13px] text-text-2">Try a different verdict, or clear the filter.</div>
          </div>
        ) : (
          <div className="mt-4 flex flex-col gap-[13px]">
            {filtered.map((card, idx) => {
              const open = isOpen(card, idx)
              const rd = readouts[card.sample_id]
              const readout = rd && rd !== 'error' ? rd : null
              return (
                <CollapsibleRow
                  key={card.sample_id}
                  open={open}
                  onToggle={() => setOverride((o) => ({ ...o, [card.sample_id]: !open }))}
                  className={`border-l-[3px] ${VERDICT_STRIPE[card.verdict]}`}
                  header={<CardHead card={card} header={readout?.header ?? null} />}
                >
                  <CardBody
                    runId={runId}
                    card={card}
                    density={density}
                    readout={readout}
                    platform={detail!.summary.platform}
                    date={detail!.summary.run_date}
                  />
                </CollapsibleRow>
              )
            })}
          </div>
        )}
      </>
    )
  }
}

// Where a card's verdict originated — verb + gate tag + dot for the header origin chip.
function originInfo(card: DecisionCard): { verb: string; tag: string; dot: string } {
  if (card.verdict === 'proceed') return { verb: 'Cleared at', tag: 'All gates', dot: 'bg-proceed' }
  const verb = card.verdict === 'rerun' ? 'Failed at' : 'Flagged at'
  const gate = card.gate_results.find((g) => g.verdict === card.verdict)?.gate ?? card.findings[0]?.gate ?? null
  if (!gate) return { verb, tag: 'Operational', dot: 'bg-warn' }
  return { verb, tag: GATE_TAG[gate], dot: GATE_DOT[gate] }
}

function CardHead({ card, header }: { card: DecisionCard; header: CardHeader | null }) {
  const oi = originInfo(card)
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <VerdictBadge verdict={card.verdict} />
      <span className="shrink-0 font-mono text-[16px] font-semibold text-text">{card.sample_id}</span>
      <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-text">{card.headline}</span>
      {header?.sample_type && (
        <span className="shrink-0 rounded-full border border-line bg-card-2 px-2.5 py-0.5 text-[11px] text-text-2">
          {header.sample_type}
        </span>
      )}
      <span className="flex shrink-0 items-center gap-1.5 rounded-full border border-line bg-card-2 px-2.5 py-0.5 text-[10.5px] font-medium text-text-2">
        <span className={`h-1.5 w-1.5 rounded-full ${oi.dot}`} />
        {oi.verb} {oi.tag}
      </span>
    </div>
  )
}

function SectionLabel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`text-[11px] font-semibold uppercase tracking-[0.5px] text-text-3 ${className}`}>{children}</div>
  )
}

function NextSteps({ steps, variant }: { steps: string[]; variant: 'arrow' | 'numbered' }) {
  if (steps.length === 0) return null
  if (variant === 'arrow') {
    return (
      <>
        <SectionLabel className="mt-[15px]">Recommended next steps</SectionLabel>
        <div className="mt-2 flex flex-col gap-[7px]">
          {steps.map((s, i) => (
            <div key={i} className="flex items-start gap-2.5 text-[13px] leading-[1.45] text-text-2">
              <ArrowRight size={15} strokeWidth={2.2} className="mt-0.5 shrink-0 text-accent" />
              <span>{s}</span>
            </div>
          ))}
        </div>
      </>
    )
  }
  return (
    <>
      <SectionLabel className="mt-4">Recommended next steps</SectionLabel>
      <div className="mt-2 flex flex-col gap-2">
        {steps.map((s, i) => (
          <div key={i} className="flex items-start gap-2.5 text-[13.5px] leading-[1.5] text-text-2">
            <span className="grid h-5 w-5 shrink-0 place-items-center rounded-[6px] bg-accent-weak font-mono text-[11px] font-semibold text-accent">
              {i + 1}
            </span>
            <span>{s}</span>
          </div>
        ))}
      </div>
    </>
  )
}

function CleanPanel({ brief = false }: { brief?: boolean }) {
  return (
    <div className="mt-4 flex items-center gap-2.5 rounded-[10px] border border-proceed-bd bg-proceed-bg px-3.5 py-3">
      <CheckCircle2 size={18} strokeWidth={2} className="shrink-0 text-proceed" />
      <span className={`${brief ? 'text-[13.5px]' : 'text-[13px]'} text-proceed-fg`}>
        {brief
          ? 'No provenance, metadata, or QC issues found.'
          : 'No provenance, metadata, or QC issues found. Every runbook check passed with margin.'}
      </span>
    </div>
  )
}

function RailButton({ to, accent, children }: { to: string; accent?: boolean; children: ReactNode }) {
  return (
    <Link
      to={to}
      className={
        accent
          ? 'flex items-center gap-[7px] rounded-lg bg-accent px-3.5 py-2 text-[12.5px] font-medium text-white transition-opacity hover:opacity-90'
          : 'flex items-center gap-[7px] rounded-lg border border-line-strong bg-card px-3.5 py-2 text-[12.5px] font-medium text-text transition-colors hover:border-text-3'
      }
    >
      {children}
    </Link>
  )
}

function CardBody({
  runId,
  card,
  density,
  readout,
  platform,
  date,
}: {
  runId: string
  card: DecisionCard
  density: Density
  readout: CardReadout | null
  platform: string | null
  date: string | null
}) {
  const gates = readout?.readout.gates ?? []
  const hasReadout = gates.some((g) => g.rows.length > 0)
  const hasFindings = card.findings.length > 0
  const clean = card.verdict === 'proceed'
  const actionable = card.verdict !== 'proceed'
  const agentTo = `/runs/${runId}/agent?sample=${encodeURIComponent(card.sample_id)}`

  // Feedback keys — the exact call the operator reacts to (verdict + gate + rule ids + hash).
  const fbGate = card.gate_results.find((g) => g.verdict === card.verdict)?.gate ?? card.findings[0]?.gate ?? null
  const fbRuleIds = [...new Set(card.findings.map((f) => f.rule_id))]

  // Cancel CollapsibleRow's body padding so the gate strip + rail run edge-to-edge (each inner
  // section owns its padding).
  return (
    <div className="-m-4">
      <GateResultStrip results={card.gate_results} cardVerdict={card.verdict} />

      {density === 'split' && (
        <>
          {hasReadout && (
            <div className="border-b border-line px-5 py-4">
              <SectionLabel className="mb-2.5">QC readout by gate</SectionLabel>
              <QCReadout gates={gates} variant="split" />
            </div>
          )}
          <div className="flex">
            <div className="min-w-0 flex-1 px-5 py-4">
              {card.rationale && <p className="text-[13.5px] leading-[1.6] text-text">{card.rationale}</p>}
              <NextSteps steps={card.next_steps} variant="arrow" />
              {hasFindings ? (
                <>
                  <SectionLabel className="mt-[18px]">Supporting evidence · cited</SectionLabel>
                  <div className="mt-2.5">
                    <CitedEvidence findings={card.findings} variant="split" />
                  </div>
                </>
              ) : clean ? (
                <CleanPanel />
              ) : null}
              <DecisionFeedback
                runId={runId}
                sampleId={card.sample_id}
                verdict={card.verdict}
                gate={fbGate}
                ruleIds={fbRuleIds}
                cardContentHash={card.content_hash}
              />
            </div>
            <DecisionContextRail
              runId={runId}
              sampleId={card.sample_id}
              verdict={card.verdict}
              header={readout?.header ?? null}
              platform={platform}
              date={date}
            />
          </div>
        </>
      )}

      {density === 'brief' && (
        <div className="max-w-[760px] px-6 py-5">
          {card.rationale && <p className="text-[15px] leading-[1.6] text-text">{card.rationale}</p>}
          <NextSteps steps={card.next_steps} variant="numbered" />
          {hasFindings ? (
            <>
              <SectionLabel className="mt-5 border-t border-line pt-[18px]">Cited evidence</SectionLabel>
              <div className="mt-2.5">
                <CitedEvidence findings={card.findings} variant="brief" />
              </div>
            </>
          ) : clean ? (
            <CleanPanel brief />
          ) : null}
          {hasReadout && (
            <>
              <SectionLabel className="mt-5 border-t border-line pt-4">QC readout by gate</SectionLabel>
              <div className="mt-2.5">
                <QCReadout gates={gates} variant="brief" />
              </div>
            </>
          )}
          <div className="mt-3.5 flex gap-2.5">
            <RailButton to={`/runs/${runId}/provenance`}>
              <GitBranch size={14} /> View lineage
            </RailButton>
            {actionable && (
              <RailButton to={agentTo} accent>
                <Sparkles size={14} /> Ask agent to triage
              </RailButton>
            )}
          </div>
        </div>
      )}

      {density === 'dense' && (
        <div className="px-[18px] py-[13px]">
          {card.rationale && <div className="mb-2.5 text-[12.5px] leading-[1.5] text-text-2">{card.rationale}</div>}
          {hasFindings ? (
            <CitedEvidence findings={card.findings} variant="dense" />
          ) : clean ? (
            <div className="flex items-center gap-[7px] text-[12.5px] text-proceed-fg">
              <Check size={15} className="text-proceed" /> All runbook checks passed.
            </div>
          ) : null}
          {hasReadout && (
            <div className="mt-2.5">
              <QCReadout gates={gates} variant="dense" />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
