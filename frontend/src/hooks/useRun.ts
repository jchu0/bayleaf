import { useEffect, useState } from 'react'
import { api } from '../api'
import type { RunDetail } from '../types'

// UX-DUP #2/#6: ONE session cache for a run's detail payload — the heaviest read in the app. Before
// this, RunDetail, AgentTriage, and Provenance each fetched `api.run(runId)` independently, so a
// single cards → triage → provenance journey pulled the same multi-hundred-KB payload three times.
// Now the first consumer fetches, the rest read the cache; concurrent mounts share one in-flight
// request. A run is not immutable within a session (a share adds a DATA_EXPORTED event, a release
// changes status), so a consumer that MUTATES a run calls `refresh()` to re-fetch and fan the fresh
// payload out to every subscriber — the cache is a fetch de-duplicator, never a staleness trap.

type Entry = { detail: RunDetail | null; error: string | null }
const cache = new Map<string, Entry>()
const inflight = new Map<string, Promise<void>>()
const subscribers = new Map<string, Set<() => void>>()

function notify(runId: string): void {
  subscribers.get(runId)?.forEach((fn) => fn())
}

function load(runId: string, force = false): Promise<void> {
  if (!force && cache.has(runId)) return Promise.resolve()
  const existing = inflight.get(runId)
  if (existing && !force) return existing
  const p = api
    .run(runId)
    .then((detail) => {
      cache.set(runId, { detail, error: null })
    })
    .catch((e: unknown) => {
      cache.set(runId, { detail: null, error: e instanceof Error ? e.message : String(e) })
    })
    .finally(() => {
      inflight.delete(runId)
      notify(runId)
    })
  inflight.set(runId, p)
  return p
}

export type UseRun = { detail: RunDetail | null; error: string | null; refresh: () => void }

// Subscribe to a run's cached detail. `runId === ''` (the run-independent /agents route) is a no-op
// that returns nulls without touching the cache. `refresh()` forces a re-fetch and updates every
// mounted subscriber of this run — call it after an action that changes the run server-side.
export function useRun(runId: string): UseRun {
  const [, forceRender] = useState(0)
  useEffect(() => {
    if (!runId) return
    const rerender = () => forceRender((n) => n + 1)
    const set = subscribers.get(runId) ?? new Set<() => void>()
    set.add(rerender)
    subscribers.set(runId, set)
    void load(runId) // cache hit → resolves immediately; miss → fetches once and notifies
    return () => {
      set.delete(rerender)
      if (set.size === 0) subscribers.delete(runId)
    }
  }, [runId])
  const entry = runId ? cache.get(runId) : undefined
  return {
    detail: entry?.detail ?? null,
    error: entry?.error ?? null,
    refresh: () => {
      if (runId) void load(runId, true)
    },
  }
}
