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

export type RunSummary = {
  run_id: string
  n_samples: number
  n_attention: number
  counts: Record<string, number>
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
