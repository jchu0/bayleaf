import type { ReactNode } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// Missing — the MISSING-VALUE primitive (the honesty substrate).
//
// This repo's whole thesis is that we never fabricate a value and never let an
// absence masquerade as data: absent ≠ 0 ≠ blocked. Before this component,
// "absent" was rendered six different ways across the app (a bare "—", a "not
// captured" span in DecisionContextRail, an empty cell, an accidental 0). This
// is the single reusable source for "there is honestly no value here", so every
// absent scalar can route through ONE de-emphasized, clearly-labeled token.
//
// It generalizes DecisionContextRail's local NotCaptured() idiom
// (`<span className="text-text-3">not captured</span>`) into a semantic family:
// the *reason* a value is absent is itself information an operator needs, so the
// variant carries a distinct muted label + hover tooltip. It renders a clearly
// non-value token (a short faint label, or an em-dash) in text-text-3, font-normal
// — NEVER a 0 and NEVER a fabricated string.
//
// Reused by: DecisionContextRail (Subject/Type/Library/Origin), MetricsPanel /
// QCReadout (a metric whose check produced no observation), EvidenceTable
// observed/expected cells, and any panel projecting a nullable scalar.
//
// Usage:
//   <Missing variant="not-captured" />                    // → "not captured" (faint, tooltip)
//   <Missing variant="not-run" display="dash" />          // → "—" (tooltip carries the reason)
//   {formatScalar(card.coverage, { precision: 1, unit: '×' })}      // real value, or honest absence
//   {formatScalar(m.value, { percent: true, absence: 'not-measured' })}
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The semantic reason a value is absent. The *why* is operator-relevant, so each
 * variant gets a distinct label + tooltip rather than collapsing to one "—".
 *  - not-captured   — the field was never collected (e.g. intake carried no subject metadata)
 *  - not-measured   — the check ran but produced no observation for this metric
 *  - not-run        — the stage was skipped or blocked upstream (absent ≠ blocked verdict)
 *  - not-applicable — the field does not apply to this record
 *  - unknown        — generic fallback; reason unspecified
 */
export type AbsenceVariant =
  | 'not-captured'
  | 'not-measured'
  | 'not-run'
  | 'not-applicable'
  | 'unknown'

interface AbsenceMeta {
  /** Short faint label shown in `display="label"` mode. */
  label: string
  /** Longer hover explanation (native title tooltip). */
  tooltip: string
}

const ABSENCE: Record<AbsenceVariant, AbsenceMeta> = {
  'not-captured': {
    label: 'not captured',
    tooltip: 'Never collected — this field was not part of the record.',
  },
  'not-measured': {
    label: 'not measured',
    tooltip: 'The check ran but produced no observation for this value.',
  },
  'not-run': {
    label: 'not run',
    tooltip: 'The stage was skipped or blocked upstream — no value was produced.',
  },
  'not-applicable': {
    label: 'n/a',
    tooltip: 'Not applicable for this record.',
  },
  unknown: {
    label: 'unknown',
    tooltip: 'No value available; reason unspecified.',
  },
}

export interface MissingProps {
  /** Which semantic absence this is. Defaults to the generic `unknown`. */
  variant?: AbsenceVariant
  /**
   * How to render the token:
   *  - 'label' (default) — the short faint word ("not captured"), mirroring DecisionContextRail.
   *  - 'dash'            — a bare em-dash "—" for tight table cells; the reason lives in the tooltip.
   */
  display?: 'label' | 'dash'
  /** Override the visible label text (tooltip still carries the variant's explanation). */
  label?: ReactNode
  /** Extra classes to merge (e.g. alignment); never used to re-color into a value tone. */
  className?: string
}

/**
 * The single reusable "no value here" token. De-emphasized (text-text-3,
 * font-normal) so it can never be mistaken for authoritative data — advisory/
 * absent content stays visually quieter than real observations by construction.
 */
export function Missing({ variant = 'unknown', display = 'label', label, className = '' }: MissingProps) {
  const meta = ABSENCE[variant]
  const content = display === 'dash' ? '—' : (label ?? meta.label)
  return (
    <span
      title={meta.tooltip}
      aria-label={typeof content === 'string' ? content : meta.label}
      data-absence={variant}
      className={`font-normal text-text-3 ${className}`.trim()}
    >
      {content}
    </span>
  )
}

/** Options for {@link formatScalar}. */
export interface FormatScalarOpts {
  /** Which absence to show when the value is absent. Defaults to `unknown`. */
  absence?: AbsenceVariant
  /** How the absence token renders (label vs em-dash). Defaults to `dash` for scalar cells. */
  display?: 'label' | 'dash'
  /** Fixed decimal places (e.g. 1 → "31.0"). Omitted → the number renders as-is. */
  precision?: number
  /** Interpret the value as a fraction (0–1) and render as a percent (e.g. 0.98 → "98%"). */
  percent?: boolean
  /** Unit suffix appended to a present value (e.g. "×", " bp"). */
  unit?: string
  /**
   * Render present values in mono + tabular-nums (the repo convention for numerics
   * so digits align). Defaults to true; pass false for plain-text scalars.
   */
  mono?: boolean
  /** Extra classes merged onto the present-value span. */
  className?: string
}

/**
 * Render a scalar honestly: a real value when one is present, or a {@link Missing}
 * token when it is absent — so a caller never has to decide (and never accidentally
 * renders `0` or an empty string for "no data").
 *
 * ABSENCE is `null | undefined | '' | NaN`. **`0` and `false` are real values** and
 * render as themselves — the core honesty rule (absent ≠ 0). Numbers render in mono
 * tabular by default; strings pass through verbatim (never reformatted into a
 * fabricated shape).
 *
 * @param value the scalar to show (number, string, null, or undefined)
 * @param opts  formatting + which absence variant to fall back to
 */
export function formatScalar(
  value: number | string | null | undefined,
  opts: FormatScalarOpts = {},
): ReactNode {
  const { absence = 'unknown', display = 'dash', precision, percent, unit, mono = true, className = '' } = opts

  // Absent — but 0 and false are real. Only null/undefined/empty/NaN route to Missing.
  const isAbsent =
    value === null || value === undefined || value === '' || (typeof value === 'number' && Number.isNaN(value))
  if (isAbsent) return <Missing variant={absence} display={display} />

  let text: string
  if (typeof value === 'number') {
    const n = percent ? value * 100 : value
    const body = precision !== undefined ? n.toFixed(precision) : String(n)
    text = percent ? `${body}%` : unit ? `${body}${unit}` : body
  } else {
    // Strings render verbatim — we do not reshape provenance text.
    text = unit ? `${value}${unit}` : value
  }

  const tone = mono ? 'font-mono tabular-nums text-text' : 'text-text'
  return <span className={`${tone} ${className}`.trim()}>{text}</span>
}
