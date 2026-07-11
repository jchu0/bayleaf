import { useCallback, useRef, useState } from 'react'

// The one checkbox multi-select model app-wide (UIC-3), so every checkbox list — Review queue
// (canonical), Submit, Settings agent table, Inbox, Accession — behaves identically: a plain click
// toggles one id and drops an anchor; a shift-click extends a contiguous range from that anchor; a
// parent checkbox drives all its children through setMany. The hook owns ONLY selection state (a Set
// of ids) — it renders nothing and knows nothing about rows — so it stays unit-testable and reusable
// across both the flat (Submit) and hierarchical (Review queue) layouts.
//
// `orderedIds` is the flat top-to-bottom RENDER order; range math is index-based over it, so a
// shift-select always spans exactly what the operator sees between anchor and target (never a hidden
// or filtered-out row).
export type RangeSelect = {
  selected: Set<string>
  isSelected: (id: string) => boolean
  // Plain click → toggle this id and make it the range anchor. Shift-click → select the contiguous
  // run from the last anchor (or the first id if there is none yet) through `id`, inclusive, leaving
  // the anchor put so successive shift-clicks extend from the same origin (Finder/Gmail semantics).
  toggle: (id: string, shiftKey?: boolean) => void
  setMany: (ids: string[], on: boolean) => void // a parent checkbox → drive all its children at once
  clear: () => void
  allSelected: (ids: string[]) => boolean
}

export function useRangeSelect(orderedIds: string[]): RangeSelect {
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  // Latest render order + anchor kept in refs so the callbacks stay stable (no identity churn as the
  // parent re-renders a fresh orderedIds array each frame) yet always read the current values — the
  // same closure discipline as useTopologyHistory.
  const order = useRef(orderedIds)
  order.current = orderedIds
  const anchor = useRef<string | null>(null)

  const toggle = useCallback((id: string, shiftKey?: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (shiftKey) {
        const ids = order.current
        const from = anchor.current != null ? ids.indexOf(anchor.current) : 0
        const to = ids.indexOf(id)
        // A missing anchor or target (e.g. filtered out of the current order) degrades to a single
        // toggle rather than selecting a bogus range.
        if (from === -1 || to === -1) {
          if (next.has(id)) next.delete(id)
          else next.add(id)
          anchor.current = id
          return next
        }
        const lo = Math.min(from, to)
        const hi = Math.max(from, to)
        for (let i = lo; i <= hi; i++) next.add(ids[i]) // shift extends the selection ON; anchor stays put
      } else {
        if (next.has(id)) next.delete(id)
        else next.add(id)
        anchor.current = id
      }
      return next
    })
  }, [])

  const setMany = useCallback((ids: string[], on: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev)
      for (const id of ids) {
        if (on) next.add(id)
        else next.delete(id)
      }
      return next
    })
  }, [])

  const clear = useCallback(() => {
    anchor.current = null
    setSelected(new Set())
  }, [])

  const isSelected = useCallback((id: string) => selected.has(id), [selected])
  // A parent is fully-checked only when its children exist AND every one is selected — an empty group
  // is never "all selected" (so a parent checkbox over zero children reads unchecked, not checked).
  const allSelected = useCallback(
    (ids: string[]) => ids.length > 0 && ids.every((id) => selected.has(id)),
    [selected],
  )

  return { selected, isSelected, toggle, setMany, clear, allSelected }
}
