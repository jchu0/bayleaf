import type { ReactNode } from 'react'

// The shared page title block (F1): a mono-ish uppercase eyebrow + a Newsreader serif H1 +
// optional subtitle, with an optional right-aligned actions slot (Refresh, window selector, …).
// Every screen routes its title through here so the serif refresh lands once, everywhere.
export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="mb-5 flex items-start justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1 text-[11px] font-bold uppercase tracking-[1px] text-text-3">{eyebrow}</p>
        )}
        <h1 className="font-serif text-[27px] font-medium leading-[1.1] tracking-[-0.3px] text-text">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1.5 max-w-2xl text-[13.5px] leading-normal text-text-2">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}
