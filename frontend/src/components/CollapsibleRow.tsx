import { ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'

// A collapsible card whose header row IS the toggle (Intake admission rows, Monitoring
// signatures, Review-queue tickets, Decision cards). The header is a role="button" div (not a
// <button>) so it may contain its own nested actions/links — those should stopPropagation.
export function CollapsibleRow({
  open,
  onToggle,
  header,
  children,
  className,
}: {
  open: boolean
  onToggle: () => void
  header: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`overflow-hidden rounded-xl border border-line bg-card shadow-card ${className ?? ''}`}>
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onToggle()
          }
        }}
        className="flex w-full cursor-pointer items-center gap-3 px-4 py-3 text-left"
      >
        <ChevronRight
          size={16}
          className={`shrink-0 text-text-3 transition-transform ${open ? 'rotate-90' : ''}`}
        />
        <div className="min-w-0 flex-1">{header}</div>
      </div>
      {open && <div className="border-t border-line px-4 py-4">{children}</div>}
    </div>
  )
}
