// Shared loading / error / empty states (design principle: clear states everywhere).

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <p className="animate-pulse text-[13px] text-text-3">{label}</p>
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="max-w-xl rounded-xl border border-escalate-bd bg-escalate-bg p-4 text-[13px] text-escalate-fg">
      {message}
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
