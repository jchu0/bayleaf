import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import type { ProvenanceEvent, RunDetail as RunDetailData } from '../types'

const EVENT_META: Record<string, { icon: string; label: string }> = {
  'analysis_run.started': { icon: '▶', label: 'Analysis run started' },
  'sample.registered': { icon: '•', label: 'Sample registered' },
  'finding.emitted': { icon: '⚑', label: 'Finding emitted' },
  'verdict.decided': { icon: '⚖', label: 'Verdict decided' },
  'analysis_run.completed': { icon: '■', label: 'Analysis run completed' },
}

function s(v: unknown): string {
  return v === null || v === undefined ? '' : String(v)
}

export function Provenance() {
  const { runId = '' } = useParams()
  const [detail, setDetail] = useState<RunDetailData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .run(runId)
      .then(setDetail)
      .catch((e) => setError(String(e)))
  }, [runId])

  if (error) return <p className="text-escalate">{error}</p>
  if (!detail) return <p className="text-ink-dim">Loading…</p>

  return (
    <div className="max-w-3xl">
      <Link to={`/runs/${runId}`} className="text-ink-dim text-sm hover:text-ink">
        ← Decision cards
      </Link>
      <h2 className="mt-2 text-2xl font-mono">{detail.run_id}</h2>
      <p className="text-ink-dim text-sm mb-6">
        Provenance ledger — {detail.events.length} append-only events. The event log is
        authoritative; the DB is a rebuildable projection (ADR-0002).
      </p>
      <ol className="relative ml-3 border-l border-border">
        {detail.events.map((ev) => (
          <EventRow key={ev.id} ev={ev} />
        ))}
      </ol>
    </div>
  )
}

function EventRow({ ev }: { ev: ProvenanceEvent }) {
  const meta = EVENT_META[ev.event_type] ?? { icon: '·', label: ev.event_type }
  const output = ev.outputs[0]
  return (
    <li className="mb-4 ml-6">
      <span className="absolute -left-3 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-surface-2 text-xs">
        {meta.icon}
      </span>
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-medium">{meta.label}</span>
        {ev.sample_id && <span className="font-mono text-xs text-ink-dim">{ev.sample_id}</span>}
        <span className="ml-auto text-[10px] uppercase tracking-wide text-ink-dim">{ev.actor}</span>
      </div>
      <PayloadLine ev={ev} />
      {output?.content_hash && (
        <p className="mt-0.5 font-mono text-xs text-ink-dim">
          → {output.entity_type} · {output.content_hash.slice(0, 12)}
        </p>
      )}
    </li>
  )
}

function PayloadLine({ ev }: { ev: ProvenanceEvent }) {
  const p = ev.payload
  let text = ''
  if (ev.event_type === 'finding.emitted') {
    text = `${s(p.rule_id)} · gate:${s(p.gate)} · ${s(p.severity)}`
  } else if (ev.event_type === 'verdict.decided') {
    text = `${s(p.verdict)} · by ${s(p.generated_by)}`
  } else if (ev.event_type === 'analysis_run.completed') {
    text = `${s(p.status)} · ${s(p.n_samples)} samples`
  } else if (ev.event_type === 'analysis_run.started') {
    const gp = p.gate_provenance as Record<string, unknown> | undefined
    text = gp ? `rule pack ${s(gp.rule_pack_version)}` : ''
  }
  if (!text) return null
  return <p className="mt-0.5 font-mono text-xs text-ink-dim">{text}</p>
}
