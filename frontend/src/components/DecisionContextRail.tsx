import { FileText, GitBranch, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { CardHeader, Verdict } from '../types'

// The 288px context rail on a split decision card (dc 759-787): Sample / Run provenance, the
// narration source, and the two rail actions. Every value is honest — a field the intake never
// captured shows "not captured" (CLAUDE.md data-handling), never a fabricated stand-in. Fields
// the API contract does not carry (subject, reads, submitter) are shown as not-captured rather
// than invented.

const LABEL = 'text-[11px] font-semibold uppercase tracking-[0.5px] text-text-3'

function NotCaptured() {
  return <span className="text-text-3">not captured</span>
}

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-2.5">
      <span className="text-text-3">{k}</span>
      <span className="text-right text-text">{children}</span>
    </div>
  )
}

export function DecisionContextRail({
  runId,
  sampleId,
  verdict,
  header,
  platform,
  date,
}: {
  runId: string
  sampleId: string
  verdict: Verdict
  header: CardHeader | null
  platform: string | null
  date: string | null
}) {
  const actionable = verdict !== 'proceed'
  const generatedBy = header?.generated_by ?? 'stub'
  return (
    <div className="w-[288px] shrink-0 border-l border-line bg-card-2 px-[18px] py-[17px]">
      <div className={LABEL}>Sample</div>
      <div className="mt-2 flex flex-col gap-1.5 text-[12px]">
        <Row k="Subject">
          <NotCaptured />
        </Row>
        <Row k="Type">{header?.sample_type ?? <NotCaptured />}</Row>
        <Row k="Library">{header?.library_prep ?? <NotCaptured />}</Row>
        <Row k="Origin">
          {header?.origin ? <span className="font-mono">{header.origin}</span> : <NotCaptured />}
        </Row>
      </div>

      <div className={`mt-4 ${LABEL}`}>Run</div>
      <div className="mt-2 flex flex-col gap-1.5 text-[12px]">
        <Row k="Run">
          <span className="font-mono">{runId}</span>
        </Row>
        <Row k="Instrument">{platform ?? <NotCaptured />}</Row>
        <Row k="Date">{date ?? <NotCaptured />}</Row>
      </div>

      <div className={`mt-4 ${LABEL}`}>Narration</div>
      <div className="mt-[7px] flex items-center gap-[7px] text-[12px] text-text-2">
        <FileText size={13} className="text-text-3" />
        Rule-derived · {generatedBy}
      </div>

      <div className="mt-3.5 flex flex-col gap-2">
        <Link
          to={`/runs/${runId}/provenance`}
          className="flex w-full items-center justify-center gap-[7px] rounded-lg border border-line-strong bg-card px-2 py-2 text-[12.5px] font-medium text-text transition-colors hover:border-text-3"
        >
          <GitBranch size={14} /> View lineage
        </Link>
        {actionable && (
          <Link
            to={`/runs/${runId}/agent?sample=${encodeURIComponent(sampleId)}`}
            className="flex w-full items-center justify-center gap-[7px] rounded-lg bg-accent px-2 py-2 text-[12.5px] font-medium text-white transition-opacity hover:opacity-90"
          >
            <Sparkles size={14} /> Ask agent to triage
          </Link>
        )}
      </div>
    </div>
  )
}
