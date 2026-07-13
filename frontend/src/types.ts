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

// Deterministic 'N ran / M not examined' coverage telemetry (WS-01). Un-hashed contextual
// metadata; contamination/identity have no check today, so they are honestly not-examined.
export type CheckCoverage = {
  checks_expected: number
  checks_ran: number
  not_examined: string[]
  categories_ran: string[]
  categories_not_run: string[]
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
  // Registry-normalized QC metrics for this sample (T-025). Always emitted (backend
  // `default_factory=list`): an empty array when a sample has no QC row, never absent.
  metric_values: MetricValue[]
  // Coverage telemetry (WS-01): null on older/partial cards; when present the UI shows the honest
  // 'N ran / M not examined' story instead of a blanket "all checks passed".
  check_coverage: CheckCoverage | null
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
// header-blind fetch would drop (X-Bayleaf-Total-Count / -Status-Counts / -Page / -Limit).
export type RunsPage = {
  data: RunSummary[]
  total: number
  statusCounts: Record<RunStatus, number> | null
  page: number | null
  limit: number | null
}

// The pipeline stages of the provenance canvas (§5). Fixed order: intake → demux → qc → align →
// variant → filter → review → gate → share. The gate checkpoints attach to demux (preflight),
// qc (qc), and review (variant — the flag-for-review VAR-FFR-001 step). The post-variant stages
// (filter/normalize, flag-for-review review, de-identified share) are honest lineage nodes that
// read "not run in this build" when this build produced no artifact/event for them (W3).
export type PipelineStage =
  | 'intake'
  | 'demux'
  | 'qc'
  | 'align'
  | 'variant'
  | 'filter'
  | 'review'
  | 'gate'
  | 'share'

// One data artifact in a run's lineage (GET /api/runs/:id/artifacts). sha256 is null for
// raw reads above the API's hash cap; origin tags where the data came from.
export type RunArtifact = {
  name: string
  stage: PipelineStage
  role: 'input' | 'output'
  sha256: string | null
  size_bytes: number
  origin: string
  url: string // same-origin download link: GET /api/runs/:id/artifacts/:name
}

export type RunDetail = {
  run_id: string
  summary: RunSummary
  cards: DecisionCard[]
  events: ProvenanceEvent[]
}

// One annotated candidate variant (GET /api/runs/:id/variants), READ from an externally-produced
// annotated VCF/table (ADR-0018) — a driver ran the annotator; bayleaf never does (composes ≠
// executes). `clinvar_significance` is a VERBATIM ClinVar quotation, never bayleaf's own call
// (ADR-0004). Every field but `sample_id` is nullable: a partial annotation is a signal, not a
// crash. Backs the RunReport's full per-variant table (W3), beneath the flag-for-review hero.
export type VariantCall = {
  sample_id: string
  gene: string | null
  hgvs: string | null
  clinvar_significance: string | null
  clinvar_review_status: string | null
  clinvar_accession: string | null
  clinvar_version: string | null
}

// A de-identified share/report egress (ADR-0018 D3): the scrubbed rows + an honesty/provenance
// manifest. `policy_id` is a scrub VERSION, never a compliance attestation (see `disclaimer`).
export type ShareManifest = {
  run_id: string
  policy_id: string
  grain: string
  n_rows: number
  origin: string
  exported_at: string
  exported_by: string
  content_hash: string
  event_id: string
  safe_harbor_classes: string[]
  disclaimer: string
}
export type ShareBundle = {
  manifest: ShareManifest
  rows: Record<string, unknown>[]
}

// The Builder-card graph in the shape POST /api/pipelines/compile accepts (name=tool per node;
// edges by typed-port index) — ADR-0003: the Builder composes this; the compiler emits Nextflow.
// A node MAY additionally carry an operator-authored custom Nextflow process (ADR-0020): a HUMAN
// supplies `script` (a verbatim `script:` body) + optional `container`/`conda` packaging. A non-empty
// `script` makes the backend render THAT body verbatim (never the tool catalog); the three fields are
// optional + additive, so an ordinary catalogued/source card omits them and the wire shape is unchanged.
export type NextflowGraphBody = {
  name: string
  nodes: { id: string; name: string; ins: string[]; outs: string[]; script?: string; container?: string; conda?: string }[]
  edges: { from: { node: string; idx: number }; to: { node: string; idx: number } }[]
}
// The compiled pipeline: a map of relative path → file content, the main.nf, and the DAG's
// topological tool order (a quick human summary).
export type CompiledNextflow = {
  name: string
  files: Record<string, string>
  main_nf: string
  steps: string[]
}

// Operator-driven EXECUTION of a composed pipeline (ADR-0003). The operator picks inputs by KEY
// from a server-side catalog; the backend runs the compiled pipeline via Nextflow → a gate-able run.
export type RunInputOption = { key: string; label: string; origin: string }
export type RunInputsCatalog = {
  reads: RunInputOption[]
  reference: RunInputOption[]
  panel_bed: RunInputOption[]
}
export type RunPipelineBody = {
  graph: NextflowGraphBody
  run_id: string
  sample?: string
  platform?: string
  inputs: { reads?: string; reference?: string; panel_bed?: string }
}
export type RunPipelineAck = { run_id: string; status: string; steps: string[] }
// Named PipelineRunStatus to avoid clashing with the run-lifecycle `RunStatus`.
export type PipelineRunStatus = { run_id: string; status: string; error: string | null }

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
  // Semantic finding signatures this note addresses (backend serves it alongside rule_ids).
  addresses_signatures: string[]
  likely_cause: string
  suggested_action: string
  citations: TriageCitation[]
  generated_by: string
  model: string | null
}

// The raw core QC threshold as served by GET /api/config (Runbook.model_dump). `our_key` is the
// registry controlled-vocabulary key this threshold gates on; `required=false` means a MISSING
// metric is NOT a finding (an optional, non-blocking check). gate/hard_fail are canonical units.
export type QCThreshold = {
  metric: string
  our_key: string
  label: string
  gate: number
  hard_fail: number
  higher_is_better: boolean
  borderline_band: number
  unit: string
  required: boolean
}

// Off-by-default flag-for-review policy (ADR-0018 D2). Disarmed when `significances` is empty (the
// shipped default). Tuples serialize to arrays over the wire.
export type FlagForReviewPolicy = {
  significances: string[]
  review_statuses: string[]
}

export type Runbook = {
  run_id_field: string
  require_metadata_fields: string[]
  qc_thresholds: QCThreshold[]
  log_failure_markers: string[]
  trace_failure_statuses: string[]
  flag_for_review: FlagForReviewPolicy
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
// X-Bayleaf-Actor / X-Bayleaf-Role headers. Approver unlocks threshold/pipeline approval
// only — never a card verdict (rules decide / AI advises).
// ─────────────────────────────────────────────────────────────────────────────
export type Role = 'viewer' | 'reviewer' | 'approver'
export type Actor = { id: string; role: Role }

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline-Builder agent-attachment binding (advisory, off-gate — ADR-0001).
// A binding attaches an ADVISORY agent (QC-triage) to a graph NODE as an OBSERVATION
// grant: it lets the agent READ that node's artifacts, it NEVER wires a data edge, adds
// a card, sets a verdict/confidence, or changes what the pipeline runs. It is persisted in
// a SIBLING envelope key (graph.agent_bindings) that the Nextflow compiler NEVER dereferences
// — the compile/run payload stays a pure function of {nodes, edges}, so the emitted pipeline
// is byte-identical with or without any binding (compose ≠ execute).
//   grants — what the agent may observe:
//     'outputs' (default, on): the node's published output artifacts.
//     'logs'    (opt-in, off by default): the node's .command.log/.err. These carry subject-id
//               PII, so the grant is de-identified + explicitly opt-in, never a default.
export type AgentGrant = 'outputs' | 'logs'
export type AgentBinding = { agent: string; node: string; grants: AgentGrant[] }

// PHASE 4 — a bound agent's SCOPED READ of a node's published outputs
// (GET /api/runs/{run_id}/nodes/{node_id}/observations?grants=outputs[,logs]). Advisory,
// read-only, off the gate (ADR-0001) and node-scoped/least-privilege (ADR-0012): 'outputs' lists
// the node's published artifacts; 'logs' (opt-in) adds the DE-IDENTIFIED tail of the node's task
// logs. `source: 'none'` + a `note` is the honest-empty state (a fixture-only run, or an
// authored-pipeline node id that didn't resolve) — never a fabricated output.
export type NodeObservationArtifact = {
  name: string
  relpath: string
  kind: string | null
  size_bytes: number
}
export type NodeLogTail = {
  stream: 'stdout' | 'stderr'
  relpath: string
  lines: string[] // scrubbed tail — subject ids + generic PII redacted
  truncated: boolean
  deid_policy: string
}
export type NodeObservation = {
  run_id: string
  node_id: string
  tool: string | null
  process: string | null
  grants: AgentGrant[]
  advisory: true
  source: 'nextflow-publish' | 'none'
  outputs: NodeObservationArtifact[]
  logs: NodeLogTail[]
  note: string | null
}

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
// Additive §7 fidelity, all now served by GET /api/monitoring's MonitoringSignature:
// first_seen/last_seen are null when only undated runs carry the signature (honest omission, never
// faked); trend is a coarse up/down/flat display heuristic (backend default 'flat'), NOT a
// calibrated rate; affected_run_ids are the distinct runs the signature appears in (chronological).
export type MonitoringSignature = {
  signature: string
  rule_id: string
  title: string
  gate: Gate
  count: number
  first_seen: string | null
  last_seen: string | null
  trend: 'up' | 'down' | 'flat'
  affected_run_ids: string[]
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
// 'within' is a both-tails (target_band) gate: the value must sit WITHIN a [low, high] band, so its
// threshold_display is a band ('[2, 2.1]'), not a one-sided comparator (WS-06 Gap 2).
export type ReadoutDirection = '>=' | '<=' | 'within' | '?'
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
// `note` (frontend-only) is an honest empty-state line for a gate with no metric rows — e.g.
// preflight (rule-based, scored in the gate strip) or variant (no metrics extracted this build).
// `blocked_by` names an upstream gate that isn't clear (so this gate is gated downstream — reads
// "blocked, clear <upstream> first" rather than "all clear"). Verdict already reflects the finding.
export type GateReadout = { gate: Gate; rows: MetricReadout[]; flagged_count: number; note?: string; blocked_by?: Gate | null }
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
// A link to a QC HTML report artifact the run published (fastp.html / multiqc_report.html), when
// present on disk. This is the AI-off suggestion surface: the real reports + the metric readout,
// never fabricated next_steps (WS-07 Q1). `scope` is 'sample' (this sample's report) or 'run'
// (run-level). `url` targets the read-only inline artifact-serve endpoint. Empty ⇒ honest absence.
export type QcReportLink = { name: string; label: string; url: string; scope: 'sample' | 'run' }
export type CardReadout = { header: CardHeader; readout: QcReadout; qc_reports: QcReportLink[] }

// ─────────────────────────────────────────────────────────────────────────────
// Operator-facing runbook policy (GET /api/runbook) — disclaimer-bearing, with `our_key` +
// direction. Distinct from the raw core Runbook (GET /api/config).
// ─────────────────────────────────────────────────────────────────────────────
export type RunbookThreshold = {
  metric: string
  our_key: string
  label: string
  gate: number // numeric pass-threshold VALUE in canonical units (e.g. 0.85) — NOT the pipeline gate
  hard_fail: number
  unit: string
  direction: 'higher_is_better' | 'lower_is_better'
  pipeline_gate: Gate // preflight | qc | variant — the metric's gate, for grouping policy by gate
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
// The status-transition actions POST /tickets/{id}/action accepts (what `ticketAction` sends).
export type ReviewActionName = 'acknowledge' | 'resolve' | 'escalate' | 'suppress' | 'reopen'
// The full audit vocabulary that can appear in a stored action trail. `assign` is an audit event
// (who now owns the ticket) with its OWN endpoint — never a status transition, so it is not a
// ReviewActionName and never reaches POST /action.
export type ReviewAuditAction = ReviewActionName | 'assign'
export type TicketAction = { action: ReviewAuditAction; actor: string; at: string }
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
  // Current owner (a user id), or null when unassigned — set via POST /tickets/{id}/assign.
  assignee: string | null
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
export type RepairCitation = {
  source_kind: 'knowledge' | 'rule' | 'signature'
  ref: string
  title?: string | null
  // Heuristic keyword-overlap for knowledge hits — NOT a calibrated probability. Null for rule/signature refs.
  score?: number | null
}

// Advisory agent read (off-gate). Mirrors backend RepairProposal (pipeline_repair/models.py) and the
// qc_triage/archivist advisory shape. Enrichment fields are optional so existing consumers
// (ReviewRepairCard, MonitoringSignatureRow, ReviewQueue) that read only summary/mode keep compiling.
// The wire field for the repair endpoint is `advisory: true`; `advisory_only` is kept optional for
// any legacy caller but is NOT emitted by the repair endpoint.
export type AgentProposal = {
  agent: 'qc_triage' | 'pipeline_repair' | 'archivist'
  advisory?: true
  advisory_only?: true
  summary: string
  mode: 'stub' | 'claude'
  // ── enrichment (present on the repair endpoint payload) ──
  addresses_rule_id?: string
  addresses_signature?: string
  signature_count?: number
  run_ids?: string[]
  rationale?: string
  attach_to?: string | null
  scope?: Gate | null
  citations?: RepairCitation[]
  generated_by?: 'stub' | 'claude'
  model?: string | null
}

// ─────────────────────────────────────────────────────────────────────────────
// Advisory node-authoring read (agent #6; GET /api/builder/node-proposal). Mirrors the backend
// NodeProposal (node_author/models.py). Advisory ONLY: `advisory` is pinned true and there is
// deliberately NO verdict/confidence field — the agent PROPOSES a typed builder node for human
// review; it never wires an edge, adds a card, runs a tool, or authors a runnable script:/stub:
// body (those live solely in the hand-curated ProcessSpec catalog). See agent-authoring-contract.md.
// ─────────────────────────────────────────────────────────────────────────────
export type NodePortSpec = {
  kind: string
  required: boolean
  role: 'data' | 'reference' | 'qc'
  note?: string | null
  // Computed server-side: true iff `kind` is a real ArtifactKind. A false port is RESERVED —
  // surfaced as an honest, labelled slot, never wired.
  known: boolean
}
export type NodeLocatorSuggestion = {
  kind: string
  field: 'path' | 'glob'
  loc: string
  parser: string
  required: boolean
  role: 'output' | 'reference'
  on_multiple: 'first' | 'all' | 'error'
}
export type NodeAuthorCitation = {
  source_kind: 'knowledge' | 'card_doc' | 'tool'
  ref: string
  title?: string | null
  // Heuristic keyword-overlap for knowledge hits — NOT a calibrated probability. Null for card_doc/tool refs.
  score?: number | null
}
export type NodeProposal = {
  id: string
  advisory: true
  agent: string
  request: string
  matched: boolean
  tool?: string | null
  version?: string | null
  stage?: string | null
  inputs: NodePortSpec[]
  outputs: NodePortSpec[]
  locators: NodeLocatorSuggestion[]
  reserved_kinds: string[]
  summary: string
  rationale: string
  citations: NodeAuthorCitation[]
  generated_by: 'stub' | 'claude'
  model?: string | null
  disclaimer: string
  // Four version coordinates a proposal pins: the corpus it read, the record schema, and the
  // platform build that produced it (W2). The tool version is `version` above.
  corpus_version: string
  schema_version: number
  platform_version: string
  created_at: string
  mode: 'stub' | 'claude'
}

// Sandboxed server-side file browser (GET /api/files?root=&path=). Powers the Builder's "Browse…"
// data pickers over server-resident inputs (FASTQ folders, reference, panel) — the GB-scale files
// live on the compute host, so the browse is SERVER-SIDE and returns metadata only, never content.
// Off-gate, read-only; `kind` is an ext-inferred artifact kind (null when unrecognized).
export type FileKind = 'fastq' | 'vcf' | 'bam' | 'panel_bed' | 'reference_fasta'
export type FileEntry = {
  name: string
  is_dir: boolean
  size: number | null // bytes; files only (null for a directory)
  kind: FileKind | null
}
export type FileListing = {
  root: string
  path: string // dir path relative to the root ('' = the root itself)
  parent: string | null // parent dir rel path for an "up" link, or null at the root
  entries: FileEntry[]
}

// Advisory archivist digest (GET /api/archive/index cross-run | GET /api/runs/:id/archive-digest
// per-run). Organizational ONLY: there is deliberately NO verdict/decision/confidence field —
// the librarian indexes, the rules decide (ADR-0001). `manifest` is populated only for scope
// 'run'; a cross-run 'index' carries n_artifacts/total_size_bytes instead (manifest is []).
export type ArchiveArtifactRef = {
  name: string
  kind: string
  sha256: string | null
  size_bytes: number
  origin: string
}
export type ArchiveSignature = {
  signature: string
  rule_id: string
  title: string
  gate: Gate
  count: number
}
export type ArchiveCitation = {
  source_kind: 'run' | 'signature' | 'artifact'
  ref: string
  title: string | null
}
export type ArchiveDigest = {
  id: string
  advisory: true
  agent: string
  generated_by: 'stub' | 'claude'
  model: string | null
  scope: 'run' | 'index'
  run_ids: string[]
  n_runs: number
  n_samples: number
  n_attention: number
  verdict_counts: Record<string, number>
  by_origin: Record<string, number>
  by_status: Record<string, number>
  n_archive_ready: number
  archive_ready: boolean
  n_artifacts: number
  total_size_bytes: number
  recurring_signatures: ArchiveSignature[]
  manifest: ArchiveArtifactRef[]
  proposed_action: string
  summary: string
  citations: ArchiveCitation[]
  disclaimer: string
  digest_version: string
  schema_version: number
  created_at: string
  content_hash: string
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

// The processing gate a submit requests (ADR-0021). `immediate` fires the driver now; `hold`
// registers the run without firing (an operator releases it later via POST /api/runs/:id/release);
// `schedule` parks it against a `scheduled_at` timestamp (released manually — a time-based
// auto-release is a deferred backend seam).
export type ProcessingMode = 'immediate' | 'hold' | 'schedule'

// Submit → run execution (POST /api/runs). The endpoint TRIGGERS the pipeline driver (the core
// still never runs a tool). Only samples with reads on disk are processed; the rest are skipped.
// The backend model is `extra="forbid"` — only the fields below are accepted; send nothing else.
export type SubmitRunIn = {
  run_name: string
  study?: string
  assay?: string
  platform?: string
  samples: { sample: string; type?: string; i7?: string; i5?: string; study?: string }[]
  // Optional authored-pipeline name to run this run's samples through (resolved + compiled from its
  // APPROVED baseline via the same approval gate as POST /api/pipelines/run). Absent → the committed
  // germline-panel reference default. `pipeline_version` optionally pins an approved revision.
  pipeline?: string | null
  pipeline_version?: number | null
  // Processing gate. `scheduled_at` is an ISO-8601 timestamp, required when mode === 'schedule'.
  mode?: ProcessingMode
  scheduled_at?: string | null
}
export type SubmitRunAck = {
  run_id: string
  status: string
  processed_samples: string[]
  skipped_samples: string[]
}
// Per-sample job state for a (potentially multi-sample) submit — a processed sample tracks the
// run's lifecycle; a skipped sample (no reads on disk) is frozen at `skipped`.
export type SampleStatus = { sample: string; status: string }
// `held`/`scheduled` are the ADR-0021 parked states (registered but the driver hasn't fired — an
// operator releases them). `lost` is the restart-recovery terminal state: a job whose launching
// process died with no run dir on disk (api/job_store.TERMINAL_STATUSES = complete|failed|lost).
// The pydantic field is an open `str`; this mirrors the actual values the intake router emits.
export type IntakeStatus = {
  run_id: string
  status: 'queued' | 'held' | 'scheduled' | 'running' | 'complete' | 'failed' | 'lost'
  error?: string | null
  processed_samples: string[]
  skipped_samples: string[]
  samples?: SampleStatus[]
  // ADR-0021 processing-gate context (additive; an older persisted job yields the defaults).
  mode?: ProcessingMode | string
  scheduled_at?: string | null
  pipeline?: string | null
}
