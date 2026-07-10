import type { ReactNode } from 'react'

// A filter/facet chip with an optional mono count badge (Runs status facets, Decision verdict
// filters, Review-queue status). ~20px radius per the design's chip shape.
export function FacetChip({
  label,
  count,
  active,
  onClick,
}: {
  label: ReactNode
  count?: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12.5px] transition-colors ${
        active
          ? 'border-accent bg-accent-weak font-semibold text-accent-strong'
          : 'border-line-strong bg-card font-medium text-text-2 hover:border-line-strong hover:text-text'
      }`}
    >
      {label}
      {count != null && (
        <span
          className={`rounded-[10px] px-[7px] py-px font-mono text-[11px] font-semibold ${
            active ? 'bg-accent text-white' : 'bg-card-3 text-text-2'
          }`}
        >
          {count}
        </span>
      )}
    </button>
  )
}
