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
          ? 'border-accent bg-accent-weak font-medium text-accent-strong'
          : 'border-line bg-card text-text-2 hover:border-line-strong'
      }`}
    >
      {label}
      {count != null && (
        <span className={`font-mono text-[11px] ${active ? 'text-accent-strong' : 'text-text-3'}`}>
          {count}
        </span>
      )}
    </button>
  )
}
