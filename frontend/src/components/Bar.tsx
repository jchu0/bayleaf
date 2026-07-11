// Canonical horizontal bars (G3) — one geometry for every bar so the app no longer carries three
// heights (h-2 / h-[11px]), two radii (5 / 6), and two gap sizes. Both are h-2 · rounded-[5px] (the
// refined Runs-bar geometry); segments sit 2px apart so adjacent tones read as distinct blocks.
// Colors are passed as full utility classes so the Tailwind compiler sees them and theming holds.

export type BarSegment = { key: string; value: number; className: string; title?: string }

// A proportional distribution bar (verdict / status mix). Zero-value segments drop out so the strip
// never lies about the mix; an all-zero bar renders an empty track.
export function SegmentBar({ segments, className }: { segments: BarSegment[]; className?: string }) {
  const shown = segments.filter((s) => s.value > 0)
  const total = shown.reduce((n, s) => n + s.value, 0)
  return (
    <div className={`flex h-2 gap-[2px] overflow-hidden rounded-[5px] bg-card-2 ${className ?? ''}`}>
      {shown.map((s) => (
        <span
          key={s.key}
          title={s.title}
          className={`min-w-[4px] ${s.className}`}
          style={{ width: `${(s.value / total) * 100}%` }}
        />
      ))}
    </div>
  )
}

// A single value (0–100) against a track. Same height/radius as SegmentBar so a meter and a
// distribution never look like two different widgets.
export function MeterBar({
  value,
  fillClassName,
  trackClassName,
  className,
}: {
  value: number
  fillClassName: string
  trackClassName?: string
  className?: string
}) {
  return (
    <div className={`h-2 overflow-hidden rounded-[5px] ${trackClassName ?? 'bg-card-2'} ${className ?? ''}`}>
      <div className={`h-full ${fillClassName}`} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  )
}
