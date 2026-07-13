import { type ReactNode } from 'react'
import type { Verdict } from '../types'
import { VERDICT_BAR, VERDICT_DOT, VERDICT_LABEL } from '../verdict'
import { SegmentBar } from './Bar'

// UX-DUP (RunDetail #4): ONE clickable verdict facet bar replacing the "two adjacent summaries of
// one list + a separate tab row" pattern (DecisionVerdictBar's proportional bar + legend, PLUS the
// CardFilter tab strip, PLUS the attention banner — three renderings of the same counts). Here the
// SAME grouped tally powers the bar widths, the legend counts, AND the active filter: the legend
// items ARE the filter buttons (count + dot, aria-pressed). `active` is the selected verdict or null
// ("all" is the absence of a filter, not a peer facet); clicking the active facet clears it. An
// optional `header` slot carries the attention CTA that used to be a separate banner. Verdict colors
// pass through VERDICT_BAR/VERDICT_DOT untouched — no verdict derivation changes.

const ORDER: Verdict[] = ['proceed', 'hold', 'rerun', 'escalate']

// Legend count colours (the darker -fg shade). Full static strings so Tailwind emits the utilities.
const COUNT_FG: Record<Verdict, string> = {
  proceed: 'text-proceed-fg',
  hold: 'text-hold-fg',
  rerun: 'text-rerun-fg',
  escalate: 'text-escalate-fg',
}

export function FacetBar({
  counts,
  active,
  onSelect,
  header,
}: {
  counts: Record<string, number>
  active: Verdict | null
  onSelect: (v: Verdict | null) => void
  header?: ReactNode
}) {
  const segs = ORDER.map((v) => ({ v, n: counts[v] ?? 0 })).filter((s) => s.n > 0)
  return (
    <div className="mt-[18px] rounded-[12px] border border-line bg-card p-4">
      {header && <div className="mb-3">{header}</div>}
      <SegmentBar
        segments={segs.map((s) => ({ key: s.v, value: s.n, className: VERDICT_BAR[s.v], title: `${s.n} ${s.v}` }))}
      />
      <div className="mt-[13px] flex flex-wrap gap-x-1.5 gap-y-2">
        {ORDER.map((v) => {
          const n = counts[v] ?? 0
          const isActive = active === v
          return (
            <button
              key={v}
              type="button"
              aria-pressed={isActive}
              // A zero-count verdict is still shown (the mix is honest) but isn't a useful filter.
              disabled={n === 0}
              onClick={() => onSelect(isActive ? null : v)}
              className={`inline-flex items-center gap-[7px] rounded-[7px] border px-2 py-1 text-[12.5px] transition-colors disabled:cursor-default disabled:opacity-55 ${
                isActive
                  ? 'border-line-strong bg-card-2 text-text'
                  : 'border-transparent text-text-2 enabled:hover:bg-card-2'
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${VERDICT_DOT[v]}`} />
              <b className={`font-semibold ${COUNT_FG[v]}`}>{n}</b> {VERDICT_LABEL[v]}
            </button>
          )
        })}
      </div>
    </div>
  )
}
