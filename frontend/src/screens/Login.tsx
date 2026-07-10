import { useState } from 'react'
import { useLocation, useNavigate, Navigate } from 'react-router-dom'
import { CheckCircle2, Eye, EyeOff, Info, Lock, Mail, ShieldCheck } from 'lucide-react'
import { useRole } from '../context/RoleContext'
import { useToast } from '../components/Toast'
import { DEMO_ACCOUNTS, DEMO_PASSWORD, type DemoAccount } from '../auth'

// The demo login gate (screen for the whole app's front door). It authenticates against the
// client-side demo roster (auth.ts) and, on success, sets the RBAC actor the API already consumes.
// CAPTCHA, password-reset, and encryption-in-flight are shown as clearly-LABELLED production seams,
// not implemented — see the copy + auth.ts. Nothing here is real security; it gates the demo and
// lets a reviewer refine each role by signing in as viewer / reviewer / approver / admin.

const ROLE_LABEL: Record<DemoAccount['role'], string> = {
  viewer: 'Viewer',
  reviewer: 'Reviewer',
  approver: 'Approver',
}

export function Login() {
  const { login, isAuthenticated } = useRole()
  const { toast } = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [human, setHuman] = useState(false) // CAPTCHA placeholder
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Already signed in → bounce to where they were headed (or the runs list).
  const from = (location.state as { from?: string } | null)?.from ?? '/'
  if (isAuthenticated) return <Navigate to={from} replace />

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!human) {
      setError('Please confirm the human check below.')
      return
    }
    setSubmitting(true)
    // A tiny delay so the demo reads like a real round-trip (the real call is async server-side).
    window.setTimeout(() => {
      const res = login(email, password)
      setSubmitting(false)
      if (res.ok) navigate(from, { replace: true })
      else setError(res.error)
    }, 250)
  }

  function pickDemo(acct: DemoAccount) {
    setEmail(acct.email)
    setPassword(DEMO_PASSWORD)
    setError(null)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-4 py-10">
      <div className="w-full max-w-[400px]">
        {/* Brand */}
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent text-white shadow-card">
            <ShieldCheck size={22} strokeWidth={2} />
          </span>
          <span className="leading-tight">
            <span className="block font-serif text-[20px] font-medium text-text">PipeGuard</span>
            <span className="block text-[10.5px] font-semibold uppercase tracking-[1.2px] text-text-3">
              Decision Gate
            </span>
          </span>
        </div>

        <div className="overflow-hidden rounded-2xl border border-line bg-card shadow-card">
          <form onSubmit={submit} className="flex flex-col gap-3.5 px-6 py-6">
            <div>
              <h1 className="font-serif text-[20px] font-medium text-text">Sign in</h1>
              <p className="mt-0.5 text-[12.5px] text-text-2">Provenance &amp; QC decision gate — operator access.</p>
            </div>

            {error && (
              <div className="rounded-lg border border-escalate-bd bg-escalate-bg px-3 py-2 text-[12px] font-medium text-escalate-fg">
                {error}
              </div>
            )}

            <label className="block">
              <span className="mb-1 block text-[12px] font-medium text-text-2">Email</span>
              <span className="flex items-center gap-2 rounded-lg border border-line bg-card-2 px-2.5 focus-within:border-accent">
                <Mail size={15} className="shrink-0 text-text-3" />
                <input
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@lab.org"
                  className="min-w-0 flex-1 bg-transparent py-2 text-[13px] text-text outline-none placeholder:text-text-3"
                />
              </span>
            </label>

            <label className="block">
              <span className="mb-1 flex items-center justify-between">
                <span className="text-[12px] font-medium text-text-2">Password</span>
                <button
                  type="button"
                  onClick={() =>
                    toast('Password reset is a production seam — real deployments email a signed, expiring reset link.', 'info')
                  }
                  className="text-[11px] text-accent-strong hover:underline"
                >
                  Forgot password?
                </button>
              </span>
              <span className="flex items-center gap-2 rounded-lg border border-line bg-card-2 px-2.5 focus-within:border-accent">
                <Lock size={15} className="shrink-0 text-text-3" />
                <input
                  type={showPw ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="min-w-0 flex-1 bg-transparent py-2 text-[13px] text-text outline-none placeholder:text-text-3"
                />
                <button type="button" onClick={() => setShowPw((v) => !v)} className="shrink-0 text-text-3 hover:text-text-2" aria-label="Toggle password visibility">
                  {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </span>
            </label>

            {/* CAPTCHA placeholder — a labelled stand-in, not a real challenge. */}
            <button
              type="button"
              onClick={() => setHuman((v) => !v)}
              className={`flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left transition-colors ${
                human ? 'border-proceed-bd bg-proceed-bg' : 'border-line bg-card-2 hover:border-line-strong'
              }`}
            >
              <span className={`grid h-[18px] w-[18px] place-items-center rounded border ${human ? 'border-proceed bg-proceed text-white' : 'border-line-strong bg-card'}`}>
                {human && <CheckCircle2 size={14} />}
              </span>
              <span className="flex-1 text-[12px] text-text-2">I'm not a robot</span>
              <span className="text-[9.5px] font-semibold uppercase tracking-[0.4px] text-text-3">CAPTCHA · demo</span>
            </button>

            <button
              type="submit"
              disabled={submitting}
              className="mt-0.5 rounded-lg bg-accent px-3.5 py-2.5 text-[13.5px] font-semibold text-white shadow-card transition-opacity hover:opacity-90 disabled:opacity-60"
            >
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          {/* Demo accounts — one-click sign-in as each role. */}
          <div className="border-t border-line bg-card-2 px-6 py-4">
            <div className="mb-2 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.5px] text-text-3">
              Demo accounts <span className="font-mono normal-case tracking-normal text-text-3">· password “{DEMO_PASSWORD}”</span>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {DEMO_ACCOUNTS.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => pickDemo(a)}
                  className="flex items-center gap-2 rounded-lg border border-line bg-card px-2.5 py-1.5 text-left hover:border-line-strong"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12px] font-medium text-text">{a.name}</span>
                    <span className="block truncate font-mono text-[10px] text-text-3">{a.email}</span>
                  </span>
                  <span className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold ${a.admin ? 'border-accent bg-accent-weak text-accent-strong' : 'border-line bg-card-2 text-text-2'}`}>
                    {a.admin ? 'Admin' : ROLE_LABEL[a.role]}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Security posture — the production seams this demo gate stands in for. */}
        <div className="mt-3.5 flex items-start gap-2 px-1 text-[11px] leading-relaxed text-text-3">
          <Info size={13} className="mt-0.5 shrink-0" />
          <span>
            Demo gate. Production would use OAuth/OIDC (no password on the client), server-side
            argon2/bcrypt verification, an httpOnly session cookie, a real CAPTCHA, signed reset
            links, and TLS in transit. None of that is live here.
          </span>
        </div>
      </div>
    </div>
  )
}
