import type { GateResult } from '../types'
import { GATE_LABEL, VERDICT_LABEL, VERDICT_TEXT } from '../verdict'

// The per-gate breakdown (Preflight / QC / Variant), each with its own verdict.
export function GateResultStrip({ results }: { results: GateResult[] }) {
  if (results.length === 0) return null
  return (
    <div className="flex flex-wrap gap-2">
      {results.map((g) => (
        <div
          key={g.gate}
          className="flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-1.5"
          title={g.rationale}
        >
          <span className="text-ink-dim text-xs uppercase tracking-wide">{GATE_LABEL[g.gate]}</span>
          <span className={`text-sm font-semibold ${VERDICT_TEXT[g.verdict]}`}>
            {VERDICT_LABEL[g.verdict]}
          </span>
        </div>
      ))}
    </div>
  )
}
