import { useEffect, useState } from 'react'
import { api } from '../api'
import type { RunStatus, RunSummary } from '../types'

// UX-DUP (Runs #6): ONE module-level store for the /api/runs collection. Before this, the runs list
// was fetched into 3+ independent client states — Layout (feeding the Sidebar flagged badge + the
// TopBar switcher), RunOverview (its own runsPage), and RunSelector's self-fetch fallback — so the
// same collection crossed the wire up to 3× per session and the copies could disagree (a stale
// Sidebar attention badge beside a fresh RunOverview facet count). Now the first subscriber fetches
// ONCE via api.runsPage() (which carries the header-borne statusCounts + total a header-blind
// api.runs() would drop), the rest read the shared state, concurrent mounts share the one in-flight
// request, and a mutation calls refresh() to re-fetch and fan the fresh list to every subscriber.
//
// Modeled on useRun.ts (session cache + subscribers + in-flight dedup + refresh) and useApiHealth.ts
// (module singleton). Deliberately Provider-free so the dependency-free RunSelector can subscribe
// anywhere without a RunsProvider ancestor — the store IS the fallback the injected-list path degrades to.

export type RunsState = {
  // `null` until the first load settles — RunOverview reads this to show its loading skeleton; a
  // loaded-but-empty index is `[]`. Consumers that only need the list default it to [] themselves.
  runs: RunSummary[] | null
  // Full-set, filter-independent facet counts (X-Bayleaf-Status-Counts) — authoritative for the
  // RunOverview status tabs so a chip's count never shifts as the client-side filters narrow the list.
  statusCounts: Record<RunStatus, number> | null
  total: number
  error: string | null
  // Force a re-fetch and notify every subscriber — call after an action that changes a run
  // server-side (a share, a release), or from an error-state retry.
  refresh: () => void
}

let runs: RunSummary[] | null = null
let statusCounts: Record<RunStatus, number> | null = null
let total = 0
let error: string | null = null
let inflight: Promise<void> | null = null
const subscribers = new Set<() => void>()

function notify(): void {
  for (const fn of subscribers) fn()
}

// Fetch once, share the in-flight promise, cache the settled result. A settled load (runs loaded OR
// a prior error) is reused unless `force`d — so a failed first load settles into a STABLE error
// state (mirrors RunSelector's old no-infinite-refetch guard) that only an explicit refresh retries.
function load(force = false): Promise<void> {
  if (inflight) return inflight
  if (!force && (runs !== null || error !== null)) return Promise.resolve()
  // Starting a fetch clears any prior error, so an error-state retry re-renders into the loading
  // state (RunOverview's skeleton) instead of holding the error box until the refetch resolves.
  error = null
  const p = api
    .runsPage()
    .then((res) => {
      runs = res.data
      statusCounts = res.statusCounts
      total = res.total
      error = null
    })
    .catch((e: unknown) => {
      error = e instanceof Error ? e.message : String(e)
    })
    .finally(() => {
      inflight = null
      notify()
    })
  inflight = p
  // Notify synchronously too: a retry immediately reflects the cleared error (skeleton on), not
  // just once the request resolves.
  notify()
  return p
}

// Subscribe to the shared runs store. The first subscriber triggers the single fetch; later ones
// hit the settled/in-flight state. `refresh()` forces a re-fetch fanned out to every subscriber.
export function useRuns(): RunsState {
  const [, forceRender] = useState(0)
  useEffect(() => {
    const rerender = () => forceRender((n) => n + 1)
    subscribers.add(rerender)
    void load() // cache hit → resolves immediately; miss → fetches once and notifies
    return () => {
      subscribers.delete(rerender)
    }
  }, [])
  return {
    runs,
    statusCounts,
    total,
    error,
    refresh: () => void load(true),
  }
}
