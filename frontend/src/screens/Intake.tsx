import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Check, CheckCircle2, ChevronRight, RefreshCw } from 'lucide-react'
import { api } from '../api'
import { MeterBar } from '../components/Bar'
import { CollapsibleRow } from '../components/CollapsibleRow'
import { Pager, type PerPage } from '../components/Pager'
import { PageHeader } from '../components/PageHeader'
import { Empty, ErrorBox, Loading } from '../components/States'
import { useRefresh } from '../hooks/useRefresh'
import type { CardHeader, DecisionCard, RunDetail, Runbook } from '../types'
import { VERDICT_LABEL } from '../verdict'

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

type TileState = 'pass' | 'border' | 'fail'
type Tile = { label: string; value: number; unit: string; state: TileState; gate: number; hib: boolean; sequencing: boolean }

// Three-state tile status straight from the runbook (the design's metricChip vocabulary):
// clears the gate → pass; past the hard-fail floor → fail; the band between → borderline.
// No band is fabricated — `gate` and `hard_fail` are the runbook's own bounds.
function classify(avg: number, gate: number, hardFail: number, hib: boolean): TileState {
  if (hib) return avg >= gate ? 'pass' : avg < hardFail ? 'fail' : 'border'
  return avg <= gate ? 'pass' : avg > hardFail ? 'fail' : 'border'
}
const TILE_CHIP: Record<TileState, { cls: string; label: string }> = {
  pass: { cls: 'border-proceed-bd bg-proceed-bg text-proceed-fg', label: 'Pass' },
  border: { cls: 'border-hold-bd bg-hold-bg text-hold-fg', label: 'Border' },
  fail: { cls: 'border-rerun-bd bg-rerun-bg text-rerun-fg', label: 'Fail' },
}

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
  const [openMap, setOpenMap] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (!runId) return
    setRun(null)
    api.run(runId).then(setRun).catch((e) => setError(String(e)))
    api.config().then(setRunbook).catch(() => setRunbook(null))
  }, [runId])

  // Refresh re-pulls the run + runbook and stamps "Updated {time}"; the button spins while
  // in flight. No verdict is recomputed here — it's an operator refetch, nothing more.
  const refetch = useCallback(async () => {
    if (!runId) return
    const [r, rb] = await Promise.all([api.run(runId), api.config().catch(() => null)])
    setRun(r)
    if (rb) setRunbook(rb)
  }, [runId])
  const { spinning, updatedLabel, refresh } = useRefresh(refetch)

  const tiles = useMemo<Tile[]>(() => {
    if (!run || !runbook) return []
    const out: Tile[] = []
    for (const t of RUN_TILES) {
      const th = runbook.qc_thresholds.find((q) => q.metric === t.metric)
      if (!th) continue
      const avg = mean(run.cards.map((c) => metricOf(c, t.key)).filter((v): v is number => v != null))
      if (avg == null) continue
      const state = classify(avg, th.gate, th.hard_fail, th.higher_is_better)
      out.push({ label: t.label, value: avg, unit: th.unit, state, gate: th.gate, hib: th.higher_is_better, sequencing: !!t.sequencing })
    }
    return out
  }, [run, runbook])

  // The yield admission cutoff is the runbook's own `pct_reads_identified` gate (0.70,
  // canonical fraction) — surfaced so the operator sees the real threshold instead of a
  // magic number. Falls back to the literal 70% if the runbook didn't load; it matches
  // the code path (`yield_ < gate`) either way.
  const yieldTarget = useMemo(() => {
    const th = runbook?.qc_thresholds.find((q) => q.metric === 'pct_reads_identified')
    const gate = th?.gate ?? 0.7
    const unit = th?.unit ?? '%'
    return { gate, unit, display: displayThreshold(gate, unit) }
  }, [runbook])

  if (error) return <ErrorBox message={error} />
  if (!runId) return <Empty message="Pick a run from the switcher to see its intake gate." />
  if (!run) return <Loading label="Loading intake…" />

  // A run "sequenced" if the flow-cell-health signals (Q30 + Cluster PF) cleared — the
  // preflight question is admission, not per-sample QC. Coverage/dup can fail downstream
  // without meaning the run didn't sequence. Status stays honest (not a hard-coded pass).
  const seqTiles = tiles.filter((t) => t.sequencing)
  const runAdmitted = seqTiles.length > 0 && seqTiles.every((t) => t.state === 'pass')
  const hasIntake = run.cards.length > 0

  return (
    <div className="pg-fade mx-auto max-w-[1000px]">
      <PageHeader
        title="Intake gate"
        actions={<IntakeHeaderActions updatedLabel={updatedLabel} spinning={spinning} onRefresh={refresh} />}
      />

      {!hasIntake ? (
        <NoIntake />
      ) : (
        <>
          {/* Run sequencing QC — bordered header over a fixed 3-col tile grid */}
          <section className="mt-[18px] overflow-hidden rounded-[14px] border border-line bg-card shadow-card">
            <div className="flex items-center justify-between gap-3 border-b border-line px-[18px] py-[14px]">
              <div>
                <div className="text-[14.5px] font-semibold text-text">Run sequencing QC</div>
                <div className="mt-0.5 text-[12px] text-text-2">
                  Rolled up across this run's samples. Instrument InterOp tiles (PhiX, cluster density, error rate)
                  aren't captured — the pipeline starts from FASTQ.
                </div>
              </div>
              <span
                className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-[11px] py-1 text-[11.5px] font-semibold ${
                  runAdmitted ? 'border-proceed-bd bg-proceed-bg text-proceed-fg' : 'border-hold-bd bg-hold-bg text-hold-fg'
                }`}
              >
                <Check size={14} />
                {runAdmitted ? 'Run admitted' : 'Run needs review'}
              </span>
            </div>

            <div className="grid grid-cols-3 gap-3 px-[18px] py-4">
              {tiles.map((t) => (
                <div key={t.label} className="rounded-[11px] border border-line px-3.5 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12px] text-text-2">{t.label}</span>
                    <span
                      className={`inline-flex items-center justify-center whitespace-nowrap rounded-full border px-[7px] py-0.5 text-[9.5px] font-semibold uppercase tracking-[0.3px] ${TILE_CHIP[t.state].cls}`}
                    >
                      {TILE_CHIP[t.state].label}
                    </span>
                  </div>
                  <div className="mt-1.5 font-mono text-[20px] font-semibold text-text">{displayValue(t.value, t.unit)}</div>
                  <div className="mt-0.5 font-mono text-[10.5px] text-text-3">
                    gate {t.hib ? '≥' : '≤'} {displayThreshold(t.gate, t.unit)}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <SampleAdmission
            run={run}
            yieldTarget={yieldTarget}
            overrides={overrides}
            setOverrides={setOverrides}
            openMap={openMap}
            setOpenMap={setOpenMap}
          />
        </>
      )}
    </div>
  )
}

// Header right cluster: "Updated {time}" + a spinning Refresh control, a divider, then the
// three-step gate breadcrumb (Preflight active, in the preflight-gate accent #1f6feb).
function IntakeHeaderActions({
  updatedLabel,
  spinning,
  onRefresh,
}: {
  updatedLabel: string | null
  spinning: boolean
  onRefresh: () => void
}) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-2.5">
      <span className="text-[11px] text-text-3">Updated {updatedLabel ?? 'just now'}</span>
      <button
        onClick={onRefresh}
        className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-[11px] py-1.5 text-[12px] font-medium text-text-2"
      >
        <RefreshCw size={14} className={spinning ? 'pg-spin' : ''} />
        Refresh
      </button>
      <span className="inline-block h-5 w-px bg-line" />
      <span className="inline-flex items-center rounded-full bg-preflight px-[11px] py-[5px] text-[11.5px] font-semibold text-white">
        1 · Preflight
      </span>
      <ChevronRight size={13} strokeWidth={2.2} className="text-text-3" />
      <span className="rounded-full border border-line px-[11px] py-[5px] text-[11.5px] font-medium text-text-3">2 · QC</span>
      <ChevronRight size={13} strokeWidth={2.2} className="text-text-3" />
      <span className="rounded-full border border-line px-[11px] py-[5px] text-[11.5px] font-medium text-text-3">3 · Variant</span>
    </div>
  )
}

// One preflight metadata field (IG1). A pending field shows a skeleton; a loaded-but-null field
// reads "not captured" (honest — we never fabricate a value the artifacts didn't carry).
function MetaField({ label, value, pending }: { label: string; value?: string | null; pending?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="text-[9.5px] font-semibold uppercase tracking-[0.4px] text-text-3">{label}</div>
      {pending ? (
        <div className="mt-1 h-[13px] w-16 animate-pulse rounded bg-card-3" />
      ) : (
        <div
          className={`mt-0.5 truncate text-[12px] ${value ? 'text-text' : 'italic text-text-3'}`}
          title={value ?? undefined}
        >
          {value || 'not captured'}
        </div>
      )}
    </div>
  )
}

function NoIntake() {
  return (
    <div className="mt-[18px] rounded-[14px] border border-dashed border-line-strong bg-card p-[38px] text-center">
      <div className="text-[15px] font-semibold text-text">No intake data for this run</div>
      <div className="mt-1 text-[13px] text-text-2">Preflight QC is available for runs that have reached the gate.</div>
    </div>
  )
}

// Chip / bar palettes keyed by the honest, rule-derived admission state. `flagged` is a real
// preflight gate hold (e.g. a barcode/index mismatch) — kept distinct from a soft sparse-yield
// hold, which is the only state the manual override applies to (ADR-0001: the override records
// an operator annotation, it never sets or overturns a gate verdict).
const CHIP: Record<string, string> = {
  admit: 'border-proceed-bd bg-proceed-bg text-proceed-fg',
  override: 'border-[#cfe0fb] bg-accent-weak text-accent-strong',
  held: 'border-hold-bd bg-hold-bg text-hold-fg',
  flagged: 'border-escalate-bd bg-escalate-bg text-escalate-fg',
}
const BAR: Record<string, string> = {
  admit: 'bg-proceed',
  override: 'bg-accent',
  held: 'bg-hold',
  flagged: 'bg-escalate',
}
const STATUS_LABEL: Record<string, string> = {
  admit: 'Admitted',
  override: 'Admitted · manual override',
  held: 'Sparse — held at intake',
  flagged: 'Flagged at intake',
}

function SampleAdmission({
  run,
  yieldTarget,
  overrides,
  setOverrides,
  openMap,
  setOpenMap,
}: {
  run: RunDetail
  yieldTarget: { gate: number; unit: string; display: string }
  overrides: Record<string, boolean>
  setOverrides: (fn: (m: Record<string, boolean>) => Record<string, boolean>) => void
  openMap: Record<string, boolean>
  setOpenMap: (fn: (m: Record<string, boolean>) => Record<string, boolean>) => void
}) {
  const rows = run.cards.map((card) => {
    const yield_ = metricOf(card, 'qc.reads_passing_filter') // fraction identified/PF
    const q30 = metricOf(card, 'qc.q30')
    const flaggedAtIntake = card.gate_results.some((g) => g.gate === 'preflight')
    // "Genuinely-sparse": below the runbook's yield gate but not flagged for a provenance/
    // metadata reason — the case the manual override exists for.
    const sparse = !flaggedAtIntake && yield_ != null && yield_ < yieldTarget.gate
    return { card, yield_, q30, flaggedAtIntake, sparse }
  })

  // Scale-aware pagination (UIC-5 / scale-aware rule): a 100+ sample flowcell can't render every
  // admission row at once. 25/page default; the page resets when the run changes so a deep page
  // never strands on a smaller run.
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState<PerPage>('25')
  useEffect(() => setPage(1), [run.run_id])
  const per = Number(perPage)
  const pages = Math.max(1, Math.ceil(rows.length / per))
  const curPage = Math.min(page, pages)
  const pagedRows = rows.slice((curPage - 1) * per, curPage * per)

  // Lazy-load each OPEN sample's card header (sample_type / library_prep / origin) — real preflight
  // metadata the DecisionCard itself doesn't carry (it lives on the CardReadout header). Fetched
  // only for expanded rows so a 100-sample run never fires 100 requests (scale-aware). undefined =
  // untouched, null = in-flight, object = loaded; a null field on a loaded header reads "not captured".
  const [headers, setHeaders] = useState<Record<string, CardHeader | null>>({})
  useEffect(() => {
    for (const { card, sparse, flaggedAtIntake } of pagedRows) {
      const id = card.sample_id
      const isOpen = openMap[id] ?? (sparse || flaggedAtIntake)
      if (isOpen && !(id in headers)) {
        setHeaders((h) => ({ ...h, [id]: null }))
        api
          .qcReadout(run.run_id, id)
          .then((r) => setHeaders((h) => ({ ...h, [id]: r.header })))
          .catch(() => undefined)
      }
    }
  }, [pagedRows, openMap, headers, run.run_id])

  return (
    <section className="mt-[14px] overflow-hidden rounded-[14px] border border-line bg-card shadow-card">
      <div className="border-b border-line px-[18px] py-[14px]">
        <div className="text-[14.5px] font-semibold text-text">Sample admission</div>
        <div className="mt-0.5 text-[12px] text-text-2">
          Yield target ≥ {yieldTarget.display} reads identified. A genuinely-sparse sample can still be admitted with a
          manual override.
        </div>
      </div>

      <div className="flex flex-col gap-[9px] px-4 pt-3">
        {pagedRows.map(({ card, yield_, q30, flaggedAtIntake, sparse }) => {
          const id = card.sample_id
          const overridden = !!overrides[id]
          const admitted = !flaggedAtIntake && (!sparse || overridden)
          const pct = yield_ != null ? Math.round(yield_ * 100) : null
          // Non-sparse rows collapse by default; sparse / flagged rows open so the operator
          // lands on the state that actually needs a decision.
          const defaultOpen = sparse || flaggedAtIntake
          const open = openMap[id] ?? defaultOpen

          const status = flaggedAtIntake ? 'flagged' : !sparse ? 'admit' : overridden ? 'override' : 'held'
          // Bar scales against the metric's own 0–100 range (its "full" reference), the honest
          // analogue of the mock's pct/25 — real % reads-identified is already high and
          // consistent, so bars read at comparable lengths with room for status + action.
          const overrideNote = admitted
            ? 'Admitted below the yield target by manual override — recorded on the run.'
            : 'Below the yield target. Admit only if the low yield is expected for this sample.'

          return (
            <CollapsibleRow
              key={id}
              open={open}
              onToggle={() => setOpenMap((m) => ({ ...m, [id]: !(m[id] ?? defaultOpen) }))}
              header={
                <div className="flex items-center gap-3">
                  <span className="shrink-0 font-mono text-[14px] font-semibold text-text">{id}</span>
                  <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-text-3">
                    {pct != null ? `${pct}% reads identified` : 'yield not captured'}
                    {q30 != null ? ` · Q30 ${Math.round(q30 * 1000) / 10}%` : ''}
                  </span>
                  <span
                    className={`inline-flex shrink-0 items-center rounded-full border px-[9px] py-[3px] text-[10.5px] font-semibold ${CHIP[status]}`}
                  >
                    {STATUS_LABEL[status]}
                  </span>
                </div>
              }
            >
              <div className="-m-4 bg-card-2 px-4 pb-[15px] pt-3.5">
                {/* Preflight sample metadata (IG1) — real fields only, no analyzed/downstream data.
                    sample_type/library_prep/origin are lazy-loaded from the card header; platform &
                    date are run-level context. A null field reads "not captured" (honest). */}
                <div className="mb-3.5 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
                  <MetaField label="Sample type" value={headers[id]?.sample_type} pending={headers[id] == null} />
                  <MetaField label="Library prep" value={headers[id]?.library_prep} pending={headers[id] == null} />
                  <MetaField label="Origin" value={headers[id]?.origin} pending={headers[id] == null} />
                  <MetaField label="Platform" value={run.summary.platform} />
                  <MetaField label="Run date" value={run.summary.run_date} />
                  <MetaField label="Verdict" value={VERDICT_LABEL[card.verdict]} />
                </div>
                <div className="mb-[7px] flex items-center justify-between gap-3">
                  <span className="text-[10px] font-semibold uppercase tracking-[0.4px] text-text-3">
                    Yield vs target · ≥ {yieldTarget.display}
                  </span>
                  <span className="font-mono text-[11.5px] text-text-2">{pct != null ? `${pct}%` : '—'}</span>
                </div>
                {/* Shrunk bar (IG1) — capped width, canonical MeterBar geometry (G3). */}
                <MeterBar value={pct ?? 0} fillClassName={BAR[status]} trackClassName="bg-card-3" className="max-w-[340px]" />


                {sparse && (
                  <div className="mt-[13px] flex flex-wrap items-center gap-3">
                    <span className="min-w-[180px] flex-1 text-[12px] leading-[1.45] text-text-2">{overrideNote}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setOverrides((m) => ({ ...m, [id]: !m[id] }))
                      }}
                      className={`inline-flex shrink-0 items-center gap-1.5 rounded-[7px] px-[11px] py-1.5 text-[11.5px] font-medium ${
                        overridden ? 'border border-line-strong bg-card text-text-2' : 'border border-accent bg-accent text-white'
                      }`}
                    >
                      <CheckCircle2 size={13} strokeWidth={1.9} />
                      {overridden ? 'Undo override' : 'Admit (override)'}
                    </button>
                  </div>
                )}
              </div>
            </CollapsibleRow>
          )
        })}
      </div>

      {/* Scale-aware pager (UIC-5) — shared primitive; self-hides at zero rows. */}
      <div className="px-4 pb-4">
        <Pager
          total={rows.length}
          page={curPage}
          perPage={perPage}
          onPage={setPage}
          onPerPage={(p) => {
            setPerPage(p)
            setPage(1)
          }}
          noun="samples"
        />
      </div>
    </section>
  )
}
