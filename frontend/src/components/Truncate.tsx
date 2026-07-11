import { type ElementType, useEffect, useRef, useState } from 'react'

// Full text on hover for any string too long to read in the card system (G2). Renders a single-line
// truncated string and attaches a native `title` tooltip ONLY when the text actually overflows —
// measured against the rendered box — so a short, fully-visible string carries no redundant tooltip.
// Re-measures on text change and on container resize (ResizeObserver), so it stays correct as cards
// reflow. Polymorphic via `as` (span by default) so it drops into headings, cells, list items, etc.
export function Truncate({
  text,
  className,
  as,
  title,
}: {
  text: string
  className?: string
  as?: ElementType
  // Override the hover text (defaults to `text`); useful when the visible label differs from the
  // full value you want to reveal.
  title?: string
}) {
  const Tag = as ?? 'span'
  const ref = useRef<HTMLElement>(null)
  const [overflowing, setOverflowing] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setOverflowing(el.scrollWidth > el.clientWidth + 1)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [text])

  return (
    <Tag ref={ref} title={overflowing ? (title ?? text) : undefined} className={`block truncate ${className ?? ''}`}>
      {text}
    </Tag>
  )
}
