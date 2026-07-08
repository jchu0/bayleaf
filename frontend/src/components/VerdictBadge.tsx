import type { Verdict } from '../types'
import { VERDICT_BADGE, VERDICT_LABEL } from '../verdict'

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${VERDICT_BADGE[verdict]}`}
    >
      {VERDICT_LABEL[verdict]}
    </span>
  )
}
