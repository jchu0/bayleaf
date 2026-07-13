import type { DecisionCard, Gate, RunStatus, Severity, Verdict } from './types'

// Real run-status → pill dot + display label. Driven off RunSummary.status, NEVER inferred from
// n_attention (F17): a `running` run with 0 flagged samples is "Sequencing", not "Released".
// Shared by the Runs list and the top-bar run switcher so both read status identically.
// UIUX-02: lifecycle dots use a palette RESERVED away from the verdict hues (proceed/hold/rerun/
// escalate) so a run-lifecycle dot can never be misread as a sample verdict — the old mapping put
// amber `bg-hold` (= verdict Hold) on "Needs review" and green `bg-proceed` (= verdict Proceed) on
// "Released", stacking two amber/green signals on one Runs card. accent (needs a human), teal
// (machine sequencing), and neutral grey (released/filed) are none of the four verdict colors.
export const RUN_STATUS_META: Record<RunStatus, { dot: string; label: string }> = {
  needs_review: { dot: 'bg-accent', label: 'Needs review' },
  running: { dot: 'bg-variant', label: 'Sequencing' },
  released: { dot: 'bg-text-3', label: 'Released' },
}

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

// Per-verdict left border-color for a card's colored spine (pair with `border-l-[3px]`),
// so a collapsed/compact card reads its verdict at a glance. Full static strings so the
// Tailwind compiler emits the utilities.
export const VERDICT_STRIPE: Record<Verdict, string> = {
  proceed: 'border-l-proceed',
  hold: 'border-l-hold',
  rerun: 'border-l-rerun',
  escalate: 'border-l-escalate',
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

// Longer gate tag used where a bare "QC" would be ambiguous (a card's governing-gate line, the
// lineage stage pill, the gate-result strip). ONE definition — was copy-pasted verbatim across
// RunDetail, Lineage, and GateResultStrip (UX-DUP: GATE_TAG ×3).
export const GATE_TAG: Record<Gate, string> = {
  preflight: 'Preflight',
  qc: 'QC gate',
  variant: 'Variant gate',
}

// Verdict severity order, most-urgent first, for sorting cards/tickets. ONE definition — was
// copy-pasted (as ORDER / VERDICT_ORDER / VERDICT_RANK) across RunDetail, RunReport, ReviewQueue,
// and Lineage (UX-DUP: verdict ORDER ×4). Same numbers everywhere so two views can never sort the
// same cards differently.
export const VERDICT_ORDER: Record<Verdict, number> = {
  escalate: 0,
  rerun: 1,
  hold: 2,
  proceed: 3,
}

// The gate that GOVERNS a card's verdict: the gate whose own verdict equals the card's overall
// verdict, else the first finding's gate, else null. ONE definition — the exact expression was
// copy-pasted across RunDetail (×2) and AgentTriage (UX-DUP: governingGate ×3), so a change to gate
// attribution now lands once instead of risking three screens showing a sample under different gates.
export function governingGate(card: Pick<DecisionCard, 'gate_results' | 'findings' | 'verdict'>): Gate | null {
  return card.gate_results.find((g) => g.verdict === card.verdict)?.gate ?? card.findings[0]?.gate ?? null
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
