import { type ReactNode, useMemo, useState } from 'react'
import { ArrowDownToLine, ArrowUpFromLine, ChevronRight, ExternalLink } from 'lucide-react'
import type { Gate, PipelineStage, RunArtifact, RunDetail, Verdict } from '../../types'
import { GATE_DOT, VERDICT_LABEL } from '../../verdict'
import { artifactNameTitle, fmtSize } from '../../provenance'
import { Fingerprint } from './Fingerprint'

// The fixed-lineage DAG + drill-in, extracted from the old Provenance.tsx so it stays one of the
// three provenance views. Tools describe what this build actually touches: it starts from FASTQ, so
// alignment/variant-calling/filter are shown but marked "not run in this build" (no artifacts)
// rather than fabricating a run — the honesty guardrail wins over a populated-looking mock. The
// three post-variant stages (filter/normalize, route-to-human review, de-identified share) are
// honest downstream nodes (W3): each reads "not run in this build" unless THIS build actually
// produced its artifact or fired its rule. The route-to-human REVIEW node carries the variant gate
// (VAR-RTH-001) — so a fired ESCALATE surfaces there instead of the DAG lying "skipped" while the
// decision escalated (the CLINVAR-RTH honesty fix). Variant *calling* stays "not run" (no VCF),
// which is the honest read — the route-to-human check ran over externally-annotated calls.
const STAGES: { key: PipelineStage; n: number; title: string; tool: string; gate?: Gate }[] = [
  { key: 'intake', n: 1, title: 'Sample intake', tool: 'Sample sheet + metadata' },
  { key: 'demux', n: 2, title: 'Demultiplex', tool: 'demux stats', gate: 'preflight' },
  { key: 'qc', n: 3, title: 'Quality control', tool: 'fastp · mosdepth', gate: 'qc' },
  { key: 'align', n: 4, title: 'Alignment', tool: 'not run in this build' },
  { key: 'variant', n: 5, title: 'Variant calling', tool: 'not run in this build' },
  { key: 'filter', n: 6, title: 'Filter / normalize', tool: 'not run in this build' },
  { key: 'review', n: 7, title: 'Route to human', tool: 'route-to-human · VAR-RTH-001', gate: 'variant' },
  { key: 'gate', n: 8, title: 'Decision gate', tool: 'PipeGuard rules' },
  { key: 'share', n: 9, title: 'De-identified share', tool: 'Safe-Harbor-style scrub' },
]

// Downstream stages that only "run" when THIS build produced their artifact OR fired their gate/
// event; absent that signal they read "not run in this build" instead of a fabricated green. The
// review node's variant gate is the win-over signal for the CLINVAR-RTH escalate (see statusFor).
const CONDITIONAL_STAGES = new Set<PipelineStage>(['align', 'variant', 'filter', 'review', 'share'])

type Status = 'ok' | 'warn' | 'blocked' | 'skipped' | 'partial'
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
  // The terminal gate DECIDED, but on partial lineage (upstream stages didn't run) — a muted,
  // deliberately-not-green treatment so an incomplete sequence never ends in a confident "Completed".
  partial: {
    numBadge: 'bg-text-3 text-white',
    dot: 'bg-text-3',
    headBadge: 'bg-card-2 border-line-strong text-text-2',
    pill: 'bg-card-2 border-line-strong text-text-2',
    label: 'Decided on partial lineage',
  },
}

// Gate pill tags per the handoff (note the asymmetry — preflight has no "gate" suffix).
const GATE_TAG: Record<Gate, string> = { preflight: 'Preflight', qc: 'QC gate', variant: 'Variant gate' }

export function ProvenanceLineage({ detail, artifacts }: { detail: RunDetail; artifacts: RunArtifact[] }) {
  const [selected, setSelected] = useState<PipelineStage | null>(null)

  // Worst (most-urgent) verdict each gate produced across the run's samples, and overall —
  // the canvas colors a stage by the gate checkpoint that sits on it. The rules already
  // decided these (ADR-0001); the canvas only visualizes them.
  const { gateWorst, runWorst } = useMemo(() => {
    const gateWorst: Record<Gate, Verdict | null> = { preflight: null, qc: null, variant: null }
    let runWorst: Verdict = 'proceed'
    for (const c of detail.cards) {
      if (VERDICT_RANK[c.verdict] < VERDICT_RANK[runWorst]) runWorst = c.verdict
      for (const g of c.gate_results) {
        const cur = gateWorst[g.gate]
        if (cur === null || VERDICT_RANK[g.verdict] < VERDICT_RANK[cur]) gateWorst[g.gate] = g.verdict
      }
    }
    return { gateWorst, runWorst }
  }, [detail])

  // Whether a de-identified share left the boundary for this run (ADR-0018 D3): the presence of a
  // DATA_EXPORTED event is the "share ran" signal — a share writes no on-disk artifact, so the
  // event trail is its only honest evidence. Absent it, the Share stage reads "not run in this build".
  const shared = useMemo(() => detail.events.some((e) => e.event_type === 'data.exported'), [detail])

  // A downstream stage is "not run in this build" when it produced no artifact AND (for a gated
  // stage) its gate never fired anything actionable. This is the honesty short-circuit — BUT a
  // fired gate must WIN over it: the CLINVAR-RTH fixture carries only variants.csv (no .vcf), so
  // the review node has zero artifacts while VAR-RTH-001 ESCALATED it. Reading "skipped" there
  // would contradict the decision the rules already made, so a fired gate falls through to the
  // gate-status branch below (escalate → blocked, hold/rerun → warn).
  const isNotRun = (stage: Stage): boolean => {
    if (!CONDITIONAL_STAGES.has(stage.key)) return false
    if (stage.key === 'share') return !shared
    const arts = artifacts.filter((a) => a.stage === stage.key)
    const gv = stage.gate ? gateWorst[stage.gate] : null
    const gateFired = gv != null && gv !== 'proceed'
    return arts.length === 0 && !gateFired
  }

  const statusFor = (stage: Stage): Status => {
    if (isNotRun(stage)) return 'skipped'
    if (stage.gate) {
      const w = gateWorst[stage.gate]
      if (w === 'escalate') return 'blocked'
      if (w === 'hold' || w === 'rerun') return 'warn'
    }
    if (stage.key === 'gate') {
      if (runWorst === 'escalate') return 'blocked'
      if (runWorst !== 'proceed') return 'warn'
      // Proceed — but the DAG shows sequence, so a terminal green while upstream stages are gray
      // (skipped, not run in this build) is misleading (P3). Read "partial lineage" instead of a
      // clean green "Completed" whenever a processing stage upstream of the gate never ran.
      const upstreamSkipped = STAGES.some((s) => s.key !== 'gate' && s.key !== 'share' && isNotRun(s))
      if (upstreamSkipped) return 'partial'
    }
    return 'ok'
  }

  // Per-stage note for the drill-in band — every stage gets a real note, never an empty bar.
  // Gate stages prefer the worst gate result's rationale (rules-authored); when that's missing
  // (or whitespace-only), and for the ungated stages, we fall back to an honest derived status
  // note — a count/state we actually know, never a fabricated metric.
  const noteFor = (stage: Stage): string => {
    const n = detail.cards.length
    const plural = n === 1 ? '' : 's'

    // Alignment / variant calling / filter are honestly not run in this build (lineage starts from
    // FASTQ; no aligner/caller/filter produced an artifact). Short-circuit before the gate-rationale
    // lookup so a stray gate note can't surface on a stage that never ran.
    if (stage.key === 'align')
      return 'Not run in this build — lineage starts from FASTQ; alignment provenance is future work.'
    if (stage.key === 'variant')
      return 'Not run in this build — no in-build variant caller ran; the route-to-human check reads externally-annotated calls (variants.csv).'
    if (stage.key === 'filter')
      return 'Not run in this build — variant filtering / normalization provenance is future work.'
    // Route-to-human: prefer the fired variant-gate rationale (rules-authored, below). When the
    // policy is disarmed / no candidate matched, the gate produced nothing → honest "not run".
    if (stage.key === 'review' && isNotRun(stage))
      return 'Not run in this build — route-to-human (VAR-RTH-001) is off by default; no clinically-significant variant was routed for review this run.'
    // De-identified share (ADR-0018 D3): status/note come from the event trail, not an artifact.
    if (stage.key === 'share')
      return shared
        ? 'A de-identified report left the boundary for this run (DATA_EXPORTED) — see the Event trail. The scrub is a version, not a compliance attestation.'
        : 'Not run in this build — no de-identified report has been shared for this run.'

    if (stage.gate) {
      const results = detail.cards.flatMap((c) => c.gate_results).filter((g) => g.gate === stage.gate)
      if (results.length) {
        const worst = results.reduce((a, b) => (VERDICT_RANK[b.verdict] < VERDICT_RANK[a.verdict] ? b : a))
        if (worst.rationale.trim()) return worst.rationale
      }
    }

    switch (stage.key) {
      case 'intake':
        return `${n} sample${plural} registered from the sample sheet.`
      case 'demux':
        return `Demultiplexed ${n} sample${plural} from the sample sheet.`
      case 'qc': {
        // Honest fallback when the QC gate carried no rationale: report how many samples the
        // QC gate flagged (verdict below proceed), derived from the rules' own gate results.
        const flagged = detail.cards.filter((c) =>
          c.gate_results.some((g) => g.gate === 'qc' && g.verdict !== 'proceed'),
        ).length
        return flagged === 0
          ? `Per-sample QC ran across ${n} sample${plural}; none flagged.`
          : `Per-sample QC ran across ${n} sample${plural}; ${flagged} flagged.`
      }
      case 'gate': {
        const upstreamSkipped = STAGES.some((s) => s.key !== 'gate' && s.key !== 'share' && isNotRun(s))
        const base = `Aggregates the gates that ran → overall verdict ${VERDICT_LABEL[runWorst]}.`
        return upstreamSkipped
          ? `${base} Decided on partial lineage — one or more processing stages (alignment / variant calling / filter) didn't run in this build, so this isn't an end-to-end pass.`
          : base
      }
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
    <div>
      <p className="mb-[18px] text-[12.5px] text-text-2">Click a stage to inspect its data I/O.</p>

      {/* Left→right stage DAG — nodes stretch equally with auto-width chevrons between. Now 9
          stages (the 3 post-variant nodes added in W3), so the column template is derived from
          STAGES.length and the row scrolls sideways (min node width) instead of crushing every card. */}
      <div
        className="grid items-stretch gap-1 overflow-x-auto px-0.5 pb-2.5 pt-1.5"
        style={{ gridTemplateColumns: `repeat(${STAGES.length - 1}, minmax(104px,1fr) auto) minmax(104px,1fr)` }}
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

// Every artifact is a link (§5.6): open-in-store / copy-fingerprint / show-full / download — all
// wired to the real same-origin artifact URL (GET /api/runs/:id/artifacts/:name). The value is a
// CONTENT fingerprint of the file's bytes (a fixity/integrity check, not a process/task/ledger id —
// those are arun_… and evt_…). The copy/show-full behavior now lives in <Fingerprint>.
function ProvArtifactRow({ art }: { art: RunArtifact }) {
  return (
    <div className="border-b border-line py-[11px]">
      <div className="flex items-center justify-between gap-2">
        <a
          href={art.url}
          target="_blank"
          rel="noopener noreferrer"
          title={artifactNameTitle(art.name)}
          className="inline-flex items-center gap-[5px] break-all font-mono text-[12.5px] font-medium text-accent-strong hover:underline"
        >
          <ExternalLink size={12} strokeWidth={1.9} className="shrink-0" />
          {art.name}
        </a>
      </div>
      <div className="mt-[5px] flex flex-wrap items-center gap-[10px]">
        <Fingerprint value={art.sha256} />
        <span className="text-[11px] text-text-3">{fmtSize(art.size_bytes)}</span>
        <span className="text-[11px] text-text-3">·</span>
        <a
          href={`${art.url}?download=1`}
          download={art.name}
          title="Download artifact"
          className="text-[11px] text-accent-strong hover:underline"
        >
          download
        </a>
      </div>
    </div>
  )
}
