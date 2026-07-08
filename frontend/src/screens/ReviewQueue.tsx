import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/States'
import { VerdictBadge } from '../components/VerdictBadge'
import type { DecisionCard } from '../types'

// Most-urgent first, matching the gate's ordering.
const VERDICT_ORDER: Record<string, number> = { escalate: 0, rerun: 1, hold: 2, proceed: 3 }

type QueueItem = { runId: string; card: DecisionCard }

export function ReviewQueue() {
  const [items, setItems] = useState<QueueItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .runs()
      .then((runs) => Promise.all(runs.map((r) => api.run(r.run_id))))
      .then((details) => {
        const queue: QueueItem[] = []
        for (const detail of details) {
          for (const card of detail.cards) {
            if (card.verdict !== 'proceed') queue.push({ runId: detail.run_id, card })
          }
        }
        queue.sort((a, b) => VERDICT_ORDER[a.card.verdict] - VERDICT_ORDER[b.card.verdict])
        setItems(queue)
      })
      .catch((e) => setError(String(e)))
  }, [])

  if (error) return <ErrorBox message={error} />
  if (!items) return <Loading label="Loading queue…" />

  return (
    <div className="max-w-4xl">
      <h2 className="text-2xl font-semibold">Review queue</h2>
      <p className="text-ink-dim text-sm mb-6">
        Samples needing a human, across all runs — most urgent first. Read-only for now
        (acknowledge / suppress / resolve arrive with the ticketing backend).
      </p>

      {items.length === 0 ? (
        <p className="text-proceed">Nothing to review — every sample cleared.</p>
      ) : (
        <div className="grid gap-2">
          {items.map(({ runId, card }) => (
            <Link
              key={`${runId}-${card.sample_id}`}
              to={`/runs/${runId}`}
              className="flex items-center gap-3 rounded-lg border border-border bg-surface-2 p-4 transition-colors hover:border-ink-dim"
            >
              <span className="font-mono">{card.sample_id}</span>
              <VerdictBadge verdict={card.verdict} />
              <span className="truncate text-sm text-ink-dim">{card.headline}</span>
              <span className="ml-auto shrink-0 font-mono text-xs text-ink-dim">{runId}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
