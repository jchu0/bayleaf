import type { ReactNode } from 'react'

export type SegmentOption<T extends string> = { value: T; label: ReactNode }

// A pill-segmented toggle (Upload/BaseSpace, Theme, Density, 7/14/30d window, …). Generic over
// the value union so callers stay type-safe. Exposes radiogroup semantics (role + aria-checked) so
// AT announces it as a single-choice control; pass `label` to give the group an accessible name.
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  className,
  label,
}: {
  options: SegmentOption<T>[]
  value: T
  onChange: (value: T) => void
  className?: string
  label?: string
}) {
  return (
    <div
      className={`inline-flex rounded-lg border border-line bg-card-2 p-0.5 ${className ?? ''}`}
      role="radiogroup"
      aria-label={label}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`rounded-[6px] px-3 py-1 text-[13px] transition-colors ${
            o.value === value
              ? 'bg-card font-medium text-text shadow-card'
              : 'text-text-2 hover:text-text'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
