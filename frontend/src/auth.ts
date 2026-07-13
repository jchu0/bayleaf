import type { Actor, Role } from './types'

// ─────────────────────────────────────────────────────────────────────────────
// DEMO AUTH — a login gate for the demo, NOT production auth.
//
// This is the single client-side roster of demo accounts + a synchronous credential check. It
// exists so the app can gate access behind a login screen and let a reviewer refine each role
// (viewer / reviewer / approver / admin) by signing in as them. It is deliberately a stub:
//
//   • Passwords are a shared demo constant, compared in the clear. PRODUCTION SEAM: real auth is
//     OAuth/OIDC against an IdP (Google/Okta/…), passwords never reach the client, and any local
//     password would be verified server-side against an argon2/bcrypt hash — never here.
//   • There is no real session token. PRODUCTION SEAM: an httpOnly, Secure, SameSite session
//     cookie (or a short-lived JWT + refresh) issued by the backend; the client would hold none of
//     this. We persist only the chosen demo identity to localStorage so a refresh stays signed in.
//   • CAPTCHA / password-reset / rate-limiting / encryption-in-flight (TLS) are surfaced on the
//     login screen as labelled placeholders, not implemented — see Login.tsx.
//
// The authenticated identity maps to the same RBAC `Actor` ({id, role}) the API already consumes
// via X-Bayleaf-Actor/-Role headers, so login simply chooses which actor the app acts as.
// ─────────────────────────────────────────────────────────────────────────────

export type DemoAccount = {
  id: string
  name: string
  email: string
  role: Role
  // `admin` is a frontend-only governance capability (the Admin panel + "Act as"), layered over the
  // backend roles (viewer|reviewer|approver) without inventing a new wire role. An admin is an
  // approver who also holds governance — distinct from a plain approver who only blesses pipelines.
  admin: boolean
}

// Shared demo password (labelled on the login screen). Never a real secret.
export const DEMO_PASSWORD = 'bayleaf'

// The demo roster — the same actor ids the app + audit trails already use, plus a dedicated admin.
export const DEMO_ACCOUNTS: DemoAccount[] = [
  { id: 'l.santos', name: 'Lia Santos', email: 'l.santos@lab.org', role: 'viewer', admin: false },
  { id: 'a.rivera', name: 'Ada Rivera', email: 'a.rivera@lab.org', role: 'reviewer', admin: false },
  { id: 'm.chen', name: 'Marcus Chen', email: 'm.chen@lab.org', role: 'approver', admin: false },
  { id: 's.ops', name: 'Sam Okonkwo', email: 'admin@lab.org', role: 'approver', admin: true },
]

// Ids that hold the admin governance capability (Admin panel, Act-as). Derived from the roster so
// there is one source of truth; `useRole().isAdmin` reads the acting actor against this set.
export const ADMIN_IDS: ReadonlySet<string> = new Set(DEMO_ACCOUNTS.filter((a) => a.admin).map((a) => a.id))

export function isAdminId(id: string): boolean {
  return ADMIN_IDS.has(id)
}

export type LoginResult = { ok: true; actor: Actor } | { ok: false; error: string }

// Synchronous demo credential check. Case-insensitive email match against the shared demo password.
// PRODUCTION SEAM: this whole function is replaced by an async round-trip to the auth backend.
export function authenticate(email: string, password: string): LoginResult {
  const acct = DEMO_ACCOUNTS.find((a) => a.email.toLowerCase() === email.trim().toLowerCase())
  if (!acct || password !== DEMO_PASSWORD) {
    // One generic message — never reveal whether the email or the password was the miss.
    return { ok: false, error: 'Incorrect email or password.' }
  }
  return { ok: true, actor: { id: acct.id, role: acct.role } }
}

// ── session persistence (demo only) ──────────────────────────────────────────
// We persist ONLY the actor {id, role} so a refresh stays signed in. No token, no password.
const SESSION_KEY = 'bayleaf.session'

export function loadSession(): Actor | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<Actor>
    // Only trust an id that is still a real demo account (roster changes shouldn't strand a session).
    const acct = DEMO_ACCOUNTS.find((a) => a.id === parsed.id)
    return acct ? { id: acct.id, role: acct.role } : null
  } catch {
    return null
  }
}

export function saveSession(actor: Actor | null): void {
  try {
    if (actor) localStorage.setItem(SESSION_KEY, JSON.stringify(actor))
    else localStorage.removeItem(SESSION_KEY)
  } catch {
    // localStorage unavailable (private mode) — the session just won't survive a refresh.
  }
}
