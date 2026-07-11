import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

// A reusable, on-brand confirmation gate (replaces jarring window.confirm) enforcing the maintainer's
// standing rule: no single accidental click may trigger a cascading/state-changing write — the
// operator must deliberately confirm. `useConfirm()` returns an async confirm(opts) → Promise<boolean>
// so a call site reads `if (!(await confirm({...}))) return` before firing an audited action.
type Tone = 'default' | 'danger'
export type ConfirmOpts = {
  title: string
  body?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  tone?: Tone
}
type Ctx = { confirm: (opts: ConfirmOpts) => Promise<boolean> }

const ConfirmContext = createContext<Ctx | null>(null)

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [opts, setOpts] = useState<ConfirmOpts | null>(null)
  const resolver = useRef<((v: boolean) => void) | null>(null)

  const confirm = useCallback((o: ConfirmOpts) => {
    setOpts(o)
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve
    })
  }, [])

  const close = useCallback((v: boolean) => {
    resolver.current?.(v)
    resolver.current = null
    setOpts(null)
  }, [])

  // Escape cancels — a deliberate dismissal, never an accidental confirm.
  useEffect(() => {
    if (!opts) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [opts, close])

  const danger = opts?.tone === 'danger'

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      {opts && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-[rgba(16,24,40,.4)] p-6"
          onClick={() => close(false)}
        >
          <div
            className="w-[420px] max-w-full overflow-hidden rounded-2xl border border-line-strong bg-card shadow-pop"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 py-4">
              <div className="flex items-start gap-3">
                <span
                  className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg ${
                    danger ? 'bg-escalate-bg text-escalate-fg' : 'bg-accent-weak text-accent-strong'
                  }`}
                >
                  <AlertTriangle size={16} />
                </span>
                <div className="min-w-0">
                  <div className="text-[15px] font-semibold text-text">{opts.title}</div>
                  {opts.body && <div className="mt-1 text-[12.5px] leading-relaxed text-text-2">{opts.body}</div>}
                </div>
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">
              <button
                type="button"
                onClick={() => close(false)}
                className="rounded-lg border border-line bg-card px-3.5 py-1.5 text-[13px] font-medium text-text-2 hover:bg-page"
              >
                {opts.cancelLabel ?? 'Cancel'}
              </button>
              <button
                type="button"
                onClick={() => close(true)}
                className={`rounded-lg px-3.5 py-1.5 text-[13px] font-semibold text-white ${
                  danger ? 'bg-escalate hover:opacity-90' : 'bg-accent hover:bg-accent-strong'
                }`}
              >
                {opts.confirmLabel ?? 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useConfirm(): (opts: ConfirmOpts) => Promise<boolean> {
  const ctx = useContext(ConfirmContext)
  if (!ctx) throw new Error('useConfirm must be used within ConfirmProvider')
  return ctx.confirm
}
