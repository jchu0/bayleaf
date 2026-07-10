// API shapes mirroring the FastAPI/pydantic models (hand-kept in sync for now).

export type Verdict = 'proceed' | 'hold' | 'rerun' | 'escalate'
export type Severity = 'info' | 'warn' | 'critical'
export type Gate = 'preflight' | 'qc' | 'variant'

export type Evidence = {
  source: string
  locator: string | null
  value: string | null
  expected: string | null
  source_kind: string
  source_field: string | null
  threshold: string | null
}

export type Finding = {
  id: string
  rule_id: string
  sample_id: string | null
  category: string
  severity: Severity
  title: string
  detail: string
  evidence: Evidence[]
  suggested_verdict: Verdict
  gate: Gate
  signature: string
  content_hash: string
}

export type GateResult = {
  gate: Gate
  verdict: Verdict
  severity: Severity
  rationale: string
  finding_rule_ids: string[]
}

// The unit a metric is normalized *to* (registry canonical_unit). Consumers read
// `normalized_value`, which is always in this unit — never `raw_value`.
export type CanonicalUnit = 'fraction' | 'percent' | 'x' | 'ratio' | 'phred' | 'count' | 'bool'

// One registry-normalized QC metric (schemas.md #6). Self-contained: `canonical_unit` +
// `metric_registry_version` are snapshotted onto the record (ADR-0007).
export type MetricValue = {
  id: string
  sample_id: string
  metric_key: string
  gate: Gate
  raw_value: number
  raw_unit: string
  normalized_value: number
  canonical_unit: CanonicalUnit
  metric_registry_version: number
  analysis_run_id: string | null
  source_artifact_id: string | null
  source_field: string | null
  source_locator: string | null
  parser_version: string | null
  content_hash: string
}

export type DecisionCard = {
  sample_id: string
  verdict: Verdict
  confidence: number | null
  headline: string
  rationale: string
  next_steps: string[]
  findings: Finding[]
  generated_by: string
  analysis_run_id: string | null
  // Registry-normalized QC metrics for this sample (T-025). Optional: absent on samples
  // with no QC row, and a full metrics panel is not yet built (types-only for now).
  metric_values?: MetricValue[]
  gate_results: GateResult[]
  content_hash: string
}

export type EntityRef = {
  entity_type: string
  id: string
  content_hash: string | null
}

export type ProvenanceEvent = {
  id: string
  event_type: string
  analysis_run_id: string | null
  run_id: string | null
  sample_id: string | null
  actor: string
  inputs: EntityRef[]
  outputs: EntityRef[]
  payload: Record<string, unknown>
  created_at: string
}

// A run's lifecycle stage — a REAL server field read from the SampleSheet [Header], never
// inferred from n_attention (a running run with 0 flagged samples is `running`, not released).
// Wire value is `needs_review` (not `review`); map to a display label at the render layer.
export type RunStatus = 'running' | 'needs_review' | 'released'

export type RunSummary = {
  run_id: string
  n_samples: number
  n_attention: number
  counts: Record<string, number>
  status: RunStatus
  platform: string | null
  run_date: string | null
}

// One page of the runs list, carrying the header-borne totals + status facet counts that a
// header-blind fetch would drop (X-PipeGuard-Total-Count / -Status-Counts / -Page / -Limit).
export type RunsPage = {
  data: RunSummary[]
  total: number
  statusCounts: Record<RunStatus, number> | null
  page: number | null
  limit: number | null
}

// The pipeline stages of the provenance canvas (§5). Fixed order: intake → demux → qc →
// align → variant → gate; the three gate checkpoints attach to demux/qc/variant.
export type PipelineStage = 'intake' | 'demux' | 'qc' | 'align' | 'variant' | 'gate'

// One data artifact in a run's lineage (GET /api/runs/:id/artifacts). sha256 is null for
// raw reads above the API's hash cap; origin tags where the data came from.
export type RunArtifact = {
  name: string
  stage: PipelineStage
  role: 'input' | 'output'
  sha256: string | null
  size_bytes: number
  origin: string
}

export type RunDetail = {
  run_id: string
  summary: RunSummary
  cards: DecisionCard[]
  events: ProvenanceEvent[]
}

export type TriageCitation = {
  source_kind: 'knowledge' | 'finding'
  ref: string
  title: string | null
  score: number | null
}

export type TriageNote = {
  id: string
  advisory: true
  agent: string
  sample_id: string | null
  addresses_rule_ids: string[]
  likely_cause: string
  suggested_action: string
  citations: TriageCitation[]
  generated_by: string
  model: string | null
}

export type QCThreshold = {
  metric: string
  label: string
  gate: number
  hard_fail: number
  higher_is_better: boolean
  borderline_band: number
  unit: string
}

export type Runbook = {
  run_id_field: string
  require_metadata_fields: string[]
  qc_thresholds: QCThreshold[]
  log_failure_markers: string[]
}

// One registered metric type from the canonical registry (GET /api/metrics/registry).
// Read-only vocabulary: `gated` reports whether the live runbook currently gates on this
// `our_key` — registered-but-ungated entries are the extensibility surface.
export type MetricCatalogEntry = {
  our_key: string
  display_name: string
  category: string
  canonical_unit: CanonicalUnit
  direction: 'higher_is_better' | 'lower_is_better' | 'target_band'
  gate: Gate
  source_module: string
  aliases: string[]
  gated: boolean
}

// The registered metric vocabulary + which entries the live runbook gates on. Versioned,
// operator-configurable tool metadata — never a calibrated or clinical panel (see `disclaimer`).
export type MetricCatalog = {
  disclaimer: string
  metric_registry_version: number
  n_registered: number
  n_gated: number
  entries: MetricCatalogEntry[]
}

// In-app feedback (W12) — product telemetry, OFF the deterministic gate. `decision` carries
// an agree/disagree signal keyed to a verdict; `product` carries a kind for diffuse feedback.
// Mirrors api/feedback.py; the request never carries any operator identity field.
export type FeedbackTarget = 'decision' | 'product'
// The exact UI surface a reaction came from (trace) — distinct from `target`.
export type FeedbackSource = 'decision-card' | 'product-fab' | 'triage-note' | 'review-queue'
export type FeedbackSignal = 'agree' | 'disagree'
export type FeedbackKind = 'idea' | 'problem' | 'confusing' | 'praise'
export type FeedbackReasonCode =
  | 'threshold_too_strict'
  | 'threshold_too_loose'
  | 'wrong_root_cause'
  | 'missing_context'
  | 'other'

export type FeedbackContext = {
  run_id?: string | null
  sample_id?: string | null
  verdict?: Verdict | null
  gate?: Gate | null
  rule_ids?: string[]
  card_content_hash?: string | null
  route?: string | null
  screen?: string | null
}

export type FeedbackIn = {
  target: FeedbackTarget
  source: FeedbackSource
  signal?: FeedbackSignal | null
  reason_code?: FeedbackReasonCode | null
  kind?: FeedbackKind | null
  message?: string | null
  context?: FeedbackContext
}

export type FeedbackAck = {
  id: string
  received_at: string
  schema_version: number
  status: 'recorded'
}

// ─────────────────────────────────────────────────────────────────────────────
// RBAC (dev shim). Mirrors api/auth.py: an actor id + a role, sent on writes via the
// X-PipeGuard-Actor / X-PipeGuard-Role headers. Approver unlocks threshold/pipeline approval
// only — never a card verdict (rules decide / AI advises).
// ─────────────────────────────────────────────────────────────────────────────
export type Role = 'viewer' | 'reviewer' | 'approver'
export type Actor = { id: string; role: Role }

// ─────────────────────────────────────────────────────────────────────────────
// Origin / artifact vocabularies (read-only in the client — origin never relabels up).
// ─────────────────────────────────────────────────────────────────────────────
export type OriginTag = 'real-giab' | 'synthetic' | 'contrived' | 'unknown'
export type ArtifactKind =
  | 'fastq' | 'bam' | 'bai' | 'recal_cram' | 'recal_table' | 'mosdepth_summary'
  | 'fastp_json' | 'markdup_metrics' | 'samtools_stats' | 'vcf' | 'gvcf'
  | 'filtered_vcf' | 'joint_vcf' | 'ngscheckmate' | 'multiqc_json' | 'versions_yml'
  | 'params_json' | 'execution_trace'
export type ReferenceKind = 'reference_fasta' | 'panel_bed' | 'truth_vcf'

// ─────────────────────────────────────────────────────────────────────────────
// Windowed monitoring aggregate (GET /api/monitoring). Replaces the per-run N-fan-out.
// auto_proceed_pct is a throughput heuristic, NOT a calibrated confidence.
// ─────────────────────────────────────────────────────────────────────────────
export type MonitoringWindow = '7d' | '14d' | '30d' | 'all'
export type MonitoringOverall = {
  n_runs: number
  n_samples: number
  n_attention: number
  verdict_counts: Record<string, number>
  auto_proceed_pct: number | null
}
export type MonitoringRunRow = {
  run_id: string
  run_date: string | null
  n_samples: number
  counts: Record<string, number>
}
export type MonitoringGate = { gate: Gate; flagged: number; total: number }
// first_seen/last_seen/trend are NOT yet served (F2) — kept optional so the row can render
// the columns honestly (omitted) until the backend aggregate carries them.
export type MonitoringSignature = {
  signature: string
  rule_id: string
  title: string
  gate: Gate
  count: number
  first_seen?: string | null
  last_seen?: string | null
  trend?: 'up' | 'down' | 'flat' | null
}
export type MonitoringMetrics = {
  window: MonitoringWindow
  n_runs_excluded_no_date: number
  n_signatures_total: number
  overall: MonitoringOverall
  runs: MonitoringRunRow[]
  gates: MonitoringGate[]
  signatures: MonitoringSignature[]
}

// ─────────────────────────────────────────────────────────────────────────────
// QC readout (GET /api/runs/:id/cards/:sid/qc-readout) — the Decision-cards hero table.
// Gate-grouped, flagged-first Metric·Observed·Threshold·Status rows.
// ─────────────────────────────────────────────────────────────────────────────
export type ReadoutStatus = 'pass' | 'borderline' | 'fail' | 'not_gated'
export type ReadoutDirection = '>=' | '<=' | '?'
export type MetricReadout = {
  metric: string
  label: string
  gate: Gate
  status: ReadoutStatus
  direction: ReadoutDirection
  observed_value: number
  canonical_unit: CanonicalUnit
  observed_unit: string
  observed_display: string
  threshold_display: string | null
  hard_fail_display: string | null
  within_borderline_band: boolean
  flagged: boolean
}
export type GateReadout = { gate: Gate; rows: MetricReadout[]; flagged_count: number }
export type QcReadout = { sample_id: string; gates: GateReadout[]; flagged_count: number }
// origin/sample_type/library_prep are honestly nullable; not_captured lists the missing ones.
export type CardHeader = {
  sample_id: string
  run_id: string | null
  verdict: Verdict
  generated_by: string
  sample_type: string | null
  library_prep: string | null
  origin: string | null
  not_captured: string[]
}
export type CardReadout = { header: CardHeader; readout: QcReadout }

// ─────────────────────────────────────────────────────────────────────────────
// Operator-facing runbook policy (GET /api/runbook) — disclaimer-bearing, with `our_key` +
// direction. Distinct from the raw core Runbook (GET /api/config).
// ─────────────────────────────────────────────────────────────────────────────
export type RunbookThreshold = {
  metric: string
  our_key: string
  label: string
  gate: Gate
  hard_fail: number
  unit: string
  direction: 'higher_is_better' | 'lower_is_better'
}
export type RunbookPolicy = {
  disclaimer: string
  units_note: string
  run_id_field: string
  required_metadata_fields: string[]
  thresholds: RunbookThreshold[]
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline graph store + lifecycle (api/pipeline.py + routers/pipelines_lifecycle.py).
// The graph is authoring state; a verdict is NEVER stored on it. Status vocab uses the
// backend wire values (pending_review, not README §7's `pending`).
// ─────────────────────────────────────────────────────────────────────────────
export type PipelineStatus = 'draft' | 'pending_review' | 'approved'
export type PipelineGraphIn = {
  name: string
  schema_version?: string
  graph: Record<string, unknown>
  profile?: string | null
}
export type PipelineGraph = {
  id: string
  name: string
  schema_version: string
  version: number
  created_at: string
  graph: Record<string, unknown>
  profile: string | null
  status: PipelineStatus
  submitted_by: string | null
  reviewed_by: string | null
  approved_by: string | null
}
export type PipelineGraphAck = {
  id: string
  name: string
  version: number
  schema_version: string
  created_at: string
  status: PipelineStatus
}
export type TransitionResult = {
  name: string
  version: number
  status: PipelineStatus
  submitted_by?: string | null
  reviewed_by?: string | null
  approved_by?: string | null
  created_at: string
  emitted_at: string | null
}
export type LocatorResolution = {
  node: string | null
  kind: string
  mode: 'path' | 'glob'
  pattern: string
  required: boolean
  role: string
  on_multiple: string
  status: 'matched' | 'ambiguous' | 'missing' | 'invalid'
  paths: string[]
}
export type DryRunResult = {
  name: string
  version: number
  run_id: string
  executed: false
  locators: LocatorResolution[]
  summary: Record<string, number>
}
export type LocatorDiff = {
  key: string
  node: string | null
  kind: string
  role: string
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
}
export type DiffResult = {
  name: string
  has_baseline: boolean
  working_version: number
  emitted_version: number | null
  emitted_at: string | null
  added: LocatorDiff[]
  removed: LocatorDiff[]
  changed: LocatorDiff[]
  unchanged_count: number
}

// ─────────────────────────────────────────────────────────────────────────────
// Review-queue tickets (routers/review_queue.py). Recurrence/issueClass/resolvedBy in the
// prototype are frontend-derived, NOT wire fields.
// ─────────────────────────────────────────────────────────────────────────────
export type TicketStatus = 'open' | 'in_review' | 'resolved'
export type TicketPriority = 'high' | 'medium' | 'low'
export type ReviewActionName = 'acknowledge' | 'resolve' | 'escalate' | 'suppress' | 'reopen'
export type TicketAction = { action: ReviewActionName; actor: string; at: string }
export type Ticket = {
  id: string
  schema_version: number
  created_at: string
  run_id: string
  sample_id: string
  gate: Gate
  verdict: Verdict
  rule_id: string
  title: string
  priority: TicketPriority
  status: TicketStatus
  opened_by: string
  actions: TicketAction[]
}
export type TicketIn = {
  run_id: string
  sample_id: string
  gate: Gate
  verdict: Verdict
  rule_id: string
  title: string
  priority?: TicketPriority
}

// ─────────────────────────────────────────────────────────────────────────────
// Settings-authoring: threshold overrides (routers/settings.py). `payload` is an opaque
// tolerant blob — the assay×sample-type rows are a frontend convention packed into it.
// ─────────────────────────────────────────────────────────────────────────────
export type SettingsStatus = 'draft' | 'pending_review' | 'approved'
export type ThresholdOverrideIn = { name: string; payload: Record<string, unknown> }
export type ThresholdOverride = {
  id: string
  name: string
  version: number
  created_at: string
  payload: Record<string, unknown>
  status: SettingsStatus
  submitted_by: string | null
  reviewed_by: string | null
  approved_by: string | null
}
export type ThresholdOverrideAck = {
  id: string
  name: string
  version: number
  created_at: string
  status: SettingsStatus
  submitted_by: string | null
}

// ─────────────────────────────────────────────────────────────────────────────
// Advisory agent reads (off-gate, read-only): pipeline-repair + archivist proposals.
// ─────────────────────────────────────────────────────────────────────────────
export type AgentProposal = {
  agent: 'qc_triage' | 'pipeline_repair' | 'archivist'
  advisory_only: true
  summary: string
  mode: 'stub' | 'claude'
}

// ─────────────────────────────────────────────────────────────────────────────
// Frontend-local compose types (README §7). NO backend write endpoint yet — Submit registers
// in local state, the Builder emits config. Compose ≠ execute.
// ─────────────────────────────────────────────────────────────────────────────
export type SampleRow = { sample: string; type: string; i7: string; i5: string; study: string }
export type Submission = {
  runName: string
  study: string
  assay: string
  platform: string
  source: 'upload' | 'basespace'
  samples: SampleRow[]
}
export type LayoutLocator = {
  kind: ArtifactKind | ReferenceKind
  path?: string
  glob?: string
  parser: string | null
  required: boolean
  role: 'output' | 'reference'
  onMultiple: 'first' | 'all' | 'error'
  origin: OriginTag
}
export type RunLayoutConfig = {
  schemaVersion: 'run_layout/1'
  profile: string
  locators: Record<string, LayoutLocator>
}
export type ProposedFlag = { flag: string; value: string; enabled: boolean; help: string }
