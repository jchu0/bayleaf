import { useCallback, useState } from 'react'

// Backs the "Refresh · Updated {time}" control on data screens (Intake, Monitoring). Wraps a
// refetch, tracks a spinner flag, and stamps the last-updated time for the label.
export function useRefresh(fn: () => Promise<void> | void) {
  const [spinning, setSpinning] = useState(false)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)

  const refresh = useCallback(async () => {
    setSpinning(true)
    try {
      await fn()
      setUpdatedAt(new Date())
    } finally {
      setSpinning(false)
    }
  }, [fn])

  const updatedLabel = updatedAt
    ? updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null

  return { spinning, updatedAt, updatedLabel, refresh }
}
