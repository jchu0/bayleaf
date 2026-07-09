// Shared loading / error / empty states (design principle: clear states everywhere).

import { RotateCw } from 'lucide-react'

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <p className="animate-pulse text-[13px] text-text-3">{label}</p>
}

// A single shimmer placeholder block. Reuses the existing `animate-pulse` idiom so
// skeletons read as the same "content is loading" language as <Loading>. Size it with
// height/width utilities passed via `className`.
export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-card-3 ${className}`} />
}

// Error surface. Pass `onRetry` to offer an in-place re-fetch (the caller owns the
// refetch handler); omitted → no button, so existing single-arg callers are unchanged.
export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="max-w-xl rounded-xl border border-escalate-bd bg-escalate-bg p-4 text-[13px] text-escalate-fg">
      <p>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-escalate-bd bg-card px-3 py-1 text-[12px] font-medium text-escalate-fg transition-colors hover:border-escalate-fg"
        >
          <RotateCw size={13} /> Retry
        </button>
      )}
    </div>
  )
}

export function Empty({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line-strong bg-card px-4 py-8 text-center text-[13px] text-text-3">
      {message}
    </div>
  )
}
