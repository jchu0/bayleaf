import { SegmentedControl, type SegmentOption } from './SegmentedControl'

// The canonical "Showing X–Y of Z + per-page + prev/numbered/next" footer, extracted from the
// idiom duplicated across Runs / Monitoring / Admin / AgentTriage. One place so every paginated
// surface reads identically and new surfaces (Provenance event trail/artifacts, accessioning)
// don't mint another copy. Purely presentational — the caller owns the page/perPage state and the
// slicing; this only renders the controls and reports intent.

export type PerPage = '10' | '25' | '50' | '100'
export const PER_PAGE_25: SegmentOption<PerPage>[] = [
  { value: '25', label: '25' },
  { value: '50', label: '50' },
  { value: '100', label: '100' },
]
export const PER_PAGE_10: SegmentOption<PerPage>[] = [
  { value: '10', label: '10' },
  { value: '25', label: '25' },
  { value: '50', label: '50' },
]

export function Pager({
  total,
  page,
  perPage,
  onPage,
  onPerPage,
  perPageOptions = PER_PAGE_25,
  noun = 'items',
  hidePerPage = false,
}: {
  total: number
  page: number
  perPage: PerPage
  onPage: (p: number) => void
  // Optional so a fixed-page-size caller (e.g. Settings' agent roster) can omit it entirely and pass
  // hidePerPage; existing callers still pass it, so this widening is backward-compatible.
  onPerPage?: (p: PerPage) => void
  perPageOptions?: SegmentOption<PerPage>[]
  noun?: string
  hidePerPage?: boolean
}) {
  if (total === 0) return null
  const per = Number(perPage)
  const pages = Math.max(1, Math.ceil(total / per))
  const cur = Math.min(page, pages)
  const from = (cur - 1) * per + 1
  const to = Math.min(cur * per, total)
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3 text-[11.5px] text-text-2">
      <span>
        Showing {from}–{to} of {total} {noun}
      </span>
      <div className="flex flex-wrap items-center gap-3">
        {!hidePerPage && onPerPage && (
          <div className="flex items-center gap-1.5">
            <span className="text-[11.5px] text-text-3">Per page</span>
            <SegmentedControl<PerPage> options={perPageOptions} value={perPage} onChange={onPerPage} />
          </div>
        )}
        {pages > 1 && (
          // nav landmark so AT users can jump to the pager; aria-current marks the active page. The
          // prev/next buttons use the native `disabled` attribute, which already conveys the disabled
          // state to assistive tech (aria-disabled would be redundant on top of it).
          <nav className="flex items-center gap-1" aria-label="Pagination">
            <button
              type="button"
              onClick={() => onPage(Math.max(1, cur - 1))}
              disabled={cur === 1}
              className="h-7 min-w-[28px] rounded-[7px] border border-line bg-card text-[13px] text-text-2 transition-colors hover:border-line-strong disabled:opacity-40"
              aria-label="Previous page"
            >
              ‹
            </button>
            {Array.from({ length: pages }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => onPage(n)}
                aria-current={n === cur ? 'page' : undefined}
                aria-label={`Page ${n}`}
                className={`h-7 min-w-[28px] rounded-[7px] px-2 text-[12px] transition-colors ${
                  n === cur
                    ? 'bg-accent font-semibold text-white'
                    : 'border border-line bg-card text-text-2 hover:border-line-strong'
                }`}
              >
                {n}
              </button>
            ))}
            <button
              type="button"
              onClick={() => onPage(Math.min(pages, cur + 1))}
              disabled={cur === pages}
              className="h-7 min-w-[28px] rounded-[7px] border border-line bg-card text-[13px] text-text-2 transition-colors hover:border-line-strong disabled:opacity-40"
              aria-label="Next page"
            >
              ›
            </button>
          </nav>
        )}
      </div>
    </div>
  )
}
