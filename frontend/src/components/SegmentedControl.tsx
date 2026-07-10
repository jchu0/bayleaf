import type { ReactNode } from 'react'

export type SegmentOption<T extends string> = { value: T; label: ReactNode }

// A pill-segmented toggle (Upload/BaseSpace, Theme, Density, 7/14/30d window, …). Generic over
// the value union so callers stay type-safe.
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  className,
}: {
  options: SegmentOption<T>[]
  value: T
  onChange: (value: T) => void
  className?: string
}) {
  return (
    <div className={`inline-flex rounded-lg border border-line bg-card-2 p-0.5 ${className ?? ''}`}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
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
