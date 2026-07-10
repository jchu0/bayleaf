import { Activity, CheckCircle2, ShieldCheck, UserCog } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { FacetChip } from '../components/FacetChip'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
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

type Tab = 'users' | 'activity' | 'system'

const ROLE_OPTS: { value: Role; label: string }[] = [
  { value: 'viewer', label: 'Viewer' },
  { value: 'reviewer', label: 'Reviewer' },
  { value: 'approver', label: 'Approver' },
]

// Client-mock roster, seeded from the real actor ids the app + audit trails use.
const SEED_USERS: { id: string; name: string; email: string; role: Role }[] = [
  { id: 'a.rivera', name: 'Ada Rivera', email: 'a.rivera@lab.org', role: 'reviewer' },
  { id: 'm.chen', name: 'Marcus Chen', email: 'm.chen@lab.org', role: 'approver' },
  { id: 'p.okafor', name: 'Priya Okafor', email: 'p.okafor@lab.org', role: 'reviewer' },
  { id: 'l.santos', name: 'Lia Santos', email: 'l.santos@lab.org', role: 'viewer' },
]

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

// ── Users & roles (client-mock) ──────────────────────────────────────────────
function UsersTab() {
  const { actor, setActor } = useRole()
  const [users, setUsers] = useState(SEED_USERS)

  const setUserRole = (id: string, role: Role) => {
    setUsers((us) => us.map((u) => (u.id === id ? { ...u, role } : u)))
    if (id === actor.id) setActor({ id, role }) // keep the live actor in sync if it's the current one
  }

  return (
    <div>
      <DemoBanner text="Demo · dev auth shim, not an identity system. Role assignment gates only off-gate writes (approvals, tickets) — never a verdict." />
      <div className="overflow-hidden rounded-xl border border-line bg-card shadow-card">
        <div className="grid grid-cols-[1fr_180px_120px] gap-3 border-b border-line px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.4px] text-text-3">
          <span>User</span>
          <span>Role</span>
          <span className="text-right">Act as</span>
        </div>
        {users.map((u) => {
          const isCurrent = u.id === actor.id
          return (
            <div
              key={u.id}
              className={`grid grid-cols-[1fr_180px_120px] items-center gap-3 border-b border-line px-4 py-3 last:border-0 ${
                isCurrent ? 'bg-accent-weak/40' : ''
              }`}
            >
              <div className="flex min-w-0 items-center gap-2.5">
                <Avatar name={u.name} />
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-[13.5px] font-semibold text-text">
                    {u.name}
                    {isCurrent && (
                      <span className="rounded-full bg-accent px-2 py-px text-[10px] font-semibold text-white">
                        you
                      </span>
                    )}
                  </div>
                  <div className="font-mono text-[11.5px] text-text-2">{u.id}</div>
                </div>
              </div>
              <SegmentedControl<Role>
                options={ROLE_OPTS}
                value={u.role}
                onChange={(r) => setUserRole(u.id, r)}
              />
              <div className="text-right">
                <button
                  onClick={() => setActor({ id: u.id, role: u.role })}
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
    </div>
  )
}

// ── Activity log (real endpoints) ────────────────────────────────────────────
type FeedKind = 'threshold' | 'pipeline' | 'ticket'
type FeedRow = { when: string; actor: string; kind: FeedKind; target: string; detail: string }

const KIND_STYLE: Record<FeedKind, string> = {
  threshold: 'bg-qc/10 text-qc',
  pipeline: 'bg-variant/10 text-variant',
  ticket: 'bg-preflight/10 text-preflight',
}

function ActivityTab() {
  const [rows, setRows] = useState<FeedRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | FeedKind>('all')

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
        setRows(feed)
      })
      .catch((e) => setError(String(e)))
  }, [])

  const counts = useMemo(() => {
    const c = { threshold: 0, pipeline: 0, ticket: 0 }
    for (const r of rows ?? []) c[r.kind]++
    return c
  }, [rows])
  const shown = (rows ?? []).filter((r) => filter === 'all' || r.kind === filter)

  if (error) return <div className="rounded-xl border border-escalate-bd bg-escalate-bg p-6 text-[13px] text-escalate-fg">{error}</div>
  if (!rows) return <div className="rounded-xl border border-line bg-card p-6 text-[13px] text-text-2">Loading activity…</div>

  return (
    <div>
      <p className="mb-3 text-[12.5px] text-text-2">
        Append-only audit trail of off-gate governance — threshold overrides, pipeline versions,
        and review tickets. Read-only; a rules-decided verdict never appears here.
      </p>
      <div className="mb-3 flex flex-wrap gap-2">
        <FacetChip label="All" count={rows.length} active={filter === 'all'} onClick={() => setFilter('all')} />
        <FacetChip label="Thresholds" count={counts.threshold} active={filter === 'threshold'} onClick={() => setFilter('threshold')} />
        <FacetChip label="Pipelines" count={counts.pipeline} active={filter === 'pipeline'} onClick={() => setFilter('pipeline')} />
        <FacetChip label="Tickets" count={counts.ticket} active={filter === 'ticket'} onClick={() => setFilter('ticket')} />
      </div>
      {shown.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line-strong bg-card p-10 text-center text-[13px] text-text-2">
          No activity yet. Approvals, pipeline versions, and ticket actions land here.
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-line bg-card shadow-card">
          {shown.map((r, i) => (
            <div key={i} className="flex items-center gap-3 border-b border-line px-4 py-2.5 last:border-0">
              <span className={`rounded-md px-2 py-0.5 text-[10.5px] font-semibold uppercase ${KIND_STYLE[r.kind]}`}>
                {r.kind}
              </span>
              <span className="min-w-0 flex-1 truncate text-[13px] text-text">{r.detail}</span>
              <span className="hidden font-mono text-[11.5px] text-text-2 sm:block">{r.target}</span>
              <span className="font-mono text-[11.5px] text-text-2">{r.actor}</span>
              <span className="w-[150px] shrink-0 text-right font-mono text-[11px] text-text-3">
                {fmtWhen(r.when)}
              </span>
            </div>
          ))}
        </div>
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

  return (
    <div>
      <p className="mb-3 text-[12.5px] text-text-2">
        Read-only posture from the live read-API. Thresholds are illustrative policy, not clinical
        cutoffs.
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
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
      </div>
      {runbook && (
        <div className="mt-3 rounded-xl border border-line bg-card-2 px-4 py-3 text-[12px] leading-relaxed text-text-2">
          {runbook.disclaimer}
        </div>
      )}
    </div>
  )
}

export function Admin() {
  const [tab, setTab] = useState<Tab>('users')
  const tabOptions = [
    { value: 'users' as const, label: <TabLabel icon={<UserCog size={13} />} text="Users & roles" /> },
    { value: 'activity' as const, label: <TabLabel icon={<Activity size={13} />} text="Activity log" /> },
    { value: 'system' as const, label: <TabLabel icon={<CheckCircle2 size={13} />} text="System" /> },
  ]
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        eyebrow="Governance"
        title="Admin"
        subtitle="Manage users and their RBAC roles, review the off-gate audit trail, and read system posture. Admin never sets or overrides a verdict."
        actions={<ShieldCheck size={20} className="text-text-3" />}
      />
      <div className="mb-5">
        <SegmentedControl<Tab> options={tabOptions} value={tab} onChange={setTab} />
      </div>
      {tab === 'users' && <UsersTab />}
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
