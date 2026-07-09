import type { Verdict } from '../types'
import { VERDICT_BADGE, VERDICT_DOT, VERDICT_LABEL } from '../verdict'

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${VERDICT_BADGE[verdict]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${VERDICT_DOT[verdict]}`} />
      {VERDICT_LABEL[verdict]}
    </span>
  )
}
