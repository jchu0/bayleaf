import { Link } from 'react-router-dom'
import { FileText, Info, SquareCheckBig, Star } from 'lucide-react'
import type { DecisionCard, TriageCitation, TriageNote } from '../types'

// The static, source-derived label rendered as each citation's second line (dc.html 1140/1151).
// The TriageCitation contract (types.ts) carries only source_kind|ref|title|score — no free-text
// 'kind' — so we never fabricate a corpus label; we key a fixed human phrase off source_kind.
// Advisory only: this names where the evidence came from, never that the agent set a verdict.
const SOURCE_KIND_LABEL: Record<TriageCitation['source_kind'], string> = {
  finding: 'From this run findings',
  knowledge: 'Knowledge and experience',
}

// The advisory subject card for Agent triage (dc.html 1107-1164): who/what is being triaged,
// the model's likely-cause + suggested-action narration, its citations split into this run's
// findings vs. the knowledge corpus, and a footer that restates the invariant + links back to
// the Decision card. The verdict is never shown or set here — rules decide, this note advises.
export function AgentSubjectCard({
  runId,
  card,
  note,
  sourceLabel,
}: {
  runId: string
  card: DecisionCard
  note: TriageNote
  sourceLabel: string
}) {
  const findings = note.citations.filter((c) => c.source_kind === 'finding')
  const knowledge = note.citations.filter((c) => c.source_kind === 'knowledge')
  // The rule that this note addresses — from the note first, else the card's leading finding.
  const rule = note.addresses_rule_ids?.[0] ?? card.findings?.[0]?.rule_id ?? ''

  return (
    <div className="mt-4 overflow-hidden rounded-[14px] border border-line bg-card shadow-card">
      {/* subject header */}
      <div className="flex items-center gap-[11px] border-b border-line px-[18px] py-[15px]">
        <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[9px] bg-accent-weak">
          <Star size={18} strokeWidth={1.6} className="text-accent" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="rounded-[5px] bg-accent-weak px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.5px] text-accent-strong">
              Advisory
            </span>
            <span className="text-[11.5px] text-text-3">{sourceLabel}</span>
          </div>
          <div className="mt-[5px] text-[14px] font-semibold text-text">{card.headline}</div>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-mono text-[13px] font-semibold text-text">{card.sample_id}</div>
          <div className="font-mono text-[10.5px] text-text-3">
            {runId}
            {rule && ` · ${rule}`}
          </div>
        </div>
      </div>

      {/* likely cause */}
      <div className="border-b border-line px-[18px] py-[17px]">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.5px] text-text-3">
          <Info size={14} strokeWidth={2} className="text-info" />
          Likely cause
        </div>
        <p className="mt-2 text-[13.5px] leading-[1.6] text-text">{note.likely_cause}</p>
      </div>

      {/* suggested action */}
      <div className="border-b border-line px-[18px] py-[17px]">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.5px] text-text-3">
          <SquareCheckBig size={14} strokeWidth={2} className="text-accent" />
          Suggested action
        </div>
        <p className="mt-2 text-[13.5px] leading-[1.6] text-text">{note.suggested_action}</p>
      </div>

      {/* citations */}
      <div className="bg-card-2 px-[18px] py-[17px]">
        <div className="text-[11px] font-semibold uppercase tracking-[0.5px] text-text-3">Citations</div>
        <div className="mt-[11px] grid grid-cols-1 gap-[14px] sm:grid-cols-2">
          <div>
            <div className="mb-[7px] text-[12px] font-semibold text-text-2">From this run's findings</div>
            <div className="flex flex-col gap-[7px]">
              {findings.length === 0 ? (
                <p className="text-[12px] text-text-3">None cited.</p>
              ) : (
                findings.map((c) => <FindingCite key={c.ref} cite={c} runId={runId} />)
              )}
            </div>
          </div>
          <div>
            <div className="mb-[7px] text-[12px] font-semibold text-text-2">Knowledge &amp; experience</div>
            <div className="flex flex-col gap-[7px]">
              {knowledge.length === 0 ? (
                <p className="text-[12px] text-text-3">None cited.</p>
              ) : (
                knowledge.map((c) => <KnowledgeCite key={c.ref} cite={c} />)
              )}
            </div>
          </div>
        </div>
      </div>

      {/* footer — restates the invariant + returns to the Decision card */}
      <div className="flex items-center gap-[10px] border-t border-line px-[18px] py-[12px]">
        <span className="flex-1 text-[11.5px] leading-[1.4] text-text-3">
          The verdict is set by the rule engine, not this note. Reviewer judgment required before any action.
        </span>
        <Link
          to={`/runs/${runId}`}
          className="inline-flex shrink-0 items-center gap-[7px] rounded-[8px] border border-line-strong bg-card px-[13px] py-2 text-[12.5px] font-medium text-text"
        >
          Back to card
        </Link>
      </div>
    </div>
  )
}

// A cited finding from this run — a file-icon card whose mono ref links back to the run's
// Decision cards (where the finding lives).
function FindingCite({ cite, runId }: { cite: TriageCitation; runId: string }) {
  return (
    <Link
      to={`/runs/${runId}`}
      className="flex items-start gap-[9px] rounded-[9px] border border-line bg-card px-[11px] py-[9px] hover:opacity-80"
    >
      <FileText size={14} strokeWidth={1.8} className="mt-0.5 shrink-0 text-accent" />
      <div className="min-w-0">
        <div className="text-[12.5px] font-semibold text-text">{cite.title ?? cite.ref}</div>
        {cite.title && <div className="mt-0.5 font-mono text-[10.5px] text-text-3">{cite.ref}</div>}
        <div className="mt-0.5 text-[10.5px] text-text-3">{SOURCE_KIND_LABEL[cite.source_kind]}</div>
      </div>
    </Link>
  )
}

// A cited knowledge/experience entry — an id-chip card (KB-217 / INC-0042 / SOP-11). Two lines:
// the corpus title (when the contract carries one) over a static source-kind sub-label. The
// sub-label is derived, not invented — the contract has no free-text "kind", so we render a fixed
// "Knowledge and experience" rather than fabricating a corpus category.
function KnowledgeCite({ cite }: { cite: TriageCitation }) {
  return (
    <div className="flex items-start gap-[9px] rounded-[9px] border border-line bg-card px-[11px] py-[9px]">
      <span className="shrink-0 rounded-[5px] bg-accent-weak px-1.5 py-0.5 font-mono text-[10px] font-semibold text-accent-strong">
        {cite.ref}
      </span>
      <div className="min-w-0">
        {cite.title && (
          <div className="text-[12.5px] font-medium leading-[1.35] text-text">{cite.title}</div>
        )}
        <div className={`text-[10.5px] text-text-3${cite.title ? ' mt-0.5' : ''}`}>
          {SOURCE_KIND_LABEL[cite.source_kind]}
        </div>
      </div>
    </div>
  )
}
