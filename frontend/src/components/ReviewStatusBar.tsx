import type { Verdict } from '../types'
import { VERDICT_BAR, VERDICT_DOT } from '../verdict'

// One segment of the queue's severity-mix bar: a verdict class, its count, and a legend label.
export type ReviewStatusSegment = { verdict: Verdict; label: string; count: number }

// The Review-queue status-summary bar (dc.html §5.5): a proportional, verdict-coloured strip
// over the *whole* queue (independent of the status filter) plus a dotted legend. It answers
// "how bad is the backlog" at a glance, complementing the status FacetChips below it. Segments
// with a zero count drop out of both the bar and the legend so the strip never lies about mix.
export function ReviewStatusBar({ segments }: { segments: ReviewStatusSegment[] }) {
  const shown = segments.filter((s) => s.count > 0)
  const total = shown.reduce((n, s) => n + s.count, 0)

  return (
    <div className="mt-4 rounded-xl border border-line bg-card px-[18px] py-4 shadow-card">
      <div className="flex h-[11px] gap-[2px] overflow-hidden rounded-[6px]">
        {total === 0 ? (
          <span className="w-full bg-card-2" />
        ) : (
          shown.map((s) => (
            <span
              key={s.verdict}
              className={VERDICT_BAR[s.verdict]}
              style={{ width: `${(s.count / total) * 100}%` }}
            />
          ))
        )}
      </div>
      <div className="mt-[13px] flex flex-wrap gap-x-[22px] gap-y-2">
        {shown.map((s) => (
          <span key={s.verdict} className="inline-flex items-center gap-[7px] text-[12.5px] text-text-2">
            <span className={`inline-block h-2 w-2 rounded-full ${VERDICT_DOT[s.verdict]}`} />
            <strong className="text-text">{s.count}</strong> {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}
