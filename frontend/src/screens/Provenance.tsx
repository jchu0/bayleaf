import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { PageHeader } from '../components/PageHeader'
import { ErrorBox, Loading } from '../components/States'
import { Tabs } from '../components/Tabs'
import type { ProvenanceEvent, RunArtifact, RunDetail } from '../types'
import { fmtTime, groupArtifacts, readGateProvenance, readNum, readStr } from '../provenance'
import { ProvenanceLineage } from '../components/provenance/Lineage'
import { EventTrail } from '../components/provenance/EventTrail'
import { ProvenanceArtifacts } from '../components/provenance/Artifacts'

// Provenance is now a thin CONTAINER (PV1): it fetches the run detail + artifacts once (unchanged
// fetch — no new api call, no wire change) and renders a persistent version-pin header band plus a
// three-way view switch (Lineage · Event trail · Artifacts). The centerpiece — a filterable,
// paginated timeline with finding→evidence trace-back — renders `detail.events`, the real
// append-only ledger trail that already shipped to the client but the screen used to discard.
// 100% read-only: the screen never sets a verdict/confidence — it displays what the rules
// authored (ADR-0001) and labels the LLM narration as narration.

type ProvView = 'lineage' | 'events' | 'artifacts'
const VIEWS: ProvView[] = ['lineage', 'events', 'artifacts']

export function Provenance() {
  const { runId = '' } = useParams()
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [artifacts, setArtifacts] = useState<RunArtifact[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()

  useEffect(() => {
    setDetail(null)
    setArtifacts(null)
    setError(null) // clear a prior run's error so switching runs via the top switcher never shows stale text
    api.run(runId).then(setDetail).catch((e) => setError(String(e)))
    // The artifacts fetch degrades to [] on failure (tolerant boundary) — the empty state renders,
    // never a crash.
    api.artifacts(runId).then(setArtifacts).catch(() => setArtifacts([]))
  }, [runId])

  // The URL owns the view so trace-back deep-links and refreshes are stable (?view=events).
  const rawView = params.get('view')
  const view: ProvView = rawView && VIEWS.includes(rawView as ProvView) ? (rawView as ProvView) : 'lineage'
  const setView = (v: ProvView) =>
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev)
        if (v === 'lineage') p.delete('view')
        else p.set('view', v)
        return p
      },
      { replace: true },
    )

  // Grouped artifact count for the tab badge (one row per file, not per stage·role edge).
  const artifactCount = useMemo(() => (artifacts ? groupArtifacts(artifacts).length : 0), [artifacts])

  if (error) return <ErrorBox message={error} />
  if (!detail || !artifacts) return <Loading label="Loading provenance…" />

  return (
    <div className="mx-auto max-w-[1080px]">
      {/* UIC-1: the run switcher already names which run this is — drop the eyebrow + descriptive
          subtitle (pure page chrome), keep only the title. */}
      <PageHeader title="Provenance" />

      <ProvenanceHeader events={detail.events} />

      <div className="mt-5">
        <Tabs<ProvView>
          items={[
            { value: 'lineage', label: 'Lineage' },
            { value: 'events', label: 'Event trail', count: detail.events.length },
            { value: 'artifacts', label: 'Artifacts', count: artifactCount },
          ]}
          value={view}
          onChange={setView}
        />
      </div>

      <div className="mt-5">
        {view === 'lineage' && <ProvenanceLineage detail={detail} artifacts={artifacts} />}
        {view === 'events' && <EventTrail events={detail.events} cards={detail.cards} runId={detail.run_id} />}
        {view === 'artifacts' && <ProvenanceArtifacts artifacts={artifacts} />}
      </div>
    </div>
  )
}

// The version-pin band — the real provenance of THIS gate execution, read straight from the
// started/completed events (never faked). The one honest seam is the pipeline provenance pin:
// AnalysisRun.gate_provenance reserves the sarek params_hash / execution_trace for phase 2
// (provenance.py:50-56), so it's labelled as a seam, not populated with a fabricated value.
function ProvenanceHeader({ events }: { events: ProvenanceEvent[] }) {
  const started = events.find((e) => e.event_type === 'analysis_run.started')
  const completed = events.find((e) => e.event_type === 'analysis_run.completed')

  // Defensive empty — mirrors the lineage screen's honesty posture.
  if (!started) {
    return (
      <div className="rounded-[14px] border border-line bg-card px-5 py-4 text-[12.5px] text-text-3">
        No run header captured for this run.
      </div>
    )
  }

  const gp = readGateProvenance(started.payload)
  const narration = readStr(started.payload, 'generated_by') ?? 'unknown'
  const nSamples = completed ? readNum(completed.payload, 'n_samples') : null
  const status = completed ? readStr(completed.payload, 'status') : null

  return (
    <div className="rounded-[14px] border border-line bg-card px-5 py-4">
      <div className="mb-3 text-[10px] font-semibold uppercase tracking-[0.6px] text-text-3">
        Version pins · this gate execution
      </div>
      <div className="flex flex-wrap gap-x-8 gap-y-3">
        <Pin label="Analysis run">
          {/* The run id IS the header's identity handle (an execution key, not a content hash), so
              it's shown in full + selectable — not deferred behind a show-full like a digest. */}
          <span className="select-all break-all font-mono text-[11.5px] text-text-2">
            {started.analysis_run_id ?? '—'}
          </span>
        </Pin>
        <Pin label="Rule pack">
          <span className="font-mono text-text-2">{gp.rule_pack_version ?? '—'}</span>
        </Pin>
        <Pin label="Runbook metrics" title={gp.runbook_metrics.join(', ') || undefined}>
          <span className="font-mono text-text-2">{gp.runbook_metrics.length}</span>
        </Pin>
        <Pin label="Narration provenance" title="How the card prose was generated — the rules decide the verdict regardless (ADR-0001).">
          <span className="font-mono text-text-2">{narration}</span>
        </Pin>
        <Pin label="Samples">
          <span className="font-mono text-text-2">
            {nSamples ?? '—'}
            {status ? ` · ${status}` : ''}
          </span>
        </Pin>
        <Pin label="Events">
          <span className="font-mono text-text-2">{events.length}</span>
        </Pin>
        <Pin label="Started">
          <span className="text-text-2">{fmtTime(started.created_at)}</span>
        </Pin>
        <Pin label="Completed">
          <span className="text-text-2">{completed ? fmtTime(completed.created_at) : '—'}</span>
        </Pin>
        <Pin
          label="Pipeline provenance"
          title="Reserved for phase 2 — the sarek params hash / execution trace is not captured in this build (provenance.py:50-56)."
        >
          <span className="text-text-3">params hash · execution trace — phase 2</span>
        </Pin>
      </div>
    </div>
  )
}

function Pin({ label, title, children }: { label: string; title?: string; children: ReactNode }) {
  return (
    <div className="min-w-0" title={title}>
      <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-[0.5px] text-text-3">{label}</div>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12px]">{children}</div>
    </div>
  )
}
