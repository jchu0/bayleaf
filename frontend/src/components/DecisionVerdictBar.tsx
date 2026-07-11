import type { Verdict } from '../types'
import { VERDICT_BAR, VERDICT_DOT, VERDICT_LABEL } from '../verdict'
import { SegmentBar } from './Bar'

// Proportional verdict bar + legend (dc 621-631) — the run's verdict mix at a glance, replacing
// the old 5-tile stat row. Segments are flex-proportional to each verdict's count; the legend
// spells out every verdict (including zero) with a colour-matched bold count.
const ORDER: Verdict[] = ['proceed', 'hold', 'rerun', 'escalate']

// Legend count colours (the darker -fg shade, per the design). Full static strings so Tailwind
// emits the utilities.
const COUNT_FG: Record<Verdict, string> = {
  proceed: 'text-proceed-fg',
  hold: 'text-hold-fg',
  rerun: 'text-rerun-fg',
  escalate: 'text-escalate-fg',
}

export function DecisionVerdictBar({ counts }: { counts: Record<string, number> }) {
  const segs = ORDER.map((v) => ({ v, n: counts[v] ?? 0 })).filter((s) => s.n > 0)
  return (
    <div className="mt-[18px] rounded-[12px] border border-line bg-card p-4">
      <SegmentBar segments={segs.map((s) => ({ key: s.v, value: s.n, className: VERDICT_BAR[s.v], title: `${s.n} ${s.v}` }))} />

      <div className="mt-[13px] flex flex-wrap gap-x-[22px] gap-y-2">
        {ORDER.map((v) => (
          <span key={v} className="inline-flex items-center gap-[7px] text-[12.5px] text-text-2">
            <span className={`h-2 w-2 rounded-full ${VERDICT_DOT[v]}`} />
            <b className={`font-semibold ${COUNT_FG[v]}`}>{counts[v] ?? 0}</b> {VERDICT_LABEL[v]}
          </span>
        ))}
      </div>
    </div>
  )
}
