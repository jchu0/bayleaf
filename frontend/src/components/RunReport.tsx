import { type ReactNode, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, GitBranch, Info, ShieldAlert, Stethoscope } from 'lucide-react'
import type { DecisionCard, Evidence, Finding, RunDetail, Verdict } from '../types'
import { CitedEvidence } from './EvidenceTable'
import { GateResultStrip } from './GateResultStrip'
import { VerdictBadge } from './VerdictBadge'
import { DecisionVerdictBar } from './DecisionVerdictBar'
import { Pager, type PerPage } from './Pager'
import { Truncate } from './Truncate'
import { fmtTime, readGateProvenance, readNum, readStr } from '../provenance'

// The per-run "QC Decision & Provenance Report" (ADR-0018 §1.8 / D1, W3). A READ/SUMMARY surface
// only — it renders what the run ALREADY produced and terminates the E2E in one signed-off-shaped
// document. It NEVER sets or annotates a verdict/confidence: every verdict here is quoted verbatim
// from the rule engine's cards (ADR-0001, G1), and every ClinVar significance is quoted VERBATIM
// from the finding's cited evidence (G3/G4) — PipeGuard authors no pathogenicity. The report has
// no write path; human sign-off is a labelled seam, not a button (ADR-0018 L61: PipeGuard can
// never mark a report final on its own). Built entirely over `detail` (cards + events) already on
// the wire — no new endpoint, no VariantCall transport, no interpretation agent for v1.

const ORDER: Record<Verdict, number> = { escalate: 0, rerun: 1, hold: 2, proceed: 3 }

// A route-to-human finding carries the ClinVar significance verbatim in a CLNSIG evidence row.
function clnsigOf(f: Finding): Evidence | null {
  return f.evidence.find((e) => e.source_field === 'CLNSIG') ?? null
}
function isRouteToHuman(f: Finding): boolean {
  return f.rule_id === 'VAR-RTH-001' || clnsigOf(f) != null
}

type RthHit = { sampleId: string; verdict: Verdict; finding: Finding; clnsig: Evidence; candidate: Evidence | null }

export function RunReport({ detail }: { detail: RunDetail }) {
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState<PerPage>('25')

  const cards = useMemo(
    () => [...detail.cards].sort((a, b) => ORDER[a.verdict] - ORDER[b.verdict] || a.sample_id.localeCompare(b.sample_id)),
    [detail],
  )

  // Every route-to-human hit across the run: the sample, its verdict, the verbatim ClinVar row,
  // and the annotated candidate row. The rules already decided ESCALATE — the report only surfaces
  // the cited evidence they stood on.
  const rthHits: RthHit[] = useMemo(() => {
    const out: RthHit[] = []
    for (const c of detail.cards) {
      for (const f of c.findings) {
        const clnsig = clnsigOf(f)
        if (!isRouteToHuman(f) || !clnsig) continue
        const candidate = f.evidence.find((e) => e !== clnsig) ?? null
        out.push({ sampleId: c.sample_id, verdict: c.verdict, finding: f, clnsig, candidate })
      }
    }
    return out
  }, [detail])

  // Run-execution provenance, read straight from the append-only ledger events (never faked).
  const started = detail.events.find((e) => e.event_type === 'analysis_run.started')
  const completed = detail.events.find((e) => e.event_type === 'analysis_run.completed')
  const gp = started ? readGateProvenance(started.payload) : { rule_pack_version: null, runbook_metrics: [] }
  const narration = started ? (readStr(started.payload, 'generated_by') ?? 'unknown') : 'unknown'
  const nSamples = completed ? readNum(completed.payload, 'n_samples') : null
  const runStatus = completed ? readStr(completed.payload, 'status') : null

  const per = Number(perPage)
  const pageCount = Math.max(1, Math.ceil(cards.length / per))
  const curPage = Math.min(page, pageCount)
  const pageCards = cards.slice((curPage - 1) * per, curPage * per)

  return (
    <div className="flex flex-col gap-4">
      {/* Report title band + honesty disclaimer */}
      <section className="overflow-hidden rounded-[14px] border border-line bg-card">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.6px] text-text-3">
              <Stethoscope size={13} strokeWidth={2} className="text-accent" />
              QC decision &amp; provenance report
            </div>
            <div className="mt-1 font-mono text-[15px] font-semibold text-text">{detail.run_id}</div>
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-[12px] text-text-2">
            <Field label="Samples">{detail.summary.n_samples}</Field>
            <Field label="Platform">{detail.summary.platform ?? '—'}</Field>
            <Field label="Run date">{detail.summary.run_date ?? '—'}</Field>
            <Field label="Generated">
              {completed ? fmtTime(completed.created_at) : started ? fmtTime(started.created_at) : '—'}
            </Field>
          </div>
        </div>
        <div className="flex items-start gap-2.5 bg-card-2 px-5 py-3 text-[12px] leading-[1.5] text-text-2">
          <Info size={15} strokeWidth={2} className="mt-px shrink-0 text-text-3" />
          <span>
            Research/demo QC decision gate — <strong>not a clinical decision system</strong> and not a diagnostic report.
            The rules decide every verdict; any ClinVar classification below is <strong>quoted verbatim</strong> from the
            cited source — PipeGuard authors no pathogenicity of its own. This report is <strong>not final</strong> until a
            qualified human signs off (ADR-0018).
          </span>
        </div>
      </section>

      {/* Verdict mix at a glance */}
      <DecisionVerdictBar counts={detail.summary.counts} />

      {detail.summary.n_attention > 0 && (
        <div className="flex items-center gap-3 rounded-[12px] border border-hold-bd bg-hold-bg px-4 py-3">
          <AlertTriangle size={18} strokeWidth={2} className="shrink-0 text-hold" />
          <div className="flex-1 text-[13px] text-hold-fg">
            <b>{detail.summary.n_attention} sample(s) need operator attention</b> before this run can be released.
          </div>
          <Link
            to="/queue"
            className="whitespace-nowrap rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-text-3"
          >
            Open review queue
          </Link>
        </div>
      )}

      {/* Route-to-human — the clinically-significant hero of the report. Rules decided ESCALATE;
          the report surfaces the verbatim ClinVar citation they stood on. */}
      <section>
        <SectionTitle icon={<ShieldAlert size={14} strokeWidth={2} className="text-escalate" />}>
          Clinically significant variants · routed to human review
        </SectionTitle>
        {rthHits.length === 0 ? (
          <div className="mt-2.5 flex items-center gap-2.5 rounded-[12px] border border-line bg-card px-4 py-3.5 text-[12.5px] text-text-2">
            <CheckCircle2 size={16} strokeWidth={2} className="shrink-0 text-text-3" />
            No variants were routed to human review in this run. Route-to-human (VAR-RTH-001) is off by default; it fires
            only when the runbook arms a ClinVar significance for the run.
          </div>
        ) : (
          <div className="mt-2.5 flex flex-col gap-2.5">
            {rthHits.map((h) => (
              <RouteToHumanCard key={`${h.sampleId}:${h.finding.id}`} hit={h} />
            ))}
          </div>
        )}
      </section>

      {/* Per-sample decision detail — gate outcomes + cited evidence + advisory next steps. */}
      <section>
        <SectionTitle icon={<GitBranch size={14} strokeWidth={2} className="text-accent" />}>
          Per-sample decisions ({cards.length})
        </SectionTitle>
        <div className="mt-2.5 flex flex-col gap-3">
          {pageCards.map((c) => (
            <SampleReport key={c.sample_id} card={c} />
          ))}
        </div>
        <Pager
          total={cards.length}
          page={curPage}
          perPage={perPage}
          onPage={setPage}
          onPerPage={(p) => {
            setPerPage(p)
            setPage(1)
          }}
          noun="samples"
        />
      </section>

      {/* Provenance pins + the human-sign-off seam (read-only). */}
      <section className="rounded-[14px] border border-line bg-card px-5 py-4">
        <SectionTitle icon={<Info size={14} strokeWidth={2} className="text-text-3" />}>Provenance &amp; sign-off</SectionTitle>
        <div className="mt-3 flex flex-wrap gap-x-8 gap-y-3">
          <Pin label="Rule pack">{gp.rule_pack_version ?? '—'}</Pin>
          <Pin label="Runbook metrics">{gp.runbook_metrics.length}</Pin>
          <Pin label="Narration">{narration}</Pin>
          <Pin label="Samples">
            {nSamples ?? detail.summary.n_samples}
            {runStatus ? ` · ${runStatus}` : ''}
          </Pin>
          <Pin label="Events">{detail.events.length}</Pin>
          <Pin label="Started">{started ? fmtTime(started.created_at) : '—'}</Pin>
          <Pin label="Completed">{completed ? fmtTime(completed.created_at) : '—'}</Pin>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-line bg-card-2 px-4 py-3">
          <div className="flex items-start gap-2.5 text-[12.5px] leading-[1.5] text-text-2">
            <Stethoscope size={15} strokeWidth={2} className="mt-px shrink-0 text-text-3" />
            <span>
              <b className="text-text">Human sign-off required.</b> PipeGuard can never mark a report final on its own
              (ADR-0018) — a qualified reviewer adjudicates via the review queue. Sign-off is not wired in this build.
            </span>
          </div>
          <Link
            to={`/runs/${detail.run_id}/provenance`}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-text-3"
          >
            <GitBranch size={14} /> Full lineage &amp; event trail
          </Link>
        </div>
      </section>
    </div>
  )
}

// One route-to-human hit — the ClinVar classification quoted VERBATIM, the annotated candidate, the
// citation, and the routing action. The big quoted string is the cited source value, unmodified.
function RouteToHumanCard({ hit }: { hit: RthHit }) {
  const { clnsig, candidate, finding } = hit
  const reviewStatus = clnsig.threshold // the finding packs "review status: …" here
  const citation = clnsig.source // e.g. "ClinVar 2026-01"
  const accession = clnsig.locator // e.g. VCV000017661
  return (
    <div className="overflow-hidden rounded-[12px] border border-escalate-bd bg-escalate-bg">
      <div className="flex flex-wrap items-center gap-2.5 border-b border-escalate-bd px-4 py-3">
        <VerdictBadge verdict={hit.verdict} />
        <span className="font-mono text-[14px] font-semibold text-text">{hit.sampleId}</span>
        <span className="text-[12.5px] text-text-2">Routed to mandatory human review</span>
        <span className="ml-auto rounded-[5px] border border-line bg-card px-1.5 py-px font-mono text-[10.5px] font-medium text-text-2">
          {finding.rule_id}
        </span>
      </div>
      <div className="grid gap-3 px-4 py-3.5 sm:grid-cols-[1.2fr_1fr]">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.5px] text-text-3">
            ClinVar significance · quoted verbatim
          </div>
          {/* VERBATIM — the cited source's value, rendered unmodified (G3/G4). */}
          <div className="mt-1.5 font-mono text-[15px] font-semibold text-escalate-fg">“{clnsig.value ?? '—'}”</div>
          {candidate?.value && <div className="mt-1 text-[12.5px] text-text-2">{candidate.value}</div>}
        </div>
        <div className="text-[11.5px] leading-[1.6] text-text-2">
          <div>
            <span className="text-text-3">Source</span>{' '}
            <span className="font-mono text-accent-strong">{citation}</span>
          </div>
          {accession && (
            <div>
              <span className="text-text-3">Accession</span> <span className="font-mono">{accession}</span>
            </div>
          )}
          {reviewStatus && (
            <div>
              <span className="text-text-3">ClinVar</span> <span className="font-mono">{reviewStatus}</span>
            </div>
          )}
        </div>
      </div>
      <div className="border-t border-escalate-bd bg-card px-4 py-2.5 text-[11.5px] leading-[1.5] text-text-3">
        PipeGuard makes no pathogenicity determination of its own — the classification above is quoted verbatim from
        ClinVar and a qualified human adjudicates (ADR-0004).
      </div>
    </div>
  )
}

// One sample's report block: header · gate outcomes · cited evidence · advisory next steps.
function SampleReport({ card }: { card: DecisionCard }) {
  const clean = card.verdict === 'proceed'
  return (
    <div className="overflow-hidden rounded-[12px] border border-line bg-card">
      <div className="flex min-w-0 items-center gap-2.5 px-4 py-3">
        <VerdictBadge verdict={card.verdict} />
        <span className="shrink-0 font-mono text-[15px] font-semibold text-text">{card.sample_id}</span>
        <Truncate text={card.headline} className="min-w-0 flex-1 text-[13px] text-text-2" />
      </div>
      <GateResultStrip results={card.gate_results} cardVerdict={card.verdict} />
      <div className="px-4 py-3.5">
        {card.findings.length > 0 ? (
          <>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.5px] text-text-3">
              Supporting evidence · cited
            </div>
            <CitedEvidence findings={card.findings} variant="brief" />
          </>
        ) : clean ? (
          <div className="flex items-center gap-2.5 rounded-[10px] border border-proceed-bd bg-proceed-bg px-3.5 py-3 text-[12.5px] text-proceed-fg">
            <CheckCircle2 size={16} strokeWidth={2} className="shrink-0 text-proceed" />
            No provenance, metadata, or QC issues found — every runbook check passed with margin.
          </div>
        ) : null}
        {card.next_steps.length > 0 && (
          <div className="mt-3 rounded-[10px] border border-line bg-card-2 px-3.5 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.5px] text-text-3">
              Recommended next steps (advisory)
            </div>
            <ol className="mt-2 flex list-inside list-decimal flex-col gap-1 text-[12.5px] leading-[1.5] text-text-2">
              {card.next_steps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  )
}

function SectionTitle({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <h2 className="flex items-center gap-2 text-[13px] font-semibold text-text">
      {icon}
      {children}
    </h2>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="inline-flex flex-col">
      <span className="text-[9.5px] font-semibold uppercase tracking-[0.5px] text-text-3">{label}</span>
      <span className="font-mono text-[12px] text-text">{children}</span>
    </span>
  )
}

function Pin({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-[0.5px] text-text-3">{label}</div>
      <div className="font-mono text-[12px] text-text-2">{children}</div>
    </div>
  )
}
