import { type MouseEvent, type ReactNode, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ArrowDownToLine, ArrowUpFromLine, ChevronRight, ExternalLink } from 'lucide-react'
import { api } from '../api'
import { PageHeader } from '../components/PageHeader'
import { ErrorBox, Loading } from '../components/States'
import type { Gate, PipelineStage, RunArtifact, RunDetail, Verdict } from '../types'
import { GATE_DOT, VERDICT_LABEL } from '../verdict'

// Fixed pipeline lineage (§5.6). Tools describe what this build actually touches: it starts
// from FASTQ, so alignment/variant-calling are shown but marked "not run in this build" (no
// artifacts) rather than fabricating an aligner/caller run — the honesty guardrail wins over
// the prototype's populated-looking mock.
const STAGES: { key: PipelineStage; n: number; title: string; tool: string; gate?: Gate }[] = [
  { key: 'intake', n: 1, title: 'Sample intake', tool: 'Sample sheet + metadata' },
  { key: 'demux', n: 2, title: 'Demultiplex', tool: 'demux stats', gate: 'preflight' },
  { key: 'qc', n: 3, title: 'Quality control', tool: 'fastp · mosdepth', gate: 'qc' },
  { key: 'align', n: 4, title: 'Alignment', tool: 'not run in this build' },
  { key: 'variant', n: 5, title: 'Variant calling', tool: 'not run in this build', gate: 'variant' },
  { key: 'gate', n: 6, title: 'Decision gate', tool: 'PipeGuard rules' },
]

type Status = 'ok' | 'warn' | 'blocked' | 'skipped'
type Stage = (typeof STAGES)[number]
const VERDICT_RANK: Record<Verdict, number> = { escalate: 0, rerun: 1, hold: 2, proceed: 3 }

// Nodes color by STAGE STATUS ONLY (§5.6). The number badge is the primary signal: a solid
// status fill; the detail badge/pill use the tinted treatment (bg + solid border + solid text).
// `skipped` stays deliberately neutral — the app declines to color a stage it never ran.
const STATUS_STYLE: Record<
  Status,
  { numBadge: string; dot: string; headBadge: string; pill: string; label: string }
> = {
  ok: {
    numBadge: 'bg-proceed text-white',
    dot: 'bg-proceed',
    headBadge: 'bg-proceed-bg border-proceed text-proceed',
    pill: 'bg-proceed-bg border-proceed text-proceed',
    label: 'Completed',
  },
  warn: {
    numBadge: 'bg-hold text-white',
    dot: 'bg-hold',
    headBadge: 'bg-hold-bg border-hold text-hold',
    pill: 'bg-hold-bg border-hold text-hold',
    label: 'Completed with warnings',
  },
  blocked: {
    numBadge: 'bg-escalate text-white',
    dot: 'bg-escalate',
    headBadge: 'bg-escalate-bg border-escalate text-escalate',
    pill: 'bg-escalate-bg border-escalate text-escalate',
    label: 'Awaiting review',
  },
  skipped: {
    numBadge: 'bg-line-strong text-white',
    dot: 'bg-line-strong',
    headBadge: 'bg-card-2 border-line text-text-3',
    pill: 'bg-card-2 border-line text-text-3',
    label: 'Not run in this build',
  },
}

// Gate pill tags per the handoff (note the asymmetry — preflight has no "gate" suffix).
const GATE_TAG: Record<Gate, string> = { preflight: 'Preflight', qc: 'QC gate', variant: 'Variant gate' }

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(1)} GB`
}

export function Provenance() {
  const { runId = '' } = useParams()
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [artifacts, setArtifacts] = useState<RunArtifact[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<PipelineStage | null>(null)

  useEffect(() => {
    setDetail(null)
    setArtifacts(null)
    setSelected(null)
    api.run(runId).then(setDetail).catch((e) => setError(String(e)))
    api.artifacts(runId).then(setArtifacts).catch(() => setArtifacts([]))
  }, [runId])

  // Worst (most-urgent) verdict each gate produced across the run's samples, and overall —
  // the canvas colors a stage by the gate checkpoint that sits on it. The rules already
  // decided these (ADR-0001); the canvas only visualizes them.
  const { gateWorst, runWorst } = useMemo(() => {
    const gateWorst: Record<Gate, Verdict | null> = { preflight: null, qc: null, variant: null }
    let runWorst: Verdict = 'proceed'
    if (detail) {
      for (const c of detail.cards) {
        if (VERDICT_RANK[c.verdict] < VERDICT_RANK[runWorst]) runWorst = c.verdict
        for (const g of c.gate_results) {
          const cur = gateWorst[g.gate]
          if (cur === null || VERDICT_RANK[g.verdict] < VERDICT_RANK[cur]) gateWorst[g.gate] = g.verdict
        }
      }
    }
    return { gateWorst, runWorst }
  }, [detail])

  const statusFor = useMemo(() => {
    return (stage: Stage): Status => {
      const arts = artifacts?.filter((a) => a.stage === stage.key) ?? []
      if ((stage.key === 'align' || stage.key === 'variant') && arts.length === 0) return 'skipped'
      if (stage.gate) {
        const w = gateWorst[stage.gate]
        if (w === 'escalate') return 'blocked'
        if (w === 'hold' || w === 'rerun') return 'warn'
      }
      if (stage.key === 'gate') {
        if (runWorst === 'escalate') return 'blocked'
        if (runWorst !== 'proceed') return 'warn'
      }
      return 'ok'
    }
  }, [artifacts, gateWorst, runWorst])

  if (error) return <ErrorBox message={error} />
  if (!detail || !artifacts) return <Loading label="Loading provenance…" />

  // Per-stage note for the drill-in band. Gate stages carry the worst gate result's rationale
  // (rules-authored); non-gate stages get an honest derived note — never a fabricated one.
  const noteFor = (stage: Stage): string => {
    if (stage.gate) {
      const results = detail.cards.flatMap((c) => c.gate_results).filter((g) => g.gate === stage.gate)
      if (results.length) {
        const worst = results.reduce((a, b) => (VERDICT_RANK[b.verdict] < VERDICT_RANK[a.verdict] ? b : a))
        if (worst.rationale) return worst.rationale
      }
    }
    const n = detail.cards.length
    switch (stage.key) {
      case 'intake':
        return `${n} sample${n === 1 ? '' : 's'} registered from the sample sheet.`
      case 'align':
        return 'Not run in this build — lineage starts from FASTQ; alignment provenance is future work.'
      case 'variant':
        return 'Not run in this build — variant-calling provenance is future work.'
      case 'gate':
        return `Aggregates the three gates → overall verdict ${VERDICT_LABEL[runWorst]}.`
      default:
        return 'No stage note captured for this stage.'
    }
  }

  // Default the drill-in to the first stage that flagged (most interesting), else the gate.
  const firstFlagged = STAGES.find((s) => statusFor(s) === 'blocked' || statusFor(s) === 'warn')
  const active = selected ?? firstFlagged?.key ?? 'gate'
  const activeStage = STAGES.find((s) => s.key === active) ?? STAGES[STAGES.length - 1]
  const activeStatus = statusFor(activeStage)
  const sc = STATUS_STYLE[activeStatus]
  const stageArts = artifacts.filter((a) => a.stage === activeStage.key)
  const inputs = stageArts.filter((a) => a.role === 'input')
  const outputs = stageArts.filter((a) => a.role === 'output')

  return (
    <div className="mx-auto max-w-[1080px]">
      <PageHeader
        eyebrow="Lineage"
        title="Provenance"
        subtitle={
          <>
            Read-only lineage for <span className="font-mono text-text">{detail.run_id}</span>. Click a stage to
            inspect its data I/O.
          </>
        }
      />

      {/* Left→right stage DAG — nodes stretch equally with auto-width chevrons between. */}
      <div
        className="mt-[18px] grid items-stretch gap-1 px-0.5 pb-2.5 pt-1.5"
        style={{ gridTemplateColumns: 'repeat(5, minmax(0,1fr) auto) minmax(0,1fr)' }}
      >
        {STAGES.flatMap((stage, i) => {
          const status = statusFor(stage)
          const s = STATUS_STYLE[status]
          const isActive = stage.key === active
          const cells: ReactNode[] = [
            <button
              key={stage.key}
              onClick={() => setSelected(stage.key)}
              className={`flex w-full flex-col gap-[7px] overflow-hidden rounded-xl border bg-card p-3 text-left transition-shadow ${
                isActive ? 'border-accent shadow-card ring-[3px] ring-accent-weak' : 'border-line'
              }`}
            >
              <div className="flex w-full items-center justify-between">
                <span
                  className={`grid h-[22px] w-[22px] place-items-center rounded-[7px] font-mono text-[12px] font-semibold ${s.numBadge}`}
                >
                  {stage.n}
                </span>
                <span
                  className={`h-[9px] w-[9px] rounded-full shadow-[0_0_0_3px_var(--color-page)] ${s.dot}`}
                  title={s.label}
                />
              </div>
              <div className="text-left text-[12.5px] font-semibold leading-[1.25] text-text">{stage.title}</div>
              <div className="max-w-full truncate text-left font-mono text-[9.5px] text-text-3">{stage.tool}</div>
              {stage.gate && (
                <span className="inline-flex max-w-full items-center gap-1 self-start whitespace-nowrap rounded-full border border-line bg-page px-[7px] py-0.5 text-[8.5px] font-semibold uppercase text-text-2">
                  <span className={`h-[5px] w-[5px] shrink-0 rounded-full ${GATE_DOT[stage.gate]}`} />
                  {GATE_TAG[stage.gate]}
                </span>
              )}
            </button>,
          ]
          if (i < STAGES.length - 1) {
            cells.push(
              <div key={`chev-${stage.key}`} className="flex shrink-0 items-center px-[3px]">
                <ChevronRight size={16} strokeWidth={2.4} className="text-line-strong" />
              </div>,
            )
          }
          return cells
        })}
      </div>

      {/* Drill-in: header · note bar · I/O grid */}
      <div className="mt-[14px] overflow-hidden rounded-[14px] border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.05)]">
        <div className="flex items-center gap-[13px] border-b border-line px-5 py-4">
          <span
            className={`grid h-9 w-9 shrink-0 place-items-center rounded-[9px] border font-mono text-[15px] font-semibold ${sc.headBadge}`}
          >
            {activeStage.n}
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-base font-semibold text-text">{activeStage.title}</div>
            <div className="font-mono text-[11.5px] text-text-3">{activeStage.tool}</div>
          </div>
          <span
            className={`shrink-0 rounded-full border px-[11px] py-1 text-[11px] font-semibold uppercase tracking-[0.3px] ${sc.pill}`}
          >
            {sc.label}
          </span>
        </div>

        {/* Per-stage note bar — shown for every stage. */}
        <div className="border-b border-line bg-card-2 px-5 py-[11px] text-[12.5px] leading-[1.5] text-text-2">
          {noteFor(activeStage)}
        </div>

        <div className="grid grid-cols-2">
          <ProvColumn icon={<ArrowDownToLine size={14} strokeWidth={2} />} label="Inputs" refs={inputs} />
          <ProvColumn
            icon={<ArrowUpFromLine size={14} strokeWidth={2} />}
            label="Outputs"
            refs={outputs}
            className="border-l border-line"
          />
        </div>
      </div>
    </div>
  )
}

function ProvColumn({
  icon,
  label,
  refs,
  className = '',
}: {
  icon: ReactNode
  label: string
  refs: RunArtifact[]
  className?: string
}) {
  return (
    <div className={`px-5 py-4 ${className}`}>
      <div className="flex items-center gap-[7px] text-[11px] font-semibold uppercase tracking-[0.5px] text-text-3">
        {icon}
        {label}
      </div>
      <div className="mt-1.5">
        {refs.length === 0 ? (
          <p className="py-[11px] font-mono text-[12px] text-text-3">—</p>
        ) : (
          refs.map((a) => <ProvArtifactRow key={a.name} art={a} />)
        )}
      </div>
    </div>
  )
}

// Every artifact is a link (§5.6): open-in-store / copy-digest / download. RunArtifact carries
// no URL yet, so open/download are graceful no-ops; copy-digest works client-side off the sha256.
function ProvArtifactRow({ art }: { art: RunArtifact }) {
  const [copied, setCopied] = useState(false)

  const copyDigest = () => {
    if (!art.sha256) return
    void navigator.clipboard?.writeText(art.sha256).then(
      () => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      },
      () => {},
    )
  }
  // No artifact URL in the contract yet — keep open/download honest no-ops rather than fake a link.
  const noop = (e: MouseEvent) => e.preventDefault()

  return (
    <div className="border-b border-line py-[11px]">
      <div className="flex items-center justify-between gap-2">
        <a
          href="#"
          onClick={noop}
          title="Open artifact in store"
          className="inline-flex items-center gap-[5px] break-all font-mono text-[12.5px] font-medium text-accent-strong hover:underline"
        >
          <ExternalLink size={12} strokeWidth={1.9} className="shrink-0" />
          {art.name}
        </a>
      </div>
      <div className="mt-[5px] flex items-center gap-[10px]">
        {art.sha256 ? (
          <button
            type="button"
            onClick={copyDigest}
            title="Copy digest"
            className="font-mono text-[11px] text-accent-strong hover:underline"
          >
            {copied ? 'copied ✓' : `sha256:${art.sha256.slice(0, 12)}…`}
          </button>
        ) : (
          <span className="font-mono text-[11px] text-text-3">sha256 n/a</span>
        )}
        <span className="text-[11px] text-text-3">{fmtSize(art.size_bytes)}</span>
        <span className="text-[11px] text-text-3">·</span>
        <a href="#" onClick={noop} title="Download artifact" className="text-[11px] text-accent-strong hover:underline">
          download
        </a>
      </div>
    </div>
  )
}
