import { useEffect, useRef } from 'react'

// The one checkbox box every UIC-3 list renders, so selection reads consistently app-wide. Purely
// presentational: it owns no state — the parent drives `checked` and handles the toggle. The click is
// surfaced through `onToggle(shiftKey)` (read off the click, not onChange) because the range-select
// model needs the shift modifier, and keyboard activation (space) also dispatches a click, so this
// stays accessible. `indeterminate` (a parent with some — but not all — children selected) has no HTML
// attribute; it's a live DOM property, so it's applied imperatively via a ref.
export function Check({
  checked,
  indeterminate,
  onToggle,
  disabled,
  label,
  className,
}: {
  checked: boolean
  indeterminate?: boolean
  onToggle: (shiftKey: boolean) => void
  disabled?: boolean
  label?: string // accessible name, e.g. "Select RUN-2026-06-14-GIAB-A"
  className?: string
}) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate ?? false
  }, [indeterminate])

  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      disabled={disabled}
      aria-label={label}
      // Controlled via `checked` + driven by onClick (which carries shiftKey); `readOnly` suppresses
      // React's "checked without onChange" warning without letting the native box self-toggle.
      readOnly
      onClick={(e) => onToggle(e.shiftKey)}
      className={`h-3.5 w-3.5 accent-accent ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'} ${className ?? ''}`}
    />
  )
}
