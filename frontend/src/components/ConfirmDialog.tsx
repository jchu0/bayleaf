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

  // Focus management (UIUX-08): move focus to the confirm button on open, and trap Tab within the
  // panel so keyboard/AT users can't tab out to the page behind the modal overlay.
  const panelRef = useRef<HTMLDivElement>(null)
  const confirmBtnRef = useRef<HTMLButtonElement>(null)

  const close = useCallback((v: boolean) => {
    resolver.current?.(v)
    resolver.current = null
    setOpts(null)
  }, [])

  // Focus the confirm button once the dialog mounts (the primary action, per the a11y spec).
  useEffect(() => {
    if (opts) confirmBtnRef.current?.focus()
  }, [opts])

  // Escape cancels — a deliberate dismissal, never an accidental confirm. Tab is trapped inside the
  // panel (wraps first↔last focusable) so focus never lands behind the overlay.
  useEffect(() => {
    if (!opts) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        close(false)
        return
      }
      if (e.key === 'Tab' && panelRef.current) {
        const focusable = panelRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        )
        if (focusable.length === 0) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
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
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-dialog-title"
            aria-describedby={opts.body ? 'confirm-dialog-body' : undefined}
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
                  <div id="confirm-dialog-title" className="text-[15px] font-semibold text-text">
                    {opts.title}
                  </div>
                  {opts.body && (
                    <div id="confirm-dialog-body" className="mt-1 text-[12.5px] leading-relaxed text-text-2">
                      {opts.body}
                    </div>
                  )}
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
                ref={confirmBtnRef}
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
