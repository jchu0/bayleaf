import type { Gate, GateResult, Verdict } from '../types'
import { GATE_DOT, GATE_TAG, VERDICT_BADGE, VERDICT_LABEL } from '../verdict'

const GATES: Gate[] = ['preflight', 'qc', 'variant']

// The full-bleed gate-results strip that opens every decision card's body (dc 678): per-gate
// verdict chip + rationale across the three checkpoints. A gate with no result reads "Not run"
// when the sample was blocked upstream (any non-proceed verdict — HOLD included) or an earlier
// gate isn't clear; only a genuinely clean card shows the not-run gate as "Passed" with margin.
// Self-contained padding + surface so it sits edge-to-edge under the card header.
export function GateResultStrip({
  results,
  cardVerdict = 'proceed',
}: {
  results: GateResult[]
  cardVerdict?: Verdict
}) {
  const byGate = new Map(results.map((g) => [g.gate, g]))
  // Gate dependency, mirroring RunDetail's unclearGates/blockingGate (and card_readout._blocking_gate):
  // a not-run gate is blocked when an EARLIER gate in the pipeline isn't clear. Returns the specific
  // upstream gate so the strip agrees with the QC readout on the same card — the two must not disagree.
  const unclearGates = new Set(results.filter((g) => g.verdict !== 'proceed').map((g) => g.gate))
  const blockingGate = (gate: Gate): Gate | null => {
    const idx = GATES.indexOf(gate)
    for (let i = idx - 1; i >= 0; i--) if (unclearGates.has(GATES[i])) return GATES[i]
    return null
  }
  // A held/rerun/escalate card is never "all passed": a gate with no result must read Not run, not
  // green. `blocked = escalate||rerun` previously excluded HOLD, painting a not-run downstream gate
  // green "Cleared with margin" on a held card — the key honesty bug this strip now closes.
  const cardBlocked = cardVerdict !== 'proceed'
  return (
    <div className="flex gap-2 overflow-x-auto border-b border-line bg-card-2 px-[18px] py-[13px]">
      {GATES.map((gate) => {
        const g = byGate.get(gate)
        const upstreamBlocker = g ? null : blockingGate(gate)
        const blocked = cardBlocked || upstreamBlocker !== null
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
                // A gate with no findings on a CLEAN card PASSED — show it green (not a neutral grey).
                // A gate blocked upstream, or on any non-proceed card (HOLD included), stays neutral
                // "Not run" — never green, so a held card can't read as all-passed.
                <span
                  className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.3px] ${
                    blocked
                      ? 'border-line bg-card-2 text-text-2'
                      : 'border-proceed-bd bg-proceed-bg text-proceed-fg'
                  }`}
                >
                  {blocked ? 'Not run' : 'Passed'}
                </span>
              )}
            </div>
            <div className="text-[11.5px] leading-[1.4] text-text-2">
              {g
                ? g.rationale
                : blocked
                  ? upstreamBlocker
                    ? `Not evaluated — blocked by the ${GATE_TAG[upstreamBlocker].replace(' gate', '')} gate.`
                    : 'Not evaluated — blocked upstream.'
                  : 'Cleared with margin.'}
            </div>
          </div>
        )
      })}
    </div>
  )
}
