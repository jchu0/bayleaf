import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Check, ChevronRight } from 'lucide-react'
import { api } from '../api'
import { Empty, ErrorBox, Loading } from '../components/States'
import type { DecisionCard, RunDetail, Runbook } from '../types'

// Runbook gates are stored canonically (fraction for %-metrics, x for coverage); `unit`
// is only the display symbol. Convert back so an 85% gate never renders as "0.85%".
function displayThreshold(value: number, unit: string): string {
  const shown = unit === '%' ? value * 100 : value
  return `${Math.round(shown * 100) / 100}${unit}`
}
function displayValue(value: number, unit: string): string {
  const shown = unit === '%' ? value * 100 : value
  return `${Math.round(shown * 10) / 10}${unit}`
}

// Run-QC rollup: registry metric_key → runbook threshold key (the two vocabularies differ,
// e.g. qc.reads_passing_filter ↔ pct_reads_identified). Only the run-health metrics we
// genuinely observe from FASTQ — instrument InterOp tiles (PhiX, cluster density, error
// rate) are not captured in this build, so we don't fabricate them.
const RUN_TILES: { key: string; metric: string; label: string; sequencing?: boolean }[] = [
  { key: 'qc.q30', metric: 'q30', label: 'Run Q30', sequencing: true },
  { key: 'qc.cluster_pf', metric: 'cluster_pf', label: 'Cluster PF', sequencing: true },
  { key: 'qc.reads_passing_filter', metric: 'pct_reads_identified', label: '% reads identified' },
  { key: 'qc.mean_target_coverage', metric: 'mean_coverage', label: 'Mean coverage' },
  { key: 'qc.duplication', metric: 'dup_rate', label: 'Duplication' },
]

type Tile = { label: string; value: number; unit: string; pass: boolean; gate: number; hib: boolean; sequencing: boolean }

function mean(xs: number[]): number | null {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null
}
function metricOf(card: DecisionCard, key: string): number | null {
  return card.metric_values?.find((m) => m.metric_key === key)?.normalized_value ?? null
}

export function Intake() {
  const { runId } = useParams()
  const [run, setRun] = useState<RunDetail | null>(null)
  const [runbook, setRunbook] = useState<Runbook | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [overrides, setOverrides] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (!runId) return
    setRun(null)
    api.run(runId).then(setRun).catch((e) => setError(String(e)))
    api.config().then(setRunbook).catch(() => setRunbook(null))
  }, [runId])

  const tiles = useMemo<Tile[]>(() => {
    if (!run || !runbook) return []
    const out: Tile[] = []
    for (const t of RUN_TILES) {
      const th = runbook.qc_thresholds.find((q) => q.metric === t.metric)
      if (!th) continue
      const avg = mean(run.cards.map((c) => metricOf(c, t.key)).filter((v): v is number => v != null))
      if (avg == null) continue
      const pass = th.higher_is_better ? avg >= th.gate : avg <= th.gate
      out.push({ label: t.label, value: avg, unit: th.unit, pass, gate: th.gate, hib: th.higher_is_better, sequencing: !!t.sequencing })
    }
    return out
  }, [run, runbook])

  if (error) return <ErrorBox message={error} />
  if (!runId) return <Empty message="Pick a run from the switcher to see its intake gate." />
  if (!run) return <Loading label="Loading intake…" />

  // A run "sequenced" if the flow-cell-health signals (Q30 + Cluster PF) cleared — the
  // preflight question is admission, not per-sample QC. Coverage/dup can fail downstream
  // without meaning the run didn't sequence.
  const seqTiles = tiles.filter((t) => t.sequencing)
  const runAdmitted = seqTiles.length > 0 && seqTiles.every((t) => t.pass)

  return (
    <div className="mx-auto max-w-[1000px]">
      <h1 className="text-[22px] font-semibold tracking-tight text-text">Intake gate</h1>
      <p className="mt-1 text-[13px] text-text-2">
        Preflight checkpoint — <span className="font-medium text-text">before processing</span>. Run-level QC rollup and
        which samples are admitted. <span className="font-mono text-text-3">{run.run_id}</span>
      </p>

      <StepIndicator />

      {/* Run QC rollup */}
      <section className="mt-5 rounded-xl border border-line bg-card p-5 shadow-card">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-[15px] font-semibold text-text">Run sequencing QC</h3>
            <p className="mt-0.5 text-[12.5px] text-text-2">
              Rolled up across this run's samples. Instrument InterOp tiles (PhiX, cluster density, error rate) aren't
              captured — the pipeline starts from FASTQ.
            </p>
          </div>
          <span
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-medium ${
              runAdmitted ? 'border-proceed-bd bg-proceed-bg text-proceed-fg' : 'border-hold-bd bg-hold-bg text-hold-fg'
            }`}
          >
            <Check size={13} />
            {runAdmitted ? 'Run admitted' : 'Run needs review'}
          </span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {tiles.map((t) => (
            <div key={t.label} className="rounded-lg border border-line bg-card-2/40 p-3">
              <div className="flex items-center justify-between">
                <span className="text-[11.5px] text-text-2">{t.label}</span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wide ${
                    t.pass ? 'bg-proceed-bg text-proceed-fg' : 'bg-escalate-bg text-escalate-fg'
                  }`}
                >
                  {t.pass ? 'Pass' : 'Fail'}
                </span>
              </div>
              <div className="mt-1 font-mono text-[22px] font-semibold text-text">{displayValue(t.value, t.unit)}</div>
              <div className="mt-0.5 font-mono text-[10.5px] text-text-3">
                gate {t.hib ? '≥' : '≤'} {displayThreshold(t.gate, t.unit)}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Sample admission */}
      <SampleAdmission run={run} overrides={overrides} setOverrides={setOverrides} />
    </div>
  )
}

function StepIndicator() {
  const steps = [
    { n: 1, label: 'Preflight', active: true },
    { n: 2, label: 'QC', active: false },
    { n: 3, label: 'Variant', active: false },
  ]
  return (
    <div className="mt-4 flex items-center gap-2">
      {steps.map((s, i) => (
        <div key={s.n} className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] font-medium ${
              s.active ? 'border-accent bg-accent-weak text-accent' : 'border-line bg-card text-text-3'
            }`}
          >
            <span
              className={`grid h-4 w-4 place-items-center rounded-full text-[10px] font-semibold ${
                s.active ? 'bg-accent text-white' : 'bg-card-2 text-text-3'
              }`}
            >
              {s.n}
            </span>
            {s.label}
          </span>
          {i < steps.length - 1 && <ChevronRight size={15} className="text-text-3" />}
        </div>
      ))}
    </div>
  )
}

function SampleAdmission({
  run,
  overrides,
  setOverrides,
}: {
  run: RunDetail
  overrides: Record<string, boolean>
  setOverrides: (fn: (m: Record<string, boolean>) => Record<string, boolean>) => void
}) {
  const rows = run.cards.map((card) => {
    const yield_ = metricOf(card, 'qc.reads_passing_filter') // fraction identified/PF
    const q30 = metricOf(card, 'qc.q30')
    const flaggedAtIntake = card.gate_results.some((g) => g.gate === 'preflight')
    // "Genuinely-sparse": low read yield but not flagged for a provenance/metadata reason —
    // the case the manual override exists for.
    const sparse = !flaggedAtIntake && yield_ != null && yield_ < 0.7
    return { card, yield_, q30, flaggedAtIntake, sparse }
  })

  return (
    <section className="mt-4 rounded-xl border border-line bg-card p-5 shadow-card">
      <h3 className="text-[15px] font-semibold text-text">Sample admission</h3>
      <p className="mt-0.5 text-[12.5px] text-text-2">
        Which samples the run admits, by read yield. A genuinely-sparse sample can still be admitted with a manual
        override.
      </p>

      <div className="mt-4 space-y-2.5">
        {rows.map(({ card, yield_, q30, flaggedAtIntake, sparse }) => {
          const overridden = overrides[card.sample_id]
          const admitted = !flaggedAtIntake && (!sparse || overridden)
          const pct = yield_ != null ? Math.round(yield_ * 100) : null
          return (
            <div key={card.sample_id} className="flex items-center gap-3">
              <Link
                to={`/runs/${run.run_id}`}
                className="w-12 shrink-0 font-mono text-[13px] font-semibold text-text hover:text-accent"
              >
                {card.sample_id}
              </Link>

              <div className="min-w-0 flex-1">
                <div className="h-2 overflow-hidden rounded-full bg-card-2">
                  <div
                    className={`h-full rounded-full ${admitted ? 'bg-proceed' : flaggedAtIntake ? 'bg-escalate' : 'bg-hold'}`}
                    style={{ width: `${pct ?? 0}%` }}
                  />
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3 font-mono text-[10.5px] text-text-3">
                  <span>{pct != null ? `${pct}% reads identified` : 'yield not captured'}</span>
                  {q30 != null && <span>Q30 {Math.round(q30 * 1000) / 10}%</span>}
                </div>
              </div>

              {sparse && (
                <button
                  onClick={() => setOverrides((m) => ({ ...m, [card.sample_id]: !m[card.sample_id] }))}
                  className={`shrink-0 rounded-lg border px-2.5 py-1 text-[11.5px] font-medium transition-colors ${
                    overridden
                      ? 'border-hold-bd bg-hold-bg text-hold-fg'
                      : 'border-line bg-card text-text-2 hover:text-text'
                  }`}
                >
                  {overridden ? 'Admitted (override)' : 'Admit anyway'}
                </button>
              )}

              <span
                className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium ${
                  flaggedAtIntake
                    ? 'border-escalate-bd bg-escalate-bg text-escalate-fg'
                    : admitted
                      ? 'border-proceed-bd bg-proceed-bg text-proceed-fg'
                      : 'border-hold-bd bg-hold-bg text-hold-fg'
                }`}
              >
                {flaggedAtIntake ? 'Flagged at intake' : admitted ? 'Admitted' : 'Sparse — needs override'}
              </span>
            </div>
          )
        })}
      </div>
    </section>
  )
}
