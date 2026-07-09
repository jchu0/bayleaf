import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/States'
import type { MetricCatalog, Runbook } from '../types'

// Runbook gates are stored in CANONICAL units (fraction for %-metrics, x for coverage);
// `unit` is only the display symbol. Convert back to the human unit the operator reads —
// this mirrors the core's registry.denormalize for the two display units the runbook uses,
// so an 85% gate never renders as "0.85%". Trim float noise to 2dp.
function displayThreshold(value: number, unit: string): string {
  const shown = unit === '%' ? value * 100 : value
  return `${Math.round(shown * 100) / 100}${unit}`
}

export function Settings() {
  const [runbook, setRunbook] = useState<Runbook | null>(null)
  const [catalog, setCatalog] = useState<MetricCatalog | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .config()
      .then(setRunbook)
      .catch((e) => setError(String(e)))
    // The metric catalog is a read-only, non-blocking companion to the runbook: fetched
    // separately so a catalog hiccup never blanks the (load-bearing) runbook policy view.
    api.metricsRegistry().then(setCatalog).catch(() => setCatalog(null))
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
                <td className="p-3 font-mono">{displayThreshold(t.gate, t.unit)}</td>
                <td className="p-3 font-mono text-ink-dim">
                  {/* borderline_band is RELATIVE to the gate (gate × band); show the
                      absolute band in display units, not the bare 0.03 fraction. */}
                  ±{displayThreshold(t.gate * t.borderline_band, t.unit)}
                </td>
                <td className="p-3 font-mono text-ink-dim">
                  {displayThreshold(t.hard_fail, t.unit)}
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

      {/* Metric catalog (W16/T-038): a READ-ONLY view of the registered metric vocabulary.
          `Gated` = the live runbook gates on this metric today; `Registered` = described in
          the versioned vocabulary but not yet a gate — the extensibility story. This panel
          never authors or edits a metric type or a threshold (ADR-0001: rules decide). */}
      {catalog && (
        <>
          <h3 className="mb-1 mt-8 text-xs font-semibold uppercase tracking-wide text-ink-dim">
            Metric catalog
          </h3>
          <p className="text-ink-dim text-sm mb-2">
            The registered metric vocabulary (registry v{catalog.metric_registry_version}) —{' '}
            {catalog.n_gated} of {catalog.n_registered} are gated by the runbook today; the rest are
            registered vocabulary the gate can adopt without new code.
          </p>
          {/* Life-science guardrail: versioned, configurable vocabulary — never a clinical panel. */}
          <p className="mb-3">
            <span className="inline-flex items-center rounded border border-hold/40 bg-hold/10 px-2 py-1 text-xs font-medium uppercase tracking-wide text-hold">
              Vocabulary · versioned · configurable · not clinical
            </span>
          </p>
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-2 text-left text-xs uppercase tracking-wide text-ink-dim">
                  <th className="p-3 font-medium">Metric</th>
                  <th className="p-3 font-medium">Gate</th>
                  <th className="p-3 font-medium">Category</th>
                  <th className="p-3 font-medium">Unit</th>
                  <th className="p-3 font-medium">Source</th>
                  <th className="p-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {catalog.entries.map((e) => (
                  <tr key={e.our_key} className="border-t border-border">
                    <td className="p-3">
                      {e.display_name}{' '}
                      <span className="font-mono text-xs text-ink-dim">{e.our_key}</span>
                    </td>
                    <td className="p-3 font-mono text-xs text-ink-dim">{e.gate}</td>
                    <td className="p-3 text-ink-dim">{e.category}</td>
                    <td className="p-3 font-mono text-xs text-ink-dim">{e.canonical_unit}</td>
                    <td className="p-3 font-mono text-xs text-ink-dim">{e.source_module}</td>
                    <td className="p-3">
                      {e.gated ? (
                        <span className="inline-flex items-center rounded border border-proceed/40 bg-proceed/10 px-2 py-0.5 text-xs font-medium text-proceed">
                          Gated
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded border border-border bg-surface-2 px-2 py-0.5 text-xs font-medium text-ink-dim">
                          Registered
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
