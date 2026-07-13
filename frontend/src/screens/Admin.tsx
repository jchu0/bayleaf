import { Activity, BarChart3, CheckCircle2, ChevronLeft, ChevronRight, Database, ExternalLink, KeyRound, LineChart, ShieldAlert, ShieldCheck, UserCog } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { AccessEditor } from '../components/AccessEditor'
import { Tabs } from '../components/Tabs'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl, type SegmentOption } from '../components/SegmentedControl'
import { useToast } from '../components/Toast'
import { DEMO_ACCOUNTS, DEMO_PASSWORD } from '../auth'
import { useAccess } from '../context/AccessContext'
import { useRole } from '../context/RoleContext'
import type {
  MetricCatalog,
  PipelineGraph,
  Role,
  RunbookPolicy,
  ThresholdOverride,
  Ticket,
} from '../types'

// Admin panel (approver-gated, off the deterministic gate). Users & roles is an explicit
// client-mock demo flag (there is no backend user store — api/auth.py is a header dev-shim);
// Activity log + System readout are 100% real read endpoints. Admin governs WHO may perform
// off-gate writes + whose id lands in audit fields — it never sets or overrides a verdict,
// finding, or confidence (ADR-0001 / README §8). No confidence meter anywhere.

type Tab = 'users' | 'access' | 'activity' | 'system'

const ROLE_OPTS: { value: Role; label: string }[] = [
  { value: 'viewer', label: 'Viewer' },
  { value: 'reviewer', label: 'Reviewer' },
  { value: 'approver', label: 'Approver' },
]

// Client-mock roster — the SAME demo accounts the login gate authenticates (auth.ts), so "Act as"
// and the sign-in options stay in lockstep. `admin` marks the governance capability.
const SEED_USERS: { id: string; name: string; email: string; role: Role; admin: boolean }[] =
  DEMO_ACCOUNTS.map((a) => ({ id: a.id, name: a.name, email: a.email, role: a.role, admin: a.admin }))

function Avatar({ name }: { name: string }) {
  const initials = name.split(' ').map((p) => p[0]).join('').slice(0, 2)
  return (
    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[linear-gradient(150deg,#3a7,#186)] text-[11px] font-semibold text-white">
      {initials}
    </span>
  )
}

function DemoBanner({ text }: { text: string }) {
  return (
    <div className="mb-3 flex items-center gap-2 rounded-lg border border-hold-bd bg-hold-bg px-3 py-2 text-[12px] text-hold-fg">
      <span className="h-1.5 w-1.5 rounded-full bg-hold" />
      {text}
    </div>
  )
}

// ── Act-as immutable audit (append-only, localStorage) ───────────────────────
// UIC-13a: acting as another user is a high-trust action, so each occurrence is written to an
// append-only log the UI never edits or deletes — it only appends + reads. PRODUCTION SEAM: a real
// build records this server-side in a tamper-evident audit store, and re-auth is an IdP step-up
// (OAuth/OIDC) or a credential-request tool — never the plaintext demo password compared below.
type ActAsEntry = { at: string; actor: string; targetUser: string; targetRole: Role }
const ACTAS_KEY = 'bayleaf.actas-audit'

function loadActAsAudit(): ActAsEntry[] {
  try {
    const raw = localStorage.getItem(ACTAS_KEY)
    return raw ? (JSON.parse(raw) as ActAsEntry[]) : []
  } catch {
    return []
  }
}
function appendActAsAudit(entry: ActAsEntry): void {
  try {
    // Append-only: read → prepend → persist. No code path removes or mutates an existing entry.
    localStorage.setItem(ACTAS_KEY, JSON.stringify([entry, ...loadActAsAudit()]))
  } catch {
    // localStorage unavailable (private mode) — the switch still proceeds; only the durable record is lost.
  }
}

// UIC-13a: a re-authentication gate for "Act as". useConfirm() is boolean-only, so this local modal
// adds the credential entry the boolean confirm cannot capture — it mirrors ConfirmDialog's shell/idiom
// rather than reinventing it. PRODUCTION SEAM: real re-auth is an IdP step-up or a credential-request
// tool; a plaintext password field is a demo-only stand-in and never ships long-term (security guardrail).
function ReAuthModal({
  user,
  onCancel,
  onConfirm,
}: {
  user: { name: string; role: Role }
  onCancel: () => void
  onConfirm: () => void
}) {
  const [pw, setPw] = useState('')
  const [err, setErr] = useState(false)
  const submit = () => {
    if (pw !== DEMO_PASSWORD) {
      setErr(true)
      return
    }
    onConfirm()
  }
  // Escape cancels — a deliberate dismissal, never an accidental impersonation.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-[rgba(16,24,40,.4)] p-6"
      onClick={onCancel}
    >
      <div
        className="w-[440px] max-w-full overflow-hidden rounded-2xl border border-line-strong bg-card shadow-pop"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-4">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-escalate-bg text-escalate-fg">
              <ShieldAlert size={16} />
            </span>
            <div className="min-w-0">
              <div className="text-[15px] font-semibold text-text">Re-authenticate to act as {user.name}</div>
              <p className="mt-1 text-[12.5px] leading-relaxed text-text-2">
                Impersonation is a high-trust action. Subsequent off-gate writes are attributed to{' '}
                {user.name} ({user.role}) and this switch is recorded in an append-only audit entry.
              </p>
            </div>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              submit()
            }}
          >
            <label className="mt-3 block text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">
              Confirm your password
            </label>
            <input
              type="password"
              autoFocus
              value={pw}
              onChange={(e) => {
                setPw(e.target.value)
                setErr(false)
              }}
              placeholder="Demo password"
              className={`mt-1 w-full rounded-lg border bg-card px-3 py-2 text-[13px] text-text outline-none focus:border-accent ${
                err ? 'border-escalate-bd' : 'border-line'
              }`}
            />
            {err && <div className="mt-1 text-[11.5px] text-escalate-fg">Incorrect password. Try again.</div>}
          </form>
          <div className="mt-3 rounded-lg border border-hold-bd bg-hold-bg px-3 py-2 text-[11px] leading-relaxed text-hold-fg">
            <strong>Production seam.</strong> Real re-auth is an identity-provider step-up (OAuth/OIDC)
            or a credential-request tool — never a plaintext password field. The demo compares a shared
            demo password client-side only.
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-line bg-card px-3.5 py-1.5 text-[13px] font-medium text-text-2 hover:bg-page"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!pw}
            className="rounded-lg bg-accent px-3.5 py-1.5 text-[13px] font-semibold text-white hover:bg-accent-strong disabled:opacity-40"
          >
            Re-authenticate &amp; act as
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Per-user edit view (UIC-13b) ─────────────────────────────────────────────
// Role allocation + password recovery moved OFF the inline roster table into this dedicated detail
// view — LOCAL view state in UsersTab, NOT an App.tsx route — so future user-management features have
// a home. Role edits stage behind an explicit Save (UIC-4): the dropdown shows state but only mutates
// the roster on Save. Keyed by user id at the call site, so its draft resets cleanly per user.
function UserDetail({
  user,
  isSelf,
  onBack,
  onSaveRole,
  onResetPassword,
}: {
  user: (typeof SEED_USERS)[number]
  isSelf: boolean
  onBack: () => void
  onSaveRole: (role: Role) => void
  onResetPassword: () => void
}) {
  const [draftRole, setDraftRole] = useState<Role>(user.role)
  const dirty = draftRole !== user.role

  return (
    <div>
      <button
        type="button"
        onClick={onBack}
        className="mb-3 inline-flex items-center gap-1 text-[12.5px] font-medium text-text-2 hover:text-text"
      >
        <ChevronLeft size={15} /> All users
      </button>

      <div className="mb-4 flex items-center gap-3 rounded-xl border border-line bg-card p-4 shadow-card">
        <Avatar name={user.name} />
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[15px] font-semibold text-text">
            {user.name}
            {isSelf && <span className="rounded-full bg-accent px-2 py-px text-[10px] font-semibold text-white">you</span>}
            {user.admin && (
              <span className="rounded-full bg-card-2 px-2 py-px text-[10px] font-semibold text-text-2">admin</span>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-2 font-mono text-[11.5px] text-text-2">
            <span>{user.id}</span>
            <span className="text-text-3">·</span>
            <span>{user.email}</span>
          </div>
        </div>
      </div>

      {/* Role allocation — staged behind an explicit Save (UIC-4). Client-mock: api/auth.py is a header
          shim, so this updates local roster state only, never a backend user store. */}
      <div className="mb-4 rounded-xl border border-line bg-card p-4 shadow-card">
        <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">
          <UserCog size={13} /> Role allocation
        </div>
        <p className="mb-3 text-[12px] leading-relaxed text-text-2">
          Gates only off-gate writes (approvals, tickets). A role change never sets or overrides a verdict.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={draftRole}
            onChange={(e) => setDraftRole(e.target.value as Role)}
            className={`rounded-lg border bg-card px-2.5 py-1.5 text-[13px] text-text outline-none focus:border-accent ${
              dirty ? 'border-hold-bd' : 'border-line'
            }`}
          >
            {ROLE_OPTS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          {dirty && <span className="text-[10px] font-semibold uppercase tracking-[0.3px] text-hold-fg">unsaved</span>}
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => setDraftRole(user.role)}
              disabled={!dirty}
              className="rounded-lg border border-line bg-card px-3 py-1.5 text-[12.5px] font-medium text-text-2 hover:border-line-strong disabled:opacity-40"
            >
              Discard
            </button>
            <button
              type="button"
              onClick={() => onSaveRole(draftRole)}
              disabled={!dirty}
              className="rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white hover:bg-accent-strong disabled:opacity-40"
            >
              Save role
            </button>
          </div>
        </div>
      </div>

      {/* Password & recovery — a labelled production seam (no live mail in the demo). */}
      <div className="rounded-xl border border-line bg-card p-4 shadow-card">
        <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">
          <KeyRound size={13} /> Password &amp; recovery
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={onResetPassword}
            className="rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12.5px] font-medium text-text hover:border-line"
          >
            Send password-reset link
          </button>
          <span className="text-[11.5px] text-text-3">
            Production seam — emails a signed, expiring reset link to {user.email}. No live mail here.
          </span>
        </div>
      </div>
    </div>
  )
}

// ── Users & roles (client-mock) ──────────────────────────────────────────────
function UsersTab() {
  const { actor, session, setActor } = useRole()
  const { toast } = useToast()
  const [users, setUsers] = useState(SEED_USERS)
  // Per-user edit detail (UIC-13b) + the Act-as re-auth gate (UIC-13a) are local view state — no route.
  const [editing, setEditing] = useState<string | null>(null)
  const [reauth, setReauth] = useState<(typeof SEED_USERS)[number] | null>(null)

  // Password/email reset is a production seam — no live mail in the demo. The action toasts what would
  // happen (a signed, expiring reset link emailed to the user).
  const resetPassword = (u: (typeof users)[number]) =>
    toast(`A password-reset link would be emailed to ${u.email} — production seam (no live mail here).`, 'info')

  const saveRole = (id: string, role: Role) => {
    setUsers((us) => us.map((u) => (u.id === id ? { ...u, role } : u)))
    // Keep the live actor in lockstep if its own role was just changed.
    if (id === actor.id && role !== actor.role) setActor({ id, role })
    toast('Role updated (client-mock — dev auth shim).', 'success')
  }

  // Act-as, gated by re-auth (UIC-13a). On success: write the append-only audit entry — attributed to
  // the logged-in admin (session), captured BEFORE the actor switches — then switch the acting actor.
  const confirmActAs = () => {
    const u = reauth
    if (!u) return
    appendActAsAudit({ at: new Date().toISOString(), actor: session?.id ?? actor.id, targetUser: u.id, targetRole: u.role })
    setActor({ id: u.id, role: u.role })
    toast(`Now acting as ${u.name} (${u.role}). Recorded in the audit log.`, 'success')
    setReauth(null)
  }

  const editingUser = editing ? users.find((u) => u.id === editing) ?? null : null

  return (
    <div>
      {editingUser ? (
        <UserDetail
          key={editingUser.id}
          user={editingUser}
          isSelf={editingUser.id === actor.id}
          onBack={() => setEditing(null)}
          onSaveRole={(role) => saveRole(editingUser.id, role)}
          onResetPassword={() => resetPassword(editingUser)}
        />
      ) : (
        <>
          <DemoBanner text="Demo · dev auth shim, not an identity system. Role assignment gates only off-gate writes (approvals, tickets) — never a verdict." />
          <div className="overflow-hidden rounded-xl border border-line bg-card shadow-card">
            <div className="grid grid-cols-[1fr_150px_170px] gap-3 border-b border-line px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">
              <span>User</span>
              <span>Role</span>
              <span className="text-right">Manage</span>
            </div>
            {users.map((u) => {
              const isCurrent = u.id === actor.id
              return (
                <div
                  key={u.id}
                  className={`grid grid-cols-[1fr_150px_170px] items-center gap-3 border-b border-line px-4 py-3 last:border-0 ${
                    isCurrent ? 'bg-accent-weak/40' : ''
                  }`}
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <Avatar name={u.name} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-[13.5px] font-semibold text-text">
                        {u.name}
                        {isCurrent && (
                          <span className="rounded-full bg-accent px-2 py-px text-[10px] font-semibold text-white">you</span>
                        )}
                      </div>
                      <div className="font-mono text-[11.5px] text-text-2">{u.id}</div>
                    </div>
                  </div>
                  <div className="min-w-0">
                    <span className="inline-flex items-center gap-1 rounded-full border border-line bg-card-2 px-2.5 py-0.5 text-[11.5px] font-medium capitalize text-text-2">
                      {u.role}
                      {u.admin && <span className="text-text-3">· admin</span>}
                    </span>
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setEditing(u.id)}
                      className="rounded-lg border border-line-strong bg-card px-3 py-1.5 text-[12px] font-medium text-accent-strong hover:border-line"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => setReauth(u)}
                      disabled={isCurrent}
                      className={`rounded-lg border px-3 py-1.5 text-[12px] font-medium transition-colors ${
                        isCurrent
                          ? 'cursor-default border-line bg-card-2 text-text-3'
                          : 'border-line-strong bg-card text-text hover:border-line'
                      }`}
                    >
                      {isCurrent ? 'Active' : 'Act as'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-text-3">
            Role allocation and password recovery live in each user&apos;s{' '}
            <span className="font-medium text-text-2">Edit</span> view. Acting as another user requires
            re-authentication and is written to an append-only audit entry.
          </p>
        </>
      )}
      {reauth && <ReAuthModal user={reauth} onCancel={() => setReauth(null)} onConfirm={confirmActAs} />}
    </div>
  )
}

// ── Activity log (real endpoints + client-side access feed) ──────────────────
// threshold/pipeline/ticket are backend-persisted; `access` is the client-side page-access
// governance store (localStorage, no backend) merged in and clearly badged — an honest seam.
// `actas` is the client-side, append-only Act-as impersonation log (UIC-13a) merged in alongside the
// page-access feed and clearly badged — a labelled seam, distinct from the backend-persisted kinds.
type FeedKind = 'threshold' | 'pipeline' | 'ticket' | 'access' | 'actas'
type FeedRow = { when: string; actor: string; kind: FeedKind; target: string; detail: string; clientSide?: boolean }

const KIND_STYLE: Record<FeedKind, string> = {
  threshold: 'bg-qc/10 text-qc',
  pipeline: 'bg-variant/10 text-variant',
  ticket: 'bg-preflight/10 text-preflight',
  access: 'bg-hold/10 text-hold-fg',
  actas: 'bg-escalate/10 text-escalate-fg',
}
// Display labels for the kind chip (so `actas` reads as "act-as", not a jammed token).
const KIND_LABEL: Record<FeedKind, string> = {
  threshold: 'threshold',
  pipeline: 'pipeline',
  ticket: 'ticket',
  access: 'access',
  actas: 'act-as',
}

type ActPerPage = '25' | '50' | '100'
const ACT_PER_PAGE: SegmentOption<ActPerPage>[] = [
  { value: '25', label: '25' },
  { value: '50', label: '50' },
  { value: '100', label: '100' },
]
const rowKey = (r: FeedRow) => `${r.when}|${r.kind}|${r.target}|${r.detail}`

function ActivityTab() {
  const { audit } = useAccess()
  const [backendRows, setBackendRows] = useState<FeedRow[] | null>(null)
  // Read the append-only Act-as log once on mount (localStorage). Switching to this tab remounts the
  // component, so a just-recorded impersonation is picked up without shared state.
  const [actAsRows] = useState<ActAsEntry[]>(() => loadActAsAudit())
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | FeedKind>('all')
  const [perPage, setPerPage] = useState<ActPerPage>('25')
  const [page, setPage] = useState(1)
  const [openKey, setOpenKey] = useState<string | null>(null) // one expanded row at a time
  useEffect(() => setPage(1), [filter, perPage])

  useEffect(() => {
    Promise.all([
      api.listThresholds().catch(() => [] as ThresholdOverride[]),
      api.listPipelines().catch(() => [] as PipelineGraph[]),
      api.listTickets().catch(() => [] as Ticket[]),
    ])
      .then(([thresholds, pipelines, tickets]) => {
        const feed: FeedRow[] = []
        for (const t of thresholds) {
          feed.push({
            when: t.created_at,
            actor: t.approved_by ?? t.submitted_by ?? '—',
            kind: 'threshold',
            target: t.name,
            detail: `v${t.version} · ${t.status}`,
          })
        }
        for (const p of pipelines) {
          feed.push({
            when: p.created_at,
            actor: p.approved_by ?? p.submitted_by ?? '—',
            kind: 'pipeline',
            target: p.name,
            detail: `v${p.version} · ${p.status}`,
          })
        }
        for (const tk of tickets) {
          feed.push({
            when: tk.created_at,
            actor: tk.opened_by,
            kind: 'ticket',
            target: `${tk.run_id} · ${tk.sample_id}`,
            detail: `opened · ${tk.title}`,
          })
          for (const a of tk.actions) {
            feed.push({
              when: a.at,
              actor: a.actor,
              kind: 'ticket',
              target: `${tk.run_id} · ${tk.sample_id}`,
              detail: `${a.action} · ${tk.title}`,
            })
          }
        }
        feed.sort((a, b) => (a.when < b.when ? 1 : -1))
        setBackendRows(feed)
      })
      .catch((e) => setError(String(e)))
  }, [])

  // The client-side page-access audit trail (localStorage), merged in as a labelled `access` feed.
  const accessRows = useMemo<FeedRow[]>(
    () =>
      audit.map((a) => ({
        when: a.at,
        actor: a.actor,
        kind: 'access' as const,
        target: a.targetUser === '*' ? 'all users' : a.targetUser,
        detail: a.summary,
        clientSide: true,
      })),
    [audit],
  )
  // The client-side Act-as impersonation trail (localStorage), merged in as a labelled `actas` feed.
  const actasFeed = useMemo<FeedRow[]>(
    () =>
      actAsRows.map((e) => ({
        when: e.at,
        actor: e.actor,
        kind: 'actas' as const,
        target: e.targetUser,
        detail: `Acted as ${e.targetUser} (${e.targetRole})`,
        clientSide: true,
      })),
    [actAsRows],
  )
  const rows = useMemo<FeedRow[] | null>(() => {
    if (backendRows == null) return null
    return [...backendRows, ...accessRows, ...actasFeed].sort((a, b) => (a.when < b.when ? 1 : -1))
  }, [backendRows, accessRows, actasFeed])

  const counts = useMemo(() => {
    const c = { threshold: 0, pipeline: 0, ticket: 0, access: 0, actas: 0 }
    for (const r of rows ?? []) c[r.kind]++
    return c
  }, [rows])
  const shown = (rows ?? []).filter((r) => filter === 'all' || r.kind === filter)
  const per = Number(perPage)
  const total = shown.length
  const pages = Math.max(1, Math.ceil(total / per))
  const curPage = Math.min(page, pages)
  const fromIdx = (curPage - 1) * per
  const paged = shown.slice(fromIdx, fromIdx + per)

  if (error) return <div className="rounded-xl border border-escalate-bd bg-escalate-bg p-6 text-[13px] text-escalate-fg">{error}</div>
  if (!rows) return <div className="rounded-xl border border-line bg-card p-6 text-[13px] text-text-2">Loading activity…</div>

  return (
    <div>
      <p className="mb-3 text-[12.5px] text-text-2">
        Append-only audit trail of off-gate governance — threshold overrides, pipeline versions,
        and review tickets (backend-persisted), plus page-access changes and act-as impersonations
        (client-side stores, badged as such). Read-only; a rules-decided verdict never appears here.
        De-identified share/export (<code>DATA_EXPORTED</code>) egress is audited per-run in that
        run&apos;s Provenance trail, not in this central feed.
      </p>
      <div className="mb-3">
        <Tabs<'all' | FeedKind>
          items={[
            { value: 'all', label: 'All', count: rows.length },
            { value: 'threshold', label: 'Thresholds', count: counts.threshold },
            { value: 'pipeline', label: 'Pipelines', count: counts.pipeline },
            { value: 'ticket', label: 'Tickets', count: counts.ticket },
            { value: 'access', label: 'Access', count: counts.access },
            { value: 'actas', label: 'Act-as', count: counts.actas },
          ]}
          value={filter}
          onChange={setFilter}
        />
      </div>
      {shown.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line-strong bg-card p-10 text-center text-[13px] text-text-2">
          No activity yet. Approvals, pipeline versions, and ticket actions land here.
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-xl border border-line bg-card shadow-card">
            {paged.map((r) => {
              const k = rowKey(r)
              const isOpen = openKey === k
              return (
                <div key={k} className="border-b border-line last:border-0">
                  {/* Compact summary row; click to expand the full detail (so a long entry never
                      makes a formatting mess in the flat list). One row open at a time. */}
                  <button
                    onClick={() => setOpenKey(isOpen ? null : k)}
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-card-2"
                  >
                    <ChevronRight size={13} className={`shrink-0 text-text-3 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                    <span className={`shrink-0 rounded-md px-2 py-0.5 text-[10.5px] font-semibold uppercase ${KIND_STYLE[r.kind]}`}>
                      {KIND_LABEL[r.kind]}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[13px] text-text">{r.detail}</span>
                    {r.clientSide && (
                      <span className="hidden shrink-0 rounded bg-card-2 px-1.5 py-0.5 text-[10px] font-medium text-text-3 sm:inline">
                        client-side
                      </span>
                    )}
                    <span className="hidden font-mono text-[11.5px] text-text-2 md:block">{r.actor}</span>
                    <span className="w-[150px] shrink-0 text-right font-mono text-[11px] text-text-3">{fmtWhen(r.when)}</span>
                  </button>
                  {isOpen && (
                    <dl className="grid grid-cols-[90px_1fr] gap-x-3 gap-y-1.5 border-t border-line bg-card-2 px-4 py-3 text-[12px]">
                      <dt className="text-text-3">Detail</dt>
                      <dd className="text-text">{r.detail}</dd>
                      <dt className="text-text-3">Target</dt>
                      <dd className="font-mono text-text-2">{r.target}</dd>
                      <dt className="text-text-3">Actor</dt>
                      <dd className="font-mono text-text-2">{r.actor}</dd>
                      <dt className="text-text-3">When</dt>
                      <dd className="font-mono text-text-2">{fmtWhen(r.when)}</dd>
                    </dl>
                  )}
                </div>
              )
            })}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="text-[12px] text-text-2">
              Showing {fromIdx + 1}–{Math.min(fromIdx + per, total)} of {total}
            </span>
            <div className="ml-auto flex items-center gap-3">
              <SegmentedControl<ActPerPage> options={ACT_PER_PAGE} value={perPage} onChange={setPerPage} />
              {pages > 1 && (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={curPage <= 1}
                    className="rounded-md border border-line px-2 py-1 text-[12px] text-text-2 hover:border-line-strong disabled:opacity-40"
                  >
                    ‹
                  </button>
                  <span className="px-1 font-mono text-[12px] text-text-2">
                    {curPage} / {pages}
                  </span>
                  <button
                    onClick={() => setPage((p) => Math.min(pages, p + 1))}
                    disabled={curPage >= pages}
                    className="rounded-md border border-line px-2 py-1 text-[12px] text-text-2 hover:border-line-strong disabled:opacity-40"
                  >
                    ›
                  </button>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function fmtWhen(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

// ── System readout (real reads) ──────────────────────────────────────────────
function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-line bg-card p-4 shadow-card">
      <div className="text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">{label}</div>
      <div className="mt-1 font-mono text-[19px] font-semibold text-text">{value}</div>
      {sub && <div className="mt-0.5 text-[12px] text-text-2">{sub}</div>}
    </div>
  )
}

function SystemTab() {
  const [runbook, setRunbook] = useState<RunbookPolicy | null>(null)
  const [registry, setRegistry] = useState<MetricCatalog | null>(null)
  const [health, setHealth] = useState<string | null>(null)

  useEffect(() => {
    api.runbook().then(setRunbook).catch(() => setRunbook(null))
    api.metricsRegistry().then(setRegistry).catch(() => setRegistry(null))
    api.health().then((h) => setHealth(h.status)).catch(() => setHealth('unreachable'))
  }, [])

  // Observability endpoints (the deploy/telemetry docker-compose stack). Off the offline demo path,
  // so these are links, not embeds (Grafana blocks framing, and they're only up when the compose
  // stack runs). The API base swaps :5173→:8010 in dev so /metrics resolves to the read-API.
  const apiBase = `${window.location.protocol}//${window.location.hostname}:8010`
  const OBS = [
    { label: 'Prometheus /metrics', href: `${apiBase}/metrics`, icon: Activity, note: 'read-API exporter · runs · samples · cards · gate-flagged' },
    { label: 'Prometheus', href: 'http://localhost:9090', icon: LineChart, note: 'scrapes the /metrics seam · :9090' },
    { label: 'Grafana', href: 'http://localhost:3000', icon: BarChart3, note: 'bayleaf — QC decision gate dashboard · :3000' },
  ]

  return (
    <div>
      <p className="mb-3 text-[12.5px] text-text-2">
        Read-only posture from the live read-API. Thresholds are illustrative policy, not clinical
        cutoffs.
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="API health"
          value={health ?? '…'}
          sub={health === 'ok' ? 'read-API reachable' : undefined}
        />
        <StatCard
          label="Runbook"
          value={runbook ? `${runbook.thresholds.length} gates` : '…'}
          sub="QC threshold policy"
        />
        <StatCard
          label="Metric registry"
          value={registry ? `v${registry.metric_registry_version}` : '…'}
          sub={registry ? `${registry.n_gated}/${registry.n_registered} gated` : undefined}
        />
        <StatCard label="Artifact store" value="local" sub="BAYLEAF_ARTIFACT_STORE · s3 seam" />
      </div>

      {/* Observability — the telemetry stack views (Prometheus/Grafana) surfaced from here. */}
      <div className="mt-5">
        <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">
          <Database size={13} /> Observability
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          {OBS.map((o) => {
            const Icon = o.icon
            return (
              <a
                key={o.label}
                href={o.href}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-2.5 rounded-xl border border-line bg-card p-3.5 shadow-card hover:border-line-strong"
              >
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-card-2 text-text-2">
                  <Icon size={15} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1 text-[13px] font-semibold text-text">
                    {o.label} <ExternalLink size={11} className="text-text-3" />
                  </span>
                  <span className="mt-0.5 block text-[11.5px] leading-snug text-text-2">{o.note}</span>
                </span>
              </a>
            )
          })}
        </div>
        <p className="mt-2 text-[11px] text-text-3">
          Prometheus/Grafana require the telemetry stack:{' '}
          <span className="font-mono">docker compose -f deploy/telemetry/docker-compose.yml up</span> — off the
          offline demo path. The read-API always serves <span className="font-mono">/metrics</span>.
        </p>
      </div>

      {runbook && (
        <div className="mt-4 rounded-xl border border-line bg-card-2 px-4 py-3 text-[12px] leading-relaxed text-text-2">
          {runbook.disclaimer}
        </div>
      )}
    </div>
  )
}

export function Admin() {
  const { isAdmin } = useRole()
  const [tab, setTab] = useState<Tab>('users')
  // Route guard: the nav hides Admin for non-admins, but the /admin URL is directly reachable —
  // refuse it here too (defense in depth). The real backend authz still lives in api/auth.py.
  if (!isAdmin) {
    return (
      <div className="mx-auto max-w-md rounded-xl border border-line bg-card p-8 text-center shadow-card">
        <ShieldCheck size={26} className="mx-auto text-text-3" />
        <div className="mt-2 text-[15px] font-semibold text-text">Admin access required</div>
        <p className="mt-1 text-[12.5px] text-text-2">
          Sign in as an admin account to manage users, roles, and system posture.
        </p>
      </div>
    )
  }
  const tabOptions = [
    { value: 'users' as const, label: <TabLabel icon={<UserCog size={13} />} text="Users & roles" /> },
    { value: 'access' as const, label: <TabLabel icon={<KeyRound size={13} />} text="Page access" /> },
    { value: 'activity' as const, label: <TabLabel icon={<Activity size={13} />} text="Activity log" /> },
    { value: 'system' as const, label: <TabLabel icon={<CheckCircle2 size={13} />} text="System" /> },
  ]
  return (
    <div className="mx-auto max-w-[1080px]">
      {/* UIC-1: no eyebrow/subtitle flavor — the nav names the page. The "never a verdict" limitation
          it used to carry lives in each tab's DemoBanner / posture note. */}
      <PageHeader title="Admin" actions={<ShieldCheck size={20} className="text-text-3" />} />
      <div className="mb-5">
        <SegmentedControl<Tab> options={tabOptions} value={tab} onChange={setTab} />
      </div>
      {tab === 'users' && <UsersTab />}
      {tab === 'access' && <AccessEditor />}
      {tab === 'activity' && <ActivityTab />}
      {tab === 'system' && <SystemTab />}
    </div>
  )
}

function TabLabel({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {icon}
      {text}
    </span>
  )
}
