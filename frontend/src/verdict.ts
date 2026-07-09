import type { Gate, Severity, Verdict } from './types'

export const VERDICT_LABEL: Record<Verdict, string> = {
  proceed: 'Proceed',
  hold: 'Hold',
  rerun: 'Rerun',
  escalate: 'Escalate',
}

// Full static class strings so Tailwind's compiler sees them (no `text-${v}`).
export const VERDICT_TEXT: Record<Verdict, string> = {
  proceed: 'text-proceed',
  hold: 'text-hold',
  rerun: 'text-rerun',
  escalate: 'text-escalate',
}

export const VERDICT_DOT: Record<Verdict, string> = {
  proceed: 'bg-proceed',
  hold: 'bg-hold',
  rerun: 'bg-rerun',
  escalate: 'bg-escalate',
}

// Solid verdict fills for segmented/stacked bars.
export const VERDICT_BAR: Record<Verdict, string> = {
  proceed: 'bg-proceed',
  hold: 'bg-hold',
  rerun: 'bg-rerun',
  escalate: 'bg-escalate',
}

// 4-shade verdict badge (tinted bg + border + fg) — the handoff's badge treatment.
export const VERDICT_BADGE: Record<Verdict, string> = {
  proceed: 'bg-proceed-bg text-proceed-fg border-proceed-bd',
  hold: 'bg-hold-bg text-hold-fg border-hold-bd',
  rerun: 'bg-rerun-bg text-rerun-fg border-rerun-bd',
  escalate: 'bg-escalate-bg text-escalate-fg border-escalate-bd',
}

export const GATE_LABEL: Record<Gate, string> = {
  preflight: 'Preflight',
  qc: 'QC',
  variant: 'Variant',
}

// Gate accent dots (preflight/qc blue, variant teal) per the handoff.
export const GATE_DOT: Record<Gate, string> = {
  preflight: 'bg-preflight',
  qc: 'bg-qc',
  variant: 'bg-variant',
}

// pass / borderline / fail status chip, derived from a finding's severity.
export const STATUS_CHIP: Record<Severity, { label: string; cls: string }> = {
  critical: { label: 'Fail', cls: 'bg-escalate-bg text-escalate-fg border-escalate-bd' },
  warn: { label: 'Border', cls: 'bg-hold-bg text-hold-fg border-hold-bd' },
  info: { label: 'Pass', cls: 'bg-proceed-bg text-proceed-fg border-proceed-bd' },
}

export const SEVERITY_DOT: Record<Severity, string> = {
  critical: 'bg-crit',
  warn: 'bg-warn',
  info: 'bg-info',
}
