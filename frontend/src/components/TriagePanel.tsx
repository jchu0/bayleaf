import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import type { TriageNote } from '../types'

// Advisory QC-triage note, fetched on demand from /triage (the Claude-agent seam).
export function TriagePanel({ runId, sampleId }: { runId: string; sampleId: string }) {
  const [note, setNote] = useState<TriageNote | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setNote(await api.triage(runId, sampleId))
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  if (note) {
    return (
      <div className="rounded-lg border border-accent/25 bg-accent-weak/60 p-3.5">
        <div className="mb-2 flex items-center gap-2">
          <Sparkles size={15} className="text-accent" />
          <span className="text-[13px] font-semibold text-text">Agent triage</span>
          <span className="rounded border border-line bg-card px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-text-3">
            advisory · {note.generated_by}
          </span>
        </div>
        <p className="text-[13px] text-text">
          <span className="text-text-2">Likely cause: </span>
          {note.likely_cause}
        </p>
        <p className="mt-1 text-[13px] text-text">
          <span className="text-text-2">Suggested action: </span>
          {note.suggested_action}
        </p>
        {note.citations.length > 0 && (
          <p className="mt-2 font-mono text-[11px] text-text-3">
            cites: {note.citations.map((c) => c.ref).join(', ')}
          </p>
        )}
      </div>
    )
  }

  return (
    <div>
      <button
        type="button"
        onClick={load}
        disabled={loading}
        className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-3 py-1.5 text-[13px] font-medium text-text hover:border-line-strong disabled:opacity-50"
      >
        <Sparkles size={14} className="text-accent" />
        {loading ? 'Asking the agent…' : 'Ask the triage agent'}
      </button>
      {error && <p className="mt-1 text-[11px] text-escalate-fg">{error}</p>}
    </div>
  )
}
