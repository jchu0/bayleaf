import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/States'
import type { Runbook } from '../types'

export function Settings() {
  const [runbook, setRunbook] = useState<Runbook | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .config()
      .then(setRunbook)
      .catch((e) => setError(String(e)))
  }, [])

  if (error) return <ErrorBox message={error} />
  if (!runbook) return <Loading label="Loading config…" />

  return (
    <div className="max-w-3xl">
      <Link to="/" className="text-ink-dim text-sm hover:text-ink">
        ← All runs
      </Link>
      <h2 className="mt-2 text-2xl font-semibold">Runbook</h2>
      <p className="text-ink-dim text-sm mb-3">
        The active QC policy (read-only for now), keyed per assay × sample type.
      </p>
      {/* Life-science guardrail: these are operator-tunable QC gates, never clinical
          thresholds — keep the label visible so no one reads them as a medical cutoff. */}
      <p className="mb-6">
        <span className="inline-flex items-center rounded border border-hold/40 bg-hold/10 px-2 py-1 text-xs font-medium uppercase tracking-wide text-hold">
          Illustrative · configurable · not clinical
        </span>
      </p>

      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-dim">
        QC thresholds
      </h3>
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-2 text-left text-xs uppercase tracking-wide text-ink-dim">
              <th className="p-3 font-medium">Metric</th>
              <th className="p-3 font-medium">Unit</th>
              <th className="p-3 font-medium">Gate</th>
              <th className="p-3 font-medium">Borderline band</th>
              <th className="p-3 font-medium">Hard-fail</th>
              <th className="p-3 font-medium">Direction</th>
            </tr>
          </thead>
          <tbody>
            {runbook.qc_thresholds.map((t) => (
              <tr key={t.metric} className="border-t border-border">
                <td className="p-3">
                  {t.label} <span className="font-mono text-xs text-ink-dim">{t.metric}</span>
                </td>
                <td className="p-3 font-mono text-xs text-ink-dim">{t.unit || '—'}</td>
                <td className="p-3 font-mono">
                  {t.gate}
                  {t.unit}
                </td>
                <td className="p-3 font-mono text-ink-dim">
                  ±{t.borderline_band}
                  {t.unit}
                </td>
                <td className="p-3 font-mono text-ink-dim">
                  {t.hard_fail}
                  {t.unit}
                </td>
                <td className="p-3 text-ink-dim">
                  {t.higher_is_better ? '≥ (higher is better)' : '≤ (lower is better)'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wide text-ink-dim">
        Required intake metadata
      </h3>
      <div className="flex flex-wrap gap-2">
        {runbook.require_metadata_fields.map((f) => (
          <span
            key={f}
            className="rounded border border-border bg-surface-2 px-2 py-1 font-mono text-xs"
          >
            {f}
          </span>
        ))}
      </div>

      <h3 className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wide text-ink-dim">
        Pipeline failure markers
      </h3>
      <div className="flex flex-wrap gap-2">
        {runbook.log_failure_markers.map((m) => (
          <span
            key={m}
            className="rounded border border-border bg-surface-2 px-2 py-1 font-mono text-xs"
          >
            {m}
          </span>
        ))}
      </div>
    </div>
  )
}
