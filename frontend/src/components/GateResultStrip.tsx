import type { GateResult, Verdict } from '../types'
import { GATE_DOT, GATE_LABEL, VERDICT_BADGE, VERDICT_LABEL } from '../verdict'

const GATES = ['preflight', 'qc', 'variant'] as const

// The per-gate breakdown across the three checkpoints. A gate with no result is shown as
// "not run" when the sample was hard-blocked upstream (escalate/rerun), else "passed".
export function GateResultStrip({
  results,
  cardVerdict = 'proceed',
}: {
  results: GateResult[]
  cardVerdict?: Verdict
}) {
  const byGate = new Map(results.map((g) => [g.gate, g]))
  const blocked = cardVerdict === 'escalate' || cardVerdict === 'rerun'
  return (
    <div className="grid gap-2.5 sm:grid-cols-3">
      {GATES.map((gate) => {
        const g = byGate.get(gate)
        return (
          <div key={gate} className="rounded-lg border border-line bg-card-2 px-3 py-2.5">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-2">
                <span className={`h-1.5 w-1.5 rounded-full ${GATE_DOT[gate]}`} />
                {GATE_LABEL[gate]} gate
              </span>
              {g ? (
                <span
                  className={`rounded border px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wide ${VERDICT_BADGE[g.verdict]}`}
                >
                  {VERDICT_LABEL[g.verdict]}
                </span>
              ) : (
                <span className="rounded border border-line px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wide text-text-3">
                  {blocked ? 'Not run' : 'Passed'}
                </span>
              )}
            </div>
            <p className="mt-1.5 text-[12px] leading-snug text-text-2">
              {g ? g.rationale : blocked ? 'Not evaluated — blocked upstream.' : 'Cleared with margin.'}
            </p>
          </div>
        )
      })}
    </div>
  )
}
