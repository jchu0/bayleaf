import type { Evidence, Finding, Severity } from '../types'
import { GATE_DOT, GATE_LABEL } from '../verdict'

// The design's separate "Supporting evidence · cited" section — findings (not metric_values)
// rendered as a Source · Field · Observed · Expected sub-table, one card per finding, with the
// cited source kept traceable. Distinct from the QC readout hero (QCReadout) so measured
// signals and cited provenance never conflate. Repurposed from the old EvidenceTable, which
// mislabeled a findings table as the QC readout.

type Variant = 'split' | 'brief' | 'dense'

// Severity chip treatment (mirrors the prototype SEV map): the accent color per severity,
// on a tinted background. Kept local — verdict.ts has no severity-chip export.
const SEV: Record<Severity, { dot: string; text: string; bg: string; label: string }> = {
  critical: { dot: 'bg-crit', text: 'text-crit', bg: 'bg-escalate-bg', label: 'Critical' },
  warn: { dot: 'bg-warn', text: 'text-warn', bg: 'bg-rerun-bg', label: 'Warn' },
  info: { dot: 'bg-info', text: 'text-info', bg: 'bg-accent-weak', label: 'Info' },
}

const RULE_CHIP =
  'shrink-0 rounded-[5px] border border-line bg-card-2 px-1.5 py-px font-mono text-[10.5px] font-medium text-text-2'

// A barcode/index sequence — the only value shape where a per-character diff is meaningful.
const isSeq = (s: string) => /^[ACGTN-]{4,}$/i.test(s)

// Highlight the differing characters of an observed index against the declared one (an index
// swap self-explains: the mismatched bases light up escalate-red). Non-sequence values render
// plainly — we never fabricate a "bad" flag the evidence didn't carry.
function ObservedCell({ value, expected }: { value: string | null; expected: string | null }) {
  if (!value) return <span className="text-text-3">—</span>
  if (expected && value !== expected && value.length === expected.length && isSeq(value) && isSeq(expected)) {
    return (
      <span className="font-mono text-[11.5px]">
        {[...value].map((ch, i) => (
          <span
            key={i}
            className={
              ch !== expected[i]
                ? 'rounded-[2px] bg-escalate-bg px-[1.5px] font-bold text-escalate-fg underline underline-offset-2'
                : 'text-text'
            }
          >
            {ch}
          </span>
        ))}
      </span>
    )
  }
  return <span className="break-all font-mono text-[11.5px] font-semibold text-text">{value}</span>
}

function SevChip({ sev }: { sev: Severity }) {
  const s = SEV[sev]
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-[5px] rounded-[5px] px-[7px] py-0.5 text-[9.5px] font-semibold uppercase tracking-[0.4px] ${s.text} ${s.bg}`}
    >
      <span className={`h-[5px] w-[5px] rounded-full ${s.dot}`} />
      {s.label}
    </span>
  )
}

function GateChip({ gate }: { gate: Finding['gate'] }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-[5px] rounded-[5px] border border-line bg-card-2 px-[7px] py-0.5 text-[9.5px] font-semibold uppercase tracking-[0.3px] text-text-2">
      <span className={`h-[5px] w-[5px] rounded-full ${GATE_DOT[gate]}`} />
      {GATE_LABEL[gate]}
    </span>
  )
}

// One evidence sub-row's cells (Source/Field/Observed/Expected).
function evField(e: Evidence): string {
  return e.source_field ?? e.locator ?? '—'
}
function evExpected(e: Evidence): string {
  return e.expected ?? e.threshold ?? '—'
}

export function CitedEvidence({ findings, variant }: { findings: Finding[]; variant: Variant }) {
  if (findings.length === 0) return null

  // Dense: compact rows — dot + title + rule chip + a single mono provenance line per citation.
  if (variant === 'dense') {
    return (
      <div className="flex flex-col gap-[7px]">
        {findings.map((f) => (
          <div key={f.id} className="flex items-start gap-2.5 rounded-[9px] border border-line px-[11px] py-2.5">
            <span className={`mt-[5px] h-2 w-2 shrink-0 rounded-full ${SEV[f.severity].dot}`} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12.5px] font-semibold text-text">{f.title}</span>
                <span className={RULE_CHIP}>{f.rule_id}</span>
              </div>
              {f.evidence.map((e, i) => (
                <div key={i} className="mt-1 font-mono text-[11px] text-text-3">
                  <span className="text-accent-strong">{e.source}</span> · {evField(e)} —{' '}
                  <span className="font-semibold text-text">{e.value ?? '—'}</span>{' '}
                  <span className="text-text-3">exp {evExpected(e)}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    )
  }

  const grid = variant === 'split' ? 'grid-cols-[1.1fr_1fr_1.25fr_1fr]' : 'grid-cols-[1fr_1fr_1.3fr_1fr]'
  return (
    <div className="flex flex-col gap-2.5">
      {findings.map((f) => (
        <div key={f.id} className="overflow-hidden rounded-[10px] border border-line">
          <div className="px-[13px] py-3">
            <div className="flex flex-wrap items-center gap-2">
              <SevChip sev={f.severity} />
              <span className="text-[13px] font-semibold text-text">{f.title}</span>
              <span className={RULE_CHIP}>{f.rule_id}</span>
              <GateChip gate={f.gate} />
            </div>
            {f.detail && <div className="mt-1.5 text-[12.5px] leading-[1.5] text-text-2">{f.detail}</div>}
          </div>
          <div
            className={`grid ${grid} border-t border-line bg-card-2 text-[9.5px] font-semibold uppercase tracking-[0.4px] text-text-3`}
          >
            <div className="px-[13px] py-1.5">Source</div>
            <div className="px-2 py-1.5">Field</div>
            <div className="px-2 py-1.5">Observed</div>
            <div className="px-[11px] py-1.5">Expected</div>
          </div>
          {f.evidence.map((e, i) => (
            <div key={i} className={`grid ${grid} items-center border-t border-line`}>
              <div className="px-[13px] py-2">
                <div className="font-mono text-[11.5px] text-accent-strong">{e.source}</div>
                <span className="mt-0.5 inline-block rounded-[4px] border border-line bg-card-2 px-[5px] font-mono text-[8.5px] font-semibold uppercase tracking-[0.2px] text-text-3">
                  {e.source_kind}
                </span>
              </div>
              <div className="px-2 py-2 font-mono text-[11px] text-text-3">{evField(e)}</div>
              <div className="px-2 py-2">
                <ObservedCell value={e.value} expected={e.expected} />
              </div>
              <div className="px-[11px] py-2 font-mono text-[11px] text-text-2">{evExpected(e)}</div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
