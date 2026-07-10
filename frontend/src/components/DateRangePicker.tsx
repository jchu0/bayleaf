import { Calendar, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import { useState } from 'react'

// A fixed-width date-range trigger + month-grid popover (Runs scale kit, §5.2). Controlled:
// `start`/`end` are ISO `YYYY-MM-DD` (or null); the parent owns the range and filters on it.
// The trigger keeps a FIXED min-width so a digit-count change ("Any date" → "Jul 2 – Jul 8")
// never reflows the toolbar row. Backend has no dateFrom/dateTo param (F16) — the caller filters
// client-side on run_date, so this is a pure presentational control over that range.

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]
const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

const pad2 = (n: number) => (n < 10 ? '0' : '') + n
const isoOf = (y: number, m: number, d: number) => `${y}-${pad2(m + 1)}-${pad2(d)}`
// "2026-07-08" → "Jul 8" for the compact trigger label.
function fmtShort(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${MONTHS_SHORT[Number(m) - 1]} ${Number(d)}`
}

type DayCell = { blank: true } | { blank: false; day: number; iso: string }

export function DateRangePicker({
  start,
  end,
  onChange,
}: {
  start: string | null
  end: string | null
  onChange: (start: string | null, end: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const today = new Date()
  const [view, setView] = useState<{ y: number; m: number }>({
    y: today.getFullYear(),
    m: today.getMonth(),
  })

  const active = !!(start || end)
  const label =
    start && end ? `${fmtShort(start)} – ${fmtShort(end)}` : start ? `${fmtShort(start)} – …` : 'Any date'

  const firstDow = new Date(view.y, view.m, 1).getDay()
  const daysInMonth = new Date(view.y, view.m + 1, 0).getDate()
  const cells: DayCell[] = []
  for (let i = 0; i < firstDow; i++) cells.push({ blank: true })
  for (let d = 1; d <= daysInMonth; d++) cells.push({ blank: false, day: d, iso: isoOf(view.y, view.m, d) })

  // Two-tap range: an empty (or already-complete) range starts a new one; a second tap on/after
  // the start closes it, a tap before the start re-anchors. Mirrors the prototype's pick logic.
  const pick = (iso: string) => {
    if (!start || (start && end)) onChange(iso, null)
    else if (iso >= start) onChange(start, iso)
    else onChange(iso, null)
  }

  // `n` days before today, as ISO — for the "Last 7d / 14d" presets (relative to the real clock,
  // so an out-of-window archive honestly shows nothing rather than a fabricated match).
  const backIso = (n: number) => {
    const t = new Date(today)
    t.setDate(t.getDate() - n)
    return isoOf(t.getFullYear(), t.getMonth(), t.getDate())
  }

  const prevMonth = () => setView((v) => (v.m === 0 ? { y: v.y - 1, m: 11 } : { y: v.y, m: v.m - 1 }))
  const nextMonth = () => setView((v) => (v.m === 11 ? { y: v.y + 1, m: 0 } : { y: v.y, m: v.m + 1 }))

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`inline-flex min-w-[162px] items-center gap-[7px] rounded-lg border px-[11px] py-[7px] text-[12px] font-medium transition-colors ${
          active ? 'border-accent bg-accent-weak text-accent-strong' : 'border-line-strong bg-card text-text-2'
        }`}
      >
        <Calendar size={14} className="shrink-0" />
        {label}
        <ChevronDown size={12} className="ml-auto shrink-0" />
      </button>

      {open && (
        <>
          {/* full-viewport click-catcher (below the panel) so any outside click dismisses */}
          <div className="fixed inset-0 z-[29]" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-10 z-30 w-[252px] rounded-xl border border-line-strong bg-card p-3 shadow-[0_16px_40px_rgba(16,24,40,0.18)]">
            <div className="mb-[11px] flex items-center gap-[7px]">
              <input
                type="date"
                value={start ?? ''}
                onChange={(e) => onChange(e.target.value || null, end)}
                className="min-w-0 flex-1 rounded-[7px] border border-line-strong bg-card px-[7px] py-1.5 text-[11px] text-text"
              />
              <span className="shrink-0 text-[12px] text-text-3">–</span>
              <input
                type="date"
                value={end ?? ''}
                onChange={(e) => onChange(start, e.target.value || null)}
                className="min-w-0 flex-1 rounded-[7px] border border-line-strong bg-card px-[7px] py-1.5 text-[11px] text-text"
              />
            </div>

            <div className="mb-[9px] flex items-center justify-between">
              <button
                type="button"
                onClick={prevMonth}
                className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px] border border-line bg-card text-text-2 transition-colors hover:border-line-strong"
                aria-label="Previous month"
              >
                <ChevronLeft size={13} />
              </button>
              <span className="text-[12.5px] font-semibold text-text">
                {MONTHS[view.m]} {view.y}
              </span>
              <button
                type="button"
                onClick={nextMonth}
                className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px] border border-line bg-card text-text-2 transition-colors hover:border-line-strong"
                aria-label="Next month"
              >
                <ChevronRight size={13} />
              </button>
            </div>

            <div className="mb-[3px] grid grid-cols-7 gap-0.5">
              {WEEKDAYS.map((w) => (
                <div key={w} className="flex h-[22px] items-center justify-center text-[9.5px] font-semibold text-text-3">
                  {w}
                </div>
              ))}
            </div>

            <div className="grid grid-cols-7 gap-0.5">
              {cells.map((c, i) => {
                if (c.blank) return <span key={`b${i}`} />
                const selected = c.iso === start || c.iso === end
                const inRange = !!(start && end && c.iso >= start && c.iso <= end)
                return (
                  <button
                    key={c.iso}
                    type="button"
                    onClick={() => pick(c.iso)}
                    className={`flex h-[30px] items-center justify-center rounded-[7px] text-[12px] transition-colors ${
                      selected
                        ? 'bg-accent font-semibold text-white'
                        : inRange
                          ? 'bg-accent-weak text-text'
                          : 'text-text hover:bg-card-2'
                    }`}
                  >
                    {c.day}
                  </button>
                )
              })}
            </div>

            <div className="mt-[11px] flex items-center gap-1.5 border-t border-line pt-2.5">
              <button
                type="button"
                onClick={() => onChange(backIso(6), backIso(0))}
                className="rounded-[7px] border border-line bg-card-2 px-[9px] py-1 text-[11px] text-text-2 transition-colors hover:border-line-strong"
              >
                Last 7d
              </button>
              <button
                type="button"
                onClick={() => onChange(backIso(13), backIso(0))}
                className="rounded-[7px] border border-line bg-card-2 px-[9px] py-1 text-[11px] text-text-2 transition-colors hover:border-line-strong"
              >
                Last 14d
              </button>
              <button
                type="button"
                onClick={() => onChange(null, null)}
                className="ml-auto px-1.5 py-1 text-[11px] text-accent-strong hover:underline"
              >
                Clear
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
