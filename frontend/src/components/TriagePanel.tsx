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
      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="mb-2 flex items-center gap-2">
          <span className="text-sm font-semibold">🤖 Triage</span>
          <span className="rounded border border-border bg-surface-2 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-ink-dim">
            advisory · {note.generated_by}
          </span>
        </div>
        <p className="text-sm">
          <span className="text-ink-dim">Likely cause: </span>
          {note.likely_cause}
        </p>
        <p className="mt-1 text-sm">
          <span className="text-ink-dim">Suggested action: </span>
          {note.suggested_action}
        </p>
        {note.citations.length > 0 && (
          <p className="mt-2 font-mono text-xs text-ink-dim">
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
        className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm hover:bg-surface-2 disabled:opacity-50"
      >
        {loading ? 'Asking the agent…' : '🤖 Ask the triage agent'}
      </button>
      {error && <p className="mt-1 text-xs text-escalate">{error}</p>}
    </div>
  )
}
