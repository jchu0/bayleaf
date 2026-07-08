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
