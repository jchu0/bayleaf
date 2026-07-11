// Pure, React-free helpers for the Provenance surface (PV1) — mirrors verdict.ts's role: a
// single place for the vocabulary + read-model logic the provenance views share. Everything
// here is derived ONLY from what the ledger actually emits (engine.py:90-171) — five event
// types, real payload keys — and reads the untyped `payload` (Record<string, unknown>)
// DEFENSIVELY, so an older/malformed event degrades to the generic renderer instead of crashing
// (the same "missing field is a signal, not a crash" tolerance the backend applies). The screen
// is 100% read-only: nothing here sets a verdict or confidence — verdicts are quoted verbatim
// from the events the rule engine authored (ADR-0001).

import { type LucideIcon, CheckCheck, FileText, Flag, Gavel, Play, ShieldCheck } from 'lucide-react'
import type { DecisionCard, Finding, Gate, PipelineStage, ProvenanceEvent, RunArtifact, Severity, Verdict } from './types'
import { VERDICT_LABEL } from './verdict'

// ── event vocabulary ─────────────────────────────────────────────────────────
// The five types run_gate actually emits, plus a generic fallback for anything else the enum
// could theoretically carry (RUN_REGISTERED, notification.emitted, …) but this API path never
// does — rendered verbatim, never faked into a promised row.
export type KnownEventType =
  | 'analysis_run.started'
  | 'sample.registered'
  | 'finding.emitted'
  | 'verdict.decided'
  | 'analysis_run.completed'

// Chip treatment uses ONLY existing theme tokens (no hex). `finding.emitted` / `verdict.decided`
// carry a neutral fallback here but are recolored per-row by severity / verdict at render time.
export const EVENT_META: Record<string, { label: string; icon: LucideIcon; chip: string }> = {
  'analysis_run.started': { label: 'Run started', icon: Play, chip: 'bg-card-2 border-line text-text-2' },
  'sample.registered': { label: 'Sample', icon: FileText, chip: 'bg-accent-weak border-line text-accent-strong' },
  'finding.emitted': { label: 'Finding', icon: Flag, chip: 'bg-card-2 border-line text-text-2' },
  'verdict.decided': { label: 'Verdict', icon: Gavel, chip: 'bg-card-2 border-line text-text-2' },
  'analysis_run.completed': { label: 'Run completed', icon: CheckCheck, chip: 'bg-card-2 border-line text-text-2' },
  // A de-identified share/report egress left the boundary (ADR-0018 D3) — an audited data-out,
  // not a decision; recolored neutral (the shield reads "guarded egress," not "verdict").
  'data.exported': { label: 'Data shared', icon: ShieldCheck, chip: 'bg-accent-weak border-line text-accent-strong' },
}

// ── defensive payload readers ────────────────────────────────────────────────
// The payload is Record<string, unknown> (types.ts:96) — narrow every key, never assume shape.
export function readStr(p: Record<string, unknown>, key: string): string | null {
  const v = p[key]
  return typeof v === 'string' ? v : null
}
export function readNum(p: Record<string, unknown>, key: string): number | null {
  const v = p[key]
  return typeof v === 'number' ? v : null
}

const VERDICTS = new Set<Verdict>(['proceed', 'hold', 'rerun', 'escalate'])
const SEVERITIES = new Set<Severity>(['info', 'warn', 'critical'])
export function readVerdict(p: Record<string, unknown>): Verdict | null {
  const v = p['verdict']
  return typeof v === 'string' && VERDICTS.has(v as Verdict) ? (v as Verdict) : null
}
export function readSeverity(p: Record<string, unknown>): Severity | null {
  const s = p['severity']
  return typeof s === 'string' && SEVERITIES.has(s as Severity) ? (s as Severity) : null
}

// The `analysis_run.started` payload nests the gate provenance (rule pack + runbook metrics).
export function readGateProvenance(p: Record<string, unknown>): {
  rule_pack_version: string | null
  runbook_metrics: string[]
} {
  const gp = p['gate_provenance']
  if (gp && typeof gp === 'object') {
    const o = gp as Record<string, unknown>
    const rpv = typeof o.rule_pack_version === 'string' ? o.rule_pack_version : null
    const rm = Array.isArray(o.runbook_metrics) ? o.runbook_metrics.filter((x): x is string => typeof x === 'string') : []
    return { rule_pack_version: rpv, runbook_metrics: rm }
  }
  return { rule_pack_version: null, runbook_metrics: [] }
}

// A human one-liner for an event, derived ONLY from real payload keys (§1 of the spec). Never
// invents a metric; an unrecognized type falls through to its verbatim wire value.
export function summarizeEvent(e: ProvenanceEvent): string {
  const p = e.payload ?? {}
  switch (e.event_type) {
    case 'analysis_run.started': {
      const gp = readGateProvenance(p)
      const rpv = gp.rule_pack_version ?? 'unknown'
      const gen = readStr(p, 'generated_by') ?? 'unknown'
      return `Gate run started · rule pack ${rpv} · ${gp.runbook_metrics.length} runbook metrics · narration ${gen}`
    }
    case 'sample.registered':
      return `Sample ${e.sample_id ?? '—'} registered`
    case 'finding.emitted': {
      const sev = readSeverity(p) ?? 'info'
      const rule = readStr(p, 'rule_id') ?? 'rule'
      const gate = readStr(p, 'gate') ?? '—'
      return `${sev} finding · ${rule} · ${gate} gate`
    }
    case 'verdict.decided': {
      const v = readVerdict(p)
      const label = v ? VERDICT_LABEL[v] : (readStr(p, 'verdict') ?? 'unknown')
      return `Verdict ${label} decided for ${e.sample_id ?? '—'}`
    }
    case 'analysis_run.completed': {
      const n = readNum(p, 'n_samples')
      const status = readStr(p, 'status') ?? 'unknown'
      return `Gate run completed · ${n ?? '—'} samples · ${status}`
    }
    case 'data.exported': {
      const n = readNum(p, 'n_rows')
      const policy = readStr(p, 'policy_id') ?? 'unknown'
      const origin = readStr(p, 'origin') ?? 'unknown'
      // Names the scrub as a version, never a compliance claim (the disclaimer rides the payload).
      return `De-identified share · ${n ?? '—'} rows · ${policy} scrub · origin ${origin}`
    }
    default:
      return e.event_type
  }
}

// Whether an event matches a free-text query (id / rule_id / signature / sample / summary).
export function eventMatches(e: ProvenanceEvent, q: string): boolean {
  const needle = q.trim().toLowerCase()
  if (!needle) return true
  const p = e.payload ?? {}
  const hay = [
    e.id,
    e.event_type,
    e.sample_id ?? '',
    readStr(p, 'rule_id') ?? '',
    readStr(p, 'signature') ?? '',
    summarizeEvent(e),
  ]
    .join(' ')
    .toLowerCase()
  return hay.includes(needle)
}

// ── origin vocabulary ────────────────────────────────────────────────────────
// origin is a PROVENANCE fact, not a quality verdict — real-giab is deliberately NOT colored
// "good/green"; the tooltip carries the meaning and the chip stays near-neutral (guardrail:
// never imply quality/pathogenicity where the data only tags where it came from). An unknown
// tag is surfaced verbatim, never laundered into a known one.
export const ORIGIN_META: Record<string, { label: string; chip: string; tip: string }> = {
  'real-giab': { label: 'real-giab', chip: 'border-line bg-card-2 text-text-2', tip: 'Real GIAB truth data' },
  synthetic: { label: 'synthetic', chip: 'border-line bg-accent-weak text-accent-strong', tip: 'Synthetic (generated) data' },
  contrived: { label: 'contrived', chip: 'border-hold-bd bg-hold-bg text-hold-fg', tip: 'Contrived demo fixture — not real data' },
}
export function originMeta(origin: string): { label: string; chip: string; tip: string } {
  return ORIGIN_META[origin] ?? { label: origin, chip: 'border-line bg-card-2 text-text-3', tip: `origin: ${origin}` }
}

// ── stage vocabulary (shared with Lineage) ───────────────────────────────────
export const STAGE_LABEL: Record<PipelineStage, string> = {
  intake: 'Intake',
  demux: 'Demux',
  qc: 'QC',
  align: 'Align',
  variant: 'Variant',
  gate: 'Gate',
}
// Which pipeline stages sit under a gate checkpoint (drives the gate dot on an artifact edge).
export const STAGE_GATE: Partial<Record<PipelineStage, Gate>> = { demux: 'preflight', qc: 'qc', variant: 'variant' }

// The two intake sheets look alike but are different files at different stages — surface the
// distinction on hover (shared by Lineage's ProvArtifactRow and the artifact index).
export function artifactNameTitle(name: string): string {
  const lower = name.toLowerCase()
  if (lower === 'sample_metadata.csv') return 'Intake · LIMS/subject metadata sheet — click to view'
  if (lower === 'samplesheet.csv') return 'Demux · Illumina barcode/index manifest — click to view'
  return 'Open artifact at its location (view)'
}

// ── formatting ───────────────────────────────────────────────────────────────
export function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(1)} GB`
}

// Localized timestamp for the event trail / header pins; a malformed ISO string falls back to
// its raw value rather than "Invalid Date".
export function fmtTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'medium' })
}

// A payload value rendered for the generic k/v expander (objects/arrays as compact JSON).
export function fmtPayloadValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

// ── code / stderr payload classification (event trail, UIC-9) ─────────────────
// A payload value is rendered as a copyable CODE BLOCK — not a compact k/v cell — when it is a
// command line, an error/stderr dump, or a structured object/array. This keeps an execution-trace
// `.command.err` payload (or the nested gate_provenance JSON) readable and copyable instead of
// crammed onto one line. Pure classification over the untyped payload — renders verbatim, never
// invents a field the event didn't carry (the same defensive posture as the readers above).
const CODE_KEYS = new Set([
  'command',
  'cmd',
  'command_line',
  'commandline',
  'script',
  'stderr',
  'stdout',
  'error',
  'err',
  'traceback',
  'stack',
  'stacktrace',
  'log',
  'logs',
  'output',
])
export function isCodeValue(key: string, v: unknown): boolean {
  if (v !== null && typeof v === 'object') return true // structured payload → pretty JSON block
  if (typeof v === 'string' && v.includes('\n')) return true // multi-line = a log/stderr dump
  return CODE_KEYS.has(key.toLowerCase()) // a command / error stream, even single-line
}
export function stringifyCode(v: unknown): string {
  if (typeof v === 'string') return v
  if (v === null || v === undefined) return ''
  return JSON.stringify(v, null, 2)
}

// ── trace-back index maps (built once from cards) ────────────────────────────
export function indexFindings(cards: DecisionCard[]): Map<string, { finding: Finding; sampleId: string }> {
  const m = new Map<string, { finding: Finding; sampleId: string }>()
  for (const c of cards) for (const f of c.findings) m.set(f.id, { finding: f, sampleId: c.sample_id })
  return m
}
export function indexCards(cards: DecisionCard[]): Map<string, DecisionCard> {
  const m = new Map<string, DecisionCard>()
  for (const c of cards) m.set(c.sample_id, c)
  return m
}

// ── artifact grouping ────────────────────────────────────────────────────────
// The artifacts endpoint emits one RunArtifact row per (stage, role) EDGE (api/main.py:582-593),
// so a file consumed downstream appears twice (e.g. demux_stats.csv as demux·output + qc·input).
// Group by name so "which stages produced/consumed it" is one row with edge chips.
export type ArtifactEdge = { stage: PipelineStage; role: string }
export type ArtifactGroup = {
  name: string
  edges: ArtifactEdge[]
  sha256: string | null
  size_bytes: number
  origin: string
  url: string
}
export function groupArtifacts(artifacts: RunArtifact[]): ArtifactGroup[] {
  const m = new Map<string, ArtifactGroup>()
  for (const a of artifacts) {
    const g = m.get(a.name)
    if (g) {
      g.edges.push({ stage: a.stage, role: a.role })
      // The file's fixity/size/origin are identical across its edges; keep the first non-null.
      if (g.sha256 == null && a.sha256 != null) g.sha256 = a.sha256
    } else {
      m.set(a.name, {
        name: a.name,
        edges: [{ stage: a.stage, role: a.role }],
        sha256: a.sha256,
        size_bytes: a.size_bytes,
        origin: a.origin,
        url: a.url,
      })
    }
  }
  return [...m.values()]
}

// De-dupe preserving first-seen order (filter-option derivation — only what's present, no dead
// options at scale).
export function distinct<T>(xs: T[]): T[] {
  return [...new Set(xs)]
}
