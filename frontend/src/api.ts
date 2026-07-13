// Thin typed client over the FastAPI read-API (proxied to :8010 in dev). Reads are header-blind
// `get<T>`; the runs list additionally exposes a header-aware variant (`runsPage`) because
// pagination totals + status-facet counts ride response headers. Writes inject the RBAC actor
// (X-Bayleaf-Actor/-Role) set by the RoleContext — approver unlocks approvals only, never a
// verdict (rules decide / AI advises). Only endpoints that actually exist are called here.

import type {
  Actor,
  AgentGrant,
  AgentProposal,
  ArchiveDigest,
  CardReadout,
  ChatSendBody,
  ChatSendResponse,
  ChatSession,
  CompiledNextflow,
  DecisionCard,
  DiffResult,
  DryRunResult,
  FeedbackAck,
  FeedbackIn,
  FileListing,
  IntakeStatus,
  LibraryEntry,
  MetricCatalog,
  MonitoringMetrics,
  MonitoringWindow,
  NextflowGraphBody,
  NodeObservation,
  NodeProposal,
  PipelineGraph,
  PipelineRunStatus,
  PipelineGraphAck,
  PipelineGraphIn,
  ReviewActionName,
  RunArtifact,
  RunDetail,
  Runbook,
  RunbookPolicy,
  RunInputsCatalog,
  RunPipelineAck,
  RunStatus,
  RunSummary,
  RunsPage,
  ShareBundle,
  SubmitRunAck,
  SubmitRunIn,
  SystemAgentInfo,
  ThresholdOverride,
  ThresholdOverrideAck,
  ThresholdOverrideIn,
  Ticket,
  TicketIn,
  TicketStatus,
  TransitionResult,
  TriageCitation,
  TriageNote,
  VariantCall,
  Verdict,
} from './types'

// The advisory answer POST .../ask returns (mirrors bayleaf.triage.AgentReply). Defined here (not
// types.ts) so the client owns the ask request/response shape — like RunPipelineArgs/TicketsQuery.
// `advisory` is pinned true and there is deliberately no verdict/confidence: the agent answers, the
// rules decide (ADR-0001). `generated_by`/`model` carry the honest provenance — 'stub' is a real
// retrieval-grounded reply, never a fabricated constant.
export type AgentReply = {
  id: string
  advisory: true
  agent: string
  sample_id: string | null
  question: string
  answer: string
  citations: TriageCitation[]
  generated_by: 'stub' | 'claude'
  model: string | null
}

// ── RBAC actor holder ────────────────────────────────────────────────────────
// Set by RoleContext at the app root; read on every write. Kept as a module-level holder so
// api.ts stays React-free. No actor → the backend applies its permissive dev-default.
let _actor: Actor | null = null
export function setApiActor(actor: Actor | null): void {
  _actor = actor
}
function authHeaders(): Record<string, string> {
  if (!_actor) return {}
  return { 'X-Bayleaf-Actor': _actor.id, 'X-Bayleaf-Role': _actor.role }
}

// ── low-level fetch ──────────────────────────────────────────────────────────
// Surface FastAPI's error body, not just the status: a 4xx HTTPException carries a `detail` string
// (e.g. "no processable sample — only HG002 …"), a 422 carries a `detail` array of {msg}. Without
// this every toast read as a bare "422 Unprocessable Content" (surfaced by the 100-sample test).
async function httpError(res: Response): Promise<Error> {
  let detail = ''
  try {
    const j = (await res.json()) as { detail?: unknown }
    if (typeof j?.detail === 'string') detail = j.detail
    else if (Array.isArray(j?.detail))
      detail = (j.detail as Array<{ msg?: string }>)
        .map((d) => d?.msg)
        .filter(Boolean)
        .join('; ')
    else if (j?.detail) detail = JSON.stringify(j.detail)
  } catch {
    /* non-JSON error body — fall back to the status line */
  }
  return new Error(detail ? `${res.status} · ${detail}` : `${res.status} ${res.statusText}`)
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw await httpError(res)
  return (await res.json()) as T
}

async function write<T>(url: string, method: 'POST' | 'PATCH' | 'DELETE', body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw await httpError(res)
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
  if (!res.ok) throw await httpError(res)
  const data = (await res.json()) as RunSummary[]
  const totalHeader = res.headers.get('X-Bayleaf-Total-Count')
  const countsHeader = res.headers.get('X-Bayleaf-Status-Counts')
  const pageHeader = res.headers.get('X-Bayleaf-Page')
  const limitHeader = res.headers.get('X-Bayleaf-Limit')
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

// ── review-queue tickets query ───────────────────────────────────────────────
export type TicketsQuery = {
  status?: TicketStatus
  run_id?: string
  rule_id?: string
  // ISO date/datetime recency window: only tickets with created_at >= since. The total header
  // still reports the count IGNORING since, so a windowed view can show the true total.
  since?: string
}
function ticketsQs(opts: TicketsQuery = {}): string {
  const p = new URLSearchParams()
  if (opts.status) p.set('status', opts.status)
  if (opts.run_id) p.set('run_id', opts.run_id)
  if (opts.rule_id) p.set('rule_id', opts.rule_id)
  if (opts.since) p.set('since', opts.since)
  const s = p.toString()
  return s ? `?${s}` : ''
}
export type TicketsPage = { data: Ticket[]; total: number | null }
// Header-aware tickets fetch: the status-scoped total (ignoring `since`) rides a response header.
async function fetchTicketsPage(opts: TicketsQuery = {}): Promise<TicketsPage> {
  const res = await fetch(`/api/review/tickets${ticketsQs(opts)}`)
  if (!res.ok) throw await httpError(res)
  const data = (await res.json()) as Ticket[]
  const totalHeader = res.headers.get('X-Bayleaf-Ticket-Total')
  return { data, total: totalHeader ? Number(totalHeader) : null }
}

// ── monitoring page query ──────────────────────────────────────────────────────
export type MonitoringPageQuery = { page?: number; limit?: number; signaturesLimit?: number }
// One monitoring response, carrying the header-borne per-run (`runs[]`) total the header-blind
// `api.monitoring` drops. Only the throughput array is paginated server-side; the KPIs, gate
// rates, and signatures inside `data` stay aggregated over the whole window (mirrors RunsPage).
export type MonitoringPage = {
  data: MonitoringMetrics
  total: number
  page: number | null
  limit: number | null
}
async function fetchMonitoringPage(
  window: MonitoringWindow = 'all',
  opts: MonitoringPageQuery = {},
): Promise<MonitoringPage> {
  const p = new URLSearchParams({ window })
  if (opts.signaturesLimit != null) p.set('signatures_limit', String(opts.signaturesLimit))
  if (opts.page != null) p.set('page', String(opts.page))
  if (opts.limit != null) p.set('limit', String(opts.limit))
  const res = await fetch(`/api/monitoring?${p.toString()}`)
  if (!res.ok) throw await httpError(res)
  const data = (await res.json()) as MonitoringMetrics
  const totalHeader = res.headers.get('X-Bayleaf-Total-Count')
  const pageHeader = res.headers.get('X-Bayleaf-Page')
  const limitHeader = res.headers.get('X-Bayleaf-Limit')
  return {
    data,
    total: totalHeader ? Number(totalHeader) : data.runs.length,
    page: pageHeader ? Number(pageHeader) : null,
    limit: limitHeader ? Number(limitHeader) : null,
  }
}

const enc = encodeURIComponent

// The body POST /api/pipelines/run accepts: a run NAMES a saved pipeline (its APPROVED baseline is
// resolved + compiled server-side), never a raw graph. `version` optionally pins an exact approved
// revision. Defined here (not types.ts) so the client owns its request shape — mirrors TicketsQuery.
export type RunPipelineArgs = {
  name: string
  version?: number
  run_id: string
  sample?: string
  platform?: string
  inputs: { reads?: string; reference?: string; panel_bed?: string }
}

export const api = {
  // ── intake: submit a run for processing (the execution boundary) ──
  submitRun: (body: SubmitRunIn) => write<SubmitRunAck>('/api/runs', 'POST', body),
  intakeStatus: (runId: string) => get<IntakeStatus>(`/api/runs/${enc(runId)}/intake-status`),
  // Release a HELD or SCHEDULED run → fire the driver now (ADR-0021; reviewer/approver-gated).
  // The manual counterpart to a time-based scheduler; 409 if the run is not held/scheduled.
  releaseRun: (runId: string) => write<IntakeStatus>(`/api/runs/${enc(runId)}/release`, 'POST', {}),

  // ── runs + cards (reads) ──
  runs: (opts?: RunsQuery) => get<RunSummary[]>(`/api/runs${runsQs(opts)}`),
  runsPage: (opts?: RunsQuery) => fetchRunsPage(opts),
  run: (runId: string) => get<RunDetail>(`/api/runs/${enc(runId)}`),
  card: (runId: string, sampleId: string) =>
    get<DecisionCard>(`/api/runs/${enc(runId)}/cards/${enc(sampleId)}`),
  qcReadout: (runId: string, sampleId: string) =>
    get<CardReadout>(`/api/runs/${enc(runId)}/cards/${enc(sampleId)}/qc-readout`),
  artifacts: (runId: string) => get<RunArtifact[]>(`/api/runs/${enc(runId)}/artifacts`),
  // Every annotated candidate variant for a run (W3) — READ-only, ClinVar significance verbatim
  // (ADR-0004); backs the RunReport's full per-variant table. Empty array for a run with no
  // variants.csv (a missing annotation is a signal, not an error).
  variants: (runId: string) => get<VariantCall[]>(`/api/runs/${enc(runId)}/variants`),
  // PHASE 4 — a bound advisory agent's SCOPED READ of one node's published outputs for a run
  // (payoff for the Wave-2 AgentBinding grant model). READ-only, off the gate: 'outputs' (default)
  // lists the node's published artifacts; 'logs' (opt-in) adds the DE-IDENTIFIED task-log tail.
  // Backs the future grant-popover / agent-triage "what the agent sees" view.
  nodeObservations: (runId: string, nodeId: string, grants: AgentGrant[] = ['outputs']) =>
    get<NodeObservation>(
      `/api/runs/${enc(runId)}/nodes/${enc(nodeId)}/observations?grants=${enc(grants.join(','))}`,
    ),
  triage: (runId: string, sampleId: string) =>
    get<TriageNote>(`/api/runs/${enc(runId)}/cards/${enc(sampleId)}/triage`),
  // Interactive sibling of `triage`: a free-text question about a card → an advisory AgentReply
  // (ADR-0001 — never sets/overrides a verdict). Off the deterministic path; the offline stub
  // returns a real retrieval-grounded answer (never a fabricated constant), the armed agent prose.
  // Even a CLEAN card can be asked about. A POST (stateless server), header-blind reads notwithstanding.
  askAgent: (runId: string, sampleId: string, question: string) =>
    write<AgentReply>(`/api/runs/${enc(runId)}/cards/${enc(sampleId)}/ask`, 'POST', { question }),

  // ── policy / catalog (reads) ──
  config: () => get<Runbook>('/api/config'),
  runbook: () => get<RunbookPolicy>('/api/runbook'),
  metricsRegistry: () => get<MetricCatalog>('/api/metrics/registry'),
  health: () => get<{ status: string }>('/api/health'),

  // ── monitoring (read) ──
  monitoring: (window: MonitoringWindow = 'all', signaturesLimit?: number) => {
    const p = new URLSearchParams({ window })
    if (signaturesLimit != null) p.set('signatures_limit', String(signaturesLimit))
    return get<MonitoringMetrics>(`/api/monitoring?${p.toString()}`)
  },
  // Header-aware variant: the body is MonitoringMetrics, but the pre-slice per-run total rides the
  // X-Bayleaf-Total-Count header a plain get<T> drops — mirrors runsPage. Used by the Monitoring
  // screen to server-paginate the throughput array without capping the KPIs/gates/signatures.
  monitoringPage: (window: MonitoringWindow = 'all', opts?: MonitoringPageQuery) =>
    fetchMonitoringPage(window, opts),

  // ── advisory agent reads (off-gate) ──
  signatureRepair: (signature: string) =>
    get<AgentProposal>(`/api/monitoring/signatures/${enc(signature)}/repair`),
  archiveDigest: (runId: string) =>
    get<ArchiveDigest>(`/api/runs/${enc(runId)}/archive-digest`),
  archiveIndex: () => get<ArchiveDigest>('/api/archive/index'),
  // Node-authoring agent #6 (W2): a natural-language request → an advisory NodeProposal (typed
  // ports, pinned version, locators, citations). Read-only + off-gate; the modal renders it for a
  // human — it never auto-adds a card or authors a runnable command.
  nodeProposal: (request: string) =>
    get<NodeProposal>(`/api/builder/node-proposal?${new URLSearchParams({ request }).toString()}`),
  // Accept an advisory proposal into the tool-card library as a draft (reviewer/approver). The
  // server RE-DERIVES the proposal from the request (never trusts a client proposal) + runs the
  // conformance guard; the stored entry is metadata only — a human still authors the ProcessSpec.
  acceptNodeProposal: (request: string) =>
    write<LibraryEntry>('/api/builder/node-proposal/accept', 'POST', { request }),
  builderLibrary: () => get<LibraryEntry[]>('/api/builder/library'),

  // ── System-agents chat (design/system-agents-chat.md) ──
  // Advisory chat with a system agent; history is structured + retained (archive/delete are
  // view-scoped soft-deletes). Off-gate — a chat never re-enters the deterministic gate.
  systemAgents: () => get<SystemAgentInfo[]>('/api/agents'),
  chatSend: (agent: string, body: ChatSendBody) =>
    write<ChatSendResponse>(`/api/agents/${enc(agent)}/chat`, 'POST', body),
  chatList: (includeArchived = false) =>
    get<ChatSession[]>(`/api/agents/chats${includeArchived ? '?include_archived=true' : ''}`),
  chatGet: (id: string) => get<ChatSession>(`/api/agents/chats/${enc(id)}`),
  chatArchive: (id: string) => write<ChatSession>(`/api/agents/chats/${enc(id)}/archive`, 'POST'),
  chatRestore: (id: string) => write<ChatSession>(`/api/agents/chats/${enc(id)}/restore`, 'POST'),
  chatDelete: (id: string) => write<ChatSession>(`/api/agents/chats/${enc(id)}`, 'DELETE'),

  // ── sandboxed server-side file browser (off-gate, read-only) ──
  // Lists one level under an allowlisted root (default 'data') for the Builder's "Browse…" data
  // pickers — the GB-scale server-resident inputs never leave the host, only their metadata does.
  // `path` omitted → the root itself; entries are dirs-first then name.
  browseFiles: (root: string, path?: string) => {
    const p = new URLSearchParams({ root })
    if (path) p.set('path', path)
    return get<FileListing>(`/api/files?${p.toString()}`)
  },

  // ── export (download link; no fetch needed for the CSV) ──
  exportUrl: (params: Record<string, string> = {}) =>
    `/api/export${Object.keys(params).length ? `?${new URLSearchParams(params).toString()}` : ''}`,

  // ── de-identified share/report egress (ADR-0018 D3; approver-gated + confirm-gated) ──
  // Records a DATA_EXPORTED provenance event server-side; the caller refetches the run to show it.
  shareRun: (runId: string) => write<ShareBundle>(`/api/runs/${enc(runId)}/share`, 'POST', {}),

  // ── compile a Builder card graph → Nextflow (ADR-0003; stateless, off-gate) ──
  compileNextflow: (body: NextflowGraphBody) =>
    write<CompiledNextflow>('/api/pipelines/compile', 'POST', body),
  compileNextflowZip: async (body: NextflowGraphBody): Promise<Blob> => {
    const res = await fetch('/api/pipelines/compile?format=zip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw await httpError(res)
    return res.blob()
  },

  // ── operator-driven execution of a composed pipeline (ADR-0003; reviewer/approver-gated) ──
  runInputs: () => get<RunInputsCatalog>('/api/pipelines/run/inputs'),
  // The approval gate (ADR-0014): a run NAMES a saved pipeline; the backend compiles + runs that
  // pipeline's APPROVED (emitted) baseline — never a raw client graph. `version` optionally pins an
  // exact approved revision (omitted → latest approved). 409 if the pipeline has no approved version.
  runPipeline: (body: RunPipelineArgs) =>
    write<RunPipelineAck>('/api/pipelines/run', 'POST', body),
  runStatus: (runId: string) =>
    get<PipelineRunStatus>(`/api/pipelines/run/${enc(runId)}`),

  // ── review-queue tickets ──
  createTicket: (body: TicketIn) => write<Ticket>('/api/review/tickets', 'POST', body),
  listTickets: (opts: TicketsQuery = {}) => get<Ticket[]>(`/api/review/tickets${ticketsQs(opts)}`),
  // Header-aware variant: the body is Ticket[], but the status-scoped total (ignoring `since`) rides
  // the X-Bayleaf-Ticket-Total header a plain get<T> would drop — mirrors fetchRunsPage. Used by
  // the Review queue's Resolved tab to show "N resolved total" while it loads only a recent window.
  listTicketsPage: (opts: TicketsQuery = {}) => fetchTicketsPage(opts),
  ticketAction: (id: string, action: ReviewActionName) =>
    write<Ticket>(`/api/review/tickets/${enc(id)}/action`, 'POST', { action }),
  // Assign (or unassign, with assignee=null) a ticket's owner — the review↔kanban link. A backend
  // write (reviewer/approver-gated); never a status transition, never a verdict (ADR-0001).
  assignTicket: (id: string, assignee: string | null) =>
    write<Ticket>(`/api/review/tickets/${enc(id)}/assign`, 'POST', { assignee }),

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
