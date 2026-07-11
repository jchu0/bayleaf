import { useState } from 'react'
import {
  AlignCenterHorizontal,
  AlignCenterVertical,
  AlignEndHorizontal,
  AlignEndVertical,
  AlignHorizontalDistributeCenter,
  AlignStartHorizontal,
  AlignStartVertical,
  AlignVerticalDistributeCenter,
  CopyPlus,
  Trash2,
} from 'lucide-react'

// Floating action bar for a multi-node selection (PB2 §4.2 / P4c). Bottom-center over the canvas;
// a bounded, scale-safe control set (NOT a per-row list) — align/distribute the selection, duplicate
// it, or delete it. All ops are local draft mutations (compose ≠ execute); delete routes through the
// caller's confirm/undo policy.

export type AlignKind = 'left' | 'hcenter' | 'right' | 'top' | 'vmiddle' | 'bottom'
export type DistributeAxis = 'h' | 'v'

const ALIGN_ITEMS: { kind: AlignKind; icon: typeof AlignStartVertical; label: string }[] = [
  { kind: 'left', icon: AlignStartVertical, label: 'Align left' },
  { kind: 'hcenter', icon: AlignCenterVertical, label: 'Align center (x)' },
  { kind: 'right', icon: AlignEndVertical, label: 'Align right' },
  { kind: 'top', icon: AlignStartHorizontal, label: 'Align top' },
  { kind: 'vmiddle', icon: AlignCenterHorizontal, label: 'Align middle (y)' },
  { kind: 'bottom', icon: AlignEndHorizontal, label: 'Align bottom' },
]

export function SelectionActionBar({
  count,
  onAlign,
  onDistribute,
  onDuplicate,
  onDelete,
}: {
  count: number
  onAlign: (k: AlignKind) => void
  onDistribute: (a: DistributeAxis) => void
  onDuplicate: () => void
  onDelete: () => void
}) {
  const [menu, setMenu] = useState<'align' | 'distribute' | null>(null)
  const canDistribute = count >= 3 // distributing < 3 nodes is a no-op

  return (
    <div className="absolute bottom-14 left-1/2 z-[7] flex -translate-x-1/2 items-center gap-1 rounded-xl border border-line-strong bg-card px-1.5 py-1 shadow-pop">
      <span className="px-2 text-[11.5px] font-semibold text-text-2">{count} selected</span>
      <span className="mx-0.5 h-4 w-px bg-line" />

      <div className="relative">
        <button
          type="button"
          onClick={() => setMenu((m) => (m === 'align' ? null : 'align'))}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] font-medium text-text-2 hover:bg-card-2"
        >
          <AlignCenterVertical size={13} /> Align
        </button>
        {menu === 'align' && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setMenu(null)} />
            <div className="absolute bottom-full left-0 z-20 mb-1.5 grid grid-cols-3 gap-0.5 rounded-lg border border-line-strong bg-card p-1 shadow-pop">
              {ALIGN_ITEMS.map((a) => {
                const Icon = a.icon
                return (
                  <button
                    key={a.kind}
                    type="button"
                    title={a.label}
                    onClick={() => {
                      setMenu(null)
                      onAlign(a.kind)
                    }}
                    className="grid h-7 w-7 place-items-center rounded-md text-text-2 hover:bg-card-2"
                  >
                    <Icon size={15} />
                  </button>
                )
              })}
            </div>
          </>
        )}
      </div>

      <div className="relative">
        <button
          type="button"
          disabled={!canDistribute}
          onClick={() => setMenu((m) => (m === 'distribute' ? null : 'distribute'))}
          className={`flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] font-medium ${
            canDistribute ? 'text-text-2 hover:bg-card-2' : 'cursor-not-allowed text-text-3'
          }`}
        >
          <AlignHorizontalDistributeCenter size={13} /> Distribute
        </button>
        {menu === 'distribute' && canDistribute && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setMenu(null)} />
            <div className="absolute bottom-full left-0 z-20 mb-1.5 flex gap-0.5 rounded-lg border border-line-strong bg-card p-1 shadow-pop">
              <button
                type="button"
                title="Distribute horizontally"
                onClick={() => {
                  setMenu(null)
                  onDistribute('h')
                }}
                className="grid h-7 w-7 place-items-center rounded-md text-text-2 hover:bg-card-2"
              >
                <AlignHorizontalDistributeCenter size={15} />
              </button>
              <button
                type="button"
                title="Distribute vertically"
                onClick={() => {
                  setMenu(null)
                  onDistribute('v')
                }}
                className="grid h-7 w-7 place-items-center rounded-md text-text-2 hover:bg-card-2"
              >
                <AlignVerticalDistributeCenter size={15} />
              </button>
            </div>
          </>
        )}
      </div>

      <span className="mx-0.5 h-4 w-px bg-line" />
      <button
        type="button"
        onClick={onDuplicate}
        className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] font-medium text-text-2 hover:bg-card-2"
      >
        <CopyPlus size={13} /> Duplicate
      </button>
      <button
        type="button"
        onClick={onDelete}
        className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] font-medium text-escalate-fg hover:bg-escalate-bg"
      >
        <Trash2 size={13} /> Delete
      </button>
    </div>
  )
}
