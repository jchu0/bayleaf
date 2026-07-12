import { AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import { createContext, type ReactNode, useCallback, useContext, useState } from 'react'

// Minimal toast system so off-gate writes surface their real backend outcome (403/409/422/503)
// instead of silently diverging. Screens call useToast().toast(msg, kind) in their write handlers.
type ToastKind = 'success' | 'error' | 'info'
type ToastItem = { id: number; kind: ToastKind; message: string }
type ToastCtx = { toast: (message: string, kind?: ToastKind) => void }

const Ctx = createContext<ToastCtx | null>(null)
let _seq = 0

const STYLE: Record<ToastKind, string> = {
  success: 'border-proceed-bd bg-proceed-bg text-proceed-fg',
  error: 'border-escalate-bd bg-escalate-bg text-escalate-fg',
  info: 'border-line-strong bg-card text-text',
}
const ICON: Record<ToastKind, typeof Info> = {
  success: CheckCircle2,
  error: AlertTriangle,
  info: Info,
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const toast = useCallback((message: string, kind: ToastKind = 'info') => {
    const id = ++_seq
    setToasts((t) => [...t, { id, kind, message }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500)
  }, [])

  return (
    <Ctx.Provider value={{ toast }}>
      {children}
      {/* aria-live region (UIUX-05) so screen readers announce the backend outcomes this component
          exists to surface. The container is polite; error toasts opt into role="alert" (assertive)
          so a failure interrupts, while success/info wait for a pause. */}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed bottom-5 right-5 z-[100] flex max-w-[360px] flex-col gap-2"
      >
        {toasts.map((t) => {
          const I = ICON[t.kind]
          return (
            <div
              key={t.id}
              role={t.kind === 'error' ? 'alert' : undefined}
              className={`pg-fade pointer-events-auto flex items-start gap-2 rounded-lg border px-3.5 py-2.5 text-[13px] leading-snug shadow-pop ${STYLE[t.kind]}`}
            >
              <I size={16} className="mt-px shrink-0" />
              <span>{t.message}</span>
            </div>
          )
        })}
      </div>
    </Ctx.Provider>
  )
}

// Co-located with its provider by design.
// eslint-disable-next-line react-refresh/only-export-components
export function useToast(): ToastCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useToast must be used within <ToastProvider>')
  return c
}
