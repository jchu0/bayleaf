import type { Gate, Severity, Verdict } from './types'

export const VERDICT_LABEL: Record<Verdict, string> = {
  proceed: 'Proceed',
  hold: 'Hold',
  rerun: 'Rerun',
  escalate: 'Escalate',
}

// Full static class strings so Tailwind's compiler can see them (no `text-${v}`).
export const VERDICT_TEXT: Record<Verdict, string> = {
  proceed: 'text-proceed',
  hold: 'text-hold',
  rerun: 'text-rerun',
  escalate: 'text-escalate',
}

export const VERDICT_BADGE: Record<Verdict, string> = {
  proceed: 'bg-proceed/15 text-proceed border-proceed/40',
  hold: 'bg-hold/15 text-hold border-hold/40',
  rerun: 'bg-rerun/15 text-rerun border-rerun/40',
  escalate: 'bg-escalate/15 text-escalate border-escalate/40',
}

export const SEVERITY_ICON: Record<Severity, string> = {
  critical: '🔴',
  warn: '🟡',
  info: '🔵',
}

export const GATE_LABEL: Record<Gate, string> = {
  preflight: 'Preflight',
  qc: 'QC',
  variant: 'Variant',
}
