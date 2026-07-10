import { CheckCircle2, Loader2, RotateCcw } from 'lucide-react'
import { Skeleton } from './States'

// Decision-card screen states that don't fit the shared States.tsx (frozen): the sequencing
// skeleton, the released panel, and the synthesis-error banner. Kept in a screen-owned file so
// their bespoke colour/copy lives with the Decision screen.

// A run still sequencing (summary.status === 'running') — the gate hasn't produced final cards
// yet. Also the initial fetch placeholder.
export function DecisionLoading() {
  return (
    <div className="mt-[22px] flex flex-col gap-3">
      <div className="flex items-center gap-2.5 text-[13px] text-text-2">
        <Loader2 size={15} className="animate-spin text-info" />
        Sequencing in progress — decision gate runs once artifacts land.
      </div>
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-16 rounded-[13px]" />
      ))}
    </div>
  )
}

// A released run: all samples cleared and were released downstream — nothing to review.
export function DecisionReleased({ count }: { count: number }) {
  return (
    <div className="mt-[22px] flex flex-col items-center gap-2.5 rounded-[14px] border border-proceed-bd bg-proceed-bg p-9 text-center">
      <div className="grid h-[46px] w-[46px] place-items-center rounded-[12px] border border-proceed-bd bg-white">
        <CheckCircle2 size={24} strokeWidth={1.9} className="text-proceed" />
      </div>
      <div className="text-[16px] font-semibold text-proceed-fg">Run released</div>
      <div className="max-w-[400px] text-[13px] text-text-2">
        All {count} samples cleared the gate and were released to downstream analysis. Nothing to review.
      </div>
    </div>
  )
}

// Narration failed but the rule engine still produced findings — the verdicts below are
// rule-derived and safe to act on (ADR-0001: rules decide, AI narrates). The cards MUST still
// render below this banner; this component only explains why the prose is thin.
export function DecisionSynthesisError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="mt-[22px] rounded-[14px] border border-escalate-bd bg-escalate-bg p-[30px] text-center">
      <div className="text-[16px] font-semibold text-escalate-fg">Synthesis failed for this run</div>
      <div className="mx-auto mt-1.5 max-w-[440px] text-[13px] text-text-2">
        The rule engine produced findings, but narration could not be generated. Verdicts below are
        rule-derived and safe to act on.
      </div>
      <button
        onClick={onRetry}
        className="mt-3.5 inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3.5 py-2 text-[13px] font-medium text-text transition-colors hover:border-text-3"
      >
        <RotateCcw size={14} /> Re-run synthesis
      </button>
    </div>
  )
}
