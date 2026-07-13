import { useEffect, useState } from 'react'
import { api } from '../api'

// Real system state: poll the read-API's health so status indicators reflect actual reachability
// instead of a hardcoded value (honest status, not a mock). 'ready' = the API answered ok;
// 'offline' = it didn't (the frontend can't reach the backend, or it reported not-ok). Checked on
// mount + every 20s. Shared by the TopBar pill and the Runs hero "Gate online" indicator so both
// tell the same truth (a hardcoded green dot lies during an outage).
export type Health = 'checking' | 'ready' | 'offline'

// UX-DUP #9: ONE module-level poller shared by every consumer. Before this each `useApiHealth()`
// call spun its OWN 20s `setInterval` + fetch, so the TopBar pill and the Runs hero polled
// `/api/health` twice every 20s and could transiently disagree (one flips to offline up to 20s
// before the other). Now the first subscriber starts the single poll, the last to unmount stops it,
// and everyone reads one shared state — same cadence, one fetch, no disagreement.
let current: Health = 'checking'
const subscribers = new Set<(h: Health) => void>()
let timer: number | null = null

function publish(next: Health): void {
  current = next
  for (const notify of subscribers) notify(next)
}

function check(): void {
  api
    .health()
    .then((h) => publish(h.status === 'ok' ? 'ready' : 'offline'))
    .catch(() => publish('offline'))
}

function ensurePolling(): void {
  if (timer != null) return
  check() // fire immediately for the first subscriber (mirrors the old on-mount check)
  timer = window.setInterval(check, 20_000)
}

function maybeStopPolling(): void {
  if (subscribers.size === 0 && timer != null) {
    window.clearInterval(timer)
    timer = null
  }
}

export function useApiHealth(): Health {
  const [state, setState] = useState<Health>(current)
  useEffect(() => {
    subscribers.add(setState)
    setState(current) // sync to the shared latest the moment we subscribe
    ensurePolling()
    return () => {
      subscribers.delete(setState)
      maybeStopPolling()
    }
  }, [])
  return state
}
