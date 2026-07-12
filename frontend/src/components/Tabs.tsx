import { useRef, type KeyboardEvent, type ReactNode } from 'react'

// FRAMED tabs — the canonical VIEW-SELECTOR across the app (G5, UIC-2). Each tab is a top-rounded
// shape with top/side borders sitting on a shared baseline; the ACTIVE tab connects to the content
// below (its card-colored bottom edge breaks through the baseline via -mb-px, so it reads as one
// surface with the card), while INACTIVE tabs are recessed (a muted card-2 fill, no lifted frame).
// The old underline-only bar read as highlighted text, not a control — this frames tabs AS tabs.
// Still distinct on purpose from SegmentedControl, which stays for compact toggle SETTINGS
// (7d/14d/30d window, theme, density). Consumers (Runs / Review queue / Admin / RunDetail /
// Provenance / Inbox) inherit automatically — same props/generics/count-badge API.
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
  // Roving-tabindex refs so ArrowLeft/Right (+ Home/End) move focus between tabs per the WAI-ARIA
  // tabs pattern. Only the active tab is in the Tab sequence; arrows move focus AND select
  // (automatic activation — these are cheap view switches).
  const btnRefs = useRef<(HTMLButtonElement | null)[]>([])
  const activeIdx = items.findIndex((it) => it.value === value)
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    let next: number | null = null
    if (e.key === 'ArrowRight') next = (activeIdx + 1 + items.length) % items.length
    else if (e.key === 'ArrowLeft') next = (activeIdx - 1 + items.length) % items.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = items.length - 1
    if (next === null || !items[next]) return
    e.preventDefault()
    onChange(items[next].value)
    btnRefs.current[next]?.focus()
  }
  return (
    <div
      className={`flex items-end gap-1 overflow-x-auto border-b border-line ${className ?? ''}`}
      role="tablist"
      onKeyDown={onKeyDown}
    >
      {items.map((it, i) => {
        const active = it.value === value
        return (
          <button
            key={it.value}
            ref={(el) => {
              btnRefs.current[i] = el
            }}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(it.value)}
            // -mb-px overlaps the container baseline; on the active tab a card-colored bottom border
            // paints over it so the tab merges into the content card (a real "connected" tab).
            className={`relative -mb-px flex shrink-0 items-center gap-1.5 rounded-t-[9px] border px-3.5 py-2 text-[13px] transition-colors ${
              active
                ? 'z-10 border-line border-b-card bg-card font-semibold text-text'
                : 'border-transparent bg-card-2 text-text-2 hover:border-line-strong hover:text-text'
            }`}
          >
            {it.icon}
            {it.label}
            {it.count != null && (
              <span
                className={`rounded-full px-1.5 py-px font-mono text-[10.5px] ${
                  active ? 'bg-accent-weak text-accent-strong' : 'bg-card-3 text-text-3'
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
