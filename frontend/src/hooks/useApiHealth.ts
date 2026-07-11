import { useEffect, useState } from 'react'
import { api } from '../api'

// Real system state: poll the read-API's health so status indicators reflect actual reachability
// instead of a hardcoded value (honest status, not a mock). 'ready' = the API answered ok;
// 'offline' = it didn't (the frontend can't reach the backend, or it reported not-ok). Checked on
// mount + every 20s. Shared by the TopBar pill and the Runs hero "Gate online" indicator so both
// tell the same truth (a hardcoded green dot lies during an outage).
export type Health = 'checking' | 'ready' | 'offline'

export function useApiHealth(): Health {
  const [state, setState] = useState<Health>('checking')
  useEffect(() => {
    let live = true
    const check = () =>
      api
        .health()
        .then((h) => live && setState(h.status === 'ok' ? 'ready' : 'offline'))
        .catch(() => live && setState('offline'))
    check()
    const t = window.setInterval(check, 20_000)
    return () => {
      live = false
      window.clearInterval(t)
    }
  }, [])
  return state
}
