import type { GateReadout, ReadoutStatus } from '../types'
import { GATE_DOT } from '../verdict'

// The Decision-card HERO: the QC readout by gate, populated from the API's `qc-readout`
// projection (card metric_values ⋈ runbook thresholds → Metric·Observed·Threshold·Status).
// This is a pure re-presentation of already-decided numbers — it never sets a verdict or a
// confidence (ADR-0001); `status` mirrors the rule the gate already applied. Repurposed from
// the old (dead) Value/Reported table into the design's four-column readout (F20).

type Variant = 'split' | 'brief' | 'dense'

// Per-status treatment. Deliberately independent of verdict.ts STATUS_CHIP (which maps a
// finding's severity, and uses ESCALATE for critical): the design's metric-status chip maps
// pass→proceed / borderline→hold / fail→RERUN, plus a neutral fourth state for an ungated
// metric we decline to classify (never fabricate a threshold).
const READOUT: Record<ReadoutStatus, { dot: string; chip: string; label: string }> = {
  pass: { dot: 'bg-proceed', chip: 'bg-proceed-bg text-proceed-fg border-proceed-bd', label: 'Pass' },
  borderline: { dot: 'bg-hold', chip: 'bg-hold-bg text-hold-fg border-hold-bd', label: 'Border' },
  fail: { dot: 'bg-rerun', chip: 'bg-rerun-bg text-rerun-fg border-rerun-bd', label: 'Fail' },
  not_gated: { dot: 'bg-line-strong', chip: 'bg-card-2 text-text-3 border-line', label: 'Ungated' },
}

const GROUP_LABEL: Record<GateReadout['gate'], string> = {
  preflight: 'Preflight gate',
  qc: 'QC gate',
  variant: 'Variant gate',
}

function StatusChip({ status }: { status: ReadoutStatus }) {
  const s = READOUT[status]
  return (
    <span
      className={`inline-flex items-center justify-center whitespace-nowrap rounded-full border px-[7px] py-0.5 text-[9.5px] font-semibold uppercase tracking-[0.3px] ${s.chip}`}
    >
      {s.label}
    </span>
  )
}

// The per-gate rollup pill: "N flagged" (amber) when any row is fail/borderline, else
// "all clear" (green) — reads the gate's own flagged_count so it can never disagree with the
// rows below it.
function Rollup({ flagged }: { flagged: number }) {
  const cls = flagged
    ? 'bg-hold-bg text-hold-fg border-hold-bd'
    : 'bg-proceed-bg text-proceed-fg border-proceed-bd'
  return (
    <span className={`ml-auto rounded-full border px-2 py-px text-[9.5px] font-semibold ${cls}`}>
      {flagged ? `${flagged} flagged` : 'all clear'}
    </span>
  )
}

export function QCReadout({ gates, variant }: { gates: GateReadout[]; variant: Variant }) {
  // Empty gate groups recede — a sample that never reached a gate has nothing to show there.
  const groups = gates.filter((g) => g.rows.length > 0)
  if (groups.length === 0) return null

  if (variant === 'split') {
    return (
      <div className="flex flex-col gap-3">
        {groups.map((g) => (
          <div key={g.gate} className="overflow-hidden rounded-[10px] border border-line">
            <div className="flex items-center gap-2 border-b border-line bg-card-2 px-[13px] py-2">
              <span className={`h-[7px] w-[7px] rounded-full ${GATE_DOT[g.gate]}`} />
              <span className="text-[10px] font-semibold uppercase tracking-[0.4px] text-text-2">
                {GROUP_LABEL[g.gate]}
              </span>
              <Rollup flagged={g.flagged_count} />
            </div>
            <div className="grid grid-cols-[1.7fr_0.8fr_1fr_0.7fr] text-[9px] font-semibold uppercase tracking-[0.4px] text-text-3">
              <div className="px-[13px] py-1.5">Metric</div>
              <div className="px-2 py-1.5">Observed</div>
              <div className="px-2 py-1.5">Threshold</div>
              <div className="px-2 py-1.5">Status</div>
            </div>
            {g.rows.map((m) => (
              <div
                key={m.metric}
                className="grid grid-cols-[1.7fr_0.8fr_1fr_0.7fr] items-center border-t border-line"
              >
                <div className="flex min-w-0 items-start gap-2 px-[13px] py-2">
                  <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${READOUT[m.status].dot}`} />
                  <div className="min-w-0 text-[12px] text-text">{m.label}</div>
                </div>
                <div className="px-2 py-2 font-mono text-[12px] font-semibold text-text">
                  {m.observed_display}
                </div>
                <div className="px-2 py-2 font-mono text-[11px] text-text-3">
                  {m.threshold_display ?? '—'}
                </div>
                <div className="px-2 py-2">
                  <StatusChip status={m.status} />
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    )
  }

  if (variant === 'brief') {
    return (
      <div className="flex flex-col gap-3">
        {groups.map((g) => (
          <div key={g.gate}>
            <div className="mb-1.5 flex items-center gap-[7px]">
              <span className={`h-[7px] w-[7px] rounded-full ${GATE_DOT[g.gate]}`} />
              <span className="text-[10px] font-semibold uppercase tracking-[0.4px] text-text-2">
                {GROUP_LABEL[g.gate]}
              </span>
              <Rollup flagged={g.flagged_count} />
            </div>
            <div className="flex flex-wrap gap-[7px]">
              {g.rows.map((m) => (
                <div
                  key={m.metric}
                  className="flex items-center gap-[7px] rounded-lg border border-line bg-card px-2.5 py-1.5"
                >
                  <span className="text-[11.5px] text-text-2">{m.label}</span>
                  <span className="font-mono text-[12.5px] font-semibold text-text">
                    {m.observed_display}
                  </span>
                  <StatusChip status={m.status} />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    )
  }

  // dense — inline chip rows per gate group.
  return (
    <div className="mt-2.5 flex flex-col gap-[7px]">
      {groups.map((g) => (
        <div key={g.gate} className="flex flex-wrap items-center gap-2">
          <span className="inline-flex min-w-[76px] items-center gap-[5px] text-[9.5px] font-semibold uppercase tracking-[0.3px] text-text-3">
            <span className={`h-1.5 w-1.5 rounded-full ${GATE_DOT[g.gate]}`} />
            {GROUP_LABEL[g.gate]}
          </span>
          {g.rows.map((m) => (
            <span key={m.metric} className="inline-flex items-center gap-[5px] text-[11px] text-text-2">
              <span className="text-text-3">{m.label}</span>
              <span className="font-mono font-semibold text-text">{m.observed_display}</span>
              <StatusChip status={m.status} />
            </span>
          ))}
        </div>
      ))}
    </div>
  )
}
