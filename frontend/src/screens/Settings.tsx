import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/States'
import { PageHeader } from '../components/PageHeader'
import { SettingsNotifications } from '../components/SettingsNotifications'
import { SettingsModelTier } from '../components/SettingsModelTier'
import { SettingsAssayTable } from '../components/SettingsAssayTable'
import type { MetricCatalog, RunbookPolicy } from '../types'

// Shared card chrome for the settings sections (dc.html: 1px border, 13px radius, surface bg,
// 17px/18px padding, no shadow).
const CARD = 'rounded-[13px] border border-line bg-card px-[18px] py-[17px]'

export function Settings() {
  // Consume the disclaimer-bearing /api/runbook (F12), not the raw /api/config core runbook.
  const [runbook, setRunbook] = useState<RunbookPolicy | null>(null)
  const [catalog, setCatalog] = useState<MetricCatalog | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.runbook().then(setRunbook).catch((e) => setError(String(e)))
    api
      .metricsRegistry()
      .then(setCatalog)
      .catch(() => setCatalog(null))
  }, [])

  if (error) return <ErrorBox message={error} />
  if (!runbook) return <Loading label="Loading runbook…" />

  return (
    <div className="mx-auto max-w-[1080px]">
      {/* UIC-1: no page eyebrow/subtitle — the left-nav already names the page. Explicit
          safety/limitation notes (the Metric-catalog disclaimer below) are kept verbatim. */}
      <PageHeader title="Settings" />

      <div className="space-y-[14px]">
        {/* The view-only "Operator profile" (lean/granular) bar was removed (ADR-0024 §6): it was a
            non-persisted local toggle that only gated the Metric-catalog section below, duplicating
            the persisted display prefs. Card layout lives in the user prefs (Density); agent scope
            now comes from graph wiring (ADR-0024), not a Settings control. The lean/granular config
            PROFILE stays an ADR-0005 backend concept, not this ad-hoc UI toggle. */}
        <SettingsNotifications />

        <SettingsModelTier />

        <SettingsAssayTable
          requiredMetadata={runbook.required_metadata_fields}
          disclaimer={runbook.disclaimer}
        />

        {/* Metric catalog (F9): the registered vocabulary + which entries the live runbook gates on.
            Versioned config metadata, never a clinical panel. Always shown now that the lean/granular
            Settings toggle is gone (ADR-0024 §6) — it degrades to nothing if the registry is absent. */}
        {catalog && (
          <section className={CARD}>
            <div className="text-[14.5px] font-semibold text-text">Metric catalog</div>
            <p className="mt-[3px] text-[12.5px] text-text-2">
              Registered metric vocabulary (registry v{catalog.metric_registry_version}) —{' '}
              {catalog.n_gated} of {catalog.n_registered} gated by the runbook today; the rest are
              vocabulary the gate can adopt without new code.
            </p>
            <div className="mt-[13px] overflow-hidden rounded-[10px] border border-line">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="bg-card-2 text-left text-[9.5px] uppercase tracking-[0.4px] text-text-3">
                    <th className="px-3 py-2 font-semibold">Metric</th>
                    <th className="px-3 py-2 font-semibold">Gate</th>
                    <th className="px-3 py-2 font-semibold">Category</th>
                    <th className="px-3 py-2 font-semibold">Unit</th>
                    <th className="px-3 py-2 text-right font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {catalog.entries.map((e) => (
                    <tr key={e.our_key} className="border-t border-line">
                      <td className="px-3 py-2">
                        {e.display_name}{' '}
                        <span className="font-mono text-[11px] text-text-3">{e.our_key}</span>
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px] text-text-2">{e.gate}</td>
                      <td className="px-3 py-2 text-[12px] text-text-2">{e.category}</td>
                      <td className="px-3 py-2 font-mono text-[11px] text-text-2">{e.canonical_unit}</td>
                      <td className="px-3 py-2 text-right">
                        {e.gated ? (
                          <span className="inline-flex rounded border border-proceed-bd bg-proceed-bg px-1.5 py-0.5 text-[10px] font-medium text-proceed-fg">
                            Gated
                          </span>
                        ) : (
                          <span className="inline-flex rounded border border-line bg-card-2 px-1.5 py-0.5 text-[10px] font-medium text-text-3">
                            Registered
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {catalog.disclaimer && (
              <p className="mt-3 text-[11px] leading-[1.5] text-text-3">{catalog.disclaimer}</p>
            )}
          </section>
        )}
      </div>
    </div>
  )
}
