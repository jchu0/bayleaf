import { AlertTriangle, ArrowRight, Check, CheckCircle2, FileText, GitBranch, Sparkles } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { CollapsibleRow } from '../components/CollapsibleRow'
import { DecisionContextRail } from '../components/DecisionContextRail'
import { DecisionFeedback } from '../components/DecisionFeedback'
import { DecisionLoading, DecisionReleased, DecisionSynthesisError } from '../components/DecisionStates'
import { DecisionVerdictBar } from '../components/DecisionVerdictBar'
import { CitedEvidence } from '../components/EvidenceTable'
import { Tabs } from '../components/Tabs'
import { Truncate } from '../components/Truncate'
import { GateResultStrip } from '../components/GateResultStrip'
import { QCReadout, emptyGateGroup, notMeasuredGroup, type ReadoutGroup } from '../components/MetricsPanel'
import { PageHeader } from '../components/PageHeader'
import { Pager, type PerPage } from '../components/Pager'
import { RunReport } from '../components/RunReport'
import { ErrorBox } from '../components/States'
import { VerdictBadge } from '../components/VerdictBadge'
import type {
  CardHeader,
  CardReadout,
  DecisionCard,
  Gate,
  CheckCoverage,
  QcReportLink,
  RunbookPolicy,
  Verdict,
} from '../types'
import { GATE_DOT, GATE_TAG, VERDICT_ORDER, governingGate } from '../verdict'
import { usePrefs } from '../context/PrefsContext'
import { useAccess } from '../context/AccessContext'
import { useRun } from '../hooks/useRun'

type Density = 'split' | 'brief' | 'dense'
type CardFilter = Verdict | 'all' | 'attention'
// Top-level view switch: the per-sample decision cards vs. the single-document run Report (W3).
type RunView = 'cards' | 'report'
// Readout join keyed by sample; 'error' marks a readout that failed to load (the card still
// renders rule-derived content — a missing hero is a signal, not a crash).
type ReadoutState = Record<string, CardReadout | 'error'>

const FILTERS: CardFilter[] = ['all', 'attention', 'escalate', 'rerun', 'hold', 'proceed']
// Pipeline order for the QC-readout gate groups, so an injected placeholder group sorts into place.
// Pipeline order for building the full three-gate readout skeleton (hero shows all three).
const GATE_SEQUENCE: Gate[] = ['preflight', 'qc', 'variant']

export function RunDetail() {
  const { runId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  // Run detail + error come from the shared useRun cache (UX-DUP #2) — RunDetail, AgentTriage, and
  // Provenance no longer each fetch this heavy payload. `refresh` re-fetches after a release/retry.
  const { detail, error, refresh } = useRun(runId)
  const [readouts, setReadouts] = useState<ReadoutState>({})
  // Run-independent QC policy, backing the "QC gate ran but nothing measured" placeholder (S3).
  const [runbook, setRunbook] = useState<RunbookPolicy | null>(null)
  // Density is a saved user preference (persists across runs + refresh); it is now authored ONLY in
  // user Settings / the profile dialog (UIC-8 removed the per-page Layout control), so this screen
  // reads it but never sets it — default stays 'split' via PrefsContext.
  const { density } = usePrefs()
  // canSee gates inline cross-links (queue, provenance) so a restricted actor is never invited into
  // a RequirePage-gated dead-end — mirrors how the nav hides those pages (view-gate, not authz).
  const { canSee } = useAccess()
  // A released run short-circuits to the released panel and hides its cards. This latch lets the
  // operator override that terminal-state gate to inspect the per-sample cards/provenance anyway.
  const [inspectReleased, setInspectReleased] = useState(false)
  // Per-card open overrides + a screen-wide expand/collapse latch. Absent override → the
  // default (first card open, rest collapsed); expand/collapse-all clears the overrides.
  const [override, setOverride] = useState<Record<string, boolean>>({})
  const [allState, setAllState] = useState<'all' | 'none' | null>(null)
  // A full flowcell can carry 100+ per-sample cards, so the list is paginated (scale-aware rule,
  // 25/50/100). Page state lives here so it survives a render; it resets on run/filter change below.
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState<PerPage>('25')

  // Reset the per-card open/expand overrides + readouts whenever the run changes (the detail itself
  // is supplied by useRun; this effect no longer fetches it).
  useEffect(() => {
    setOverride({})
    setAllState(null)
    setReadouts({})
  }, [runId])

  // Fan out each card's QC readout once the (cached or freshly fetched) detail arrives — the hero
  // table + honest header chips come from this api projection; a failure degrades one card, never
  // the screen. Skips running (no final cards) / released (cards hidden) runs. Keyed on `detail` so
  // it re-runs after a refresh() re-fetch, and on runId so a stale run's readouts never land.
  useEffect(() => {
    if (!detail) return
    if (detail.summary.status === 'running' || detail.summary.status === 'released') return
    let cancelled = false
    for (const c of detail.cards) {
      api
        .qcReadout(runId, c.sample_id)
        .then((rd) => !cancelled && setReadouts((m) => ({ ...m, [c.sample_id]: rd })))
        .catch(() => !cancelled && setReadouts((m) => ({ ...m, [c.sample_id]: 'error' })))
    }
    return () => {
      cancelled = true
    }
  }, [detail, runId])

  // A released run hides its cards, so the main effect never fetches their QC readouts. When the
  // operator opts to inspect anyway (inspectReleased), fan out the readout fetch on demand so the
  // revealed cards carry the same metric hero as any other run — a degraded readout stays honest.
  useEffect(() => {
    if (!inspectReleased || !detail || detail.summary.status !== 'released') return
    let cancelled = false
    for (const c of detail.cards) {
      api
        .qcReadout(runId, c.sample_id)
        .then((rd) => !cancelled && setReadouts((m) => ({ ...m, [c.sample_id]: rd })))
        .catch(() => !cancelled && setReadouts((m) => ({ ...m, [c.sample_id]: 'error' })))
    }
    return () => {
      cancelled = true
    }
  }, [inspectReleased, detail, runId])

  // Reset the released-inspection latch when the run changes, so switching runs starts fresh at the
  // released panel rather than carrying a prior run's reveal.
  useEffect(() => {
    setInspectReleased(false)
  }, [runId])

  // The runbook is run-independent QC policy — fetch once. It backs the not-measured placeholder;
  // a failure just leaves it null and the readout hero degrades to hiding (the pre-S3 behavior).
  useEffect(() => {
    let cancelled = false
    api
      .runbook()
      .then((rb) => !cancelled && setRunbook(rb))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  // The URL owns the top-level view (`?view=report`) so a Report deep-link / refresh is stable,
  // sitting alongside the verdict `?filter`. Unknown values fall back to the decision cards.
  const view: RunView = searchParams.get('view') === 'report' ? 'report' : 'cards'
  const setView = (v: RunView) =>
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev)
        if (v === 'cards') p.delete('view')
        else p.set('view', v)
        return p
      },
      { replace: true },
    )

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

  // Reset to the first page when the run or the verdict filter changes — a stale page could
  // otherwise land past the (new, shorter) last page.
  useEffect(() => {
    setPage(1)
  }, [filter, runId])

  // UIC-1: the nav + top-bar run switcher already name the page and the active run, so the header
  // is just a concise title — the eyebrow, the descriptive subtitle (run id/platform/date/samples,
  // still shown per-card in the context rail), and the Layout control are all gone.
  return (
    <div className="mx-auto max-w-[1080px]">
      <PageHeader title={view === 'report' ? 'Run report' : 'Decision cards'} />
      {renderBody()}
    </div>
  )

  // The top-level Decision-cards ↔ Report view switch (W3). Shown once the run has decided cards
  // to render (hidden on running/released/error states, where there is nothing to switch between).
  function viewTabs() {
    return (
      <div className="mb-4">
        <Tabs<RunView>
          items={[
            { value: 'cards', label: 'Decision cards' },
            { value: 'report', label: 'Report' },
          ]}
          value={view}
          onChange={setView}
        />
      </div>
    )
  }

  function renderBody() {
    if (error) return <ErrorBox message={error} onRetry={() => refresh()} />
    if (!detail) return <DecisionLoading />
    if (detail.summary.status === 'running') return <DecisionLoading />
    if (detail.summary.status === 'released' && !inspectReleased) {
      return (
        <div className="flex flex-col items-center gap-3.5">
          <DecisionReleased count={detail.summary.n_samples} />
          {/* Inspection shouldn't be gated by the terminal state — expose the per-sample cards +
              provenance from here too. Provenance is RequirePage-gated, so only offer that link
              when this actor can see the page (mirrors how the nav hides it). */}
          <div className="flex flex-wrap items-center justify-center gap-2.5">
            <button
              onClick={() => setInspectReleased(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3.5 py-2 text-[13px] font-medium text-text transition-colors hover:border-text-3"
            >
              <FileText size={14} /> View cards anyway
            </button>
            {canSee('provenance') && (
              <Link
                to={`/runs/${runId}/provenance`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3.5 py-2 text-[13px] font-medium text-text transition-colors hover:border-text-3"
              >
                <GitBranch size={14} /> Open provenance
              </Link>
            )}
          </div>
        </div>
      )
    }

    if (view === 'report') {
      return (
        <>
          {viewTabs()}
          <RunReport detail={detail} />
        </>
      )
    }

    const counts = detail.summary.counts
    const cards = [...detail.cards].sort(
      (a, b) => VERDICT_ORDER[a.verdict] - VERDICT_ORDER[b.verdict] || a.sample_id.localeCompare(b.sample_id),
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

    // Paginate the (sorted, filtered) card list; clamp so a narrowing filter can't strand the pager.
    const per = Number(perPage)
    const pageCount = Math.max(1, Math.ceil(filtered.length / per))
    const curPage = Math.min(page, pageCount)
    const pageCards = filtered.slice((curPage - 1) * per, curPage * per)

    return (
      <>
        {viewTabs()}

        {synthesisError && <DecisionSynthesisError onRetry={() => refresh()} />}

        <DecisionVerdictBar counts={counts} />

        {detail.summary.n_attention > 0 && (
          <div className="mt-3.5 flex items-center gap-3 rounded-[12px] border border-hold-bd bg-hold-bg px-4 py-3">
            <div className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-[9px] border border-hold-bd bg-white">
              <AlertTriangle size={18} strokeWidth={2} className="text-hold" />
            </div>
            <div className="flex-1 text-[13.5px] text-hold-fg">
              <b>{detail.summary.n_attention} sample(s) need operator attention</b> before this run can be released.
            </div>
            {/* The review queue is RequirePage-gated — only invite the actor there when they can
                see the page, so a restricted user isn't sent into an access-denied dead-end. */}
            {canSee('queue') && (
              <Link
                to="/queue"
                className="whitespace-nowrap rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-text-3"
              >
                Open review queue
              </Link>
            )}
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <div className="min-w-0 flex-1">
            <Tabs<CardFilter>
              items={chips.map((c) => ({ value: c.key, label: c.label, count: c.count }))}
              value={filter}
              onChange={setFilter}
            />
          </div>
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
          <>
            <div className="mt-4 flex flex-col gap-[13px]">
              {pageCards.map((card, idx) => {
                const open = isOpen(card, idx)
                const rd = readouts[card.sample_id]
                const readout = rd && rd !== 'error' ? rd : null
                return (
                  <CollapsibleRow
                    key={card.sample_id}
                    open={open}
                    onToggle={() => setOverride((o) => ({ ...o, [card.sample_id]: !open }))}
                    header={<CardHead card={card} header={readout?.header ?? null} />}
                  >
                    <CardBody
                      runId={runId}
                      card={card}
                      density={density}
                      readout={readout}
                      runbook={runbook}
                      platform={detail!.summary.platform}
                      date={detail!.summary.run_date}
                    />
                  </CollapsibleRow>
                )
              })}
            </div>
            <Pager
              total={filtered.length}
              page={curPage}
              perPage={perPage}
              onPage={setPage}
              onPerPage={(p) => {
                setPerPage(p)
                setPage(1)
              }}
              noun="cards"
            />
          </>
        )}
      </>
    )
  }
}

// Where a card's verdict originated — verb + gate tag + dot for the header origin chip.
function originInfo(card: DecisionCard): { verb: string; tag: string; dot: string } {
  if (card.verdict === 'proceed') return { verb: 'Cleared at', tag: 'All gates', dot: 'bg-proceed' }
  const verb = card.verdict === 'rerun' ? 'Failed at' : 'Flagged at'
  const gate = governingGate(card)
  if (!gate) return { verb, tag: 'Operational', dot: 'bg-warn' }
  return { verb, tag: GATE_TAG[gate], dot: GATE_DOT[gate] }
}

function CardHead({ card, header }: { card: DecisionCard; header: CardHeader | null }) {
  const oi = originInfo(card)
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <VerdictBadge verdict={card.verdict} />
      <span className="shrink-0 font-mono text-[16px] font-semibold text-text">{card.sample_id}</span>
      <Truncate text={card.headline} className="min-w-0 flex-1 text-[13.5px] font-medium text-text" />
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

// UIC-8 / ADR-0001: the Claude-generated narration + "recommended next steps" are the ONLY
// AI-authored content on a card. Framing them as one bordered, explicitly-labelled "advisory"
// block (placed *under* the rules-derived metric tables + cited evidence) keeps the separation
// legible: evidence reads first, the synthesizer's narration reads second and never sets a
// verdict. Renders nothing when the synthesizer produced neither (a blank rationale on a card
// with findings is surfaced by the run-level synthesis-error banner instead).
function AiNarration({
  rationale,
  steps,
  variant,
}: {
  rationale: string | null
  steps: string[]
  variant: 'arrow' | 'numbered'
}) {
  if (!rationale?.trim() && steps.length === 0) return null
  return (
    <div className="mt-4 rounded-[10px] border border-line bg-card-2 px-4 py-3.5">
      <SectionLabel className="flex items-center gap-1.5">
        <Sparkles size={12} className="text-accent" />
        AI narration (advisory)
      </SectionLabel>
      {rationale?.trim() && <p className="mt-2.5 text-[13.5px] leading-[1.6] text-text">{rationale}</p>}
      <NextSteps steps={steps} variant={variant} />
    </div>
  )
}

// WS-07 Q1: the AI-off suggestion surface. Instead of fabricated per-verdict "next steps", the
// stub card points the operator at the REAL QC artifacts — the run's fastp.html / multiqc_report
// .html reports if published, always alongside the metric readout above. Each link opens the
// read-only inline artifact-serve endpoint. When the run published no HTML report (e.g. a CSV-only
// synthetic run), the absence is stated honestly — never boilerplate advice. When Claude authored
// the narration, the "Recommended next steps" in AiNarration are real; this block complements it.
function QcReports({ reports }: { reports: QcReportLink[] }) {
  return (
    <>
      <SectionLabel className="mt-4">QC reports</SectionLabel>
      {reports.length === 0 ? (
        <p className="mt-2 text-[12.5px] leading-[1.5] text-text-3">
          No QC report artifact was published for this run — review the metric readout above.
        </p>
      ) : (
        <div className="mt-2 flex flex-wrap gap-2">
          {reports.map((r) => (
            <a
              key={r.name}
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-text-3"
            >
              <FileText size={14} className="text-accent" />
              {r.label}
              {r.scope === 'run' && <span className="text-text-3">· run</span>}
            </a>
          ))}
        </div>
      )}
    </>
  )
}

function CleanPanel({
  coverage,
  brief = false,
}: {
  coverage: CheckCoverage | null
  brief?: boolean
}) {
  // Honest clean-card message (WS-01): "no issues in the checks that RAN", never "every check
  // passed" — contamination/identity have no check today, so name them as not-examined.
  const notRun = coverage?.not_examined ?? []
  return (
    <div className="mt-4 flex items-start gap-2.5 rounded-[10px] border border-proceed-bd bg-proceed-bg px-3.5 py-3">
      <CheckCircle2 size={18} strokeWidth={2} className="mt-0.5 shrink-0 text-proceed" />
      <span className={`${brief ? 'text-[13.5px]' : 'text-[13px]'} text-proceed-fg`}>
        {coverage
          ? `No issues found in the ${coverage.checks_ran} of ${coverage.checks_expected} check categories that ran.`
          : 'No issues found in the checks that ran.'}
        {notRun.length > 0 && (
          <span className="opacity-70">
            {' '}
            {notRun.join(', ')} not examined — no check for {notRun.length === 1 ? 'it' : 'them'}{' '}
            exists yet.
          </span>
        )}
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
  runbook,
  platform,
  date,
}: {
  runId: string
  card: DecisionCard
  density: Density
  readout: CardReadout | null
  runbook: RunbookPolicy | null
  platform: string | null
  date: string | null
}) {
  // Build the full three-gate readout so the card shows the whole pipeline architecture, not just
  // the one gate that happened to carry metrics. Per gate, in pipeline order:
  //   1. the real projection group if it measured anything;
  //   2. else, when the gate ran but measured nothing, the runbook thresholds as `not_measured`
  //      placeholder rows (keeps QC checks visible instead of dropping the hero — S3);
  //   3. else an honest empty-state note (preflight is rule-based; variant extracts no metrics),
  //      so the gate keeps its place without fabricating rows.
  // Status stays rules-derived (never a confidence meter); a missing runbook degrades gracefully.
  const realByGate = new Map(readout?.readout.gates.map((g) => [g.gate, g as ReadoutGroup]) ?? [])
  const gateRan = (gate: Gate) => card.gate_results.some((g) => g.gate === gate)
  // Gate dependency (mirrors card_readout._blocking_gate): a downstream gate is "blocked" when an
  // upstream gate isn't clear. The API-projected groups already carry blocked_by; the placeholder /
  // empty groups the frontend synthesizes need it computed from the card's gate_results too.
  const unclearGates = new Set(card.gate_results.filter((g) => g.verdict !== 'proceed').map((g) => g.gate))
  const blockingGate = (gate: Gate): Gate | null => {
    const idx = GATE_SEQUENCE.indexOf(gate)
    for (let i = idx - 1; i >= 0; i--) if (unclearGates.has(GATE_SEQUENCE[i])) return GATE_SEQUENCE[i]
    return null
  }
  const gates: ReadoutGroup[] = GATE_SEQUENCE.map((gate) => {
    const real = realByGate.get(gate)
    if (real && real.rows.length > 0) return real
    const placeholder = gateRan(gate) && runbook ? notMeasuredGroup(gate, runbook) : null
    const g = placeholder ?? emptyGateGroup(gate)
    return g ? { ...g, blocked_by: blockingGate(gate) } : null
  }).filter((g): g is ReadoutGroup => g !== null)
  const hasReadout = gates.some((g) => g.rows.length > 0 || g.note)
  // Same canSee gate as the run-level cross-links: never invite a restricted actor into a
  // RequirePage-gated page (provenance / agent) from a card's rail either.
  const { canSee } = useAccess()
  const hasFindings = card.findings.length > 0
  const clean = card.verdict === 'proceed'
  const actionable = card.verdict !== 'proceed'
  const agentTo = `/runs/${runId}/agent?sample=${encodeURIComponent(card.sample_id)}`

  // Feedback keys — the exact call the operator reacts to (verdict + gate + rule ids + hash).
  const fbGate = governingGate(card)
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
              {/* Evidence/tables first (rules-derived), then the AI narration block (advisory). */}
              {hasFindings ? (
                <>
                  <SectionLabel>Supporting evidence · cited</SectionLabel>
                  <div className="mt-2.5">
                    <CitedEvidence findings={card.findings} variant="split" />
                  </div>
                </>
              ) : clean ? (
                <CleanPanel coverage={card.check_coverage} />
              ) : null}
              <AiNarration rationale={card.rationale} steps={card.next_steps} variant="arrow" />
              <QcReports reports={readout?.qc_reports ?? []} />
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
          {/* Evidence/tables first (rules-derived), then the AI narration block (advisory). */}
          {hasFindings ? (
            <>
              <SectionLabel>Cited evidence</SectionLabel>
              <div className="mt-2.5">
                <CitedEvidence findings={card.findings} variant="brief" />
              </div>
            </>
          ) : clean ? (
            <CleanPanel coverage={card.check_coverage} brief />
          ) : null}
          {hasReadout && (
            <>
              <SectionLabel className="mt-5 border-t border-line pt-4">QC readout by gate</SectionLabel>
              <div className="mt-2.5">
                <QCReadout gates={gates} variant="brief" />
              </div>
            </>
          )}
          <AiNarration rationale={card.rationale} steps={card.next_steps} variant="numbered" />
          <QcReports reports={readout?.qc_reports ?? []} />
          <div className="mt-3.5 flex gap-2.5">
            {canSee('provenance') && (
              <RailButton to={`/runs/${runId}/provenance`}>
                <GitBranch size={14} /> View lineage
              </RailButton>
            )}
            {actionable && canSee('agent') && (
              <RailButton to={agentTo} accent>
                <Sparkles size={14} /> Ask agent to triage
              </RailButton>
            )}
          </div>
        </div>
      )}

      {density === 'dense' && (
        <div className="px-[18px] py-[13px]">
          {/* Evidence/tables first (rules-derived); the AI narration reads last, in a compact
              labelled advisory block — dense drops the recommended-next-steps list to stay terse. */}
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
          {card.rationale?.trim() && (
            <div className="mt-2.5 rounded-[9px] border border-line bg-card-2 px-3 py-2.5">
              <SectionLabel className="flex items-center gap-1.5">
                <Sparkles size={12} className="text-accent" />
                AI narration (advisory)
              </SectionLabel>
              <div className="mt-1.5 text-[12.5px] leading-[1.5] text-text-2">{card.rationale}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
