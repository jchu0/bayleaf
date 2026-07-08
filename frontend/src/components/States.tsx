// Shared loading / error / empty states (design principle: clear states everywhere).

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <p className="animate-pulse text-ink-dim">{label}</p>
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="max-w-3xl rounded-lg border border-escalate/50 bg-escalate/10 p-4 text-sm text-escalate">
      {message}
    </div>
  )
}

export function Empty({ message }: { message: string }) {
  return <p className="text-ink-dim">{message}</p>
}
