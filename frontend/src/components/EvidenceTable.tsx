import type { Finding } from '../types'
import { GATE_LABEL, SEVERITY_ICON } from '../verdict'

// Gate-grouped cited evidence: every finding traces to a source + observed vs expected.
export function EvidenceTable({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return <p className="text-proceed text-sm">No provenance, metadata, or QC issues found.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-ink-dim text-left text-xs uppercase tracking-wide">
            <th className="py-2 pr-3 font-medium"></th>
            <th className="py-2 pr-3 font-medium">Gate</th>
            <th className="py-2 pr-3 font-medium">Finding</th>
            <th className="py-2 pr-3 font-medium">Source</th>
            <th className="py-2 pr-3 font-medium">Observed</th>
            <th className="py-2 pr-3 font-medium">Expected</th>
          </tr>
        </thead>
        <tbody>
          {findings.flatMap((f) =>
            f.evidence.map((e, i) => (
              <tr key={`${f.id}-${i}`} className="border-t border-border align-top">
                <td className="py-2 pr-3">{i === 0 ? SEVERITY_ICON[f.severity] : ''}</td>
                <td className="py-2 pr-3 text-ink-dim text-xs uppercase">{GATE_LABEL[f.gate]}</td>
                <td className="py-2 pr-3">{i === 0 ? f.title : ''}</td>
                <td className="py-2 pr-3">
                  <span className="font-mono text-xs">{e.source}</span>
                  <SourceKindChip kind={e.source_kind} />
                </td>
                <td className="py-2 pr-3 font-mono text-xs">
                  <Observed value={e.value} expected={e.expected} />
                </td>
                <td className="py-2 pr-3 font-mono text-xs text-ink-dim">
                  {e.expected ?? e.threshold ?? '—'}
                </td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  )
}

function SourceKindChip({ kind }: { kind: string }) {
  return (
    <span className="ml-2 rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-ink-dim">
      {kind}
    </span>
  )
}

// For barcode-like values (i7-i5), highlight the segment(s) that differ from the
// declared index in red — a self-explanatory view of an index swap.
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
            <span className={seg !== declared[i] ? 'font-semibold text-escalate' : ''}>{seg}</span>
          </span>
        ))}
      </>
    )
  }
  return <>{value}</>
}
