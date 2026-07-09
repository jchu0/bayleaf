import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ArrowDownToLine, ArrowUpFromLine, ChevronRight } from 'lucide-react'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/States'
import type { Gate, PipelineStage, RunArtifact, RunDetail, Verdict } from '../types'
import { GATE_LABEL } from '../verdict'

// Fixed pipeline lineage (§5). Tools describe what this build actually touches: it starts
// from FASTQ, so alignment/variant-calling are shown but marked "not run in this build"
// (no artifacts) rather than fabricating an aligner/caller run we didn't execute.
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

const STATUS_DOT: Record<Status, string> = {
  ok: 'bg-proceed',
  warn: 'bg-hold',
  blocked: 'bg-escalate',
  skipped: 'bg-line-strong',
}
const STATUS_PILL: Record<Status, { label: string; cls: string }> = {
  ok: { label: 'Completed', cls: 'border-proceed-bd bg-proceed-bg text-proceed-fg' },
  warn: { label: 'Completed with warnings', cls: 'border-hold-bd bg-hold-bg text-hold-fg' },
  blocked: { label: 'Blocked', cls: 'border-escalate-bd bg-escalate-bg text-escalate-fg' },
  skipped: { label: 'Not run in this build', cls: 'border-line bg-card-2 text-text-3' },
}
const ORIGIN_CHIP: Record<string, string> = {
  'real-giab': 'border-preflight/40 bg-preflight/10 text-preflight',
  synthetic: 'border-hold-bd bg-hold-bg text-hold-fg',
  contrived: 'border-line bg-card-2 text-text-3',
  unknown: 'border-line bg-card-2 text-text-3',
}

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

  // Default the drill-in to the first stage that flagged (most interesting), else the gate.
  const firstFlagged = STAGES.find((s) => statusFor(s) === 'blocked' || statusFor(s) === 'warn')
  const active = selected ?? firstFlagged?.key ?? 'gate'
  const activeStage = STAGES.find((s) => s.key === active) ?? STAGES[STAGES.length - 1]
  const origin = artifacts[0]?.origin ?? 'unknown'

  return (
    <div className="mx-auto max-w-[1080px]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-text">Provenance</h1>
          <p className="mt-1 text-[13px] text-text-2">
            Read-only lineage for <span className="font-mono text-text-3">{detail.run_id}</span>. Click a stage to
            inspect its data I/O.
          </p>
        </div>
        <span
          className={`rounded-full border px-2.5 py-1 text-[10.5px] font-semibold uppercase tracking-wide ${ORIGIN_CHIP[origin] ?? ORIGIN_CHIP.unknown}`}
        >
          {origin}
        </span>
      </div>

      {/* Horizontal DAG */}
      <div className="mt-5 flex items-stretch gap-1.5 overflow-x-auto pb-1">
        {STAGES.map((stage, i) => {
          const status = statusFor(stage)
          const isActive = stage.key === active
          return (
            <div key={stage.key} className="flex items-stretch gap-1.5">
              <button
                onClick={() => setSelected(stage.key)}
                className={`w-[150px] shrink-0 rounded-xl border bg-card p-3 text-left shadow-card transition-colors ${
                  isActive ? 'border-accent ring-1 ring-accent/30' : 'border-line hover:border-line-strong'
                } ${status === 'skipped' ? 'opacity-70' : ''}`}
              >
                <div className="flex items-center justify-between">
                  <span className="grid h-5 w-5 place-items-center rounded-full bg-card-2 font-mono text-[11px] font-semibold text-text-2">
                    {stage.n}
                  </span>
                  <span className={`h-2 w-2 rounded-full ${STATUS_DOT[status]}`} title={STATUS_PILL[status].label} />
                </div>
                <div className="mt-2 text-[13px] font-semibold text-text">{stage.title}</div>
                <div className="mt-0.5 truncate text-[11px] text-text-3">{stage.tool}</div>
                {stage.gate && (
                  <div className="mt-2 inline-flex items-center gap-1 rounded border border-line bg-card-2 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-text-2">
                    {GATE_LABEL[stage.gate]} gate
                  </div>
                )}
              </button>
              {i < STAGES.length - 1 && <ChevronRight size={16} className="my-auto shrink-0 text-text-3" />}
            </div>
          )
        })}
      </div>

      {/* Drill-in */}
      <StageDrillIn
        stage={activeStage}
        status={statusFor(activeStage)}
        artifacts={artifacts.filter((a) => a.stage === activeStage.key)}
        rationale={
          activeStage.gate
            ? detail.cards.flatMap((c) => c.gate_results).find((g) => g.gate === activeStage.gate)?.rationale ?? null
            : null
        }
      />
    </div>
  )
}

function StageDrillIn({
  stage,
  status,
  artifacts,
  rationale,
}: {
  stage: Stage
  status: Status
  artifacts: RunArtifact[]
  rationale: string | null
}) {
  const inputs = artifacts.filter((a) => a.role === 'input')
  const outputs = artifacts.filter((a) => a.role === 'output')
  const pill = STATUS_PILL[status]

  return (
    <section className="mt-4 rounded-xl border border-line bg-card p-5 shadow-card">
      <div className="flex flex-wrap items-center gap-3">
        <span className="grid h-6 w-6 place-items-center rounded-full bg-card-2 font-mono text-[12px] font-semibold text-text-2">
          {stage.n}
        </span>
        <div>
          <h3 className="text-[15px] font-semibold text-text">{stage.title}</h3>
          <p className="text-[11.5px] text-text-3">{stage.tool}</p>
        </div>
        <span className={`ml-auto rounded-full border px-2.5 py-1 text-[11px] font-medium ${pill.cls}`}>{pill.label}</span>
      </div>

      {rationale && <p className="mt-3 text-[13px] text-text-2">{rationale}</p>}

      {artifacts.length === 0 ? (
        <p className="mt-4 rounded-lg border border-dashed border-line-strong bg-card-2/40 px-4 py-6 text-center text-[12.5px] text-text-3">
          Not executed in this build — the pipeline starts from FASTQ. Alignment / variant lineage is future
          pipeline-provenance.
        </p>
      ) : (
        <div className="mt-4 grid gap-5 sm:grid-cols-2">
          <RefColumn icon={<ArrowDownToLine size={13} />} label="Inputs" refs={inputs} />
          <RefColumn icon={<ArrowUpFromLine size={13} />} label="Outputs" refs={outputs} />
        </div>
      )}
    </section>
  )
}

function RefColumn({ icon, label, refs }: { icon: ReactNode; label: string; refs: RunArtifact[] }) {
  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-3">
        {icon}
        {label}
      </p>
      {refs.length === 0 ? (
        <p className="text-[12px] text-text-3">—</p>
      ) : (
        <div className="space-y-2">
          {refs.map((a) => (
            <div key={a.name} className="rounded-lg border border-line bg-card-2/40 px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-[12.5px] text-text">{a.name}</span>
                <span
                  className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide ${ORIGIN_CHIP[a.origin] ?? ORIGIN_CHIP.unknown}`}
                >
                  {a.origin}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 font-mono text-[10.5px] text-text-3">
                {a.sha256 ? <span className="text-accent">sha256:{a.sha256.slice(0, 12)}</span> : <span>sha256: —</span>}
                <span>{fmtSize(a.size_bytes)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
