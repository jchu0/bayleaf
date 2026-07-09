import type { Evidence, Finding, Severity } from '../types'
import { GATE_DOT, GATE_LABEL, STATUS_CHIP } from '../verdict'

const GATES = ['preflight', 'qc', 'variant'] as const

// The "QC readout by gate": findings grouped by gate, each a Metric · Observed · Threshold ·
// Status row (flagged-first), with the cited source(s) kept as a caption so evidence stays
// traceable. Bad barcode segments are highlighted (self-explaining index swaps).
export function EvidenceTable({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return <p className="text-[13px] font-medium text-proceed-fg">No provenance, metadata, or QC issues found.</p>
  }
  const groups = GATES.map((gate) => ({ gate, items: findings.filter((f) => f.gate === gate) })).filter(
    (g) => g.items.length > 0,
  )
  return (
    <div className="space-y-4">
      {groups.map(({ gate, items }) => (
        <div key={gate}>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.4px] text-text-2">
              <span className={`h-1.5 w-1.5 rounded-full ${GATE_DOT[gate]}`} />
              {GATE_LABEL[gate]} gate
            </span>
            <span className="rounded border border-hold-bd bg-hold-bg px-1.5 py-0.5 text-[10px] font-medium text-hold-fg">
              {items.length} flagged
            </span>
          </div>
          <div className="overflow-hidden rounded-lg border border-line">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="bg-card-2 text-left text-[10.5px] uppercase tracking-wide text-text-3">
                  <th className="px-3 py-2 font-medium">Metric</th>
                  <th className="px-3 py-2 font-medium">Observed</th>
                  <th className="px-3 py-2 font-medium">Threshold</th>
                  <th className="px-3 py-2 text-right font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((f) => {
                  const e: Evidence | undefined = f.evidence[0]
                  return (
                    <tr key={f.id} className="border-t border-line align-top">
                      <td className="px-3 py-2">
                        <div className="font-medium text-text">{f.title}</div>
                        {f.detail && <div className="mt-0.5 text-[11.5px] text-text-3">{f.detail}</div>}
                        {e && (
                          <div className="mt-0.5 font-mono text-[10.5px] text-text-3">
                            {f.rule_id} · {e.source}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono text-[12px] text-text">
                        <Observed value={e?.value ?? null} expected={e?.expected ?? null} />
                      </td>
                      <td className="px-3 py-2 font-mono text-[12px] text-text-2">
                        {e?.expected ?? e?.threshold ?? '—'}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <StatusChip sev={f.severity} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}

function StatusChip({ sev }: { sev: Severity }) {
  const s = STATUS_CHIP[sev]
  return (
    <span
      className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${s.cls}`}
    >
      {s.label}
    </span>
  )
}

// Highlight the differing segment(s) of a barcode value in red vs the declared index.
function Observed({ value, expected }: { value: string | null; expected: string | null }) {
  if (!value) return <>—</>
  if (expected && value.includes('-') && expected.includes('-')) {
    const observed = value.split('-')
    const declared = expected.split('-')
    return (
      <>
        {observed.map((seg, i) => (
          <span key={i}>
            {i > 0 ? '-' : ''}
            <span className={seg !== declared[i] ? 'font-semibold text-escalate-fg' : ''}>{seg}</span>
          </span>
        ))}
      </>
    )
  }
  return <>{value}</>
}
