import type { CanonicalUnit, Gate, MetricValue } from '../types'
import { GATE_LABEL } from '../verdict'

// Gate ordering matches the pipeline's checkpoint order (preflight → qc → variant),
// so a reader scans metrics in the same sequence the gate evaluates them.
const GATE_ORDER: Record<Gate, number> = { preflight: 0, qc: 1, variant: 2 }

// Trim a measured value to at most `maxDecimals`, dropping trailing zeros so integers
// read cleanly (30, not 30.000) while fractions keep the precision that matters (0.0123).
function fmt(n: number, maxDecimals = 3): string {
  if (Number.isInteger(n)) return String(n)
  return n
    .toFixed(maxDecimals)
    .replace(/0+$/, '')
    .replace(/\.$/, '')
}

// Render the registry-normalized value in its canonical unit. The unit is made visible
// (glyph for the common ones, a dim word otherwise) so a bare number is never ambiguous —
// e.g. `95%` vs `0.95` vs `30×` read as distinct things at a glance.
function NormalizedValue({ value, unit }: { value: number; unit: CanonicalUnit }) {
  switch (unit) {
    case 'percent':
      return (
        <>
          {fmt(value, 2)}
          <span className="text-text-3">%</span>
        </>
      )
    case 'x':
      return (
        <>
          {fmt(value, 1)}
          <span className="text-text-3">×</span>
        </>
      )
    case 'phred':
      return (
        <>
          <span className="text-text-3">Q</span>
          {fmt(value, 0)}
        </>
      )
    case 'fraction':
      return (
        <>
          {fmt(value, 4)} <span className="text-text-3">fraction</span>
        </>
      )
    case 'ratio':
      return (
        <>
          {fmt(value, 3)} <span className="text-text-3">ratio</span>
        </>
      )
    case 'bool':
      return <>{value ? 'true' : 'false'}</>
    case 'count':
      return <>{fmt(value, 0)}</>
    default:
      return <>{fmt(value)}</>
  }
}

// Read-only readout of the per-sample QC metrics (T-025). Each row shows the metric key,
// its gate, the canonical (normalized) value, and the raw value/unit the tool reported —
// the two representations ADR-0007 snapshots side by side. Measured signals, not heuristics.
export function MetricsPanel({ metrics }: { metrics: MetricValue[] }) {
  // A card with no QC row (e.g. never reached the QC gate) has nothing to show — recede.
  if (metrics.length === 0) return null

  const sorted = [...metrics].sort(
    (a, b) => GATE_ORDER[a.gate] - GATE_ORDER[b.gate] || a.metric_key.localeCompare(b.metric_key),
  )

  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-3">
        QC metrics · registry-normalized
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-text-3 text-left text-xs uppercase tracking-wide">
              <th className="py-2 pr-3 font-medium">Gate</th>
              <th className="py-2 pr-3 font-medium">Metric</th>
              <th className="py-2 pr-3 font-medium">Value (canonical)</th>
              <th className="py-2 pr-3 font-medium">Reported (raw)</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((m) => (
              <tr key={m.id} className="border-t border-line align-top">
                <td className="py-2 pr-3 text-text-3 text-xs uppercase">{GATE_LABEL[m.gate]}</td>
                <td className="py-2 pr-3 font-mono text-xs">{m.metric_key}</td>
                <td className="py-2 pr-3 font-mono">
                  <NormalizedValue value={m.normalized_value} unit={m.canonical_unit} />
                </td>
                <td className="py-2 pr-3 font-mono text-xs text-text-3">
                  {fmt(m.raw_value)}
                  {m.raw_unit ? ` ${m.raw_unit}` : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
