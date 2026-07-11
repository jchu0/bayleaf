import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { LucideIcon } from 'lucide-react'

// A small right-click menu for the builder canvas (PB2 §4.6) — the discoverability surface for the
// on-canvas edits (rename / duplicate / disconnect / delete / select-all / fit / tidy). Bounded item
// list, Escape + click-outside close, clamped into the viewport. Mirrors the ConfirmDialog/RunSelector
// overlay idiom (fixed overlay, token surfaces). Purely presentational — every item's effect is the
// caller's handler; nothing here mutates the graph.

export type MenuItem = {
  label: string
  icon?: LucideIcon
  danger?: boolean
  disabled?: boolean
  onClick: () => void
}

export function BuilderContextMenu({
  x,
  y,
  items,
  onClose,
}: {
  x: number
  y: number
  items: MenuItem[]
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [pos, setPos] = useState({ x, y })

  // Clamp into the viewport so a menu opened near the right/bottom edge stays fully visible.
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const nx = Math.min(x, window.innerWidth - r.width - 8)
    const ny = Math.min(y, window.innerHeight - r.height - 8)
    setPos({ x: Math.max(8, nx), y: Math.max(8, ny) })
  }, [x, y])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    // A full-screen catcher so any click (incl. right-click elsewhere) dismisses the menu.
    <div className="fixed inset-0 z-[60]" onClick={onClose} onContextMenu={(e) => { e.preventDefault(); onClose() }}>
      <div
        ref={ref}
        className="absolute min-w-[184px] overflow-hidden rounded-lg border border-line-strong bg-card py-1 shadow-pop"
        style={{ left: pos.x, top: pos.y }}
        onClick={(e) => e.stopPropagation()}
      >
        {items.map((it, i) => {
          const Icon = it.icon
          return (
            <button
              key={i}
              type="button"
              disabled={it.disabled}
              onClick={() => {
                if (it.disabled) return
                onClose()
                it.onClick()
              }}
              className={`flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-[12.5px] ${
                it.disabled
                  ? 'cursor-not-allowed text-text-3'
                  : it.danger
                    ? 'text-escalate-fg hover:bg-escalate-bg'
                    : 'text-text hover:bg-card-2'
              }`}
            >
              {Icon && <Icon size={14} className="shrink-0" />}
              <span className="flex-1">{it.label}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
