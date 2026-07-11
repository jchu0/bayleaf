import type { ReactNode } from 'react'

// A traditional underline tab bar — the canonical VIEW-SELECTOR across the app (G5). It reads
// unambiguously as "pick a view", unlike the rounded-full filter pills it replaces in Runs /
// Review queue (which looked like highlighted values, not controls). Distinct on purpose from
// SegmentedControl, which stays for compact toggle SETTINGS (7d/14d/30d window, theme, density).
// Generic over the value union so callers stay type-safe; optional count badge + leading icon.

export type TabItem<T extends string> = { value: T; label: ReactNode; count?: number; icon?: ReactNode }

export function Tabs<T extends string>({
  items,
  value,
  onChange,
  className,
}: {
  items: TabItem<T>[]
  value: T
  onChange: (value: T) => void
  className?: string
}) {
  return (
    <div className={`flex items-center gap-0.5 overflow-x-auto border-b border-line ${className ?? ''}`} role="tablist">
      {items.map((it) => {
        const active = it.value === value
        return (
          <button
            key={it.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(it.value)}
            className={`relative -mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-[13px] transition-colors ${
              active
                ? 'border-accent font-semibold text-text'
                : 'border-transparent text-text-2 hover:border-line-strong hover:text-text'
            }`}
          >
            {it.icon}
            {it.label}
            {it.count != null && (
              <span
                className={`rounded-full px-1.5 py-px font-mono text-[10.5px] ${
                  active ? 'bg-accent-weak text-accent-strong' : 'bg-card-2 text-text-3'
                }`}
              >
                {it.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
