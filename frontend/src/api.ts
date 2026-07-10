// Thin typed client over the FastAPI read-API (proxied to :8010 in dev). Reads are header-blind
// `get<T>`; the runs list additionally exposes a header-aware variant (`runsPage`) because
// pagination totals + status-facet counts ride response headers. Writes inject the RBAC actor
// (X-PipeGuard-Actor/-Role) set by the RoleContext — approver unlocks approvals only, never a
// verdict (rules decide / AI advises). Only endpoints that actually exist are called here.

import type {
  Actor,
  AgentProposal,
  CardReadout,
  DecisionCard,
  DiffResult,
  DryRunResult,
  FeedbackAck,
  FeedbackIn,
  MetricCatalog,
  MonitoringMetrics,
  MonitoringWindow,
  PipelineGraph,
  PipelineGraphAck,
  PipelineGraphIn,
  ReviewActionName,
  RunArtifact,
  RunDetail,
  Runbook,
  RunbookPolicy,
  RunStatus,
  RunSummary,
  RunsPage,
  ThresholdOverride,
  ThresholdOverrideAck,
  ThresholdOverrideIn,
  Ticket,
  TicketIn,
  TicketStatus,
  TransitionResult,
  TriageNote,
  Verdict,
} from './types'

// ── RBAC actor holder ────────────────────────────────────────────────────────
// Set by RoleContext at the app root; read on every write. Kept as a module-level holder so
// api.ts stays React-free. No actor → the backend applies its permissive dev-default.
let _actor: Actor | null = null
export function setApiActor(actor: Actor | null): void {
  _actor = actor
}
function authHeaders(): Record<string, string> {
  if (!_actor) return {}
  return { 'X-PipeGuard-Actor': _actor.id, 'X-PipeGuard-Role': _actor.role }
}

// ── low-level fetch ──────────────────────────────────────────────────────────
async function get<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

async function write<T>(url: string, method: 'POST' | 'PATCH' | 'DELETE', body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

// ── runs list query ──────────────────────────────────────────────────────────
export type RunsSort =
  | 'run_id' | '-run_id' | 'run_date' | '-run_date'
  | 'n_samples' | '-n_samples' | 'n_attention' | '-n_attention'
  | 'recent' | 'urgent' | 'date'
export type RunsQuery = {
  verdict?: Verdict
  status?: RunStatus
  q?: string
  sort?: RunsSort
  page?: number
  limit?: number
}
function runsQs(opts: RunsQuery = {}): string {
  const p = new URLSearchParams()
  if (opts.verdict) p.set('verdict', opts.verdict)
  if (opts.status) p.set('status', opts.status)
  if (opts.q) p.set('q', opts.q)
  if (opts.sort) p.set('sort', opts.sort)
  if (opts.page != null) p.set('page', String(opts.page))
  if (opts.limit != null) p.set('limit', String(opts.limit))
  const s = p.toString()
  return s ? `?${s}` : ''
}

// Header-aware runs fetch: the body is RunSummary[], but total/status-counts/page/limit ride
// response headers a plain get<T> would drop.
async function fetchRunsPage(opts: RunsQuery = {}): Promise<RunsPage> {
  const res = await fetch(`/api/runs${runsQs(opts)}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  const data = (await res.json()) as RunSummary[]
  const totalHeader = res.headers.get('X-PipeGuard-Total-Count')
  const countsHeader = res.headers.get('X-PipeGuard-Status-Counts')
  const pageHeader = res.headers.get('X-PipeGuard-Page')
  const limitHeader = res.headers.get('X-PipeGuard-Limit')
  let statusCounts: Record<RunStatus, number> | null = null
  if (countsHeader) {
    try {
      statusCounts = JSON.parse(countsHeader) as Record<RunStatus, number>
    } catch {
      statusCounts = null
    }
  }
  return {
    data,
    total: totalHeader ? Number(totalHeader) : data.length,
    statusCounts,
    page: pageHeader ? Number(pageHeader) : null,
    limit: limitHeader ? Number(limitHeader) : null,
  }
}

const enc = encodeURIComponent

export const api = {
  // ── runs + cards (reads) ──
  runs: (opts?: RunsQuery) => get<RunSummary[]>(`/api/runs${runsQs(opts)}`),
  runsPage: (opts?: RunsQuery) => fetchRunsPage(opts),
  run: (runId: string) => get<RunDetail>(`/api/runs/${enc(runId)}`),
  card: (runId: string, sampleId: string) =>
    get<DecisionCard>(`/api/runs/${enc(runId)}/cards/${enc(sampleId)}`),
  qcReadout: (runId: string, sampleId: string) =>
    get<CardReadout>(`/api/runs/${enc(runId)}/cards/${enc(sampleId)}/qc-readout`),
  artifacts: (runId: string) => get<RunArtifact[]>(`/api/runs/${enc(runId)}/artifacts`),
  triage: (runId: string, sampleId: string) =>
    get<TriageNote>(`/api/runs/${enc(runId)}/cards/${enc(sampleId)}/triage`),

  // ── policy / catalog (reads) ──
  config: () => get<Runbook>('/api/config'),
  runbook: () => get<RunbookPolicy>('/api/runbook'),
  metricsRegistry: () => get<MetricCatalog>('/api/metrics/registry'),

  // ── monitoring (read) ──
  monitoring: (window: MonitoringWindow = 'all', signaturesLimit?: number) => {
    const p = new URLSearchParams({ window })
    if (signaturesLimit != null) p.set('signatures_limit', String(signaturesLimit))
    return get<MonitoringMetrics>(`/api/monitoring?${p.toString()}`)
  },

  // ── advisory agent reads (off-gate) ──
  signatureRepair: (signature: string) =>
    get<AgentProposal>(`/api/monitoring/signatures/${enc(signature)}/repair`),
  archiveDigest: (runId: string) =>
    get<Record<string, unknown>>(`/api/runs/${enc(runId)}/archive-digest`),
  archiveIndex: () => get<Record<string, unknown>>('/api/archive/index'),

  // ── export (download link; no fetch needed for the CSV) ──
  exportUrl: (params: Record<string, string> = {}) =>
    `/api/export${Object.keys(params).length ? `?${new URLSearchParams(params).toString()}` : ''}`,

  // ── review-queue tickets ──
  createTicket: (body: TicketIn) => write<Ticket>('/api/review/tickets', 'POST', body),
  listTickets: (opts: { status?: TicketStatus; run_id?: string; rule_id?: string } = {}) => {
    const p = new URLSearchParams()
    if (opts.status) p.set('status', opts.status)
    if (opts.run_id) p.set('run_id', opts.run_id)
    if (opts.rule_id) p.set('rule_id', opts.rule_id)
    const qs = p.toString()
    return get<Ticket[]>(`/api/review/tickets${qs ? `?${qs}` : ''}`)
  },
  ticketAction: (id: string, action: ReviewActionName) =>
    write<Ticket>(`/api/review/tickets/${enc(id)}/action`, 'POST', { action }),

  // ── pipeline graph store + lifecycle ──
  savePipeline: (body: PipelineGraphIn) => write<PipelineGraphAck>('/api/pipelines', 'POST', body),
  listPipelines: () => get<PipelineGraph[]>('/api/pipelines'),
  pipelineVersions: (name: string) => get<PipelineGraph[]>(`/api/pipelines/${enc(name)}`),
  submitPipeline: (name: string) =>
    write<TransitionResult>(`/api/pipelines/${enc(name)}/submit`, 'POST', {}),
  approvePipeline: (name: string) =>
    write<TransitionResult>(`/api/pipelines/${enc(name)}/approve`, 'POST', {}),
  dryRunPipeline: (name: string, runId: string) =>
    write<DryRunResult>(`/api/pipelines/${enc(name)}/dry-run?run_id=${enc(runId)}`, 'POST', {}),
  pipelineDiff: (name: string) => get<DiffResult>(`/api/pipelines/${enc(name)}/diff`),

  // ── settings: threshold overrides (draft → approve) ──
  saveThresholds: (body: ThresholdOverrideIn) =>
    write<ThresholdOverrideAck>('/api/settings/thresholds', 'POST', body),
  listThresholds: () => get<ThresholdOverride[]>('/api/settings/thresholds'),
  thresholdVersions: (name: string) =>
    get<ThresholdOverride[]>(`/api/settings/thresholds/${enc(name)}`),
  approveThresholds: (name: string) =>
    write<ThresholdOverride>(`/api/settings/thresholds/${enc(name)}/approve`, 'POST', {}),

  // ── the original off-gate product telemetry write (W12) ──
  feedback: (body: FeedbackIn) => write<FeedbackAck>('/api/feedback', 'POST', body),
}
