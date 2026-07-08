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
  gate_results: GateResult[]
  content_hash: string
}

export type ProvenanceEvent = {
  id: string
  event_type: string
  analysis_run_id: string | null
  run_id: string | null
  sample_id: string | null
  actor: string
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
