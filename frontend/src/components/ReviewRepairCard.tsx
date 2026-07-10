import { Check, Loader2, Lock, Sparkles } from 'lucide-react'
import type { AgentProposal } from '../types'

export type RepairApproval = 'none' | 'instance' | 'class'

// Honest fallback used only when the advisory pipeline-repair agent can't be reached (off-gate,
// non-critical). We do NOT fabricate a class-specific fix for an unknown signature — the card
// simply states the agent is unavailable; the recurring pattern and the gate are unaffected.
const FALLBACK_SUMMARY =
  'The pipeline-repair agent is unavailable, so no proposed fix can be shown for this signature. The recurring pattern is unchanged and the gate is unaffected.'

// The pipeline-repair agent's proposed fix, surfaced inline on a recurring ticket after the
// reviewer escalates the signature (`api.signatureRepair`). Strictly ADVISORY: the two approve
// scopes (see-one/fix-one vs. class-wide) are approver-gated in the UI — a reviewer sees locked
// buttons, an approver sees live ones. Approving records intent locally; it never sets a verdict.
export function ReviewRepairCard({
  proposal,
  loading,
  approved,
  isApprover,
  onApprove,
}: {
  proposal: AgentProposal | null
  loading: boolean
  approved: RepairApproval
  isApprover: boolean
  onApprove: (scope: 'instance' | 'class') => void
}) {
  const summary = proposal?.summary ?? FALLBACK_SUMMARY

  return (
    <div className="mt-2.5 overflow-hidden rounded-[10px] border border-line">
      <div className="flex items-center gap-2 bg-accent-weak px-3 py-2.5">
        <Sparkles size={15} className="shrink-0 text-accent" />
        <span className="text-[12px] font-semibold text-accent-strong">Pipeline-repair agent · proposed fix</span>
        <span className="ml-auto text-[9.5px] font-semibold uppercase tracking-[0.4px] text-accent-strong">
          Advisory
        </span>
      </div>
      <div className="px-[13px] py-[11px]">
        {loading ? (
          <p className="inline-flex items-center gap-1.5 text-[12.5px] text-text-3">
            <Loader2 size={13} className="animate-spin" /> Asking the pipeline-repair agent…
          </p>
        ) : (
          <p className="text-[12.5px] leading-relaxed text-text-2">{summary}</p>
        )}

        {approved !== 'none' ? (
          <div className="mt-2.5 inline-flex items-center gap-1.5 rounded-full border border-proceed-bd bg-proceed-bg px-3 py-1 text-[11.5px] font-medium text-proceed-fg">
            <Check size={13} />
            Fix approved · {approved === 'instance' ? 'this instance' : 'issue class'}
          </div>
        ) : (
          <div className="mt-2.5 flex flex-wrap items-center gap-[9px]">
            <ApproveButton scope="instance" label="Approve fix · this instance" locked={!isApprover} onApprove={onApprove} />
            <ApproveButton scope="class" label="Approve fix · issue class" locked={!isApprover} onApprove={onApprove} />
            <span className="text-[11px] text-text-3">
              Approver sign-off required (see-one / fix-one or class-wide)
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

function ApproveButton({
  scope,
  label,
  locked,
  onApprove,
}: {
  scope: 'instance' | 'class'
  label: string
  locked: boolean
  onApprove: (scope: 'instance' | 'class') => void
}) {
  if (locked) {
    // A reviewer can see the proposal but not approve it — the affordance stays visible but
    // inert, spelling out the missing capability rather than hiding the action.
    return (
      <span
        className="inline-flex cursor-default items-center gap-1.5 rounded-lg border border-line bg-card-2 px-2.5 py-1.5 text-[11.5px] text-text-3"
        title="Approver sign-off required."
      >
        <Lock size={12} />
        {label}
      </span>
    )
  }
  return (
    <button
      type="button"
      onClick={() => onApprove(scope)}
      className="inline-flex items-center gap-1.5 rounded-lg border border-accent bg-accent-weak px-2.5 py-1.5 text-[11.5px] font-medium text-accent-strong transition-colors hover:bg-accent hover:text-white"
    >
      <Check size={12} />
      {label}
    </button>
  )
}
