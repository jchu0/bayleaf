import type { Gate, GateResult, Verdict } from '../types'
import { GATE_DOT, VERDICT_BADGE, VERDICT_LABEL } from '../verdict'

const GATES: Gate[] = ['preflight', 'qc', 'variant']

// The design's gate tags (distinct from GATE_LABEL: qc/variant read as "… gate" here).
const GATE_TAG: Record<Gate, string> = {
  preflight: 'Preflight',
  qc: 'QC gate',
  variant: 'Variant gate',
}

// The full-bleed gate-results strip that opens every decision card's body (dc 678): per-gate
// verdict chip + rationale across the three checkpoints. A gate with no result reads "Not run"
// when the sample was hard-blocked upstream (escalate/rerun), else "Passed" with margin.
// Self-contained padding + surface so it sits edge-to-edge under the card header.
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
    <div className="flex gap-2 overflow-x-auto border-b border-line bg-card-2 px-[18px] py-[13px]">
      {GATES.map((gate) => {
        const g = byGate.get(gate)
        return (
          <div key={gate} className="min-w-[150px] flex-1 rounded-[10px] border border-line bg-card px-3 py-2.5">
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <span className="flex items-center gap-[5px] text-[10px] font-semibold uppercase tracking-[0.3px] text-text-2">
                <span className={`h-1.5 w-1.5 rounded-full ${GATE_DOT[gate]}`} />
                {GATE_TAG[gate]}
              </span>
              {g ? (
                <span
                  className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.3px] ${VERDICT_BADGE[g.verdict]}`}
                >
                  {VERDICT_LABEL[g.verdict]}
                </span>
              ) : (
                <span className="shrink-0 rounded-full border border-line bg-card-2 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.3px] text-text-2">
                  {blocked ? 'Not run' : 'Passed'}
                </span>
              )}
            </div>
            <div className="text-[11.5px] leading-[1.4] text-text-2">
              {g ? g.rationale : blocked ? 'Not evaluated — blocked upstream.' : 'Cleared with margin.'}
            </div>
          </div>
        )
      })}
    </div>
  )
}
