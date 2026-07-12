import { useEffect, useId, useMemo, useState } from 'react'
import { ChevronDown, Loader2, Search } from 'lucide-react'
import { api } from '../api'
import { RUN_STATUS_META } from '../verdict'
import type { RunStatus, RunSummary } from '../types'

// Stable empty fallback so `runs` keeps a referential identity across renders when neither an
// injected nor a self-fetched list is present (otherwise the memo below recomputes every render).
const NO_RUNS: RunSummary[] = []

// A reusable, searchable, keyboard-friendly run picker (T-070) sharing the top-bar switcher idiom
// (dot = REAL status, F17; capped rows; search by id/platform). Dependency-free. Never fabricates a
// run: on a fetch failure it says so honestly rather than showing a placeholder row. Off the gate —
// it is a pure input control that shows no verdict/confidence and triggers no execution.
export type RunSelectorProps = {
  value: string | null // selected run_id (controlled)
  onChange: (runId: string) => void
  runs?: RunSummary[] // optional pre-fetched list; if omitted, self-fetches lazily on first open
  status?: RunStatus // optional filter (e.g. 'released'); threaded to api.runs({ status }) on self-fetch
  placeholder?: string // trigger text when value is null
  disabled?: boolean
  maxRows?: number // capped visible rows (mirrors the top-bar switcher)
  align?: 'left' | 'right' // popover anchor side
  onViewAll?: () => void // optional footer action; omit to hide the footer
}

export function RunSelector({
  value,
  onChange,
  runs: injected,
  status,
  placeholder = 'Select a run…',
  disabled = false,
  maxRows = 8,
  align = 'left',
  onViewAll,
}: RunSelectorProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [fetched, setFetched] = useState<RunSummary[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  // Keyboard active-descendant: the highlighted option index within `matches` (arrow keys move it).
  const [active, setActive] = useState(0)
  const listboxId = useId()
  const optionId = (i: number) => `${listboxId}-opt-${i}`

  // Lazy self-fetch on first open (only when no list is injected). Honest on failure: no rows.
  // `error` is in the guard AND deps so a failed fetch settles into a STABLE "Couldn't load runs"
  // state instead of an infinite refetch loop (the loading true→false transition re-runs the effect;
  // without the error guard it would re-fire the request forever). `close()` clears error so
  // reopening the picker retries.
  useEffect(() => {
    if (injected || !open || fetched || loading || error) return
    setLoading(true)
    setError(false)
    api
      .runs(status ? { status } : undefined)
      .then((r) => setFetched(r))
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [open, injected, status, fetched, loading, error])

  const runs = injected ?? fetched ?? NO_RUNS
  const current = runs.find((r) => r.run_id === value)
  const q = query.trim().toLowerCase()
  const matches = useMemo(() => {
    const filtered = q
      ? runs.filter(
          (r) => r.run_id.toLowerCase().includes(q) || (r.platform ?? '').toLowerCase().includes(q),
        )
      : runs
    return filtered.slice(0, maxRows)
  }, [runs, q, maxRows])
  // Clamp the highlight into the current match range (a filter can shrink the list under `active`).
  const activeIdx = matches.length ? Math.min(active, matches.length - 1) : 0

  function close() {
    setOpen(false)
    setQuery('')
    setActive(0)
    setError(false) // clear a prior fetch failure so reopening the picker retries
  }
  function pick(id: string) {
    onChange(id)
    close()
  }

  return (
    <div className="relative inline-block">
      <button
        type="button"
        disabled={disabled}
        onClick={() => (open ? close() : setOpen(true))}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        aria-label={value ? `Selected run ${value}. Change run` : placeholder}
        className={`flex items-center gap-1.5 rounded-lg border border-line bg-card-2 px-2.5 py-1 font-mono text-[12px] text-text hover:border-line-strong ${
          disabled ? 'cursor-not-allowed opacity-50' : ''
        }`}
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${current ? RUN_STATUS_META[current.status].dot : 'bg-line-strong'}`}
        />
        {value ?? placeholder}
        <ChevronDown size={13} className="text-text-3" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={close} />
          <div
            className={`absolute top-full z-20 mt-1 w-[300px] overflow-hidden rounded-xl border border-line-strong bg-card shadow-pop ${
              align === 'right' ? 'right-0' : 'left-0'
            }`}
          >
            <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
              <Search size={14} className="text-text-3" />
              {/* eslint-disable-next-line jsx-a11y/no-autofocus -- opening the selector is an explicit user action; focusing search is expected */}
              <input
                autoFocus
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value)
                  setActive(0) // reset the highlight when the match set changes
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') close()
                  else if (e.key === 'ArrowDown') {
                    e.preventDefault()
                    setActive((a) => Math.min(a + 1, matches.length - 1))
                  } else if (e.key === 'ArrowUp') {
                    e.preventDefault()
                    setActive((a) => Math.max(a - 1, 0))
                  } else if (e.key === 'Enter' && matches.length) {
                    e.preventDefault()
                    pick(matches[activeIdx].run_id)
                  }
                }}
                placeholder="Search runs by id or platform…"
                role="combobox"
                aria-expanded={open}
                aria-controls={listboxId}
                aria-autocomplete="list"
                aria-activedescendant={matches.length ? optionId(activeIdx) : undefined}
                aria-label="Search runs by id or platform"
                className="min-w-0 flex-1 bg-transparent text-[12.5px] text-text outline-none placeholder:text-text-3"
              />
            </div>
            <div className="max-h-[280px] overflow-y-auto p-1.5" role="listbox" id={listboxId} aria-label="Runs">
              {loading && !runs.length ? (
                <div className="flex items-center gap-2 px-2.5 py-3 text-[12px] text-text-3">
                  <Loader2 size={13} className="animate-spin" /> Loading runs…
                </div>
              ) : error && !runs.length ? (
                <div className="px-3 py-5 text-center text-[12px] text-text-2">Couldn’t load runs.</div>
              ) : (
                <>
                  {matches.map((r, i) => {
                    const meta = RUN_STATUS_META[r.status]
                    return (
                      <button
                        key={r.run_id}
                        type="button"
                        role="option"
                        id={optionId(i)}
                        aria-selected={r.run_id === value}
                        onClick={() => pick(r.run_id)}
                        onMouseEnter={() => setActive(i)}
                        className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-card-2 ${
                          i === activeIdx || r.run_id === value ? 'bg-card-2' : ''
                        }`}
                      >
                        <span className={`h-[7px] w-[7px] shrink-0 rounded-full ${meta.dot}`} />
                        <span className="font-mono text-[12.5px] font-medium text-text">{r.run_id}</span>
                        {r.platform && <span className="text-[11px] text-text-3">· {r.platform}</span>}
                        <span className="ml-auto shrink-0 text-[11px] text-text-3">{meta.label}</span>
                      </button>
                    )
                  })}
                  {runs.length > 0 && matches.length === 0 && (
                    <div className="px-3 py-5 text-center text-[12px] text-text-2">
                      No runs match “{query}”.
                    </div>
                  )}
                </>
              )}
            </div>
            {onViewAll && (
              <button
                type="button"
                onClick={() => {
                  close()
                  onViewAll()
                }}
                className="flex w-full items-center justify-between border-t border-line bg-card px-3 py-2.5 hover:bg-card-2"
              >
                <span className="text-[12px] font-semibold text-accent-strong">View all runs</span>
                <span className="text-[11px] text-text-3">{runs.length} runs →</span>
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}
