import type {
  FeedbackAck,
  FeedbackIn,
  MetricCatalog,
  RunArtifact,
  RunDetail,
  Runbook,
  RunSummary,
  TriageNote,
} from './types'

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

// Thin typed client over the FastAPI read-API (proxied to :8010 in dev).
export const api = {
  runs: () => get<RunSummary[]>('/api/runs'),
  run: (runId: string) => get<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`),
  artifacts: (runId: string) => get<RunArtifact[]>(`/api/runs/${encodeURIComponent(runId)}/artifacts`),
  triage: (runId: string, sampleId: string) =>
    get<TriageNote>(
      `/api/runs/${encodeURIComponent(runId)}/cards/${encodeURIComponent(sampleId)}/triage`,
    ),
  config: () => get<Runbook>('/api/config'),
  metricsRegistry: () => get<MetricCatalog>('/api/metrics/registry'),
  // The one write: off-gate product telemetry (W12).
  feedback: (body: FeedbackIn) => post<FeedbackAck>('/api/feedback', body),
}
