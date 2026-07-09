import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { EvidenceTable } from '../components/EvidenceTable'
import { GateResultStrip } from '../components/GateResultStrip'
import { MetricsPanel } from '../components/MetricsPanel'
import { ErrorBox, Loading } from '../components/States'
import { TriagePanel } from '../components/TriagePanel'
import { VerdictBadge } from '../components/VerdictBadge'
import type { DecisionCard, RunDetail as RunDetailData } from '../types'

export function RunDetail() {
  const { runId = '' } = useParams()
  const [detail, setDetail] = useState<RunDetailData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .run(runId)
      .then(setDetail)
      .catch((e) => setError(String(e)))
  }, [runId])

  if (error) return <ErrorBox message={error} />
  if (!detail) return <Loading label="Loading run…" />

  return (
    <div className="max-w-4xl">
      <Link to="/" className="text-ink-dim text-sm hover:text-ink">
        ← All runs
      </Link>
      <h2 className="mt-2 text-2xl font-mono">{detail.run_id}</h2>
      <p className="text-ink-dim text-sm mb-6">
        {detail.summary.n_samples} samples · {detail.summary.n_attention} need attention ·{' '}
        <Link to={`/runs/${runId}/provenance`} className="underline hover:text-ink">
          {detail.events.length} provenance events →
        </Link>
      </p>
      <div className="grid gap-4">
        {detail.cards.map((card) => (
          <CardView key={card.sample_id} runId={runId} card={card} />
        ))}
      </div>
    </div>
  )
}

function CardView({ runId, card }: { runId: string; card: DecisionCard }) {
  const actionable = card.verdict !== 'proceed'
  return (
    <article className="bg-surface-2 border border-border rounded-xl p-5">
      <div className="flex items-center gap-3">
        <span className="font-mono text-lg">{card.sample_id}</span>
        <VerdictBadge verdict={card.verdict} />
        <span className="text-ink-dim text-xs ml-auto font-mono" title="card content hash">
          {card.content_hash.slice(0, 10)}
        </span>
      </div>
      <p className="mt-2 font-semibold">{card.headline}</p>
      <p className="text-ink-dim text-sm mt-1">{card.rationale}</p>

      {card.gate_results.length > 0 && (
        <div className="mt-4">
          <GateResultStrip results={card.gate_results} />
        </div>
      )}

      {card.next_steps.length > 0 && (
        <ul className="mt-4 list-disc pl-5 text-sm space-y-1">
          {card.next_steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ul>
      )}

      <div className="mt-4">
        <EvidenceTable findings={card.findings} />
      </div>

      {card.metric_values && card.metric_values.length > 0 && (
        <div className="mt-4">
          <MetricsPanel metrics={card.metric_values} />
        </div>
      )}

      {actionable && (
        <div className="mt-4">
          <TriagePanel runId={runId} sampleId={card.sample_id} />
        </div>
      )}
    </article>
  )
}
